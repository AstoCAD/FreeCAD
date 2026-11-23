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


class TestMeasurementSubElementCenterOfMass(unittest.TestCase):
    """Measurement.com() of a reference with a sub-element is the center of
    mass of that sub-element, not of the whole referenced object."""

    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementSubElementCenterOfMass")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _checkCenter(self, root, subName, expected, volume):
        measurement = Measure.Measurement()
        try:
            measurement.addReference3D(root.Name, subName)
            self.assertAlmostEqual(measurement.volume(), volume, places=6)
            result = measurement.com()
            actual = App.Vector(result[0], result[1], result[2])
            self.assertLess(
                (actual - expected).Length, 1e-7, f"{subName}: got {actual}, expected {expected}"
            )
        finally:
            measurement.clear()

    def testSolidOfCompound(self):
        compound = self.doc.addObject("Part::Feature", "Compound")
        compound.Shape = Part.makeCompound(
            [Part.makeBox(10, 10, 10), Part.makeBox(2, 4, 6, App.Vector(100, 0, 0))]
        )
        compound.Placement = App.Placement(
            App.Vector(7, 11, 13), App.Rotation(App.Vector(0, 1, 0), 90)
        )
        self.doc.recompute()
        # The center of the second box, from its dimensions and position
        expected = compound.Placement.multVec(App.Vector(101, 2, 3))
        self._checkCenter(compound, "Solid2", expected, 48.0)

    def testObjectInNestedParts(self):
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 2, 4, 6
        box.Placement = App.Placement(App.Vector(7, 11, 13), App.Rotation(App.Vector(0, 1, 0), 90))
        other = self.doc.addObject("Part::Box", "Other")
        other.Placement.Base = App.Vector(-50, 0, 0)
        inner = self.doc.addObject("App::Part", "Inner")
        inner.addObject(box)
        inner.addObject(other)
        inner.Placement = App.Placement(
            App.Vector(10, -20, 30), App.Rotation(App.Vector(0, 0, 1), 90)
        )
        outer = self.doc.addObject("App::Part", "Outer")
        outer.addObject(inner)
        outer.Placement = App.Placement(
            App.Vector(100, 200, 300), App.Rotation(App.Vector(1, 0, 0), 90)
        )
        self.doc.recompute()
        center = box.Placement.multVec(App.Vector(1, 2, 3))
        expected = outer.Placement.multVec(inner.Placement.multVec(center))
        self._checkCenter(outer, "Inner.Box.Solid1", expected, 48.0)

    def testLinkArrayElement(self):
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 2, 4, 6
        array = self.doc.addObject("App::Link", "Array")
        array.LinkedObject = box
        array.ShowElement = False
        array.ElementCount = 3
        array.Placement = App.Placement(
            App.Vector(0, 0, 200), App.Rotation(App.Vector(0, 0, 1), -30)
        )
        self.doc.recompute()
        element = App.Placement(App.Vector(60, 0, 0), App.Rotation(App.Vector(1, 1, 0), 20))
        placements = list(array.PlacementList)
        placements[2] = element
        array.PlacementList = placements
        scales = list(array.ScaleList)
        scales[2] = App.Vector(-1, 2, 1)
        array.ScaleList = scales
        self.doc.recompute()
        # The element places the box (the link ignores the box's own
        # placement) after scaling it; the array places the element.
        expected = array.Placement.multVec(element.multVec(App.Vector(-1, 4, 3)))
        self._checkCenter(array, "2.Solid1", expected, 96.0)


