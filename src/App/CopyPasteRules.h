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

#pragma once

#include <map>
#include <string>
#include <vector>

#include <Base/Placement.h>
#include <FCGlobal.h>

namespace App
{

class DocumentObject;

/** Hooks through which a module tells how its objects are copied and pasted, for the
 * types that App does not know (e.g. Part's attachment). Every hook has a neutral
 * default. A module registers an instance as a service:
 * Base::registerServiceImplementation<App::CopyPasteHandler>(new MyHandler).
 */
class CopyPasteHandler
{
public:
    CopyPasteHandler() = default;
    virtual ~CopyPasteHandler() = default;
    CopyPasteHandler(const CopyPasteHandler&) = delete;
    CopyPasteHandler(CopyPasteHandler&&) = delete;
    CopyPasteHandler& operator=(const CopyPasteHandler&) = delete;
    CopyPasteHandler& operator=(CopyPasteHandler&&) = delete;

    /// Detach @a obj, pasted outside any container with an origin, if it is attached to
    /// objects of @a orphans only: the orphan datums created by the same paste (see
    /// CopyPasteRules::isOrphanDatum()). Returns true if done.
    virtual bool detachFromOrphanDatums(DocumentObject* /*obj*/,
                                        const std::vector<DocumentObject*>& /*orphans*/) const
    {
        return false;
    }

    /// Insert @a obj into @a container right after @a after, a child of @a container.
    /// Returns true if done.
    virtual bool insertObject(DocumentObject* /*container*/,
                              DocumentObject* /*obj*/,
                              DocumentObject* /*after*/) const
    {
        return false;
    }

    /// Objects that Copy takes together with @a obj without asking, as if @a obj owned
    /// them (e.g. the profile sketch of a PartDesign feature). Paste places them as
    /// separate objects.
    virtual std::vector<DocumentObject*> getCopiedWith(const DocumentObject* /*obj*/) const
    {
        return {};
    }

    /// Names of the link properties of @a obj that Paste re-creates in the target
    /// container (e.g. the BaseFeature of a PartDesign feature): Copy does not follow them,
    /// so their targets are not copied.
    virtual std::vector<std::string> getRebuiltLinks(const DocumentObject* /*obj*/) const
    {
        return {};
    }

    /// Called for each pasted object once all of them are placed, e.g. to clear a rebuilt
    /// link that the target container could not re-create.
    virtual void finishPastedObject(DocumentObject* /*obj*/) const
    {}
};

/** Rules that let Copy and Paste of document objects work without asking the user
 * in the common cases (https://github.com/FreeCAD/FreeCAD/issues/9251).
 *
 * Copy: a dependency of the copied objects is "explained" when it is owned by a
 * copied object (group children, the Origin of an origin group, the features of a
 * coordinate system), recursively, or when it is an origin feature, which Paste
 * resolves in the target container. Modules can add explained objects and links
 * (CopyPasteHandler). When every dependency is explained, the objects can be
 * copied with their dependencies without asking.
 *
 * Paste: the pasted objects go into the selected container, or into the container
 * of the selected object, and links to copied origin features are re-pointed to
 * the origin of that container.
 *
 * The functions have no state and do not depend on the GUI.
 */
class AppExport CopyPasteRules
{
public:
    /// Objects owned by @a obj: group children, the Origin of an origin group and the
    /// features of a coordinate system. Not recursive.
    static std::vector<DocumentObject*> getOwnedObjects(const DocumentObject* obj);

    /// True if @a objs can be copied together with their dependencies (getObjectsToCopy())
    /// without asking the user, i.e. every dependency is explained (see class description).
    /// False for an empty list.
    static bool canCopyWithoutAsking(const std::vector<DocumentObject*>& objs);

    /// The objects Copy exports for @a objs when it does not ask: @a objs and their
    /// dependencies in dependency order, without following the links that Paste re-creates
    /// (CopyPasteHandler::getRebuiltLinks()).
    static std::vector<DocumentObject*> getObjectsToCopy(const std::vector<DocumentObject*>& objs);

    /// The objects of @a objs that are not owned by another object of @a objs, in the
    /// order of @a objs.
    static std::vector<DocumentObject*> getRootObjects(const std::vector<DocumentObject*>& objs);

    /// True for a datum element (plane, axis, point) that is not part of a coordinate
    /// system, e.g. a copied origin feature pasted without its Origin.
    static bool isOrphanDatum(const DocumentObject* obj);

    /// True if pasted objects may be put into @a obj: a plain App::DocumentObjectGroup
    /// (not a specialised subclass) or an origin group (Body, Part, Assembly).
    static bool isPasteContainer(const DocumentObject* obj);

    /// The group or geometry group that directly contains @a obj, or nullptr.
    static DocumentObject* getParentContainer(const DocumentObject* obj);

    /// The container that receives @a pasted objects when @a selected is the selected
    /// object: @a selected itself if it is a paste container, else its parent container,
    /// walking up through paste containers until one accepts all the pasted root objects.
    /// Returns nullptr for the document root.
    static DocumentObject* findPasteContainer(const std::vector<DocumentObject*>& pasted,
                                              const DocumentObject* selected);

    /// Put freshly @a pasted objects into the container found for @a selected (see
    /// findPasteContainer()), right after @a selected (or the child of the container that
    /// contains it) when the container supports it, else at its end. If the container has
    /// an origin, links of the pasted objects to orphan datums are re-pointed to the origin
    /// feature of the same role and the orphans left without users are removed. Then
    /// finishPastedObjects().
    /// Returns the container, or nullptr when the objects stay at the root.
    static DocumentObject*
    placePastedObjects(const std::vector<DocumentObject*>& pasted,
                       const DocumentObject* selected,
                       const std::map<const DocumentObject*, Base::Placement>& sourcePlacements = {});

    /// Pasted objects outside any container with an origin (document root or plain group)
    /// that are attached to orphan datums only are detached (see CopyPasteHandler) and get
    /// their global placement in the source document from @a sourcePlacements, if known.
    /// The orphan datums they used are removed when no other object uses them.
    static void
    finishPastedObjects(const std::vector<DocumentObject*>& pasted,
                        const std::map<const DocumentObject*, Base::Placement>& sourcePlacements = {});
};

}  // namespace App
