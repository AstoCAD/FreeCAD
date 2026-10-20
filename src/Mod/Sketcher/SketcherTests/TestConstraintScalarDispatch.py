# SPDX-License-Identifier: LGPL-2.1-or-later
"""Scalar constraint constructors distinguish integer values from index roles."""

import math
import unittest
import xml.etree.ElementTree as ET

import FreeCAD as App
import Sketcher


class TestConstraintScalarIntegerValues(unittest.TestCase):
    def _valid(self, *args):
        try:
            return Sketcher.Constraint(*args)
        except Exception as exc:
            self.fail("Valid constraint constructor {!r} raised {}: {}".format(
                args, type(exc).__name__, exc
            ))

    def _assert_same_dimension(self, kind, prefix, value):
        expected = self._valid(kind, *prefix, float(value))
        actual = self._valid(kind, *prefix, value)
        self.assertEqual(actual.Type, expected.Type)
        self.assertEqual(actual.Value, float(value))
        self.assertEqual(actual.Value, expected.Value)
        self.assertEqual(
            (actual.First, actual.FirstPos, actual.Second, actual.SecondPos),
            (expected.First, expected.FirstPos, expected.Second, expected.SecondPos),
        )

    def test_large_integer_radius_matches_float_value(self):
        for value in (2**31, 2**100):
            with self.subTest(value=value):
                self._assert_same_dimension("Radius", (0,), value)

    def test_large_integer_point_distance_matches_float_value(self):
        for kind in ("DistanceX", "DistanceY"):
            for value in (2**31, 2**100):
                with self.subTest(kind=kind, value=value):
                    self._assert_same_dimension(kind, (0, 1), value)

    def test_large_integer_two_geometry_distance_matches_float_value(self):
        for value in (2**31, 2**100):
            with self.subTest(value=value):
                self._assert_same_dimension("Distance", (0, 1), value)

    def test_small_integer_dimensional_controls(self):
        for kind, prefix in (("Radius", (0,)), ("DistanceX", (0, 1)),
                             ("DistanceY", (0, 1)), ("Distance", (0, 1))):
            for value in (1, 10, 2**30):
                with self.subTest(kind=kind, value=value):
                    self._assert_same_dimension(kind, prefix, value)

    def test_float_dimensional_controls(self):
        for kind, prefix in (("Radius", (0,)), ("DistanceX", (0, 1)),
                             ("DistanceY", (0, 1)), ("Distance", (0, 1))):
            for value in (1.5, float(2**31), float(2**100)):
                with self.subTest(kind=kind, value=value):
                    constraint = self._valid(kind, *prefix, value)
                    self.assertEqual(constraint.Type, kind)
                    self.assertEqual(constraint.Value, value)

    def test_scalar_geometry_index_normal_input_error_control(self):
        for kind, prefix in (("Parallel", (0,)), ("PointOnObject", (0, 1))):
            for value in (2**31, 2**100):
                with self.subTest(kind=kind, value=value):
                    try:
                        actual = Sketcher.Constraint(kind, *prefix, value)
                    except Exception as exc:
                        self.assertIsInstance(exc, (TypeError, ValueError, OverflowError))
                    else:
                        self.fail("Out-of-int-range geometry index was accepted: {!r}".format(actual))


