# SPDX-License-Identifier: LGPL-2.1-or-later
"""Record and replay commands from Python modules and packages.

The tests exercise the actual recorder, native macro playback, and Customize
export. Unique Python commands registered for compatibility controls remain
process-local; FreeCAD has no public general command-unregistration API.
"""

import ast
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import runpy
import sys
import traceback
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


# The recorder suite explicitly controls only whether its two real workbenches
# are disabled in the selector. This isolates macro assertions from the separate
# RTL temporary-disabled-tab regression. No workbench activation is retried.
_selector_fixture_state = {}


def _restore_selector_fixture():
    state = _selector_fixture_state
    if not state:
        return
    params = state["params"]
    if state["present"]:
        params.SetString("Disabled", state["value"])
    else:
        params.RemString("Disabled")
    name = state["owner"]
    if name in Gui.listWorkbenches():
        if Gui.activeWorkbench().name() == name:
            Gui.activateWorkbench(state["previous"])
        Gui.removeWorkbench(name)
    present = any(name == "Disabled" for kind, name, value in (params.GetContents() or []))
    assert present == state["present"], "Restore exact Disabled key presence"
    if present:
        assert params.GetString("Disabled") == state["value"], "Restore exact Disabled value"
    state.clear()


def setUpModule():
    if not App.GuiUp:
        return
    params = App.ParamGet("User parameter:BaseApp/Preferences/Workbenches")
    values = [value for kind, name, value in (params.GetContents() or []) if name == "Disabled"]
    owner = "RecorderSelectorFixture12604_" + uuid4().hex[:12]
    _selector_fixture_state.update(
        params=params, present=bool(values), value=values[0] if values else None,
        owner=owner, previous=Gui.activeWorkbench().name(),
    )
    unittest.addModuleCleanup(_restore_selector_fixture)
    if values:
        disabled = values[0].split(",")
        controlled = ",".join(name for name in disabled if name not in ("DraftWorkbench", "PartWorkbench"))
        params.SetString("Disabled", controlled)
        assert not set(controlled.split(",")).intersection(("DraftWorkbench", "PartWorkbench"))
    # add/removeWorkbench are public APIs that synchronously refresh selectors.
    cls = type(owner, (Gui.Workbench,), {
        "MenuText": owner, "ToolTip": owner,
        "Initialize": lambda self: None,
        "GetClassName": lambda self: "Gui::PythonWorkbench",
    })
    Gui.addWorkbench(cls())
    assert owner in Gui.listWorkbenches()


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRecordedPackageImport12604(unittest.TestCase):
    def setUp(self):
        self.initial_documents = set(App.listDocuments())
        self.previous = App.activeDocument().Name if App.activeDocument() else None
        self.previous_workbench = Gui.activeWorkbench().name()
        self.recording = False
        self.custom_commands = []
        self.directory = TemporaryDirectory(prefix="FreeCAD12604-")
        self.addCleanup(self.directory.cleanup)
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/Macro")
        contents = self.params.GetContents() or []
        self.old_macro_path = next(
            (value for kind, name, value in contents if name == "MacroPath"), None
        )
        self.addCleanup(self._restore_macro_path)
        self.addCleanup(self._cleanup_gui)
        self.params.SetString("MacroPath", self.directory.name)
        self.doc = App.newDocument("RecordedPackageImport12604")
        self.box = self.doc.addObject("Part::Box", "SourceBox")
        self.box.Length, self.box.Width, self.box.Height = 13, 7, 11
        self.doc.recompute()
        self.assertTrue(self.box.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 1001)

    def _cleanup_gui(self):
        if self.recording:
            Gui.runCommand("Std_DlgMacroRecord", 0)
            self.recording = False
        for name in self.custom_commands:
            Gui.Command.removeCustomCommand(name)
        Gui.Selection.clearSelection()
        for name in list(App.listDocuments()):
            if name not in self.initial_documents:
                App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        Gui.activateWorkbench(self.previous_workbench)

    def _restore_macro_path(self):
        if self.old_macro_path is None:
            self.params.RemString("MacroPath")
        else:
            self.params.SetString("MacroPath", self.old_macro_path)

    def _wait(self, condition, timeout=3.0):
        deadline = monotonic() + timeout
        while not condition() and monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(10, loop.quit)
            loop.exec_()
        return bool(condition())

    def _start_recording(self, name):
        state = {"started": False, "error": None}
        self.macro = Path(self.directory.name) / (name + ".FCMacro")
        self.assertFalse(self.macro.exists())

        def fill_actual_recorder():
            dialog = QtWidgets.QApplication.activeModalWidget()
            try:
                self.assertIsNotNone(dialog)
                self.assertEqual(dialog.objectName(), "Gui__Dialog__DlgMacroRecord")
                filename = dialog.findChild(QtWidgets.QLineEdit, "lineEditPath")
                folder = dialog.findChild(QtWidgets.QLineEdit, "lineEditMacroPath")
                start = dialog.findChild(QtWidgets.QPushButton, "buttonStart")
                self.assertIsNotNone(filename)
                self.assertIsNotNone(folder)
                self.assertIsNotNone(start)
                self.assertEqual(Path(folder.text()), Path(self.directory.name))
                filename.setText(name)
                self.assertTrue(start.isEnabled())
                start.click()
                state["started"] = True
            except Exception:
                state["error"] = traceback.format_exc()
                if dialog is not None:
                    dialog.reject()

        QtCore.QTimer.singleShot(0, fill_actual_recorder)
        Gui.runCommand("Std_DlgMacroRecord", 0)
        self.recording = state["started"]
        self.assertIsNone(state["error"], state["error"])
        self.assertTrue(self.recording)
        self.assertTrue(self.macro.exists())

    def _stop_recording(self):
        self.assertTrue(self.recording)
        Gui.runCommand("Std_DlgMacroRecord", 0)
        self.recording = False
        code = self.macro.read_text(encoding="utf-8")
        ast.parse(code)
        self.assertIn("# Macro Begin:", code)
        return code

    def _select_original_face(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.box.Name, "Face1")
        selected = Gui.Selection.getSelectionEx("", 0)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].Object, self.box)
        self.assertEqual(tuple(selected[0].SubElementNames), ("Face1",))
        return selected

    def _facebinders(self):
        return [obj for obj in self.doc.Objects
                if getattr(getattr(obj, "Proxy", None), "Type", None) == "Facebinder"]

    def _assert_facebinder(self, obj):
        self.doc.recompute()
        self.assertTrue(obj.Shape.isValid())
        self.assertEqual(len(obj.Shape.Faces), 1)
        self.assertAlmostEqual(obj.Shape.Area, self.box.Shape.Faces[0].Area)
        self.assertTrue(any(link[0] == self.box and tuple(link[1]) == ("Face1",)
                            for link in obj.Faces))

    def _record_facebinder(self):
        Gui.activateWorkbench("DraftWorkbench")
        self.assertIsNotNone(Gui.Command.get("Draft_Facebinder"))
        self.assertNotIn("gui_facebinders", __import__("sys").modules)
        self._select_original_face()
        before = set(obj.Name for obj in self._facebinders())
        self._start_recording("facebinder")
        Gui.runCommand("Draft_Facebinder", 0)
        self.assertTrue(self._wait(lambda: len(self._facebinders()) == len(before) + 1))
        self.assertFalse(Gui.Control.activeDialog())
        created = [obj for obj in self._facebinders() if obj.Name not in before]
        self.assertEqual(len(created), 1)
        self._assert_facebinder(created[0])
        code = self._stop_recording()
        self.assertIn("Draft.make_facebinder", code)
        return code

    def test_recorded_packaged_command_imports_resolve(self):
        code = self._record_facebinder()
        imports = [alias.name for node in ast.parse(code).body
                   if isinstance(node, ast.Import) for alias in node.names]
        self.assertIn("Draft", imports)
        for module in imports:
            with self.subTest(recorded_import=module):
                try:
                    importlib.import_module(module)
                except ImportError as error:
                    self.fail("Recorded import cannot be replayed: {}: {}".format(module, error))

    def test_recorded_packaged_command_native_playback_creates_facebinder(self):
        self._record_facebinder()
        self._select_original_face()
        before = set(obj.Name for obj in self._facebinders())
        command = Gui.Command.createCustomCommand(str(self.macro))
        self.custom_commands.append(command)
        Gui.runCommand(command, 0)
        self.assertTrue(self._wait(lambda: len(self._facebinders()) == len(before) + 1),
                        "The genuinely recorded macro must replay through the native macro command")
        created = [obj for obj in self._facebinders() if obj.Name not in before]
        self.assertEqual(len(created), 1)
        self._assert_facebinder(created[0])

    def test_native_part_command_recording_and_playback_control(self):
        Gui.activateWorkbench("PartWorkbench")
        self._start_recording("part_box")
        before = {obj.Name for obj in self.doc.Objects}
        Gui.runCommand("Part_Box", 0)
        created = [obj for obj in self.doc.Objects if obj.Name not in before]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].TypeId, "Part::Box")
        code = self._stop_recording()
        self.assertIn("Part::Box", code)
        before = {obj.Name for obj in self.doc.Objects}
        command = Gui.Command.createCustomCommand(str(self.macro))
        self.custom_commands.append(command)
        Gui.runCommand(command, 0)
        self.assertTrue(self._wait(lambda: len(self.doc.Objects) == len(before) + 1))
        created = [obj for obj in self.doc.Objects if obj.Name not in before]
        self.assertEqual(len(created), 1)
        self.doc.recompute()
        self.assertEqual(created[0].TypeId, "Part::Box")
        self.assertTrue(created[0].Shape.isValid())
        self.assertAlmostEqual(created[0].Shape.Volume, 1000)

    def test_direct_packaged_facebinder_api_control(self):
        Gui.activateWorkbench("DraftWorkbench")
        import Draft
        module = importlib.import_module("draftguitools.gui_facebinders")
        self.assertEqual(module.__name__, "draftguitools.gui_facebinders")
        self.assertNotIn("gui_facebinders", __import__("sys").modules)
        obj = Draft.make_facebinder(self._select_original_face())
        self._assert_facebinder(obj)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRecordedRegistrationCompatibility12604(unittest.TestCase):
    _cleanup_gui = TestRecordedPackageImport12604._cleanup_gui
    _restore_macro_path = TestRecordedPackageImport12604._restore_macro_path
    _wait = TestRecordedPackageImport12604._wait
    _start_recording = TestRecordedPackageImport12604._start_recording
    _stop_recording = TestRecordedPackageImport12604._stop_recording

    def setUp(self):
        TestRecordedPackageImport12604.setUp(self)
        self.token = uuid4().hex[:12]
        self.module_prefix = "recorder12604_" + self.token
        self.workbenches = []
        self.customize = None
        self.addCleanup(self._cleanup_registration)
        self.original_path = list(sys.path)
        sys.path.insert(0, self.directory.name)

    def _cleanup_registration(self):
        if self.customize is not None:
            try:
                self.customize.close()
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            except RuntimeError:
                pass
            self.customize = None
        if self.workbenches:
            Gui.activateWorkbench(self.previous_workbench)
        for name in self.workbenches:
            if name in Gui.listWorkbenches():
                Gui.removeWorkbench(name)
            App.ParamGet("User parameter:BaseApp/Workbench").RemGroup(name)
        sys.path[:] = self.original_path
        for name in list(sys.modules):
            if name == self.module_prefix or name.startswith(self.module_prefix + "."):
                del sys.modules[name]
        importlib.invalidate_caches()

    def _source(self, command, variant="standard", group=False, metadata=""):
        body = [
            "FreeCAD.ActiveDocument.addObject('App::FeaturePython', 'CompatMarker')",
            "FreeCAD.ActiveDocument.ActiveObject.addProperty('App::PropertyString', 'MarkerToken')",
            "FreeCAD.ActiveDocument.ActiveObject.MarkerToken = " + repr(self.token),
        ]
        lines = ["import FreeCAD", "import FreeCADGui as Gui", "class Command:",
                 "    def GetResources(self):",
                 "        return {'MenuText': 'Recorder compatibility', 'ToolTip': "
                 + repr(command) + ", 'CmdType': 'ForEdit'}",
                 "    def IsActive(self):", "        return True", "    def Activated(self):"]
        lines += ["        Gui.doCommand(" + repr(line) + ")" for line in body]
        if variant == "absent_module":
            lines += ["    def __getattribute__(self, name):",
                      "        if name == '__module__':",
                      "            raise AttributeError(name)",
                      "        return object.__getattribute__(self, name)"]
        lines += ["command_object = Command()"]
        if variant == "callable":
            lines += ["original_object = command_object", "def command_object(): pass",
                      "command_object.GetResources = original_object.GetResources",
                      "command_object.IsActive = original_object.IsActive",
                      "command_object.Activated = original_object.Activated"]
        if metadata:
            lines += [metadata]
        lines += ["Gui.addCommand(" + repr(command) + ", command_object)"]
        if group:
            lines += ["class Group:", "    def GetResources(self):",
                      "        return {'MenuText': 'Recorder group', 'ToolTip': 'Recorder group'}",
                      "    def GetCommands(self):", "        return (" + repr(command) + ",)",
                      "    def IsActive(self):", "        return True",
                      "Gui.addCommand(" + repr(command + "_Group") + ", Group())"]
        return "\n".join(lines) + "\n"

    def _register(self, mode, variant="standard", group=False, metadata=""):
        command = "Recorder12604_" + self.token
        source = self._source(command, variant, group, metadata)
        base = Path(self.directory.name)
        if mode in ("package", "initializer"):
            folder = base / self.module_prefix
            folder.mkdir()
            if mode == "package":
                (folder / "__init__.py").write_text("# ordinary package\n", encoding="utf-8")
                (folder / "commands.py").write_text(source, encoding="utf-8")
                module_name = self.module_prefix + ".commands"
                expected_group = "commands"
            else:
                (folder / "__init__.py").write_text(source, encoding="utf-8")
                module_name = self.module_prefix
                expected_group = "__init__"
            importlib.invalidate_caches()
            module = importlib.import_module(module_name)
            namespace = module.__dict__
        else:
            path = base / (self.module_prefix + ".py")
            path.write_text(source, encoding="utf-8")
            importlib.invalidate_caches()
            if mode == "main":
                namespace = runpy.run_path(str(path), run_name="__main__")
            else:
                namespace = importlib.import_module(self.module_prefix).__dict__
            module_name = self.module_prefix
            expected_group = self.module_prefix
        native = Gui.Command.get(command)
        self.assertIsNotNone(native)
        self.assertTrue(native.isActive())
        self.assertEqual(native.getInfo()["name"], command)
        self.assertEqual(native.getInfo()["toolTip"], command)
        return command, module_name, expected_group, namespace

    def _markers(self):
        return [obj for obj in self.doc.Objects
                if getattr(obj, "MarkerToken", None) == self.token]

    def _record_and_replay(self, command, expected_import):
        before = {obj.ID for obj in self._markers()}
        self._start_recording("compatibility")
        Gui.runCommand(command, 0)
        self.assertTrue(self._wait(lambda: len(self._markers()) == len(before) + 1))
        code = self._stop_recording()
        imports = [alias.name for node in ast.parse(code).body
                   if isinstance(node, ast.Import) for alias in node.names]
        with self.subTest(oracle="recorded_module_identity"):
            self.assertIn(expected_import, imports)
        for name in imports:
            with self.subTest(oracle="recorded_import_resolves", module=name):
                try:
                    importlib.import_module(name)
                except ImportError as error:
                    self.fail("Recorded module {} cannot import: {}".format(name, error))
        before = {obj.ID for obj in self._markers()}
        macro = Gui.Command.createCustomCommand(str(self.macro))
        self.custom_commands.append(macro)
        Gui.runCommand(macro, 0)
        with self.subTest(oracle="native_macro_replay"):
            self.assertTrue(self._wait(lambda: len(self._markers()) == len(before) + 1))
        self.assertTrue(self.box.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 1001)
        return code

    def _activate_toolbar(self, commands):
        toolbar = "RecorderToolbar12604_" + self.token

        def initialize(workbench):
            workbench.appendToolbar(toolbar, commands)

        name = "RecorderWorkbench12604_" + self.token
        cls = type(name, (Gui.Workbench,), {
            "MenuText": name, "ToolTip": name, "Initialize": initialize,
            "GetClassName": lambda workbench: "Gui::PythonWorkbench",
        })
        self.workbenches.append(name)
        Gui.addWorkbench(cls())
        self.assertTrue(Gui.activateWorkbench(name))
        self.assertTrue(self._wait(lambda: Gui.activeWorkbench().name() == name))
        bars = Gui.getMainWindow().findChildren(QtWidgets.QToolBar, toolbar)
        self.assertEqual(len(bars), 1)
        self.assertTrue(bars[0].isVisible())
        return name, bars[0]

    def _choose_combo(self, combo, index):
        self.assertGreaterEqual(index, 0)
        combo.showPopup()
        view = combo.view()
        target = combo.model().index(index, combo.modelColumn(), combo.rootModelIndex())
        view.scrollTo(target)
        QtWidgets.QApplication.processEvents()
        rectangle = view.visualRect(target)
        self.assertTrue(rectangle.isValid())
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton,
                               QtCore.Qt.NoModifier, rectangle.center())
        self.assertTrue(self._wait(lambda: combo.currentIndex() == index))

    def _customize_toolbar(self, command, expected_group, expected_module, workbench):
        Gui.runCommand("Std_DlgCustomize", 0)
        tabs = Gui.getMainWindow().findChild(QtWidgets.QTabWidget, "Gui__Dialog__TabWidget")
        self.assertIsNotNone(tabs)
        self.customize = tabs.window()
        pages = [tabs.widget(index) for index in range(tabs.count())
                 if tabs.widget(index).inherits("Gui::Dialog::DlgCustomToolbarsImp")]
        self.assertEqual(len(pages), 1)
        page = pages[0]
        tabs.setCurrentWidget(page)
        self.assertTrue(self._wait(page.isVisible))
        combo = page.findChild(QtWidgets.QComboBox, "categoryBox")
        commands = page.findChild(QtWidgets.QTreeWidget, "commandTreeWidget")
        workbenches = page.findChild(QtWidgets.QComboBox, "workbenchBox")
        toolbars = page.findChild(QtWidgets.QTreeWidget, "toolbarTreeWidget")
        create = page.findChild(QtWidgets.QPushButton, "newButton")
        add = page.findChild(QtWidgets.QPushButton, "moveActionRightButton")
        self.assertTrue(all(widget is not None for widget in
                            (combo, commands, workbenches, toolbars, create, add)))
        self.assertEqual(str(workbenches.currentData()), workbench)
        self._choose_combo(combo, combo.findData(expected_group))

        def find_command():
            for index in range(commands.topLevelItemCount()):
                item = commands.topLevelItem(index)
                value = item.data(1, QtCore.Qt.UserRole)
                if value is not None and bytes(value).decode("utf-8") == command:
                    return item
            return None

        self.assertTrue(self._wait(lambda: find_command() is not None))
        selected = find_command()
        commands.setCurrentItem(selected)
        custom_name = "RecordedCustom12604_" + self.token
        state = {"error": None}

        def fill_name():
            dialog = QtWidgets.QApplication.activeModalWidget()
            try:
                self.assertIsInstance(dialog, QtWidgets.QInputDialog)
                dialog.setTextValue(custom_name)
                dialog.accept()
            except Exception as error:
                state["error"] = repr(error)
                if dialog is not None:
                    dialog.reject()

        QtCore.QTimer.singleShot(0, fill_name)
        create.click()
        self.assertIsNone(state["error"], state["error"])
        self.assertEqual(toolbars.topLevelItemCount(), 1)
        self.assertEqual(toolbars.topLevelItem(0).text(0), custom_name)
        toolbars.setCurrentItem(toolbars.topLevelItem(0))
        commands.setCurrentItem(find_command())
        self.assertTrue(add.isEnabled())
        add.click()
        group = App.ParamGet("User parameter:BaseApp/Workbench/" + workbench + "/Toolbar/Custom_1")
        self.assertEqual(group.GetString("Name"), custom_name)
        self.assertEqual(group.GetString(command), expected_module,
                         "Real Customize toolbar export must retain an importable command module")
        self.assertEqual(toolbars.topLevelItem(0).childCount(), 1)
        self.customize.close()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.customize = None

    def test_real_package_module_registration(self):
        command, module, group, namespace = self._register("package")
        self._record_and_replay(command, module)

    def test_package_initializer_registration(self):
        command, module, group, namespace = self._register("initializer")
        self._record_and_replay(command, module)

    def test_top_level_module_registration_control(self):
        command, module, group, namespace = self._register("top_level")
        self._record_and_replay(command, module)

    def test_main_script_keeps_filename_fallback_control(self):
        command, module, group, namespace = self._register("main")
        self.assertEqual(namespace["__name__"], "__main__")
        self._record_and_replay(command, module)

    def test_command_without_module_attribute_control(self):
        command, module, group, namespace = self._register("top_level", "absent_module")
        self.assertFalse(hasattr(namespace["command_object"], "__module__"))
        self._record_and_replay(command, module)

    def test_callable_function_command_control(self):
        command, module, group, namespace = self._register("top_level", "callable")
        self.assertTrue(callable(namespace["command_object"]))
        self._record_and_replay(command, module)

    def test_missing_or_nonstring_caller_metadata_fallback_control(self):
        metadata = "globals().pop('__name__', None); globals()['__package__'] = 42"
        command, module, group, namespace = self._register("top_level", metadata=metadata)
        self.assertNotIn("__name__", namespace)
        self.assertEqual(namespace["__package__"], 42)
        self._record_and_replay(command, module)

    def test_group_toolbar_category_and_export_module(self):
        command, module, group, namespace = self._register("package", group=True)
        group_command = command + "_Group"
        workbench, toolbar = self._activate_toolbar([command, group_command])
        actions = Gui.Command.get(command).getAction()
        self.assertEqual(len(actions), 1)
        self.assertIn(actions[0], toolbar.actions())
        before = len(self._markers())
        actions[0].trigger()
        self.assertTrue(self._wait(lambda: len(self._markers()) == before + 1))
        self.assertGreaterEqual(len(Gui.Command.get(group_command).getAction()), 1)
        before = len(self._markers())
        Gui.runCommand(group_command, 0)
        self.assertTrue(self._wait(lambda: len(self._markers()) == before + 1))
        self._customize_toolbar(command, group, module, workbench)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRecordedUnicodeBoundary12604(unittest.TestCase):
    setUp = TestRecordedRegistrationCompatibility12604.setUp
    _cleanup_gui = TestRecordedRegistrationCompatibility12604._cleanup_gui
    _restore_macro_path = TestRecordedRegistrationCompatibility12604._restore_macro_path
    _wait = TestRecordedRegistrationCompatibility12604._wait
    _start_recording = TestRecordedRegistrationCompatibility12604._start_recording
    _stop_recording = TestRecordedRegistrationCompatibility12604._stop_recording
    _cleanup_registration = TestRecordedRegistrationCompatibility12604._cleanup_registration
    _source = TestRecordedRegistrationCompatibility12604._source
    _register = TestRecordedRegistrationCompatibility12604._register
    _markers = TestRecordedRegistrationCompatibility12604._markers
    _record_and_replay = TestRecordedRegistrationCompatibility12604._record_and_replay

    def test_top_level_unicode_module_recording_encoding_boundary(self):
        self.module_prefix = "команда12604_" + self.token
        command, module, group, namespace = self._register("top_level")
        self._record_and_replay(command, module)

    def test_unicode_package_prefix_recording_boundary(self):
        self.module_prefix = "пакет12604_" + self.token
        command, module, group, namespace = self._register("package")
        self._record_and_replay(command, module)


if __name__ == "__main__":
    unittest.main()
