// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2023 Abdullah Tahiri <abdullah.tahiri.yo@gmail.com>     *
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


#include <functional>

#include <QElapsedTimer>
#include <QEvent>
#include <QKeyEvent>
#include <QPointer>

#include <Gui/Application.h>
#include <Gui/Document.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>


namespace Gui
{
class ViewProvider;
}  // namespace Gui

namespace SketcherGui
{

class ViewProviderSketch;

/** Class implementing an event filter for DrawSketchHandler tools, enabling seamless introduction
 * of values to parameters, including units, while still allowing operation of shortcuts.
 *
 * The basic mechanism to decide which control should respond is based on using timers, type of
 * entered event.
 *
 * Letters typed in a field are text (units, user parameter names, expressions), so the tool
 * shortcuts that are letters in the 3D view are other keys in a field: tapping Alt switches the
 * construction method (M), Home/End/Page Up/Page Down are the first to fourth tool shortcuts
 * (U/J/R/F). Alt+key sends the key to the 3D view. These keys work the same while the 3D view
 * has the focus, where the manager also filters the events of the viewer.
 */
class DrawSketchKeyboardManager: public QObject
{
    Q_OBJECT

public:
    DrawSketchKeyboardManager();
    ~DrawSketchKeyboardManager() override;

    DrawSketchKeyboardManager(const DrawSketchKeyboardManager&) = delete;
    DrawSketchKeyboardManager(DrawSketchKeyboardManager&&) = delete;
    DrawSketchKeyboardManager& operator=(const DrawSketchKeyboardManager&) = delete;
    DrawSketchKeyboardManager& operator=(DrawSketchKeyboardManager&&) = delete;


    /** Indicates whether the DSH control (e.g. on-view parameter or widget) should handle keyboard
     * input or should signal it via boost */
    enum class KeyboardEventHandlingMode
    {
        DSHControl,
        ViewProvider
    };

    /// returns whether the provided entity will currently receive the event.
    bool isMode(KeyboardEventHandlingMode mode);

    /// returns which entity will currently receive the event.
    KeyboardEventHandlingMode getMode();

    /// resets the mode to ViewProvider
    void resetMode();

    bool eventFilter(QObject* object, QEvent* event) override;

    /// Receives the tool shortcuts typed in a field, as the 3D view key that is the shortcut
    /// (SoKeyboardEvent::Key), see the class description.
    void setToolShortcutHandler(std::function<void(bool pressed, int key)> handler);

private:
    /// This function decides whether events should be send to the ViewProvider
    /// or to the UI control of DSH.
    KeyboardEventHandlingMode detectKeyboardEventHandlingMode(QObject* object, QKeyEvent* keyEvent);
    /// Whether the field @p object holds an expression being typed (`= expression`).
    static bool holdsExpression(QObject* object);
    /// Sends the tool shortcut typed in a field (@p inField) or the 3D view, if @p keyEvent is one
    /// (see the class description).
    bool sendToolShortcut(QKeyEvent* keyEvent, bool inField);
    /// The events of the 3D view itself: the tool shortcuts, the rest goes on to the viewer.
    bool filterViewerEvent(QObject* object, QEvent* event);
    /// Sends a key typed in a field to the 3D view.
    bool sendToViewer(QKeyEvent* keyEvent);
    /// Claims the keys of the tool shortcuts from the application shortcuts and the menu bar.
    bool overrideShortcut(QKeyEvent* keyEvent);
    /// The tool shortcut (SoKeyboardEvent::Key) of Home/End/Page Up/Page Down, 0 for other keys.
    static int toolShortcutOf(const QKeyEvent* keyEvent);

    /// Viewer responsible for the active document
    QPointer<Gui::View3DInventorViewer> vpViewer;
    /// A key typed in a field is being sent to the 3D view (sendToViewer()).
    bool sendingToViewer = false;
    KeyboardEventHandlingMode keyMode;
    std::function<void(bool pressed, int key)> toolShortcutHandler;
    /// Alt pressed alone and not yet released: a tap switches the construction method
    bool altTap = false;
    QElapsedTimer altPressTime;
};

}  // namespace SketcherGui
