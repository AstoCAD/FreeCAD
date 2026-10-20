# SPDX-License-Identifier: LGPL-2.1-or-later
"""A model object's internal name must not change a dimension's subelement."""

import time
import unittest

import FreeCAD as App
import Part
import TechDraw
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionShapeNameTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DimensionShapeNameRegression")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.edge = Part.makeLine(App.Vector(0, 0, 0), App.Vector(12, 0, 0))
        self.compound = Part.makeCompound([
            self.edge, Part.makeLine(App.Vector(0, 4, 0), App.Vector(7, 4, 0))])
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = self.compound
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [source]
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
        # Clear model references before view references: a failed model lookup
        # must not be repeated while document deletion updates the dimension.
        dimension.References3D = []
        dimension.References2D = []

    def _checkDimension(self, references, expected, expected_type):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.addCleanup(self._clearReferences, dimension)
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(self.view, "")]
        dimension.MeasureType = "True"
        try:
            dimension.References3D = references
        except Exception as exc:
            self.fail(f"Assigning the dimension's model references failed: {exc}")
        self.doc.recompute()
        self.assertIn("Up-to-date", dimension.State)
        self.assertNotIn("Invalid", dimension.State)
        self.assertEqual([shape.ShapeType for shape in dimension.SavedGeometry],
                         [expected_type] * len(references))
        self.assertAlmostEqual(dimension.getRawValue(), expected)
        first, second = dimension.getLinearPoints()
        self.assertAlmostEqual((second - first).Length, expected)

    def _checkCompoundEdge(self, name):
        feature = self.doc.addObject("Part::Feature", name)
        feature.Shape = self.compound
        self._checkDimension([(feature, "Edge2")], 7, "Edge")

    def _checkEdgeVertices(self, name):
        feature = self.doc.addObject("Part::Feature", name)
        feature.Shape = self.edge
        self._checkDimension([(feature, "Vertex1"), (feature, "Vertex2")], 12, "Vertex")

    def testOrdinaryNamedCompoundEdge(self):
        self._checkCompoundEdge("OrdinaryCompound")

    def testPointNamedCompoundEdge(self):
        self._checkCompoundEdge("HasPointWordCompound")

    def testVertexNamedCompoundEdge(self):
        self._checkCompoundEdge("HasVertexWordCompound")

    def testOrdinaryNamedEdgeVertices(self):
        self._checkEdgeVertices("OrdinaryEdge")

    def testPointNamedEdgeVertices(self):
        self._checkEdgeVertices("HasPointWordEdge")

    def testVertexNamedEdgeVertices(self):
        self._checkEdgeVertices("HasVertexWordEdge")

    def testPartVertexObjects(self):
        pair = [self.doc.addObject("Part::Vertex", name) for name in ("VertexA", "VertexB")]
        pair[0].X, pair[1].X = 2, 11
        pair[0].Y = pair[1].Y = 3
        self.doc.recompute()
        self._checkDimension([(point, "Vertex1") for point in pair], 9, "Vertex")

    def testPartDesignPointObjects(self):
        import PartDesign

        pair = [self.doc.addObject("PartDesign::Point", name) for name in ("PointA", "PointB")]
        pair[0].Placement = App.Placement(App.Vector(2, 3, 0), App.Rotation())
        pair[1].Placement = App.Placement(App.Vector(11, 3, 0), App.Rotation())
        self.doc.recompute()
        self._checkDimension([(point, "Vertex1") for point in pair], 9, "Vertex")
