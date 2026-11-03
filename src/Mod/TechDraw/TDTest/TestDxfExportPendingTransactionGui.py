# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regression tests for pending edits during DXF export.

The real save dialog writes only to an explicitly selected disposable profile.
Normal GUI sessions skip these profile-dependent tests.
"""

import math
import os
from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import TechDraw
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "DXF export GUI diagnostic")
class TestDxfExportPendingTransactionGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        self.doc = None
        self.temporary = None
        self.dialog_settings = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        previous_workbench = Gui.activeWorkbench()
        self.previous_workbench = previous_workbench.name() if previous_workbench else None
        self.previous_selection = [
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        ]
        self.addCleanup(self._cleanup)
        self.temporary = tempfile.TemporaryDirectory(prefix="dxf-export-", dir=self.profile)
        self.directory = Path(self.temporary.name).resolve()
        self.assertTrue(self.directory.is_relative_to(self.profile))
        self.assertTrue(str(self.directory).isascii())
        self.dialog_settings = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        self.previous_native = self._parameter(
            self.dialog_settings, "Boolean", "DontUseNativeDialog"
        )
        self.general_settings = App.ParamGet("User parameter:BaseApp/Preferences/General")
        self.previous_save_path = self._parameter(
            self.general_settings, "String", "FileOpenSavePath"
        )
        self.dialog_settings.SetBool("DontUseNativeDialog", True)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.window = Gui.getMainWindow()
        self.app = QtWidgets.QApplication.instance()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(self.app.activeModalWidget())
        self.doc = App.newDocument("DxfExportTransaction")
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        fixture = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(fixture.is_file())
        template.Template = str(fixture)
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.X, self.view.Y = 60, 80
        self.doc.recompute()
        self.assertTrue(
            self._wait(
                lambda: self.view.isProjectionReady() and len(self.view.getVisibleEdges()) >= 4
            )
        )
        self.assertGreater(self.view.getEdgeBySelection("Edge0").Length, 0)
        self.annotation = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        self.annotation.Text = ["DXF export control"]
        self.annotation.X, self.annotation.Y = 100, 40
        self.page.addView(self.annotation)
        self.dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.dimension.Type = "Distance"
        self.dimension.MeasureType = "Projected"
        self.dimension.References2D = [(self.view, "Edge0")]
        self.dimension.X, self.dimension.Y = 0, -30
        self.page.addView(self.dimension)
        self.doc.recompute()
        self.assertTrue(
            self._wait(
                lambda: self.view.isProjectionReady() and "Up-to-date" in self.dimension.State
            )
        )
        self.assertGreater(self.dimension.getRawValue(), 0)
        self.page.ViewObject.show()
        self._pump()
        self.doc.recompute()
        self.assertTrue(self._wait(self.view.isProjectionReady))
        self.doc.clearUndos()
        Gui.getDocument(self.doc.Name).Modified = False
        Gui.Selection.addSelection(self.doc.Name, self.page.Name)
        self.command = Gui.Command.get("TechDraw_ExportPageDXF")
        self.assertIsNotNone(self.command)
        self.assertTrue(self.command.isActive())
        actions = self.command.getAction()
        self.assertEqual(len(actions), 1)
        self.action = actions[0]
        self.assertTrue(self._wait(self.action.isEnabled))
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(Gui.getDocument(self.doc.Name).Modified)
        self.assertEqual(self._selection(), ((self.doc.Name, self.page.Name, ()),))

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
        paths = (parameter_file, data_directory)
        if not all(path.is_absolute() and plain_path(path) for path in paths):
            self.skipTest("Active profile paths must be absolute and free of links")
        if parameter_file.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside the selected test profile")
        if not all(path.resolve().is_relative_to(profile) for path in paths):
            self.skipTest("Active user configuration and data must stay in the test profile")
        return profile

    @staticmethod
    def _parameter(group, kind, name):
        found = [
            value
            for entry_kind, key, value in group.GetContents() or []
            if entry_kind == kind and key == name
        ]
        assert len(found) <= 1
        return bool(found), found[0] if found else None

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    @staticmethod
    def _selection():
        return tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        )

    def _model(self):
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "labels": tuple((obj.Name, obj.Label) for obj in self.doc.Objects),
            "page_views": tuple(obj.Name for obj in self.page.Views),
            "source_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "source_volume": self.source.Shape.Volume,
            "view_source": tuple(obj.Name for obj in self.view.Source),
            "view_position_scale": (self.view.X.Value, self.view.Y.Value, self.view.Scale),
            "edge_lengths": tuple(edge.Length for edge in self.view.getVisibleEdges()),
            "annotation": (
                tuple(self.annotation.Text),
                self.annotation.X.Value,
                self.annotation.Y.Value,
            ),
            "dimension": (
                self.dimension.Type,
                self.dimension.MeasureType,
                self.dimension.getRawValue(),
                self.dimension.X.Value,
                self.dimension.Y.Value,
            ),
        }

    def _snapshot(self):
        return {
            "model": self._model(),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "touched": self.doc.isTouched(),
            "modified": Gui.getDocument(self.doc.Name).Modified,
            "selection": self._selection(),
        }

    def _path(self, basename):
        path = self.directory / basename
        self.assertEqual(path.parent, self.directory)
        self.assertTrue(str(path).isascii())
        self.assertEqual(path.suffix, ".dxf")
        self.assertFalse(path.exists())
        return path

    def _file_valid(self, path):
        self.assertTrue(path.is_file())
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines) % 2, 0)
        pairs = [(int(code.strip()), value.strip()) for code, value in zip(lines[::2], lines[1::2])]
        self.assertEqual(pairs[-1], (0, "EOF"))
        entities = []
        in_entities = False
        current = None
        for code, value in pairs:
            if code == 2 and value == "ENTITIES":
                in_entities = True
                continue
            if in_entities and code == 0 and value == "ENDSEC":
                in_entities = False
            if not in_entities:
                continue
            if code == 0:
                current = (value, [])
                entities.append(current)
            elif current is not None:
                current[1].append((code, value))
        line_entities = [data for kind, data in entities if kind == "LINE"]
        self.assertGreaterEqual(len(line_entities), 4)
        for data in line_entities:
            values = dict(data)
            coords = [float(values[code]) for code in (10, 20, 30, 11, 21, 31)]
            self.assertTrue(all(math.isfinite(value) for value in coords))
        texts = [
            value for kind, data in entities if kind == "TEXT" for code, value in data if code == 1
        ]
        self.assertIn("DXF export control", texts)
        self.assertEqual(sum(kind == "DIMENSION" for kind, _data in entities), 1)
        return pairs

    def _observe(self, operation):
        events = []
        document = self.doc.Name

        class ModelObserver:
            def slotChangedObject(self, obj, prop):
                if obj.Document.Name == document:
                    events.append(("changed", obj.Name, prop))

            def slotCreatedObject(self, obj):
                if obj.Document.Name == document:
                    events.append(("created", obj.Name))

            def slotDeletedObject(self, obj):
                if obj.Document.Name == document:
                    events.append(("deleted", obj.Name))

        observer = ModelObserver()
        App.addDocumentObserver(observer)
        try:
            operation()
            self._pump()
        finally:
            App.removeDocumentObserver(observer)
        self.assertEqual(
            events, [], "A normal DXF export must not change any model property or object"
        )

    def _toolbar(self, path, cancel=False):
        self.assertTrue(self.command.isActive())
        self.assertTrue(self.action.isEnabled())
        self.assertIsNone(self.app.activeModalWidget())
        seen, errors, unexpected = [], [], []
        expired = []
        testcase = self

        class Messages(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.Show and isinstance(
                    watched, QtWidgets.QMessageBox
                ):
                    unexpected.append((watched.windowTitle(), watched.text()))
                    QtCore.QTimer.singleShot(0, watched.reject)
                return False

        def handle_picker():
            modal = self.app.activeModalWidget()
            if not isinstance(modal, QtWidgets.QFileDialog):
                return
            poll.stop()
            try:
                self.assertTrue(modal.isVisible())
                self.assertTrue(modal.isModal())
                self.assertEqual(modal.acceptMode(), QtWidgets.QFileDialog.AcceptSave)
                self.assertTrue(modal.testOption(QtWidgets.QFileDialog.DontUseNativeDialog))
                self.assertTrue(any("*.dxf" in name.lower() for name in modal.nameFilters()))
                seen.append(modal.windowTitle())
                if cancel:
                    modal.reject()
                else:
                    modal.selectFile(str(path))
                    self.assertEqual(
                        [Path(value).resolve() for value in modal.selectedFiles()], [path]
                    )
                    modal.accept()
            except Exception as error:
                errors.append(type(error).__name__ + ": " + str(error))
                modal.reject()

        def timeout():
            expired.append(True)
            modal = self.app.activeModalWidget()
            if isinstance(modal, QtWidgets.QDialog):
                modal.reject()

        observer = Messages()
        poll = QtCore.QTimer()
        poll.timeout.connect(handle_picker)
        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(timeout)
        self.app.installEventFilter(observer)
        poll.start(20)
        watchdog.start(10000)
        try:
            self.action.trigger()
        finally:
            poll.stop()
            watchdog.stop()
            self.app.removeEventFilter(observer)
        self._pump()
        self.assertEqual(len(seen), 1, "Exactly one actual save dialog must be observed")
        self.assertEqual(errors, [])
        self.assertEqual(unexpected, [])
        self.assertEqual(expired, [])
        self.assertIsNone(self.app.activeModalWidget())
        if cancel:
            self.assertFalse(path.exists())
        else:
            self._file_valid(path)

    def _pending(self):
        original = self.source.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.source.Label = "Uncommitted source label"
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Unrelated pending edit"])
        return original

    def _pending_export(self, basename, export_page, *, cancel=False):
        path = self._path(basename)
        original = self._pending()
        before = self._snapshot()
        self._observe(lambda: export_page(path))
        if not cancel:
            self._file_valid(path)
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])
        self.doc.abortTransaction()
        with self.subTest(oracle="unrelated_edit_remains_abortable"):
            self.assertEqual(self.source.Label, original)
        with self.subTest(oracle="abort_leaves_no_undo_record"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_direct_api_export_valid_file_control(self):
        path = self._path("direct-control.dxf")
        before = self._snapshot()
        self._observe(lambda: TechDraw.writeDXFPage(self.page, str(path)))
        self._file_valid(path)
        self.assertEqual(self._snapshot(), before)

    def test_toolbar_export_valid_file_control(self):
        path = self._path("toolbar-control.dxf")
        before = self._snapshot()
        self._observe(lambda: self._toolbar(path))
        self.assertEqual(self._snapshot(), before)

    def test_toolbar_cancel_preserves_pending_edit_control(self):
        self._pending_export(
            "cancel-control.dxf", lambda path: self._toolbar(path, cancel=True), cancel=True
        )

    def test_direct_api_export_preserves_pending_edit_control(self):
        self._pending_export(
            "api-pending-control.dxf", lambda path: TechDraw.writeDXFPage(self.page, str(path))
        )

    def test_toolbar_export_preserves_pending_edit_target(self):
        self._pending_export("toolbar-pending-target.dxf", self._toolbar)

    def test_gui_api_export_preserves_pending_edit_target(self):
        import TechDrawGui

        self.assertEqual(App.ActiveDocument.Name, self.page.Document.Name)
        self._pending_export(
            "gui-api-pending-target.dxf", lambda path: TechDrawGui.export([self.page], str(path))
        )

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc.Name)
            self._pump()
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, obj, names in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(obj):
                for name in names or ("",):
                    Gui.Selection.addSelection(document, obj, name)
        if self.dialog_settings is not None:
            present, value = self.previous_native
            if present:
                self.dialog_settings.SetBool("DontUseNativeDialog", value)
            else:
                self.dialog_settings.RemBool("DontUseNativeDialog")
            present, value = self.previous_save_path
            if present:
                self.general_settings.SetString("FileOpenSavePath", value)
            else:
                self.general_settings.RemString("FileOpenSavePath")
        if self.temporary is not None:
            self.temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
