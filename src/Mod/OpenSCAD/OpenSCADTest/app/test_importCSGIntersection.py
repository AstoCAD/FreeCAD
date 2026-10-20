# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import unary and multi-operand CSG intersections with real native shapes."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import Part
import importCSG


def _cube(size):
    return "cube(size = [%d, %d, %d], center = false);" % (size, size, size)


class TestCsgIntersectionArity(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(
            prefix="freecad-csg-intersection-"
        )
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import_and_check(self, csg, expected_side, expected_type):
        path = Path(self.temp.name) / "IntersectionArity.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        failure = None
        try:
            doc = importCSG.open(str(path))
        except AttributeError as error:
            # Convert the precisely reported API/property failure to a bounded
            # failing assertion. Unexpected native exceptions remain errors.
            if "Base" not in str(error) and "Tool" not in str(error):
                raise
            failure = str(error)
        if failure is not None:
            self.fail("Valid CSG intersection input failed: " + failure)
        self.assertIsNotNone(doc)
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        result = roots[0]
        self.assertEqual(result.TypeId, expected_type)
        shape = result.Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.Volume, expected_side ** 3, places=6)
        bounds = shape.BoundBox
        actual_bounds = (bounds.XMin, bounds.YMin, bounds.ZMin,
                         bounds.XMax, bounds.YMax, bounds.ZMax)
        for actual, expected in zip(actual_bounds, (0, 0, 0, expected_side, expected_side, expected_side)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_three_child_intersection(self):
        self._import_and_check(
            "intersection() {" + _cube(10) + _cube(8) + _cube(6) + "}",
            6, "Part::MultiCommon",
        )

    def test_one_child_intersection(self):
        self._import_and_check("intersection() {" + _cube(6) + "}", 6, "Part::Box")

    def test_two_child_intersection_control(self):
        self._import_and_check(
            "intersection() {" + _cube(10) + _cube(6) + "}", 6, "Part::Common"
        )

    def test_binary_nested_three_child_control(self):
        self._import_and_check(
            "intersection() { intersection() {" + _cube(10) + _cube(8)
            + "}" + _cube(6) + "}", 6, "Part::Common",
        )

    def test_primitive_control(self):
        self._import_and_check(_cube(6), 6, "Part::Box")

    def test_three_child_union_control(self):
        self._import_and_check(
            "union() {" + _cube(2) + _cube(3) + _cube(4) + "}",
            4, "Part::MultiFuse",
        )
