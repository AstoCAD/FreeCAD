# SPDX-License-Identifier: LGPL-2.1-or-later
"""Model edge/vertex references must produce drawable distance dimensions."""

import time
import unittest

import FreeCAD as App
import Part
import TechDraw
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionEdgeVertexTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DimensionEdgeVertexRegression")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Geometry")
        self.source.Shape = Part.makeCompound([
            Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
            Part.makeLine(App.Vector(0, 8, 0), App.Vector(10, 8, 0)),
            Part.Vertex(App.Vector(3, 4, 0))])
        self.point_sub = next(
            "Vertex" + str(index)
            for index, vertex in enumerate(self.source.Shape.Vertexes, 1)
            if (vertex.Point - App.Vector(3, 4, 0)).Length < 1e-7)
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        deadline = time.monotonic() + 20
        while not self.view.getVisibleEdges() or "Up-to-date" not in self.view.State:
            self.assertLess(time.monotonic(), deadline, self.view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

    @staticmethod
    def _clearReferences(dimension):
        dimension.References3D = []
        dimension.References2D = []

    def _checkDimension(self, sub_names, expected, saved_types, mode="True"):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.addCleanup(self._clearReferences, dimension)
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(self.view, "")]
        dimension.MeasureType = mode
        try:
            dimension.References3D = [(self.source, sub) for sub in sub_names]
        except Exception as exc:
            self.fail(f"Assigning the dimension's model references failed: {exc}")
        self.doc.recompute()
        self.assertEqual([shape.ShapeType for shape in dimension.SavedGeometry], saved_types)
        self.assertIn("Up-to-date", dimension.State)
        self.assertNotIn("Invalid", dimension.State)
        self.assertAlmostEqual(dimension.getRawValue(), expected)
        first, second = dimension.getLinearPoints()
        self.assertAlmostEqual((second - first).Length, expected)

    def testEdgeVertexTrue(self):
        self._checkDimension(["Edge1", self.point_sub], 4, ["Edge", "Vertex"])

    def testVertexEdgeTrue(self):
        self._checkDimension([self.point_sub, "Edge1"], 4, ["Vertex", "Edge"])

    def testEdgeVertexProjected(self):
        self._checkDimension(["Edge1", self.point_sub], 4, ["Edge", "Vertex"], "Projected")

    def testVertexEdgeProjected(self):
        self._checkDimension([self.point_sub, "Edge1"], 4, ["Vertex", "Edge"], "Projected")

    def testSingleEdgeControl(self):
        self._checkDimension(["Edge1"], 10, ["Edge"])

    def testTwoVerticesControl(self):
        self._checkDimension(["Vertex1", "Vertex2"], 10, ["Vertex", "Vertex"])

    def testTwoEdgesControl(self):
        self._checkDimension(["Edge1", "Edge2"], 8, ["Edge", "Edge"], "Projected")

    def testTwoEdgesReversedControl(self):
        self._checkDimension(["Edge2", "Edge1"], 8, ["Edge", "Edge"], "Projected")
