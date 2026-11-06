# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cosmetic arcs keep their center through save and reload.

A reloaded cosmetic arc reported its center mirrored about the view X axis
(CosmeticEdge.Center gave (10, -20) for an arc made at (10, 20)), because
CosmeticEdge::Restore took the center from the saved, uninverted arc while the
other perma points are Y inverted.

Setting CosmeticEdge.Radius or .Center of an arc replaced it with a full
circle.
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

    def drawnArc(self, tag):
        """Geometry of the drawn cosmetic edge (center, radius, length, closed, end points)."""
        self.view.touch()
        self.doc.recompute()
        index = [ce.Tag for ce in self.view.CosmeticEdges].index(tag)
        edges = self.circleEdges()
        self.assertEqual(len(edges), len(self.view.CosmeticEdges))
        edge = edges[index]
        return (edge.Curve.Center, edge.Curve.Radius, edge.Length, edge.isClosed(),
                edge.Vertexes[0].Point, edge.Vertexes[-1].Point)

    def assertSameDrawing(self, actual, expected):
        self.assertVectorAlmostEqual(actual[0], expected[0])
        self.assertAlmostEqual(actual[1], expected[1])
        self.assertAlmostEqual(actual[2], expected[2])
        self.assertEqual(actual[3], expected[3])
        self.assertVectorAlmostEqual(actual[4], expected[4])
        self.assertVectorAlmostEqual(actual[5], expected[5])

    def testSetRadiusKeepsArc(self):
        tag = self.view.makeCosmeticCircleArc(FreeCAD.Vector(10, 20, 0), 5.0, 0.0, 90.0)
        edge = self.view.getCosmeticEdge(tag)
        edge.Radius = 8.0
        self.assertAlmostEqual(edge.Radius, 8.0)
        self.assertVectorAlmostEqual(edge.Center, FreeCAD.Vector(10, 20, 0))
        changed = self.drawnArc(tag)
        self.view.removeCosmeticEdge(tag)
        expected = self.drawnArc(
            self.view.makeCosmeticCircleArc(FreeCAD.Vector(10, 20, 0), 8.0, 0.0, 90.0))
        self.assertFalse(changed[3], "the arc became a full circle")
        self.assertSameDrawing(changed, expected)

    def testSetCenterKeepsArc(self):
        tag = self.view.makeCosmeticCircleArc(FreeCAD.Vector(10, 20, 0), 5.0, 30.0, 150.0)
        edge = self.view.getCosmeticEdge(tag)
        edge.Center = FreeCAD.Vector(-15, 25, 0)
        self.assertAlmostEqual(edge.Radius, 5.0)
        self.assertVectorAlmostEqual(edge.Center, FreeCAD.Vector(-15, 25, 0))
        changed = self.drawnArc(tag)
        self.view.removeCosmeticEdge(tag)
        expected = self.drawnArc(
            self.view.makeCosmeticCircleArc(FreeCAD.Vector(-15, 25, 0), 5.0, 30.0, 150.0))
        self.assertFalse(changed[3], "the arc became a full circle")
        self.assertSameDrawing(changed, expected)

    def testSetRadiusAndCenterOfCircleControl(self):
        tag = self.view.makeCosmeticCircle(FreeCAD.Vector(10, 20, 0), 5.0)
        edge = self.view.getCosmeticEdge(tag)
        edge.Radius = 8.0
        edge.Center = FreeCAD.Vector(-15, 25, 0)
        changed = self.drawnArc(tag)
        self.view.removeCosmeticEdge(tag)
        expected = self.drawnArc(self.view.makeCosmeticCircle(FreeCAD.Vector(-15, 25, 0), 8.0))
        self.assertTrue(changed[3])
        self.assertSameDrawing(changed, expected)


if __name__ == "__main__":
    unittest.main()
