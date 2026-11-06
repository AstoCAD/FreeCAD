# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw.makeDistanceDim3d must anchor the dimension on the 3d points.

The 3d points were projected without subtracting the view's centroid, inverted
twice and not scaled or rotated, so the two cosmetic vertices of the dimension
landed far outside the view (mirrored and shifted by the model position).
"""

import math
import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDistanceDim3dTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDistanceDim3d")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length = 10
        self.box.Width = 20
        self.box.Height = 30
        self.box.Placement.Base = FreeCAD.Vector(100, 200, 300)
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.view.XDirection = FreeCAD.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def assertVectorAlmostEqual(self, actual, expected):
        self.assertAlmostEqual(actual.x, expected.x, places=6)
        self.assertAlmostEqual(actual.y, expected.y, places=6)
        self.assertAlmostEqual(actual.z, expected.z, places=6)

    def _makeDimension(self):
        before = {obj.Name for obj in self.doc.Objects}
        TechDraw.makeDistanceDim3d(
            self.view,
            "Distance",
            FreeCAD.Vector(100, 200, 330),
            FreeCAD.Vector(110, 220, 330),
        )
        created = [obj for obj in self.doc.Objects if obj.Name not in before]
        dims = [obj for obj in created if obj.isDerivedFrom("TechDraw::DrawViewDimension")]
        self.assertEqual(len(dims), 1)
        return dims[0]

    def _check(self, scale, rotation):
        self.view.Scale = scale
        self.view.Rotation = rotation
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)
        dim = self._makeDimension()
        ((owner, _subNames),) = dim.References2D
        self.assertEqual(owner, self.view)
        # the dimension's two cosmetic vertices are the only ones of the view
        points = [vertex.Point for vertex in self.view.CosmeticVertexes]
        self.assertEqual(len(points), 2)
        # canonical (unscaled, unrotated) view coordinates of the box corners (100, 200)
        # and (110, 220), the same as makeCosmeticVertex3d and makeCosmeticLine3D give,
        # and as makeDistanceDim gives for the scaled and rotated view points of the corners
        self.assertVectorAlmostEqual(points[0], FreeCAD.Vector(-5, -10, 0))
        self.assertVectorAlmostEqual(points[1], FreeCAD.Vector(5, 10, 0))
        self.doc.recompute()
        self.assertAlmostEqual(dim.getRawValue(), math.hypot(10, 20), places=6)

    def testUnscaledView(self):
        self._check(1.0, 0.0)

    def testScaledView(self):
        self._check(2.0, 0.0)

    def testScaledRotatedView(self):
        self._check(2.0, 90.0)


if __name__ == "__main__":
    unittest.main()
