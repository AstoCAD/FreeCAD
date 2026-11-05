// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#pragma once

#include <string>
#include <vector>

#include <FCGlobal.h>

namespace App
{
class Document;
class DocumentObject;
class Expression;
class ObjectIdentifier;
class Property;
}  // namespace App

namespace Base
{
class Unit;
}

/**
 * The document-level parameter list shown by the Parameters dialog
 * (Std_Parameters, Gui::Dialog::DlgDocumentParameters).  This part has no widget dependency so that it can be
 * tested without a main window.
 *
 * Parameters are:
 * - user parameters: properties in the property group named exactly
 *   "UserParameters" on any object of the document that is not a VarSet;
 * - VarSet parameters: the visible dynamic properties of every App::VarSet;
 * - model parameters (optional): expressions bound to properties of other
 *   objects, and named sketch constraints.
 *
 * All the scanning of user parameters is done in collectUserParameters() so
 * that it can be replaced by a document-level helper later.
 */
namespace Gui::Parameters
{

/// The property group that marks a property as a user parameter.
GuiExport const char* userParametersGroup();

enum class Category
{
    User,
    VarSet,
    Model
};

struct GuiExport Entry
{
    Category category = Category::User;
    /// Internal name of the object that holds the parameter.
    std::string objectName;
    /// Label of the object that holds the parameter.
    std::string objectLabel;
    /// Name of the property that holds the parameter.
    std::string propertyName;
    /// Path of the parameter relative to its object, e.g. "Length" or "Constraints.width".
    std::string path;
    /// The name shown to the user.
    std::string name;
    /// The type shown to the user, e.g. "Length", "Float" or "String".
    std::string type;
    /// The expression bound to the parameter, empty if there is none.
    std::string expression;
    /// The value as a user string, e.g. "10 mm".
    std::string value;
    /// The documentation of the property.
    std::string comment;
    /// Dynamic properties can be renamed and deleted.
    bool isDynamic = false;
    /// The value can be edited directly (a whole property, no expression, editable type).
    bool valueEditable = false;
};

/// Whether \a prop is a user parameter (in the "UserParameters" group).
GuiExport bool isUserParameter(const App::Property* prop);

/// The user parameters of the document, sorted by name.  VarSets are skipped.
GuiExport std::vector<App::Property*> collectUserParameters(const App::Document* doc);

/// All parameters of the document: user parameters, then each VarSet (sorted by label), then the
/// model parameters if \a includeModel is true.
GuiExport std::vector<Entry> collect(const App::Document* doc, bool includeModel);

/// Build an entry for the property path \a path of \a obj.
GuiExport Entry makeEntry(const App::DocumentObject* obj, const App::ObjectIdentifier& path, Category category);

/// Find the user parameter named \a name in \a doc, ignoring \a exclude.
GuiExport App::Property* findUserParameter(
    const App::Document* doc,
    const std::string& name,
    const App::Property* exclude = nullptr
);

enum class NameError
{
    None,
    Empty,
    NotIdentifier,
    Constant,
    Unit,
    ExistsInObject,
    ExistsInDocument,
    /// User parameters only: a spreadsheet cell address (App::UserParameters::isCellAddressName).
    CellAddress
};

/**
 * Check \a name for a new or renamed parameter held by \a holder.  If \a userParameter is true,
 * the name must also be unique among the user parameters of the document.  \a exclude is the
 * property being renamed, if any.
 */
GuiExport NameError checkName(
    const App::DocumentObject* holder,
    const std::string& name,
    bool userParameter,
    const App::Property* exclude = nullptr
);

struct GuiExport Reference
{
    std::string objectName;
    std::string objectLabel;
    /// The path that holds the referencing expression, empty if the reference could not be
    /// located precisely (e.g. a spreadsheet cell).
    std::string path;
};

/// The expressions in the document of \a holder that reference its property \a propertyName.
GuiExport std::vector<Reference> findReferences(
    const App::DocumentObject* holder,
    const std::string& propertyName
);

/// The property type for a new parameter whose value is a quantity with unit \a unit,
/// e.g. "App::PropertyDistance", "App::PropertyAngle" or "App::PropertyFloat"
/// (App::UserParameters::propertyTypeForUnit).  Returns an empty string when no property type
/// stores that unit (a plain App::PropertyQuantity would lose it on save).
GuiExport std::string propertyTypeForUnit(const Base::Unit& unit);

/// The property type for a new parameter whose value is the result of \a expr.  Returns an empty
/// string if the result is not a number or a string, or has a unit no property type stores.
GuiExport std::string propertyTypeForExpression(const App::Expression& expr);

}  // namespace Gui::Parameters
