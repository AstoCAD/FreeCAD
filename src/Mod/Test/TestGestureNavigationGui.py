# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression tests for reentrant Gesture navigation event dispatch."""

import traceback
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from pivy import coin
from PySide import QtCore, QtGui


class PointerTrace(QtCore.QObject):
    def __init__(self, viewport):
        super().__init__(viewport)
        self.events = []

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            if event.button() == QtCore.Qt.LeftButton:
                self.events.append(
                    "DOWN" if event.type() == QtCore.QEvent.MouseButtonPress else "UP")
        return False


class TestGestureNavigationGui(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/View")
        self.original_debug = self.preferences.GetBool("NavigationDebug", False)
        self.had_debug = self.original_debug == self.preferences.GetBool("NavigationDebug", True)
        self.addCleanup(self.restoreNavigationDebug)
        self.preferences.SetBool("NavigationDebug", False)

        self.doc = App.newDocument("GestureReentrantDispatch")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(Gui.Selection.clearSelection)
        self.view = Gui.activeDocument().activeView()
        self.original_navigation = self.view.getNavigationType()
        self.addCleanup(self.view.setNavigationType, self.original_navigation)
        self.viewport = self.view.graphicsView().viewport()
        self.qt_trace = PointerTrace(self.viewport)
        self.addCleanup(self.qt_trace.deleteLater)
        self.viewport.installEventFilter(self.qt_trace)
        self.addCleanup(self.viewport.removeEventFilter, self.qt_trace)
        self.event_type = coin.SoMouseButtonEvent.getClassTypeId()
        self.events = []
        self.timer_errors = []
        self.entered_modal = False
        self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.view.fitAll()
        Gui.updateGui()
        self.position = self.viewport.rect().topLeft() + QtCore.QPoint(15, 15)

    def restoreNavigationDebug(self):
        if self.had_debug:
            self.preferences.SetBool("NavigationDebug", self.original_debug)
        else:
            self.preferences.RemBool("NavigationDebug")

    def sendMouse(self, kind, button, buttons):
        local = QtCore.QPointF(self.position)
        global_position = QtCore.QPointF(self.viewport.mapToGlobal(self.position))
        event = QtGui.QMouseEvent(kind, local, global_position, button, buttons,
                                 QtCore.Qt.NoModifier)
        QtGui.QApplication.sendEvent(self.viewport, event)

    def click(self):
        self.sendMouse(QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton,
                       QtCore.Qt.LeftButton)
        self.sendMouse(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.LeftButton,
                       QtCore.Qt.NoButton)

    def checkDispatch(self, navigation, reentrant):
        self.view.setNavigationType(navigation)

        def callback(action):
            event = action.getEvent()
            if event.getButton() != coin.SoMouseButtonEvent.BUTTON1:
                return
            state = "DOWN" if event.getState() == coin.SoButtonEvent.DOWN else "UP"
            self.events.append(state)
            if state != "DOWN" or self.entered_modal or not reentrant:
                return
            self.entered_modal = True
            dialog = QtGui.QDialog(Gui.getMainWindow())
            dialog.setWindowTitle("Gesture dispatch modal control")
            dialog.setModal(True)

            def finishAndReenter():
                try:
                    # Deliver another pointer stream before the modal callback
                    # unwinds, as queued input can while an edit dialog closes.
                    dialog.accept()
                    self.click()
                except Exception:
                    self.timer_errors.append(traceback.format_exc())
                    dialog.reject()

            QtCore.QTimer.singleShot(0, finishAndReenter)
            try:
                dialog.exec_()
            finally:
                dialog.close()
                dialog.deleteLater()

        callback_handle = self.view.addEventCallbackPivy(self.event_type, callback)
        self.addCleanup(self.view.removeEventCallbackPivy, self.event_type, callback_handle)
        self.click()
        self.assertFalse(self.timer_errors, self.timer_errors)
        if not reentrant:
            expected = ["DOWN", "UP"]
        elif navigation.endswith("GestureNavigationStyle"):
            expected = ["DOWN", "UP", "DOWN", "UP"]
        else:
            expected = ["DOWN", "DOWN", "UP", "UP"]
        self.assertEqual(self.qt_trace.events, expected,
                         "All pointer events must reach native Qt routing")
        # Coin suppresses recursive scene traversal while SoHandleEventAction
        # is active. Navigation still receives the inner Qt events, which can
        # clear Gesture's postponed queue. A scene handler may consume UP.
        self.assertEqual(self.events.count("DOWN"), 1)
        self.assertLessEqual(self.events.count("UP"), 1)
        self.assertEqual(self.entered_modal, reentrant)
        self.assertTrue(self.doc.Box.Shape.isValid())

    def testCadNavigationModalControl(self):
        self.checkDispatch("Gui::CADNavigationStyle", reentrant=True)

    def testGestureNavigationWithoutReentryControl(self):
        self.checkDispatch("Gui::GestureNavigationStyle", reentrant=False)

    def testGestureNavigationReentrantModalDispatch(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33461
        self.checkDispatch("Gui::GestureNavigationStyle", reentrant=True)
