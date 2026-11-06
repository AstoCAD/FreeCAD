# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cosmetic arcs keep their center through save and reload.

A reloaded cosmetic arc reported its center mirrored about the view X axis
(CosmeticEdge.Center gave (10, -20) for an arc made at (10, 20)), because
CosmeticEdge::Restore took the center from the saved, uninverted arc while the
other perma points are Y inverted.
"""

import os
import tempfile
import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticArcTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticArc")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)
        self.fileName = None

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        if self.fileName and os.path.exists(self.fileName):
            os.remove(self.fileName)

    def assertVectorAlmostEqual(self, actual, expected):
        self.assertLess((actual - expected).Length, 1e-7, "%s != %s" % (actual, expected))

    def circleEdges(self):
        return [e for e in self.view.getVisibleEdges() if isinstance(e.Curve, Part.Circle)]

    def reload(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "TDCosmeticArc.FCStd")
        self.doc.saveAs(self.fileName)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(self.fileName)
        self.view = self.doc.getObject("View")
        self.doc.recompute()

    def testReloadedArcKeepsCenter(self):
        self.view.makeCosmeticCircleArc(FreeCAD.Vector(10, 20, 0), 5.0, 0.0, 90.0)
        self.view.makeCosmeticCircle(FreeCAD.Vector(-10, 20, 0), 3.0)
        self.doc.recompute()
        arc, circle = self.view.CosmeticEdges
        self.assertVectorAlmostEqual(arc.Center, FreeCAD.Vector(10, 20, 0))
        self.assertVectorAlmostEqual(circle.Center, FreeCAD.Vector(-10, 20, 0))
        drawn = [(e.Curve.Center, e.Length) for e in self.circleEdges()]

        self.reload()
        arc, circle = self.view.CosmeticEdges
        self.assertVectorAlmostEqual(arc.Center, FreeCAD.Vector(10, 20, 0))
        self.assertAlmostEqual(arc.Radius, 5.0)
        self.assertVectorAlmostEqual(circle.Center, FreeCAD.Vector(-10, 20, 0))
        self.assertAlmostEqual(circle.Radius, 3.0)
        # the drawn geometry was already right and stays so
        reloaded = [(e.Curve.Center, e.Length) for e in self.circleEdges()]
        self.assertEqual(len(reloaded), 2)
        for (center, length), (center2, length2) in zip(drawn, reloaded):
            self.assertVectorAlmostEqual(center2, center)
            self.assertAlmostEqual(length2, length)


if __name__ == "__main__":
    unittest.main()
