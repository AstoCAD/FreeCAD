// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <memory>
#include <string>
#include <vector>

#include <FCGlobal.h>

#include <Base/Type.h>
#include <Base/Unit.h>

namespace App
{
class Document;
class DocumentObject;
class Expression;
class Property;

/**
 * User parameters: named values that the user creates while typing an expression.
 *
 * Typing `myVar = 23 mm` in an expression-capable input creates the dynamic property `myVar`
 * in the group `UserParameters` of the object owning the edited property, and binds the edited
 * property to it. The names of the properties in `UserParameters` groups are unique in a
 * document, so typing `myVar` anywhere in that document refers to that parameter.
 *
 * References are resolved when the user enters an expression and are stored qualified
 * (`Holder.myVar`), which is plain expression syntax: existing expressions keep their meaning
 * and files remain readable by any FreeCAD version. A bare identifier is only looked up as a user
 * parameter when it does not resolve the usual way.
 */
namespace UserParameters
{

/// Name of the property group holding user parameters.
constexpr const char* GroupName = "UserParameters";

enum class NameStatus
{
    Available,
    /// Not an identifier, or a unit, a constant or a reserved name.
    Invalid,
    /// Another user parameter of the document already has this name.
    UsedByParameter,
    /// A document object has this name or label.
    UsedByObject,
    /// The owner already has a property with this name.
    UsedByOwnerProperty,
    /// The name is a spreadsheet cell address (`B5`, `AA12`): in a spreadsheet formula it names
    /// the cell, even an empty one, so the parameter could not be referred to from there.
    CellAddress
};

/// True when @p name is a spreadsheet cell address such as `A1` or `ZZ16384`: one or two
/// capital letters and a row number in range (the syntax of App::CellAddress, without `$`).
AppExport bool isCellAddressName(const std::string& name);

/// True when @p prop belongs to the group @ref GroupName.
AppExport bool isUserParameter(const Property* prop);

/// All user parameters of @p doc, in object order.
AppExport std::vector<Property*> getParameters(const Document* doc);

/// The user parameter named @p name in @p doc, or nullptr if there is none or more than one.
AppExport Property* findParameter(const Document* doc, const std::string& name);

/// Check whether a new user parameter @p name can be created on @p owner in @p doc.
AppExport NameStatus
checkName(const Document* doc, const std::string& name, const DocumentObject* owner = nullptr);

/// An English message explaining @p status, for user interfaces.
AppExport std::string nameStatusMessage(NameStatus status, const std::string& name);

/// The property type used for a parameter holding a value of @p unit: PropertyFloat when
/// dimensionless, PropertyDistance for lengths (signed), else the App::Property<UnitType> class.
/// Base::Type::BadType when no property type stores that unit.
AppExport Base::Type propertyTypeForUnit(const Base::Unit& unit);

/// Add an empty user parameter. Throws Base::NameError when the name is not available and
/// Base::TypeError when no property type stores @p unit.
AppExport Property*
addParameter(DocumentObject* owner, const std::string& name, const Base::Unit& unit);

/**
 * Create the user parameter @p name on @p owner from @p value.
 *
 * @p value is parsed with @p owner as owner. A literal value is assigned as value, any other
 * expression is bound to the new property. A dimensionless value takes @p impliedUnit.
 * Throws (Base::NameError, Base::ValueError, Base::RuntimeError) and leaves the owner unchanged
 * on failure.
 */
AppExport Property* createParameter(
    DocumentObject* owner,
    const std::string& name,
    const std::shared_ptr<Expression>& value,
    const Base::Unit& impliedUnit = Base::Unit::One
);

/// Rename the user parameter @p prop, checking that @p newName is available. As for any dynamic
/// property, the expressions referring to it follow the rename. Throws Base::NameError.
AppExport bool rename(Property* prop, const std::string& newName);

/**
 * Split user input of the form `name = expression`.
 *
 * Returns false when @p text is not an assignment. A single `=` is not part of the expression
 * grammar, so no valid expression is an assignment.
 */
AppExport bool splitAssignment(const std::string& text, std::string& name, std::string& rhs);

/**
 * Qualify the identifiers of @p expr that name a user parameter of another object.
 *
 * Only identifiers that do not resolve the usual way from @p owner are changed, to
 * `Holder.name`. Returns the number of changed identifiers.
 */
AppExport int qualifyReferences(const DocumentObject* owner, Expression& expr);

/// The text of @p expr with qualified user parameter references shortened back to their name
/// wherever the short name refers to the same parameter.
AppExport std::string toDisplayString(const DocumentObject* owner, const Expression& expr);

}  // namespace UserParameters
}  // namespace App
