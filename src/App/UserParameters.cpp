// SPDX-License-Identifier: LGPL-2.1-or-later

#include "UserParameters.h"

#include <algorithm>
#include <cctype>
#include <cstring>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectPy.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/PropertyStandard.h>
#include <App/PropertyUnits.h>
#include <App/Range.h>
#include <App/VarSet.h>
#include <Base/Exception.h>
#include <Base/Interpreter.h>
#include <Base/Quantity.h>
#include <Base/Tools.h>
#include <CXX/Objects.hxx>

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

/// True when @p name is an attribute or a method of the Python type of @p owner, the object
/// that gets the parameter, or of every document object when there is none yet. Python looks a
/// property up before the attributes of the type (PropertyContainerPy::getCustomAttributes), so a
/// property of that name would hide the attribute: `obj.Name` would return the value of the
/// parameter.
bool isPythonAttribute(const DocumentObject* owner, const std::string& name)
{
    Base::PyGILStateLocker lock;
    PyTypeObject* type = &DocumentObjectPy::Type;
    Py::Object pyOwner;
    if (owner) {
        pyOwner = Py::asObject(const_cast<DocumentObject*>(owner)->getPyObject());
        type = Py_TYPE(pyOwner.ptr());
    }
    // The attribute tables of the type and of its bases are searched, as Python does once the
    // properties are passed. Asking the object would find the properties and run the getter of
    // the attribute, asking the type object would also find the attributes of types (`mro`).
    PyObject* bases = type->tp_mro;
    if (!bases) {
        return false;
    }
    for (Py_ssize_t i = 0; i < PyTuple_GET_SIZE(bases); ++i) {
        const auto* base = reinterpret_cast<PyTypeObject*>(PyTuple_GET_ITEM(bases, i));
        if (base->tp_dict && PyDict_GetItemString(base->tp_dict, name.c_str())) {
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
    explicit QualifyVisitor(const std::function<bool(const std::string&)>& keepsMeaning)
        : keepsMeaning(keepsMeaning)
    {}

    void visit(Expression& expr) override
    {
        auto* var = freecad_cast<VariableExpression*>(&expr);
        if (!var) {
            return;
        }
        ObjectIdentifier path = var->getPath();
        DocumentObject* holder = parameterHolder(path);
        if (!holder) {
            return;
        }
        // parameterHolder() only accepts a path that starts with the name of the parameter.
        if (keepsMeaning && keepsMeaning(path.getComponents()[0].getName())) {
            return;
        }
        path.setDocumentObjectName(holder, true);
        var->setPath(path);
        ++count;
    }

    int count {0};

private:
    const std::function<bool(const std::string&)>& keepsMeaning;
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

/// Gives what an expression names from its owner the name of that owner, so that the text of
/// the expression means the same for another object: `Length` typed in a Pad is `Pad.Length`.
class OwnerQualifyVisitor: public ExpressionVisitor
{
public:
    OwnerQualifyVisitor(const DocumentObject* owner, const DocumentObject* target)
        : owner(owner)
        , target(target)
    {}

    void visit(Expression& expr) override
    {
        auto* var = freecad_cast<VariableExpression*>(&expr);
        if (!var) {
            return;
        }
        ObjectIdentifier path = var->getPath();
        // `Length` and `.Length`; `Other.Length` already says whose property it is.
        if (path.getOwner() != owner
            || (path.hasDocumentObjectName() && !path.isLocalProperty())) {
            return;
        }
        const Property* prop = path.getProperty();
        if (!prop || prop->getContainer() != owner) {
            return;
        }
        // Written as seen from the target: an identifier does not write the name of its own
        // owner, the text would still be `Length`.
        ObjectIdentifier qualified(target);
        qualified.setDocumentObjectName(owner, true);
        for (const auto& component : path.getComponents()) {
            qualified << component;
        }
        var->setPath(qualified);
    }

private:
    const DocumentObject* owner;
    const DocumentObject* target;
};

/// @p value, an expression of @p owner, as an expression of @p target with the same meaning.
std::shared_ptr<Expression>
expressionFor(DocumentObject* target, const DocumentObject* owner, const Expression& value)
{
    std::shared_ptr<Expression> expr(value.copy());
    if (target == owner) {
        return expr;
    }
    UserParameters::qualifyReferences(owner, *expr);
    OwnerQualifyVisitor visitor(owner, target);
    expr->visit(visitor);
    return std::shared_ptr<Expression>(
        ExpressionParser::parse(target, expr->toString(true).c_str())
    );
}

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

bool UserParameters::isHolder(const DocumentObject* obj)
{
    return obj && obj->isAttachedToDocument() && obj->isDerivedFrom<VarSet>()
        && std::strcmp(obj->getNameInDocument(), HolderName) == 0;
}

DocumentObject* UserParameters::findHolder(const Document* doc)
{
    DocumentObject* obj = doc ? doc->getObject(HolderName) : nullptr;
    return isHolder(obj) ? obj : nullptr;
}

DocumentObject* UserParameters::holder(Document* doc)
{
    if (!doc) {
        throw Base::RuntimeError("No document for the user parameters");
    }
    if (DocumentObject* existing = findHolder(doc)) {
        return existing;
    }
    if (doc->getObject(HolderName)) {
        throw Base::RuntimeError(
            std::string("The object '") + HolderName
            + "' is not a variable set: it cannot hold the user parameters"
        );
    }
    DocumentObject* created = doc->addObject(VarSet::getClassTypeId().getName(), HolderName);
    if (!created) {
        throw Base::RuntimeError("Cannot create the object holding the user parameters");
    }
    created->Label.setValue(HolderLabel);
    return created;
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
    // The parameter is a property of the holder; before the holder exists, of a variable set
    // like any other, which has the attributes of every document object.
    const DocumentObject* holderObject = findHolder(doc);
    if (isPythonAttribute(holderObject, name)) {
        return NameStatus::PythonAttribute;
    }
    if (!doc) {
        return NameStatus::Available;
    }
    for (const auto* obj : doc->getObjects()) {
        if (isUserParameter(obj->getDynamicPropertyByName(name.c_str()))) {
            return NameStatus::UsedByParameter;
        }
    }
    // The holder has this name, also the one that the first parameter is going to create.
    if (hasObjectNamed(doc, name) || name == HolderName) {
        return NameStatus::UsedByObject;
    }
    if ((owner && owner->getPropertyByName(name.c_str()))
        || (holderObject && holderObject->getPropertyByName(name.c_str()))) {
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
        case NameStatus::PythonAttribute:
            return "'" + name
                + "' is an attribute of the object in Python and cannot name a user parameter";
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
    Document* doc = owner->getDocument();
    const bool hadHolder = findHolder(doc) != nullptr;
    DocumentObject* target = holder(doc);
    try {
        // A new holder has the properties of every variable set: the name was only checked
        // against those of a holder that existed.
        if (!hadHolder && target->getPropertyByName(name.c_str())) {
            throw Base::NameError(nameStatusMessage(NameStatus::UsedByOwnerProperty, name));
        }
        Property* prop = target->addDynamicProperty(type.getName(), name.c_str(), GroupName);
        if (!prop) {
            throw Base::RuntimeError("Cannot add the user parameter '" + name + "'");
        }
        return prop;
    }
    catch (...) {
        if (!hadHolder) {
            doc->removeObject(target->getNameInDocument());
        }
        throw;
    }
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

    Document* doc = owner ? owner->getDocument() : nullptr;
    const bool hadHolder = findHolder(doc) != nullptr;
    Property* prop = addParameter(owner, name, unit);
    auto* target = freecad_cast<DocumentObject*>(prop->getContainer());
    try {
        if (!isLiteral(value.get())) {
            const ObjectIdentifier path(*prop);
            const std::shared_ptr<Expression> expr = expressionFor(target, owner, *value);
            if (!expr) {
                throw Base::ValueError("Invalid value for the user parameter");
            }
            const std::string error = target->ExpressionEngine.validateExpression(path, expr);
            if (!error.empty()) {
                throw Base::RuntimeError(error);
            }
            target->setExpression(path, expr);
        }
        // Every parameter type derives from PropertyFloat; the value is in internal units.
        static_cast<PropertyFloat*>(prop)->setValue(quantity.getValue());
    }
    catch (...) {
        target->ExpressionEngine.setValue(ObjectIdentifier(*prop), std::shared_ptr<Expression>());
        target->removeDynamicProperty(name.c_str());
        if (!hadHolder) {
            doc->removeObject(target->getNameInDocument());
        }
        throw;
    }
    return prop;
}

std::shared_ptr<Expression>
UserParameters::referenceTo(const DocumentObject* owner, const Property* parameter)
{
    if (!owner || !isUserParameter(parameter)) {
        return nullptr;
    }
    const auto* container = freecad_cast<const DocumentObject*>(parameter->getContainer());
    if (!container || !container->isAttachedToDocument()
        || container->getDocument() != owner->getDocument()) {
        return nullptr;
    }
    std::string text = parameter->getName();
    if (container != owner) {
        text = std::string(container->getNameInDocument()) + "." + text;
    }
    return std::shared_ptr<Expression>(ExpressionParser::parse(owner, text.c_str()));
}

bool UserParameters::removeParameter(Property* parameter)
{
    if (!isUserParameter(parameter) || !parameter->testStatus(Property::PropDynamic)) {
        return false;
    }
    auto* container = freecad_cast<DocumentObject*>(parameter->getContainer());
    if (!container) {
        return false;
    }
    // By value: the property is gone once removed.
    const std::string name = parameter->getName();
    container->ExpressionEngine.setValue(ObjectIdentifier(*parameter), std::shared_ptr<Expression>());
    return container->removeDynamicProperty(name.c_str());
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
    return qualifyReferences(owner, expr, {});
}

int UserParameters::qualifyReferences(
    const DocumentObject* owner,
    Expression& expr,
    const std::function<bool(const std::string& name)>& keepsMeaning
)
{
    if (!owner || !owner->getDocument()) {
        return 0;
    }
    QualifyVisitor visitor(keepsMeaning);
    expr.visit(visitor);
    return visitor.count;
}

namespace
{
thread_local UserParameters::PendingScope* innermostPendingScope = nullptr;
}  // namespace

UserParameters::PendingScope::PendingScope(
    const DocumentObject* owner,
    std::vector<PendingParameter> parameters
)
    : owner(owner)
    , parameters(std::move(parameters))
    , outer(innermostPendingScope)
{
    innermostPendingScope = this;
}

UserParameters::PendingScope::~PendingScope()
{
    innermostPendingScope = outer;
}

const Base::Quantity* UserParameters::PendingScope::find(const ObjectIdentifier& path)
{
    const DocumentObject* owner = path.getOwner();
    if (!owner || !innermostPendingScope) {
        return nullptr;
    }
    // A bare name only, as typed for a user parameter (see parameterHolder())
    if (path.hasDocumentObjectName() || path.isLocalProperty()
        || !path.getSubObjectName().empty()) {
        return nullptr;
    }
    const auto& components = path.getComponents();
    if (components.size() != 1 || !components[0].isSimple()) {
        return nullptr;
    }
    const std::string& name = components[0].getName();
    for (const PendingScope* scope = innermostPendingScope; scope; scope = scope->outer) {
        if (scope->owner != owner) {
            continue;
        }
        for (const auto& parameter : scope->parameters) {
            if (parameter.name == name) {
                return &parameter.value;
            }
        }
    }
    return nullptr;
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