class TestConstraintScalarDispatchCompatibility(unittest.TestCase):
    _dimensional_forms = (
        ("Radius", (0,)),
        ("DistanceX", (0, 1)),
        ("Distance", (0, 1, 1)),
        ("Distance", (0, 1, 1, 2)),
        ("SnellsLaw", (0, 1, 1, 2, 2)),
    )

    def _valid(self, *args):
        try:
            return Sketcher.Constraint(*args)
        except Exception as exc:
            self.fail("Valid constructor {!r} raised {}: {}".format(
                args, type(exc).__name__, exc
            ))

    def _fields(self, constraint):
        return (constraint.First, constraint.FirstPos, constraint.Second,
                constraint.SecondPos, constraint.Third, constraint.ThirdPos)

    def _assert_xml_and_roundtrip(self, constraint):
        root = ET.fromstring(constraint.Content)
        node = root if root.tag == "Constrain" else root.find(".//Constrain")
        self.assertIsNotNone(node)
        fields = self._fields(constraint)
        self.assertEqual(
            tuple(int(node.attrib[key]) for key in (
                "First", "FirstPos", "Second", "SecondPos", "Third", "ThirdPos"
            )), fields,
        )
        self.assertEqual(tuple(map(int, node.attrib["ElementIds"].split())), fields[::2])
        self.assertEqual(tuple(map(int, node.attrib["ElementPositions"].split())), fields[1::2])
        restored = Sketcher.Constraint()
        restored.restoreContent(constraint.dumpContent(0))
        self.assertEqual(restored.Type, constraint.Type)
        self.assertEqual(self._fields(restored), fields)
        self.assertEqual(restored.Value, constraint.Value)
        self.assertEqual((restored.IsActive, restored.Driving),
                         (constraint.IsActive, constraint.Driving))

    def _assert_input_rejected(self, args):
        try:
            result = Sketcher.Constraint(*args)
        except Exception as exc:
            self.assertIsInstance(exc, (TypeError, ValueError, OverflowError))
        else:
            self.fail("Out-of-int-range index accepted: {!r}".format(result))

    def test_longer_dimensional_arities_accept_large_integer_values(self):
        for kind, prefix in self._dimensional_forms[2:]:
            for value in (2**31, 2**100):
                with self.subTest(kind=kind, prefix=prefix, value=value):
                    expected = self._valid(kind, *prefix, float(value))
                    actual = self._valid(kind, *prefix, value)
                    self.assertEqual(actual.Value, expected.Value)
                    self.assertEqual(actual.Value, float(value))
                    self.assertEqual(self._fields(actual), self._fields(expected))

    def test_longer_index_arities_reject_out_of_int_range_values(self):
        for kind, prefix in (("Coincident", (0, 1, 1)),
                             ("Symmetric", (0, 1, 1, 2)),
                             ("Symmetric", (0, 1, 1, 2, 2))):
            for value in (2**31, 2**100):
                with self.subTest(kind=kind, prefix=prefix, value=value):
                    self._assert_input_rejected((kind, *prefix, value))

    def test_large_integer_values_with_activation_and_driving_flags(self):
        for kind, prefix in self._dimensional_forms:
            for flags in ((False,), (False, False), (True, False)):
                with self.subTest(kind=kind, prefix=prefix, flags=flags):
                    expected = self._valid(kind, *prefix, float(2**31), *flags)
                    actual = self._valid(kind, *prefix, 2**31, *flags)
                    self.assertEqual(actual.Value, expected.Value)
                    self.assertEqual(self._fields(actual), self._fields(expected))
                    self.assertEqual(actual.IsActive, flags[0])
                    if len(flags) == 2:
                        self.assertEqual(actual.Driving, flags[1])

    def test_quantity_angle_conversion_controls(self):
        for prefix in ((0,), (0, 1), (0, 1, 1, 2)):
            for value in ("90 deg", "1.25 rad"):
                with self.subTest(prefix=prefix, value=value):
                    quantity = App.Units.Quantity(value)
                    expected = math.pi / 2 if value == "90 deg" else 1.25
                    constraint = self._valid("Angle", *prefix, quantity, False, False)
                    self.assertAlmostEqual(constraint.Value, expected, places=13)
                    self.assertFalse(constraint.IsActive)
                    self.assertFalse(constraint.Driving)

    def test_quantity_length_and_unitless_value_controls(self):
        for kind, prefix in self._dimensional_forms:
            with self.subTest(kind=kind, prefix=prefix):
                text = "1.5" if kind == "SnellsLaw" else "12.5 mm"
                quantity = App.Units.Quantity(text)
                actual = self._valid(kind, *prefix, quantity)
                expected = self._valid(kind, *prefix, float(quantity))
                self.assertEqual(actual.Value, expected.Value)
                self.assertEqual(self._fields(actual), self._fields(expected))

    def test_bool_integer_subclass_and_small_integer_flag_controls(self):
        class IntegerSubclass(int):
            pass

        for kind, prefix in self._dimensional_forms:
            for value in (True, IntegerSubclass(7), 2**30):
                with self.subTest(kind=kind, prefix=prefix, value=value):
                    expected = self._valid(kind, *prefix, float(value), False, False)
                    actual = self._valid(kind, *prefix, value, False, False)
                    self.assertEqual(actual.Value, expected.Value)
                    self.assertEqual(self._fields(actual), self._fields(expected))
                    self.assertFalse(actual.IsActive)
                    self.assertFalse(actual.Driving)

    def test_index_mapping_flags_and_legacy_element_xml_controls(self):
        cases = (
            (("Parallel", 2, 4), (2, 0, 4, 0)),
            (("PointOnObject", 2, 1, 4), (2, 1, 4, 0)),
            (("Coincident", 2, 1, 4, 2), (2, 1, 4, 2)),
            (("TangentViaPoint", 2, 4, 6, 1), (2, 0, 4, 0, 6, 1)),
            (("PerpendicularViaPoint", 2, 4, 6, 2), (2, 0, 4, 0, 6, 2)),
            (("InternalAlignment:BSplineControlPoint", 2, 1, 4, 3), (2, 1, 4, 0)),
            (("Symmetric", 2, 1, 4, 2, 6), (2, 1, 4, 2, 6, 0)),
            (("Symmetric", 2, 1, 4, 2, 6, 1), (2, 1, 4, 2, 6, 1)),
        )
        for args, expected in cases:
            for flags in ((), (False,), (False, False)):
                with self.subTest(args=args, flags=flags):
                    constraint = self._valid(*args, *flags)
                    self.assertEqual(self._fields(constraint)[:len(expected)], expected)
                    self.assertEqual(constraint.IsActive, not flags or flags[0])
                    self._assert_xml_and_roundtrip(constraint)

    def test_dimensional_legacy_element_xml_and_roundtrip_controls(self):
        for kind, prefix in self._dimensional_forms:
            with self.subTest(kind=kind, prefix=prefix):
                constraint = self._valid(kind, *prefix, 7, False, False)
                self._assert_xml_and_roundtrip(constraint)
