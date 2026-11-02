// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2026 FreeCAD Project Association                        *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Material.h>
#include <Base/Tools.h>

#include "Isolation.h"
#include "Application.h"
#include "Control.h"
#include "ViewProviderGeometryObject.h"
#include "ViewProviderLink.h"
#include "Selection/Selection.h"
#include "Selection/SoFCSelectionAction.h"
#include "TaskView/TaskView.h"

using namespace Gui;

namespace
{
/// Isolation changes the selectability of the other objects for a while only: the
/// document must not become modified because of it
App::PropertyBool* selectableProperty(ViewProvider* vp)
{
    if (auto* vpl = dynamic_cast<ViewProviderLink*>(vp)) {
        return &vpl->Selectable;
    }
    if (auto* vpg = dynamic_cast<ViewProviderGeometryObject*>(vp)) {
        return &vpg->Selectable;
    }
    return nullptr;
}

void setSelectable(App::PropertyBool& prop, bool selectable)
{
    if (prop.getValue() == selectable) {
        return;
    }
    Base::ObjectStatusLocker<App::Property::Status, App::Property> guard(
        App::Property::NoModify,
        &prop
    );
    prop.setValue(selectable);
}

/// The object, the objects shown as part of it and, for a link, what it links to
void collectIsolated(App::DocumentObject* obj, std::set<App::DocumentObject*>& isolated)
{
    if (!obj || !obj->isAttachedToDocument() || !isolated.insert(obj).second) {
        return;
    }
    if (auto* vp = Application::Instance->getViewProvider(obj)) {
        for (auto* child : vp->claimChildren3D()) {
            collectIsolated(child, isolated);
        }
    }
    auto* linked = obj->getLinkedObject(true);
    if (linked && linked != obj) {
        collectIsolated(linked, isolated);
    }
}
}  // namespace

Isolation& Isolation::instance()
{
    static Isolation isolation;
    return isolation;
}

Isolation::Isolation()
{
    // NOLINTBEGIN
    auto& app = App::GetApplication();
    connectDeletedObject = app.signalDeletedObject.connect(
        [this](const App::DocumentObject& obj) { slotDeletedObject(obj); }
    );
    connectDeleteDocument = app.signalDeleteDocument.connect(
        [this](const App::Document& doc) { slotDeleteDocument(doc); }
    );
    connectStartSave = app.signalStartSaveDocument.connect(
        [this](const App::Document& doc, const std::string&) { slotStartSave(doc); }
    );
    connectFinishSave = app.signalFinishSaveDocument.connect(
        [this](const App::Document& doc, const std::string&) { slotFinishSave(doc); }
    );
    // NOLINTEND
}

void Isolation::isolate(const std::vector<Path>& paths)
{
    App::Document* doc = nullptr;
    std::set<App::DocumentObject*> isolated;
    for (const auto& [root, sub] : paths) {
        if (!root || !root->isAttachedToDocument()) {
            continue;
        }
        if (!doc) {
            doc = root->getDocument();
        }
        else if (root->getDocument() != doc) {
            continue;
        }
        // The objects along the path keep the selected object visible: its containers,
        // and the links it is shown through
        auto objs = root->getSubObjectList(sub.c_str());
        if (objs.empty()) {
            objs.push_back(root);
        }
        for (std::size_t i = 0; i + 1 < objs.size(); ++i) {
            isolated.insert(objs[i]);
        }
        collectIsolated(objs.back(), isolated);
    }
    if (!doc || isolated.empty()) {
        return;
    }

    end(doc);
    auto& state = documents[doc];
    state.isolated = std::move(isolated);
    apply(doc, state);
    updateTaskWatcher();
}

void Isolation::isolateSelection()
{
    auto selection = Selection().getSelectionEx(
        nullptr,
        App::DocumentObject::getClassTypeId(),
        ResolveMode::NoResolve
    );

    std::vector<Path> paths;
    for (auto& sel : selection) {
        std::vector<std::string> subs = sel.getSubNames();
        if (subs.empty()) {
            subs.emplace_back();
        }
        for (const auto& sub : subs) {
            paths.emplace_back(sel.getObject(), sub);
        }
    }

    // Selection observers may restore states of their own when the selection is cleared,
    // so it is cleared before anything is isolated
    Selection().clearSelection();
    isolate(paths);
}

void Isolation::end(const App::Document* doc)
{
    auto it = documents.find(doc);
    if (it == documents.end()) {
        return;
    }
    restore(it->second);
    documents.erase(it);
    updateTaskWatcher();
}

bool Isolation::isActive(const App::Document* doc) const
{
    return doc && documents.count(doc) > 0;
}

bool Isolation::isActive() const
{
    return isActive(App::GetApplication().getActiveDocument());
}

bool Isolation::isIsolated(const App::DocumentObject* obj) const
{
    if (!obj) {
        return false;
    }
    auto it = documents.find(obj->getDocument());
    return it != documents.end()
        && it->second.isolated.count(const_cast<App::DocumentObject*>(obj)) > 0;
}

void Isolation::apply(const App::Document* doc, DocumentState& state)
{
    Base::Color transparentColor(App::Material::getDefaultAppearance().diffuseColor);
    transparentColor.setTransparency(0.8F);
    std::map<std::string, Base::Color> colorMap;
    colorMap["Face"] = transparentColor;  // The "Face" wildcard targets all faces

    for (auto* obj : doc->getObjects()) {
        if (state.isolated.count(obj) || !obj->Visibility.getValue()) {
            continue;
        }
        auto* vp = Application::Instance->getViewProvider(obj);
        App::PropertyBool* selectable = selectableProperty(vp);
        if (!selectable) {
            continue;  // only geometry and links are shown in the 3D view
        }

        state.changed[obj].selectable = selectable->getValue();
        setSelectable(*selectable, false);

        // swapColors() takes the map: each object needs its own copy
        auto colors = colorMap;
        SoSelectionElementAction action(SoSelectionElementAction::Color, true);
        action.swapColors(colors);
        action.apply(vp->getRoot());
    }
}

void Isolation::restore(DocumentState& state)
{
    for (const auto& [obj, objState] : state.changed) {
        if (!obj->isAttachedToDocument()) {
            continue;
        }
        auto* vp = Application::Instance->getViewProvider(obj);
        App::PropertyBool* selectable = selectableProperty(vp);
        if (!selectable) {
            continue;
        }
        setSelectable(*selectable, objState.selectable);
        SoSelectionElementAction action(SoSelectionElementAction::Color, true);
        action.apply(vp->getRoot());
    }
    state.changed.clear();
}

void Isolation::updateTaskWatcher()
{
    if (auto* taskView = Control().taskPanel()) {
        taskView->updateWatcher();
    }
}

void Isolation::slotDeletedObject(const App::DocumentObject& obj)
{
    auto it = documents.find(obj.getDocument());
    if (it == documents.end()) {
        return;
    }
    auto* key = const_cast<App::DocumentObject*>(&obj);
    it->second.changed.erase(key);
    it->second.isolated.erase(key);
}

void Isolation::slotDeleteDocument(const App::Document& doc)
{
    // The view providers are about to go: nothing to restore
    if (documents.erase(&doc) > 0) {
        updateTaskWatcher();
    }
}

void Isolation::slotStartSave(const App::Document& doc)
{
    auto it = documents.find(&doc);
    if (it != documents.end()) {
        restore(it->second);
    }
}

void Isolation::slotFinishSave(const App::Document& doc)
{
    auto it = documents.find(&doc);
    if (it != documents.end()) {
        apply(&doc, it->second);
    }
}
