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


#include <QAbstractSpinBox>
#include <QApplication>
#include <QEvent>
#include <QKeyEvent>
#include <QStyleHints>

#include <utility>

#include <Inventor/events/SoKeyboardEvent.h>

#include "DrawSketchKeyboardManager.h"

using namespace SketcherGui;


DrawSketchKeyboardManager::DrawSketchKeyboardManager()
    : QObject(nullptr)
    , keyMode(KeyboardEventHandlingMode::DSHControl)
{
    // get the active viewer, so that we can send it key events
    auto doc = Gui::Application::Instance->activeDocument();

    if (doc) {
        auto temp = dynamic_cast<Gui::View3DInventor*>(doc->getActiveView());
        if (temp) {
            vpViewer = temp->getViewer();
            keyMode = KeyboardEventHandlingMode::ViewProvider;
        }
    }
    if (vpViewer) {
        // The tool shortcuts also work while the 3D view has the focus. Installed after Quarter's
        // filters, this one sees the keys first, Alt included.
        vpViewer->installEventFilter(this);
        vpViewer->viewport()->installEventFilter(this);
    }
}

DrawSketchKeyboardManager::~DrawSketchKeyboardManager()
{
    if (vpViewer) {
        vpViewer->removeEventFilter(this);
        vpViewer->viewport()->removeEventFilter(this);
    }
}

bool DrawSketchKeyboardManager::isMode(KeyboardEventHandlingMode mode)
{
    return mode == keyMode;
}

DrawSketchKeyboardManager::KeyboardEventHandlingMode DrawSketchKeyboardManager::getMode()
{
    return keyMode;
}

void DrawSketchKeyboardManager::resetMode()
{
    keyMode = KeyboardEventHandlingMode::ViewProvider;
}

bool DrawSketchKeyboardManager::eventFilter(QObject* object, QEvent* event)
{
    if (!vpViewer) {
        return false;
    }
    if (object == vpViewer || object == vpViewer->viewport()) {
        return filterViewerEvent(object, event);
    }
    if (event->type() == QEvent::ShortcutOverride) {
        return overrideShortcut(static_cast<QKeyEvent*>(event));
    }
    if (event->type() == QEvent::KeyPress || event->type() == QEvent::KeyRelease) {
        // Here we decide if we redirect the input the viewer
        auto keyEvent = static_cast<QKeyEvent*>(event);

        if (sendToolShortcut(keyEvent, /*inField=*/true)) {
            return true;
        }

        // Pressing Alt/Option sends the keypress to the viewer
        // without permanently switching the destination (keyMode)
        bool altPressed = (keyEvent->modifiers() & Qt::AltModifier);
        if (isMode(KeyboardEventHandlingMode::DSHControl) && altPressed) {
            // Convert from Alt+Key to just Key For view navigation
            keyEvent->setModifiers(keyEvent->modifiers() & ~Qt::AltModifier);
            return sendToViewer(keyEvent);
        }
        const int key = keyEvent->key();
        if (key == Qt::Key_Enter || key == Qt::Key_Return || key == Qt::Key_Tab) {
            // This keys switch to camera control but are sent to the widget
            keyMode = KeyboardEventHandlingMode::ViewProvider;
            return false;
        }

        keyMode = detectKeyboardEventHandlingMode(object, keyEvent);  // determine the handler

        if (isMode(KeyboardEventHandlingMode::ViewProvider)) {
            return sendToViewer(keyEvent);
        }
        return false;  // do not intercept the event and feed it to the widget
    }

    return false;
}

bool DrawSketchKeyboardManager::filterViewerEvent(QObject* object, QEvent* event)
{
    switch (event->type()) {
        case QEvent::ShortcutOverride:
            return object == vpViewer && overrideShortcut(static_cast<QKeyEvent*>(event));
        case QEvent::KeyPress:
        case QEvent::KeyRelease:
            // The keys of a field sent on to the 3D view were handled in the field already.
            return object == vpViewer && !sendingToViewer
                && sendToolShortcut(static_cast<QKeyEvent*>(event), /*inField=*/false);
        case QEvent::MouseButtonPress:
        case QEvent::Wheel:
            // Alt held while clicking or scrolling in the 3D view is no tap
            altTap = false;
            return false;
        default:
            return false;
    }
}

bool DrawSketchKeyboardManager::sendToViewer(QKeyEvent* keyEvent)
{
    const bool wasSending = std::exchange(sendingToViewer, true);
    const bool handled = QApplication::sendEvent(vpViewer, keyEvent);
    sendingToViewer = wasSending;
    return handled;
}

bool DrawSketchKeyboardManager::overrideShortcut(QKeyEvent* keyEvent)
{
    // Accepting the shortcut override delivers the key to the field or the 3D view:
    // - Alt pressed and released alone activates the menu bar on some platforms (Windows), which
    //   then takes the focus: the tap would switch the construction method and leave the next
    //   keys, the next tap included, to the menu bar. The menu bar watches for the override
    //   reaching the window.
    // - Home and End are application shortcuts (Std_ViewHome, Std_RecallWorkingView).
    if (!toolShortcutHandler
        || (keyEvent->key() != Qt::Key_Alt && toolShortcutOf(keyEvent) == 0)) {
        return false;
    }
    keyEvent->accept();
    return true;
}

