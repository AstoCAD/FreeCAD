// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2026 The FreeCAD Project Association AISBL
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1            *
 *   of the License, or (at your option) any later version.                   *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful,               *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty              *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                  *
 *   See the GNU Lesser General Public License for more details.              *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD. If not, see https://www.gnu.org/licenses     *
 *                                                                            *
 ******************************************************************************/

#include <algorithm>
#include <iterator>
#include <list>
#include <memory>
#include <set>

#include <Base/Exception.h>
#include <Base/ServiceProvider.h>

#include "CopyPasteRules.h"
#include "Datums.h"
#include "Document.h"
#include "DocumentObject.h"
#include "DocumentObjectGroup.h"
#include "GeoFeature.h"
#include "GeoFeatureGroupExtension.h"
#include "GroupExtension.h"
#include "Origin.h"
#include "OriginGroupExtension.h"
#include "Part.h"
#include "PropertyLinks.h"

using namespace App;

namespace
{

bool isOriginFeature(const DocumentObject* obj)
{
    return obj && obj->isDerivedFrom<DatumElement>()
        && static_cast<const DatumElement*>(obj)->isOriginFeature();
}

// An orphan datum that a pasted object links to: Paste can re-link it to a container origin.
bool isUsedOrphanDatum(const DocumentObject* obj)
{
    return CopyPasteRules::isOrphanDatum(obj) && !obj->getInList().empty();
}

// The origin group (Body, Part...) that is or contains obj, or nullptr.
DocumentObject* getOriginGroupOf(const DocumentObject* obj)
{
    std::set<const DocumentObject*> visited;
    while (obj && visited.insert(obj).second) {
        if (obj->hasExtension(OriginGroupExtension::getExtensionClassTypeId())) {
            return const_cast<DocumentObject*>(obj);  // NOLINT
        }
        obj = GeoFeatureGroupExtension::getGroupOfObject(obj);
    }
    return nullptr;
}

// Re-point the links of the pasted objects from orphan datums to the origin features of
// originGroup with the same role, then remove the orphans left without users.
// Returns the removed objects (they must not be dereferenced any more).
std::set<const DocumentObject*> relinkOrphanDatums(const std::vector<DocumentObject*>& pasted,
                                                   DocumentObject* originGroup)
{
    std::set<const DocumentObject*> removed;
    auto ext = originGroup->getExtensionByType<OriginGroupExtension>(true);
    if (!ext) {
        return removed;
    }
    App::Origin* origin = nullptr;
    try {
        origin = ext->getOrigin();
    }
    catch (const Base::Exception&) {
        return removed;
    }
    if (!origin) {
        return removed;
    }

    for (auto orphan : pasted) {
        if (removed.count(orphan) != 0 || !isUsedOrphanDatum(orphan)) {
            continue;
        }
        auto datum = static_cast<DatumElement*>(orphan);
        DatumElement* target = nullptr;
        try {
            target = origin->getDatumElement(datum->Role.getValue());
        }
        catch (const Base::Exception&) {
            continue;
        }
        if (!target || target->getTypeId() != datum->getTypeId()) {
            continue;
        }

        for (auto obj : pasted) {
            if (obj == orphan || removed.count(obj) != 0 || !obj->isAttachedToDocument()) {
                continue;
            }
            std::vector<Property*> props;
            obj->getPropertyList(props);
            for (auto prop : props) {
                auto linkProp = freecad_cast<PropertyLinkBase*>(prop);
                if (!linkProp) {
                    continue;
                }
                std::unique_ptr<Property> copy(linkProp->CopyOnLinkReplace(obj, orphan, target));
                if (copy) {
                    prop->Paste(*copy);
                }
            }
        }

        if (orphan->getInList().empty()) {
            orphan->getDocument()->removeObject(orphan->getNameInDocument());
            removed.insert(orphan);
        }
    }
    return removed;
}

std::list<CopyPasteHandler*> getHandlers()
{
    return Base::provideServiceImplementations<CopyPasteHandler>();
}

// True if an object other than a group that merely contains obj links to obj
bool hasUsers(const DocumentObject* obj)
{
    auto inList = obj->getInList();
    return std::any_of(inList.begin(), inList.end(), [obj](const DocumentObject* user) {
        auto grp = user->getExtensionByType<GroupExtension>(true);
        if (!grp) {
            return true;
        }
        const auto& children = grp->Group.getValues();
        return std::find(children.begin(), children.end(), obj) == children.end();
    });
}

// Detach the pasted objects that are outside any geometry group and attached to orphan
// datums only, give them their source placement, and remove the orphans they used if
// nothing else uses them. Adds the removed objects to removed.
void detachFromOrphanDatums(const std::vector<DocumentObject*>& pasted,
                            const std::map<const DocumentObject*, Base::Placement>& placements,
                            std::set<const DocumentObject*>& removed)
{
    // Only the orphans created by this paste: never touch existing objects
    std::vector<DocumentObject*> pastedOrphans;
    for (auto obj : pasted) {
        if (removed.count(obj) == 0 && CopyPasteRules::isOrphanDatum(obj)) {
            pastedOrphans.push_back(obj);
        }
    }
    if (pastedOrphans.empty()) {
        return;
    }

    std::vector<DocumentObject*> released;
    for (auto obj : pasted) {
        if (removed.count(obj) != 0 || !obj->isAttachedToDocument()
            || CopyPasteRules::isOrphanDatum(obj)
            || GeoFeatureGroupExtension::getGroupOfObject(obj)) {
            continue;
        }
        std::vector<DocumentObject*> orphans;
        for (auto dep : obj->getOutList()) {
            if (std::find(pastedOrphans.begin(), pastedOrphans.end(), dep) != pastedOrphans.end()) {
                orphans.push_back(dep);
            }
        }
        if (orphans.empty()) {
            continue;
        }
        for (const auto& handler : getHandlers()) {
            if (!handler->detachFromOrphanDatums(obj, pastedOrphans)) {
                continue;
            }
            auto it = placements.find(obj);
            auto geo = freecad_cast<GeoFeature*>(obj);
            if (geo && it != placements.end()) {
                geo->Placement.setValue(it->second);
            }
            released.insert(released.end(), orphans.begin(), orphans.end());
            break;
        }
    }

    for (auto orphan : released) {
        if (removed.count(orphan) == 0 && orphan->isAttachedToDocument() && !hasUsers(orphan)) {
            removed.insert(orphan);
            orphan->getDocument()->removeObject(orphan->getNameInDocument());
        }
    }
}

// The child of container that is or contains selected, or nullptr
DocumentObject* getInsertionPoint(const DocumentObject* container,
                                  const GroupExtension* grp,
                                  const DocumentObject* selected)
{
    const auto& children = grp->Group.getValues();
    std::set<const DocumentObject*> visited;
    for (auto obj = selected; obj && obj != container && visited.insert(obj).second;
         obj = CopyPasteRules::getParentContainer(obj)) {
        if (std::find(children.begin(), children.end(), obj) != children.end()) {
            return const_cast<DocumentObject*>(obj);  // NOLINT
        }
    }
    return nullptr;
}

// Insert obj into container right after its child after. Returns false if the container
// does not support it.
bool insertAfter(DocumentObject* container,
                 GroupExtension* grp,
                 DocumentObject* obj,
                 DocumentObject* after)
{
    for (auto handler : getHandlers()) {
        if (handler->insertObject(container, obj, after)) {
            return true;
        }
    }
    // In plain groups and parts the order of the children is only presentational
    if (container->getTypeId() != DocumentObjectGroup::getClassTypeId()
        && container->getTypeId() != Part::getClassTypeId()) {
        return false;
    }
    grp->addObject(obj);
    auto children = grp->Group.getValues();
    auto it = std::find(children.begin(), children.end(), obj);
    if (it == children.end()) {
        return false;
    }
    children.erase(it);
    auto pos = std::find(children.begin(), children.end(), after);
    if (pos == children.end()) {
        return false;
    }
    children.insert(pos + 1, obj);
    grp->Group.setValues(children);
    return true;
}

void finish(const std::vector<DocumentObject*>& pasted,
            const std::map<const DocumentObject*, Base::Placement>& placements,
            std::set<const DocumentObject*>& removed)
{
    detachFromOrphanDatums(pasted, placements, removed);

    for (auto obj : pasted) {
        if (removed.count(obj) != 0 || !obj->isAttachedToDocument()) {
            continue;
        }
        for (auto handler : getHandlers()) {
            handler->finishPastedObject(obj);
        }
    }
}

}  // namespace

