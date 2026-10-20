# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for shortcut dispatch across modal and reentrant commands."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


def _enum(value):
    return value.value if hasattr(value, "value") else int(value)


class _KeyHost(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent, QtCore.Qt.Window)
        self.setObjectName("Issue33598KeyHost")
        self.setWindowTitle("FreeCAD shortcut diagnostic")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.resize(280, 120)
        self.keys = []

    def keyPressEvent(self, event):
        self.keys.append(event.key())
        super().keyPressEvent(event)


class _EscapeDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Issue33598ModalDialog")
        self.setWindowTitle("Shortcut modal Escape diagnostic")
        self.resize(280, 100)
        self.keys = []

    def keyPressEvent(self, event):
        self.keys.append(event.key())
        super().keyPressEvent(event)


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestShortcutManagerGui(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        settings = App.ParamGet("User parameter:BaseApp/Preferences/Shortcut/Settings")
        self.timeout = settings.GetInt("ShortcutTimeout", 300)
        if self.timeout <= 0:
            self.skipTest("Ambiguous shortcut timeout is disabled")
        self.actions = []
        self.dialogs = []
        self.host = _KeyHost(Gui.getMainWindow())
        self.observation = {"case": self._testMethodName, "short": 0, "long": 0}
        self.addCleanup(self._cleanup)
        self.host.show()
        self.host.raise_()
        self.host.activateWindow()
        self.host.setFocus()
        self._wait(lambda: self.app.focusWidget() == self.host, "Host did not receive focus")

    def _wait(self, condition, message, milliseconds=None):
        if milliseconds is None:
            milliseconds = 2 * self.timeout + 1500
        timer = QtCore.QElapsedTimer()
        timer.start()
        while not condition() and timer.elapsed() < milliseconds:
            QtTest.QTest.qWait(20)
        self.assertTrue(condition(), message)

    def _cleanup(self):
        for dialog in self.dialogs:
            dialog.reject()
        for action in self.actions:
            action.setShortcut(QtGui.QKeySequence())
            self.host.removeAction(action)
            action.deleteLater()
        self.host.close()
        self.host.deleteLater()
        self.app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtTest.QTest.qWait(self.timeout + 40)
        Gui.getMainWindow().activateWindow()

    def _action(self, suffix, shortcut, callback):
        action_type = QtGui.QAction if hasattr(QtGui, "QAction") else QtWidgets.QAction
        action = action_type("Issue33598" + suffix, self.host)
        action.setObjectName("Issue33598" + suffix)
        action.setShortcutContext(QtCore.Qt.WindowShortcut)
        self.host.addAction(action)
        action.setShortcut(QtGui.QKeySequence(shortcut))
        action.triggered.connect(callback)
        self.actions.append(action)
        self.assertTrue(action.isEnabled())
        return action

    def _long_triggered(self):
        self.observation["long"] += 1

    def _short_triggered(self):
        self.observation["short"] += 1

    def _modal_triggered(self):
        self.observation["short"] += 1
        dialog = _EscapeDialog(self.host)
        self.dialogs.append(dialog)
        watchdog = QtCore.QTimer(dialog)
        watchdog.setSingleShot(True)
        first_escape = QtCore.QTimer(dialog)
        first_escape.setSingleShot(True)
        second_escape = QtCore.QTimer(dialog)
        second_escape.setSingleShot(True)

        def expire():
            self.observation["watchdog"] = True
            dialog.reject()

        def press_second():
            try:
                before = len(dialog.keys)
                QtTest.QTest.keyClick(dialog, QtCore.Qt.Key_Escape)
                self.observation["second_forwarded"] = len(dialog.keys) > before
                self.observation["second_closed"] = not dialog.isVisible()
            except Exception as error:
                self.observation["delivery_error"] = repr(error)
                dialog.reject()

        def press_first():
            try:
                self.observation["active_modal"] = self.app.activeModalWidget() == dialog
                before = len(dialog.keys)
                QtTest.QTest.keyClick(dialog, QtCore.Qt.Key_Escape)
                self.observation["first_forwarded"] = len(dialog.keys) > before
                self.observation["first_closed"] = not dialog.isVisible()
                if dialog.isVisible():
                    second_escape.start(80)
            except Exception as error:
                self.observation["delivery_error"] = repr(error)
                dialog.reject()

        watchdog.timeout.connect(expire)
        first_escape.timeout.connect(press_first)
        second_escape.timeout.connect(press_second)
        watchdog.start(1000)
        first_escape.start(80)
        execute = dialog.exec if hasattr(dialog, "exec") else dialog.exec_
        try:
            execute()
        finally:
            for timer in (watchdog, first_escape, second_escape):
                timer.stop()
        self.observation["dialog_keys"] = dialog.keys
        self.observation["completed"] = True

    def _check_modal(self, overlap):
        self._action("Short", "F35", self._modal_triggered)
        if overlap:
            self._action("Long", "F35, F34", self._long_triggered)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        self._wait(lambda: self.observation.get("completed"), "Modal shortcut did not finish")
        self.assertEqual(self.observation["short"], 1)
        self.assertEqual(self.observation["long"], 0)
        self.assertNotIn("delivery_error", self.observation)
        self.assertFalse(self.observation.get("watchdog", False), "Modal watchdog was needed")
        self.assertTrue(self.observation.get("active_modal"), "Escape did not target the actual modal")
        if not self.observation.get("first_closed"):
            self.assertTrue(self.observation.get("second_forwarded"))
            self.assertTrue(self.observation.get("second_closed"))
        self.assertTrue(self.observation.get("first_forwarded"), "First Escape was consumed before the dialog")
        self.assertTrue(self.observation.get("first_closed"), "One Escape must close the modal dialog")

    def test_overlapping_shortcut_modal_receives_first_escape(self):
        self._check_modal(overlap=True)

    def test_single_shortcut_modal_escape_control(self):
        self._check_modal(overlap=False)

    def test_overlapping_nonmodal_shortcut_releases_next_key_control(self):
        self._action("Short", "F35", self._short_triggered)
        self._action("Long", "F35, F34", self._long_triggered)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        self._wait(lambda: self.observation["short"] == 1, "Short action did not activate")
        QtTest.QTest.qWait(80)
        before = self.host.keys.count(_enum(QtCore.Qt.Key_Escape))
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_Escape)
        self.assertEqual(self.observation["long"], 0)
        self.assertEqual(self.host.keys.count(_enum(QtCore.Qt.Key_Escape)), before + 1)

    def test_longer_shortcut_wins_control(self):
        self._action("Short", "F35", self._short_triggered)
        self._action("Long", "F35, F34", self._long_triggered)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        QtTest.QTest.qWait(20)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F34)
        self._wait(lambda: self.observation["long"] == 1, "Long action did not activate")
        QtTest.QTest.qWait(self.timeout + 40)
        self.assertEqual(self.observation["short"], 0)
        self.assertEqual(self.observation["long"], 1)

    def test_reentrant_command_preserves_new_pending_shortcut(self):
        self.observation["inner"] = 0

        def inner_triggered():
            self.observation["inner"] += 1

        inner = self._action("InnerShort", "F33", inner_triggered)
        self._action("InnerLong", "F33, F32", self._long_triggered)

        def outer_triggered():
            self.observation["short"] += 1
            # Cancel any previous Qt prefix before queuing a distinct sequence.
            QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_Escape)
            QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F33)
            self.observation["inner_queued"] = not inner.isEnabled()

        self._action("OuterShort", "F35", outer_triggered)
        self._action("OuterLong", "F35, F34", self._long_triggered)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        self._wait(lambda: self.observation["short"] == 1, "Outer action did not activate")
        self.assertTrue(self.observation.get("inner_queued"), "Inner sequence was not enqueued")
        self._wait(lambda: self.observation["inner"] == 1, "Reentrant pending action was discarded")
        self.assertEqual(self.observation["short"], 1)
        self.assertEqual(self.observation["long"], 0)
        self.assertTrue(inner.isEnabled())

    def test_line_edit_typing_does_not_trigger_application_shortcuts_control(self):
        self._action("TypedShort", "M", self._short_triggered)
        self._action("TypedLong", "M, O", self._long_triggered)
        editor = QtWidgets.QLineEdit(self.host)
        editor.setGeometry(10, 10, 200, 30)
        editor.show()
        editor.setFocus()
        self._wait(lambda: self.app.focusWidget() == editor, "Line editor did not receive focus")
        QtTest.QTest.keyClicks(editor, "mo")
        QtTest.QTest.qWait(self.timeout + 40)
        self.assertEqual(editor.text(), "mo")
        self.assertEqual(self.observation["short"], 0)
        self.assertEqual(self.observation["long"], 0)

    def test_duplicate_shortcuts_activate_once_and_restore_actions_control(self):
        calls = []
        first = self._action("First", "F35", lambda: calls.append("first"))
        second = self._action("Second", "F35", lambda: calls.append("second"))
        longer = self._action("Long", "F35, F34", self._long_triggered)
        QtTest.QTest.keyClick(self.host, QtCore.Qt.Key_F35)
        self._wait(lambda: bool(calls), "No matching action activated")
        QtTest.QTest.qWait(self.timeout + 40)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.observation["long"], 0)
        self.assertTrue(all(action.isEnabled() for action in (first, second, longer)))
