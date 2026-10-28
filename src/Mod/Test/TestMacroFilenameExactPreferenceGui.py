# SPDX-License-Identifier: LGPL-2.1-or-later
"""Macro row activation prefers an available exact filename.

GUI tests require a disposable profile explicitly selected before FreeCAD starts:
FREECAD_TEST_ISOLATED_PROFILE and FREECAD_USER_HOME must name the same existing
absolute directory. Generated macro files are never executed. Close/reopen tests
in-process script identity, without claiming disk persistence or key dispatch.
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
class TestMacroFilenameExactPreferenceGui(unittest.TestCase):
    def setUp(self):
        self.dialog = None
        self.command_name = None
        self.created_paths = []
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
        self.stem = "AuditFoo_" + uuid4().hex
        self.short_filename = self.stem + ".FCMacro"
        self.long_filename = self.short_filename + "_extra.py"
        self.owned_filenames = (self.short_filename, self.long_filename)
        self.created_filenames = (
            (self.short_filename,)
            if self._testMethodName == "test_short_filename_without_collision_control"
            else self.owned_filenames
        )
        self.filename = (
            self.long_filename
            if self._testMethodName == "test_long_filename_with_prefix_neighbor_control"
            else self.short_filename
        )
        self.paths = tuple(macro_directory / name for name in self.owned_filenames)
        for path in self.paths:
            self._owned_path(path)
            self.assertFalse(path.exists())
        self.system_directory = Path(App.getHomePath()) / "Macro"
        # Exclude every unowned same-prefix candidate before creating any file.
        for directory in (macro_directory, self.system_directory):
            if directory.exists():
                self.assertTrue(directory.is_dir())
                self.assertEqual(
                    tuple(
                        path.name
                        for path in directory.iterdir()
                        if path.name.startswith(self.short_filename)
                    ),
                    (),
                )
        self.payload = b"# Owned filename diagnostic; this macro must never be executed.\n"
        self.payload_hash = hashlib.sha256(self.payload).hexdigest()
        self.menu_old = self.stem + "_old"
        self.menu_new = self.stem + "_new"
        self.addCleanup(self._cleanup)
        if not self.directory_existed:
            macro_directory.mkdir()
            self.directory_created = True
        for path in self.paths:
            if path.name in self.created_filenames:
                with path.open("xb") as stream:
                    self.created_paths.append(path)
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
        self._admit_macro_entries()

    def _admit_macro_entries(self):
        combo = self._widget(QtWidgets.QComboBox, "actionMacros")
        entries = tuple(
            (combo.itemText(index), bool(combo.itemData(index)), index)
            for index in range(combo.count())
            if combo.itemText(index).startswith(self.short_filename)
        )
        self.assertEqual(len(entries), len(self.created_filenames))
        self.assertEqual(
            sorted(name for name, _system, _index in entries), sorted(self.created_filenames)
        )
        self.assertTrue(all(not system for _name, system, _index in entries))
        if self._testMethodName == "test_short_filename_with_earlier_prefix_neighbor_target":
            indices = {name: index for name, _system, index in entries}
            self.assertLess(indices[self.long_filename], indices[self.short_filename])

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
        index = combo.findText(self.filename, QtCore.Qt.MatchExactly | QtCore.Qt.MatchCaseSensitive)
        self.assertGreaterEqual(index, 0)
        self.assertFalse(combo.itemData(index))
        combo.setCurrentIndex(index)
        self._widget(QtWidgets.QLineEdit, "actionMenu").setText(self.menu_old)
        self.assertTrue(self._key_edit().keySequence().isEmpty())
        self._button("buttonAddAction").click()
        self._wait(
            lambda: self._listing().topLevelItemCount() == 1, "GUI Add did not add one macro"
        )
        item = self._listing().topLevelItem(0)
        name = bytes(item.data(1, QtCore.Qt.UserRole)).decode("ascii")
        self.command_name = name
        self.assertRegex(name, r"^Std_Macro_[0-9]+$")
        self.assertNotIn(name, self.original_commands)
        self.assertIsNotNone(Gui.Command.get(name))
        return self._snapshot()

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
        return self._snapshot()

    def _snapshot(self):
        combo = self._widget(QtWidgets.QComboBox, "actionMacros")
        listing = self._listing()
        self.assertEqual(listing.topLevelItemCount(), 1)
        item = listing.topLevelItem(0)
        self.assertEqual(bytes(item.data(1, QtCore.Qt.UserRole)).decode("ascii"), self.command_name)
        observation = {
            "selected_filename": combo.currentText(),
            "selected_system": bool(combo.currentData(QtCore.Qt.UserRole)),
            "shortcut_empty": self._key_edit().keySequence().isEmpty(),
            "row_menu": item.text(1),
            "field_menu": self._widget(QtWidgets.QLineEdit, "actionMenu").text(),
            "lookups": tuple(
                (name, Gui.Command.findCustomCommand(name)) for name in self.owned_filenames
            ),
            "override": self._entry(self.shortcuts),
            "priority": self._entry(self.priorities),
        }
        print("MACRO_FILENAME " + json.dumps(observation, sort_keys=True))
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

    def _replace(self):
        self._activate()
        self._widget(QtWidgets.QLineEdit, "actionMenu").setText(self.menu_new)
        self.assertTrue(self._key_edit().keySequence().isEmpty())
        self._button("buttonReplaceAction").click()
        self._events(200)
        return self._observe()

    def _assert_observation(self, actual, menu, activated=True):
        with self.subTest(oracle="native_filename"):
            self.assertEqual(actual["selected_filename"], self.filename)
        self.assertFalse(actual["selected_system"])
        self.assertTrue(actual["shortcut_empty"])
        self.assertEqual(actual["row_menu"], menu)
        self.assertEqual(actual["field_menu"], menu if activated else "")
        self.assertEqual(actual["override"], ())
        self.assertEqual(actual["priority"], ())
        for filename, command in actual["lookups"]:
            with self.subTest(oracle="exact_script_identity", filename=filename):
                self.assertEqual(command, self.command_name if filename == self.filename else None)

    def _run_case(self):
        created = self._add()
        activated = self._observe()
        replaced = self._replace()
        reopened = self._reopen()
        self._cleanup()
        # All functional filename/data assertions follow complete owned cleanup.
        self._assert_observation(created, self.menu_old, activated=False)
        for phase, observation, menu in (
            ("activation", activated, self.menu_old),
            ("replace", replaced, self.menu_new),
            ("reopen", reopened, self.menu_new),
        ):
            with self.subTest(phase=phase):
                self._assert_observation(observation, menu)

    def test_short_filename_without_collision_control(self):
        self._run_case()

    def test_long_filename_with_prefix_neighbor_control(self):
        self._run_case()

    def test_short_filename_with_earlier_prefix_neighbor_target(self):
        self._run_case()

    def _cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        try:
            if self.command_name is not None and Gui.Command.get(self.command_name) is not None:
                if self.dialog is None:
                    self._open()
                # A before-fix Replace may retarget this owned command to the other owned file.
                owned_scripts = tuple(
                    name
                    for name in self.created_filenames
                    if Gui.Command.findCustomCommand(name) == self.command_name
                )
                self.assertEqual(len(owned_scripts), 1)
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
                for filename in self.owned_filenames:
                    self.assertIsNone(Gui.Command.findCustomCommand(filename))
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
        for filename in self.owned_filenames:
            self.assertIsNone(Gui.Command.findCustomCommand(filename))
        for path in self.paths:
            self._owned_path(path)
            if path in self.created_paths:
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.payload_hash)
                path.unlink()
            self.assertFalse(path.exists())
        if self.system_directory.exists():
            self.assertEqual(
                tuple(
                    path.name
                    for path in self.system_directory.iterdir()
                    if path.name.startswith(self.short_filename)
                ),
                (),
            )
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
