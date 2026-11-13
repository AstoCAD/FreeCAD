# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests that setDatum() takes a datum in the unit of the constraint, or a plain number."""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector
Q = App.Units.Quantity


class TestSketchSetDatumUnits(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchSetDatumUnits")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(0, 5, 0), V(10, 15, 0)))
        self.sketch.addGeometry(Part.Circle(V(30, 0, 0), V(0, 0, 1), 5))
        self.distance = self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
        self.angle = self.sketch.addConstraint(Sketcher.Constraint("Angle", 1, math.pi / 4))
        self.radius = self.sketch.addConstraint(Sketcher.Constraint("Radius", 2, 5.0))
        self.sketch.renameConstraint(self.radius, "r")
        self.doc.recompute()

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _datum(self, constraint, unit):
        return self.sketch.getDatum(constraint).getValueAs(unit).Value

    def testLengthRejectsAngle(self):
        with self.assertRaises(ValueError):
            self.sketch.setDatum(self.distance, Q("30 deg"))
        self.assertAlmostEqual(self._datum(self.distance, "mm"), 10.0)

    def testAngleRejectsLength(self):
        with self.assertRaises(ValueError):
            self.sketch.setDatum(self.angle, Q("10 mm"))
        self.assertAlmostEqual(self._datum(self.angle, "deg"), 45.0)

    def testByNameRejectsWrongUnit(self):
        with self.assertRaises(ValueError):
            self.sketch.setDatum("r", Q("2 deg"))
        self.assertAlmostEqual(self._datum(self.radius, "mm"), 5.0)

    def testMatchingUnitsAndPlainNumbers(self):
        self.sketch.setDatum(self.distance, Q("2 cm"))
        self.assertAlmostEqual(self._datum(self.distance, "mm"), 20.0)
        self.sketch.setDatum(self.distance, 15.0)
        self.assertAlmostEqual(self._datum(self.distance, "mm"), 15.0)
        self.sketch.setDatum(self.distance, Q(12))
        self.assertAlmostEqual(self._datum(self.distance, "mm"), 12.0)

        self.sketch.setDatum(self.angle, Q("60 deg"))
        self.assertAlmostEqual(self._datum(self.angle, "deg"), 60.0)
        self.sketch.setDatum(self.angle, math.pi / 6)
        self.assertAlmostEqual(self._datum(self.angle, "deg"), 30.0)

        self.sketch.setDatum("r", Q("4 mm"))
        self.assertAlmostEqual(self._datum(self.radius, "mm"), 4.0)
