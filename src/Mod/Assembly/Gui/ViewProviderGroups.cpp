// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2023 Ondsel <development@ondsel.com>                     *
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

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/DocumentObjectGroup.h>
#include <App/GroupExtension.h>
#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>

#include <Mod/Assembly/App/AssemblyUtils.h>
#include <Mod/Assembly/App/Groups.h>

#include "ViewProviderGroups.h"

using namespace AssemblyGui;

namespace
{
bool isEmptyGroup(const App::DocumentObject* obj)
{
    if (!obj || !obj->isDerivedFrom<App::DocumentObjectGroup>()) {
        return false;
    }

    auto* group = obj->getExtensionByType<App::GroupExtension>(/*no_except=*/true);
    return group && group->Group.getValues().empty();
}
}  // namespace

PROPERTY_SOURCE(AssemblyGui::ViewProviderGroupBase, Gui::ViewProviderDocumentObjectGroup)
PROPERTY_SOURCE(AssemblyGui::ViewProviderBomGroup, AssemblyGui::ViewProviderGroupBase)
PROPERTY_SOURCE(AssemblyGui::ViewProviderJointGroup, AssemblyGui::ViewProviderGroupBase)
PROPERTY_SOURCE(AssemblyGui::ViewProviderSimulationGroup, AssemblyGui::ViewProviderGroupBase)
PROPERTY_SOURCE(AssemblyGui::ViewProviderSnapshotGroup, AssemblyGui::ViewProviderGroupBase)
PROPERTY_SOURCE(AssemblyGui::ViewProviderViewGroup, AssemblyGui::ViewProviderGroupBase)

QIcon ViewProviderBomGroup::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Assembly_BillOfMaterialsGroup.svg");
}

QIcon ViewProviderJointGroup::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Assembly_JointGroup.svg");
}

bool ViewProviderJointGroup::canDragObject(App::DocumentObject* obj) const
{
    return obj != nullptr;
}

bool ViewProviderJointGroup::canDragObjectToTarget(
    App::DocumentObject* obj,
    App::DocumentObject* target
) const
{
    auto* jointGroup = getObject<Assembly::JointGroup>();
    if (!jointGroup || !obj) {
        return false;
    }

    const bool targetIsRoot = target == jointGroup;
    const bool targetIsInside = target && jointGroup->hasObject(target, true);
    if (targetIsRoot || targetIsInside) {
        return Assembly::isJointGroupItem(obj) || Assembly::isJointGroupFolder(obj);
    }

    // Joints, and folders containing joints, must never leave their JointGroup.
    return !Assembly::containsJointGroupItem(obj);
}

bool ViewProviderJointGroup::canDropObject(App::DocumentObject* obj) const
{
    if (!obj) {
        return false;
    }

    auto* jointGroup = getObject<Assembly::JointGroup>();
    return Assembly::isJointGroupItem(obj) || isEmptyGroup(obj)
        || (jointGroup && jointGroup->hasObject(obj, true)
            && Assembly::isJointGroupFolder(obj));
}

bool ViewProviderJointGroup::canDropObjectToTarget(
    App::DocumentObject* obj,
    App::DocumentObject* target
) const
{
    auto* jointGroup = getObject<Assembly::JointGroup>();
    if (!jointGroup || !obj || !target || !jointGroup->hasObject(target, true)) {
        return false;
    }

    if (Assembly::isJointGroupItem(obj) || isEmptyGroup(obj)) {
        return true;
    }

    // Non-empty folders may only be reorganized once they are already contained
    // by this JointGroup, and only if their complete subtree is valid.
    return jointGroup->hasObject(obj, true) && Assembly::isJointGroupFolder(obj);
}

QIcon ViewProviderSimulationGroup::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Assembly_SimulationGroup.svg");
}

QIcon ViewProviderSnapshotGroup::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Assembly_SnapshotGroup.svg");
}

QIcon ViewProviderViewGroup::getIcon() const
{
    return Gui::BitmapFactory().pixmap("Assembly_ExplodedViewGroup.svg");
}

bool ViewProviderJointGroup::onDelete(const std::vector<std::string>&)
{
    auto* group = getObject<Assembly::JointGroup>();

    // if empty or orphaned ok to delete.
    if (group && (group->Group.getValues().empty() || group->getParents().empty())) {
        return true;
    }

    return false;
};
