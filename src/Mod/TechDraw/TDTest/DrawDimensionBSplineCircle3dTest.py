# SPDX-License-Identifier: LGPL-2.1-or-later
"""Radius and diameter dimensions on circular B-spline model edges.

With a 3d reference to a B-spline edge that is a circle or an arc of circle,
DrawViewDimension::arcPointsFromEdge asked the B-spline adaptor for its circle
("GeomAdaptor_Curve::Circle() - curve is not a Circle") instead of the circle
it had just built from the B-spline, and the dimension became Invalid.
"""

import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionBSplineCircle3dTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TDDimensionBSplineCircle3d")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10)
        arc = Part.ArcOfCircle(Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 5), 0.0, 1.5)
        self.source = self.doc.addObject("Part::Feature", "Geometry")
        self.source.Shape = Part.makeCompound([
            circle.toBSpline().toShape(),
            arc.toBSpline().toShape(),
            Part.makeCircle(7, App.Vector(-30, 0, 0))])
        self.assertEqual([type(edge.Curve).__name__ for edge in self.source.Shape.Edges],
                         ["BSplineCurve", "BSplineCurve", "Circle"])
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 3)

    @staticmethod
    def _clearReferences(dimension):
        dimension.References3D = []
        dimension.References2D = []

    def _checkDimension(self, dimType, sub, expected, isArc):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.addCleanup(self._clearReferences, dimension)
        self.page.addView(dimension)
        dimension.Type = dimType
        dimension.References2D = [(self.view, "")]
        dimension.MeasureType = "Projected"
        dimension.References3D = [(self.source, sub)]
        self.doc.recompute()
        self.assertNotIn("Invalid", dimension.State)
        self.assertIn("Up-to-date", dimension.State)
        self.assertAlmostEqual(dimension.getRawValue(), expected, places=4)
        center, onCurve, _, arcStart, arcEnd, _ = dimension.getArcPoints()
        radius = expected / 2 if dimType == "Diameter" else expected
        self.assertAlmostEqual((onCurve - center).Length, radius, places=4)
        if isArc:
            self.assertAlmostEqual((arcStart - center).Length, radius, places=4)
            self.assertAlmostEqual((arcEnd - center).Length, radius, places=4)
            self.assertGreater((arcEnd - arcStart).Length, 1.0)

    def testRadiusOfBSplineCircle(self):
        self._checkDimension("Radius", "Edge1", 10.0, False)

    def testDiameterOfBSplineCircle(self):
        self._checkDimension("Diameter", "Edge1", 20.0, False)

    def testRadiusOfBSplineArc(self):
        self._checkDimension("Radius", "Edge2", 5.0, True)

    def testRadiusOfCircleControl(self):
        self._checkDimension("Radius", "Edge3", 7.0, False)


if __name__ == "__main__":
    unittest.main()
