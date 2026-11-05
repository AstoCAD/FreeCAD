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

#include <algorithm>
#include <cstring>
#include <iterator>
#include <set>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/ObjectIdentifier.h>
#include <App/Property.h>
#include <App/PropertyExpressionEngine.h>
#include <App/PropertyStandard.h>
#include <App/UserParameters.h>
#include <App/VarSet.h>
#include <Base/Console.h>
#include <Base/Quantity.h>
#include <Base/Tools.h>
#include <Base/Unit.h>

#include "Dialogs/DocumentParameters.h"

using namespace Gui;

namespace
{

constexpr const char* PropertyTypePrefix = "App::Property";

bool isVarSet(const App::DocumentObject* obj)
{
    return obj && obj->isDerivedFrom<App::VarSet>();
}

bool isVisible(const App::PropertyContainer* container, const App::Property* prop)
{
    return !container->isHidden(prop) && !prop->testStatus(App::Property::Hidden);
}

bool isPropertyType(const App::Property* prop, const char* typeName)
{
    Base::Type type = Base::Type::fromName(typeName);
    return !type.isBad() && prop->getTypeId().isDerivedFrom(type);
}

/// The type shown to the user: the property type without the "App::Property" prefix.
std::string displayType(const App::Property* prop, const App::any& value, bool isSubPath)
{
    if (!prop) {
        return {};
    }
    if (isSubPath) {
        if (value.type() == typeid(Base::Quantity)) {
            std::string unitType = App::any_cast<Base::Quantity>(value).getUnit().getTypeString();
            if (!unitType.empty()) {
                return unitType;
            }
        }
        return "Number";
    }
    std::string type {prop->getTypeId().getName()};
    if (type.starts_with(PropertyTypePrefix)) {
        type = type.substr(std::strlen(PropertyTypePrefix));
    }
    else if (auto pos = type.rfind("::Property"); pos != std::string::npos) {
        type = type.substr(pos + std::strlen("::Property"));
    }
    return type;
}

bool isEditableValue(const App::any& value)
{
    const auto& type = value.type();
    return type == typeid(Base::Quantity) || type == typeid(double) || type == typeid(float)
        || type == typeid(int) || type == typeid(long) || type == typeid(bool)
        || type == typeid(std::string);
}

/**
 * The only place that scans the document for user parameters.  If the
 * document gets a helper that lists its user parameters, use it here.
 */
std::vector<App::Property*> scanUserParameters(const App::Document* doc, bool includeVarSets)
{
    std::vector<App::Property*> result;
    if (!doc) {
        return result;
    }
    for (auto* obj : doc->getObjects()) {
        if (!includeVarSets && isVarSet(obj)) {
            continue;
        }
        std::vector<App::Property*> props;
        obj->getPropertyList(props);
        for (auto* prop : props) {
            if (Parameters::isUserParameter(prop)) {
                result.push_back(prop);
            }
        }
    }
    return result;
}

std::vector<App::DocumentObject*> sortedVarSets(const App::Document* doc)
{
    std::vector<App::DocumentObject*> varSets;
    for (auto* obj : doc->getObjects()) {
        if (isVarSet(obj)) {
            varSets.push_back(obj);
        }
    }
    std::ranges::stable_sort(varSets, [](const App::DocumentObject* a, const App::DocumentObject* b) {
        return std::strcmp(a->Label.getValue(), b->Label.getValue()) < 0;
    });
    return varSets;
}

void collectModelParameters(const App::Document* doc, std::vector<Parameters::Entry>& entries)
{
    for (auto* obj : doc->getObjects()) {
        if (isVarSet(obj)) {
            continue;
        }
        std::set<std::string> seen;
        std::vector<Parameters::Entry> objEntries;

        // properties bound to an expression
        for (const auto& [path, expr] : obj->ExpressionEngine.getExpressions()) {
            App::Property* prop = path.getProperty();
            if (!prop || Parameters::isUserParameter(prop)) {
                continue;
            }
            auto entry = Parameters::makeEntry(obj, path, Parameters::Category::Model);
            if (seen.insert(entry.path).second) {
                objEntries.push_back(std::move(entry));
            }
        }

        // named sketch constraints, found without a link dependency on Sketcher
        std::vector<App::Property*> props;
        obj->getPropertyList(props);
        for (auto* prop : props) {
            if (!isPropertyType(prop, "Sketcher::PropertyConstraintList")) {
                continue;
            }
            std::vector<App::ObjectIdentifier> paths;
            prop->getPaths(paths);
            for (const auto& path : paths) {
                auto entry = Parameters::makeEntry(obj, path, Parameters::Category::Model);
                if (entry.type.empty() || entry.value.empty()) {
                    continue;
                }
                if (seen.insert(entry.path).second) {
                    objEntries.push_back(std::move(entry));
                }
            }
        }

        std::ranges::stable_sort(objEntries, [](const auto& a, const auto& b) {
            return a.path < b.path;
        });
        std::ranges::move(objEntries, std::back_inserter(entries));
    }
}

}  // namespace

