# SPDX-License-Identifier: LGPL-2.1-or-later

"""Driven (reference) constraints must follow the geometry.

The solver computes the value of a driven constraint from the geometry after every solve. These
tests change the geometry after switching a constraint to driven and check its new value.
"""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestDrivenConstraintEvaluation(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DrivenConstraintEvaluation")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _line(self, start, end):
        return self.sketch.addGeometry(Part.LineSegment(V(*start), V(*end)))

    def _toDriven(self, index):
        self.assertEqual(self.sketch.solve(), 0)
        self.sketch.setDriving(index, False)
        self.assertEqual(self.sketch.solve(), 0)
        self.assertFalse(self.sketch.Constraints[index].Driving)

    def _direction(self, geoId):
        geo = self.sketch.Geometry[geoId]
        return (geo.EndPoint - geo.StartPoint).normalize()

    def testAngleViaPointFollowsGeometry(self):
        line1 = self._line((0, 0, 0), (10, 0, 0))
        line2 = self._line((10, 0, 0), (10, 10, 0))
        self.sketch.addConstraint(Sketcher.Constraint("Block", line1))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", line1, 2, line2, 1))
        point = self.sketch.addGeometry(Part.Point(V(10, 0, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", point, 1, line1, 2))
        c = self.sketch.addConstraint(
            Sketcher.Constraint("AngleViaPoint", line1, line2, point, 1, math.radians(90))
        )
        self._toDriven(c)
        self.assertAlmostEqual(math.degrees(self.sketch.Constraints[c].Value), 90, places=6)

        self.sketch.moveGeometry(line2, 2, V(20, 10, 0))
        self.assertEqual(self.sketch.solve(), 0)
        d = self._direction(line2)
        expected = math.degrees(math.atan2(d.y, d.x))
        self.assertAlmostEqual(expected, 45, places=3)
        self.assertAlmostEqual(math.degrees(self.sketch.Constraints[c].Value), expected, places=6)

    def testSnellsLawFollowsGeometry(self):
        ray1 = self._line((-10, 10, 0), (0, 0, 0))
        ray2 = self._line((0, 0, 0), (5, -10, 0))
        boundary = self._line((-20, 0, 0), (20, 0, 0))
        self.sketch.addConstraint(Sketcher.Constraint("Block", boundary))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", ray1, 2, ray2, 1))
        self.sketch.addConstraint(Sketcher.Constraint("PointOnObject", ray1, 2, boundary))
        c = self.sketch.addConstraint(
            Sketcher.Constraint("SnellsLaw", ray1, 2, ray2, 1, boundary, 1.5)
        )
        self._toDriven(c)
        self.assertAlmostEqual(self.sketch.Constraints[c].Value, 1.5, places=6)

        self.sketch.moveGeometry(ray1, 1, V(-20, 10, 0))
        self.assertEqual(self.sketch.solve(), 0)
        # n1 * sin(incidence) = n2 * sin(refraction), angles measured from the boundary normal;
        # the boundary is horizontal, so the sines are the x components of the unit directions
        expected = abs(self._direction(ray1).x) / abs(self._direction(ray2).x)
        self.assertNotAlmostEqual(expected, 1.5, places=2)
        self.assertAlmostEqual(self.sketch.Constraints[c].Value, expected, places=6)

    def testSnellsLawNormalIncidenceKeepsValue(self):
        # a ray normal to the boundary defines no ratio; the value must not become 0, then NaN
        ray1 = self._line((-10, 10, 0), (0, 0, 0))
        ray2 = self._line((0, 0, 0), (5, -10, 0))
        boundary = self._line((-20, 0, 0), (20, 0, 0))
        self.sketch.addConstraint(Sketcher.Constraint("Block", boundary))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", ray1, 2, ray2, 1))
        self.sketch.addConstraint(Sketcher.Constraint("PointOnObject", ray1, 2, boundary))
        c = self.sketch.addConstraint(
            Sketcher.Constraint("SnellsLaw", ray1, 2, ray2, 1, boundary, 1.5)
        )
        self._toDriven(c)
        self.sketch.addConstraint(Sketcher.Constraint("Vertical", ray1))
        for _ in range(2):
            self.assertEqual(self.sketch.solve(), 0)
            self.assertTrue(math.isfinite(self.sketch.Constraints[c].Value))
            self.assertAlmostEqual(self.sketch.Constraints[c].Value, 1.5, places=6)

    def testDistanceFollowsGeometry(self):
        # control: constraint types that were already evaluated
        line = self._line((0, 0, 0), (10, 0, 0))
        c = self.sketch.addConstraint(Sketcher.Constraint("Distance", line, 10))
        self._toDriven(c)
        self.sketch.moveGeometry(line, 2, V(20, 0, 0))
        self.assertEqual(self.sketch.solve(), 0)
        self.assertAlmostEqual(
            self.sketch.Constraints[c].Value, self.sketch.Geometry[line].length(), places=6
        )
        self.assertAlmostEqual(self.sketch.Constraints[c].Value, 20, places=6)


if __name__ == "__main__":
    unittest.main()
