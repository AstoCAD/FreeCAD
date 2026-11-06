# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the values of driven (reference) angle constraints.

A driven angle is computed from the geometry. It is only defined up to a multiple of 360
degrees, so switching a driving angle to driven must keep its value (e.g. 250 degrees, not
-110 degrees), and the value must keep following the geometry.
"""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestDrivenAngleConstraints(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DrivenAngleConstraints")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _degrees(self, index):
        return math.degrees(self.sketch.Constraints[index].Value)

    def _toDriven(self, index):
        self.assertEqual(self.sketch.solve(), 0)
        self.sketch.setDriving(index, False)
        self.assertEqual(self.sketch.solve(), 0)
        self.assertFalse(self.sketch.Constraints[index].Driving)

    def _arc(self, startDeg, endDeg):
        circle = Part.Circle(V(0, 0, 0), V(0, 0, 1), 10)
        return self.sketch.addGeometry(
            Part.ArcOfCircle(circle, math.radians(startDeg), math.radians(endDeg))
        )

    def _polar(self, deg, length=10):
        return V(length * math.cos(math.radians(deg)), length * math.sin(math.radians(deg)), 0)

    def testArcAngleKeepsValueWhenDriven(self):
        arc = self._arc(0, 250)
        c = self.sketch.addConstraint(Sketcher.Constraint("Angle", arc, math.radians(250)))
        self._toDriven(c)
        self.assertAlmostEqual(self._degrees(c), 250, places=6)

    def testDrivenArcAngleFollowsGeometry(self):
        arc = self._arc(0, 250)
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", arc, 3, -1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("PointOnObject", arc, 1, -1))
        self.sketch.addConstraint(Sketcher.Constraint("Radius", arc, 10))
        c = self.sketch.addConstraint(Sketcher.Constraint("Angle", arc, math.radians(250)))
        self._toDriven(c)
        self.sketch.moveGeometry(arc, 2, self._polar(260))
        self.assertEqual(self.sketch.solve(), 0)
        arcGeo = self.sketch.Geometry[arc]
        rangeDeg = math.degrees(arcGeo.LastParameter - arcGeo.FirstParameter)
        self.assertAlmostEqual(rangeDeg, 260, places=3)
        self.assertAlmostEqual(self._degrees(c), rangeDeg, places=6)

    def testLineAngleKeepsValueWhenDriven(self):
        line = self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), self._polar(200)))
        c = self.sketch.addConstraint(Sketcher.Constraint("Angle", line, math.radians(200)))
        self._toDriven(c)
        self.assertAlmostEqual(self._degrees(c), 200, places=6)

    def testLineLineAngleKeepsValueWhenDriven(self):
        line1 = self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        line2 = self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), self._polar(200)))
        c = self.sketch.addConstraint(
            Sketcher.Constraint("Angle", line1, line2, math.radians(200))
        )
        self._toDriven(c)
        self.assertAlmostEqual(self._degrees(c), 200, places=6)

    def testSmallAnglesUnchanged(self):
        arc = self._arc(30, 120)
        line = self.sketch.addGeometry(Part.LineSegment(V(20, 0, 0), V(20, 0, 0) + self._polar(30)))
        cArc = self.sketch.addConstraint(Sketcher.Constraint("Angle", arc, math.radians(90)))
        cLine = self.sketch.addConstraint(Sketcher.Constraint("Angle", line, math.radians(30)))
        self._toDriven(cArc)
        self._toDriven(cLine)
        self.assertAlmostEqual(self._degrees(cArc), 90, places=6)
        self.assertAlmostEqual(self._degrees(cLine), 30, places=6)


if __name__ == "__main__":
    unittest.main()
