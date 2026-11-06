# SPDX-License-Identifier: LGPL-2.1-or-later
"""makeCosmeticVertex3d must put the vertex where the 3d point is drawn.

The projected point was inverted twice (once by projectPoint, once by
addCosmeticVertex), so the vertex came out mirrored about the view's X axis,
while makeCosmeticLine3D and makeCosmeticCircle3d put their ends on the point.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticVertex3dTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticVertex3d")
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
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def assertVectorAlmostEqual(self, actual, expected):
        self.assertAlmostEqual(actual.x, expected.x, places=6)
        self.assertAlmostEqual(actual.y, expected.y, places=6)
        self.assertAlmostEqual(actual.z, expected.z, places=6)

    def testVertexOnModelCorner(self):
        # top view of a 10 x 20 box: the corner (110, 220) is drawn at (+5, +10)
        tag = self.view.makeCosmeticVertex3d(FreeCAD.Vector(110, 220, 330))
        self.assertVectorAlmostEqual(
            self.view.getCosmeticVertex(tag).Point, FreeCAD.Vector(5, 10, 0)
        )

    def testVertexMatchesTwoDimensionalAndLine3d(self):
        corner = FreeCAD.Vector(110, 220, 330)
        tag3d = self.view.makeCosmeticVertex3d(corner)
        tag2d = self.view.makeCosmeticVertex(FreeCAD.Vector(5, 10, 0))
        lineTag = self.view.makeCosmeticLine3D(FreeCAD.Vector(100, 200, 330), corner)
        point3d = self.view.getCosmeticVertex(tag3d).Point
        self.assertVectorAlmostEqual(point3d, self.view.getCosmeticVertex(tag2d).Point)
        self.assertVectorAlmostEqual(point3d, self.view.getCosmeticEdge(lineTag).End)
        self.doc.recompute()
        self.assertIn("Up-to-date", self.view.State)


if __name__ == "__main__":
    unittest.main()
