# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the constraints that SketchObject.split() and trim() give to the new pieces.

The pieces must keep the meaning of the constraints of the original curve: solving the sketch
right after the operation must not move any geometry.
"""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchSplitTrimConstraints(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchSplitTrimConstraints")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _points(self):
        result = []
        for geo in self.sketch.Geometry:
            if isinstance(geo, Part.Point):
                result.append(V(geo.X, geo.Y, geo.Z))
            elif hasattr(geo, "StartPoint"):
                result.extend((geo.StartPoint, geo.EndPoint))
            else:
                result.append(geo.value(geo.FirstParameter))
        return result

    def _assertSolveKeepsGeometry(self):
        before = self._points()
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(self.sketch.MalformedConstraints, [])
        after = self._points()
        self.assertEqual(len(before), len(after))
        for a, b in zip(before, after):
            self.assertLess((a - b).Length, 1e-6, "solving moved the geometry")

    def _edgeDistances(self):
        return [
            (c.First, c.Second, c.Value)
            for c in self.sketch.Constraints
            if c.Type == "Distance" and c.FirstPos == 0 and c.SecondPos == 0
        ]

    def testSplitLineKeepsCircleToLineDistance(self):
        self.sketch.addGeometry(Part.LineSegment(V(-10, 0, 0), V(10, 0, 0)))  # 0
        self.sketch.addGeometry(Part.Circle(V(0, 8, 0), V(0, 0, 1), 3))  # 1
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 1, 0, 5.0))
        self.doc.recompute()

        self.sketch.split(0, V(-2, 0, 0))

        self.assertEqual(len(self.sketch.Geometry), 3)
        self.assertEqual(self._edgeDistances(), [(1, 0, 5.0)])
        self._assertSolveKeepsGeometry()
        self.assertAlmostEqual(self.sketch.Geometry[0].StartPoint.x, -10.0)
        self.assertAlmostEqual(self.sketch.Geometry[2].EndPoint.x, 10.0)

    def testSplitArcKeepsArcToLineDistance(self):
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 6), 0.3, 2.8)
        self.sketch.addGeometry(arc)  # 0
        self.sketch.addGeometry(Part.LineSegment(V(-10, 9, 0), V(10, 9, 0)))  # 1
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 1, 3.0))
        self.doc.recompute()

        self.sketch.split(0, arc.value(1.5))

        self.assertEqual(self._edgeDistances(), [(0, 1, 3.0)])
        self._assertSolveKeepsGeometry()

    def testSplitArcKeepsArcToCircleDistance(self):
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 6), 0.3, 2.8)
        self.sketch.addGeometry(arc)  # 0
        self.sketch.addGeometry(Part.Circle(V(0, 12, 0), V(0, 0, 1), 3))  # 1
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 1, 3.0))
        self.doc.recompute()

        self.sketch.split(0, arc.value(1.5))

        self.assertEqual(self._edgeDistances(), [(0, 1, 3.0)])
        self._assertSolveKeepsGeometry()

    def testTrimArcInTwoKeepsArcToLineDistance(self):
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 6), 0.3, 2.8)
        self.sketch.addGeometry(arc)  # 0
        self.sketch.addGeometry(Part.LineSegment(V(-10, 9, 0), V(10, 9, 0)))  # 1
        self.sketch.addGeometry(Part.LineSegment(V(-1, -10, 0), V(-1, 10, 0)))  # 2
        self.sketch.addGeometry(Part.LineSegment(V(1, -10, 0), V(1, 10, 0)))  # 3
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 1, 3.0))
        self.doc.recompute()

        # remove the middle of the arc, between the two vertical lines
        self.sketch.trim(0, arc.value(math.pi / 2))

        self.assertEqual(len(self.sketch.Geometry), 5)
        self.assertEqual(self._edgeDistances(), [(0, 1, 3.0)])
        self._assertSolveKeepsGeometry()

    def testSplitLineKeepsItsLength(self):
        # control: a length is turned into the distance between the outer end points
        self.sketch.addGeometry(Part.LineSegment(V(-10, 0, 0), V(10, 0, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 20.0))
        self.doc.recompute()

        self.sketch.split(0, V(-2, 0, 0))

        lengths = [
            (c.First, c.FirstPos, c.Second, c.SecondPos)
            for c in self.sketch.Constraints
            if c.Type == "Distance"
        ]
        self.assertEqual(lengths, [(0, 1, 1, 2)])
        self._assertSolveKeepsGeometry()
