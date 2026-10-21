# SPDX-License-Identifier: LGPL-2.1-or-later
"""Constraint activation keeps unrelated transactions when geometry is selected."""

import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import Sketcher
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestToggleActiveSelectionTransactionGui(unittest.TestCase):
    command_name = "Sketcher_ToggleActiveConstraint"

    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (entry.DocumentName, entry.ObjectName, tuple(entry.SubElementNames))
            for entry in Gui.Selection.getSelectionEx()
        ]
        self.doc_name = None
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog())
        Gui.activateWorkbench("SketcherWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("ActiveConstraintSelection_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.gui_doc = Gui.getDocument(self.doc_name)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(
            [
                Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
                Part.LineSegment(App.Vector(20, 5, 0), App.Vector(28, 5, 0)),
            ],
            False,
        )
        self.sketch.addConstraint(
            [Sketcher.Constraint("Horizontal", 0), Sketcher.Constraint("Horizontal", 1)]
        )
        self.box = self.doc.addObject("Part::Box", "UnrelatedBox")
        self.box.Length, self.box.Width, self.box.Height = 2, 3, 4
        self.doc.recompute()
        self.assertEqual(self.sketch.GeometryCount, 2)
        self.assertEqual(self.sketch.ConstraintCount, 2)
        self.assertEqual(tuple(c.IsActive for c in self.sketch.Constraints), (True, True))
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertAlmostEqual(self.sketch.Shape.Length, 18)
        self.assertAlmostEqual(self.box.Shape.Volume, 24)
        self.assertEqual(self.doc.FileName, "")
        self.assertTrue(self.gui_doc.setEdit(self.sketch.Name))
        self._pump()
        self.assertEqual(self.gui_doc.getInEdit().Object, self.sketch)
        self.doc.recompute()
        self.doc.commitTransaction()
        self.doc.clearUndos()
        self.assertFalse(self.doc.HasPendingTransaction)

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            task = Gui.Control.activeTaskDialog(self.gui_doc)
            if task:
                task.reject()
                self._pump()
            if self.gui_doc.getInEdit():
                self.gui_doc.resetEdit()
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, name, subnames in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(name):
                if subnames:
                    for subname in subnames:
                        Gui.Selection.addSelection(document, name, subname)
                else:
                    Gui.Selection.addSelection(document, name)

    def _select(self, *subnames):
        Gui.Selection.clearSelection()
        for subname in subnames:
            Gui.Selection.addSelection(self.doc_name, self.sketch.Name, subname)
        entries = Gui.Selection.getSelectionEx()
        if not subnames:
            self.assertEqual(entries, [])
            return
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].Object, self.sketch)
        self.assertEqual(tuple(entries[0].SubElementNames), subnames)
        if "Vertex1" in subnames:
            self.assertEqual(self.sketch.getGeoVertexIndex(0), (0, 1))
            self.assertLess((self.sketch.getPoint(0, 1) - App.Vector(0, 0, 0)).Length, 1e-9)
        if "Edge1" in subnames:
            self.assertIsInstance(self.sketch.Geometry[0], Part.LineSegment)
            self.assertLess((self.sketch.Geometry[0].StartPoint - App.Vector(0, 0, 0)).Length, 1e-9)
            self.assertLess((self.sketch.Geometry[0].EndPoint - App.Vector(10, 0, 0)).Length, 1e-9)

    @staticmethod
    def _vector(value):
        return (value.x, value.y, value.z)

    def _model(self):
        shape = self.sketch.Shape
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "geometry_count": self.sketch.GeometryCount,
            "constraint_count": self.sketch.ConstraintCount,
            "construction": tuple(
                self.sketch.getConstruction(index) for index in range(self.sketch.GeometryCount)
            ),
            "lines": tuple(
                (self._vector(geometry.StartPoint), self._vector(geometry.EndPoint))
                for geometry in self.sketch.Geometry
            ),
            "constraints": tuple(
                (
                    c.Type,
                    c.First,
                    c.FirstPos,
                    c.Second,
                    c.SecondPos,
                    c.Third,
                    c.ThirdPos,
                    c.Value,
                    c.IsActive,
                    c.Driving,
                )
                for c in self.sketch.Constraints
            ),
            "shape": (shape.isNull(), shape.isValid(), shape.Length, len(shape.Edges)),
            "box_volume": self.box.Shape.Volume,
        }

    def _run(self, name, expected_active=True):
        command = Gui.Command.get(name)
        self.assertIsNotNone(command)
        self.assertEqual(command.isActive(), expected_active)
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports)
        previous = [widget.toPlainText() for widget in reports]
        Gui.runCommand(name)
        self._pump()
        for widget, old in zip(reports, previous):
            current = widget.toPlainText()
            delta = current[len(old) :] if current.startswith(old) else current
            for marker in ("traceback", "access violation", "<exception>"):
                self.assertNotIn(marker, delta.lower())

    def _pending(self, subnames, command, expected_active=True):
        self._select(*subnames)
        self.doc.recompute()
        original_label = self.box.Label
        self.doc.openTransaction("Unrelated pending box label")
        self.box.Label = "Pending box label"
        self.assertTrue(self.doc.HasPendingTransaction)
        before = {
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "model": self._model(),
        }
        self.assertNotEqual(before["booked"], 0)
        self._run(command, expected_active)
        self.doc.recompute()
        after = {
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "model": self._model(),
        }
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])
        if command == self.command_name and subnames:
            self.assertEqual(Gui.Selection.getSelectionEx(), [])
        self.doc.abortTransaction()
        with self.subTest(oracle="unrelated_label_still_abortable"):
            self.assertEqual(self.box.Label, original_label)
        with self.subTest(oracle="unrelated_label_not_committed"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_selected_edge_preserves_pending_edit(self):
        self._pending(("Edge1",), self.command_name)

    def test_selected_vertex_preserves_pending_edit(self):
        self._pending(("Vertex1",), self.command_name)

    def test_fit_all_with_edge_preserves_pending_edit_control(self):
        self._pending(("Edge1",), "Std_ViewFitAll")

    def test_no_selection_remains_inactive_and_preserves_pending_edit_control(self):
        self._pending((), self.command_name, expected_active=False)

    def _accepted(self, subnames, expected_active):
        self._select(*subnames)
        self.doc.recompute()
        before = self._model()
        self._run(self.command_name)
        self.doc.recompute()
        self.assertEqual(tuple(c.IsActive for c in self.sketch.Constraints), expected_active)
        self.assertEqual(self.sketch.GeometryCount, 2)
        self.assertEqual(self.sketch.ConstraintCount, 2)
        self.assertEqual(self._model()["lines"], before["lines"])
        self.assertEqual(self._model()["construction"], before["construction"])
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertAlmostEqual(self.sketch.Shape.Length, 18)
        self.assertAlmostEqual(self.box.Shape.Volume, 24)
        self.assertEqual(Gui.Selection.getSelectionEx(), [])
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(len(self.doc.UndoNames), 1)
        after = self._model()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self._model(), before)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(self._model(), after)

    def test_selected_constraint_toggles_and_one_undo_redo_control(self):
        self._accepted(("Constraint1",), (False, True))

    def test_mixed_constraint_and_edge_toggles_only_constraint_control(self):
        self._accepted(("Edge1", "Constraint2"), (True, False))

    def test_all_selected_constraints_toggle_and_one_undo_redo_control(self):
        self._accepted(("Constraint1", "Constraint2"), (False, False))
