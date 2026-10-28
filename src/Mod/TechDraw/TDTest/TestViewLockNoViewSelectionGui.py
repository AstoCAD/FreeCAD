# SPDX-License-Identifier: LGPL-2.1-or-later
"""View-lock commands preserve pending edits when no drawing view is selected.

The actual GUI command and independent public model snapshots are used. An
explicit disposable profile is required before any GUI or model mutation.
"""

import json
import os
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


COMMAND = "TechDraw_ExtensionLockUnlockView"
TEMPLATE = Path(__file__).with_name("TestTemplate.svg")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestViewLockNoViewSelectionGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        if App.listDocuments():
            self.skipTest("Requires a disposable GUI process without existing documents")
        if QtWidgets.QApplication.activeModalWidget() is not None:
            self.skipTest("Requires a GUI process without a foreign modal dialog")
        self.assertTrue(TEMPLATE.is_file())
        self.document_name = None
        self.document_uid = None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.addCleanup(self._cleanup)
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        Gui.activateWorkbench("TechDrawWorkbench")

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, message):
        deadline = time.monotonic() + 20
        while not predicate():
            require(time.monotonic() < deadline, message)
            self._pump()

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.document_name and self.document_name in App.listDocuments():
            document = App.getDocument(self.document_name)
            self.assertEqual(str(document.Uid), self.document_uid)
            if document.HasPendingTransaction:
                document.abortTransaction()
            App.closeDocument(self.document_name)
            self._pump()
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

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

    def _fixture(self, name, initially_locked=False):
        document = App.newDocument("LockAudit87" + name)
        uid = str(document.Uid)
        self.document_name = document.Name
        self.document_uid = uid
        document.UndoMode = 1
        source = document.addObject("Part::Box", "Source")
        source.Length, source.Width, source.Height = 20, 30, 10
        container = document.addObject("App::Part", "Container")
        container.Label = "Stable container"
        page = document.addObject("TechDraw::DrawPage", "Page")
        template = document.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        page.Template = template
        view = document.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [source]
        view.Direction = App.Vector(0, 0, 1)
        view.XDirection = App.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.LockPosition = initially_locked
        document.recompute()
        self._wait(lambda: "Up-to-date" in view.State and len(view.getVisibleEdges()) >= 4,
             "The ordinary box projection did not produce its visible geometry")
        self._wait(view.isProjectionReady, "The ordinary projection is not complete")
        require(source.Shape.isValid() and source.Shape.Volume == 6000,
                "Ordinary box fixture geometry differs")
        require(len(view.getVisibleEdges()) >= 4, "The projected fixture has too few edges")
        require(list(page.Views) == [view], "The page must contain exactly its real view")
        App.setActiveDocument(document.Name)
        page.ViewObject.show()
        self._pump()
        document.clearUndos()
        require(not document.HasPendingTransaction and document.UndoNames == []
                and document.RedoNames == [], "Fixture history must already be empty")
        return {"doc": document, "uid": uid, "source": source, "container": container,
                "page": page, "view": view}

    def _select(self, fx, objects):
        Gui.Selection.clearSelection()
        for obj in objects:
            Gui.Selection.addSelection(fx["doc"].Name, obj.Name)
        selected = Gui.Selection.getSelectionEx()
        actual = sorted((item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
                        for item in selected)
        expected = sorted((fx["doc"].Name, obj.Name, ()) for obj in objects)
        require(actual == expected, "Actual GUI selection differs from the admitted objects")
        return actual

    def _model(self, fx):
        document, source, view = fx["doc"], fx["source"], fx["view"]
        return {
            "objects": [(obj.Name, obj.TypeId) for obj in document.Objects],
            "page_views": [obj.Name for obj in fx["page"].Views],
            "container_label": fx["container"].Label,
            "source_label": source.Label,
            "source_dimensions": [source.Length.Value, source.Width.Value, source.Height.Value],
            "source_volume": source.Shape.Volume,
            "view_source": [obj.Name for obj in view.Source],
            "lock": bool(view.LockPosition),
            "visible_lengths": sorted(edge.Length for edge in view.getVisibleEdges()),
            "hidden_lengths": sorted(edge.Length for edge in view.getHiddenEdges()),
        }

    def _snapshot(self, fx):
        document = fx["doc"]
        return {"model": self._model(fx), "pending": bool(document.HasPendingTransaction),
                "booked": document.getBookedTransactionID(),
                "undo": list(document.UndoNames), "redo": list(document.RedoNames)}

    def _invoke(self, fx):
        require(App.ActiveDocument.Name == fx["doc"].Name, "Fixture is not active")
        command = Gui.Command.get(COMMAND)
        require(command is not None and command.isActive(),
                "The ordinary Toggle View Lock GUI action must be enabled")
        Gui.runCommand(COMMAND)
        self._pump()
        fx["doc"].recompute()
        self._wait(fx["view"].isProjectionReady, "Projection did not settle after the ordinary action")
        require(QtWidgets.QApplication.activeModalWidget() is None,
                "Ordinary view-lock selections must not leave a modal dialog")

    def _toggle_control(self, kind, mixed, initially_locked):
        fx = self._fixture(kind, initially_locked)
        self._select(fx, [fx["page"], fx["view"]] if mixed else [fx["view"]])
        before = self._snapshot(fx)
        self._invoke(fx)
        after = self._snapshot(fx)
        expected = json.loads(json.dumps(before["model"]))
        normalized = json.loads(json.dumps(after["model"]))
        expected["lock"] = not initially_locked
        self.assertEqual(normalized, expected)
        self.assertFalse(after["pending"])
        self.assertEqual(after["redo"], [])
        self.assertEqual(after["undo"], ["Lock/Unlock View"])
        fx["doc"].undo()
        fx["doc"].recompute()
        self._wait(fx["view"].isProjectionReady, "Undo projection did not settle")
        undone = self._snapshot(fx)
        self.assertEqual(undone["model"], before["model"])
        self.assertFalse(undone["pending"])
        self.assertEqual(undone["undo"], [])
        self.assertEqual(undone["redo"], ["Lock/Unlock View"])
        fx["doc"].redo()
        fx["doc"].recompute()
        self._wait(fx["view"].isProjectionReady, "Redo projection did not settle")
        redone = self._snapshot(fx)
        self.assertEqual(redone["model"], after["model"])
        self.assertFalse(redone["pending"])
        self.assertEqual(redone["undo"], ["Lock/Unlock View"])
        self.assertEqual(redone["redo"], [])

    def _preserve_pending(self, kind, selected_kind):
        fx = self._fixture(kind)
        choices = {"empty": [], "page": [fx["page"]], "part": [fx["container"]]}
        self._select(fx, choices[selected_kind])
        pristine = self._snapshot(fx)
        original_label = fx["container"].Label
        fx["doc"].openTransaction("Unrelated pending edit")
        fx["container"].Label = "Uncommitted container label"
        self.assertTrue(fx["doc"].HasPendingTransaction)
        self.assertEqual(fx["doc"].UndoNames, ["Unrelated pending edit"])
        self.assertEqual(fx["doc"].RedoNames, [])
        before = self._snapshot(fx)
        self._invoke(fx)
        after = self._snapshot(fx)
        for key in before:
            with self.subTest(preserved=key):
                self.assertEqual(after[key], before[key])
        fx["doc"].abortTransaction()
        self._pump()
        aborted = self._snapshot(fx)
        with self.subTest(oracle="abort_restored_label"):
            self.assertEqual(fx["container"].Label, original_label)
        with self.subTest(oracle="abort_restored_model"):
            self.assertEqual(aborted["model"], pristine["model"])
        with self.subTest(oracle="abort_history_match"):
            self.assertEqual((aborted["undo"], aborted["redo"]),
                             (pristine["undo"], pristine["redo"]))
        with self.subTest(oracle="abort_no_pending"):
            self.assertFalse(aborted["pending"])

    def test_control_single_view_toggle_undo_redo(self):
        self._toggle_control("SingleView", False, False)

    def test_control_mixed_page_view_toggle_undo_redo(self):
        self._toggle_control("MixedPageView", True, True)

    def test_control_empty_selection_preserves_pending_edit(self):
        self._preserve_pending("EmptySelection", "empty")

    def test_page_only_selection_preserves_pending_edit(self):
        self._preserve_pending("PageOnly", "page")

    def test_part_only_selection_preserves_pending_edit(self):
        self._preserve_pending("PartOnly", "part")
