# SPDX-License-Identifier: LGPL-2.1-or-later
"""Space on a focused button presses the button, also when there is a selection
(issue #33204). Without the fix Std_ToggleVisibility (Space) took the key."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestButtonSpaceShortcutGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ButtonSpaceShortcut33204")
        self.addCleanup(self._cleanup)
        self.obj = self.doc.addObject("App::Part", "Part")
        self.doc.recompute()
        self.assertIsNotNone(self.obj.ViewObject)
        self.obj.ViewObject.Visibility = True

        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        self.button = QtWidgets.QPushButton("Press")
        self.check = QtWidgets.QCheckBox("Check")
        self.plain = QtWidgets.QWidget()
        self.plain.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.plain.setMinimumSize(20, 20)
        for widget in (self.button, self.check, self.plain):
            layout.addWidget(widget)
        self.clicked = []
        self.button.clicked.connect(lambda: self.clicked.append(True))

        class Panel:
            def __init__(self, form):
                self.form = form

            def accept(self):
                return True

            def reject(self):
                return True

        Gui.Control.showDialog(Panel(self.form))
        # application shortcuts only fire in the active window
        main_window = Gui.getMainWindow()
        for _ in range(30):
            if main_window.isActiveWindow():
                break
            main_window.raise_()
            main_window.activateWindow()
            self._events()
        if not main_window.isActiveWindow():
            self.skipTest("The main window cannot be activated")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.obj.Name)
        self._events()

    def _cleanup(self):
        Gui.Selection.clearSelection()
        Gui.Control.closeDialog()
        App.closeDocument(self.doc.Name)
        self._events()

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _space(self, widget):
        widget.setFocus()
        self._events()
        if not (widget.hasFocus() and Gui.getMainWindow().isActiveWindow()):
            self.skipTest("The test widget cannot get the keyboard focus")
        QtTest.QTest.keyClick(widget, QtCore.Qt.Key_Space)
        self._events(500)

    def testSpaceClicksFocusedPushButton(self):
        self._space(self.button)
        self.assertTrue(self.obj.ViewObject.Visibility, "Space toggled the selection")
        self.assertEqual(self.clicked, [True])

    def testSpaceTogglesFocusedCheckBox(self):
        self._space(self.check)
        self.assertTrue(self.obj.ViewObject.Visibility, "Space toggled the selection")
        self.assertTrue(self.check.isChecked())

    def testSpaceStillTogglesVisibilityElsewhere(self):
        # control: the Space shortcut is active for other focused widgets
        self._space(self.plain)
        self.assertFalse(self.obj.ViewObject.Visibility)