std::vector<DocumentObject*> CopyPasteRules::getOwnedObjects(const DocumentObject* obj)
{
    std::vector<DocumentObject*> res;
    if (!obj || !obj->isAttachedToDocument()) {
        return res;
    }
    if (auto grp = obj->getExtensionByType<GroupExtension>(true)) {
        for (auto child : grp->Group.getValues()) {
            if (child) {
                res.push_back(child);
            }
        }
    }
    if (auto originGrp = obj->getExtensionByType<OriginGroupExtension>(true)) {
        if (auto origin = originGrp->Origin.getValue()) {
            res.push_back(origin);
        }
    }
    if (obj->isDerivedFrom<LocalCoordinateSystem>()) {
        auto lcs = static_cast<const LocalCoordinateSystem*>(obj);
        for (auto feature : lcs->OriginFeatures.getValues()) {
            if (feature) {
                res.push_back(feature);
            }
        }
    }
    return res;
}

bool CopyPasteRules::canCopyWithoutAsking(const std::vector<DocumentObject*>& objs)
{
    if (objs.empty()) {
        return false;
    }

    // The copied objects and everything they own, recursively
    std::set<const DocumentObject*> owned;
    std::vector<const DocumentObject*> stack(objs.begin(), objs.end());
    while (!stack.empty()) {
        auto obj = stack.back();
        stack.pop_back();
        if (!obj || !owned.insert(obj).second) {
            continue;
        }
        for (auto child : getOwnedObjects(obj)) {
            stack.push_back(child);
        }
        for (auto handler : getHandlers()) {
            for (auto child : handler->getCopiedWith(obj)) {
                stack.push_back(child);
            }
        }
    }

    for (auto dep : getObjectsToCopy(objs)) {
        if (owned.count(dep) == 0 && !isOriginFeature(dep)) {
            return false;
        }
    }
    return true;
}

