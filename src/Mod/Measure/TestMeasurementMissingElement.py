# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure.Measurement must not crash when a referenced element has disappeared."""

import unittest

import FreeCAD as App
import Measure
import Part


class TestMeasurementMissingElement(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementMissingElement")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _measureThenRemoveElements(self, shape, subNames):
        feature = self.doc.addObject("Part::Feature", "Feature")
        feature.Shape = shape
        self.doc.recompute()

        measurement = Measure.Measurement()
        for subName in subNames:
            measurement.addReference3D(feature.Name, subName)

        # The referenced elements disappear after the measurement was set up
        feature.Shape = Part.Compound([Part.Vertex(5, 5, 5)])
        self.doc.recompute()
        return measurement

    def testThreePointAngle(self):
        shape = Part.Compound(
            [Part.Vertex(1, 0, 0), Part.Vertex(0, 0, 0), Part.Vertex(0, 1, 0)]
        )
        measurement = self._measureThenRemoveElements(shape, ["Vertex1", "Vertex2", "Vertex3"])
        with self.assertRaises(ValueError):
            measurement.angle()

    def testTwoLinesAngle(self):
        V = App.Vector
        shape = Part.Compound(
            [Part.makeLine(V(0, 0, 0), V(1, 0, 0)), Part.makeLine(V(0, 0, 0), V(0, 1, 0))]
        )
        measurement = self._measureThenRemoveElements(shape, ["Edge1", "Edge2"])
        with self.assertRaises(ValueError):
            measurement.angle()

    def testParallelLinesDistance(self):
        V = App.Vector
        shape = Part.Compound(
            [Part.makeLine(V(0, 0, 0), V(1, 0, 0)), Part.makeLine(V(0, 1, 0), V(1, 1, 0))]
        )
        measurement = self._measureThenRemoveElements(shape, ["Edge1", "Edge2"])
        with self.assertRaises(ValueError):
            measurement.lineLineDistance()

    def testTwoCirclesAngle(self):
        shape = Part.Compound([Part.makeCircle(1), Part.makeCircle(2, App.Vector(0, 0, 1))])
        measurement = self._measureThenRemoveElements(shape, ["Edge1", "Edge2"])
        with self.assertRaises(ValueError):
            measurement.angle()

    def testCircleRadius(self):
        shape = Part.Compound([Part.makeCircle(1), Part.makeCircle(2, App.Vector(0, 0, 1))])
        measurement = self._measureThenRemoveElements(shape, ["Edge1"])
        with self.assertRaises(ValueError):
            measurement.radius()


class TestMeasurementDeletedObject(unittest.TestCase):
    """The references of a Measurement are dropped when their object is deleted.

    The link property of Measurement has no container, so nothing cleared it:
    measuring after closing the document read the destroyed object.
    """

    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementDeletedObject")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()

    def tearDown(self):
        for name in ("MeasurementDeletedObject", "MeasurementDeletedObject2"):
            if name in App.listDocuments():
                App.closeDocument(name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def testCloseDocument(self):
        measurement = Measure.Measurement()
        measurement.addReference3D(self.box.Name, "Face1")
        self.assertAlmostEqual(measurement.area(), 100.0)
        App.closeDocument(self.doc.Name)
        self.assertEqual(measurement.area(), 0.0)
        self.assertFalse(measurement.has3DReferences())

    def testRemoveObject(self):
        other = self.doc.addObject("Part::Box", "Other")
        self.doc.recompute()
        measurement = Measure.Measurement()
        measurement.addReference3D(self.box.Name, "Face1")
        measurement.addReference3D(other.Name, "Face2")
        self.doc.removeObject(self.box.Name)
        self.assertTrue(measurement.has3DReferences())
        self.assertAlmostEqual(measurement.area(), 100.0)
        self.doc.removeObject(other.Name)
        self.assertFalse(measurement.has3DReferences())

    def testCloseOtherDocument(self):
        doc2 = App.newDocument("MeasurementDeletedObject2")
        box2 = doc2.addObject("Part::Box", "Box2")
        doc2.recompute()
        measurement = Measure.Measurement()
        measurement.addReference3D(box2.Name, "Face1")
        App.closeDocument(doc2.Name)
        self.assertFalse(measurement.has3DReferences())


if __name__ == "__main__":
    unittest.main()
