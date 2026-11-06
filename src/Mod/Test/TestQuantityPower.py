# SPDX-License-Identifier: LGPL-2.1-or-later

"""Regression tests for numeric bases with dimensionless Quantity exponents.

FreeCAD/FreeCAD#11810: function results and normalized constraint quantities must
be usable as exponents while retaining ordinary Python numeric power behavior.
"""

import math
import unittest

import FreeCAD as App

try:
    import Part
    import Sketcher
except ModuleNotFoundError as error:
    if error.name not in {"Part", "Sketcher"}:
        raise
    Part = None
    Sketcher = None


class TestQuantityReflectedPower(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("QuantityPower11810")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.owner = self.doc.addObject("App::FeaturePython", "Parameters")
        self.owner.addProperty("App::PropertyFloat", "Exponent")
        self.owner.addProperty("App::PropertyFloat", "Result")
        self.owner.Exponent = 3.0

    @staticmethod
    def _value(result):
        return result.Value if isinstance(result, App.Units.Quantity) else float(result)

    def _must_succeed(self, action, description):
        try:
            return action()
        except Exception as error:
            self.fail(f"{description} must evaluate successfully: {type(error).__name__}: {error}")

    def test_numeric_base_dimensionless_quantity_exponent(self):
        for base, exponent, expected in ((2, 3, 8), (2.0, 3, 8), (-2, 3, -8), (4.0, 0.5, 2)):
            with self.subTest(base=base, exponent=exponent):
                actual = self._must_succeed(
                    lambda: base ** App.Units.Quantity(exponent),
                    f"{base!r} ** Quantity({exponent!r})",
                )
                self.assertAlmostEqual(self._value(actual), expected, places=12)
                if isinstance(actual, App.Units.Quantity):
                    self.assertEqual(actual.Unit, App.Units.Quantity(1).Unit)

    def test_expression_function_result_as_exponent(self):
        for expression in ("2^abs(-3)", "2^trunc(3.25)", "2^floor(3.25)", "2^round(2.75)"):
            with self.subTest(expression=expression):
                actual = self._must_succeed(lambda: self.owner.evalExpression(expression), expression)
                self.assertAlmostEqual(self._value(actual), 8, places=12)

    @unittest.skipIf(Sketcher is None, "Part and Sketcher modules are unavailable")
    def test_sketcher_dimensionless_constraint_ratio_exponent(self):
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(2, 0, 0)), False)
        index = sketch.addConstraint(Sketcher.Constraint("Distance", 0, 2.0))
        sketch.renameConstraint(index, "length_1")
        self.doc.recompute()
        self.assertEqual(sketch.getStatusString(), "Valid")
        self.assertAlmostEqual(sketch.Constraints[index].Value, 2, places=12)
        expression = "1 mm * e^(.Constraints.length_1 / 1 mm)"
        value = self._must_succeed(lambda: sketch.evalExpression(expression), expression)
        self.assertEqual(value.Unit, App.Units.Quantity("1 mm").Unit)
        self.assertAlmostEqual(value.Value, math.exp(2), places=12)

    def test_pow_function_controls(self):
        for expression in ("pow(2; abs(-3))", "pow(2; trunc(3.25))", "pow(2; floor(3.25))"):
            with self.subTest(expression=expression):
                self.assertAlmostEqual(self._value(self.owner.evalExpression(expression)), 8, places=12)

    def test_quantity_base_and_ordinary_numeric_controls(self):
        for expression in ("2^3", "pow(2; 3)"):
            with self.subTest(expression=expression):
                self.assertAlmostEqual(self._value(self.owner.evalExpression(expression)), 8, places=12)
        self.assertAlmostEqual((App.Units.Quantity(2) ** App.Units.Quantity(3)).Value, 8, places=12)
        squared = App.Units.Quantity("2 mm") ** App.Units.Quantity(2)
        self.assertEqual(squared.Unit, App.Units.Quantity("1 mm^2").Unit)
        self.assertAlmostEqual(squared.Value, 4, places=12)

    def test_pow_function_fractional_exponent_of_unit(self):
        # pow() accepts a fractional exponent of a unit when it gives whole unit
        # exponents, like the ^ operator. Its own check only rejected a fraction
        # above the next lower integer: pow(8 mm^3; 1/3) failed, pow(4 mm^2; 0.5) worked.
        for expression, expected, unit in (
            ("pow(4 mm^2; 0.5)", 2, "mm"),
            ("pow(8 mm^3; 1/3)", 2, "mm"),
            ("pow(16 mm^4; 0.25)", 2, "mm"),
            ("pow(8 mm^3; 2/3)", 4, "mm^2"),
            ("pow(4 mm^2; -0.5)", 0.5, "mm^-1"),
            ("(8 mm^3) ^ (1/3)", 2, "mm"),
        ):
            with self.subTest(expression=expression):
                actual = self._must_succeed(lambda: self.owner.evalExpression(expression), expression)
                self.assertEqual(actual.Unit, App.Units.Quantity("1 " + unit).Unit)
                self.assertAlmostEqual(actual.Value, expected, places=12)
        for expression in ("pow(2 mm; 2.4)", "pow(2 mm; 2.6)", "pow(2 mm; -1.5)", "pow(2 mm; 0.5)"):
            with self.subTest(expression=expression):
                with self.assertRaises(Exception):
                    self.owner.evalExpression(expression)

    def test_dimensionful_exponent_remains_rejected(self):
        for base in (2, 2.0, App.Units.Quantity(2), App.Units.Quantity("2 mm")):
            with self.subTest(base=repr(base)):
                with self.assertRaises(Exception):
                    base ** App.Units.Quantity("3 mm")
        with self.assertRaises(Exception):
            self.owner.evalExpression("2^(3 mm)")


class TestQuantityReflectedPowerCompatibility(unittest.TestCase):
    def _must_succeed(self, action, description):
        try:
            return action()
        except Exception as error:
            self.fail(f"{description} must evaluate successfully: {type(error).__name__}: {error}")

    def test_numeric_result_and_domain_match_python_float_exponent(self):
        for base, exponent in ((4.0, 0.5), (-1.0, 0.5), (2, -3), (1.0, 1000), (2, 130)):
            with self.subTest(base=base, exponent=exponent):
                expected = base ** float(exponent)
                actual = self._must_succeed(
                    lambda: base ** App.Units.Quantity(exponent), repr((base, exponent))
                )
                self.assertEqual(type(actual), type(expected))
                self.assertEqual(actual, expected)
        try:
            0.0 ** App.Units.Quantity(-1)
        except Exception as error:
            self.assertIs(type(error), ZeroDivisionError)
        else:
            self.fail("Zero to a negative exponent must retain Python's ZeroDivisionError")

    def test_large_integer_base_uses_python_conversion(self):
        base = 2**40
        actual = self._must_succeed(lambda: base ** App.Units.Quantity(2), "64-bit integer base")
        self.assertEqual(actual, base**2.0)
        self.assertIs(type(actual), float)

    def test_unit_and_angle_exponents_remain_rejected(self):
        for unit in ("3 mm", "30 deg", "1 rad"):
            with self.subTest(unit=unit):
                with self.assertRaises(TypeError):
                    2.0 ** App.Units.Quantity(unit)

    def test_modular_and_unsupported_bases_remain_rejected(self):
        with self.assertRaises(TypeError):
            pow(2, App.Units.Quantity(3), 5)
        for base in ("2", [2], complex(2, 1)):
            with self.subTest(base=repr(base)):
                with self.assertRaises(TypeError):
                    base ** App.Units.Quantity(3)
