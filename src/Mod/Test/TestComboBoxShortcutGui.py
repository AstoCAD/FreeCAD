# SPDX-License-Identifier: LGPL-2.1-or-later
"""Typing letters in a focused combo box must not trigger application shortcuts."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestComboBoxShortcutGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ComboBoxShortcut27018")
        self.triggered = []
        self.actions = []
        main_window = Gui.getMainWindow()
        for name, shortcut in (("single", "J"), ("multi", "K, Q")):
            action = QtGui.QAction(name, main_window)
            action.setShortcut(QtGui.QKeySequence(shortcut))
            action.setShortcutContext(QtCore.Qt.ApplicationShortcut)
            action.triggered.connect(lambda checked=False, n=name: self.triggered.append(n))
            main_window.addAction(action)
            self.actions.append(action)

        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["Dimension", "Jitem", "Kitem", "Litem"])
        layout.addWidget(self.combo)

        class Panel:
            def __init__(self, form):
                self.form = form

            def accept(self):
                return True

            def reject(self):
                return True

        Gui.Control.showDialog(Panel(self.form))
        self._events()

    def tearDown(self):
        Gui.Control.closeDialog()
        for action in self.actions:
            Gui.getMainWindow().removeAction(action)
            action.deleteLater()
        App.closeDocument(self.doc.Name)
        self._events()

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _type(self, key):
        self.combo.setCurrentIndex(0)
        self.combo.setFocus()
        self._events()
        QtTest.QTest.keyClick(self.combo, key)
        self._events(500)

    def testLetterOfSingleKeyShortcutSelectsItem(self):
        # https://github.com/FreeCAD/FreeCAD/issues/27018
        self._type("j")
        self.assertEqual(self.combo.currentText(), "Jitem")
        self.assertEqual(self.triggered, [])

    def testFirstLetterOfMultiKeyShortcutSelectsItem(self):
        self._type("k")
        self.assertEqual(self.combo.currentText(), "Kitem")
        self.assertEqual(self.triggered, [])

    def testOtherLetterSelectsItem(self):
        self._type("l")
        self.assertEqual(self.combo.currentText(), "Litem")