std::vector<DocumentObject*>
CopyPasteRules::getObjectsToCopy(const std::vector<DocumentObject*>& objs)
{
    auto all = Document::getDependencyList(objs, Document::DepSort);

    // Follow the out-lists like getDependencyList(), except the rebuilt links
    bool cut = false;
    std::set<const DocumentObject*> reached;
    std::vector<DocumentObject*> stack(objs.begin(), objs.end());
    while (!stack.empty()) {
        auto obj = stack.back();
        stack.pop_back();
        if (!obj || !obj->isAttachedToDocument() || !reached.insert(obj).second) {
            continue;
        }
        std::vector<std::string> rebuilt;
        for (auto handler : getHandlers()) {
            auto names = handler->getRebuiltLinks(obj);
            rebuilt.insert(rebuilt.end(), names.begin(), names.end());
        }
        if (rebuilt.empty()) {
            const auto& outList = obj->getOutList();
            stack.insert(stack.end(), outList.begin(), outList.end());
            continue;
        }
        for (const auto& edge : obj->getOutListProp(0)) {
            if (std::find(rebuilt.begin(), rebuilt.end(), edge.fromProp) != rebuilt.end()) {
                cut = true;
            }
            else {
                stack.push_back(edge.toObj);
            }
        }
    }
    if (!cut) {
        return all;
    }

    // Same order as getDependencyList(): dependencies first
    std::vector<DocumentObject*> res;
    std::copy_if(all.begin(), all.end(), std::back_inserter(res), [&reached](auto obj) {
        return reached.count(obj) != 0;
    });
    return res;
}

std::vector<DocumentObject*>
CopyPasteRules::getRootObjects(const std::vector<DocumentObject*>& objs)
{
    std::set<const DocumentObject*> owned;
    for (auto obj : objs) {
        for (auto child : getOwnedObjects(obj)) {
            owned.insert(child);
        }
    }
    std::vector<DocumentObject*> res;
    for (auto obj : objs) {
        if (obj && owned.count(obj) == 0) {
            res.push_back(obj);
        }
    }
    return res;
}

