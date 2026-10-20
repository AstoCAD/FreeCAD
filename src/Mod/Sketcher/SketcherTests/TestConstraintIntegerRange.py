# SPDX-License-Identifier: LGPL-2.1-or-later
"""App-only constructor validation diagnostic; no document geometry is mutated.

The original nonnumeric-index crash is FreeCAD/FreeCAD#17721, already guarded in
this branch.  The range checks here concern a separate, unticketed list-parser
boundary and must not be reported as proof of the original crash.
"""

import unittest

import FreeCAD as App
import Part
import Sketcher


class TestConstraintElementIntegerRange(unittest.TestCase):
    def _construct(self, kind, elements):
        if kind == "Text":
            return Sketcher.Constraint(kind, elements, "range diagnostic", "", True)
        return Sketcher.Constraint(kind, elements)

    def _assert_input_rejected(self, action):
        try:
            result = action()
        except Exception as exc:
            self.assertIsInstance(
                exc,
                (TypeError, ValueError, OverflowError),
                "Input must be rejected as an input error, not {}: {}".format(
                    type(exc).__name__, exc
                ),
            )
        else:
            self.fail("Out-of-range or malformed input was accepted: {!r}".format(result))

    def test_group_rejects_out_of_int_range_geometry_indices(self):
        for value in (2**31, -(2**31) - 1, 2**100, -(2**100)):
            with self.subTest(value=value):
                self._assert_input_rejected(lambda: self._construct("Group", [value, 0]))

    def test_text_rejects_out_of_int_range_geometry_indices(self):
        for value in (2**31, -(2**31) - 1, 2**100, -(2**100)):
            with self.subTest(value=value):
                self._assert_input_rejected(lambda: self._construct("Text", [value, 0]))

    def test_group_in_range_geometry_indices_control(self):
        for value in (-(2**31), -2, -1, 0, 2**31 - 1):
            with self.subTest(value=value):
                constraint = self._construct("Group", [value, 0])
                self.assertEqual(constraint.Type, "Group")
                self.assertEqual(constraint.First, value)
                self.assertEqual(constraint.FirstPos, 0)

    def test_text_in_range_geometry_indices_control(self):
        for value in (-(2**31), -2, -1, 0, 2**31 - 1):
            with self.subTest(value=value):
                constraint = self._construct("Text", [value, 0])
                self.assertEqual(constraint.Type, "Text")
                self.assertEqual(constraint.First, value)
                self.assertEqual(constraint.FirstPos, 0)

    def test_malformed_element_list_controls(self):
        for kind in ("Group", "Text"):
            for elements in ([0], [0, "start"], [0.5, 0]):
                with self.subTest(kind=kind, elements=elements):
                    self._assert_input_rejected(lambda: self._construct(kind, elements))

    def test_original_nonnumeric_index_rejection_control(self):
        first = Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0))
        second = Part.LineSegment(App.Vector(0, 10, 0), App.Vector(5, 10, 0))
        self._assert_input_rejected(
            lambda: Sketcher.Constraint("Coincident", first, 2, second, 1)
        )
        valid = Sketcher.Constraint("Coincident", 0, 2, 1, 1)
        self.assertEqual((valid.First, valid.FirstPos, valid.Second, valid.SecondPos), (0, 2, 1, 1))

    def test_position_indices_reject_out_of_int_range_values(self):
        for kind in ("Group", "Text"):
            for value in (2**31, -(2**31) - 1, 2**100, -(2**100)):
                for preceding_pair in ([], [1, 0]):
                    with self.subTest(kind=kind, value=value, preceding_pair=preceding_pair):
                        elements = preceding_pair + [0, value]
                        self._assert_input_rejected(lambda: self._construct(kind, elements))

    def test_position_int_range_and_integer_subclass_controls(self):
        class IntegerSubclass(int):
            pass

        for kind in ("Group", "Text"):
            for value in (-(2**31), -1, 0, 1, 2, 3, 2**31 - 1):
                with self.subTest(kind=kind, value=value):
                    constraint = self._construct(kind, [0, value])
                    self.assertEqual(constraint.Type, kind)
                    self.assertEqual(constraint.First, 0)
                    self.assertEqual(constraint.FirstPos, value)
            for elements in ([True, False], [IntegerSubclass(7), IntegerSubclass(2)]):
                with self.subTest(kind=kind, elements=elements):
                    constraint = self._construct(kind, elements)
                    self.assertEqual((constraint.First, constraint.FirstPos), tuple(elements))
