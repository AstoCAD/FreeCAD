// SPDX-License-Identifier: LGPL-2.1-or-later

#include "UserParameters.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>
#include <set>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectPy.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/PropertyExpressionEngine.h>
#include <App/PropertyLinks.h>
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

bool isLiteral(const Expression* expr);

/// The unit of a number as the parser builds it: `mm`, `m/s`, `mm^2`, `m^-1`.
bool isUnit(const Expression* expr)
{
    if (freecad_cast<const UnitExpression*>(expr)) {
        return !freecad_cast<const VariableExpression*>(expr);
    }
    const auto* op = freecad_cast<const OperatorExpression*>(expr);
    if (!op) {
        return false;
    }
    switch (op->getOperator()) {
        case OperatorExpression::MUL:
        case OperatorExpression::DIV:
            return isUnit(op->getLeft()) && isUnit(op->getRight());
        case OperatorExpression::POW:
            return isUnit(op->getLeft()) && isLiteral(op->getRight());
        default:
            return false;
    }
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
        case OperatorExpression::MUL:
        case OperatorExpression::DIV:
            // `9.81 m/s^2` is read as (9.81 m) / (s^2)
            return isLiteral(op->getLeft()) && isUnit(op->getRight());
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
    // The only property type not named after its unit type (TimeSpan).
    if (unit == Base::Unit::TimeSpan) {
        return PropertyTime::getClassTypeId();
    }
    // The unit must come from the property type: a plain PropertyQuantity does not save its unit.
    // A unit without a property type of its own (a concentration, m^5) has none.
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

namespace
{

/// Throw unless a user parameter @p name can be typed in @p owner.
void checkNewParameter(const DocumentObject* owner, const std::string& name)
{
    // A deleted object kept for undo still knows its document but is no longer part of it.
    if (!owner || !owner->isAttachedToDocument() || !owner->getDocument()) {
        throw Base::RuntimeError("Invalid owner for a user parameter");
    }
    const auto status = UserParameters::checkName(owner->getDocument(), name, owner);
    if (status != UserParameters::NameStatus::Available) {
        throw Base::NameError(UserParameters::nameStatusMessage(status, name));
    }
}

/// Add the empty user parameter @p name of the property type @p type, see checkNewParameter().
Property*
addCheckedParameter(DocumentObject* owner, const std::string& name, const Base::Type& type)
{
    using namespace UserParameters;
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

}  // namespace

Property*
UserParameters::addParameter(DocumentObject* owner, const std::string& name, const Base::Unit& unit)
{
    checkNewParameter(owner, name);
    const Base::Type type = propertyTypeForUnit(unit);
    if (type.isBad()) {
        throw Base::TypeError("No property type for the unit '" + unit.getString() + "'");
    }
    return addCheckedParameter(owner, name, type);
}

Property* UserParameters::createParameter(
    DocumentObject* owner,
    const std::string& name,
    const std::shared_ptr<Expression>& value,
    const Base::Unit& impliedUnit,
    ValueKind accepted
)
{
    if (!value) {
        throw Base::ValueError("No value for the user parameter");
    }
    // Evaluate first: a failing value must leave the owner unchanged.
    const ExpressionPtr result = value->eval();
    const auto* number = freecad_cast<NumberExpression*>(result.get());
    const auto* text = accepted == ValueKind::NumberOrText
        ? freecad_cast<StringExpression*>(result.get())
        : nullptr;
    if (!number && !text) {
        throw Base::TypeError(
            accepted == ValueKind::NumberOrText
                ? "A user parameter needs a number, a quantity or a text"
                : "A user parameter needs a numeric value"
        );
    }

    Document* doc = owner ? owner->getDocument() : nullptr;
    const bool hadHolder = findHolder(doc) != nullptr;
    Property* prop = nullptr;
    bool literal = false;
    if (number) {
        const Base::Quantity quantity = number->getQuantity();
        const Base::Unit unit = quantity.isDimensionless() ? impliedUnit : quantity.getUnit();
        prop = addParameter(owner, name, unit);
        literal = isLiteral(value.get());
    }
    else {
        checkNewParameter(owner, name);
        prop = addCheckedParameter(owner, name, PropertyString::getClassTypeId());
        literal = freecad_cast<StringExpression*>(value.get()) != nullptr;
    }
    auto* target = freecad_cast<DocumentObject*>(prop->getContainer());
    try {
        if (!literal) {
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
        if (number) {
            // Every numeric parameter type derives from PropertyFloat; the value is in
            // internal units.
            static_cast<PropertyFloat*>(prop)->setValue(number->getQuantity().getValue());
        }
        else {
            static_cast<PropertyString*>(prop)->setValue(text->getText());
        }
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

namespace
{

/// Import names a copy of the holder after it: `UserParameters` when the document has no object
/// of that name, else `UserParameters001`...
bool isHolderCopyName(const char* name)
{
    const std::size_t length = std::strlen(UserParameters::HolderName);
    if (!name || std::strncmp(name, UserParameters::HolderName, length) != 0) {
        return false;
    }
    const std::string suffix(name + length);
    return std::all_of(suffix.begin(), suffix.end(), [](unsigned char c) {
        return std::isdigit(c) != 0;
    });
}

/// The copy of a holder among freshly pasted objects, or nullptr.
DocumentObject* pastedHolder(const std::vector<DocumentObject*>& pasted)
{
    for (auto* obj : pasted) {
        if (obj && obj->isAttachedToDocument() && obj->isDerivedFrom<VarSet>()
            && isHolderCopyName(obj->getNameInDocument())) {
            return obj;
        }
    }
    return nullptr;
}

/// The holder that the document had before @p copy was pasted, or nullptr.
DocumentObject* holderBeforePaste(const DocumentObject* copy)
{
    DocumentObject* existing = UserParameters::findHolder(copy->getDocument());
    return existing == copy ? nullptr : existing;
}

std::vector<std::string> parameterNames(const DocumentObject* obj)
{
    std::vector<std::string> names;
    for (const auto& name : obj->getDynamicPropertyNames()) {
        if (UserParameters::isUserParameter(obj->getDynamicPropertyByName(name.c_str()))) {
            names.push_back(name);
        }
    }
    return names;
}

/// Add to @p names the properties of @p copy that the expressions of @p obj name. With @p only,
/// just the expressions bound to those properties of @p obj.
void addNamedProperties(
    const DocumentObject* obj,
    const DocumentObject* copy,
    const std::set<std::string>* only,
    std::set<std::string>& names
)
{
    std::vector<Property*> props;
    obj->getPropertyList(props);
    for (const auto* prop : props) {
        const auto* container = freecad_cast<const PropertyExpressionContainer*>(prop);
        if (!container) {
            continue;
        }
        for (const auto& [path, expr] : container->getExpressions()) {
            if (!expr || (only && only->count(path.getPropertyName()) == 0)) {
                continue;
            }
            for (const auto& [id, hidden] : expr->getIdentifiers()) {
                const Property* named = id.getProperty();
                if (named && named->getContainer() == copy) {
                    names.insert(named->getName());
                }
            }
        }
    }
}

/// The user parameters of @p copy that the other pasted objects use, with the parameters that
/// those are computed from. All of them when the holder was pasted alone.
std::set<std::string>
usedParameters(const DocumentObject* copy, const std::vector<DocumentObject*>& pasted)
{
    const std::vector<std::string> all = parameterNames(copy);
    std::set<std::string> used;
    bool alone = true;
    for (const auto* obj : pasted) {
        if (obj && obj != copy && obj->isAttachedToDocument()) {
            alone = false;
            addNamedProperties(obj, copy, nullptr, used);
        }
    }
    if (alone) {
        return {all.begin(), all.end()};
    }
    for (std::size_t count = 0; count != used.size();) {
        count = used.size();
        const std::set<std::string> known = used;
        addNamedProperties(copy, copy, &known, used);
    }
    std::set<std::string> result;
    for (const auto& name : all) {
        if (used.count(name) != 0) {
            result.insert(name);
        }
    }
    return result;
}

Base::Quantity quantityOf(const Property* prop)
{
    if (const auto* quantity = freecad_cast<const PropertyQuantity*>(prop)) {
        return quantity->getQuantityValue();
    }
    if (const auto* number = freecad_cast<const PropertyFloat*>(prop)) {
        return Base::Quantity(number->getValue());
    }
    return {};
}

/// The value of the parameter @p prop as shown to the user.
std::string valueText(const Property* prop)
{
    if (const auto* text = freecad_cast<const PropertyString*>(prop)) {
        return text->getStrValue();
    }
    return quantityOf(prop).getUserString();
}

/// True when the parameter @p pasted cannot stand for @p existing: another type or value.
bool differs(const Property* existing, const Property* pasted)
{
    if (existing->getTypeId() != pasted->getTypeId()) {
        return true;
    }
    if (const auto* text = freecad_cast<const PropertyString*>(existing)) {
        return text->getStrValue() != static_cast<const PropertyString*>(pasted)->getStrValue();
    }
    const double a = quantityOf(existing).getValue();
    const double b = quantityOf(pasted).getValue();
    return std::fabs(a - b) > 1e-9 * std::max({1.0, std::fabs(a), std::fabs(b)});
}

std::string freeName(const Document* doc, const std::string& name)
{
    for (int i = 2;; ++i) {
        std::string candidate = name + "_" + std::to_string(i);
        if (UserParameters::checkName(doc, candidate) == UserParameters::NameStatus::Available) {
            return candidate;
        }
    }
}

/// Makes what an expression names of @p copy a property of @p target, the owner of the
/// rewritten expression: `UserParameters001.width` and `width` of the copy become `width`.
class OwnPropertyVisitor: public ExpressionVisitor
{
public:
    OwnPropertyVisitor(const DocumentObject* copy, const DocumentObject* target)
        : copy(copy)
        , target(target)
    {}

    void visit(Expression& expr) override
    {
        auto* var = freecad_cast<VariableExpression*>(&expr);
        if (!var) {
            return;
        }
        ObjectIdentifier path = var->getPath();
        const Property* prop = path.getProperty();
        if (!prop || prop->getContainer() != copy) {
            return;
        }
        int index = 0;
        path.getPropertyComponent(0, &index);
        ObjectIdentifier own(target);
        const auto& components = path.getComponents();
        for (std::size_t i = index; i < components.size(); ++i) {
            own << components[i];
        }
        var->setPath(own);
    }

private:
    const DocumentObject* copy;
    const DocumentObject* target;
};

/// Re-point what @p obj links to @p from, expressions included, to @p to.
void replaceLinks(DocumentObject* obj, DocumentObject* from, DocumentObject* to)
{
    std::vector<Property*> props;
    obj->getPropertyList(props);
    for (auto* prop : props) {
        auto* link = freecad_cast<PropertyLinkBase*>(prop);
        if (!link) {
            continue;
        }
        std::unique_ptr<Property> replaced(link->CopyOnLinkReplace(obj, from, to));
        if (replaced) {
            prop->Paste(*replaced);
        }
    }
}

}  // namespace

std::vector<UserParameters::PastedConflict>
UserParameters::pastedConflicts(const std::vector<DocumentObject*>& pasted)
{
    std::vector<PastedConflict> conflicts;
    const DocumentObject* copy = pastedHolder(pasted);
    const DocumentObject* target = copy ? holderBeforePaste(copy) : nullptr;
    if (!target) {
        return conflicts;
    }
    for (const auto& name : usedParameters(copy, pasted)) {
        const Property* existing = target->getPropertyByName(name.c_str());
        const Property* source = copy->getDynamicPropertyByName(name.c_str());
        if (existing && source && differs(existing, source)) {
            conflicts.push_back({name, valueText(existing), valueText(source)});
        }
    }
    return conflicts;
}

void UserParameters::mergePasted(std::vector<DocumentObject*>& pasted, PastePolicy policy)
{
    DocumentObject* copy = pastedHolder(pasted);
    if (!copy) {
        return;
    }
    Document* doc = copy->getDocument();
    const std::set<std::string> used = usedParameters(copy, pasted);
    DocumentObject* target = holderBeforePaste(copy);
    pasted.erase(std::remove(pasted.begin(), pasted.end(), copy), pasted.end());

    if (!target) {
        // The copy is the holder of the document, unless another kind of object has the name
        // of the holder: then the copy is left as a variable set of its own.
        if (isHolder(copy)) {
            for (const auto& name : parameterNames(copy)) {
                if (used.count(name) == 0) {
                    removeParameter(copy->getDynamicPropertyByName(name.c_str()));
                }
            }
        }
        return;
    }

    std::set<std::string> added;
    for (const auto& name : used) {
        Property* source = copy->getDynamicPropertyByName(name.c_str());
        if (!source) {
            continue;
        }
        std::string finalName = name;
        if (const Property* existing = target->getPropertyByName(name.c_str())) {
            if (policy == PastePolicy::UseExisting || !differs(existing, source)) {
                continue;
            }
            // The expressions that name the parameter follow the rename.
            finalName = freeName(doc, name);
            if (!copy->renameDynamicProperty(source, finalName.c_str())) {
                continue;
            }
            source = copy->getDynamicPropertyByName(finalName.c_str());
        }
        Property* prop = source
            ? target->addDynamicProperty(source->getTypeId().getName(), finalName.c_str(), GroupName)
            : nullptr;
        if (prop) {
            prop->Paste(*source);
            added.insert(finalName);
        }
    }

    // Once every parameter is there: an expression may name the other ones.
    for (const auto& [path, expr] : copy->ExpressionEngine.getExpressions()) {
        const std::string name = path.getPropertyName();
        Property* prop = added.count(name) != 0 ? target->getDynamicPropertyByName(name.c_str())
                                                : nullptr;
        if (!prop || !expr) {
            continue;
        }
        try {
            // Written for the target: what names a parameter of the copy names the parameter
            // of the target, so that the target never depends on the copy.
            const ExpressionPtr local = expr->copy();
            OwnPropertyVisitor visitor(copy, target);
            local->visit(visitor);
            const std::shared_ptr<Expression> moved(
                ExpressionParser::parse(target, local->toString().c_str())
            );
            target->setExpression(ObjectIdentifier(*prop), moved);
        }
        catch (const Base::Exception& e) {
            // The parameter keeps the value it had
            e.reportException();
        }
    }

    for (auto* obj : pasted) {
        if (obj && obj->isAttachedToDocument()) {
            replaceLinks(obj, copy, target);
        }
    }
    // Something else than expressions may link to the copy: then it stays. A parameter
    // computed from another one makes the copy link to itself.
    const auto users = copy->getInList();
    if (std::all_of(users.begin(), users.end(), [copy](const DocumentObject* user) {
            return user == copy;
        })) {
        doc->removeObject(copy->getNameInDocument());
    }
}
