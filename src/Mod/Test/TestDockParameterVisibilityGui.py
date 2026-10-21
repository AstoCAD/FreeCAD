# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dock visibility follows asynchronous changes to canonical user parameters."""

import os
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestDockParameterVisibilityGui(unittest.TestCase):
    def setUp(self):
        self.audit_mode = bool(
            os.environ.get("ASTO_AUDIT_CASE") or os.environ.get("ASTO_AUDIT_LABEL")
        )
        if self.audit_mode:
            self._owned_profile()
        self.window = Gui.getMainWindow()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(Gui.Control.activeDialog())
        self.overlay_preferences = App.ParamGet("User parameter:BaseApp/Preferences/DockWindows")
        if not self.overlay_preferences.GetBool("ActivateOverlay", True):
            if self.audit_mode:
                self.fail("Overlay management must already be enabled in the isolated GUI profile")
            self.skipTest("Overlay management is disabled in this GUI session")
        self.parameters = App.ParamGet("User parameter:BaseApp/MainWindow/DockWindows")
        self.python = self._dock("Python console", "Std_PythonView")
        self.report = self._dock("Report view", "Std_ReportView")
        self.docks = (self.python, self.report)
        self.all_docks = tuple(self.window.findChildren(QtWidgets.QDockWidget))
        self.original_visibility = [
            (dock, dock.isVisible(), dock.isHidden()) for dock in self.all_docks
        ]
        self.original_parameters = {
            ("Boolean", "Std_PythonView"): self._parameter("Boolean", "Std_PythonView"),
            ("Boolean", "Std_ReportView"): self._parameter("Boolean", "Std_ReportView"),
            ("Integer", "CursorMargin"): self._parameter("Integer", "CursorMargin"),
        }
        self.original_documents = tuple(sorted(App.listDocuments()))
        self.original_active_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.addCleanup(self._restore)
        self._via_action(self.report, False)
        self._via_action(self.python, False)
        self._pump(200)
        self.assertFalse(self.python.isVisible())
        self.assertFalse(self.report.isVisible())

    def _owned_profile(self):
        label = os.environ.get("ASTO_AUDIT_LABEL", "")
        self.assertTrue(label)
        self.assertNotIn("/", label)
        self.assertNotIn("\\", label)
        profile = Path(os.environ["FREECAD_USER_HOME"]).resolve()
        self.assertEqual(profile.name, label + "-profile")
        output = profile.parent
        self.assertEqual(output.name, "issue-audit-20261019")
        self.assertEqual(output.parent.name, ".codex-test-bin")
        workspace = output.parent.parent
        self.assertTrue((workspace / ".git").exists())
        self.assertTrue(Path(__file__).resolve().is_relative_to(workspace))
        self.assertEqual(Path(os.environ["ASTO_AUDIT_SOURCE"]).resolve(), Path(__file__).resolve())
        self.assertTrue(profile.is_relative_to(output))
        self.assertTrue(profile.is_dir())
        self.assertEqual(Path(App.ConfigGet("UserParameter")).resolve(), profile / "user.cfg")
        actual_data = Path(App.getUserAppDataDir()).resolve()
        self.assertTrue(actual_data.is_relative_to(profile))
        self.assertEqual(Path(App.ConfigGet("UserAppData")).resolve(), actual_data)

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=2):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            self._pump()
        return bool(predicate())

    def _dock(self, name, key):
        docks = [
            dock
            for dock in self.window.findChildren(QtWidgets.QDockWidget)
            if dock.objectName() == name
        ]
        if not docks and not self.audit_mode:
            self.skipTest(name + " is not enabled in this GUI session")
        self.assertEqual(len(docks), 1, name)
        dock = docks[0]
        inner = dock.widget()
        self.assertIsNotNone(inner)
        self.assertNotIsInstance(inner, QtWidgets.QDockWidget)
        self.assertEqual(inner.parentWidget(), dock)
        action = dock.toggleViewAction()
        self.assertTrue(action.isCheckable())
        self.assertEqual(action.parent(), dock)
        self.assertEqual(action.data(), key)
        title = dock.titleBarWidget()
        if not self.audit_mode and (title is None or title.objectName() != "OverlayTitle"):
            self.skipTest("Overlay management was not installed when this GUI session started")
        self.assertIsNotNone(title)
        self.assertEqual(title.objectName(), "OverlayTitle")
        return dock

    def _parameter(self, kind, key):
        matches = [
            value
            for entry_kind, name, value in (self.parameters.GetContents() or [])
            if entry_kind == kind and name == key
        ]
        self.assertLessEqual(len(matches), 1)
        return (bool(matches), matches[0] if matches else None)

    def _via_action(self, dock, visible):
        action = dock.toggleViewAction()
        # Always finish through a real triggered action, also creating the canonical bool
        # when the requested initial visibility happened to match the fresh profile.
        if action.isChecked() == visible:
            action.trigger()
            self._pump()
        action.trigger()
        if visible:
            dock.raise_()
        self.assertTrue(
            self._wait(lambda: dock.isVisible() == visible and action.isChecked() == visible),
            (dock.objectName(), visible, dock.isVisible(), action.isChecked()),
        )
        self.assertEqual(self._parameter("Boolean", action.data()), (True, visible))

    def _document_state_unchanged(self):
        self.assertEqual(tuple(sorted(App.listDocuments())), self.original_documents)
        self.assertEqual(
            App.ActiveDocument.Name if App.ActiveDocument else None,
            self.original_active_document,
        )

    def _restore(self):
        for (kind, key), (present, value) in self.original_parameters.items():
            if kind == "Boolean":
                if present:
                    self.parameters.SetBool(key, value)
                else:
                    self.parameters.RemBool(key)
            else:
                if present:
                    self.parameters.SetInt(key, value)
                else:
                    self.parameters.RemInt(key)
        # Let genuine parameter notifications finish before restoring any transient
        # visibility that differed from the user's saved preference at entry.
        self._pump(200)
        for dock, _visible, hidden in self.original_visibility:
            dock.setVisible(not hidden)
        for dock, visible, _hidden in self.original_visibility:
            if visible:
                dock.raise_()
        self._pump()
        for dock, visible, hidden in self.original_visibility:
            self.assertEqual(dock.isHidden(), hidden, dock.objectName())
            self.assertEqual(dock.isVisible(), visible, dock.objectName())
        for (kind, key), expected in self.original_parameters.items():
            self.assertEqual(self._parameter(kind, key), expected)
        self._document_state_unchanged()

    def test_bool_parameter_hides_visible_python_console(self):
        self._via_action(self.python, True)
        self.assertFalse(self.report.isVisible())
        self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, True))
        self.parameters.SetBool(self.python.toggleViewAction().data(), False)
        self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, False))
        self._pump(200)
        self.assertTrue(
            self._wait(lambda: not self.python.isVisible()),
            "The real 100ms parameter observer must hide the Python console",
        )
        self.assertFalse(self.report.isVisible())
        self.assertEqual(self._parameter("Boolean", "Std_ReportView"), (True, False))
        self._document_state_unchanged()

    def test_bool_parameter_shows_hidden_report_view(self):
        self.assertFalse(self.report.isVisible())
        self.assertEqual(self._parameter("Boolean", "Std_ReportView"), (True, False))
        self.parameters.SetBool(self.report.toggleViewAction().data(), True)
        self.assertEqual(self._parameter("Boolean", "Std_ReportView"), (True, True))
        self._pump(200)
        self.assertTrue(
            self._wait(lambda: self.report.isVisible()),
            "The real 100ms parameter observer must show the Report view",
        )
        self.assertFalse(self.python.isVisible())
        self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, False))
        self._document_state_unchanged()

    def test_individual_toggle_actions_persist_only_their_dock_control(self):
        for visible in (True, False):
            self._via_action(self.report, visible)
            self._pump(200)
            self.assertEqual(self.report.isVisible(), visible)
            self.assertFalse(self.python.isVisible())
            self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, False))
        self._document_state_unchanged()

    def test_nonbool_cursor_margin_change_preserves_visibility_control(self):
        self._via_action(self.python, True)
        # A normal QWidget hide does not trigger the toggle action's persistence
        # callback. Keep this genuine mismatch to detect an unwanted bool timer.
        self.python.hide()
        self.assertTrue(self._wait(lambda: not self.python.isVisible()))
        self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, True))
        before = (self.python.isVisible(), self.report.isVisible())
        self.assertEqual(before, (False, False))
        original = self.parameters.GetInt("CursorMargin", 5)
        value = 7 if original != 7 else 6
        self.parameters.SetInt("CursorMargin", value)
        self.assertEqual(self._parameter("Integer", "CursorMargin"), (True, value))
        self._pump(250)
        self.assertEqual((self.python.isVisible(), self.report.isVisible()), before)
        self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (True, True))
        self.assertEqual(self._parameter("Boolean", "Std_ReportView"), (True, False))
        self._document_state_unchanged()

    def test_missing_bool_key_retains_current_visibility_control(self):
        for visible in (True, False):
            self._via_action(self.python, visible)
            self.parameters.RemBool(self.python.toggleViewAction().data())
            self.assertEqual(self._parameter("Boolean", "Std_PythonView"), (False, None))
            self._pump(200)
            self.assertEqual(self.python.isVisible(), visible)
            self.assertFalse(self.report.isVisible())
            self.assertEqual(self._parameter("Boolean", "Std_ReportView"), (True, False))
        self._document_state_unchanged()


if __name__ == "__main__":
    unittest.main()
