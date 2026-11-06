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

    def _bspline(self):
        poles = [V(-10, 0, 0), V(-5, 6, 0), V(0, 6, 0), V(5, 6, 0), V(10, 0, 0)]
        curve = Part.BSplineCurve()
        curve.buildFromPolesMultsKnots(poles, [4, 1, 4], [0, 0.5, 1], False, 3)
        return curve

    def _trimBSplineStart(self, expose):
        curve = self._bspline()
        self.sketch.addGeometry(curve)  # 0
        self.sketch.addGeometry(Part.LineSegment(V(0, -20, 0), V(0, 20, 0)))  # 1
        if expose:
            self.sketch.exposeInternalGeometry(0)
        self.doc.recompute()

        # remove the part of the spline left of the vertical line
        self.sketch.trim(0, curve.value(curve.parameter(V(-8, 2.5, 0))))

        splines = [g for g in self.sketch.Geometry if isinstance(g, Part.BSplineCurve)]
        self.assertEqual(len(splines), 1)
        self.assertAlmostEqual(splines[0].StartPoint.x, 0.0)
        self.assertLess((splines[0].EndPoint - V(10, 0, 0)).Length, 1e-6)
        self.assertEqual(self.sketch.solve(), 0)

    def testTrimBSplineIsNotCutByItsControlPolygon(self):
        # the circles of the poles must not stop the trim
        self._trimBSplineStart(True)

    def testTrimBSplineWithoutInternalGeometry(self):
        # control
        self._trimBSplineStart(False)

    def testTrimEllipseStopsAtItsAxes(self):
        # unlike the poles of a B-spline, the axes of an ellipse still stop a trim
        self.sketch.addGeometry(Part.Ellipse(V(0, 0, 0), 12, 6))  # 0
        self.sketch.addGeometry(Part.LineSegment(V(5, -20, 0), V(5, 20, 0)))  # 1
        self.sketch.exposeInternalGeometry(0)
        self.doc.recompute()
        internal = len(self.sketch.Geometry) - 2
        majorAxis = [
            c.First
            for c in self.sketch.Constraints
            if c.Type == "InternalAlignment" and c.Second == 0 and c.FirstPos == 0
            and abs(self.sketch.Geometry[c.First].StartPoint.y) < 1e-6
            and abs(self.sketch.Geometry[c.First].EndPoint.y) < 1e-6
        ]
        self.assertEqual(len(majorAxis), 1)

        # remove the piece between the vertical line and the end of the major axis
        self.sketch.trim(0, V(12 * math.cos(0.2), 6 * math.sin(0.2), 0))

        arc = self.sketch.Geometry[0]
        self.assertIsInstance(arc, Part.ArcOfEllipse)
        self.assertLess((arc.StartPoint - V(5, 6 * math.sqrt(1 - (5 / 12) ** 2), 0)).Length, 1e-6)
        self.assertLess((arc.EndPoint - V(12, 0, 0)).Length, 1e-6)
        self.assertEqual(len(self.sketch.Geometry), 2 + internal)
        alignments = [c for c in self.sketch.Constraints if c.Type == "InternalAlignment"]
        self.assertEqual(len(alignments), internal)
        self.assertEqual(self._constraintsBetween(0, majorAxis[0]), [("PointOnObject", 0, 2)])
        self._assertSolveKeepsGeometry()
        self.assertEqual(self.sketch.PartiallyRedundantConstraints, [])

    def _constraintsBetween(self, geoId, otherGeoId):
        return [
            (c.Type, c.First, c.FirstPos)
            for c in self.sketch.Constraints
            if c.Type != "InternalAlignment" and {c.First, c.Second} == {geoId, otherGeoId}
        ]

    def testTrimRotatedArcOfEllipseAtItsMinorAxisHasNoRedundantConstraint(self):
        # The end of the minor axis is already on the curve through the internal alignment: the
        # new end of the arc is kept on the axis, not made coincident with its end point again.
        ellipse = Part.Ellipse(V(0, 0, 0), 12, 6)
        arc = Part.ArcOfEllipse(ellipse, -2.8, 2.8)
        arc.rotate(App.Placement(V(), App.Rotation(V(0, 0, 1), 20)))
        self.sketch.addGeometry(arc)  # 0
        self.sketch.addGeometry(Part.LineSegment(V(5, -20, 0), V(5, 20, 0)))  # 1
        self.sketch.exposeInternalGeometry(0)
        self.doc.recompute()
        minorAxis = [
            c.First
            for c in self.sketch.Constraints
            if c.Type == "InternalAlignment"
            and c.Second == 0
            and isinstance(self.sketch.Geometry[c.First], Part.LineSegment)
            and abs(self.sketch.Geometry[c.First].length() - 12) < 1e-6
        ]
        self.assertEqual(len(minorAxis), 1)
        minorAxisEnds = (
            self.sketch.Geometry[minorAxis[0]].StartPoint,
            self.sketch.Geometry[minorAxis[0]].EndPoint,
        )

        # remove the piece between the end of the minor axis and the end of the arc
        self.sketch.trim(0, arc.value(arc.parameter(V(-11, 2, 0))))

        trimmed = self.sketch.Geometry[0]
        self.assertIsInstance(trimmed, Part.ArcOfEllipse)
        self.assertLess((trimmed.StartPoint - arc.StartPoint).Length, 1e-6)
        # the trim still stops at the end of the minor axis
        self.assertLess(min((trimmed.EndPoint - p).Length for p in minorAxisEnds), 1e-6)
        self.assertEqual(self._constraintsBetween(0, minorAxis[0]), [("PointOnObject", 0, 2)])
        self._assertSolveKeepsGeometry()
        self.assertEqual(self.sketch.RedundantConstraints, [])
        self.assertEqual(self.sketch.PartiallyRedundantConstraints, [])

    def _splitArc(self, arc, splitParameter):
        self.sketch.addGeometry(arc)  # 0
        self.doc.recompute()
        start = self.sketch.getPoint(0, 1)
        end = self.sketch.getPoint(0, 2)
        cut = arc.value(splitParameter)

        self.sketch.split(0, cut)

        self.assertEqual(len(self.sketch.Geometry), 2)
        self._assertSolveKeepsGeometry()
        self.assertAlmostEqual(
            self.sketch.Geometry[0].length() + self.sketch.Geometry[1].length(), arc.length()
        )
        # the first piece keeps the start point, the second one the end point
        for geoId, pos, point in ((0, 1, start), (0, 2, cut), (1, 1, cut), (1, 2, end)):
            self.assertLess((self.sketch.getPoint(geoId, pos) - point).Length, 1e-6)

    def testSplitClockwiseArcOfCircle(self):
        arc = Part.ArcOfCircle(Part.Circle(V(1, 2, 0), V(0, 0, -1), 5), 0.3, 2.5)
        self._splitArc(arc, 1.2)

    def testSplitClockwiseArcOfEllipse(self):
        arc = Part.ArcOfEllipse(Part.Ellipse(V(0, 0, 0), 6, 3), 0.3, 2.5)
        arc.mirror(V(0, 0, 0), V(1, 0, 0))
        self.assertLess(arc.Axis.z, 0)
        self._splitArc(arc, 1.2)

    def testSplitCounterClockwiseArcOfCircle(self):
        # control
        arc = Part.ArcOfCircle(Part.Circle(V(1, 2, 0), V(0, 0, 1), 5), 0.3, 2.5)
        self._splitArc(arc, 1.2)
