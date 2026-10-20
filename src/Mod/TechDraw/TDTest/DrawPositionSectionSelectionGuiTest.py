# SPDX-License-Identifier: LGPL-2.1-or-later
"""Section positioning rejects unsupported selection counts without changing drawings."""

from pathlib import Path
import time
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
from PySide import QtCore, QtWidgets


class TestPositionSectionSelectionGui(unittest.TestCase):
    COMMAND = "TechDraw_ExtensionPositionSectionView"

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
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("PositionSection_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(Path(__file__).with_name("TestTemplate.svg"))
        self.page.Template = template
        self.base = self._view("BaseView", (0, 0, 1), 60, 100)
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        self.page.addView(self.section)
        self.section.Source = [self.source]
        self.section.BaseView = self.base
        self.section.Direction = App.Vector(0, 1, 0)
        self.section.SectionNormal = App.Vector(0, 1, 0)
        self.section.SectionOrigin = App.Vector(10, 15, 5)
        self.section.ScaleType = "Custom"
        self.section.Scale = 1
        self.section.X, self.section.Y = 150, 125
        self.other = self._view("OtherView", (1, 0, 0), 220, 80)
        self.other.XDirection = App.Vector(0, 1, 0)
        self.views = (self.base, self.section, self.other)
        self.doc.recompute()
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(
                lambda: all(
                    len(view.getVisibleEdges()) == 4 and "Up-to-date" in view.State
                    for view in self.views
                )
            ),
            "The native box views and section must finish their ordinary projections",
        )
        self.assertEqual(self.section.BaseView, self.base)
        self.assertFalse(self.section.LockRelativePositionToSource)
        self.assertAlmostEqual(self.source.Shape.Volume, 6000, places=7)
        self.assertAlmostEqual(self.section.Scale, self.base.Scale)
        self.doc.clearUndos()
        self.assertEqual(self.doc.FileName, "")

    def _view(self, name, direction, x, y):
        view = self.doc.addObject("TechDraw::DrawViewPart", name)
        self.page.addView(view)
        view.Source = [self.source]
        view.Direction = App.Vector(*direction)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.X, view.Y = x, y
        return view

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
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            doc = App.getDocument(self.doc_name)
            if doc.HasPendingTransaction:
                doc.abortTransaction()
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

    def _selection(self):
        return tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        )

    def _select(self, entries):
        Gui.Selection.clearSelection()
        for view, sub in entries:
            if sub:
                Gui.Selection.addSelection(self.doc_name, view.Name, sub)
            else:
                Gui.Selection.addSelection(self.doc_name, view.Name)
        self.assertEqual(
            self._selection(),
            tuple((self.doc_name, view.Name, (sub,) if sub else ()) for view, sub in entries),
        )

    def _positions(self):
        return {view.Name: (view.X.Value, view.Y.Value) for view in self.views}

    def _geometry(self):
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "page_views": tuple(view.Name for view in self.page.Views),
            "source_volume": self.source.Shape.Volume,
            "source_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "visible_edge_lengths": tuple(
                (view.Name, tuple(edge.Length for edge in view.getVisibleEdges()))
                for view in self.views
            ),
        }

    def _run(self):
        command = Gui.Command.get(self.COMMAND)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports, "The native Report view must observe caught command errors")
        previous = [widget.toPlainText() for widget in reports]
        Gui.runCommand(self.COMMAND)
        self._pump()
        output = []
        for widget, prior in zip(reports, previous):
            current = widget.toPlainText()
            output.append(current[len(prior) :] if current.startswith(prior) else current)
        delta = "\n".join(output)
        for marker in (
            "traceback",
            "unboundlocalerror",
            "access violation",
            "<exception>",
            "running the python command",
        ):
            self.assertNotIn(marker, delta.lower())

    def _unchanged(self):
        before = (self._positions(), self._geometry(), self._selection())
        self._run()
        after = (self._positions(), self._geometry(), self._selection())
        self.assertEqual(after, before)

    def test_three_actual_views_are_ignored_without_command_error(self):
        self._select([(self.section, ""), (self.base, ""), (self.other, "")])
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 3)
        self._unchanged()

    def test_empty_selection_control(self):
        self.assertEqual(self._selection(), ())
        self._unchanged()

    def test_one_ordinary_view_control(self):
        self._select([(self.base, "")])
        self._unchanged()

    def test_one_section_aligns_y_control(self):
        self._select([(self.section, "")])
        before_positions = self._positions()
        geometry = self._geometry()
        self.assertGreater(abs(self.section.X.Value - self.base.X.Value), 25)
        self._run()
        self.assertAlmostEqual(self.section.X.Value, before_positions[self.section.Name][0])
        self.assertAlmostEqual(self.section.Y.Value, self.base.Y.Value, places=7)
        self.assertEqual(self._positions()[self.base.Name], before_positions[self.base.Name])
        self.assertEqual(self._positions()[self.other.Name], before_positions[self.other.Name])
        self.assertEqual(self._geometry(), geometry)

    def test_one_section_aligns_x_control(self):
        self.section.X, self.section.Y = 75, 180
        self.doc.recompute()
        self._select([(self.section, "")])
        before_positions = self._positions()
        geometry = self._geometry()
        self._run()
        self.assertAlmostEqual(self.section.X.Value, self.base.X.Value, places=7)
        self.assertAlmostEqual(self.section.Y.Value, before_positions[self.section.Name][1])
        self.assertEqual(self._positions()[self.base.Name], before_positions[self.base.Name])
        self.assertEqual(self._positions()[self.other.Name], before_positions[self.other.Name])
        self.assertEqual(self._geometry(), geometry)

    def test_two_views_align_real_straight_edge_to_vertex_control(self):
        edge_name = "Edge0"
        vertex_name = "Vertex0"
        edge = self.section.getEdgeBySelection(edge_name)
        vertex = self.base.getVertexBySelection(vertex_name)
        self.assertEqual(len(edge.Vertexes), 2)
        self.assertEqual(vertex.ShapeType, "Vertex")
        direction = edge.Curve.Direction
        self.assertGreater(direction.Length, 0)
        self.assertAlmostEqual(direction.z, 0, places=7)
        scale = self.base.Scale
        first = edge.Vertexes[0].Point * scale
        base_point = App.Vector(self.base.X.Value, self.base.Y.Value, 0) + vertex.Point * scale
        before_positions = self._positions()
        before_center = App.Vector(self.section.X.Value, self.section.Y.Value, 0)
        self.assertGreater((base_point - before_center - first).cross(direction).Length, 1)
        self._select([(self.section, edge_name), (self.base, vertex_name)])
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 2)
        geometry = self._geometry()
        self._run()
        after_center = App.Vector(self.section.X.Value, self.section.Y.Value, 0)
        self.assertAlmostEqual(
            (base_point - after_center - first).cross(direction).Length, 0, places=7
        )
        self.assertAlmostEqual((after_center - before_center).dot(direction), 0, places=7)
        self.assertEqual(self._positions()[self.base.Name], before_positions[self.base.Name])
        self.assertEqual(self._positions()[self.other.Name], before_positions[self.other.Name])
        self.assertEqual(self._geometry(), geometry)