bool CopyPasteRules::isOrphanDatum(const DocumentObject* obj)
{
    return obj && obj->isAttachedToDocument() && obj->isDerivedFrom<DatumElement>()
        && !static_cast<const DatumElement*>(obj)->getLCS();
}

bool CopyPasteRules::isPasteContainer(const DocumentObject* obj)
{
    // Only plain groups: specialised groups (Assembly joints, FEM analysis...) are not
    // meant to receive arbitrary objects.
    return obj && obj->isAttachedToDocument()
        && (obj->getTypeId() == DocumentObjectGroup::getClassTypeId()
            || obj->hasExtension(OriginGroupExtension::getExtensionClassTypeId()));
}

DocumentObject* CopyPasteRules::getParentContainer(const DocumentObject* obj)
{
    if (!obj || !obj->isAttachedToDocument()) {
        return nullptr;
    }
    // A plain group is nested in the geometry group (if any): check it first.
    if (auto grp = GroupExtension::getGroupOfObject(obj)) {
        return grp;
    }
    return GeoFeatureGroupExtension::getGroupOfObject(obj);
}

DocumentObject* CopyPasteRules::findPasteContainer(const std::vector<DocumentObject*>& pasted,
                                                   const DocumentObject* selected)
{
    if (!selected || !selected->isAttachedToDocument()) {
        return nullptr;
    }
    auto roots = getRootObjects(pasted);
    if (roots.empty() || roots.front()->getDocument() != selected->getDocument()) {
        return nullptr;
    }
    // Used orphan datums are re-linked and removed when the container has an origin.
    std::vector<DocumentObject*> nonOrphans;
    for (auto obj : roots) {
        if (!isUsedOrphanDatum(obj)) {
            nonOrphans.push_back(obj);
        }
    }

    std::set<const DocumentObject*> visited;
    const DocumentObject* current = isPasteContainer(selected) ? selected
                                                                : getParentContainer(selected);
    // Climb only through paste containers: below anything else, paste to the root as before.
    while (isPasteContainer(current) && visited.insert(current).second) {
        auto grp = current->getExtensionByType<GroupExtension>(true);
        const auto& required = getOriginGroupOf(current) ? nonOrphans : roots;
        bool accepted = grp && std::all_of(required.begin(), required.end(), [&](auto obj) {
                            return obj != current && grp->allowObject(obj);
                        });
        if (accepted) {
            return const_cast<DocumentObject*>(current);  // NOLINT
        }
        current = getParentContainer(current);
    }
    return nullptr;
}

DocumentObject* CopyPasteRules::placePastedObjects(
    const std::vector<DocumentObject*>& pasted,
    const DocumentObject* selected,
    const std::map<const DocumentObject*, Base::Placement>& sourcePlacements)
{
    std::set<const DocumentObject*> removed;
    auto container = findPasteContainer(pasted, selected);
    auto grp = container ? container->getExtensionByType<GroupExtension>(true) : nullptr;
    if (grp) {
        // Computed before removing anything: removed objects must not be dereferenced.
        auto roots = getRootObjects(pasted);

        if (auto originGroup = getOriginGroupOf(container)) {
            removed = relinkOrphanDatums(pasted, originGroup);
        }

        // Selecting the container itself appends, as before
        auto after = getInsertionPoint(container, grp, selected);
        for (auto obj : roots) {
            if (removed.count(obj) != 0 || !obj->isAttachedToDocument() || grp->hasObject(obj)) {
                continue;
            }
            try {
                if (after && insertAfter(container, grp, obj, after)) {
                    after = obj;  // keep the pasted objects in their order
                }
                else if (!grp->hasObject(obj)) {
                    grp->addObject(obj);
                }
            }
            catch (const Base::Exception& e) {
                e.reportException();
            }
        }
    }
    finish(pasted, sourcePlacements, removed);
    return grp ? container : nullptr;
}

void CopyPasteRules::finishPastedObjects(
    const std::vector<DocumentObject*>& pasted,
    const std::map<const DocumentObject*, Base::Placement>& sourcePlacements)
{
    std::set<const DocumentObject*> removed;
    finish(pasted, sourcePlacements, removed);
}