const char* Parameters::userParametersGroup()
{
    return "UserParameters";
}

bool Parameters::isUserParameter(const App::Property* prop)
{
    if (!prop) {
        return false;
    }
    const App::PropertyContainer* container = prop->getContainer();
    if (!container) {
        return false;
    }
    const char* group = container->getPropertyGroup(prop);
    return group && std::strcmp(group, userParametersGroup()) == 0;
}

std::vector<App::Property*> Parameters::collectUserParameters(const App::Document* doc)
{
    std::vector<App::Property*> props = scanUserParameters(doc, false);
    std::ranges::stable_sort(props, [](const App::Property* a, const App::Property* b) {
        return std::strcmp(a->getName(), b->getName()) < 0;
    });
    return props;
}

Parameters::Entry
Parameters::makeEntry(const App::DocumentObject* obj, const App::ObjectIdentifier& path, Category category)
{
    Entry entry;
    entry.category = category;
    if (!obj || !obj->isAttachedToDocument()) {
        return entry;
    }

    entry.objectName = obj->getNameInDocument();
    entry.objectLabel = obj->Label.getValue();

    App::Property* prop = path.getProperty();
    std::string subPath = path.getSubPathStr();
    entry.propertyName = prop ? std::string(prop->getName()) : path.getPropertyName();
    entry.path = entry.propertyName + subPath;
    entry.name = category == Category::Model ? entry.objectLabel + "." + entry.path : entry.path;

    App::any value;
    try {
        value = path.getValue();
        entry.value = App::anyToString(value);
    }
    catch (const Base::Exception& e) {
        entry.value = e.what();
    }
    catch (...) {
        entry.value.clear();
    }

    entry.type = displayType(prop, value, !subPath.empty());

    auto info = obj->getExpression(path);
    if (info.expression) {
        entry.expression = info.expression->toString();
    }

    if (prop) {
        const char* doc = obj->getPropertyDocumentation(prop);
        entry.comment = doc ? doc : "";
        entry.isDynamic = subPath.empty() && prop->testStatus(App::Property::PropDynamic);
        // Sub-paths (e.g. sketch constraints) are only edited through expressions: a direct
        // value cannot tell a driving constraint from a reference one.
        entry.valueEditable = subPath.empty() && !info.expression && !obj->isReadOnly(prop)
            && !prop->testStatus(App::Property::ReadOnly) && isEditableValue(value);
    }
    return entry;
}

std::vector<Parameters::Entry> Parameters::collect(const App::Document* doc, bool includeModel)
{
    std::vector<Entry> entries;
    if (!doc) {
        return entries;
    }

    for (auto* prop : collectUserParameters(doc)) {
        auto* obj = freecad_cast<App::DocumentObject*>(prop->getContainer());
        if (obj && isVisible(obj, prop)) {
            entries.push_back(makeEntry(obj, App::ObjectIdentifier(*prop), Category::User));
        }
    }

    for (auto* varSet : sortedVarSets(doc)) {
        std::vector<App::Property*> props;
        varSet->getPropertyList(props);
        for (auto* prop : props) {
            if (prop->testStatus(App::Property::PropDynamic) && isVisible(varSet, prop)) {
                entries.push_back(makeEntry(varSet, App::ObjectIdentifier(*prop), Category::VarSet));
            }
        }
    }

    if (includeModel) {
        collectModelParameters(doc, entries);
    }
    return entries;
}

