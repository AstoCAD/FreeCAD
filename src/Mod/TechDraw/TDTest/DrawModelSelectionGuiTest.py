# SPDX-License-Identifier: LGPL-2.1-or-later
"""Drawing commands reject model geometry without changing the drawing."""

from pathlib import Path
import time
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw
from PySide import QtCore, QtWidgets


class TestTechDrawModelSelectionGui(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        ]
        self.doc_name = None
        self.retained = []
        self.opened_offset = False
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("DrawingSelection_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(Path(__file__).with_name("TestTemplate.svg"))
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(1, 1, 1)
        self.view.XDirection = App.Vector(1, -1, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(
                lambda: len(self.view.getVisibleEdges()) >= 2 and "Up-to-date" in self.view.State
            )
        )
        self.assertAlmostEqual(self.source.Shape.Volume, 6000)
        self.assertEqual(self.view.CosmeticVertexes, [])
        self.assertFalse(hasattr(self.source, "getEdgeBySelection"))
        self.assertFalse(hasattr(self.source, "getVertexBySelection"))
        self.assertEqual(self.doc.FileName, "")
        self.doc.clearUndos()

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

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            if self.opened_offset:
                task = Gui.Control.activeTaskDialog()
                if task:
                    task.reject()
                    self._pump()
            Gui.Selection.clearSelection()
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, obj, names in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(obj):
                if names:
                    for name in names:
                        Gui.Selection.addSelection(document, obj, name)
                else:
                    Gui.Selection.addSelection(document, obj)

    def _retain(self, widget):
        while widget is not None:
            self.retained.append(widget)
            widget = widget.parent()

    def _select(self, obj, *names):
        Gui.Selection.clearSelection()
        if names:
            for name in names:
                Gui.Selection.addSelection(self.doc_name, obj.Name, name)
        else:
            Gui.Selection.addSelection(self.doc_name, obj.Name)
        selection = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selection), 1)
        self.assertEqual(selection[0].Object, obj)
        self.assertEqual(tuple(selection[0].SubElementNames), tuple(names))

    def _model(self):
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "page_views": tuple(view.Name for view in self.page.Views),
            "source_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "source_volume": self.source.Shape.Volume,
            "source_placement": (
                tuple(self.source.Placement.Base),
                self.source.Placement.Rotation.Q,
            ),
            "view_source": tuple(obj.Name for obj in self.view.Source),
            "view_position": (self.view.X.Value, self.view.Y.Value),
            "view_edges": tuple(edge.Length for edge in self.view.getVisibleEdges()),
            "cosmetic_vertices": tuple(
                (vertex.Tag, tuple(vertex.Point)) for vertex in self.view.CosmeticVertexes
            ),
        }

    def _snapshot(self):
        return {
            "model": self._model(),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "selection": tuple(
                (entry.DocumentName, entry.ObjectName, tuple(entry.SubElementNames))
                for entry in Gui.Selection.getSelectionEx()
            ),
        }

    def _run(self, command_name):
        command = Gui.Command.get(command_name)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports)
        previous = [widget.toPlainText() for widget in reports]
        errors = []
        testcase = self

        class AnswerOwnedValidation(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() != QtCore.QEvent.Show or not isinstance(
                    watched, QtWidgets.QMessageBox
                ):
                    return False
                if (
                    watched.windowTitle() != "TechDraw_Utils"
                    or watched.text() != "No view selected"
                ):
                    return False
                testcase._retain(watched)

                def answer():
                    try:
                        button = watched.button(QtWidgets.QMessageBox.Ok)
                        testcase.assertIsNotNone(button)
                        testcase._retain(button)
                        button.click()
                    except Exception as error:
                        errors.append(repr(error))
                        watched.reject()

                QtCore.QTimer.singleShot(0, answer)
                return False

        responder = AnswerOwnedValidation()
        application = QtWidgets.QApplication.instance()
        application.installEventFilter(responder)
        try:
            Gui.runCommand(command_name)
        finally:
            application.removeEventFilter(responder)
        self._pump()
        self.assertEqual(errors, [])
        for widget, before in zip(reports, previous):
            current = widget.toPlainText()
            delta = current[len(before) :] if current.startswith(before) else current
            for marker in ("traceback", "attributeerror", "access violation", "<exception>"):
                self.assertNotIn(marker, delta.lower())

    def _rejected(self, command_name):
        before = self._snapshot()
        self._run(command_name)
        self.assertEqual(self._snapshot(), before)
        self.assertIsNone(Gui.Control.activeTaskDialog())

    def test_axonometric_command_rejects_real_model_edges(self):
        self.assertEqual(self.source.Shape.Edges[0].ShapeType, "Edge")
        self.assertEqual(self.source.Shape.Edges[1].ShapeType, "Edge")
        self._select(self.source, "Edge1", "Edge2")
        self._rejected("TechDraw_AxoLengthDimension")

    def test_offset_command_rejects_real_model_vertex(self):
        self.assertEqual(self.source.Shape.Vertexes[0].ShapeType, "Vertex")
        self._select(self.source, "Vertex1")
        self.opened_offset = True
        self._rejected("TechDraw_CommandAddOffsetVertex")

    def test_position_section_model_object_control(self):
        self._select(self.source)
        self._rejected("TechDraw_ExtensionPositionSectionView")

    def test_axonometric_real_view_edges_and_undo_control(self):
        chosen = None
        edges = []
        for index in range(len(self.view.getVisibleEdges())):
            name = "Edge" + str(index)
            edge = self.view.getEdgeBySelection(name)
            self.assertEqual(len(edge.Vertexes), 2)
            direction = edge.Vertexes[1].Point - edge.Vertexes[0].Point
            self.assertGreater(direction.Length, 0)
            for other_name, other_direction in edges:
                if (
                    direction.cross(other_direction).Length
                    / (direction.Length * other_direction.Length)
                    > 0.2
                ):
                    chosen = (other_name, name)
                    break
            if chosen:
                break
            edges.append((name, direction))
        self.assertIsNotNone(chosen)
        self._select(self.view, *chosen)
        before = self._model()
        self._run("TechDraw_AxoLengthDimension")
        dimensions = [
            obj for obj in self.doc.Objects if obj.isDerivedFrom("TechDraw::DrawViewDimension")
        ]
        self.assertEqual(len(dimensions), 1)
        self.assertEqual(dimensions[0].References2D[0][0], self.view)
        self.assertIn(dimensions[0], self.page.Views)
        self.assertTrue(dimensions[0].isValid())
        self.assertFalse(self.doc.HasPendingTransaction)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self._model(), before)

    def test_offset_real_view_vertex_accept_and_undo_control(self):
        vertex = self.view.getVertexBySelection("Vertex0")
        self.assertEqual(vertex.ShapeType, "Vertex")
        expected = TechDraw.makeCanonicalPoint(self.view, vertex.Point, False) + App.Vector(3, 4, 0)
        self._select(self.view, "Vertex0")
        before = self._model()
        self.opened_offset = True
        self._run("TechDraw_CommandAddOffsetVertex")
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        self.retained.append(task)
        for name, value in (("dSpinBoxX", 3), ("dSpinBoxY", 4)):
            widgets = [
                widget
                for widget in Gui.getMainWindow().findChildren(QtWidgets.QDoubleSpinBox, name)
                if widget.isVisible()
            ]
            self.assertEqual(len(widgets), 1)
            self._retain(widgets[0])
            widgets[0].setValue(value)
            self._pump()
        task.accept()
        self._pump()
        self.assertIsNone(Gui.Control.activeTaskDialog())
        self.assertEqual(len(self.view.CosmeticVertexes), 1)
        self.assertLess((self.view.CosmeticVertexes[0].Point - expected).Length, 1e-7)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self._model(), before)
