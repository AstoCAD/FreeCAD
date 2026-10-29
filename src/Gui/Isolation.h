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

#pragma once

#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include <QPointer>

#include <fastsignals/signal.h>
#include <FCGlobal.h>

class QWidget;

namespace App
{
class Document;
class DocumentObject;
}  // namespace App

namespace Gui
{
class Document;

/** Isolation of some objects of a document.
 *
 * The other visible objects of the document become transparent, wireframe or hidden, and
 * unselectable, until the isolation ends. Only the scene and the Selectable view property
 * are changed, and the document is not marked as modified. The isolation is suspended
 * while the document is saved, so the saved file keeps the original selectability.
 */
class GuiExport Isolation
{
public:
    /// A selected object: its root object and the subname path to it
    using Path = std::pair<App::DocumentObject*, std::string>;

    /// How the objects that are not isolated are shown, as in the joint task of Assembly
    enum class Mode
    {
        Transparent,
        Wireframe,
        Hidden,
    };

    static Isolation& instance();

    /// The mode is kept in the preferences and applies to every isolated document
    Mode mode() const;
    void setMode(Mode mode);

    /// Isolates the objects of the paths in their document, replacing any isolation there
    void isolate(const std::vector<Path>& paths);
    /// Isolates the objects of the current selection
    void isolateSelection();
    /// Ends the isolation of the document
    void end(const App::Document* doc);
    bool isActive(const App::Document* doc) const;
    /// Whether the active document is isolated
    bool isActive() const;
    /// Whether the object is one of the objects isolated in its document
    bool isIsolated(const App::DocumentObject* obj) const;

private:
    Isolation();

    struct ObjectState
    {
        bool selectable {true};
        /// The display mode shown before the object was hidden, -1 when it was not hidden
        int hiddenMode {-1};
    };
    struct DocumentState
    {
        std::set<App::DocumentObject*> isolated;
        std::map<App::DocumentObject*, ObjectState> changed;
        /// The Isolation box, a permanent task box of the document's task panel
        QPointer<QWidget> panel;
    };

    void apply(const App::Document* doc, DocumentState& state);
    void restore(DocumentState& state);
    void addPanel(const App::Document* doc, DocumentState& state);
    void removePanel(const App::Document* doc, DocumentState& state);

    void slotDeletedObject(const App::DocumentObject& obj);
    void slotDeleteDocument(const App::Document& doc);
    void slotStartSave(const App::Document& doc);
    void slotFinishSave(const App::Document& doc);

    std::map<const App::Document*, DocumentState> documents;

    fastsignals::scoped_connection connectDeletedObject;
    fastsignals::scoped_connection connectDeleteDocument;
    fastsignals::scoped_connection connectStartSave;
    fastsignals::scoped_connection connectFinishSave;
};

}  // namespace Gui
