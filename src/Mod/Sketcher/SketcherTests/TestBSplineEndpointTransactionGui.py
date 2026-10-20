# SPDX-License-Identifier: LGPL-2.1-or-later
"""B-spline degree commands preserve transactions when only an endpoint is selected."""

import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher  # noqa: F401
from PySide import QtCore, QtWidgets


class TestBSplineEndpointTransactionGui(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.doc_name = None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("SketcherWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("SplineEndpoint_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.gui_doc = Gui.getDocument(self.doc_name)
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        curve = Part.BSplineCurve()
        curve.buildFromPolesMultsKnots(
            [
                App.Vector(0, 0, 0),
                App.Vector(15, 15, 0),
                App.Vector(30, 0, 0),
            ],
            [3, 3],
            [0, 1],
            False,
            2,
        )
        # A degree-elevated quadratic supports both accepted degree directions.
        curve.increaseDegree(3)
        self.sketch.addGeometry(curve, False)
        self.box = self.doc.addObject("Part::Box", "UnrelatedBox")
        self.box.Length, self.box.Width, self.box.Height = 2, 3, 4
        self.doc.recompute()
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertEqual(self.sketch.getGeoVertexIndex(0), (0, 1))
        self.assertAlmostEqual(self.box.Shape.Volume, 24)
        self.assertEqual(self.doc.FileName, "")
        self.assertTrue(self.gui_doc.setEdit(self.sketch.Name))
        self._pump()
        self.assertEqual(self.gui_doc.getInEdit().Object, self.sketch)
        self.assertIsInstance(self.sketch.Geometry[0], Part.BSplineCurve)
        self.assertEqual(self.sketch.Geometry[0].Degree, 3)
        self.doc.commitTransaction()
        self.doc.clearUndos()

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

    def _select(self, subname):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc_name, self.sketch.Name, subname)
        entries = Gui.Selection.getSelectionEx()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].Object, self.sketch)
        self.assertEqual(tuple(entries[0].SubElementNames), (subname,))
        if subname == "Vertex1":
            self.assertEqual(self.sketch.getGeoVertexIndex(0), (0, 1))
            self.assertEqual(self.sketch.getPoint(0, 1), self.sketch.Geometry[0].StartPoint)

    @staticmethod
    def _vector(point):
        return (point.x, point.y, point.z)

    def _model(self):
        curve = self.sketch.Geometry[0]
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "geometry_count": self.sketch.GeometryCount,
            "constraint_count": self.sketch.ConstraintCount,
            "degree": curve.Degree,
            "poles": tuple(self._vector(point) for point in curve.getPoles()),
            "weights": tuple(curve.getWeights()),
            "knots": tuple(curve.getKnots()),
            "multiplicities": tuple(curve.getMultiplicities()),
            "curve_samples": tuple(self._vector(curve.value(index / 20)) for index in range(21)),
            "valid": self.sketch.Shape.isValid(),
            "box_volume": self.box.Shape.Volume,
        }

    def _run(self, name):
        command = Gui.Command.get(name)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive(), "The ordinary command must accept this selection")
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

    def _pending(self, command):
        self._select("Vertex1")
        self.assertEqual(self.sketch.Geometry[0].Degree, 3)
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
        self._run(command)
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
        self.doc.abortTransaction()
        with self.subTest(oracle="unrelated_label_still_abortable"):
            self.assertEqual(self.box.Label, original_label)
        with self.subTest(oracle="unrelated_label_not_committed"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_increase_degree_endpoint_preserves_pending_edit(self):
        self._pending("Sketcher_BSplineIncreaseDegree")

    def test_decrease_degree_endpoint_preserves_pending_edit(self):
        self._pending("Sketcher_BSplineDecreaseDegree")

    def test_fit_all_endpoint_pending_control(self):
        self._pending("Std_ViewFitAll")

    def _accepted(self, name, expected_degree):
        self._select("Edge1")
        before = self._model()
        self._run(name)
        self.assertEqual(self.sketch.Geometry[0].Degree, expected_degree)
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 24)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertTrue(self.doc.UndoNames)
        after = self._model()
        self.doc.undo()
        self.doc.recompute()
        with self.subTest(oracle="one_undo_restores_spline"):
            self.assertEqual(self._model(), before)
        self.doc.redo()
        self.doc.recompute()
        with self.subTest(oracle="redo_restores_degree_operation"):
            self.assertEqual(self._model(), after)

    def test_selected_edge_increase_and_undo_redo_control(self):
        self._accepted("Sketcher_BSplineIncreaseDegree", 4)

    def test_selected_edge_decrease_and_undo_redo_control(self):
        self._accepted("Sketcher_BSplineDecreaseDegree", 2)
