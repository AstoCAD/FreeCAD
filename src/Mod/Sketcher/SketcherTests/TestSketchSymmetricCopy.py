# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the constraints that SketchObject.addSymmetric() copies onto the mirrored geometry.

The mirrored geometry is placed exactly; the copied constraints must hold on it, so solving
right after the operation must not move anything.
"""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchSymmetricCopy(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchSymmetricCopy")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _endPoints(self):
        result = []
        for g in self.sketch.Geometry:
            if isinstance(g, Part.Point):
                p = V(g.X, g.Y, g.Z)
                result.append((p, p))
            else:
                result.append((g.StartPoint, g.EndPoint))
        return result

    def _assertSolveKeepsGeometry(self):
        before = self._endPoints()
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(self.sketch.MalformedConstraints, [])
        for (s0, e0), (s1, e1) in zip(before, self._endPoints()):
            self.assertLess((s0 - s1).Length, 1e-6, "solving moved the geometry")
            self.assertLess((e0 - e1).Length, 1e-6, "solving moved the geometry")

    def _mirrorLineWithAngle(self, reference):
        self.sketch.addGeometry(Part.LineSegment(V(2, 1, 0), V(6, 4, 0)))  # 0
        self.sketch.addConstraint(Sketcher.Constraint("Angle", 0, math.atan2(3, 4)))
        if reference == "line":
            ref = self.sketch.addGeometry(Part.LineSegment(V(-10, -5, 0), V(10, 15, 0)))
            refPos = 0
        elif reference == "point":
            ref = self.sketch.addGeometry(Part.Point(V(-3, -2, 0)))
            refPos = 1
        else:
            ref, refPos = reference
        self.doc.recompute()
        self.assertEqual(self.sketch.solve(), 0)

        self.sketch.addSymmetric([0], ref, refPos)

        mirrored = self.sketch.Geometry[-1]
        self.assertIsInstance(mirrored, Part.LineSegment)
        angles = [c for c in self.sketch.Constraints if c.Type == "Angle"]
        self.assertEqual(len(angles), 2)
        self.assertEqual(angles[1].First, len(self.sketch.Geometry) - 1)
        direction = mirrored.EndPoint - mirrored.StartPoint
        self.assertAlmostEqual(angles[1].Value, math.atan2(direction.y, direction.x))
        self._assertSolveKeepsGeometry()

    def testLineAngleMirroredAboutSlantedLine(self):
        self._mirrorLineWithAngle("line")

    def testLineAngleMirroredAboutPoint(self):
        self._mirrorLineWithAngle("point")

    def testLineAngleMirroredAboutHorizontalAxis(self):
        self._mirrorLineWithAngle((-1, 0))

    def testLineAngleMirroredAboutVerticalAxis(self):
        self._mirrorLineWithAngle((-2, 0))

    def testLineAngleMirroredAboutOrigin(self):
        self._mirrorLineWithAngle((-1, 1))

    def testArcAngleIsCopiedUnchanged(self):
        # control: the span of an arc does not change with a symmetry
        arc = Part.ArcOfCircle(Part.Circle(V(9, 6, 0), V(0, 0, 1), 2), -math.pi / 2, 0.8)
        self.sketch.addGeometry(arc)  # 0
        span = 0.8 + math.pi / 2
        self.sketch.addConstraint(Sketcher.Constraint("Angle", 0, span))
        ref = self.sketch.addGeometry(Part.LineSegment(V(-10, -5, 0), V(10, 15, 0)))
        self.doc.recompute()
        self.assertEqual(self.sketch.solve(), 0)

        self.sketch.addSymmetric([0], ref, 0)

        angles = [c for c in self.sketch.Constraints if c.Type == "Angle"]
        self.assertEqual(len(angles), 2)
        self.assertAlmostEqual(angles[1].Value, span)
        self._assertSolveKeepsGeometry()
