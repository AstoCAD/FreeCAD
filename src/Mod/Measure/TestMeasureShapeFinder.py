# SPDX-License-Identifier: LGPL-2.1-or-later
"""Whole-object center of mass must include the same placements for all names,
and the placement and scale of a link exactly once."""

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

    def _checkLink(self, scale, linkTransform=False):
        # The link's placement and scale must be applied once, as Part does
        # for the shape of the link.
        feature = self.doc.addObject("Part::Feature", "Linked")
        feature.Shape = Part.makeBox(2, 4, 6)
        feature.Placement = App.Placement(App.Vector(7, 11, 13),
                                          App.Rotation(App.Vector(0, 1, 0), 90))
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = feature
        link.LinkTransform = linkTransform
        link.Placement = App.Placement(App.Vector(100, 200, 300),
                                       App.Rotation(App.Vector(0, 0, 1), 90))
        link.ScaleVector = scale
        self.doc.recompute()

        center = App.Vector(1, 2, 3)
        if linkTransform:
            center = feature.Placement.multVec(center)
        center = App.Vector(center.x * scale.x, center.y * scale.y, center.z * scale.z)
        expected = link.Placement.multVec(center)

        measurement = Measure.Measurement()
        try:
            measurement.addReference3D(link.Name, "")
            result = measurement.com()
            actual = App.Vector(result[0], result[1], result[2])
            self.assertLess((actual - expected).Length, 1e-7,
                            f"got {actual}, expected {expected}")
        finally:
            measurement.clear()

    def testUnscaledLink(self):
        self._checkLink(App.Vector(1, 1, 1))

    def testUniformlyScaledLink(self):
        self._checkLink(App.Vector(2, 2, 2))

    def testNonUniformlyScaledLink(self):
        self._checkLink(App.Vector(2, 1, 3))

    def testLinkWithLinkedTransform(self):
        # With LinkTransform the linked object's own placement is kept under
        # the link's placement.
        self._checkLink(App.Vector(1, 1, 1), linkTransform=True)