int DrawSketchKeyboardManager::toolShortcutOf(const QKeyEvent* keyEvent)
{
    // Shift+Home selects text, Ctrl+Home and the like keep their meaning
    if (keyEvent->modifiers() & ~Qt::KeypadModifier) {
        return 0;
    }
    switch (keyEvent->key()) {
        case Qt::Key_Home:
            return SoKeyboardEvent::U;
        case Qt::Key_End:
            return SoKeyboardEvent::J;
        case Qt::Key_PageUp:
            return SoKeyboardEvent::R;
        case Qt::Key_PageDown:
            return SoKeyboardEvent::F;
        default:
            return 0;
    }
}

DrawSketchKeyboardManager::KeyboardEventHandlingMode DrawSketchKeyboardManager::detectKeyboardEventHandlingMode(
    QObject* object,
    QKeyEvent* keyEvent
)
{
    // Detect if the user wants to start editing the input

    if (keyEvent->matches(QKeySequence::Paste)) {
        return KeyboardEventHandlingMode::DSHControl;
    }
    // on Linux you need to use key() for backspace
    if (keyEvent->key() == Qt::Key_Backspace || keyEvent->matches(QKeySequence::Backspace)
        || keyEvent->matches(QKeySequence::Delete)) {
        return KeyboardEventHandlingMode::DSHControl;
    }

    const QString& text = keyEvent->text();
    if (!text.isEmpty()) {
        QChar ch = text.front();
        if (ch.isDigit()) {
            return KeyboardEventHandlingMode::DSHControl;
        }
        if (ch == '-' || ch == '.' || ch == ',') {
            return KeyboardEventHandlingMode::DSHControl;
        }
        // Letters are text in a field: units, names of user parameters (`height = 20 mm`) and
        // expressions (`= 2 * height`). The tool shortcuts are then other keys (see
        // sendToolShortcut()); Alt+letter still sends the letter to the 3D view.
        const auto commandModifiers = Qt::ControlModifier | Qt::AltModifier | Qt::MetaModifier;
        if ((ch.isLetter() || ch == '_' || ch == '=') && !(keyEvent->modifiers() & commandModifiers)) {
            return KeyboardEventHandlingMode::DSHControl;
        }
    }
    // A field still holding an expression (e.g. one refused on Enter) keeps being edited.
    if (holdsExpression(object)) {
        return KeyboardEventHandlingMode::DSHControl;
    }
    return keyMode;
}

bool DrawSketchKeyboardManager::holdsExpression(QObject* object)
{
    // A quantity never contains '=': the text is an expression being typed.
    auto* field = qobject_cast<QAbstractSpinBox*>(object);
    return field && field->text().contains(QLatin1Char('='));
}

void DrawSketchKeyboardManager::setToolShortcutHandler(std::function<void(bool, int)> handler)
{
    toolShortcutHandler = std::move(handler);
}

bool DrawSketchKeyboardManager::sendToolShortcut(QKeyEvent* keyEvent, bool inField)
{
    if (!toolShortcutHandler) {
        return false;
    }
    const bool pressed = keyEvent->type() == QEvent::KeyPress;
    const int key = keyEvent->key();

    // Tapping Alt alone switches the construction method, like M in the 3D view. Alt itself keeps
    // its usual routing (Alt+key sends the key to the 3D view).
    if (key == Qt::Key_Alt) {
        if (pressed) {
            if (!keyEvent->isAutoRepeat()) {
                altTap = true;
                altPressTime.start();
            }
        }
        else if (altTap) {
            altTap = false;
            // Not Alt held while clicking or dragging in the 3D view
            if (altPressTime.elapsed() < QGuiApplication::styleHints()->mousePressAndHoldInterval()
                && QGuiApplication::mouseButtons() == Qt::NoButton) {
                // After the 3D view has handled the release: Quarter's interaction mode, on while
                // Alt is down, then restores the cursor it had, not the one of the new method.
                QMetaObject::invokeMethod(
                    this,
                    [this]() {
                        toolShortcutHandler(true, SoKeyboardEvent::M);
                        toolShortcutHandler(false, SoKeyboardEvent::M);
                    },
                    Qt::QueuedConnection
                );
            }
        }
        return false;
    }
    if (pressed) {
        altTap = false;
    }

    const int shortcut = toolShortcutOf(keyEvent);
    if (shortcut == 0) {
        return false;
    }
    // While a value is typed in the field, Home and End move the cursor in it
    if (inField && (key == Qt::Key_Home || key == Qt::Key_End)
        && isMode(KeyboardEventHandlingMode::DSHControl)) {
        return false;
    }
    toolShortcutHandler(pressed, shortcut);
    return true;
}

#include "moc_DrawSketchKeyboardManager.cpp"
