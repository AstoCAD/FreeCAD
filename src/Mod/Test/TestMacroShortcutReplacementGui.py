# SPDX-License-Identifier: LGPL-2.1-or-later
"""Macro shortcuts follow native Replace without reprioritizing unchanged keys.

These GUI tests require a disposable profile explicitly selected before FreeCAD
starts. Set FREECAD_TEST_ISOLATED_PROFILE and FREECAD_USER_HOME to that same
existing absolute directory. Ordinary sessions skip before test-owned writes.
Close/reopen checks the existing command in process, not saved macro metadata.
"""

import hashlib
import json
import os
from pathlib import Path
import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the native Customize Macros page")
class TestMacroShortcutReplacement14824Gui(unittest.TestCase):
    def setUp(self):
        self.dialog = None
        self.command_name = None
        self.file_created = False
        self.directory_created = False
        self.cleaned = False
        self.toolbar_scope = None
        self.profile = self._owned_profile()
        self.assertEqual(App.listDocuments(), {})
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        self._events(300)
        self.main = Gui.getMainWindow()
        self.assertEqual(self._dialogs(), [])
        self.original_commands = tuple(sorted(Gui.Command.listAll()))
        self.assertFalse(any(name.startswith("Std_Macro_") for name in self.original_commands))
        self.main_geometry = QtCore.QRect(self.main.geometry())
        self.main_state = self.main.windowState()
        workbench = Gui.activeWorkbench()
        self.workbench = workbench.name() if workbench else None
        self.cursor = QtGui.QCursor.pos()
        areas = self.main.findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]
        self.initial_windows = tuple(self.area.subWindowList())
        self.reports = [
            (widget, widget.toPlainText())
            for widget in self.main.findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(self.reports)

        self.base = App.ParamGet("User parameter:BaseApp")
        # These groups are already owned by initialized application managers.
        # Do not create/remove their namespaces as a test setup/cleanup shortcut.
        self.assertTrue(self.base.HasGroup("Preferences"))
        self.preferences = self.base.GetGroup("Preferences")
        self.assertTrue(self.base.HasGroup("Macro"))
        self.macro_before = self._tree(self.base, "Macro")
        self.macros = self.base.GetGroup("Macro")
        self.persisted_macros_before = self._tree(self.macros, "Macros")
        if self.persisted_macros_before is not None:
            self.assertEqual(self.persisted_macros_before, ((), ()))
        self.assertTrue(self.preferences.HasGroup("Macro"))
        self.macro_preferences_before = self._tree(self.preferences, "Macro")
        self.assertFalse(any(entry[1] == "MacroPath" for entry in self.macro_preferences_before[0]))
        self.assertTrue(self.preferences.HasGroup("Shortcut"))
        self.shortcut_before = self._tree(self.preferences, "Shortcut")
        self.shortcuts = self.preferences.GetGroup("Shortcut")
        self.assertTrue(self.shortcuts.HasGroup("Priorities"))
        self.assertTrue(self.shortcuts.HasGroup("Settings"))
        self.priorities = self.shortcuts.GetGroup("Priorities")
        self.workbench_before = self._tree(self.base, "Workbench")
        # A fresh diagnostic profile must contain no saved custom toolbar data.
        # This admission precedes even opening a dialog whose hideEvent exports it.
        if self.workbench_before is not None:
            for _scope, (_entries, children) in self.workbench_before[1]:
                toolbar = dict(children).get("Toolbar")
                if toolbar is not None:
                    self.assertEqual(toolbar, ((), ()))
        self.assertFalse(
            any(entry[1].startswith("Std_Macro_") for entry in self.shortcuts.GetContents() or ())
        )
        self.assertFalse(
            any(entry[1].startswith("Std_Macro_") for entry in self.priorities.GetContents() or ())
        )

        macro_directory = Path(App.getUserMacroDir(True)).absolute()
        self._owned_path(macro_directory)
        self.assertEqual(macro_directory.resolve(), Path(App.getUserMacroDir()).resolve())
        self.macro_directory = macro_directory
        self.directory_existed = macro_directory.exists()
        self.directory_entries_before = (
            tuple(sorted(path.name for path in macro_directory.iterdir()))
            if self.directory_existed
            else ()
        )
        if self.directory_existed:
            self.assertTrue(macro_directory.is_dir())
        else:
            self.assertTrue(macro_directory.parent.is_dir())
        self.filename = "Shortcut14824_" + uuid4().hex + ".FCMacro"
        self.path = macro_directory / self.filename
        self._owned_path(self.path)
        self.assertFalse(self.path.exists())
        self.payload = b"# Owned shortcut diagnostic; this macro must never be executed.\n"
        self.payload_hash = hashlib.sha256(self.payload).hexdigest()
        self.menu_old = self.filename[:-8] + "_old"
        self.menu_new = self.filename[:-8] + "_new"
        self.old_key = QtGui.QKeySequence("Ctrl+Alt+Shift+F11", QtGui.QKeySequence.PortableText)
        self.new_key = QtGui.QKeySequence("Ctrl+Alt+Shift+F12", QtGui.QKeySequence.PortableText)
        self.assertFalse(self.old_key.isEmpty())
        self.assertFalse(self.new_key.isEmpty())
        self.assertNotEqual(self.old_key, self.new_key)
        # This API observes existing QActions only; no action is initialized here.
        for key in (self.old_key, self.new_key):
            self.assertEqual(Gui.Command.listByShortcut(key.toString()), [])
        self.addCleanup(self._cleanup)
        if not self.directory_existed:
            macro_directory.mkdir()
            self.directory_created = True
        with self.path.open("xb") as stream:
            self.file_created = True
            stream.write(self.payload)
        self._open()
        self.assertEqual(self._listing().topLevelItemCount(), 0)

    def _owned_profile(self):
        selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
        if not selected:
            self.skipTest("Requires an explicitly selected disposable test profile")
        import stat

        def plain_path(path):
            for component in (path, *path.parents):
                try:
                    if component.is_symlink():
                        return False
                    is_junction = getattr(component, "is_junction", None)
                    if is_junction is not None and is_junction():
                        return False
                    attributes = getattr(component.lstat(), "st_file_attributes", 0)
                    if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                        return False
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
            return True

        raw = Path(selected)
        if not raw.is_absolute() or not plain_path(raw):
            self.skipTest("The disposable test profile must be an absolute directory without links")
        try:
            profile = raw.resolve(strict=True)
        except OSError:
            self.skipTest("The disposable test profile must already exist")
        if not profile.is_dir():
            self.skipTest("The disposable test profile must be a directory")
        configured_home = os.environ.get("FREECAD_USER_HOME")
        if not configured_home:
            self.skipTest("FREECAD_USER_HOME must explicitly select the disposable test profile")
        home = Path(configured_home)
        if not home.is_absolute() or not plain_path(home):
            self.skipTest("FREECAD_USER_HOME must be an absolute directory without links")
        try:
            matching_home = home.resolve(strict=True) == profile
        except OSError:
            matching_home = False
        if not matching_home:
            self.skipTest("FREECAD_USER_HOME does not match the disposable test profile")
        parameter_file = Path(App.ConfigGet("UserParameter"))
        data_directory = Path(App.getUserAppDataDir())
        macro_directory = Path(App.getUserMacroDir())
        paths = (parameter_file, data_directory, macro_directory)
        if not all(path.is_absolute() and plain_path(path) for path in paths):
            self.skipTest("Active profile paths must be absolute and free of links")
        if parameter_file.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside the selected test profile")
        if not all(path.resolve().is_relative_to(profile) for path in paths):
            self.skipTest(
                "Active user configuration, data and macros must stay in the test profile"
            )
        return profile

    def _owned_path(self, path):
        self.assertTrue(path.is_relative_to(self.profile))
        self.assertTrue(path.resolve().is_relative_to(self.profile))
        current = self.profile
        for part in path.relative_to(self.profile).parts:
            current = current / part
            self.assertFalse(current.is_symlink())

    @classmethod
    def _node(cls, group):
        entries = tuple(sorted(group.GetContents() or (), key=lambda entry: entry[:2]))
        children = tuple(
            (name, cls._node(group.GetGroup(name))) for name in sorted(group.GetGroups())
        )
        return entries, children

    @classmethod
    def _tree(cls, parent, name):
        # HasGroup precedes GetGroup so an absent child stays absent.
        return cls._node(parent.GetGroup(name)) if parent.HasGroup(name) else None

    @classmethod
    def _with_empty_path(cls, node, names):
        entries, children = node if node is not None else ((), ())
        mapped = dict(children)
        if names:
            name, *rest = names
            mapped[name] = cls._with_empty_path(mapped.get(name), rest)
        return entries, tuple(sorted(mapped.items()))

    @staticmethod
    def _events(milliseconds=150):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            self._events(50)
        self.fail(message)

    def _dialogs(self):
        return [
            dialog
            for dialog in self.main.findChildren(QtWidgets.QDialog)
            if dialog.inherits("Gui::Dialog::DlgCustomizeImp")
        ]

    def _open(self):
        self.assertIsNone(self.dialog)
        self.assertEqual(self._dialogs(), [])
        self.assertTrue(Gui.Command.get("Std_DlgCustomize").isActive())
        Gui.runCommand("Std_DlgCustomize")
        self._wait(lambda: len(self._dialogs()) == 1, "Owned Customize dialog did not appear")
        self.dialog = self._dialogs()[0]
        self.assertEqual(self.dialog.parentWidget(), self.main)
        self.assertFalse(self.dialog.isModal())
        self.assertTrue(self.dialog.testAttribute(QtCore.Qt.WA_DeleteOnClose))
        tabs = self.dialog.findChildren(QtWidgets.QTabWidget, "Gui__Dialog__TabWidget")
        self.assertEqual(len(tabs), 1)
        toolbars = self.dialog.findChildren(QtWidgets.QWidget, "Gui__Dialog__DlgCustomToolbars")
        self.assertEqual(len(toolbars), 1)
        combos = toolbars[0].findChildren(QtWidgets.QComboBox, "workbenchBox")
        listings = toolbars[0].findChildren(QtWidgets.QTreeWidget, "toolbarTreeWidget")
        self.assertEqual(len(combos), 1)
        self.assertEqual(len(listings), 1)
        scope = combos[0].currentData(QtCore.Qt.UserRole)
        self.assertIsInstance(scope, str)
        self.assertTrue(scope)
        self.assertEqual(scope, self.workbench if self.workbench else "Global")
        if self.toolbar_scope is None:
            self.toolbar_scope = scope
        self.assertEqual(scope, self.toolbar_scope)
        self.assertEqual(listings[0].topLevelItemCount(), 0)
        original = dict(self.workbench_before[1]) if self.workbench_before is not None else {}
        if scope in original:
            toolbar = dict(original[scope][1]).get("Toolbar")
            if toolbar is not None:
                self.assertEqual(toolbar, ((), ()))
        pages = self.dialog.findChildren(QtWidgets.QWidget, "Gui__Dialog__DlgCustomActions")
        self.assertEqual(len(pages), 1)
        index = tabs[0].indexOf(pages[0])
        self.assertGreaterEqual(index, 0)
        tabs[0].setCurrentIndex(index)
        self._events(200)
        self.assertTrue(pages[0].isVisible())

    def _page(self):
        pages = self.dialog.findChildren(QtWidgets.QWidget, "Gui__Dialog__DlgCustomActions")
        self.assertEqual(len(pages), 1)
        return pages[0]

    def _widget(self, kind, name):
        widgets = self._page().findChildren(kind, name)
        self.assertEqual(len(widgets), 1)
        self.assertTrue(widgets[0].isVisible())
        self.assertTrue(widgets[0].isEnabled())
        return widgets[0]

    def _listing(self):
        return self._widget(QtWidgets.QTreeWidget, "actionListWidget")

    def _key_edit(self):
        edit = self._widget(QtWidgets.QKeySequenceEdit, "actionAccel")
        self.assertTrue(edit.inherits("Gui::AccelLineEdit"))
        return edit

    def _button(self, name):
        return self._widget(QtWidgets.QPushButton, name)

    def _add(self):
        combo = self._widget(QtWidgets.QComboBox, "actionMacros")
        index = combo.findText(self.filename, QtCore.Qt.MatchExactly)
        self.assertGreaterEqual(index, 0)
        self.assertFalse(combo.itemData(index))
        combo.setCurrentIndex(index)
        self._widget(QtWidgets.QLineEdit, "actionMenu").setText(self.menu_old)
        self._key_edit().setKeySequence(self.old_key)
        self.assertEqual(self._key_edit().keySequence(), self.old_key)
        self._button("buttonAddAction").click()
        self._wait(
            lambda: self._listing().topLevelItemCount() == 1, "GUI Add did not add one macro"
        )
        item = self._listing().topLevelItem(0)
        name = bytes(item.data(1, QtCore.Qt.UserRole)).decode("ascii")
        self.command_name = name
        self.assertRegex(name, r"^Std_Macro_[0-9]+$")
        self.assertNotIn(name, self.original_commands)
        self.assertEqual(Gui.Command.findCustomCommand(self.filename), name)
        self.assertEqual(item.text(1), self.menu_old)
        self._activate()
        self._events(200)

    def _activate(self):
        listing = self._listing()
        self.assertEqual(listing.topLevelItemCount(), 1)
        item = listing.topLevelItem(0)
        self.assertEqual(bytes(item.data(1, QtCore.Qt.UserRole)).decode("ascii"), self.command_name)
        listing.setCurrentItem(item)
        # This public native activation signal is the UI connection in DlgActionsImp.
        listing.itemActivated.emit(item, 1)
        self._events(200)

    def _entry(self, group):
        return tuple(entry for entry in group.GetContents() or () if entry[1] == self.command_name)

    def _observe(self):
        self._activate()
        command = Gui.Command.get(self.command_name)
        self.assertIsNotNone(command)
        actions = command.getAction()
        self.assertLessEqual(len(actions), 1)
        # Observe a genuinely existing action only; this diagnostic never initializes it.
        action_keys = tuple(
            action.shortcut().toString(QtGui.QKeySequence.PortableText) for action in actions
        )
        public_key = (
            QtGui.QKeySequence(command.getShortcut()).toString(QtGui.QKeySequence.PortableText)
            if actions
            else None
        )
        observation = {
            "field": self._key_edit().keySequence().toString(QtGui.QKeySequence.PortableText),
            "menu": self._widget(QtWidgets.QLineEdit, "actionMenu").text(),
            "override": self._entry(self.shortcuts),
            "priority": self._entry(self.priorities),
            "action_keys": action_keys,
            "public_key": public_key,
        }
        print("MACRO14824 " + json.dumps(observation, sort_keys=True))
        return observation

    def _close(self):
        if self.dialog is None:
            self.assertEqual(self._dialogs(), [])
            return
        expected = QtCore.QCoreApplication.translate("Gui::Dialog::DlgCustomizeImp", "&Close")
        buttons = [
            button
            for button in self.dialog.findChildren(QtWidgets.QPushButton)
            if button.parentWidget() == self.dialog and button.text() == expected
        ]
        self.assertEqual(len(buttons), 1)
        self.assertTrue(buttons[0].isEnabled())
        self.dialog = None
        buttons[0].click()
        buttons = None
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self._events(200)
        self._wait(lambda: self._dialogs() == [], "Owned Customize dialog was not destroyed")

    def _reopen(self):
        self._close()
        self._open()
        # Reopen observes the existing command in this process, not disk persistence.
        return self._observe()

    def _replace(self, key):
        self._activate()
        self._widget(QtWidgets.QLineEdit, "actionMenu").setText(self.menu_new)
        self._key_edit().setKeySequence(key)
        self.assertEqual(self._key_edit().keySequence(), key)
        self._button("buttonReplaceAction").click()
        self._events(200)
        return self._observe()

    def _assert_observation(self, actual, key, menu):
        expected = key.toString(QtGui.QKeySequence.PortableText)
        with self.subTest(oracle="native_keySequence"):
            self.assertEqual(actual["field"], expected)
        self.assertEqual(actual["menu"], menu)
        for action_key in actual["action_keys"]:
            with self.subTest(oracle="genuine_action"):
                self.assertEqual(action_key, expected)
        if actual["public_key"] is not None:
            with self.subTest(oracle="genuine_public_shortcut"):
                self.assertEqual(actual["public_key"], expected)

    def _priority_value(self, observation):
        entries = observation["priority"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][:2], ("Integer", self.command_name))
        return entries[0][2]

    def test_add_old_shortcut_then_reopen_control(self):
        self._add()
        before = self._observe()
        after = self._reopen()
        self._cleanup()
        self._assert_observation(before, self.old_key, self.menu_old)
        self._assert_observation(after, self.old_key, self.menu_old)
        expected = (("String", self.command_name, self.old_key.toString()),)
        self.assertEqual(before["override"], expected)
        self.assertEqual(after["override"], expected)
        self.assertEqual(after["priority"], before["priority"])
        self.assertGreater(self._priority_value(before), 0)

    def test_same_key_menu_replacement_preserves_priority_control(self):
        self._add()
        before = self._reopen()
        replaced = self._replace(self.old_key)
        after = self._reopen()
        self._cleanup()
        self._assert_observation(replaced, self.old_key, self.menu_new)
        self._assert_observation(after, self.old_key, self.menu_new)
        self.assertEqual(replaced["override"], before["override"])
        self.assertEqual(after["override"], before["override"])
        self.assertEqual(replaced["priority"], before["priority"])
        self.assertEqual(after["priority"], before["priority"])

    def test_replacement_changes_nonempty_shortcut_and_persists_target(self):
        self._add()
        before = self._reopen()
        replaced = self._replace(self.new_key)
        after = self._reopen()
        self._cleanup()
        # Target observations are asserted only after owned native/filesystem/parameter cleanup.
        self._assert_observation(replaced, self.new_key, self.menu_new)
        self._assert_observation(after, self.new_key, self.menu_new)
        with self.subTest(oracle="manager_override_after_replace"):
            self.assertEqual(replaced["override"], ())
        with self.subTest(oracle="manager_override_after_reopen"):
            self.assertEqual(after["override"], ())
        with self.subTest(oracle="changed_key_priority"):
            self.assertGreater(self._priority_value(replaced), self._priority_value(before))
        self.assertEqual(after["priority"], replaced["priority"])

    def _cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        try:
            if self.command_name is not None and Gui.Command.get(self.command_name) is not None:
                if self.dialog is None:
                    self._open()
                self.assertEqual(Gui.Command.findCustomCommand(self.filename), self.command_name)
                listing = self._listing()
                self.assertEqual(listing.topLevelItemCount(), 1)
                item = listing.topLevelItem(0)
                self.assertEqual(
                    bytes(item.data(1, QtCore.Qt.UserRole)).decode("ascii"), self.command_name
                )
                listing.setCurrentItem(item)
                item = None
                listing = None
                self._button("buttonRemoveAction").click()
                self._events(200)
                self.assertIsNone(Gui.Command.get(self.command_name))
                self.assertIsNone(Gui.Command.findCustomCommand(self.filename))
        finally:
            self._close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self._events(200)
        if self.command_name is not None:
            # The derived event path does not establish the reset callback.
            # After ordinary GUI removal, clean only originally absent owned keys.
            self.assertIsNone(Gui.Command.get(self.command_name))
            self.assertNotIn(self.command_name, {entry[1] for entry in self.shortcut_before[0]})
            original_priorities = dict(self.shortcut_before[1])["Priorities"]
            self.assertNotIn(self.command_name, {entry[1] for entry in original_priorities[0]})
            for group, tag, remover in (
                (self.shortcuts, "String", self.shortcuts.RemString),
                (self.priorities, "Integer", self.priorities.RemInt),
            ):
                entries = self._entry(group)
                self.assertLessEqual(len(entries), 1)
                if entries:
                    self.assertEqual(entries[0][:2], (tag, self.command_name))
                    remover(self.command_name)
        self.assertEqual(self._tree(self.base, "Macro"), self.macro_before)
        self.assertEqual(self._tree(self.preferences, "Macro"), self.macro_preferences_before)
        self.assertEqual(self._tree(self.preferences, "Shortcut"), self.shortcut_before)
        expected_workbench = self.workbench_before
        if self.toolbar_scope is not None:
            expected_workbench = self._with_empty_path(
                expected_workbench, (self.toolbar_scope, "Toolbar")
            )
        self.assertEqual(self._tree(self.base, "Workbench"), expected_workbench)
        self.assertEqual(tuple(sorted(Gui.Command.listAll())), self.original_commands)
        self._owned_path(self.path)
        if self.file_created:
            self.assertTrue(self.path.is_file())
            self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.payload_hash)
            self.path.unlink()
        self.assertFalse(self.path.exists())
        self._owned_path(self.macro_directory)
        if self.directory_created:
            self.assertEqual(tuple(self.macro_directory.iterdir()), ())
            self.macro_directory.rmdir()
        self.assertEqual(self.macro_directory.exists(), self.directory_existed)
        if self.directory_existed:
            self.assertEqual(
                tuple(sorted(path.name for path in self.macro_directory.iterdir())),
                self.directory_entries_before,
            )
        QtGui.QCursor.setPos(self.cursor)
        self._events(200)
        self.assertEqual(QtGui.QCursor.pos(), self.cursor)
        self.assertEqual(App.listDocuments(), {})
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        self.assertEqual(self._dialogs(), [])
        self.assertEqual(tuple(self.area.subWindowList()), self.initial_windows)
        self.assertEqual(self.main.geometry(), self.main_geometry)
        self.assertEqual(self.main.windowState(), self.main_state)
        workbench = Gui.activeWorkbench()
        self.assertEqual(workbench.name() if workbench else None, self.workbench)
        for report, previous in self.reports:
            current = report.toPlainText()
            self.assertTrue(current.startswith(previous))
            added = current[len(previous) :]
            for marker in (
                "Traceback",
                "Unhandled Base::Exception",
                "Unhandled std::exception",
                "Unhandled unknown exception",
                "Access violation",
                "Python exception",
            ):
                self.assertNotIn(marker, added)
