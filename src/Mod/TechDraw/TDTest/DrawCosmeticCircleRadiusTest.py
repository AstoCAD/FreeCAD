# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cosmetic circles need a positive radius.

A zero radius built a degenerate circle edge, which made the Python API crash
with an access violation (makeCosmeticCircle and friends) or broke the next
recompute of the view (CosmeticEdge.Radius = 0). A negative radius raised an
OCC error or an unknown exception. The Gui task already refuses radius <= 0.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticCircleRadiusTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticCircleRadius")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _makers(self, radius):
        center = FreeCAD.Vector(1, 2, 0)
        return {
            "makeCosmeticCircle": lambda: self.view.makeCosmeticCircle(center, radius),
            "makeCosmeticCircleArc": lambda: self.view.makeCosmeticCircleArc(
                center, radius, 0.0, 90.0
            ),
            "makeCosmeticCircle3d": lambda: self.view.makeCosmeticCircle3d(center, radius),
            "makeCosmeticCircleArc3d": lambda: self.view.makeCosmeticCircleArc3d(
                center, radius, 0.0, 90.0
            ),
        }

    def testZeroRadiusIsRejected(self):
        for name, make in self._makers(0.0).items():
            with self.subTest(method=name):
                with self.assertRaises(ValueError):
                    make()
        self.assertEqual(self.view.CosmeticEdges, [])

    def testNegativeRadiusIsRejected(self):
        for name, make in self._makers(-2.0).items():
            with self.subTest(method=name):
                with self.assertRaises(ValueError):
                    make()
        self.assertEqual(self.view.CosmeticEdges, [])

    def testPositiveRadiusStillWorks(self):
        for name, make in self._makers(3.0).items():
            with self.subTest(method=name):
                tag = make()
                self.assertTrue(tag)
                self.assertAlmostEqual(self.view.getCosmeticEdge(tag).Radius, 3.0)
        self.doc.recompute()
        self.assertEqual(len(self.view.CosmeticEdges), 4)

    def testSetZeroRadiusIsRejected(self):
        tag = self.view.makeCosmeticCircle(FreeCAD.Vector(1, 2, 0), 5.0)
        edge = self.view.getCosmeticEdge(tag)
        for radius in (0.0, -1.0):
            with self.subTest(radius=radius):
                with self.assertRaises(ValueError):
                    edge.Radius = radius
                self.assertAlmostEqual(edge.Radius, 5.0)
        edge.Radius = 4.0
        self.assertAlmostEqual(edge.Radius, 4.0)
        self.doc.recompute()
        self.assertNotIn("Invalid", self.view.State)


if __name__ == "__main__":
    unittest.main()
