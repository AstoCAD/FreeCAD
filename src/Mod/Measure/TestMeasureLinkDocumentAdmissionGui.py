# SPDX-License-Identifier: LGPL-2.1-or-later
"""Ordinary command admission and geometry controls for loaded linked objects."""

import os
from pathlib import Path
import shutil
import tempfile
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import MeasureGui  # noqa: F401
    import Part
    from PySide import QtCore

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest

    try:
        import Sketcher
        import SketcherGui  # noqa: F401
    except ModuleNotFoundError as error:
        if error.name not in {"Sketcher", "SketcherGui"}:
            raise
        Sketcher = None
else:
    Sketcher = None


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestMeasureLinkDocumentAdmissionGui(unittest.TestCase):
    def setUp(self):
        self.assertIsNone(Gui.Control.activeTaskDialog(), "Requires no existing task")
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = []
        for item in Gui.Selection.getSelectionEx("*", 0):
            for index, subname in enumerate(list(item.SubElementNames) or [""]):
                points = list(item.PickedPoints)
                point = points[index] if index < len(points) else App.Vector()
                self.previous_selection.append(
                    (
                        item.Object.Document.Name,
                        item.Object.Name,
                        subname,
                        point.x,
                        point.y,
                        point.z,
                    )
                )
        self.documents = []
        self.temporary_directory = None
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Measure/TaskMeasure")
        contents = self.settings.GetContents() or []
        self.preferences = {
            key: (
                any(kind == "Boolean" and name == key for kind, name, _value in contents),
                self.settings.GetBool(key, False),
            )
            for key in ("AutoSave", "GreedySelection")
        }
        self.addCleanup(self._cleanup)
        self._owned_temporary_directory()
        self.settings.SetBool("AutoSave", False)
        self.settings.SetBool("GreedySelection", False)
        Gui.Selection.clearSelection()
        Gui.activateWorkbench("PartWorkbench")
        self.command = Gui.Command.get("Std_Measure")
        self.assertIsNotNone(self.command)
        actions = self.command.getAction()
        self.assertEqual(len(actions), 1)
        self.action = actions[0]

        self.source = self._new_document("MeasureAdmissionSource")
        self.source_box = self._box(self.source, "SourceBox")
        self.plain_group = self.source.addObject("App::DocumentObjectGroup", "PlainGroup")
        self.source.recompute()
        source_file = self.temporary_directory / "MeasureSource.FCStd"
        self.assertFalse(source_file.exists())
        self.source.saveAs(str(source_file))
        self.assertTrue(source_file.is_file())
        self.assertEqual(Path(self.source.FileName).resolve(), source_file)
        self.source_names = tuple(obj.Name for obj in self.source.Objects)
        self.source_volume = self.source_box.Shape.Volume
        self.doc = self._new_document("MeasureAdmissionTarget")
        owner_file = self.temporary_directory / "MeasureOwner.FCStd"
        self.assertFalse(owner_file.exists())
        self.doc.saveAs(str(owner_file))
        self.assertTrue(owner_file.is_file())
        self.assertEqual(Path(self.doc.FileName).resolve(), owner_file)
        self._activate(self.doc)

    def _owned_temporary_directory(self):
        parent = Path(tempfile.gettempdir()).resolve()
        profile = parent
        if os.environ.get("ASTO_AUDIT_CASE") or os.environ.get("ASTO_AUDIT_LABEL"):
            label = os.environ.get("ASTO_AUDIT_LABEL", "")
            self.assertTrue(label)
            self.assertNotIn("/", label)
            self.assertNotIn("\\", label)
            profile = Path(os.environ["FREECAD_USER_HOME"]).resolve()
            output = profile.parent
            self.assertEqual(profile.name, label + "-profile")
            self.assertEqual(output.name, "issue-audit-20261019")
            self.assertEqual(output.parent.name, ".codex-test-bin")
            workspace = output.parent.parent
            self.assertTrue((workspace / ".git").exists())
            self.assertTrue(Path(__file__).resolve().is_relative_to(workspace))
            self.assertEqual(
                Path(os.environ["ASTO_AUDIT_SOURCE"]).resolve(), Path(__file__).resolve()
            )
            self.assertTrue(profile.is_dir())
            self.assertEqual(Path(App.ConfigGet("UserParameter")).resolve(), profile / "user.cfg")
            self.assertTrue(Path(App.getUserAppDataDir()).resolve().is_relative_to(profile))
            parent = (profile / "temp").resolve()
            self.assertEqual(Path(os.environ["TEMP"]).resolve(), parent)
        self.audit_profile = profile
        self.profile_temporary = parent
        self.assertTrue(parent.is_dir())
        self.assertTrue(parent.is_relative_to(profile))
        self.temporary_directory = Path(
            tempfile.mkdtemp(prefix="measure-link-source-", dir=parent)
        ).resolve()
        self.assertEqual(self.temporary_directory.parent, parent)
        self.assertTrue(self.temporary_directory.is_relative_to(profile))

    def _pump(self):
        Gui.updateGui()
        QtTest.QTest.qWait(40)
        Gui.updateGui()

    def _wait(self, predicate, message):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while not predicate() and timer.elapsed() < 3000:
            self._pump()
        self.assertTrue(predicate(), message)

    def _new_document(self, name):
        doc = App.newDocument(name)
        self.documents.append(doc)
        return doc

    def _box(self, doc, name):
        box = doc.addObject("Part::Box", name)
        box.Length, box.Width, box.Height = 3, 5, 7
        doc.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertAlmostEqual(box.Shape.Volume, 105, places=9)
        self.assertEqual(len(box.Shape.Edges), 12)
        return box

    def _activate(self, doc):
        App.setActiveDocument(doc.Name)
        self._pump()
        self.assertEqual(App.ActiveDocument.Name, doc.Name)
        gui = Gui.getDocument(doc.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, doc.Name)
        self.assertEqual(gui.activeView().getTypeId(), "Gui::View3DInventor")
        self.assertIsNone(gui.getInEdit())

    def _link(self, source):
        link = self.doc.addObject("App::Link", "Occurrence")
        link.setLink(source)
        self.doc.recompute()
        self.assertEqual(link.LinkedObject, source)
        self.assertEqual(link.TypeId, "App::Link")
        self.assertFalse(link.isDerivedFrom("App::GeoFeature"))
        return link

    def _assert_command(self, active):
        self.assertEqual(self.command.isActive(), active)
        self._wait(
            lambda: self.action.isEnabled() == active,
            "Native command action did not reflect ordinary active-document admission",
        )

    @staticmethod
    def _measurements(doc):
        return [obj for obj in doc.Objects if obj.isDerivedFrom("Measure::MeasureBase")]

    def _measure_edge(self, selected):
        self._activate(self.doc)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, selected.Name, "Edge1")
        self._pump()
        selection = Gui.Selection.getSelectionEx(self.doc.Name, 0)
        self.assertEqual(len(selection), 1)
        self.assertEqual(selection[0].Object, selected)
        self.assertEqual(tuple(selection[0].SubElementNames), ("Edge1",))
        self.assertEqual(len(selection[0].SubObjects), 1)
        edge = selection[0].SubObjects[0]
        self.assertEqual(edge.ShapeType, "Edge")
        self.assertGreater(edge.Length, 0)
        expected_length = edge.Length
        self.assertAlmostEqual(expected_length, self.source_box.Shape.Edges[0].Length, places=9)
        before = tuple(obj.Name for obj in self.doc.Objects)

        self._assert_command(True)
        self.action.trigger()
        self._wait(
            lambda: Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name)) is not None,
            "Enabled Measure command did not open an owned native task",
        )
        task = Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name))
        self.assertEqual(task.getDocumentName(), self.doc.Name)
        self._wait(
            lambda: len(self._measurements(self.doc)) == 1,
            "Ordinary edge selection did not produce one measurement preview",
        )
        measure = self._measurements(self.doc)[0]
        self.assertEqual(measure.TypeId, "Measure::MeasureLength")
        self.assertAlmostEqual(measure.Length.Value, expected_length, places=9)
        self.assertEqual(len(measure.Elements), 1)
        self.assertEqual(measure.Elements[0][0], selected)
        self.assertEqual(tuple(measure.Elements[0][1]), ("Edge1",))
        self.assertEqual(self._measurements(self.source), [])
        self.assertEqual(tuple(obj.Name for obj in self.source.Objects), self.source_names)
        self.assertEqual(self.source_box.Shape.Volume, self.source_volume)
        task.reject()
        self._pump()
        self.assertIsNone(Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name)))
        self.assertEqual(self._measurements(self.doc), [])
        self.assertEqual(tuple(obj.Name for obj in self.doc.Objects), before)

    def test_empty_active_document_remains_inactive_control(self):
        self.assertEqual(self.doc.Objects, [])
        self._assert_command(False)

    def test_non_geometric_link_document_remains_inactive_control(self):
        self._link(self.plain_group)
        self.assertEqual(len(self.doc.Objects), 1)
        self.assertFalse(any(obj.isDerivedFrom("App::GeoFeature") for obj in self.doc.Objects))
        self._assert_command(False)

    def test_normal_part_solid_is_admitted_and_measured_control(self):
        box = self._box(self.doc, "LocalBox")
        self.assertTrue(box.isDerivedFrom("App::GeoFeature"))
        self._measure_edge(box)

    def test_link_selection_is_measured_in_mixed_document_control(self):
        link = self._link(self.source_box)
        sentinel = self._box(self.doc, "HiddenAdmissionSolid")
        sentinel.Visibility = False
        self.assertFalse(sentinel.Visibility)
        self.assertEqual(len(self.doc.Objects), 2)
        self._measure_edge(link)
        self.assertFalse(sentinel.Visibility)
        self.assertAlmostEqual(sentinel.Shape.Volume, 105, places=9)

    def test_valid_geometric_link_only_document_is_admitted(self):
        link = self._link(self.source_box)
        self.assertEqual(len(self.doc.Objects), 1)
        self.assertFalse(any(obj.isDerivedFrom("App::GeoFeature") for obj in self.doc.Objects))
        self._measure_edge(link)

    @unittest.skipIf(Sketcher is None, "Requires the Sketcher module")
    def test_active_sketch_edit_remains_inactive_control(self):
        sketch = self.doc.addObject("Sketcher::SketchObject", "AdmissionSketch")
        sketch.addGeometry(Part.LineSegment(App.Vector(), App.Vector(3, 0, 0)), False)
        self.doc.recompute()
        self._assert_command(True)
        gui = Gui.getDocument(self.doc.Name)
        self.assertTrue(gui.setEdit(sketch.Name))
        self._pump()
        self.assertIsNotNone(gui.getInEdit())
        self._assert_command(False)
        gui.resetEdit()
        self._pump()
        task = Gui.Control.activeTaskDialog(gui)
        if task is not None:
            task.reject()
            self._pump()
        self.assertIsNone(gui.getInEdit())
        self.assertIsNone(Gui.Control.activeTaskDialog(gui))
        self.assertEqual(sketch.GeometryCount, 1)
        self._assert_command(True)

    def _cleanup(self):
        owned_document_names = tuple(doc.Name for doc in self.documents)
        Gui.Selection.clearSelection()
        for doc in reversed(self.documents):
            if doc.Name not in App.listDocuments():
                continue
            App.setActiveDocument(doc.Name)
            gui = Gui.getDocument(doc.Name)
            if gui.getInEdit():
                gui.resetEdit()
                self._pump()
            task = Gui.Control.activeTaskDialog(gui)
            if task is not None:
                task.reject()
                self._pump()
            self.assertIsNone(gui.getInEdit())
            self.assertIsNone(Gui.Control.activeTaskDialog(gui))
            App.closeDocument(doc.Name)
            self._pump()
        if self.temporary_directory is not None:
            self.assertTrue(all(name not in App.listDocuments() for name in owned_document_names))
            target = self.temporary_directory.resolve()
            self.assertEqual(target.parent, self.profile_temporary)
            self.assertTrue(target.is_relative_to(self.audit_profile))
            self.assertTrue(target.name.startswith("measure-link-source-"))
            shutil.rmtree(target)
            self.assertFalse(target.exists())
        for key, (present, value) in self.preferences.items():
            if present:
                self.settings.SetBool(key, value)
            else:
                self.settings.RemBool(key)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        elif self.previous_document is None:
            App.setActiveDocument("")
        for args in self.previous_selection:
            doc_name, name = args[:2]
            if doc_name in App.listDocuments() and App.getDocument(doc_name).getObject(name):
                Gui.Selection.addSelection(*args)
        self._pump()
