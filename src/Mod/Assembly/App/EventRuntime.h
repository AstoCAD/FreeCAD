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
#include <functional>
#include <memory>
#include <set>
#include <string>
#include <vector>
#include <Base/Placement.h>

namespace App
{
class DocumentObject;
}
namespace MbD
{
class ASMTAssembly;
}
namespace Assembly
{
// A marker factory preserves component occurrence and rigid-group offsets.
using EventMarkerFactory = std::function<std::string(App::DocumentObject*, const Base::Placement&)>;
std::set<App::DocumentObject*> eventTargets(App::DocumentObject* study);
void configureEvents(
    App::DocumentObject* study,
    MbD::ASMTAssembly* assembly,
    const EventMarkerFactory& marker
);
// Release document/Python callbacks before returning to the GUI, also on error.
struct EventRunScope
{
    MbD::ASMTAssembly* assembly;
    ~EventRunScope();
};
}  // namespace Assembly
