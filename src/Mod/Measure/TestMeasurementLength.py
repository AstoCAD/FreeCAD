# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure.Measurement measures the length of edges of every curve type."""

import unittest

import FreeCAD as App
import Measure
import Part


class TestMeasurementLength(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementLength")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def testOffsetCurveEdge(self):
        line = Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).toBSpline()
        edge = Part.OffsetCurve(line, 2.0, App.Vector(0, 0, 1)).toShape()
        feature = self.doc.addObject("Part::Feature", "Feature")
        feature.Shape = edge
        self.doc.recompute()

        measurement = Measure.Measurement()
        measurement.addReference3D(feature.Name, "Edge1")
        self.assertAlmostEqual(measurement.length(), edge.Length, places=6)


if __name__ == "__main__":
    unittest.main()
