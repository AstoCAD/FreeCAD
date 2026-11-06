# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measurements of the elements of a link array (App::LinkElement sub-objects)."""

import unittest

import FreeCAD as App
import Measure  # noqa: F401  (registers the measure types)
import Part  # noqa: F401


class TestMeasureLinkElement(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureLinkElement")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.array = self.doc.addObject("App::Link", "Array")
        self.array.LinkedObject = self.box

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _makeArray(self, showElement):
        self.array.ShowElement = showElement
        self.array.ElementCount = 3
        self.doc.recompute()
        placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        if showElement:
            self.array.ElementList[1].Placement = placement
        else:
            placements = list(self.array.PlacementList)
            placements[1] = placement
            self.array.PlacementList = placements
        self.doc.recompute()

    def _measure(self, typeName, assign):
        measure = self.doc.addObject(typeName, "Measure")
        assign(measure)
        self.doc.recompute()
        self.assertNotIn("Invalid", measure.State)
        return measure

    def _checkElementOne(self, prefix):
        area = self._measure(
            "Measure::MeasureArea",
            lambda m: setattr(m, "Elements", [(self.array, prefix + "Face1")]),
        )
        self.assertAlmostEqual(area.Area.Value, 100.0, places=6)

        length = self._measure(
            "Measure::MeasureLength",
            lambda m: setattr(m, "Elements", [(self.array, prefix + "Edge1")]),
        )
        self.assertAlmostEqual(length.Length.Value, 10.0, places=6)

        position = self._measure(
            "Measure::MeasurePosition",
            lambda m: setattr(m, "Element", (self.array, prefix + "Vertex1")),
        )
        expected = self.box.Shape.Vertexes[0].Point + App.Vector(50, 0, 0)
        self.assertTrue(position.Position.isEqual(expected, 1e-6), str(position.Position))

        def assignDistance(m):
            m.Element1 = (self.array, prefix + "Vertex1")
            m.Element2 = (self.box, "Vertex1")

        distance = self._measure("Measure::MeasureDistance", assignDistance)
        self.assertAlmostEqual(distance.Distance.Value, 50.0, places=6)

    def testShownElementsByIndex(self):
        self._makeArray(True)
        self._checkElementOne("1.")

    def testShownElementsByName(self):
        self._makeArray(True)
        self._checkElementOne(self.array.ElementList[1].Name + ".")

    def testHiddenElements(self):
        self._makeArray(False)
        self._checkElementOne("1.")


if __name__ == "__main__":
    unittest.main()
