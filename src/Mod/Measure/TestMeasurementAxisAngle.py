# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure.Measurement reports the angle between two circle or cylinder axes as a line angle."""

import math
import unittest

import FreeCAD as App
import Measure
import Part


class TestMeasurementAxisAngle(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementAxisAngle")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _angle(self, shapes, subNames):
        feature = self.doc.addObject("Part::Feature", "Feature")
        feature.Shape = Part.Compound(shapes)
        self.doc.recompute()
        measurement = Measure.Measurement()
        for subName in subNames:
            measurement.addReference3D(feature.Name, subName)
        return measurement.angle()

    @staticmethod
    def _direction(degrees):
        """Unit vector in the YZ plane at the given angle from +Z"""
        radians = math.radians(degrees)
        return App.Vector(0, -math.sin(radians), math.cos(radians))

    def testTwoCircles(self):
        for degrees, expected in ((30, 30), (90, 90), (120, 60), (150, 30), (180, 0)):
            with self.subTest(degrees=degrees):
                circles = [
                    Part.makeCircle(1),
                    Part.makeCircle(2, App.Vector(0, 0, 5), self._direction(degrees)),
                ]
                angle = self._angle(circles, ["Edge1", "Edge2"])
                self.assertAlmostEqual(angle, expected, places=6)

    def testTwoCylinders(self):
        for degrees, expected in ((45, 45), (135, 45), (170, 10)):
            with self.subTest(degrees=degrees):
                cylinders = [
                    Part.makeCylinder(1, 2),
                    Part.makeCylinder(1, 2, App.Vector(0, 0, 10), self._direction(degrees)),
                ]
                faces = [cylinder.Faces[0] for cylinder in cylinders]
                angle = self._angle(faces, ["Face1", "Face2"])
                self.assertAlmostEqual(angle, expected, places=6)

    def testCircleToCylinder(self):
        shapes = [
            Part.makeCylinder(1, 2).Faces[0],
            Part.makeCircle(2, App.Vector(0, 0, 10), self._direction(160)),
        ]
        angle = self._angle(shapes, ["Face1", "Edge4"])
        self.assertAlmostEqual(angle, 20, places=6)


if __name__ == "__main__":
    unittest.main()
