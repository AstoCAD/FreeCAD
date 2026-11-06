# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for clockwise (axis -Z) arcs of hyperbola and parabola in a sketch.

The sketch reads every arc of conic as the counter-clockwise arc: the start point of a clockwise
arc is at its last parameter. Solving a sketch with such an arc must not move it.
"""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


def _arcOfHyperbola():
    return Part.ArcOfHyperbola(Part.Hyperbola(V(0, 0, 0), 5, 2), -1.0, 1.2)


def _arcOfParabola():
    return Part.ArcOfParabola(Part.Parabola(V(0, 1, 0), V(0, 0, 0), V(0, 0, 1)), -2, 3)


def _clockwise(arc):
    # mirroring about an in-plane axis turns the arc clockwise (axis -Z)
    arc.mirror(V(0, 0, 0), V(1, 0, 0))
    return arc


class TestSketchReversedConicArcs(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchReversedConicArcs")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _assertOnCurve(self, curve, geometry):
        edge = curve.toShape()
        first, last = geometry.FirstParameter, geometry.LastParameter
        for k in range(9):
            point = geometry.value(first + k * (last - first) / 8)
            self.assertLess(edge.distToShape(Part.Vertex(point))[0], 1e-6, "the arc moved")
        self.assertAlmostEqual(geometry.length(), curve.length(), places=6)

    def _solve(self, arc, clockwise):
        if clockwise:
            _clockwise(arc)
            self.assertLess(arc.Axis.z, 0)
        self.sketch.addGeometry(arc)
        start = self.sketch.getPoint(0, 1)
        end = self.sketch.getPoint(0, 2)
        # the start point is the one of the counter-clockwise arc
        first, last = (arc.EndPoint, arc.StartPoint) if clockwise else (arc.StartPoint, arc.EndPoint)
        self.assertLess((start - first).Length, 1e-9)
        self.assertLess((end - last).Length, 1e-9)

        self.assertEqual(self.sketch.solve(), 0)

        self._assertOnCurve(arc, self.sketch.Geometry[0])
        self.assertLess((self.sketch.getPoint(0, 1) - start).Length, 1e-6)
        self.assertLess((self.sketch.getPoint(0, 2) - end).Length, 1e-6)

    def testSolveKeepsClockwiseArcOfHyperbola(self):
        self._solve(_arcOfHyperbola(), True)

    def testSolveKeepsClockwiseArcOfParabola(self):
        self._solve(_arcOfParabola(), True)

    def testSolveKeepsArcOfHyperbola(self):
        # control
        self._solve(_arcOfHyperbola(), False)

    def testSolveKeepsArcOfParabola(self):
        # control
        self._solve(_arcOfParabola(), False)

    def _recomputeWithFixedStart(self, arc):
        _clockwise(arc)
        self.sketch.addGeometry(arc)  # 0
        start = self.sketch.getPoint(0, 1)
        self.sketch.addGeometry(Part.Point(start))  # 1
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 1, 0, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Block", 1))

        self.doc.recompute()

        self.assertNotIn("Invalid", self.sketch.State)
        self.assertEqual(self.sketch.MalformedConstraints, [])
        self._assertOnCurve(arc, self.sketch.Geometry[0])
        self.assertLess((self.sketch.getPoint(0, 1) - start).Length, 1e-6)

    def testRecomputeKeepsClockwiseArcOfHyperbolaWithFixedStart(self):
        self._recomputeWithFixedStart(_arcOfHyperbola())

    def testRecomputeKeepsClockwiseArcOfParabolaWithFixedStart(self):
        self._recomputeWithFixedStart(_arcOfParabola())


if __name__ == "__main__":
    unittest.main()
