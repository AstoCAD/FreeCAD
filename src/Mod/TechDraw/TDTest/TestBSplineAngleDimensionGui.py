# SPDX-License-Identifier: LGPL-2.1-or-later
"""Projected dimensions retain references to straight B-spline drawing edges."""

import math
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import TechDraw  # noqa: F401
    from PySide import QtCore


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestBSplineAngleDimensionGui(unittest.TestCase):
    def setUp(self):
        self.doc_name = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        ]
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog())
        Gui.Selection.clearSelection()
        Gui.activateWorkbench("TechDrawWorkbench")
        self.preferences = App.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions"
        )
        self.previous_autocorrect = self.preferences.GetBool("AutoCorrectRefs", True)
        self.autocorrect_was_present = any(
            item[1] == "AutoCorrectRefs" for item in (self.preferences.GetContents() or [])
        )
        self.previous_matcher = self.preferences.GetBool("UseMatcher", True)
        self.matcher_was_present = any(
            item[1] == "UseMatcher" for item in (self.preferences.GetContents() or [])
        )
        self.addCleanup(self._restore_autocorrect)
        self.preferences.SetBool("AutoCorrectRefs", True)
        self.preferences.SetBool("UseMatcher", True)

    def _restore_autocorrect(self):
        if self.autocorrect_was_present:
            self.preferences.SetBool("AutoCorrectRefs", self.previous_autocorrect)
        else:
            self.preferences.RemBool("AutoCorrectRefs")
        if self.matcher_was_present:
            self.preferences.SetBool("UseMatcher", self.previous_matcher)
        else:
            self.preferences.RemBool("UseMatcher")

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                self._pump()
                return bool(predicate())
            self._pump()
        return bool(predicate())

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._pump()
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

    @staticmethod
    def _endpoints(edge):
        return (
            edge.valueAt(edge.FirstParameter),
            edge.valueAt(edge.LastParameter),
        )

    @classmethod
    def _edge_signature(cls, edge):
        curve = edge.Curve
        return (
            type(curve).__name__,
            edge.Length,
            tuple(tuple(point) for point in cls._endpoints(edge)),
            (
                tuple(tuple(point) for point in curve.getPoles())
                if isinstance(curve, Part.BSplineCurve)
                else ()
            ),
        )

    def _create(self, kind):
        self.doc = App.newDocument("BSplineAngleDimension")
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        origin = App.Vector(0, 0, 0)
        end = App.Vector(20, 0, 0)
        if kind == "line":
            first = Part.makeLine(origin, end)
        else:
            spline = Part.BSplineCurve()
            if kind == "straight":
                poles = [origin, App.Vector(5, 0, 0), App.Vector(13, 0, 0), end]
                spline.buildFromPolesMultsKnots(poles, [2, 1, 1, 2], [0, 1, 2, 3], False, 1)
                self.assertEqual(spline.Degree, 1)
            else:
                self.assertEqual(kind, "curved")
                poles = [origin, App.Vector(6, 3, 0), App.Vector(14, 3, 0), end]
                spline.buildFromPolesMultsKnots(poles, [3, 1, 3], [0, 1, 2], False, 2)
                self.assertEqual(spline.Degree, 2)
            self.assertEqual(
                [tuple(point) for point in spline.getPoles()], [tuple(p) for p in poles]
            )
            first = spline.toShape()
            self.assertIsInstance(first.Curve, Part.BSplineCurve)
        diagonal = Part.makeLine(origin, App.Vector(10, 10, 0))
        self.source = self.doc.addObject("Part::Feature", "SourceWire")
        self.source.Shape = Part.Wire([first, diagonal])
        self.assertTrue(self.source.Shape.isValid())
        self.assertEqual(len(self.source.Shape.Edges), 2)
        self.source_signature = tuple(
            self._edge_signature(edge) for edge in self.source.Shape.Edges
        )
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        self.template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template_file = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(template_file.is_file())
        self.template.Template = str(template_file)
        self.page.Template = self.template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.view.Source = [self.source]
        self.view.Direction = (0, 0, 1)
        self.view.XDirection = (1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.Rotation = 0
        self.view.CoarseView = False
        self.page.addView(self.view)
        self.doc.recompute()
        self.page.ViewObject.show()
        previous = None
        stable = 0

        def ready():
            nonlocal previous, stable
            if not self.view.isProjectionReady() or "Up-to-date" not in self.view.State:
                stable = 0
                return False
            edges = self.view.getVisibleEdges()
            if len(edges) != 2 or self.view.getHiddenEdges():
                stable = 0
                return False
            current = tuple(self._edge_signature(edge) for edge in edges)
            stable = stable + 1 if current == previous else 0
            previous = current
            return stable >= 3

        self.assertTrue(self._wait(ready), list(self.view.State))
        self.assertEqual(self.page.Template, self.template)
        self.assertEqual(self.view.Source, [self.source])
        self.doc.clearUndos()

    def _find_edge(self, first, last):
        center = self.view.getGeometricCenter()
        expected = [self.view.projectPoint(point - center, False) for point in (first, last)]
        matches = []
        for index in range(len(self.view.getVisibleEdges()) + len(self.view.getHiddenEdges())):
            edge = self.view.getEdgeByIndex(index).copy()
            actual = self._endpoints(edge)
            if any(
                (actual[0] - expected[order]).Length < 1e-7
                and (actual[1] - expected[1 - order]).Length < 1e-7
                for order in (0, 1)
            ):
                matches.append(("Edge" + str(index), edge))
        self.assertEqual(len(matches), 1, (tuple(map(tuple, expected)), matches))
        return matches[0]

    def _angle(self):
        origin = App.Vector(0, 0, 0)
        first_name, first = self._find_edge(origin, App.Vector(20, 0, 0))
        diagonal_name, diagonal = self._find_edge(origin, App.Vector(10, 10, 0))
        self.assertAlmostEqual(first.Length, 20, delta=1e-7)
        self.assertAlmostEqual(diagonal.Length, math.sqrt(200), delta=1e-7)
        names = (first_name, diagonal_name)
        Gui.Selection.clearSelection()
        for name in names:
            Gui.Selection.addSelection(self.doc_name, self.view.Name, name)
        selection = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selection), 1)
        self.assertEqual(selection[0].Object, self.view)
        self.assertEqual(tuple(selection[0].SubElementNames), names)
        command = Gui.Command.get("TechDraw_AngleDimension")
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        before = {obj.Name for obj in self.doc.Objects}
        Gui.runCommand("TechDraw_AngleDimension", 0)
        self.doc.recompute()
        dimensions = [
            obj
            for obj in self.doc.Objects
            if obj.Name not in before and obj.isDerivedFrom("TechDraw::DrawViewDimension")
        ]
        self.assertEqual(len(dimensions), 1)
        dimension = dimensions[0]
        self.assertEqual(dimension.Type, "Angle")
        self.assertEqual(dimension.MeasureType, "Projected")
        self.assertEqual(dimension.References2D, [(self.view, names)])
        self.assertEqual(dimension.References3D, [])
        saved = dimension.SavedGeometry
        self.assertEqual(len(saved), 2)
        self.assertTrue(all(not shape.isNull() for shape in saved))
        self.assertEqual(type(saved[0].Edges[0].Curve), type(first.Curve))
        self.assertTrue(
            self._wait(lambda: "Up-to-date" in dimension.State),
            (list(dimension.State), dimension.getStatusString()),
        )
        self.assertAlmostEqual(dimension.getRawValue(), 45, delta=1e-7)
        dimension.touch()
        self.doc.recompute()
        self.assertTrue(
            self._wait(lambda: "Up-to-date" in dimension.State),
            (list(dimension.State), dimension.getStatusString()),
        )
        self.assertAlmostEqual(dimension.getRawValue(), 45, delta=1e-7)
        self.assertEqual(dimension.References2D, [(self.view, names)])
        self.assertEqual(
            tuple(self._edge_signature(e) for e in self.source.Shape.Edges), self.source_signature
        )
        self.assertEqual(self.view.Source, [self.source])

    def test_ordinary_line_angle_control(self):
        self._create("line")
        self._angle()

    def test_straight_multipole_bspline_angle_recomputes(self):
        self._create("straight")
        _, projected = self._find_edge(App.Vector(0, 0, 0), App.Vector(20, 0, 0))
        self.assertIsInstance(projected.Curve, Part.BSplineCurve)
        self.assertEqual(projected.Curve.Degree, 1)
        self.assertGreaterEqual(len(projected.Curve.getPoles()), 3)
        self._angle()

    def test_noncollinear_bspline_projection_control(self):
        self._create("curved")
        _, projected = self._find_edge(App.Vector(0, 0, 0), App.Vector(20, 0, 0))
        self.assertIsInstance(projected.Curve, Part.BSplineCurve)
        self.assertEqual(projected.Curve.Degree, 2)
        self.assertGreater(projected.Length, 20)
        self.assertEqual(len(projected.Curve.getPoles()), 4)
        self.assertEqual(
            tuple(self._edge_signature(edge) for edge in self.source.Shape.Edges),
            self.source_signature,
        )


if __name__ == "__main__":
    unittest.main()
