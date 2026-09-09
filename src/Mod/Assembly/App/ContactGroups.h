// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                         *
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
#include <App/DocumentObject.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <algorithm>
#include <functional>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace Assembly
{
// Shared by drag activation, drag response and forward dynamics. Sets contain
// occurrences, never their linked sources or the children of consolidated Parts.
inline std::vector<std::pair<App::DocumentObject*, App::DocumentObject*>> contactComponentPairs(
    App::DocumentObject* contact,
    const std::vector<App::DocumentObject*>& components
)
{
    using Object = App::DocumentObject;
    using Pair = std::pair<Object*, Object*>;
    const auto fail = [&](const std::string& message) {
        throw std::invalid_argument(contact->getFullName() + ": " + message);
    };
    const auto links = [&](const char* name) {
        auto* p = dynamic_cast<App::PropertyLinkList*>(contact->getPropertyByName(name));
        return p ? p->getValues() : std::vector<Object*> {};
    };
    const auto link = [&](const char* name) {
        auto* p = dynamic_cast<App::PropertyLink*>(contact->getPropertyByName(name));
        return p ? p->getValue() : nullptr;
    };
    const std::set<Object*> membership(components.begin(), components.end());
    const auto validate = [&](const auto& objects) {
        for (auto* object : objects) {
            if (!object || !membership.contains(object)) {
                fail("Contact members must belong to this assembly");
            }
        }
    };
    const auto key = [](Object* a, Object* b) {
        return std::less<Object*> {}(a, b) ? Pair {a, b} : Pair {b, a};
    };
    std::set<Pair> excluded, seen;
    auto* property = dynamic_cast<App::PropertyEnumeration*>(contact->getPropertyByName("Mode"));
    const std::string mode = property ? property->getValueAsString() : "Between two components";
    // Each key names a two-link property. FreeCAD remaps both links during
    // copy/import; deletion makes that pair incomplete, never a different pair.
    auto* exclusions = dynamic_cast<App::PropertyStringList*>(
        contact->getPropertyByName("ExcludedPairs")
    );
    if (exclusions && mode != "Between two components") {
        for (const auto& name : exclusions->getValues()) {
            auto* pairProperty = dynamic_cast<App::PropertyLinkList*>(
                contact->getPropertyByName(name.c_str()));
            if (!name.starts_with("ExcludedPair_") || !pairProperty) {
                fail("Invalid contact exclusion");
            }
            const auto& pair = pairProperty->getValues();
            if (pair.size() == 2 && membership.contains(pair[0]) && membership.contains(pair[1])) {
                excluded.insert(key(pair[0], pair[1]));
            }
        }
    }
    std::vector<Object*> first, second;
    bool within = false;
    if (mode == "General collision detection") {
        first = components;
        within = true;
    }
    else if (mode == "Between two components") {
        first = {link("ComponentI")};
        second = {link("ComponentJ")};
        if (first[0] == second[0]) {
            fail("Contact requires two different components");
        }
    }
    else if (mode == "Between component sets" || mode == "Within a component set") {
        first = links("ComponentsI");
        within = mode == "Within a component set";
        second = within ? std::vector<Object*> {} : links("ComponentsJ");
        const std::set<Object*> unique(first.begin(), first.end());
        if (unique.size() < (within ? 2u : 1u) || (!within && second.empty())) {
            fail("Select at least two members within a set, or at least one member in each set");
        }
    }
    else {
        fail("Unknown contact mode");
    }
    validate(first);
    validate(second);
    std::vector<Pair> result;
    const auto append = [&](Object* a, Object* b) {
        const auto pair = key(a, b);
        if (a != b && !excluded.contains(pair) && seen.insert(pair).second) {
            result.emplace_back(a, b);
        }
    };
    for (size_t i = 0; i < first.size(); ++i) {
        if (within) {
            for (size_t j = i + 1; j < first.size(); ++j) {
                append(first[i], first[j]);
            }
        }
        else {
            for (auto* b : second) {
                append(first[i], b);
            }
        }
    }
    return result;
}
}  // namespace Assembly
