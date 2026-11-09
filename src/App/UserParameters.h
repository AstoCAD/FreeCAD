// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>

#include <FCGlobal.h>

#include <Base/Quantity.h>
#include <Base/Type.h>
#include <Base/Unit.h>

namespace App
{
class Document;
class DocumentObject;
class Expression;
class ObjectIdentifier;
class Property;

/**
 * User parameters: named values that the user creates while typing an expression.
 *
 * Typing `myVar = 23 mm` in an expression-capable input creates the dynamic property `myVar`
 * in the group `UserParameters` of the holder of the document, and binds the edited property to
 * it. The holder is one variable set per document (@ref HolderName), created with the first
 * parameter: it depends on no other object unless a parameter is given an expression that does,
 * so every object can use every parameter without a cyclic dependency, and deleting or copying
 * the object in which a parameter was typed leaves the parameter alone.
 *
 * The names of the properties in `UserParameters` groups are unique in a document, so typing
 * `myVar` anywhere in that document refers to that parameter. Documents made before the holder
 * existed have such properties on the objects in which they were typed: they are user parameters
 * all the same.
 *
 * References are resolved when the user enters an expression and are stored qualified
 * (`UserParameters.myVar`), which is plain expression syntax: existing expressions keep their
 * meaning and files remain readable by any FreeCAD version. A bare identifier is only looked up
 * as a user parameter when it does not resolve the usual way.
 */
namespace UserParameters
{

/// Name of the property group holding user parameters.
constexpr const char* GroupName = "UserParameters";
/// Internal name of the object holding the user parameters of a document.
constexpr const char* HolderName = "UserParameters";
/// Label given to the holder when it is created.
constexpr const char* HolderLabel = "User Parameters";

enum class NameStatus
{
    Available,
    /// Not an identifier, or a unit, a constant or a reserved name.
    Invalid,
    /// Another user parameter of the document already has this name.
    UsedByParameter,
    /// A document object has this name or label.
    UsedByObject,
    /// The object in which the name is typed, or the holder of the user parameters, already
    /// has a property with this name.
    UsedByOwnerProperty,
    /// The name is a spreadsheet cell address (`B5`, `AA12`): in a spreadsheet formula it names
    /// the cell, even an empty one, so the parameter could not be referred to from there.
    CellAddress,
    /// The name is an attribute or a method of the Python object of the holder (`Name`,
    /// `Document`, `recompute`...): a property of that name would hide it from Python.
    PythonAttribute
};

/// True when @p name is a spreadsheet cell address such as `A1` or `ZZ16384`: one or two
/// capital letters and a row number in range (the syntax of App::CellAddress, without `$`).
AppExport bool isCellAddressName(const std::string& name);

/// True when @p prop belongs to the group @ref GroupName.
AppExport bool isUserParameter(const Property* prop);

/// True when @p obj is the holder of the user parameters of its document.
AppExport bool isHolder(const DocumentObject* obj);

/// The holder of the user parameters of @p doc, or nullptr when it has none yet.
AppExport DocumentObject* findHolder(const Document* doc);

/// The holder of the user parameters of @p doc, created when the document has none. Throws
/// Base::RuntimeError when another kind of object has taken its name.
AppExport DocumentObject* holder(Document* doc);

/// All user parameters of @p doc, in object order.
AppExport std::vector<Property*> getParameters(const Document* doc);

/// The user parameter named @p name in @p doc, or nullptr if there is none or more than one.
AppExport Property* findParameter(const Document* doc, const std::string& name);

/// Check whether a new user parameter @p name can be created in @p doc. @p owner is the object
/// in which the name is typed, if any: a name of one of its properties means that property there,
/// so the parameter could not be referred to from it.
AppExport NameStatus
checkName(const Document* doc, const std::string& name, const DocumentObject* owner = nullptr);

/// An English message explaining @p status, for user interfaces.
AppExport std::string nameStatusMessage(NameStatus status, const std::string& name);

/// The property type used for a parameter holding a value of @p unit: PropertyFloat when
/// dimensionless, PropertyDistance for lengths (signed), else the App::Property<UnitType> class.
/// Base::Type::BadType when no property type stores that unit.
AppExport Base::Type propertyTypeForUnit(const Base::Unit& unit);

/// Add an empty user parameter to the holder of the document of @p owner, the object in which
/// the name is typed. Throws Base::NameError when the name is not available and Base::TypeError
/// when no property type stores @p unit.
AppExport Property*
addParameter(DocumentObject* owner, const std::string& name, const Base::Unit& unit);

/// What the value of a new user parameter may be.
enum class ValueKind
{
    /// A number or a quantity: what the input of a quantity can use.
    Number,
    /// Also a text (`<<text>>`), which is stored in a PropertyString.
    NumberOrText
};

/**
 * Create the user parameter @p name from @p value, on the holder of the document of @p owner.
 *
 * @p owner is the object in which the parameter is typed and @p value is parsed with it as
 * owner. A literal value is assigned as value, any other expression is bound to the new property,
 * with what it names from @p owner written as seen from the holder (`Length` typed in a Pad is
 * `Pad.Length`). A dimensionless value takes @p impliedUnit. The holder is created when the
 * document has none. A text is a value only where @p accepted says so: a parameter typed in the
 * input of a quantity has to be one.
 * Throws (Base::NameError, Base::TypeError, Base::ValueError, Base::RuntimeError) and leaves the
 * document unchanged on failure.
 */
AppExport Property* createParameter(
    DocumentObject* owner,
    const std::string& name,
    const std::shared_ptr<Expression>& value,
    const Base::Unit& impliedUnit = Base::Unit::One,
    ValueKind accepted = ValueKind::Number
);

/// An expression of @p owner that is the user parameter @p parameter, to bind a property of
/// @p owner to it. nullptr when @p parameter is no user parameter of the document of @p owner.
AppExport std::shared_ptr<Expression>
referenceTo(const DocumentObject* owner, const Property* parameter);

/// Remove the user parameter @p parameter with the expression bound to it. Returns false when
/// @p parameter is no user parameter or cannot be removed.
AppExport bool removeParameter(Property* parameter);

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

/**
 * As above, for an owner to which some names mean something although they do not resolve as a
 * property (an empty spreadsheet cell): the identifiers for which @p keepsMeaning returns true
 * are not changed.
 */
AppExport int qualifyReferences(
    const DocumentObject* owner,
    Expression& expr,
    const std::function<bool(const std::string& name)>& keepsMeaning
);

/// The text of @p expr with qualified user parameter references shortened back to their name
/// wherever the short name refers to the same parameter.
AppExport std::string toDisplayString(const DocumentObject* owner, const Expression& expr);

/// A user parameter of pasted objects that the document already has with another value.
struct PastedConflict
{
    std::string name;
    /// The value in the document and the pasted one, as shown to the user.
    std::string existing;
    std::string pasted;
};

/// What mergePasted() does with a PastedConflict.
enum class PastePolicy
{
    /// The pasted objects use the parameter of the document.
    UseExisting,
    /// The pasted parameter is added under a new name, which the pasted objects use.
    KeepPasted
};

/**
 * The user parameters that freshly pasted objects use and that the document already has with
 * another type or value. Empty when the paste brought no copy of a holder, or when the document
 * had no holder before.
 */
AppExport std::vector<PastedConflict> pastedConflicts(const std::vector<DocumentObject*>& pasted);

/**
 * Give freshly pasted objects the user parameters of the document.
 *
 * Objects that use user parameters are copied with the holder of their document, so a paste
 * brings a copy of that holder. Its parameters that the pasted objects use are added to the
 * holder of the document, the ones that the document already has are used as they are or added
 * under a new name (@p policy), the expressions of the pasted objects are re-pointed and the
 * copy is removed. When the document has no holder, the copy is its holder, with the used
 * parameters only. A holder pasted alone brings all its parameters.
 *
 * The copy of the holder is taken out of @p pasted: it is removed, or it is the holder of the
 * document, which stays at the root.
 */
AppExport void mergePasted(
    std::vector<DocumentObject*>& pasted,
    PastePolicy policy = PastePolicy::UseExisting
);

/// A user parameter that is going to be created, see PendingScope.
struct PendingParameter
{
    std::string name;
    Base::Quantity value;
};

/**
 * Make user parameters that are not created yet known to the expressions of @p owner.
 *
 * A tool may create user parameters only when it finishes (the on-view parameters of a sketch
 * tool create them with the geometry), while the user already refers to them in the next input
 * of the same tool (`height = 10 mm`, then `= 2 * height`). While the scope is alive, on this
 * thread, evaluating a bare name of an expression owned by @p owner that resolves nowhere else
 * gives the value of the pending parameter of that name. The document is not changed and the
 * expression keeps the bare name, which qualifyReferences() makes a reference to the parameter
 * once it is created. Scopes nest; the innermost one is searched first.
 */
class AppExport PendingScope
{
public:
    PendingScope(const DocumentObject* owner, std::vector<PendingParameter> parameters);
    ~PendingScope();

    PendingScope(const PendingScope&) = delete;
    PendingScope(PendingScope&&) = delete;
    PendingScope& operator=(const PendingScope&) = delete;
    PendingScope& operator=(PendingScope&&) = delete;

    /// The value of the pending parameter that the bare identifier @p path names, nullptr when
    /// @p path is not a bare name or no scope of its owner has a pending parameter of that name.
    static const Base::Quantity* find(const ObjectIdentifier& path);

private:
    const DocumentObject* owner;
    std::vector<PendingParameter> parameters;
    PendingScope* outer;
};

}  // namespace UserParameters
}  // namespace App
