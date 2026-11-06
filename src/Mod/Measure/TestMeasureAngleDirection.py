# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure::MeasureAngle reports an error for elements without a direction."""

import unittest

import FreeCAD as App
import Measure  # noqa: F401  (registers the measure types)
import Part  # noqa: F401


class TestMeasureAngleDirection(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureAngleDirection")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _angle(self, element1, element2):
        measure = self.doc.addObject("Measure::MeasureAngle", "Angle")
        # Setting the elements recomputes the measurement: it must not raise
        measure.Element1 = (self.box, element1)
        measure.Element2 = (self.box, element2)
        self.doc.recompute()
        return measure

    def testEdgeAndFace(self):
        measure = self._angle("Edge1", "Face2")
        self.assertNotIn("Invalid", measure.State)
        self.assertAlmostEqual(measure.Angle.Value, 90.0, places=6)

    def testVertexHasNoDirection(self):
        for element1, element2 in (("Vertex1", "Face2"), ("Edge1", "Vertex3")):
            with self.subTest(element1=element1, element2=element2):
                measure = self._angle(element1, element2)
                self.assertIn("Invalid", measure.State)


if __name__ == "__main__":
    unittest.main()