App::Property* Parameters::findUserParameter(
    const App::Document* doc,
    const std::string& name,
    const App::Property* exclude
)
{
    for (auto* prop : scanUserParameters(doc, true)) {
        if (prop != exclude && name == prop->getName()) {
            return prop;
        }
    }
    return nullptr;
}

Parameters::NameError Parameters::checkName(
    const App::DocumentObject* holder,
    const std::string& name,
    bool userParameter,
    const App::Property* exclude
)
{
    if (name.empty()) {
        return NameError::Empty;
    }
    if (name != Base::Tools::getIdentifier(name)) {
        return NameError::NotIdentifier;
    }
    if (App::ExpressionParser::isTokenAConstant(name)) {
        return NameError::Constant;
    }
    if (App::ExpressionParser::isTokenAUnit(name)) {
        return NameError::Unit;
    }
    if (userParameter && App::UserParameters::isCellAddressName(name)) {
        return NameError::CellAddress;
    }
    if (holder) {
        App::Property* prop = holder->getPropertyByName(name.c_str());
        if (prop && prop != exclude) {
            return NameError::ExistsInObject;
        }
        if (userParameter && findUserParameter(holder->getDocument(), name, exclude)) {
            return NameError::ExistsInDocument;
        }
    }
    return NameError::None;
}

std::vector<Parameters::Reference>
Parameters::findReferences(const App::DocumentObject* holder, const std::string& propertyName)
{
    std::vector<Reference> refs;
    if (!holder || !holder->isAttachedToDocument()) {
        return refs;
    }

    auto* target = const_cast<App::DocumentObject*>(holder);  // NOLINT: map key type
    std::set<const App::DocumentObject*> located;
    for (auto* obj : holder->getDocument()->getObjects()) {
        for (const auto& [path, expr] : obj->ExpressionEngine.getExpressions()) {
            if (!expr) {
                continue;
            }
            auto deps = expr->getDeps(App::Expression::DepAll);
            auto it = deps.find(target);
            if (it == deps.end() || it->second.count(propertyName) == 0) {
                continue;
            }
            refs.push_back(
                {obj->getNameInDocument(), obj->Label.getValue(), path.getPropertyName() + path.getSubPathStr()}
            );
            located.insert(obj);
        }
    }

    // Other expression containers (e.g. spreadsheet cells) do not list their
    // expressions in a generic way: report the dependent object without a path.
    for (auto* obj : holder->getInList()) {
        if (!obj || obj == holder || located.contains(obj)) {
            continue;
        }
        std::vector<App::Property*> props;
        obj->getPropertyList(props);
        bool hasOtherExpressions = std::ranges::any_of(props, [obj](const App::Property* prop) {
            return prop != &obj->ExpressionEngine
                && prop->isDerivedFrom<App::PropertyExpressionContainer>();
        });
        if (hasOtherExpressions) {
            refs.push_back({obj->getNameInDocument(), obj->Label.getValue(), {}});
            located.insert(obj);
        }
    }
    return refs;
}

std::string Parameters::propertyTypeForUnit(const Base::Unit& unit)
{
    // Same rule as the user parameters typed in any input: no plain App::PropertyQuantity,
    // which does not save its unit.
    const Base::Type type = App::UserParameters::propertyTypeForUnit(unit);
    return type.isBad() ? std::string() : std::string(type.getName());
}

std::string Parameters::propertyTypeForExpression(const App::Expression& expr)
{
    App::ExpressionPtr result = expr.eval();
    if (auto* number = freecad_cast<App::NumberExpression*>(result.get())) {
        return propertyTypeForUnit(number->getUnit());
    }
    if (freecad_cast<App::StringExpression*>(result.get())) {
        return "App::PropertyString";
    }
    return {};
}
