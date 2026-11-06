# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the constraints kept by SketchObject.join().

join() replaces the two curves by one B-spline that takes the index of the first curve. The
constraints on the free ends must follow the ends of the spline, constraints of other geometry
must not move, and constraints that no longer apply to the spline must be dropped instead of
being left malformed.
"""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchJoinCurves(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchJoinCurves")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _line(self, a, b):
        return self.sketch.addGeometry(Part.LineSegment(V(*a), V(*b)))

    def _constraints(self, ctype):
        return [c for c in self.sketch.Constraints if c.Type == ctype]

    def _assertValid(self):
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(self.sketch.MalformedConstraints, [])

    def testFreeEndOfSecondCurveKeepsItsConstraint(self):
        self._line((0, 0, 0), (4, 0, 0))  # 0
        self._line((4, 0, 0), (10, 0, 0))  # 1
        self._line((10, 0, 0), (10, 5, 0))  # 2
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
        self.doc.recompute()

        self.sketch.join(0, 2, 1, 1)

        # line 2 is now geometry 1, its start stays on the end of the spline
        self.assertIsInstance(self.sketch.Geometry[0], Part.BSplineCurve)
        coincidents = [(c.First, c.FirstPos, c.Second, c.SecondPos) for c in self._constraints("Coincident")]
        self.assertTrue(
            (0, 2, 1, 1) in coincidents or (1, 1, 0, 2) in coincidents,
            coincidents,
        )
        self._assertValid()

    def testConstraintsOfFollowingGeometryAreNotMoved(self):
        self._line((0, 0, 0), (4, 0, 0))  # 0
        self._line((4, 0, 0), (10, 0, 0))  # 1
        self._line((10, 2, 0), (10, 5, 0))  # 2, renumbered to 1 by the join
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceX", 2, 1, 2, 2, 0.0))
        self.doc.recompute()

        self.sketch.join(0, 2, 1, 1)

        distances = [(c.First, c.FirstPos, c.Second, c.SecondPos) for c in self._constraints("DistanceX")]
        self.assertEqual(distances, [(1, 1, 1, 2)])
        self._assertValid()
        self.assertAlmostEqual(self.sketch.Geometry[1].StartPoint.y, 2.0, places=6)

    def testFreeEndOfFirstCurveFollowsTheSpline(self):
        # join at the start of the first curve: its end becomes the start of the spline
        self._line((4, 0, 0), (0, 0, 0))  # 0, reversed
        self._line((4, 0, 0), (10, 0, 0))  # 1
        self._line((0, 0, 0), (0, 5, 0))  # 2
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 2, 1))
        self.doc.recompute()

        self.sketch.join(0, 1, 1, 1)

        coincidents = [(c.First, c.FirstPos, c.Second, c.SecondPos) for c in self._constraints("Coincident")]
        self.assertEqual(coincidents, [(0, 1, 1, 1)])
        self._assertValid()
        spline = self.sketch.Geometry[0]
        self.assertAlmostEqual((spline.StartPoint - V(0, 0, 0)).Length, 0.0, places=6)
        self.assertAlmostEqual((spline.EndPoint - V(10, 0, 0)).Length, 0.0, places=6)

    def testEdgeAndJointConstraintsAreDropped(self):
        self._line((0, 0, 0), (4, 0, 0))  # 0
        self._line((4, 0, 0), (10, 3, 0))  # 1
        self._line((4, 0, 0), (4, -5, 0))  # 2, also at the joint
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 2, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 4.0))
        self.doc.recompute()

        self.sketch.join(0, 2, 1, 1)

        self.assertEqual(self._constraints("Horizontal"), [])
        self.assertEqual(self._constraints("Distance"), [])
        self.assertEqual(self._constraints("Coincident"), [])
        self._assertValid()
        spline = self.sketch.Geometry[0]
        self.assertAlmostEqual((spline.EndPoint - V(10, 3, 0)).Length, 0.0, places=6)
        self.assertAlmostEqual((self.sketch.Geometry[1].StartPoint - V(4, 0, 0)).Length, 0.0, places=6)

    def testConicInternalGeometryIsReleased(self):
        arc = Part.ArcOfEllipse(Part.Ellipse(V(0, 0, 0), 12, 6), 0.2, 2.9)
        self.sketch.addGeometry(arc)  # 0
        start = arc.StartPoint
        self._line((start.x, start.y, 0), (start.x, start.y - 5, 0))  # 1
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 1))
        self.sketch.exposeInternalGeometry(0)
        self.doc.recompute()
        self.assertTrue(self._constraints("InternalAlignment"))

        self.sketch.join(0, 1, 1, 1)

        # the axes and foci of the ellipse stay as construction geometry, no longer aligned
        self.assertIsInstance(self.sketch.Geometry[0], Part.BSplineCurve)
        for c in self._constraints("InternalAlignment"):
            self.assertEqual(c.Second, 0)
            self.assertIsInstance(self.sketch.Geometry[c.First], (Part.Circle, Part.Point))
        self._assertValid()

    def testPointOnFirstCurveIsKept(self):
        self._line((0, 0, 0), (4, 0, 0))  # 0
        self._line((4, 0, 0), (10, 0, 0))  # 1
        self.sketch.addGeometry(Part.Point(V(2, 0, 0)))  # 2
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("PointOnObject", 2, 1, 0))
        self.doc.recompute()

        self.sketch.join(0, 2, 1, 1)

        onObject = [(c.First, c.FirstPos, c.Second) for c in self._constraints("PointOnObject")]
        self.assertEqual(onObject, [(1, 1, 0)])
        self._assertValid()

    def testSecondCurveBeforeFirstCurve(self):
        # The GUI passes the curves in selection order, so geoId2 can be the lower index.
        # Deleting it moves the spline down: the construction flag and the exposed control
        # points must go to the spline, not to the geometry that now has the old index.
        self.sketch.addGeometry(Part.LineSegment(V(0, 10, 0), V(5, 10, 0)), True)  # 0
        self._line((0, 0, 0), (4, 0, 0))  # 1
        self._line((4, 0, 0), (10, 0, 0))  # 2
        self.sketch.addGeometry(Part.LineSegment(V(0, 20, 0), V(5, 20, 0)), True)  # 3
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
        self.doc.recompute()

        self.sketch.join(2, 1, 1, 2)

        self.assertIsInstance(self.sketch.Geometry[1], Part.BSplineCurve)
        self.assertFalse(self.sketch.getConstruction(1))
        # the old line 3 is geometry 2 now and stays construction
        self.assertIsInstance(self.sketch.Geometry[2], Part.LineSegment)
        self.assertTrue(self.sketch.getConstruction(2))
        self.assertAlmostEqual((self.sketch.Geometry[2].StartPoint - V(0, 20, 0)).Length, 0.0)
        # the control points of the spline are exposed
        poles = [c for c in self._constraints("InternalAlignment") if c.Second == 1]
        self.assertTrue(poles)
        self._assertValid()

    def _joinArcAndLine(self, arc, arcFirst):
        # the sketch end point of the arc (geometry 0) is joined to a line going down from it
        self.sketch.addGeometry(arc)  # 0
        start = self.sketch.getPoint(0, 1)
        end = self.sketch.getPoint(0, 2)
        lineEnd = V(end.x, end.y - 5, 0)
        if arcFirst:
            self._line((end.x, end.y, 0), (lineEnd.x, lineEnd.y, 0))  # 1
            self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        else:
            self._line((lineEnd.x, lineEnd.y, 0), (end.x, end.y, 0))  # 1
            self.sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 0, 2))
        self.doc.recompute()
        length = arc.length() + 5

        if arcFirst:
            self.sketch.join(0, 2, 1, 1)
            expectedStart, expectedEnd = start, lineEnd
        else:
            self.sketch.join(1, 2, 0, 2)
            expectedStart, expectedEnd = lineEnd, start

        splines = [g for g in self.sketch.Geometry if isinstance(g, Part.BSplineCurve)]
        self.assertEqual(len(splines), 1)
        spline = splines[0]
        self.assertLess((spline.StartPoint - expectedStart).Length, 1e-6)
        self.assertLess((spline.EndPoint - expectedEnd).Length, 1e-6)
        self.assertAlmostEqual(spline.length(), length, places=4)
        self._assertValid()

    def testJoinClockwiseArcOfCircle(self):
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, -1), 5), 0.3, 2.5)
        self._joinArcAndLine(arc, True)

    def testJoinLineToClockwiseArcOfCircle(self):
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, -1), 5), 0.3, 2.5)
        self._joinArcAndLine(arc, False)

    def testJoinClockwiseArcOfEllipse(self):
        arc = Part.ArcOfEllipse(Part.Ellipse(V(0, 0, 0), 6, 3), 0.3, 2.5)
        arc.mirror(V(0, 0, 0), V(1, 0, 0))
        self.assertLess(arc.Axis.z, 0)
        self._joinArcAndLine(arc, True)

    def testJoinCounterClockwiseArcOfCircle(self):
        # control
        arc = Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5), 0.3, 2.5)
        self._joinArcAndLine(arc, True)


if __name__ == "__main__":
    unittest.main()
