// SPDX-License-Identifier: LGPL-2.1-or-later

#include "UserParameters.h"

#include <algorithm>
#include <cctype>
#include <cstring>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/PropertyStandard.h>
#include <App/PropertyUnits.h>
#include <App/Range.h>
#include <Base/Exception.h>
#include <Base/Quantity.h>
#include <Base/Tools.h>

using namespace App;

namespace
{

bool hasObjectNamed(const Document* doc, const std::string& name)
{
    if (doc->getObject(name.c_str())) {
        return true;
    }
    for (const auto* obj : doc->getObjects()) {
        if (name == obj->Label.getValue()) {
            return true;
        }
    }
    return false;
}

/// The object holding the user parameter that the bare identifier @p path refers to, or nullptr
/// when @p path is not a bare identifier, resolves the usual way, or names no unique parameter.
DocumentObject* parameterHolder(const ObjectIdentifier& path)
{
    const DocumentObject* owner = path.getOwner();
    if (!owner || !owner->getDocument()) {
        return nullptr;
    }
    if (path.hasDocumentObjectName() || path.isLocalProperty()
        || !path.getSubObjectName().empty()) {
        return nullptr;
    }
    const auto& components = path.getComponents();
    if (components.empty() || !components[0].isSimple()) {
        return nullptr;
    }
    // Existing meaning first: owner properties, `Object.property` and pseudo properties win.
    if (path.getProperty()) {
        return nullptr;
    }
    const std::string& name = components[0].getName();
    const Document* doc = owner->getDocument();
    if (components.size() > 1 && hasObjectNamed(doc, name)) {
        return nullptr;
    }
    Property* param = UserParameters::findParameter(doc, name);
    if (!param) {
        return nullptr;
    }
    auto* holder = freecad_cast<DocumentObject*>(param->getContainer());
    if (!holder || holder == owner) {
        return nullptr;
    }
    return holder;
}

class QualifyVisitor: public ExpressionVisitor
{
public:
    void visit(Expression& expr) override
    {
        auto* var = freecad_cast<VariableExpression*>(&expr);
        if (!var) {
            return;
        }
        ObjectIdentifier path = var->getPath();
        if (DocumentObject* holder = parameterHolder(path)) {
            path.setDocumentObjectName(holder, true);
            var->setPath(path);
            ++count;
        }
    }

    int count {0};
};

class ShortenVisitor: public ExpressionVisitor
{
public:
    void visit(Expression& expr) override
    {
        auto* var = freecad_cast<VariableExpression*>(&expr);
        if (!var) {
            return;
        }
        ObjectIdentifier path = var->getPath();
        const DocumentObject* owner = path.getOwner();
        Property* prop = owner ? path.getProperty() : nullptr;
        if (!prop || !UserParameters::isUserParameter(prop) || !path.getSubObjectName().empty()) {
            return;
        }
        auto* holder = freecad_cast<DocumentObject*>(prop->getContainer());
        if (!holder || holder == owner || holder->getDocument() != owner->getDocument()) {
            return;
        }
        int index = 0;
        path.getPropertyComponent(0, &index);
        ObjectIdentifier shortPath(owner);
        const auto& components = path.getComponents();
        for (std::size_t i = index; i < components.size(); ++i) {
            shortPath << components[i];
        }
        // Only shorten when typing the short form back gives the very same reference.
        if (parameterHolder(shortPath) == holder) {
            var->setPath(shortPath);
        }
    }
};

bool isLiteral(const Expression* expr)
{
    if (freecad_cast<const NumberExpression*>(expr)) {
        return true;
    }
    const auto* op = freecad_cast<const OperatorExpression*>(expr);
    if (!op) {
        return false;
    }
    switch (op->getOperator()) {
        case OperatorExpression::UNIT:
            return isLiteral(op->getLeft()) && freecad_cast<const UnitExpression*>(op->getRight())
                && !freecad_cast<const VariableExpression*>(op->getRight());
        case OperatorExpression::NEG:
        case OperatorExpression::POS:
            return isLiteral(op->getLeft());
        default:
            return false;
    }
}

}  // namespace

bool UserParameters::isUserParameter(const Property* prop)
{
    if (!prop || !prop->getContainer()) {
        return false;
    }
    const char* group = prop->getGroup();
    return group && std::strcmp(group, GroupName) == 0;
}

std::vector<Property*> UserParameters::getParameters(const Document* doc)
{
    std::vector<Property*> result;
    if (!doc) {
        return result;
    }
    for (const auto* obj : doc->getObjects()) {
        for (const auto& name : obj->getDynamicPropertyNames()) {
            Property* prop = obj->getDynamicPropertyByName(name.c_str());
            if (isUserParameter(prop)) {
                result.push_back(prop);
            }
        }
    }
    return result;
}

