# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for changes to the shortcut ambiguity timeout preference."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestShortcutTimeoutGui(unittest.TestCase):
    def setUp(self):
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut/Settings")
        self.previous = self.settings.GetInt("ShortcutTimeout", 300)
        self.had_key = self._has_key()
        self.actions = []
        self.clock = QtCore.QElapsedTimer()
        self.activated = {"short": [], "long": []}
        self.host = QtWidgets.QWidget(Gui.getMainWindow(), QtCore.Qt.Window)
        self.host.setObjectName("ShortcutTimeoutTestHost")
        self.host.setWindowTitle("Shortcut timeout preference test")
        self.host.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.host.resize(240, 100)
        self.addCleanup(self._cleanup)
        self.host.show()
        self.host.raise_()
        self.host.activateWindow()
        self.host.setFocus()
        for _ in range(50):
            if QtWidgets.QApplication.focusWidget() == self.host:
                break
            QtTest.QTest.qWait(20)
        self.assertEqual(QtWidgets.QApplication.focusWidget(), self.host)
        self._action("Short", "F35", "short")
        self._action("Long", "F35, F34", "long")

    def _has_key(self):
        return any(entry[1] == "ShortcutTimeout" for entry in (self.settings.GetContents() or []))

    def _action(self, suffix, shortcut, kind):
        action_type = QtGui.QAction if hasattr(QtGui, "QAction") else QtWidgets.QAction
        action = action_type("TimeoutTest" + suffix, self.host)
        action.setObjectName("TimeoutTest" + suffix)
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        self.host.addAction(action)
        action.setShortcut(QtGui.QKeySequence(shortcut))
        action.triggered.connect(lambda: self.activated[kind].append(self.clock.elapsed()))
        self.actions.append(action)

    def _observe(self):
        self.clock.start()
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        immediate = len(self.activated["short"])
        QtTest.QTest.qWait(50)
        early_count = len(self.activated["short"])
        early_elapsed = self.clock.elapsed()
        while not self.activated["short"] and self.clock.elapsed() < 1500:
            QtTest.QTest.qWait(20)
        self.assertEqual(len(self.activated["short"]), 1, "Short action did not activate once")
        self.assertEqual(self.activated["long"], [])
        self.assertTrue(all(action.isEnabled() for action in self.actions))
        return immediate, early_count, early_elapsed, self.activated["short"][0]

    def test_explicit_delay_control(self):
        self.settings.SetInt("ShortcutTimeout", 180)
        immediate, early_count, early_elapsed, activation = self._observe()
        self.assertEqual(immediate, 0, "Explicit delay activated synchronously")
        if early_elapsed < 130:
            self.assertEqual(early_count, 0)
        self.assertGreaterEqual(activation, 130)

    def test_explicit_zero_control(self):
        self.settings.SetInt("ShortcutTimeout", 0)
        immediate, _, _, _ = self._observe()
        self.assertEqual(immediate, 1, "Explicit zero must activate synchronously")

    def test_removed_timeout_uses_default_delay(self):
        self.settings.SetInt("ShortcutTimeout", 180)
        self.settings.RemInt("ShortcutTimeout")
        self.assertFalse(self._has_key())
        immediate, _, _, activation = self._observe()
        self.assertEqual(immediate, 0, "Removing the key changed the default to immediate")
        self.assertGreaterEqual(activation, 240)

    def _cleanup(self):
        for action in self.actions:
            action.setShortcut(QtGui.QKeySequence())
            self.host.removeAction(action)
            action.deleteLater()
        self.host.close()
        self.host.deleteLater()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtTest.QTest.qWait(40)
        if self.had_key:
            self.settings.SetInt("ShortcutTimeout", self.previous)
        else:
            self.settings.RemInt("ShortcutTimeout")
        Gui.getMainWindow().activateWindow()
