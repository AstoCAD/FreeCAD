# SPDX-License-Identifier: LGPL-2.1-or-later
"""Horizontal and vertical dimensions between two circles with 3d references.

DistanceX/DistanceY between two circles measure between the circles' sides.
DrawViewDimension::getPointsTwoCircles chose which sides from the dot product of
the center direction, taken in the view's coordinate system, with the alignment
direction, taken in model coordinates. Outside a top view this gave the wrong
sides (DistanceX 38 instead of 22 in a rear view) or a zero product and the
closest points (DistanceY 33.6 instead of 32 in a front view). The same
dimension with 2d references was right.
"""

import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionCircleAlignmentTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TDDimensionCircleAlignment")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Geometry")
        self.source.Shape = Part.makeCompound([
            Part.makeCylinder(5, 10, App.Vector(0, 0, 0), App.Vector(0, 1, 0)),
            Part.makeCylinder(3, 10, App.Vector(30, 0, 40), App.Vector(0, 1, 0))])
        # the two circles on the y = 0 plane
        self.circles3d = [
            "Edge%d" % (i + 1) for i, e in enumerate(self.source.Shape.Edges)
            if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Center.y) < 1e-9]
        self.assertEqual(len(self.circles3d), 2)
        self.page = createPageWithSVGTemplate(self.doc)

    def makeView(self, direction, xDirection):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [self.source]
        view.Direction = direction
        view.XDirection = xDirection
        view.ScaleType = "Custom"
        view.Scale = 1
        self.doc.recompute()
        circles2d = ["Edge%d" % i for i, e in enumerate(view.getVisibleEdges())
                     if isinstance(e.Curve, Part.Circle)]
        self.assertEqual(len(circles2d), 2)
        return view, circles2d

    def dimension(self, view, dimType, references3d=None, references2d=None):
        dim = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(dim)
        dim.Type = dimType
        if references3d:
            dim.References2D = [(view, "")]
            dim.MeasureType = "Projected"
            dim.References3D = [(self.source, sub) for sub in references3d]
        else:
            dim.References2D = [(view, sub) for sub in references2d]
        self.doc.recompute()
        self.assertIn("Up-to-date", dim.State)
        return dim

    def checkView(self, direction, xDirection):
        view, circles2d = self.makeView(direction, xDirection)
        for dimType, expected in (("DistanceX", 22.0), ("DistanceY", 32.0)):
            with self.subTest(direction=direction, type=dimType):
                dim2d = self.dimension(view, dimType, references2d=circles2d)
                dim3d = self.dimension(view, dimType, references3d=self.circles3d)
                self.assertAlmostEqual(dim2d.getRawValue(), expected, places=6)
                self.assertAlmostEqual(dim3d.getRawValue(), expected, places=6)

    def testFrontView(self):
        self.checkView(App.Vector(0, -1, 0), App.Vector(1, 0, 0))

    def testRearView(self):
        self.checkView(App.Vector(0, 1, 0), App.Vector(-1, 0, 0))


if __name__ == "__main__":
    unittest.main()
