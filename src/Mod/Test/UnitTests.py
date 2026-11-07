# ***************************************************************************
# *   Copyright (c) 2010 Juergen Riegel <juergen.riegel@web.de>             *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************/

import FreeCAD
import unittest
import math


def tu(str):
    return FreeCAD.Units.Quantity(str).Value


def ts(q):
    return q.UserString


def ts2(q):
    return FreeCAD.Units.Quantity(q.UserString).UserString


# ---------------------------------------------------------------------------
# define the functions to test the FreeCAD UnitApi code
# ---------------------------------------------------------------------------


def compare(x, y):
    return math.fabs(x - y) < 0.00001


class UnitBasicCases(unittest.TestCase):
    def setUp(self):
        par = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Units")
        dec = par.GetInt("Decimals")
        self.delta = math.pow(10, -dec)

    def testConversions(self):
        # tu = FreeCAD.Units.translateUnit
        self.assertTrue(compare(tu("10 m"), 10000.0))
        self.assertTrue(compare(tu("3/8 in"), 9.525))
        self.assertTrue(compare(tu("100 km/h"), 27777.77777777))
        self.assertTrue(compare(tu("m^2*kg*s^-3*A^-2"), 1000000.0))
        self.assertTrue(compare(tu("(m^2*kg)/(A^2*s^3)"), 1000000.0))
        self.assertTrue(compare(tu("2*pi rad"), 360.0))
        self.assertTrue(compare(tu("2*pi rad") / tu("gon"), 400.0))
        self.assertTrue(compare(tu("999 kg") / tu("1 m^3"), 0.000009999))

    def testImperial(self):
        # tu = FreeCAD.Units.translateUnit
        self.assertTrue(compare(tu("3/8in"), 9.525))
        # self.assertTrue(compare(tu('1fo(3+7/16)in'),392.112500))thisgivesaparsersyntaxerror!!!
        self.assertTrue(compare(tu("1'(3+7/16)\""), 392.112500))

        psi = FreeCAD.Units.parseQuantity("1psi")
        mpa = psi.getValueAs("MPa").Value
        self.assertAlmostEqual(0.0068947572932, mpa, delta=self.delta)
        kpa = psi.getValueAs("kPa").Value
        self.assertAlmostEqual(6.8947572932, kpa, delta=self.delta)

        ksi = FreeCAD.Units.parseQuantity("1ksi")
        mpa = ksi.getValueAs("MPa").Value
        self.assertAlmostEqual(6.8947572931783, mpa, delta=self.delta)
        kpa = ksi.getValueAs("kPa").Value
        self.assertAlmostEqual(6894.7572931783, kpa, delta=self.delta)

    def testSelfConsistency(self):
        qu = FreeCAD.Units.Quantity("0.23 W/m/K")
        self.assertTrue(ts(qu), ts2(qu))
        qu = FreeCAD.Units.Quantity("237 mm*kg/(s^3*K)")
        self.assertTrue(ts(qu), ts2(qu))
        qu = FreeCAD.Units.Quantity("237.000 W/mm/K")
        self.assertTrue(ts(qu), ts2(qu))

    def testDivide(self):
        qu1 = FreeCAD.Units.Quantity("1 m/s")
        qu2 = FreeCAD.Units.Quantity("m/s")
        self.assertTrue(qu1 / qu2, 1)

    def testSchemas(self):
        schemas = FreeCAD.Units.listSchemas()
        num = len(schemas)

        psi = FreeCAD.Units.parseQuantity("1psi")
        for i in range(num):
            t = FreeCAD.Units.schemaTranslate(psi, i)
            v = FreeCAD.Units.parseQuantity(t[0]).getValueAs("psi")
            self.assertAlmostEqual(
                1,
                v.Value,
                msg='Failed with "{0}" scheme: {1} != 1 (delta: {2})'.format(
                    schemas[i], v.Value, self.delta
                ),
                delta=self.delta,
            )

        ksi = FreeCAD.Units.parseQuantity("1ksi")
        for i in range(num):
            t = FreeCAD.Units.schemaTranslate(ksi, i)
            v = FreeCAD.Units.parseQuantity(t[0]).getValueAs("ksi")
            self.assertAlmostEqual(
                1,
                v.Value,
                msg='Failed with "{0}" scheme: {1} != 1 (delta: {2})'.format(
                    schemas[i], v.Value, self.delta
                ),
                delta=self.delta,
            )

        vacuum_permittivity = FreeCAD.Units.parseQuantity("1F/m")
        vacuum_permittivity.Format = {"NumberFormat": FreeCAD.Units.NumberFormat.Scientific}
        for i in range(num):
            t = FreeCAD.Units.schemaTranslate(vacuum_permittivity, i)
            v = FreeCAD.Units.parseQuantity(t[0]).getValueAs("F/m")
            self.assertAlmostEqual(
                1,
                v.Value,
                msg='Failed with "{0}" scheme: {1} != 1 (delta: {2})'.format(
                    schemas[i], v.Value, self.delta
                ),
                delta=self.delta,
            )

    def testSchemeTranslation(self):
        quantities = []
        for i in dir(FreeCAD.Units):
            if issubclass(type(getattr(FreeCAD.Units, i)), FreeCAD.Units.Quantity):
                quantities.append(i)

        schemas = FreeCAD.Units.listSchemas()
        for i in quantities:
            q1 = getattr(FreeCAD.Units, i)
            q1 = FreeCAD.Units.Quantity(q1)
            q1.Format = {"Precision": 16}
            for idx, val in enumerate(schemas):
                [t, amountPerUnit, unit] = FreeCAD.Units.schemaTranslate(q1, idx)
                try:
                    q2 = FreeCAD.Units.Quantity(t)
                    if math.fabs(q1.Value - q2.Value) > 0.01:
                        print(
                            " {} : {} : {} : {} : {}".format(q1, q2, t, i, val)
                            .encode("utf-8")
                            .strip()
                        )
                except Exception as e:
                    print("{} : {} : {} : {}".format(q1, i, val, e).encode("utf-8").strip())

    def testVoltage(self):
        q1 = FreeCAD.Units.Quantity("1e20 V")
        t = FreeCAD.Units.schemaTranslate(q1, 0)  # Standard
        q2 = FreeCAD.Units.Quantity(t[0])
        self.assertAlmostEqual(q1.Value, q2.Value, delta=self.delta)

    def testEnergy(self):
        q1 = FreeCAD.Units.Quantity("1e20 J")
        t = FreeCAD.Units.schemaTranslate(q1, 0)  # Standard
        q2 = FreeCAD.Units.Quantity(t[0])
        self.assertAlmostEqual(q1.Value, q2.Value, delta=self.delta)

    def testTrigonometric(self):
        # tu=FreeCAD.Units.translateUnit
        self.assertTrue(compare(tu("sin(pi)"), math.sin(math.pi)))
        self.assertTrue(compare(tu("cos(pi)"), math.cos(math.pi)))
        self.assertTrue(compare(tu("tan(pi)"), math.tan(math.pi)))

    def testQuantity(self):
        length = FreeCAD.Units.Quantity(1, "m")
        self.assertEqual(length.Value, 1000)
        self.assertEqual(length.Unit, FreeCAD.Units.Length)

    def testUnitMismatchMessageNamesUnits(self):
        # https://github.com/FreeCAD/FreeCAD/issues/17850
        length = FreeCAD.Units.Quantity("5 mm")
        number = FreeCAD.Units.Quantity(3)
        with self.assertRaises(Exception) as ctx:
            length + number
        self.assertIn("Unit mismatch in plus operation", str(ctx.exception))
        self.assertIn("(left: mm, right: unitless)", str(ctx.exception))
        with self.assertRaises(Exception) as ctx:
            number - FreeCAD.Units.Quantity("2 s")
        self.assertIn("Unit mismatch in minus operation", str(ctx.exception))
        self.assertIn("(left: unitless, right: s)", str(ctx.exception))

    def testExpressionUnitMismatchMessageNamesUnits(self):
        # https://github.com/FreeCAD/FreeCAD/issues/17850
        doc = FreeCAD.newDocument("UnitMismatchMessage")
        try:
            varset = doc.addObject("App::VarSet", "VarSet")
            varset.addProperty("App::PropertyLength", "Length")
            varset.Length = 5
            with self.assertRaises(Exception) as ctx:
                varset.evalExpression("Length + 3")
            self.assertIn("(left: mm, right: unitless)", str(ctx.exception))
            self.assertEqual(varset.evalExpression("Length + 3 mm"), FreeCAD.Units.Quantity("8 mm"))
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testToString(self):
        value = FreeCAD.Units.toNumber(1023, "g", 2)
        self.assertEqual(float(value), 1000)

        value = FreeCAD.Units.toNumber(1023, "g", 3)
        self.assertEqual(float(value), 1020)

        value = FreeCAD.Units.toNumber(1023, "f", 2)
        self.assertEqual(float(value), 1023)

        value = FreeCAD.Units.toNumber(1023, "e", 1)
        self.assertEqual(float(value), 1000)

        value = FreeCAD.Units.toNumber(1023, "e", 2)
        self.assertEqual(float(value), 1020)

        value = FreeCAD.Units.toNumber(1023, "e", 3)
        self.assertEqual(float(value), 1023)

        q = FreeCAD.Units.Quantity("1023")
        value = FreeCAD.Units.toNumber(q, "f", 2)
        self.assertEqual(float(value), 1023)

        # Omitted decimals default to -1 (the user's number of decimals) as documented,
        # not to 0 decimals
        self.assertEqual(
            FreeCAD.Units.toNumber(1.23456789), FreeCAD.Units.toNumber(1.23456789, "g", -1)
        )
        self.assertEqual(
            FreeCAD.Units.toNumber(1.23456789, "f"), FreeCAD.Units.toNumber(1.23456789, "f", -1)
        )
        q = FreeCAD.Units.Quantity("1.23456789 mm")
        self.assertEqual(FreeCAD.Units.toNumber(q), FreeCAD.Units.toNumber(q, "g", -1))

        with self.assertRaises(TypeError):
            FreeCAD.Units.toNumber("1023", "g", 2)
        with self.assertRaises(ValueError):
            FreeCAD.Units.toNumber(1023, "gg", 2)
        with self.assertRaises(ValueError):
            FreeCAD.Units.toNumber(1023, "s", 2)

    def testCompareDifferentUnits(self):
        # Ordering quantities of different units threw a C++ exception straight
        # through the rich comparison slot instead of raising a Python error
        length = FreeCAD.Units.Quantity("1 m")
        mass = FreeCAD.Units.Quantity("1 kg")
        for compare in (
            lambda: length < mass,
            lambda: length <= mass,
            lambda: length > mass,
            lambda: length >= mass,
        ):
            with self.assertRaises(ArithmeticError):
                compare()
        self.assertFalse(length == mass)
        self.assertTrue(length != mass)
        self.assertTrue(length > FreeCAD.Units.Quantity("999 mm"))
        self.assertTrue(length <= FreeCAD.Units.Quantity("1000 mm"))

    def testIssue6735(self):
        FreeCAD.Units.Quantity("1400.0 N/mm^2")

    def testHugeIntegerOperand(self):
        # Integers that do not fit into a C long used to leave an OverflowError
        # pending while returning a result (SystemError)
        huge = 2**70
        one = FreeCAD.Units.Quantity(1.0)
        self.assertEqual((one + huge).Value, float(huge))
        self.assertEqual((huge * one).Value, float(huge))
        self.assertEqual((FreeCAD.Units.Quantity(5.0) % huge).Value, 5.0)
        self.assertEqual((one**huge).Value, 1.0)
        self.assertEqual((FreeCAD.Units.Quantity(2.0) ** 3).Value, 8.0)
        with self.assertRaises(OverflowError):
            one + 10**400

    def testPowerUnitExponentOutOfRangeRaises(self):
        # Unit::pow cast the new exponents to int8 unchecked: 1 mm ** 256 gave a
        # dimensionless result, 1 mm ** 200 an underflow
        mm = FreeCAD.Units.Quantity("1 mm")
        for exp in (8, 200, 256, 2**40, 1e300, float("inf")):
            with self.subTest(exp=exp):
                with self.assertRaises(OverflowError):
                    mm**exp
        for exp in (-9, -200, -256):
            with self.subTest(exp=exp):
                with self.assertRaises(ArithmeticError):
                    mm**exp
        # in range and dimensionless powers are unchanged
        self.assertEqual((mm**7).Unit, FreeCAD.Units.Unit(7))
        self.assertEqual((mm**-8).Unit, FreeCAD.Units.Unit(-8))
        self.assertEqual((FreeCAD.Units.Quantity(2.0) ** 1000).Unit, FreeCAD.Units.Unit())
        self.assertEqual(
            (FreeCAD.Units.Quantity(2.0) ** float("inf")).Value, float("inf")
        )

    def testPowerQuantityExponentOutOfRangeRaises(self):
        # Quantity::pow(Quantity) cast the exponent to signed char unchecked:
        # 1 mm ** Quantity(256) gave a dimensionless result
        mm = FreeCAD.Units.Quantity("1 mm")
        for exp in (200, 256, 1e300):
            with self.subTest(exp=exp):
                with self.assertRaises(OverflowError):
                    mm ** FreeCAD.Units.Quantity(exp)
        with self.assertRaises(ArithmeticError):
            mm ** FreeCAD.Units.Quantity(-200)
        # in range exponents are unchanged
        self.assertEqual((mm ** FreeCAD.Units.Quantity(7)).Unit, FreeCAD.Units.Unit(7))
        self.assertEqual(
            (FreeCAD.Units.Quantity(2.0) ** FreeCAD.Units.Quantity(1000)).Unit,
            FreeCAD.Units.Unit(),
        )

    def testPowerQuantityExponentIsExact(self):
        # A Quantity exponent was truncated for the unit, unlike a float exponent:
        # (4 mm^2) ** Quantity(0.5) gave 2 with no unit, 1 mm ** Quantity(2.5) mm^2,
        # "1 mm^1.5" 1 mm, and the expression "(4 mm^2) ^ Half" 2
        q = FreeCAD.Units.Quantity
        root = q("4 mm^2") ** q(0.5)
        self.assertEqual((root.Value, root.Unit), (2.0, FreeCAD.Units.Length))
        for base, exp in (("1 mm", 2.5), ("1 mm", -0.5), ("1 mm^3", 0.5)):
            with self.subTest(base=base, exp=exp):
                with self.assertRaises(ArithmeticError):
                    q(base) ** q(exp)
                with self.assertRaises(ArithmeticError):
                    q(base) ** exp
        for text in ("1 mm^1.5", "1 mm^(1/2)"):
            with self.subTest(text=text):
                with self.assertRaises(ArithmeticError):
                    q(text)
        self.assertEqual(q("1 m^2").Unit, FreeCAD.Units.Area)
        self.assertEqual(q("8 mm^3") ** q(1 / 3), q("2 mm"))
        doc = FreeCAD.newDocument("QuantityPower")
        self.addCleanup(FreeCAD.closeDocument, doc.Name)
        obj = doc.addObject("App::FeaturePython", "Obj")
        obj.addProperty("App::PropertyQuantity", "Half").Half = q(0.5)
        self.assertEqual(obj.evalExpression("(4 mm^2) ^ Half"), q("2 mm"))
        with self.assertRaises(ArithmeticError):
            obj.evalExpression("(1 mm) ^ Half")

    def testUnitExponentOutOfRangeRaises(self):
        # The C++ OverflowError/UnderflowError used to escape from these
        # constructors and abort the interpreter.
        with self.assertRaises(OverflowError):
            FreeCAD.Units.Quantity("1 m^9")
        with self.assertRaises(ArithmeticError):
            FreeCAD.Units.Quantity("1 m^-9")
        with self.assertRaises(OverflowError):
            FreeCAD.Units.Quantity(1, "m^9")
        with self.assertRaises(OverflowError):
            FreeCAD.Units.Quantity(1, 9)
        with self.assertRaises(OverflowError):
            FreeCAD.Units.Unit("m^9")
        with self.assertRaises(OverflowError):
            FreeCAD.Units.parseQuantity("1 m^9")
        # values in range are unchanged
        self.assertEqual(FreeCAD.Units.Quantity("1 m^3").Value, 1e9)
        self.assertEqual(FreeCAD.Units.Unit("m^3"), FreeCAD.Units.Volume)
        self.assertEqual(FreeCAD.Units.Quantity(1, 3).Unit, FreeCAD.Units.Volume)
        self.assertEqual(FreeCAD.Units.parseQuantity("1 m^3").Value, 1e9)

    def testSetSchemaInvalidArgument(self):
        # an argument that is not an int returned None with the parse error
        # still set (SystemError) instead of raising it
        schema = FreeCAD.Units.getSchema()
        self.addCleanup(FreeCAD.Units.setSchema, schema)
        with self.assertRaises(TypeError):
            FreeCAD.Units.setSchema("0")
        with self.assertRaises(TypeError):
            FreeCAD.Units.setSchema()
        with self.assertRaises(OverflowError):
            FreeCAD.Units.setSchema(2**70)
        with self.assertRaises(ValueError):
            FreeCAD.Units.setSchema(-1)
        self.assertEqual(FreeCAD.Units.getSchema(), schema)
        FreeCAD.Units.setSchema(schema)
        self.assertEqual(FreeCAD.Units.getSchema(), schema)

    def testUnknownCharacterIsSyntaxError(self):
        # A character the parser does not know ended the input when it was not ASCII:
        # "1 m²" gave 1 m, "1 µPa" or "1 μm" (Greek mu) a plain 1 and "１ mm" (full-width
        # digit) the empty-input value
        for text in ("1 m²", "1 kg/m³", "1 N·m", "1 µPa", "1 μm", "１ mm", "1 Ω", "1 mm €"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    FreeCAD.Units.Quantity(text)
        with self.assertRaises(ValueError):
            FreeCAD.Units.Quantity("1 mm !")
        # the known non-ASCII units still parse
        self.assertEqual(FreeCAD.Units.Quantity("1 µm").Value, 0.001)
        self.assertEqual(FreeCAD.Units.Quantity("2 °").Value, 2)
        self.assertEqual(FreeCAD.Units.Quantity("1 kg/m^3").Unit, FreeCAD.Units.Density)
        self.assertEqual(FreeCAD.Units.Quantity("−1 mm").Value, -1)

    def testNegativeFeetAndInches(self):
        # -10' 5" means minus (10 feet 5 inches), as the Building US schema writes it,
        # but was read as -10' + 5"
        q = FreeCAD.Units.Quantity
        for text, inches in (
            ("-10' 5\"", -125),
            ("-10'5\"", -125),
            ("-10 ft 5 in", -125),
            ("-10' -5\"", -125),
            ("-1' 2\" - 1/4\"", -14.25),
            ("-2\" - 1/2\"", -2.5),
            ("10' 5\"", 125),
            ("1' 2\" + 1/4\"", 14.25),
            ("2' -4\"", 20),
        ):
            with self.subTest(text=text):
                self.assertAlmostEqual(q(text).getValueAs("in"), inches)
        # the schema's own output reads back
        schemas = FreeCAD.Units.listSchemas()
        building = schemas.index("ImperialBuilding")
        for mm in (-2540.0, -390.525, -85.725, -317.5, 390.525):
            with self.subTest(mm=mm):
                text = FreeCAD.Units.schemaTranslate(q(mm, FreeCAD.Units.Length), building)[0]
                self.assertAlmostEqual(q(text).Value, mm, msg=text)

    def testNegativeDegreesMinutesSeconds(self):
        # The same rule for degrees, minutes and seconds: -10°30′ is -(10°30′). The Civil
        # schema wrote -10.5° as -11°30′ (-11° + 30′), which now read back as -11.5°.
        q = FreeCAD.Units.Quantity
        self.assertAlmostEqual(q("-10°30′").Value, -10.5)
        self.assertAlmostEqual(q("-0°15′").Value, -0.25)
        self.assertAlmostEqual(q("-0°0′36″").Value, -0.01)
        civil = FreeCAD.Units.listSchemas().index("ImperialCivil")
        for degrees in (10.5, -10.5, -0.25, -0.01, -45.11, -30.0, 0.0):
            with self.subTest(degrees=degrees):
                angle = q(degrees, FreeCAD.Units.Angle)
                text = FreeCAD.Units.schemaTranslate(angle, civil)[0]
                self.assertAlmostEqual(q(text).Value, degrees, msg=text)

    def testQuantityFromNonFiniteOrLargestFloat(self):
        # The float constructor took the largest double as "no argument": inf, nan and
        # the largest double itself silently gave 0 (and dropped the unit exponents)
        q = FreeCAD.Units.Quantity
        big = 1.7976931348623157e308
        self.assertEqual(q(float("inf")).Value, float("inf"))
        self.assertEqual(q(float("-inf")).Value, float("-inf"))
        self.assertTrue(math.isnan(q(float("nan")).Value))
        self.assertEqual(q(big).Value, big)
        self.assertEqual(q(big, 1).Unit, FreeCAD.Units.Length)
        self.assertEqual(q(5.0, 1).Value, 5.0)
        self.assertEqual(q().Value, 0.0)
        self.assertEqual(q().Unit, FreeCAD.Units.Unit())

    def testLongNumberLiteral(self):
        # A number of 40 characters or more overflowed the lexer's buffer and read as 0
        digits = "0." + "1" * 45
        self.assertAlmostEqual(FreeCAD.Units.Quantity(digits + " mm").Value, float(digits))
        self.assertEqual(FreeCAD.Units.Quantity("1" + "0" * 45).Value, 1e45)
