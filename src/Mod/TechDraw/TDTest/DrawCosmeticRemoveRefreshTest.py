# SPDX-License-Identifier: LGPL-2.1-or-later
"""Removing cosmetics updates the drawn geometry; non-finite input is refused.

removeCosmeticEdge, removeCenterLine, clearCosmeticEdges, clearCenterLines and
clearCosmeticVertices left the drawn geometry unchanged until the next
recompute (removeCosmeticVertex already refreshed it): getVisibleEdges() still
listed the removed edge and the selection names of the remaining cosmetics
were off.

The makeCosmetic* methods accepted infinite or NaN coordinates, radii and
angles: makeCosmeticCircle with an infinite radius crashed with an access
violation, an arc with a NaN angle made the view Invalid on the next recompute.
The CosmeticEdge Radius, Center, Start and End setters accepted them too, and
the next recompute of the view crashed with an access violation.
"""

import math
import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

Vector = FreeCAD.Vector


class DrawCosmeticRemoveRefreshTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticRemoveRefresh")
        box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def edgeCount(self):
        return len(self.view.getVisibleEdges())

    def selectedTag(self, name):
        """Tag of the cosmetic edge or center line drawn as name."""
        try:
            return self.view.getCosmeticEdgeBySelection(name).Tag
        except ValueError:
            return self.view.getCenterLineBySelection(name).Tag

    def assertSameAfterRecompute(self):
        edges = self.edgeCount()
        vertexes = len(self.view.getVisibleVertexes())
        self.view.touch()
        self.doc.recompute()
        self.assertEqual(self.edgeCount(), edges)
        self.assertEqual(len(self.view.getVisibleVertexes()), vertexes)

    def testRemoveCosmeticEdge(self):
        first = self.view.makeCosmeticLine(Vector(0, 0, 0), Vector(5, 5, 0))
        second = self.view.makeCosmeticLine(Vector(0, 5, 0), Vector(5, 0, 0))
        self.assertEqual(self.edgeCount(), 6)
        self.view.removeCosmeticEdge(first)
        self.assertEqual(self.edgeCount(), 5)
        self.assertEqual(self.selectedTag("Edge4"), second)
        self.assertSameAfterRecompute()

    def testRemoveCenterLine(self):
        edge = self.view.makeCosmeticLine(Vector(0, 0, 0), Vector(5, 5, 0))
        line = self.view.makeCenterLine(["Edge0", "Edge2"], 2)
        self.assertEqual(self.edgeCount(), 6)
        self.view.removeCenterLine(line)
        self.assertEqual(self.edgeCount(), 5)
        self.assertEqual(self.selectedTag("Edge4"), edge)
        self.assertSameAfterRecompute()

    def testRemoveCosmeticEdgeKeepsCenterLine(self):
        first = self.view.makeCosmeticLine(Vector(0, 0, 0), Vector(5, 5, 0))
        line = self.view.makeCenterLine(["Edge0", "Edge2"], 2)
        second = self.view.makeCosmeticLine(Vector(0, 5, 0), Vector(5, 0, 0))
        self.view.removeCosmeticEdge(first)
        self.assertEqual(self.edgeCount(), 6)
        self.assertEqual({self.selectedTag("Edge4"), self.selectedTag("Edge5")}, {line, second})
        self.assertSameAfterRecompute()

    def testClearCosmetics(self):
        vertexes = len(self.view.getVisibleVertexes())
        self.view.makeCosmeticLine(Vector(0, 0, 0), Vector(5, 5, 0))
        self.view.makeCenterLine(["Edge0", "Edge2"], 2)
        self.view.makeCosmeticVertex(Vector(1, 2, 0))
        self.assertEqual(self.edgeCount(), 6)
        self.assertEqual(len(self.view.getVisibleVertexes()), vertexes + 1)

        self.view.clearCosmeticEdges()
        self.assertEqual(self.edgeCount(), 5)
        self.view.clearCenterLines()
        self.assertEqual(self.edgeCount(), 4)
        self.view.clearCosmeticVertices()
        self.assertEqual(len(self.view.getVisibleVertexes()), vertexes)
        self.assertSameAfterRecompute()

    def testRemoveFromViewWithoutGeometry(self):
        empty = self.doc.addObject("TechDraw::DrawViewPart", "Empty")
        self.page.addView(empty)
        empty.removeCosmeticEdge("none")
        empty.removeCenterLine("none")
        empty.clearCosmeticEdges()
        empty.clearCenterLines()
        empty.clearCosmeticVertices()
        self.assertEqual(len(empty.getVisibleEdges()), 0)


class DrawCosmeticNonFiniteInputTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticNonFiniteInput")
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def calls(self, value):
        """Every maker, with value in each of its numeric arguments in turn."""
        view = self.view
        origin = Vector(0, 0, 0)
        point = Vector(value, 1, 0)
        return {
            "makeCosmeticVertex": lambda: view.makeCosmeticVertex(Vector(1, value, 0)),
            "makeCosmeticVertex3d": lambda: view.makeCosmeticVertex3d(Vector(1, 2, value)),
            "makeCosmeticLine start": lambda: view.makeCosmeticLine(point, Vector(5, 5, 0)),
            "makeCosmeticLine end": lambda: view.makeCosmeticLine(origin, Vector(5, 5, value)),
            "makeCosmeticLine3D": lambda: view.makeCosmeticLine3D(point, Vector(5, 5, 0)),
            "makeCosmeticCircle center": lambda: view.makeCosmeticCircle(point, 2.0),
            "makeCosmeticCircle radius": lambda: view.makeCosmeticCircle(origin, value),
            "makeCosmeticCircleArc center": lambda: view.makeCosmeticCircleArc(
                point, 2.0, 0.0, 90.0
            ),
            "makeCosmeticCircleArc radius": lambda: view.makeCosmeticCircleArc(
                origin, value, 0.0, 90.0
            ),
            "makeCosmeticCircleArc start": lambda: view.makeCosmeticCircleArc(
                origin, 2.0, value, 90.0
            ),
            "makeCosmeticCircleArc end": lambda: view.makeCosmeticCircleArc(
                origin, 2.0, 0.0, value
            ),
            "makeCosmeticCircle3d center": lambda: view.makeCosmeticCircle3d(point, 2.0),
            "makeCosmeticCircle3d radius": lambda: view.makeCosmeticCircle3d(origin, value),
            "makeCosmeticCircleArc3d center": lambda: view.makeCosmeticCircleArc3d(
                point, 2.0, 0.0, 90.0
            ),
            "makeCosmeticCircleArc3d radius": lambda: view.makeCosmeticCircleArc3d(
                origin, value, 0.0, 90.0
            ),
            "makeCosmeticCircleArc3d start": lambda: view.makeCosmeticCircleArc3d(
                origin, 2.0, value, 90.0
            ),
            "makeCosmeticCircleArc3d end": lambda: view.makeCosmeticCircleArc3d(
                origin, 2.0, 0.0, value
            ),
        }

    def assertRefused(self, value):
        for name, call in self.calls(value).items():
            with self.subTest(call=name, value=value):
                with self.assertRaises(ValueError):
                    call()
        self.assertEqual(self.view.CosmeticEdges, [])
        self.assertEqual(self.view.CosmeticVertexes, [])
        self.doc.recompute()
        self.assertNotIn("Invalid", self.view.State)

    def testNaNIsRefused(self):
        self.assertRefused(math.nan)

    def testInfinityIsRefused(self):
        self.assertRefused(math.inf)
        self.assertRefused(-math.inf)

    def testFiniteValuesStillWork(self):
        calls = self.calls(3.0)
        for name, call in calls.items():
            with self.subTest(call=name):
                self.assertTrue(call())
        self.view.makeCosmeticCircleArc(Vector(0, 0, 0), 2.0, -90.0, 450.0)
        self.view.makeCosmeticLine(Vector(-500, 0, 0), Vector(500, -1e-3, 0))
        self.doc.recompute()
        self.assertEqual(len(self.view.CosmeticEdges) + len(self.view.CosmeticVertexes),
                         len(calls) + 2)
        self.assertNotIn("Invalid", self.view.State)

    def testSettersRefuseNonFiniteValues(self):
        """CosmeticEdge.Radius/Center/Start/End crashed the next recompute when not finite."""
        view = self.view
        circle = view.getCosmeticEdge(view.makeCosmeticCircle(Vector(1, 2, 0), 5.0))
        arc = view.getCosmeticEdge(view.makeCosmeticCircleArc(Vector(1, 2, 0), 5.0, 0.0, 90.0))
        line = view.getCosmeticEdge(view.makeCosmeticLine(Vector(1, 2, 0), Vector(5, 6, 0)))
        for value in (math.nan, math.inf, -math.inf):
            for name, edge, attribute, newValue in (
                ("circle", circle, "Radius", value),
                ("circle", circle, "Center", Vector(1, value, 0)),
                ("arc", arc, "Radius", value),
                ("arc", arc, "Center", Vector(value, 2, 0)),
                ("line", line, "Start", Vector(value, 2, 0)),
                ("line", line, "End", Vector(5, 6, value)),
            ):
                with self.subTest(edge=name, attribute=attribute, value=value):
                    with self.assertRaises(ValueError):
                        setattr(edge, attribute, newValue)
        for edge in (circle, arc):
            self.assertAlmostEqual(edge.Radius, 5.0)
            self.assertEqual(edge.Center, Vector(1, 2, 0))
        self.assertEqual(line.Start, Vector(1, 2, 0))
        self.assertEqual(line.End, Vector(5, 6, 0))
        view.touch()
        self.doc.recompute()
        self.assertNotIn("Invalid", view.State)
        # finite values are still accepted
        circle.Radius = 4.0
        arc.Center = Vector(-3, 4, 0)
        line.End = Vector(7, 8, 0)
        view.touch()
        self.doc.recompute()
        self.assertNotIn("Invalid", view.State)
        self.assertAlmostEqual(circle.Radius, 4.0)
        self.assertEqual(arc.Center, Vector(-3, 4, 0))
        self.assertEqual(line.End, Vector(7, 8, 0))


if __name__ == "__main__":
    unittest.main()