class TestMeasureGetLocatedTopoShape(unittest.TestCase):
    """Measure.getLocatedTopoShape() is available from Python and returns the
    shape or sub-shape in global coordinates."""

    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureGetLocatedTopoShape")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length, self.box.Width, self.box.Height = 2, 4, 6
        self.box.Placement = App.Placement(
            App.Vector(7, 11, 13), App.Rotation(App.Vector(0, 1, 0), 90)
        )
        self.inner = self.doc.addObject("App::Part", "Inner")
        self.inner.addObject(self.box)
        self.inner.Placement = App.Placement(
            App.Vector(10, -20, 30), App.Rotation(App.Vector(0, 0, 1), 90)
        )
        self.outer = self.doc.addObject("App::Part", "Outer")
        self.outer.addObject(self.inner)
        self.outer.Placement = App.Placement(
            App.Vector(100, 200, 300), App.Rotation(App.Vector(1, 0, 0), 90)
        )
        self.doc.recompute()
        # The center of the box, from its dimensions and the placements
        center = self.box.Placement.multVec(App.Vector(1, 2, 3))
        self.expected = self.outer.Placement.multVec(self.inner.Placement.multVec(center))

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _checkSolid(self, shape):
        self.assertIsInstance(shape, Part.Shape)
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.Volume, 48.0, places=6)
        actual = shape.Solids[0].CenterOfMass
        self.assertLess(
            (actual - self.expected).Length, 1e-7, f"got {actual}, expected {self.expected}"
        )

    def testElementThroughPath(self):
        self._checkSolid(Measure.getLocatedTopoShape(self.outer, "Inner.Box.Solid1"))

    def testObjectInParts(self):
        # The containing groups place the whole object
        self._checkSolid(Measure.getLocatedTopoShape(self.box, ""))

    def testNoDocumentObject(self):
        self.assertIsNone(Measure.getLocatedTopoShape(None, ""))

    def testSubnameMustBeText(self):
        # A subname that is not text, or has no UTF-8 form, is rejected
        # instead of being ignored or crashing
        for subname in (None, 5, b"Solid1", "\ud800"):
            with self.subTest(subname=subname):
                with self.assertRaises(TypeError):
                    Measure.getLocatedTopoShape(self.box, subname)


class TestMeasureLocatedPointObject(unittest.TestCase):
    """The shape of a point object (a single vertex) is located like any
    other shape, whatever the name of the object, and including the placement
    of the groups that contain it."""

    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureLocatedPointObject")
        self.part = self.doc.addObject("App::Part", "Part")
        self.part.Placement = App.Placement(
            App.Vector(100, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90)
        )
        self.local = App.Placement(App.Vector(0, 10, 0), App.Rotation(App.Vector(1, 0, 0), 90))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _addPoint(self, name):
        point = self.doc.addObject("Part::Vertex", name)
        point.X, point.Y, point.Z = 1, 2, 3
        point.Placement = self.local
        self.part.addObject(point)
        self.doc.recompute()
        # The located point, from the vertex coordinates and the placements
        return point, self.part.Placement.multVec(self.local.multVec(App.Vector(1, 2, 3)))

    def _checkVertex(self, shape, expected):
        self.assertIsInstance(shape, Part.Shape)
        self.assertEqual(shape.ShapeType, "Vertex")
        actual = shape.Vertexes[0].Point
        self.assertLess((actual - expected).Length, 1e-7, f"got {actual}, expected {expected}")

    def testPointObjectInPart(self):
        for name in ("Vertex", "Point", "Pin"):
            with self.subTest(name=name):
                point, expected = self._addPoint(name)
                self._checkVertex(Measure.getLocatedTopoShape(point, "Vertex1"), expected)
                self._checkVertex(Measure.getLocatedTopoShape(point, ""), expected)

    def testPointObjectThroughPath(self):
        point, expected = self._addPoint("Pin")
        self._checkVertex(Measure.getLocatedTopoShape(self.part, "Pin.Vertex1"), expected)

    def testRemovedObject(self):
        # An object removed by an undoable transaction is no longer in the
        # document but is still alive: the lookup finds no shape, it must not crash
        point, expected = self._addPoint("Point")
        self.doc.openTransaction("Remove point")
        self.doc.removeObject(point.Name)
        self.doc.commitTransaction()
        self.assertTrue(Measure.getLocatedTopoShape(point, "Vertex1").isNull())
