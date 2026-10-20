# SPDX-License-Identifier: LGPL-2.1-or-later
"""Whole-object center of mass must include the same placements for all names."""

import unittest

import FreeCAD as App
import Measure
import Part


class TestMeasureShapeFinder(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureShapeFinderRegression")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _checkNames(self, local, inner=None, outer=None):
        # The center follows directly from the box dimensions, independently
        # of the shape extraction used by Measurement.com().
        expected = local.multVec(App.Vector(1, 2, 3))
        if inner is not None:
            expected = inner.multVec(expected)
        if outer is not None:
            expected = outer.multVec(expected)

        for name in ("OrdinarySolid", "HasPointWordSolid", "HasVertexWordSolid"):
            with self.subTest(name=name):
                feature = self.doc.addObject("Part::Feature", name)
                feature.Shape = Part.makeBox(2, 4, 6)
                feature.Placement = local
                if inner is not None:
                    inner_part = self.doc.addObject("App::Part", "Inner")
                    inner_part.addObject(feature)
                    inner_part.Placement = inner
                    if outer is not None:
                        outer_part = self.doc.addObject("App::Part", "Outer")
                        outer_part.addObject(inner_part)
                        outer_part.Placement = outer
                self.doc.recompute()

                measurement = Measure.Measurement()
                try:
                    measurement.addReference3D(feature.Name, "")
                    result = measurement.com()
                    actual = App.Vector(result[0], result[1], result[2])
                    self.assertLess((actual - expected).Length, 1e-7,
                                    f"{name}: got {actual}, expected {expected}")
                finally:
                    measurement.clear()

    def testIdentityPlacement(self):
        self._checkNames(App.Placement())

    def testLocalRigidPlacement(self):
        local = App.Placement(App.Vector(7, 11, 13), App.Rotation(App.Vector(0, 1, 0), 90))
        self._checkNames(local)

    def testNestedRigidPlacements(self):
        local = App.Placement(App.Vector(7, 11, 13), App.Rotation(App.Vector(0, 1, 0), 90))
        inner = App.Placement(App.Vector(10, -20, 30), App.Rotation(App.Vector(0, 0, 1), 90))
        outer = App.Placement(App.Vector(100, 200, 300), App.Rotation(App.Vector(1, 0, 0), 90))
        self._checkNames(local, inner, outer)