Property* UserParameters::findParameter(const Document* doc, const std::string& name)
{
    if (!doc || name.empty()) {
        return nullptr;
    }
    Property* found = nullptr;
    for (const auto* obj : doc->getObjects()) {
        Property* prop = obj->getDynamicPropertyByName(name.c_str());
        if (!isUserParameter(prop)) {
            continue;
        }
        if (found) {
            // Not unique (e.g. after copying the holder): refuse to guess.
            return nullptr;
        }
        found = prop;
    }
    return found;
}

UserParameters::NameStatus
UserParameters::checkName(const Document* doc, const std::string& name, const DocumentObject* owner)
{
    if (name.empty() || name[0] == '_' || Base::Tools::getIdentifier(name) != name
        || !ExpressionParser::isTokenAnIndentifier(name)) {
        return NameStatus::Invalid;
    }
    if (isCellAddressName(name)) {
        return NameStatus::CellAddress;
    }
    if (!doc) {
        return NameStatus::Available;
    }
    for (const auto* obj : doc->getObjects()) {
        if (isUserParameter(obj->getDynamicPropertyByName(name.c_str()))) {
            return NameStatus::UsedByParameter;
        }
    }
    if (hasObjectNamed(doc, name)) {
        return NameStatus::UsedByObject;
    }
    if (owner && owner->getPropertyByName(name.c_str())) {
        return NameStatus::UsedByOwnerProperty;
    }
    return NameStatus::Available;
}

std::string UserParameters::nameStatusMessage(NameStatus status, const std::string& name)
{
    switch (status) {
        case NameStatus::Available:
            return {};
        case NameStatus::Invalid:
            return "'" + name
                + "' is not a valid parameter name (use letters, digits and '_', not a unit or a "
                  "constant)";
        case NameStatus::UsedByParameter:
            return "A user parameter named '" + name + "' already exists in this document";
        case NameStatus::UsedByObject:
            return "An object of this document is named or labeled '" + name + "'";
        case NameStatus::UsedByOwnerProperty:
            return "The object already has a property named '" + name + "'";
        case NameStatus::CellAddress:
            return "'" + name
                + "' is a spreadsheet cell address and cannot name a user parameter";
    }
    return {};
}

bool UserParameters::isCellAddressName(const std::string& name)
{
    // Same rule as Spreadsheet::PropertySheet::isValidCellAddressName (without the `$` of
    // absolute references, which is not part of an identifier).
    std::size_t letters = 0;
    while (letters < name.size() && name[letters] >= 'A' && name[letters] <= 'Z') {
        ++letters;
    }
    const std::size_t digits = name.size() - letters;
    if (letters < 1 || letters > 2 || digits < 1 || digits > 5) {
        return false;
    }
    const std::string row = name.substr(letters);
    if (!std::all_of(row.begin(), row.end(), [](char c) { return c >= '0' && c <= '9'; })) {
        return false;
    }
    return validRow(row) >= 0 && validColumn(name.substr(0, letters));
}

Base::Type UserParameters::propertyTypeForUnit(const Base::Unit& unit)
{
    if (unit == Base::Unit::One) {
        return PropertyFloat::getClassTypeId();
    }
    // A parameter is a free value: use the signed distance rather than the non-negative length.
    if (unit == Base::Unit::Length) {
        return PropertyDistance::getClassTypeId();
    }
    // The unit must come from the property type: a plain PropertyQuantity does not save its unit.
    const std::string unitType = unit.getTypeString();
    if (!unitType.empty()) {
        const std::string typeName = "App::Property" + unitType;
        const Base::Type type = Base::Type::fromName(typeName.c_str());
        if (!type.isBad() && type.isDerivedFrom(PropertyQuantity::getClassTypeId())) {
            return type;
        }
    }
    return Base::Type::BadType;
}

Property*
UserParameters::addParameter(DocumentObject* owner, const std::string& name, const Base::Unit& unit)
{
    // A deleted object kept for undo still knows its document but is no longer part of it.
    if (!owner || !owner->isAttachedToDocument() || !owner->getDocument()) {
        throw Base::RuntimeError("Invalid owner for a user parameter");
    }
    const NameStatus status = checkName(owner->getDocument(), name, owner);
    if (status != NameStatus::Available) {
        throw Base::NameError(nameStatusMessage(status, name));
    }
    const Base::Type type = propertyTypeForUnit(unit);
    if (type.isBad()) {
        throw Base::TypeError("No property type for the unit '" + unit.getString() + "'");
    }
    return owner->addDynamicProperty(type.getName(), name.c_str(), GroupName);
}

Property* UserParameters::createParameter(
    DocumentObject* owner,
    const std::string& name,
    const std::shared_ptr<Expression>& value,
    const Base::Unit& impliedUnit
)
{
    if (!value) {
        throw Base::ValueError("No value for the user parameter");
    }
    // Evaluate first: a failing value must leave the owner unchanged.
    const ExpressionPtr result = value->eval();
    const auto* number = freecad_cast<NumberExpression*>(result.get());
    if (!number) {
        throw Base::TypeError("A user parameter needs a numeric value");
    }
    const Base::Quantity quantity = number->getQuantity();
    const Base::Unit unit = quantity.isDimensionless() ? impliedUnit : quantity.getUnit();

    Property* prop = addParameter(owner, name, unit);
    try {
        if (!isLiteral(value.get())) {
            const ObjectIdentifier path(*prop);
            std::shared_ptr<Expression> expr(value->copy());
            const std::string error = owner->ExpressionEngine.validateExpression(path, expr);
            if (!error.empty()) {
                throw Base::RuntimeError(error);
            }
            owner->setExpression(path, expr);
        }
        // Every parameter type derives from PropertyFloat; the value is in internal units.
        static_cast<PropertyFloat*>(prop)->setValue(quantity.getValue());
    }
    catch (...) {
        owner->ExpressionEngine.setValue(ObjectIdentifier(*prop), std::shared_ptr<Expression>());
        owner->removeDynamicProperty(name.c_str());
        throw;
    }
    return prop;
}

bool UserParameters::rename(Property* prop, const std::string& newName)
{
    if (!isUserParameter(prop) || !prop->testStatus(Property::PropDynamic)
        || prop->testStatus(Property::LockDynamic)) {
        return false;
    }
    auto* owner = freecad_cast<DocumentObject*>(prop->getContainer());
    Document* doc = owner && owner->isAttachedToDocument() ? owner->getDocument() : nullptr;
    if (!doc) {
        return false;
    }
    const std::string oldName = prop->getName();
    if (oldName == newName) {
        return true;
    }
    const NameStatus status = checkName(doc, newName, owner);
    if (status != NameStatus::Available) {
        throw Base::NameError(nameStatusMessage(status, newName));
    }
    // Renaming a dynamic property also renames the references to it in every expression
    // (PropertyExpressionEngine::onRenameDynamicProperty), qualified ones included.
    return owner->renameDynamicProperty(prop, newName.c_str());
}

bool UserParameters::splitAssignment(const std::string& text, std::string& name, std::string& rhs)
{
    const auto isSpace = [](char c) {
        return std::isspace(static_cast<unsigned char>(c)) != 0;
    };
    std::size_t pos = 0;
    while (pos < text.size() && isSpace(text[pos])) {
        ++pos;
    }
    const std::size_t start = pos;
    while (pos < text.size() && !isSpace(text[pos]) && text[pos] != '=') {
        ++pos;
    }
    const std::string candidate = text.substr(start, pos - start);
    while (pos < text.size() && isSpace(text[pos])) {
        ++pos;
    }
    // A single '=' only: '==' is the comparison operator.
    if (pos >= text.size() || text[pos] != '=' || (pos + 1 < text.size() && text[pos + 1] == '=')) {
        return false;
    }
    if (candidate.empty() || Base::Tools::getIdentifier(candidate) != candidate) {
        return false;
    }
    std::size_t first = pos + 1;
    std::size_t last = text.size();
    while (first < last && isSpace(text[first])) {
        ++first;
    }
    while (last > first && isSpace(text[last - 1])) {
        --last;
    }
    if (first == last) {
        return false;
    }
    name = candidate;
    rhs = text.substr(first, last - first);
    return true;
}

int UserParameters::qualifyReferences(const DocumentObject* owner, Expression& expr)
{
    if (!owner || !owner->getDocument()) {
        return 0;
    }
    QualifyVisitor visitor;
    expr.visit(visitor);
    return visitor.count;
}

std::string UserParameters::toDisplayString(const DocumentObject* owner, const Expression& expr)
{
    if (!owner || !owner->getDocument()) {
        return expr.toString();
    }
    try {
        ExpressionPtr copy = expr.copy();
        ShortenVisitor visitor;
        copy->visit(visitor);
        return copy->toString();
    }
    catch (const Base::Exception&) {
        // Display only: never fail where the plain text would have been shown.
        return expr.toString();
    }
}
