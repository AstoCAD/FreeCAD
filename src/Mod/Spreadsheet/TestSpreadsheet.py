# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2016 Werner Mayer <wmayer[at]users.sourceforge.net>     *
# *   Copyright (c) 2016 Eivind Kvedalen <eivind@kvedalen.name>             *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU General Public License (GPL)            *
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
# ***************************************************************************/

import os
import math
from math import sqrt
import unittest
import FreeCAD
import Part
import Sketcher
import tempfile
import zipfile
from FreeCAD import Base
from FreeCAD import Units

v = Base.Vector


# ----------------------------------------------------------------------------------
# Test Spreadsheet module and expression engine
# ----------------------------------------------------------------------------------


#############################################################################################
class SpreadsheetAggregates(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument()
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def test_sum(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("A1", "=sum(1)")
        self.sheet.set("A2", "=sum(1;2)")
        self.sheet.set("A3", "=sum(1;2;3)")
        self.sheet.set("A4", "=sum(1;2;3;B13)")
        self.sheet.set("A5", "=sum(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.A1, 1)
        self.assertEqual(self.sheet.A2, 3)
        self.assertEqual(self.sheet.A3, 6)
        self.assertEqual(self.sheet.A4, 10)
        self.assertEqual(self.sheet.A5, 21)

    def test_min(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("B1", "=min(1)")
        self.sheet.set("B2", "=min(1;2)")
        self.sheet.set("B3", "=min(1;2;3)")
        self.sheet.set("B4", "=min(1;2;3;B13)")
        self.sheet.set("B5", "=min(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.B1, 1)
        self.assertEqual(self.sheet.B2, 1)
        self.assertEqual(self.sheet.B3, 1)
        self.assertEqual(self.sheet.B4, 1)
        self.assertEqual(self.sheet.B5, 1)

    def test_max(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("C1", "=max(1)")
        self.sheet.set("C2", "=max(1;2)")
        self.sheet.set("C3", "=max(1;2;3)")
        self.sheet.set("C4", "=max(1;2;3;B13)")
        self.sheet.set("C5", "=max(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.C1, 1)
        self.assertEqual(self.sheet.C2, 2)
        self.assertEqual(self.sheet.C3, 3)
        self.assertEqual(self.sheet.C4, 4)
        self.assertEqual(self.sheet.C5, 6)

    def test_stddev(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("D1", "=stddev(1)")
        self.sheet.set("D2", "=stddev(1;2)")
        self.sheet.set("D3", "=stddev(1;2;3)")
        self.sheet.set("D4", "=stddev(1;2;3;B13)")
        self.sheet.set("D5", "=stddev(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertTrue(
            self.sheet.D1.startswith("ERR: Invalid number of entries: at least two required.")
        )
        self.assertEqual(self.sheet.D2, 0.7071067811865476)
        self.assertEqual(self.sheet.D3, 1.0)
        self.assertEqual(self.sheet.D4, 1.2909944487358056)
        self.assertEqual(self.sheet.D5, 1.8708286933869707)

    def test_count(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("E1", "=count(1)")
        self.sheet.set("E2", "=count(1;2)")
        self.sheet.set("E3", "=count(1;2;3)")
        self.sheet.set("E4", "=count(1;2;3;B13)")
        self.sheet.set("E5", "=count(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.E1, 1)
        self.assertEqual(self.sheet.E2, 2)
        self.assertEqual(self.sheet.E3, 3)
        self.assertEqual(self.sheet.E4, 4)
        self.assertEqual(self.sheet.E5, 6)

    def test_average(self):
        self.sheet.set("B13", "4")
        self.sheet.set("B14", "5")
        self.sheet.set("B15", "6")
        self.sheet.set("F1", "=average(1)")
        self.sheet.set("F2", "=average(1;2)")
        self.sheet.set("F3", "=average(1;2;3)")
        self.sheet.set("F4", "=average(1;2;3;B13)")
        self.sheet.set("F5", "=average(1;2;3;B13:B15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.F1, 1)
        self.assertEqual(self.sheet.F2, (1.0 + 2.0) / 2.0)
        self.assertEqual(self.sheet.F3, (1.0 + 2 + 3) / 3)
        self.assertEqual(self.sheet.F4, (1.0 + 2 + 3 + 4) / 4)
        self.assertEqual(self.sheet.F5, (1.0 + 2 + 3 + 4 + 5 + 6) / 6)

    def test_range(self):
        self.sheet.set("C13", "4mm")
        self.sheet.set("C14", "5mm")
        self.sheet.set("C15", "6mm")
        self.sheet.set("G1", "=average(C13:C15)")
        self.sheet.set("G2", "=min(C13:C15)")
        self.sheet.set("G3", "=max(C13:C15)")
        self.sheet.set("G4", "=count(C13:C15)")
        self.sheet.set("G5", "=stddev(C13:C15)")
        self.sheet.set("G6", "=sum(C13:C15)")

        self.doc.recompute()

        self.assertEqual(self.sheet.G1, Units.Quantity("5 mm"))
        self.assertEqual(self.sheet.G2, Units.Quantity("4 mm"))
        self.assertEqual(self.sheet.G3, Units.Quantity("6 mm"))
        self.assertEqual(self.sheet.G4, 3)
        self.assertEqual(self.sheet.G5, Units.Quantity("1 mm"))
        self.assertEqual(self.sheet.G6, Units.Quantity("15 mm"))

    def test_range_invalid(self):
        self.sheet.set("C13", "4mm")
        self.sheet.set("C14", "5mm")
        self.sheet.set("C15", "6mm")
        self.sheet.set("C16", "6")
        self.sheet.set("H1", "=average(C13:C16)")
        self.sheet.set("H2", "=min(C13:C16)")
        self.sheet.set("H3", "=max(C13:C16)")
        self.sheet.set("H4", "=count(C13:C16)")
        self.sheet.set("H5", "=stddev(C13:C16)")
        self.sheet.set("H6", "=sum(C13:C16)")

        self.doc.recompute()

        self.assertTrue(
            self.sheet.H1.startswith(
                "ERR: Quantity::operator +=(): Unit mismatch in plus operation"
            )
        )
        self.assertTrue(
            self.sheet.H2.startswith(
                "ERR: Quantity::operator <(): quantities need to have same unit to compare"
            )
        )
        self.assertTrue(
            self.sheet.H3.startswith(
                "ERR: Quantity::operator >(): quantities need to have same unit to compare"
            )
        )
        self.assertEqual(self.sheet.H4, 4)
        self.assertTrue(
            self.sheet.H5.startswith(
                "ERR: Quantity::operator -(): Unit mismatch in minus operation"
            )
        )
        self.assertTrue(
            self.sheet.H6.startswith(
                "ERR: Quantity::operator +=(): Unit mismatch in plus operation"
            )
        )

    def test_and(self):
        self.sheet.set("C20", "4")
        self.sheet.set("C21", "5")
        self.sheet.set("C22", "6")
        self.sheet.set("C23", "0")

        self.sheet.set("A1", "=and(1)")
        self.sheet.set("A2", "=and(1;2)")
        self.sheet.set("A3", "=and(1;2;3)")
        self.sheet.set("A4", "=and(1;2;3;C20)")
        self.sheet.set("A5", "=and(1;2;3;C20:C22)")
        self.sheet.set("A6", "=and(1;2;3;C20:C23)")

        self.sheet.set("B1", "=and(0)")
        self.sheet.set("B2", "=and(0;1;2)")
        self.sheet.set("B3", "=and(0;1;2;3)")
        self.sheet.set("B4", "=and(1;2;0)")
        self.sheet.set("B5", "=and(1;2;3;0)")
        self.sheet.set("B6", "=and(1;0;2)")
        self.sheet.set("B6", "=and(1;0;2;0;3)")

        self.doc.recompute()

        self.assertEqual(self.sheet.A1, 1)
        self.assertEqual(self.sheet.A2, 1)
        self.assertEqual(self.sheet.A3, 1)
        self.assertEqual(self.sheet.A4, 1)
        self.assertEqual(self.sheet.A5, 1)
        self.assertEqual(self.sheet.A6, 0)

        self.assertEqual(self.sheet.B1, 0)
        self.assertEqual(self.sheet.B2, 0)
        self.assertEqual(self.sheet.B3, 0)
        self.assertEqual(self.sheet.B4, 0)
        self.assertEqual(self.sheet.B5, 0)
        self.assertEqual(self.sheet.B6, 0)

    def test_or(self):
        self.sheet.set("C20", "4")
        self.sheet.set("C21", "5")
        self.sheet.set("C22", "6")
        self.sheet.set("C23", "0")
        self.sheet.set("C24", "0")

        self.sheet.set("A1", "=or(1)")
        self.sheet.set("A2", "=or(1;2)")
        self.sheet.set("A3", "=or(1;2;3)")
        self.sheet.set("A4", "=or(1;2;3;C20)")
        self.sheet.set("A5", "=or(1;2;3;C20:C22)")
        self.sheet.set("A6", "=or(1;2;3;C20:C23)")

        self.sheet.set("B1", "=or(0)")
        self.sheet.set("B2", "=or(0;1;2)")
        self.sheet.set("B3", "=or(0;1;2;3)")
        self.sheet.set("B4", "=or(1;2;0)")
        self.sheet.set("B5", "=or(1;2;3;0)")
        self.sheet.set("B6", "=or(1;0;2)")
        self.sheet.set("B6", "=or(1;0;2;0;3)")

        self.sheet.set("C1", "=or(0)")
        self.sheet.set("C2", "=or(0;0)")
        self.sheet.set("C3", "=or(0mm;0;0)")
        self.sheet.set("C4", "=or(0;0;0;C23)")
        self.sheet.set("C5", "=or(0;0;0;C23:C24)")
        self.sheet.set("C6", "=or(C23:C24)")
        self.sheet.set("C7", "=or(C22:C24)")

        self.doc.recompute()

        self.assertEqual(self.sheet.A1, 1)
        self.assertEqual(self.sheet.A2, 1)
        self.assertEqual(self.sheet.A3, 1)
        self.assertEqual(self.sheet.A4, 1)
        self.assertEqual(self.sheet.A5, 1)
        self.assertEqual(self.sheet.A6, 1)

        self.assertEqual(self.sheet.B1, 0)
        self.assertEqual(self.sheet.B2, 1)
        self.assertEqual(self.sheet.B3, 1)
        self.assertEqual(self.sheet.B4, 1)
        self.assertEqual(self.sheet.B5, 1)
        self.assertEqual(self.sheet.B6, 1)

        self.assertEqual(self.sheet.C1, 0)
        self.assertEqual(self.sheet.C2, 0)
        self.assertEqual(self.sheet.C3, 0)
        self.assertEqual(self.sheet.C4, 0)
        self.assertEqual(self.sheet.C5, 0)
        self.assertEqual(self.sheet.C6, 0)
        self.assertEqual(self.sheet.C7, 1)

    def test_address(self):
        # Valid cases
        self.sheet.set("A1", "=address(1;2)")
        self.sheet.set("A2", "=address(1;2;1)")
        self.sheet.set("A3", "=address(1;2;2)")
        self.sheet.set("A4", "=address(1;2;3)")
        self.sheet.set("A5", "=address(1;2;4)")
        self.sheet.set("A6", "=address(1;1)")
        self.sheet.set("A7", "=address(16384;702)")

        # Invalid reference type
        self.sheet.set("A8", "=address(1;2;0)")
        self.sheet.set("A9", "=address(1;2;5)")

        # Out of bounds
        self.sheet.set("A10", "=address(0;0)")
        self.sheet.set("A11", "=address(0;1)")
        self.sheet.set("A12", "=address(1;0)")
        self.sheet.set("A13", "=address(16384+1;1)")
        self.sheet.set("A14", "=address(1;702+1)")

        self.doc.recompute()

        self.assertEqual(self.sheet.A1, "$B$1")
        self.assertEqual(self.sheet.A2, "$B$1")
        self.assertEqual(self.sheet.A3, "B$1")
        self.assertEqual(self.sheet.A4, "$B1")
        self.assertEqual(self.sheet.A5, "B1")
        self.assertEqual(self.sheet.A6, "$A$1")
        self.assertEqual(self.sheet.A7, "$ZZ$16384")

        self.assertTrue(self.sheet.A8.startswith("ERR: Invalid reference type:"))
        self.assertTrue(self.sheet.A9.startswith("ERR: Invalid reference type:"))

        self.assertTrue(self.sheet.A10.startswith("ERR: Cell address out of bounds."))
        self.assertTrue(self.sheet.A11.startswith("ERR: Cell address out of bounds."))
        self.assertTrue(self.sheet.A12.startswith("ERR: Cell address out of bounds."))
        self.assertTrue(self.sheet.A13.startswith("ERR: Cell address out of bounds."))
        self.assertTrue(self.sheet.A14.startswith("ERR: Cell address out of bounds."))


#############################################################################################
class SpreadsheetFunction(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument()
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def assertMostlyEqual(self, a, b):
        if type(a) is Units.Quantity:
            self.assertTrue(math.fabs(a.Value - b.Value) < 1e-14)
            self.assertTrue(a.Unit == b.Unit)
        else:
            self.assertNotIsInstance(a, str)
            self.assertNotIsInstance(b, str)
            self.assertTrue(
                math.fabs(a - b) < 1e-14,
                "Values are not 'Mostly Equal': %s != %s" % (a, b),
            )

    def test_cos(self):
        self.sheet.set("A1", "=cos(60)")
        self.sheet.set("B1", "=cos(60deg)")
        self.sheet.set("C1", "=cos(pi / 2 * 1rad)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A1, 0.5)
        self.assertMostlyEqual(self.sheet.B1, 0.5)
        self.assertMostlyEqual(self.sheet.C1, 0)

    def test_sin(self):
        self.sheet.set("A2", "=sin(30)")
        self.sheet.set("B2", "=sin(30deg)")
        self.sheet.set("C2", "=sin(pi / 6 * 1rad)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A2, 0.5)
        self.assertMostlyEqual(self.sheet.B2, 0.5)
        self.assertMostlyEqual(self.sheet.C2, 0.5)

    def test_tan(self):
        self.sheet.set("A3", "=tan(45)")
        self.sheet.set("B3", "=tan(45deg)")
        self.sheet.set("C3", "=tan(pi / 4 * 1rad)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A3, 1)
        self.assertMostlyEqual(self.sheet.B3, 1)
        self.assertMostlyEqual(self.sheet.C3, 1)

    def test_abs(self):
        self.sheet.set("A4", "=abs(3)")
        self.sheet.set("B4", "=abs(-3)")
        self.sheet.set("C4", "=abs(-3mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A4, 3)
        self.assertMostlyEqual(self.sheet.B4, 3)
        self.assertMostlyEqual(self.sheet.C4, Units.Quantity("3 mm"))

    def test_exp(self):
        self.sheet.set("A5", "=exp(3)")
        self.sheet.set("B5", "=exp(-3)")
        self.sheet.set("C5", "=exp(-3mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A5, math.exp(3))
        self.assertMostlyEqual(self.sheet.B5, math.exp(-3))
        self.assertTrue(self.sheet.C5.startswith("ERR: Unit must be empty."))

    def test_log(self):
        self.sheet.set("A6", "=log(3)")
        self.sheet.set("B6", "=log(-3)")
        self.sheet.set("C6", "=log(-3mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A6, math.log(3))
        self.assertTrue(math.isnan(self.sheet.B6))
        self.assertTrue(self.sheet.C6.startswith("ERR: Unit must be empty."))

    def test_log10(self):
        self.sheet.set("A7", "=log10(10)")
        self.sheet.set("B7", "=log10(-3)")
        self.sheet.set("C7", "=log10(-3mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A7, math.log10(10))
        self.assertTrue(math.isnan(self.sheet.B7))
        self.assertTrue(self.sheet.C7.startswith("ERR: Unit must be empty."))

    def test_round(self):
        self.sheet.set("A8", "=round(3.4)")
        self.sheet.set("B8", "=round(3.6)")
        self.sheet.set("C8", "=round(-3.4)")
        self.sheet.set("D8", "=round(-3.6)")
        self.sheet.set("E8", "=round(3.4mm)")
        self.sheet.set("F8", "=round(3.6mm)")
        self.sheet.set("G8", "=round(-3.4mm)")
        self.sheet.set("H8", "=round(-3.6mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A8, 3)
        self.assertMostlyEqual(self.sheet.B8, 4)
        self.assertMostlyEqual(self.sheet.C8, -3)
        self.assertMostlyEqual(self.sheet.D8, -4)
        self.assertEqual(self.sheet.E8, Units.Quantity("3 mm"))
        self.assertEqual(self.sheet.F8, Units.Quantity("4 mm"))
        self.assertEqual(self.sheet.G8, Units.Quantity("-3 mm"))
        self.assertEqual(self.sheet.H8, Units.Quantity("-4 mm"))

    def test_trunc(self):
        self.sheet.set("A9", "=trunc(3.4)")
        self.sheet.set("B9", "=trunc(3.6)")
        self.sheet.set("C9", "=trunc(-3.4)")
        self.sheet.set("D9", "=trunc(-3.6)")
        self.sheet.set("E9", "=trunc(3.4mm)")
        self.sheet.set("F9", "=trunc(3.6mm)")
        self.sheet.set("G9", "=trunc(-3.4mm)")
        self.sheet.set("H9", "=trunc(-3.6mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A9, 3)
        self.assertMostlyEqual(self.sheet.B9, 3)
        self.assertMostlyEqual(self.sheet.C9, -3)
        self.assertMostlyEqual(self.sheet.D9, -3)
        self.assertEqual(self.sheet.E9, Units.Quantity("3 mm"))
        self.assertEqual(self.sheet.F9, Units.Quantity("3 mm"))
        self.assertEqual(self.sheet.G9, Units.Quantity("-3 mm"))
        self.assertEqual(self.sheet.H9, Units.Quantity("-3 mm"))

    def test_ceil(self):
        self.sheet.set("A10", "=ceil(3.4)")
        self.sheet.set("B10", "=ceil(3.6)")
        self.sheet.set("C10", "=ceil(-3.4)")
        self.sheet.set("D10", "=ceil(-3.6)")
        self.sheet.set("E10", "=ceil(3.4mm)")
        self.sheet.set("F10", "=ceil(3.6mm)")
        self.sheet.set("G10", "=ceil(-3.4mm)")
        self.sheet.set("H10", "=ceil(-3.6mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A10, 4)
        self.assertMostlyEqual(self.sheet.B10, 4)
        self.assertMostlyEqual(self.sheet.C10, -3)
        self.assertMostlyEqual(self.sheet.D10, -3)
        self.assertMostlyEqual(self.sheet.E10, Units.Quantity("4 mm"))
        self.assertMostlyEqual(self.sheet.F10, Units.Quantity("4 mm"))
        self.assertMostlyEqual(self.sheet.G10, Units.Quantity("-3 mm"))
        self.assertMostlyEqual(self.sheet.H10, Units.Quantity("-3 mm"))

    def test_floor(self):
        self.sheet.set("A11", "=floor(3.4)")
        self.sheet.set("B11", "=floor(3.6)")
        self.sheet.set("C11", "=floor(-3.4)")
        self.sheet.set("D11", "=floor(-3.6)")
        self.sheet.set("E11", "=floor(3.4mm)")
        self.sheet.set("F11", "=floor(3.6mm)")
        self.sheet.set("G11", "=floor(-3.4mm)")
        self.sheet.set("H11", "=floor(-3.6mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A11, 3)
        self.assertMostlyEqual(self.sheet.B11, 3)
        self.assertMostlyEqual(self.sheet.C11, -4)
        self.assertMostlyEqual(self.sheet.D11, -4)
        self.assertMostlyEqual(self.sheet.E11, Units.Quantity("3 mm"))
        self.assertMostlyEqual(self.sheet.F11, Units.Quantity("3 mm"))
        self.assertMostlyEqual(self.sheet.G11, Units.Quantity("-4 mm"))
        self.assertMostlyEqual(self.sheet.H11, Units.Quantity("-4 mm"))

    def test_asin(self):
        self.sheet.set("A12", "=asin(0.5)")
        self.sheet.set("B12", "=asin(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A12, Units.Quantity("30 deg"))
        self.assertTrue(self.sheet.B12.startswith("ERR: Unit must be empty."))

    def test_acos(self):
        self.sheet.set("A13", "=acos(0.5)")
        self.sheet.set("B13", "=acos(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A13, Units.Quantity("60 deg"))
        self.assertTrue(self.sheet.B13.startswith("ERR: Unit must be empty."))

    def test_atan(self):
        self.sheet.set("A14", "=atan(sqrt(3))")
        self.sheet.set("B14", "=atan(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A14, Units.Quantity("60 deg"))
        self.assertTrue(self.sheet.B14.startswith("ERR: Unit must be empty."))

    def test_asinh(self):
        self.sheet.set("A15", "=sinh(0.5)")
        self.sheet.set("B15", "=sinh(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A15, math.sinh(0.5))
        self.assertTrue(self.sheet.B15.startswith("ERR: Unit must be empty."))

    def test_cosh(self):
        self.sheet.set("A16", "=cosh(0.5)")
        self.sheet.set("B16", "=cosh(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A16, math.cosh(0.5))
        self.assertTrue(self.sheet.B16.startswith("ERR: Unit must be empty."))

    def test_tanh(self):
        self.sheet.set("A17", "=tanh(0.5)")
        self.sheet.set("B17", "=tanh(0.5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A17, math.tanh(0.5))
        self.assertTrue(self.sheet.B17.startswith("ERR: Unit must be empty."))

    def test_sqrt(self):
        self.sheet.set("A18", "=sqrt(4)")
        self.sheet.set("B18", "=sqrt(4mm^2)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A18, 2)
        self.assertMostlyEqual(self.sheet.B18, Units.Quantity("2 mm"))

    def test_mod(self):
        self.sheet.set("A19", "=mod(7; 4)")
        self.sheet.set("B19", "=mod(-7; 4)")
        self.sheet.set("C19", "=mod(7mm; 4)")
        self.sheet.set("D19", "=mod(7mm; 4mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A19, 3)
        self.assertMostlyEqual(self.sheet.B19, -3)
        self.assertMostlyEqual(self.sheet.C19, Units.Quantity("3 mm"))
        self.assertEqual(self.sheet.D19, 3)

    def test_atan2(self):
        self.sheet.set("A20", "=atan2(3; 3)")
        self.sheet.set("B20", "=atan2(-3; 3)")
        self.sheet.set("C20", "=atan2(3mm; 3)")
        self.sheet.set("D20", "=atan2(3mm; 3mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A20, Units.Quantity("45 deg"))
        self.assertMostlyEqual(self.sheet.B20, Units.Quantity("-45 deg"))
        self.assertTrue(self.sheet.C20.startswith("ERR: Units must be equal"))
        self.assertMostlyEqual(self.sheet.D20, Units.Quantity("45 deg"))

    def test_pow(self):
        self.sheet.set("A21", "=pow(7; 4)")
        self.sheet.set("B21", "=pow(-7; 4)")
        self.sheet.set("C21", "=pow(7mm; 4)")
        self.sheet.set("D21", "=pow(7mm; 4mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A21, 2401)
        self.assertMostlyEqual(self.sheet.B21, 2401)
        self.assertMostlyEqual(self.sheet.C21, Units.Quantity("2401mm^4"))
        self.assertTrue(self.sheet.D21.startswith("ERR: Exponent is not allowed to have a unit."))

    def test_hypot(self):
        self.sheet.set("A23", "=hypot(3; 4)")
        self.sheet.set("B23", "=hypot(-3; 4)")
        self.sheet.set("C23", "=hypot(3mm; 4)")
        self.sheet.set("D23", "=hypot(3mm; 4mm)")
        self.sheet.set("A24", "=hypot(3; 4; 5)")
        self.sheet.set("B24", "=hypot(-3; 4; 5)")
        self.sheet.set("C24", "=hypot(3mm; 4; 5)")
        self.sheet.set("D24", "=hypot(3mm; 4mm; 5mm)")

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A23, 5)
        self.assertMostlyEqual(self.sheet.B23, 5)
        self.assertTrue(self.sheet.C23.startswith("ERR: Units must be equal"))
        self.assertMostlyEqual(self.sheet.D23, Units.Quantity("5mm"))
        self.assertMostlyEqual(self.sheet.A24, math.sqrt(3 * 3 + 4 * 4 + 5 * 5))
        self.assertMostlyEqual(self.sheet.B24, math.sqrt(3 * 3 + 4 * 4 + 5 * 5))
        self.assertTrue(self.sheet.C24.startswith("ERR: Units must be equal"))
        self.assertMostlyEqual(self.sheet.D24, Units.Quantity("7.07106781186548 mm"))

    def test_cath(self):
        self.sheet.set("A26", "=cath(5; 3)")
        self.sheet.set("B26", "=cath(-5; 3)")
        self.sheet.set("C26", "=cath(5mm; 3)")
        self.sheet.set("D26", "=cath(5mm; 3mm)")
        l = math.sqrt(5 * 5 + 4 * 4 + 3 * 3)
        self.sheet.set("A27", "=cath(%0.15f; 5; 4)" % l)
        self.sheet.set("B27", "=cath(%0.15f; -5; 4)" % l)
        self.sheet.set("C27", "=cath(%0.15f mm; 5mm; 4)" % l)
        self.sheet.set("D27", "=cath(%0.15f mm; 5mm; 4mm)" % l)

        self.doc.recompute()

        self.assertMostlyEqual(self.sheet.A26, 4)
        self.assertMostlyEqual(self.sheet.B26, 4)
        self.assertTrue(self.sheet.C26.startswith("ERR: Units must be equal"))
        self.assertMostlyEqual(self.sheet.D26, Units.Quantity("4mm"))
        self.assertMostlyEqual(self.sheet.A27, math.sqrt(l * l - 5 * 5 - 4 * 4))
        self.assertMostlyEqual(self.sheet.B27, math.sqrt(l * l - 5 * 5 - 4 * 4))
        self.assertTrue(self.sheet.C27.startswith("ERR: Units must be equal"))
        self.assertMostlyEqual(self.sheet.D27, Units.Quantity("3 mm"))

    def test_not(self):
        self.sheet.set("A20", "=not(3)")
        self.sheet.set("B20", "=not(-3)")
        self.sheet.set("C20", "=not(-3.5)")
        self.sheet.set("D20", "=not(3mm)")
        self.sheet.set("E20", "=not(3.5mm)")
        self.sheet.set("F20", "=not(-3.5mm)")
        self.sheet.set("G20", "=not(0)")
        self.sheet.set("H20", "=not(0mm)")
        self.sheet.set("I20", "=not(1)")

        self.doc.recompute()

        self.assertEqual(self.sheet.A20, 0)
        self.assertEqual(self.sheet.B20, 0)
        self.assertEqual(self.sheet.C20, 0)
        self.assertEqual(self.sheet.D20, 0)
        self.assertEqual(self.sheet.E20, 0)
        self.assertEqual(self.sheet.F20, 0)
        self.assertEqual(self.sheet.G20, 1)
        self.assertEqual(self.sheet.H20, 1)
        self.assertEqual(self.sheet.I20, 0)

        self.sheet.set("J21", f"=not(not({1e-7}))")
        self.sheet.set("J22", f"=not(not({1e-8}))")
        self.doc.recompute()
        self.assertEqual(self.sheet.J21, 1)
        self.assertEqual(self.sheet.J22, 0)


#############################################################################################
class SpreadsheetCases(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument()
        self.TempPath = tempfile.gettempdir()
        FreeCAD.Console.PrintLog("  Using temp path: " + self.TempPath + "\n")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testGetRange(self):
        """Sheet.get(from, to) returns every cell of the range, in either order and with aliases."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("A2", "2")
        sheet.set("B1", "3")
        sheet.set("B2", "4")
        sheet.setAlias("B2", "last")
        self.doc.recompute()
        self.assertEqual(sheet.get("A1", "A2"), (1, 2))
        self.assertEqual(sheet.get("A2", "A1"), (1, 2))
        self.assertEqual(sheet.get("A1", "last"), (1, 2, 3, 4))
        self.assertEqual(sheet.get("A1"), 1)

    def testGetRangeWithEmptyCells(self):
        """Sheet.get(from, to) gives None for the empty cells of the range."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("B2", "4")
        sheet.setBackground("A2", (1.0, 0.0, 0.0))  # formatted, but empty
        self.doc.recompute()
        self.assertEqual(sheet.get("A1", "B2"), (1, None, None, 4))
        self.assertEqual(sheet.get("C1", "C2"), (None, None))
        # A cell with contents that has no value yet is still an error
        sheet.set("C2", "5")
        with self.assertRaises(ValueError):
            sheet.get("C1", "C2")

    def testRecomputeCellsRange(self):
        """Sheet.recomputeCells(from, to) recomputes every cell of the range."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.doc.recompute()
        sheet.set("A1", "=1 + 1")
        sheet.set("B2", "=2 + 2")
        sheet.recomputeCells("A1", "B2")
        self.assertEqual(sheet.get("A1"), 2)
        self.assertEqual(sheet.get("B2"), 4)

    def testRecomputeCellsRangeString(self):
        """Sheet.recomputeCells/touchCells still accept a single "A1:B2" range."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.doc.recompute()
        sheet.set("A1", "=1 + 1")
        sheet.set("B2", "=2 + 2")
        sheet.touchCells("A1:B2")
        sheet.recomputeCells("A1:B2")
        self.assertEqual(sheet.get("A1"), 2)
        self.assertEqual(sheet.get("B2"), 4)

    def testExportQuotesFieldWithQuoteChar(self):
        """A text cell containing the quote character survives a CSV export/import."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", 'say "hi"')
        sheet.set("B1", "a,b")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "quote.csv")
            self.assertTrue(sheet.exportFile(path, ",", '"', "\\"))
            other = self.doc.addObject("Spreadsheet::Sheet", "Imported")
            self.assertTrue(other.importFile(path, ",", '"', "\\"))
        self.doc.recompute()
        self.assertEqual(other.get("A1"), 'say "hi"')
        self.assertEqual(other.get("B1"), "a,b")

    def testExportKeepsColumnsOfRowsLeftOfFirstCell(self):
        """CSV export keeps the column layout when a later row starts left of the first cell."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B1", "x")
        sheet.set("C1", "z")
        sheet.set("A2", "y")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "columns.csv")
            self.assertTrue(sheet.exportFile(path, ",", '"', "\\"))
            other = self.doc.addObject("Spreadsheet::Sheet", "Imported")
            self.assertTrue(other.importFile(path, ",", '"', "\\"))
        self.doc.recompute()
        self.assertEqual(sorted(other.getNonEmptyCells()), ["A2", "B1", "C1"])
        self.assertEqual(other.get("B1"), "x")
        self.assertEqual(other.get("C1"), "z")
        self.assertEqual(other.get("A2"), "y")

    def testExportKeepsAllDigitsOfNumbers(self):
        """CSV export writes numbers with all their digits, not 6 significant ones."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=1/3")
        sheet.set("B1", "1234567.891")
        sheet.set("C1", "0.1")
        sheet.set("D1", "12.3456789 mm")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "digits.csv")
            self.assertTrue(sheet.exportFile(path, ",", '"', "\\"))
            with open(path) as csv_file:
                self.assertEqual(
                    csv_file.read().strip(), "0.3333333333333333,1234567.891,0.1,12.3456789"
                )
            other = self.doc.addObject("Spreadsheet::Sheet", "Imported")
            self.assertTrue(other.importFile(path, ",", '"', "\\"))
        self.doc.recompute()
        self.assertEqual(other.get("A1"), 1 / 3)
        self.assertEqual(other.get("B1"), 1234567.891)
        self.assertEqual(other.get("C1"), 0.1)
        self.assertEqual(other.get("D1"), 12.3456789)

    def testExportEscapesEscapeCharAndNewline(self):
        """Text with the escape character or a newline survives a CSV export/import: the
        backslash of "C:\\temp" was written as is, the import read it as an escape sequence
        and failed, leaving the importing sheet empty"""
        texts = ["C:\\temp\\file", "back\\", "line1\nline2", 'quote " and \\ both']
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for row, text in enumerate(texts, 1):
            sheet.set("A%d" % row, "'" + text)
        sheet.set("B1", "5")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            for delimiter in (",", "\t"):
                path = os.path.join(temp_dir, "escape.csv")
                self.assertTrue(sheet.exportFile(path, delimiter, '"', "\\"))
                other = self.doc.addObject("Spreadsheet::Sheet", "Imported")
                self.assertTrue(other.importFile(path, delimiter, '"', "\\"))
                self.doc.recompute()
                for row, text in enumerate(texts, 1):
                    self.assertEqual(other.get("A%d" % row), text, repr(delimiter))
                self.assertEqual(other.get("B1"), 5)
                self.assertEqual(sorted(other.getNonEmptyCells()), ["A1", "A2", "A3", "A4", "B1"])
                self.doc.removeObject(other.Name)

    def testImportSkipsByteOrderMark(self):
        """A CSV file saved as "CSV UTF-8" starts with a byte order mark, which ended up in
        the first cell (a text "\\ufeff5" instead of the number 5)"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "bom.csv")
            with open(path, "wb") as csv_file:
                csv_file.write(b"\xef\xbb\xbf5,abc\n6,\xc3\xa9\n")
            self.assertTrue(sheet.importFile(path, ",", '"', "\\"))
        self.doc.recompute()
        self.assertEqual(sheet.get("A1"), 5)
        self.assertEqual(sheet.get("B1"), "abc")
        self.assertEqual(sheet.get("A2"), 6)
        self.assertEqual(sheet.get("B2"), "\u00e9")

    def testNumericLiteralIsStableAcrossSaveRestore(self):
        """Numeric literals retain their value and type across save and restore."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        values = {
            "A1": "9030000.000000002",
            "A2": "1.23456789e-9",
            "A3": "1.234567891234567",
            "A4": "42",
        }
        for address, value in values.items():
            sheet.set(address, value)
        self.doc.recompute()

        contents_before = {address: sheet.getContents(address) for address in values}
        values_before = {address: sheet.get(address) for address in values}
        types_before = {address: sheet.getTypeIdOfProperty(address) for address in values}
        self.assertEqual(values_before["A1"], float(values["A1"]))
        self.assertEqual(types_before["A1"], "App::PropertyFloat")
        self.assertEqual(types_before["A2"], "App::PropertyFloat")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "numeric-literals.FCStd")
            self.doc.saveAs(path)
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)

        sheet = self.doc.getObject("Spreadsheet")
        self.assertEqual(
            {address: sheet.getContents(address) for address in values},
            contents_before,
        )
        self.assertEqual(
            {address: sheet.get(address) for address in values},
            values_before,
        )
        self.assertEqual(
            {address: sheet.getTypeIdOfProperty(address) for address in values},
            types_before,
        )
        self.assertEqual(sheet.getContents("A1"), "9030000")
        self.assertEqual(sheet.getContents("A2"), "1.23456789e-09")

    def testRelationalOperators(self):
        """Test relational operators"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        # All should be 1 as result
        sheet.set("A1", "=1 == 1     ? 1 : 0")
        sheet.set("A2", "=1 != 1     ? 0 : 1")
        sheet.set("A3", "=1e9 == 1e9 ? 1 : 0")
        sheet.set("A4", "=1e9 != 1e9 ? 0 : 1")
        sheet.set("A5", "=1 > 1      ? 0 : 1")
        sheet.set("A6", "=2 > 1      ? 1 : 0")
        sheet.set("A7", "=1 > 2      ? 0 : 1")
        sheet.set("A8", "=1 < 1      ? 0 : 1")
        sheet.set("A9", "=1 < 2      ? 1 : 0")
        sheet.set("A10", "=2 < 1      ? 0 : 1")
        sheet.set("A11", "=1 >= 1     ? 1 : 0")
        sheet.set("A12", "=2 >= 1     ? 1 : 0")
        sheet.set("A13", "=1 >= 2     ? 0 : 1")
        sheet.set("A14", "=1 <= 1     ? 1 : 1")
        sheet.set("A15", "=1 <= 2     ? 1 : 0")
        sheet.set("A16", "=2 <= 1     ? 0 : 1")
        sheet.set("A17", "=1 >= 1.000000000000001 ? 0 : 1")
        sheet.set("A18", "=1 >= 1.0000000000000001 ? 1 : 0")
        sheet.set("A19", "=1 <= 1.000000000000001 ? 1 : 0")
        sheet.set("A20", "=1 <= 1.0000000000000001 ? 1 : 0")
        sheet.set("A21", "=1 == 1.000000000000001 ? 0 : 1")
        sheet.set("A22", "=1 == 1.0000000000000001 ? 1 : 0")
        sheet.set("A23", "=1 != 1.000000000000001 ? 1 : 0")
        sheet.set("A24", "=1 != 1.0000000000000001 ? 0 : 1")

        self.doc.recompute()

        self.assertEqual(sheet.A1, 1)
        self.assertEqual(sheet.A2, 1)
        self.assertEqual(sheet.A3, 1)
        self.assertEqual(sheet.A4, 1)
        self.assertEqual(sheet.A5, 1)
        self.assertEqual(sheet.A6, 1)
        self.assertEqual(sheet.A7, 1)
        self.assertEqual(sheet.A8, 1)
        self.assertEqual(sheet.A9, 1)
        self.assertEqual(sheet.A10, 1)
        self.assertEqual(sheet.A11, 1)
        self.assertEqual(sheet.A12, 1)
        self.assertEqual(sheet.A13, 1)
        self.assertEqual(sheet.A14, 1)
        self.assertEqual(sheet.A15, 1)
        self.assertEqual(sheet.A16, 1)
        self.assertEqual(sheet.A17, 1)
        self.assertEqual(sheet.A18, 1)
        self.assertEqual(sheet.A19, 1)
        self.assertEqual(sheet.A20, 1)
        self.assertEqual(sheet.A21, 1)
        self.assertEqual(sheet.A22, 1)
        self.assertEqual(sheet.A23, 1)
        self.assertEqual(sheet.A24, 1)

    def testUnits(self):
        """Units -- test unit calculations."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=2mm + 3mm")
        sheet.set("A2", "=2mm - 3mm")
        sheet.set("A3", "=2mm * 3mm")
        sheet.set("A4", "=4mm / 2mm")
        sheet.set("A5", "=(4mm)^2")
        sheet.set("A6", "=5(mm^2)")
        sheet.set("A7", "=5mm^2")  # ^2 operates on whole number
        sheet.set("A8", "=5")
        sheet.set("A9", "=5*1/K")  # Currently fails
        sheet.set("A10", "=5 K^-1")  # Currently fails
        sheet.set("A11", "=9.8 m/s^2")  # Currently fails
        sheet.setDisplayUnit("A8", "1/K")

        self.doc.recompute()

        self.assertEqual(sheet.A1, Units.Quantity("5mm"))
        self.assertEqual(sheet.A2, Units.Quantity("-1 mm"))
        self.assertEqual(sheet.A3, Units.Quantity("6 mm^2"))
        self.assertEqual(sheet.A4, Units.Quantity("2"))
        self.assertEqual(sheet.A5, Units.Quantity("16 mm^2"))
        self.assertEqual(sheet.A6, Units.Quantity("5 mm^2"))
        self.assertEqual(sheet.A7, Units.Quantity("5 mm^2"))
        self.assertEqual(sheet.A8, Units.Quantity("5"))
        self.assertEqual(sheet.A9, Units.Quantity("5 K^-1"))
        self.assertEqual(sheet.A10, Units.Quantity("5 K^-1"))
        self.assertEqual(sheet.A11, Units.Quantity("9.8 m/s^2"))

    def testPrecedence(self):
        """Precedence -- test precedence for relational operators and conditional operator."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=1 < 2 ? 3 : 4")
        sheet.set("A2", "=1 + 2 < 3 + 4 ? 5 + 6 : 7 + 8")
        sheet.set("A3", "=1 + 2 * 1 < 3 + 4 ? 5 * 2 + 6 * 3 + 2 ^ 4 : 7 * 2 + 8 * 3 + 2 ^ 3")
        sheet.set("A4", "=123")
        sheet.set("A5", "=123 + 321")
        sheet.set("A6", "=123 * 2 + 321")
        sheet.set("A7", "=123 * 2 + 333 / 3")
        sheet.set("A8", "=123 * (2 + 321)")
        sheet.set("A9", "=3 ^ 4")
        sheet.set("A10", "=3 ^ 4 * 2")
        sheet.set("A11", "=3 ^ (4 * 2)")
        sheet.set("A12", "=3 ^ 4 + 4")
        sheet.set("A13", "=1 + 4 / 2 + 5")
        sheet.set("A14", "=(3 + 6) / (1 + 2)")
        sheet.set("A15", "=1 * 2 / 3 * 4")
        sheet.set("A16", "=(1 * 2) / (3 * 4)")
        # Test associativity
        sheet.set(
            "A17", "=3 ^ 4 ^ 2"
        )  # exponentiation is left-associative; to follow excel, openoffice, matlab, octave
        sheet.set("A18", "=3 ^ (4 ^ 2)")  # exponentiation is left-associative
        sheet.set("A19", "=(3 ^ 4) ^ 2")  # exponentiation is left-associative
        sheet.set("A20", "=3 + 4 + 2")
        sheet.set("A21", "=3 + (4 + 2)")
        sheet.set("A22", "=(3 + 4) + 2")
        sheet.set("A23", "=3 - 4 - 2")
        sheet.set("A24", "=3 - (4 - 2)")
        sheet.set("A25", "=(3 - 4) - 2")
        sheet.set("A26", "=3 * 4 * 2")
        sheet.set("A27", "=3 * (4 * 2)")
        sheet.set("A28", "=(3 * 4) * 2")
        sheet.set("A29", "=3 / 4 / 2")
        sheet.set("A30", "=3 / (4 / 2)")
        sheet.set("A31", "=(3 / 4) / 2")
        sheet.set("A32", "=pi * 3")
        sheet.set("A33", "=A32 / 3")
        sheet.set("A34", "=1 < 2 ? <<A>> : <<B>>")
        sheet.set("A35", "=min(A32:A33)")
        sheet.set("A36", "=(1 < 2 ? 0 : 1) * 3")
        sheet.set("A37", "=8/(2^2*2)")
        sheet.set("A38", "=(2^2*2)/8")
        sheet.set("A39", "=2^(2*2)/8")
        sheet.set("A40", "=8/2^(2*2)")
        sheet.set("A41", "=-1")
        sheet.set("A42", "=-(1)")
        sheet.set("A43", "=-(1 + 1)")
        sheet.set("A44", "=-(1 - 1)")
        sheet.set("A45", "=-(-1 + 1)")
        sheet.set("A46", "=-(-1 + -1)")
        sheet.set("A47", "=+1")
        sheet.set("A48", "=+(1)")
        sheet.set("A49", "=+(1 + 1)")
        sheet.set("A50", "=+(1 - 1)")
        sheet.set("A51", "=+(-1 + 1)")
        sheet.set("A52", "=+(-1 + -1)")

        self.doc.addObject("Part::Cylinder", "Cylinder")
        # We cannot use Thickness, as this feature requires a source shape,
        # otherwise it will cause recomputation failure. The new logic of
        # App::Document will not continue recompute any dependent objects

        #  self.doc.addObject("Part::Thickness", "Pipe")
        self.doc.addObject("Part::Box", "Box")
        self.doc.Box.Length = 1

        sheet.set("B1", "101")
        sheet.set("A53", "=-(-(B1-1)/2)")
        sheet.set("A54", '=-(Cylinder.Radius + Box.Length - 1"/2)')

        self.doc.recompute()

        self.assertEqual(sheet.getContents("A1"), "=1 < 2 ? 3 : 4")
        self.assertEqual(sheet.getContents("A2"), "=1 + 2 < 3 + 4 ? 5 + 6 : 7 + 8")
        self.assertEqual(
            sheet.getContents("A3"),
            "=1 + 2 * 1 < 3 + 4 ? 5 * 2 + 6 * 3 + 2 ^ 4 : 7 * 2 + 8 * 3 + 2 ^ 3",
        )
        self.assertEqual(sheet.A1, 3)
        self.assertEqual(sheet.A2, 11)
        self.assertEqual(sheet.A3, 44)
        self.assertEqual(sheet.A4, 123)
        self.assertEqual(sheet.A5, 444)
        self.assertEqual(sheet.A6, 567)
        self.assertEqual(sheet.A7, 357)
        self.assertEqual(sheet.A8, 39729)
        self.assertEqual(sheet.A9, 81)
        self.assertEqual(sheet.A10, 162)
        self.assertEqual(sheet.A11, 6561)
        self.assertEqual(sheet.A12, 85)
        self.assertEqual(sheet.A13, 8)
        self.assertEqual(sheet.A14, 3)
        self.assertEqual(sheet.A15, 8.0 / 3)
        self.assertEqual(sheet.A16, 1.0 / 6)
        self.assertEqual(sheet.A17, 6561)
        self.assertEqual(sheet.A18, 43046721)
        self.assertEqual(sheet.A19, 6561)
        self.assertEqual(sheet.A20, 9)
        self.assertEqual(sheet.A21, 9)
        self.assertEqual(sheet.A22, 9)
        self.assertEqual(sheet.A23, -3)
        self.assertEqual(sheet.A24, 1)
        self.assertEqual(sheet.A25, -3)
        self.assertEqual(sheet.A26, 24)
        self.assertEqual(sheet.A27, 24)
        self.assertEqual(sheet.A28, 24)
        self.assertEqual(sheet.A29, 3.0 / 8)
        self.assertEqual(sheet.A30, 3.0 / 2)
        self.assertEqual(sheet.A31, 3.0 / 8)
        self.assertEqual(sheet.A37, 1)
        self.assertEqual(sheet.A38, 1)
        self.assertEqual(sheet.A39, 2)
        self.assertEqual(sheet.A40, 0.5)
        self.assertEqual(sheet.A41, -1)
        self.assertEqual(sheet.A42, -1)
        self.assertEqual(sheet.A43, -2)
        self.assertEqual(sheet.A44, 0)
        self.assertEqual(sheet.A45, 0)
        self.assertEqual(sheet.A46, 2)
        self.assertEqual(sheet.A47, 1)
        self.assertEqual(sheet.A48, 1)
        self.assertEqual(sheet.A49, 2)
        self.assertEqual(sheet.A50, 0)
        self.assertEqual(sheet.A51, 0)
        self.assertEqual(sheet.A52, -2)
        self.assertEqual(sheet.A53, 50)
        self.assertEqual(sheet.A54, Units.Quantity("9.7mm"))
        self.assertEqual(sheet.getContents("A1"), "=1 < 2 ? 3 : 4")
        self.assertEqual(sheet.getContents("A2"), "=1 + 2 < 3 + 4 ? 5 + 6 : 7 + 8")
        self.assertEqual(
            sheet.getContents("A3"),
            "=1 + 2 * 1 < 3 + 4 ? 5 * 2 + 6 * 3 + 2 ^ 4 : 7 * 2 + 8 * 3 + 2 ^ 3",
        )
        self.assertEqual(sheet.getContents("A4"), "123")
        self.assertEqual(sheet.getContents("A5"), "=123 + 321")
        self.assertEqual(sheet.getContents("A6"), "=123 * 2 + 321")
        self.assertEqual(sheet.getContents("A7"), "=123 * 2 + 333 / 3")
        self.assertEqual(sheet.getContents("A8"), "=123 * (2 + 321)")
        self.assertEqual(sheet.getContents("A9"), "=3 ^ 4")
        self.assertEqual(sheet.getContents("A10"), "=3 ^ 4 * 2")
        self.assertEqual(sheet.getContents("A11"), "=3 ^ (4 * 2)")
        self.assertEqual(sheet.getContents("A12"), "=3 ^ 4 + 4")
        self.assertEqual(sheet.getContents("A13"), "=1 + 4 / 2 + 5")
        self.assertEqual(sheet.getContents("A14"), "=(3 + 6) / (1 + 2)")
        self.assertEqual(sheet.getContents("A15"), "=1 * 2 / 3 * 4")
        self.assertEqual(sheet.getContents("A16"), "=1 * 2 / (3 * 4)")
        self.assertEqual(sheet.getContents("A17"), "=3 ^ 4 ^ 2")
        self.assertEqual(sheet.getContents("A18"), "=3 ^ (4 ^ 2)")
        self.assertEqual(sheet.getContents("A19"), "=3 ^ 4 ^ 2")
        self.assertEqual(sheet.getContents("A20"), "=3 + 4 + 2")
        self.assertEqual(sheet.getContents("A21"), "=3 + 4 + 2")
        self.assertEqual(sheet.getContents("A22"), "=3 + 4 + 2")
        self.assertEqual(sheet.getContents("A23"), "=3 - 4 - 2")
        self.assertEqual(sheet.getContents("A24"), "=3 - (4 - 2)")
        self.assertEqual(sheet.getContents("A25"), "=3 - 4 - 2")
        self.assertEqual(sheet.getContents("A26"), "=3 * 4 * 2")
        self.assertEqual(sheet.getContents("A27"), "=3 * 4 * 2")
        self.assertEqual(sheet.getContents("A28"), "=3 * 4 * 2")
        self.assertEqual(sheet.getContents("A29"), "=3 / 4 / 2")
        self.assertEqual(sheet.getContents("A30"), "=3 / (4 / 2)")
        self.assertEqual(sheet.getContents("A31"), "=3 / 4 / 2")
        self.assertEqual(sheet.getContents("A32"), "=pi * 3")
        self.assertEqual(sheet.getContents("A33"), "=A32 / 3")
        self.assertEqual(sheet.getContents("A34"), "=1 < 2 ? <<A>> : <<B>>")
        self.assertEqual(sheet.getContents("A35"), "=min(A32:A33)")
        self.assertEqual(sheet.getContents("A36"), "=(1 < 2 ? 0 : 1) * 3")
        self.assertEqual(sheet.getContents("A37"), "=8 / (2 ^ 2 * 2)")
        self.assertEqual(sheet.getContents("A38"), "=2 ^ 2 * 2 / 8")
        self.assertEqual(sheet.getContents("A39"), "=2 ^ (2 * 2) / 8")
        self.assertEqual(sheet.getContents("A40"), "=8 / 2 ^ (2 * 2)")
        self.assertEqual(sheet.getContents("A41"), "=-1")
        self.assertEqual(sheet.getContents("A42"), "=-1")
        self.assertEqual(sheet.getContents("A43"), "=-(1 + 1)")
        self.assertEqual(sheet.getContents("A44"), "=-(1 - 1)")
        self.assertEqual(sheet.getContents("A45"), "=-(-1 + 1)")
        self.assertEqual(sheet.getContents("A46"), "=-(-1 + -1)")
        self.assertEqual(sheet.getContents("A47"), "=+1")
        self.assertEqual(sheet.getContents("A48"), "=+1")
        self.assertEqual(sheet.getContents("A49"), "=+(1 + 1)")
        self.assertEqual(sheet.getContents("A50"), "=+(1 - 1)")
        self.assertEqual(sheet.getContents("A51"), "=+(-1 + 1)")
        self.assertEqual(sheet.getContents("A52"), "=+(-1 + -1)")

        # More ternary operator precedence tests
        sheet.set("X1", "1")
        sheet.set("X2", "10")
        sheet.set("X3", "100")
        sheet.set("X4", "1000")
        sheet.set("Y1", "= X1 ? 0 : 1   ?   X2 ? 2 : 3   :   X3 ? 4 : 5")
        sheet.set("Y2", "= X1 + X2 ? X3 - 2 : 3 + X4")

        self.doc.recompute()
        self.assertEqual(sheet.getContents("Y1"), "=X1 ? 0 : (1 ? (X2 ? 2 : 3) : (X3 ? 4 : 5))")
        self.assertEqual(sheet.Y2, 98)

    def testImplicitRelOpChains(self):
        """Test implicit chains of relational operators"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        def check(implicit: str, explicit: str):
            sheet.set("Z1", implicit)
            sheet.set("Z2", explicit)
            self.doc.recompute()
            self.assertEqual(sheet.getContents("Z2"), sheet.getContents("Z1"))

        check("=1 < 2 < 3 ? 3 : 4", "=(1 < 2) < 3 ? 3 : 4")
        check("=1 < 2 < 3 < 4 ? 3 : 4", "=((1 < 2) < 3) < 4 ? 3 : 4")
        check("=A1 < B1 < 3 ? 3 : 4", "=(A1 < B1) < 3 ? 3 : 4")
        check("=1 < C1 < D2 ? 3 : 4", "=(1 < C1) < D2 ? 3 : 4")
        check("=X1 < B1 < D1 < 0 ? 3 : 4", "=((X1 < B1) < D1) < 0 ? 3 : 4")

    def testExplicitRelOpChaining(self):
        """Testing explicit relational operators chaining."""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        sheet.set("X1", "= (1 < 2) == (2 < 3)")
        sheet.set("X2", "= (1 < 2) == (2 > 3)")
        sheet.set("X3", "= (1 < 2) == 1")
        sheet.set("X4", "= 0 == (1 > 2)")
        self.doc.recompute()
        self.assertTrue(sheet.get("X1"))
        self.assertFalse(sheet.get("X2"))
        self.assertTrue(sheet.get("X3"))
        self.assertTrue(sheet.get("X4"))

    def testNumbers(self):
        """Test different numbers"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("A2", "1.5")
        sheet.set("A3", ".5")
        sheet.set("A4", "1e2")
        sheet.set("A5", "1E2")
        sheet.set("A6", "1e-2")
        sheet.set("A7", "1E-2")
        sheet.set("A8", "1.5e2")
        sheet.set("A9", "1.5E2")
        sheet.set("A10", "1.5e-2")
        sheet.set("A11", "1.5E-2")
        sheet.set("A12", ".5e2")
        sheet.set("A13", ".5E2")
        sheet.set("A14", ".5e-2")
        sheet.set("A15", ".5E-2")
        sheet.set("A16", "1/1")
        sheet.set("A17", "1/2")
        sheet.set("A18", "2/4")

        self.doc.recompute()

        self.assertEqual(sheet.A1, 1)
        self.assertEqual(sheet.A2, 1.5)
        self.assertEqual(sheet.A3, 0.5)
        self.assertEqual(sheet.A4, 1e2)
        self.assertEqual(sheet.A5, 1e2)
        self.assertEqual(sheet.A6, 1e-2)
        self.assertEqual(sheet.A7, 1e-2)
        self.assertEqual(sheet.A8, 1.5e2)
        self.assertEqual(sheet.A9, 1.5e2)
        self.assertEqual(sheet.A10, 1.5e-2)
        self.assertEqual(sheet.A11, 1.5e-2)
        self.assertEqual(sheet.A12, 0.5e2)
        self.assertEqual(sheet.A13, 0.5e2)
        self.assertEqual(sheet.A14, 0.5e-2)
        self.assertEqual(sheet.A15, 0.5e-2)
        self.assertEqual(sheet.A16, 1)
        self.assertEqual(sheet.A17, 0.5)
        self.assertEqual(sheet.A18, 0.5)

    def testQuantitiesAndFractionsAsNumbers(self):
        """Test quantities and simple fractions as numbers"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1mm")
        sheet.set("A2", "1/2")
        sheet.set("A3", "4mm/2")
        sheet.set("A4", "2/mm")
        sheet.set("A5", "4/2mm")
        sheet.set("A6", "6mm/3s")

        self.doc.recompute()

        self.assertEqual(sheet.A1, Units.Quantity("1 mm"))
        self.assertEqual(sheet.A2, 0.5)
        self.assertEqual(sheet.A3, Units.Quantity("2 mm"))
        self.assertEqual(sheet.A4, Units.Quantity("2 1/mm"))
        self.assertEqual(sheet.A5, Units.Quantity("2 1/mm"))
        self.assertEqual(sheet.A6, Units.Quantity("2 mm/s"))

    def testSignedQuantitiesAndFractionsAsNumbers(self):
        """A sign in front of a quantity or a simple fraction is part of it, as for plain
        numbers: "-12 mm" and "-1/2" were stored as text"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "-12 mm")
        sheet.set("A2", "+1mm")
        sheet.set("A3", "-1/2")
        sheet.set("A4", "-4mm/2")
        sheet.set("A5", "-6mm/3s")
        sheet.set("A6", "-2/mm")
        # Still text: more than one sign, a sign in the denominator, or no number after it
        sheet.set("B1", "--12 mm")
        sheet.set("B2", "1/-2")
        sheet.set("B3", "- 3")
        sheet.set("B4", "-12 mm + 1")
        self.doc.recompute()
        self.assertEqual(sheet.A1, Units.Quantity("-12 mm"))
        self.assertEqual(sheet.A2, Units.Quantity("1 mm"))
        self.assertEqual(sheet.A3, -0.5)
        self.assertEqual(sheet.A4, Units.Quantity("-2 mm"))
        self.assertEqual(sheet.A5, Units.Quantity("-2 mm/s"))
        self.assertEqual(sheet.A6, Units.Quantity("-2 1/mm"))
        for cell, text in (("B1", "--12 mm"), ("B2", "1/-2"), ("B3", "- 3"), ("B4", "-12 mm + 1")):
            self.assertEqual(sheet.getContents(cell), "'" + text)
        # The signed quantity is kept across save and restore
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "signed.FCStd")
            self.doc.saveAs(path)
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
        sheet = self.doc.getObject("Spreadsheet")
        self.doc.recompute()
        self.assertEqual(sheet.A1, Units.Quantity("-12 mm"))
        self.assertEqual(sheet.A3, -0.5)

    def testRemoveRows(self):
        """Removing rows -- check renaming of internal cells"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A3", "123")
        sheet.set("A1", "=A3")
        sheet.removeRows("2", 1)
        self.assertEqual(sheet.getContents("A1"), "=A2")

    def testInsertRows(self):
        """Inserting rows -- check renaming of internal cells"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B1", "=B2")
        sheet.set("B2", "124")
        # Calling getContents() here activates ObjectIdentifier internal cache,
        # which needs to be tested as well.
        self.assertEqual(sheet.getContents("B1"), "=B2")
        sheet.insertRows("2", 1)
        self.assertEqual(sheet.getContents("B1"), "=B3")

    def testIssue3225(self):
        """Inserting rows -- check renaming of internal cells"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B2", "25")
        sheet.set("B3", "=B2")
        sheet.insertRows("2", 1)
        self.assertEqual(sheet.getContents("B4"), "=B3")

    def testRenameAlias(self):
        """Test renaming of alias1 to alias2 in a spreadsheet"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B1", "124")
        sheet.setAlias("B1", "alias1")
        sheet.set("B2", "=alias1")
        self.doc.recompute()
        self.assertEqual(sheet.get("alias1"), 124)
        self.assertEqual(sheet.get("B1"), 124)
        self.assertEqual(sheet.get("B2"), 124)
        sheet.setAlias("B1", "alias2")
        self.doc.recompute()
        self.assertEqual(sheet.get("alias2"), 124)
        self.assertEqual(sheet.getContents("B2"), "=alias2")

    def testRenameAndMovePropertyReferencedBelowIt(self):
        """Cells referring below a renamed or moved dynamic property follow it"""
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyPlacement", "Pos")
        varset.Pos = FreeCAD.Placement(FreeCAD.Vector(1, 2, 3), FreeCAD.Rotation())
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=VarSet.Pos.Base.y")
        sheet.set("A2", "=VarSet.Pos")
        self.doc.recompute()
        varset.renameProperty("Pos", "NewPos")
        self.assertEqual(sheet.getContents("A1"), "=VarSet.NewPos.Base.y")
        self.assertEqual(sheet.getContents("A2"), "=VarSet.NewPos")
        other = self.doc.addObject("App::VarSet", "VarSet2")
        varset.moveProperty("NewPos", other)
        self.assertEqual(sheet.getContents("A1"), "=VarSet2.NewPos.Base.y")
        self.assertEqual(sheet.getContents("A2"), "=VarSet2.NewPos")
        self.doc.recompute()
        self.assertEqual(sheet.A1, FreeCAD.Units.Quantity("2 mm"))

    def testReferenceToMissingObjectByLabelKeepsQuotes(self):
        """A reference by a label that is not an identifier (<<My Sheet>>.A1) lost its quotes
        while no object had that label (not created yet, or deleted): the cell turned into
        text when the object appeared, and the expression was lost after saving it twice"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=<<Later Sheet>>.A1 * 2")
        varset = self.doc.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyFloat", "Result")
        varset.setExpression("Result", "<<Later Sheet>>.A1 + 1")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "=<<Later Sheet>>.A1 * 2")
        self.assertEqual(varset.ExpressionEngine, [("Result", "<<Later Sheet>>.A1 + 1")])

        later = self.doc.addObject("Spreadsheet::Sheet", "Later")
        later.Label = "Later Sheet"
        later.set("A1", "4")
        # The reference to a missing object gave the sheet no dependency on it, so the document
        # does not know to recompute it first (as with a reference by name): do it here
        later.recompute()
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "=<<Later Sheet>>.A1 * 2")
        self.assertEqual(sheet.A1, 8)
        self.assertEqual(varset.ExpressionEngine, [("Result", "<<Later Sheet>>.A1 + 1")])

        self.doc.removeObject("Later")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            for name in ("first.FCStd", "second.FCStd"):
                path = os.path.join(temp_dir, name)
                self.doc.saveAs(path)
                FreeCAD.closeDocument(self.doc.Name)
                self.doc = FreeCAD.openDocument(path)
                sheet = self.doc.getObject("Spreadsheet")
                varset = self.doc.getObject("VarSet")
                self.assertEqual(sheet.getContents("A1"), "=<<Later Sheet>>.A1 * 2", name)
                self.assertEqual(
                    varset.ExpressionEngine, [("Result", "<<Later Sheet>>.A1 + 1")], name
                )

    def testRenameAlias2(self):
        """Test renaming of alias1 to alias2 in a spreadsheet, when referenced from another object"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B1", "124")
        sheet.setAlias("B1", "alias1")
        box = self.doc.addObject("Part::Box", "Box")
        box.setExpression("Length", "Spreadsheet.alias1")
        sheet.setAlias("B1", "alias2")
        self.assertEqual(box.ExpressionEngine[0][1], "Spreadsheet.alias2")

    def testRenameAlias3(self):
        """Test renaming of document object referenced from another object"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("B1", "124")
        sheet.setAlias("B1", "alias1")
        box = self.doc.addObject("Part::Box", "Box")
        box.setExpression("Length", "Spreadsheet.alias1")
        box2 = self.doc.addObject("Part::Box", "Box")
        box2.setExpression("Length", "<<Spreadsheet>>.alias1")
        sheet.Label = "Params"
        self.assertEqual(box.ExpressionEngine[0][1], "Spreadsheet.alias1")
        self.assertEqual(box2.ExpressionEngine[0][1], "<<Params>>.alias1")

    def testNonUtf8StringArguments(self):
        """Strings that cannot be encoded as UTF-8 raise instead of crashing"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        bad = "\ud800"
        with self.assertRaises(UnicodeEncodeError):
            sheet.setAlias("A1", bad)
        with self.assertRaises(UnicodeEncodeError):
            sheet.setStyle("A1", bad)
        with self.assertRaises(UnicodeEncodeError):
            sheet.setStyle("A1", {bad})
        with self.assertRaises(UnicodeEncodeError):
            sheet.setAlignment("A1", bad)
        with self.assertRaises(UnicodeEncodeError):
            sheet.setAlignment("A1", {bad})
        sheet.setAlias("A1", "Good")
        sheet.setStyle("A1", "bold|italic")
        sheet.setAlignment("A1", {"left"})
        self.assertEqual(sheet.getAlias("A1"), "Good")
        self.assertEqual(sheet.getStyle("A1"), {"bold", "italic"})

    def testAlias(self):
        """Playing with aliases"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.setAlias("A1", "Test")
        self.assertEqual(sheet.getAlias("A1"), "Test")

        sheet.set("A1", "4711")
        self.doc.recompute()
        self.assertEqual(sheet.get("Test"), 4711)
        self.assertEqual(sheet.get("Test"), sheet.get("A1"))

    def testAmbiguousAlias(self):
        """Try to set the same alias twice (bug #2402)"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.setAlias("A1", "Test")
        try:
            sheet.setAlias("A2", "Test")
            self.fail("An ambiguous alias was set which shouldn't be allowed")
        except Exception:
            self.assertEqual(sheet.getAlias("A2"), None)

    def testClearAlias(self):
        """This was causing a crash"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.setAlias("A1", "Test")
        sheet.setAlias("A1", "")
        self.assertEqual(sheet.getAlias("A1"), None)

    def testMovedAliasUpdatesDependants(self):
        """Issue #18207: a cell referring to an alias must follow the alias
        when it is moved to another cell (cut and paste)"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.set("A1", "5")
        sheet.setAlias("A1", "Var1")
        sheet.set("B4", "=Var1 + 1")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 6)
        # What cut A1 and paste into C10 does
        sheet.clear("A1")
        sheet.set("C10", "7")
        sheet.setAlias("C10", "Var1")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 8)
        sheet.set("C10", "9")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 10)

    def testMovedAliasUpdatesDependantsOfComputedSheet(self):
        """Issue #18207: same as testMovedAliasUpdatesDependants, with the
        reference entered after the aliased cell was computed (it then
        resolves to the cell, not to the alias name)"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.set("A1", "5")
        sheet.setAlias("A1", "Var1")
        self.doc.recompute()
        sheet.set("B4", "=Var1 + 1")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 6)
        # What cut A1 and paste into C10 does. (Removing the alias with
        # setAlias("A1", "") instead rewrites B4 to "=A1 + 1".)
        sheet.clear("A1")
        sheet.set("C10", "7")
        sheet.setAlias("C10", "Var1")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 8)
        sheet.set("C10", "9")
        self.doc.recompute()
        self.assertEqual(sheet.B4, 10)
        # What cut C10 and paste into E5 does
        sheet.set("D1", "=Var1 + 1")
        self.doc.recompute()
        sheet.clear("C10")
        sheet.set("E5", "20")
        sheet.setAlias("E5", "Var1")
        self.doc.recompute()
        self.assertEqual((sheet.B4, sheet.D1), (21, 21))
        sheet.set("E5", "30")
        self.doc.recompute()
        self.assertEqual((sheet.B4, sheet.D1), (31, 31))

    def testAliasDefinedAfterReferenceUpdatesDependants(self):
        """Issue #18207: a cell referring to an alias that is defined later
        must be updated when the aliased cell changes"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        sheet.set("A1", "=Var1 + 1")
        sheet.set("A5", "5")
        sheet.setAlias("A5", "Var1")
        self.doc.recompute()
        self.assertEqual(sheet.A1, 6)
        sheet.set("A5", "6")
        self.doc.recompute()
        self.assertEqual(sheet.A1, 7)

    def testSetInvalidAlias(self):
        """Try to use a cell address as alias name"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        try:
            sheet.setAlias("A1", "B1")
        except Exception:
            self.assertEqual(sheet.getAlias("A1"), None)
        else:
            self.fail("A cell address was used as alias which shouldn't be allowed")

    def testSetInvalidAlias2(self):
        """Try to use a unit (reserved word) as alias name"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        try:
            sheet.setAlias("A1", "mA")
        except Exception as err:
            self.assertIn("reserved unit token", str(err))
            self.assertEqual(sheet.getAlias("A1"), None)
        else:
            self.fail("A unit (reserved word) was used as alias which shouldn't be allowed")

    def testSetInvalidAliasConstant(self):
        """Try to use a constant (reserved word) as alias name"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Calc")
        try:
            sheet.setAlias("A1", "pi")
        except Exception as err:
            self.assertIn("reserved constant token", str(err))
            self.assertEqual(sheet.getAlias("A1"), None)
        else:
            self.fail("A constant (reserved word) was used as alias which shouldn't be allowed")

    def testPlacementName(self):
        """Object name is equal to property name (bug #2389)"""
        if not FreeCAD.GuiUp:
            return

        import FreeCADGui

        o = self.doc.addObject("Part::FeaturePython", "Placement")
        FreeCADGui.Selection.addSelection(o)

    def testInvoluteGear(self):
        """Support of boolean or integer values"""
        try:
            import InvoluteGearFeature
        except ImportError:
            return
        InvoluteGearFeature.makeInvoluteGear("InvoluteGear")
        self.doc.recompute()
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.LineSegment(v(0, 0, 0), v(10, 10, 0)), False)
        sketch.addConstraint(Sketcher.Constraint("Distance", 0, 65.285388))
        sketch.setExpression("Constraints[0]", "InvoluteGear.NumberOfTeeth")
        self.doc.recompute()
        self.assertIn("Up-to-date", sketch.State)

    def testSketcher(self):
        """Mixup of Label and Name (bug #2407)"""
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.setAlias("A1", "Length")
        self.doc.recompute()
        sheet.set("A1", "47,11")
        self.doc.recompute()

        index = sketch.addGeometry(Part.LineSegment(v(0, 0, 0), v(10, 10, 0)), False)
        sketch.addConstraint(Sketcher.Constraint("Distance", index, 14.0))
        self.doc.recompute()
        sketch.setExpression("Constraints[0]", "<<Spreadsheet>>.Length")
        self.doc.recompute()
        sheet.Label = "Calc"
        self.doc.recompute()
        self.assertEqual(sketch.ExpressionEngine[0][1], "<<Calc>>.Length")
        self.assertIn("Up-to-date", sketch.State)

    def testCrossDocumentLinks(self):
        """Expressions across files are not saved (bug #2442)"""

        # Create a box
        box = self.doc.addObject("Part::Box", "Box")

        # Create a second document with a cylinder
        doc2 = FreeCAD.newDocument()
        cylinder = doc2.addObject("Part::Cylinder", "Cylinder")
        cylinder.setExpression("Radius", "cube#Cube.Height")

        # Save and close first document
        self.doc.saveAs(self.TempPath + os.sep + "cube.fcstd")
        FreeCAD.closeDocument(self.doc.Name)

        # Save and close second document
        doc2.saveAs(self.TempPath + os.sep + "cylinder.fcstd")
        FreeCAD.closeDocument(doc2.Name)

        # Open both documents again
        self.doc = FreeCAD.openDocument(self.TempPath + os.sep + "cube.fcstd")
        doc2 = FreeCAD.openDocument(self.TempPath + os.sep + "cylinder.fcstd")

        # Check reference between them
        self.assertEqual(doc2.getObject("Cylinder").ExpressionEngine[0][1], "cube#Cube.Height")

        # Close second document
        FreeCAD.closeDocument(doc2.Name)

    def testMatrix(self):
        """Test Matrix/Vector/Placement/Rotation operations"""

        def plm_equal(plm1, plm2):
            from math import sqrt

            qpair = zip(plm1.Rotation.Q, plm2.Rotation.Q)
            qdiff1 = sqrt(sum([(v1 - v2) ** 2 for v1, v2 in qpair]))
            qdiff2 = sqrt(sum([(v1 + v2) ** 2 for v1, v2 in qpair]))
            return (plm1.Base - plm2.Base).Length < 1e-7 and (qdiff1 < 1e-12 or qdiff2 < 1e-12)

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        mat = FreeCAD.Matrix()
        mat.scale(2, 1, 2)
        imat = mat.inverse()

        vec = FreeCAD.Vector(2, 1, 2)

        rot = FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 45)
        irot = rot.inverted()

        pla = FreeCAD.Placement(vec, rot)
        ipla = pla.inverse()

        sheet.set("A1", "=vector(2, 1, 2)")

        # different ways of calling mscale()
        sheet.set("B1", "=mscale(create(<<matrix>>), A1)")
        sheet.set("C1", "=mscale(create(<<matrix>>), tuple(2, 1, 2))")
        sheet.set("A2", "=mscale(create(<<matrix>>), 2, 1, 2)")

        # test matrix power operation
        sheet.set("B2", "=A2^-2")
        sheet.set("C2", "=A2^-1")
        sheet.set("D2", "=A2^0")
        sheet.set("E2", "=A2^1")
        sheet.set("F2", "=A2^2")
        sheet.set("G2", "=matrix(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)")
        sheet.set("H2", "=G2^-1")

        sheet.set("A3", "=rotation(vector(0, 1, 0), 45)")

        # test rotation power operation
        sheet.set("B3", "=A3^-2")
        sheet.set("C3", "=A3^-1")
        sheet.set("D3", "=A3^0")
        sheet.set("E3", "=A3^1")
        sheet.set("F3", "=A3^2")

        sheet.set("A4", "=placement(A1, A3)")

        # test placement power operation
        sheet.set("B4", "=A4^-2")
        sheet.set("C4", "=A4^-1")
        sheet.set("D4", "=A4^0")
        sheet.set("E4", "=A4^1")
        sheet.set("F4", "=A4^2")

        # vector transformation with mixing matrix and placement and rotation
        sheet.set("A5", "=A2*A3*A4*A1")
        sheet.set("B5", "=B2*B4*B3*A1")
        sheet.set("C5", "=C3*C2*C4*A1")
        sheet.set("D5", "=D3*D4*D2*A1")
        sheet.set("E5", "=E4*E2*E3*A1")
        sheet.set("F5", "=F3*F4*F2*A1")

        # inverse of the above transformation with power -1 and minvert()
        sheet.set("A6", "=A4^-1 * minvert(A3) * A2^-1 * A5")
        sheet.set("B6", "=minvert(B3) * B4^-1 * minvert(B2) * B5")
        sheet.set("C6", "=C4^-1 * C2^-1 * C3^-1 * C5")
        sheet.set("D6", "=minvert(D4*D2) * minvert(D3) * D5")
        sheet.set("E6", "=(E2 * E3)^-1 * E4^-1 * E5")
        sheet.set("F6", "=(F3*F4*F2)^-1 * F5")

        # Rotate and translate.
        sheet.set("A7", "=placement(vector(1; 2; 3), vector(1; 0; 0); 0)")
        sheet.set("B7", "=mrotate(A7; vector(1; 0; 0); 90)")
        sheet.set("C7", "=mrotatex(A7; 90)")
        sheet.set("D7", "=mrotatey(A7; 90)")
        sheet.set("E7", "=mrotatez(A7; 90)")
        sheet.set("F7", "=mtranslate(A7; vector(1; 2; 3))")
        sheet.set("G7", "=mtranslate(A7; 1; 2; 3)")

        # Compatibility with old syntax.
        sheet.set("A8", "=create(<<vector>>, 2, 1, 2)")
        sheet.set("B8", "=create(<<rotation>>, create(<<vector>>, 0, 1, 0), 45)")
        sheet.set("C8", "=create(<<placement>>, A8, B8)")

        self.doc.recompute()

        self.assertEqual(sheet.A1, vec)

        self.assertEqual(sheet.B1, mat)
        self.assertEqual(sheet.C1, mat)
        self.assertEqual(sheet.A2, mat)

        self.assertEqual(sheet.B2, imat * imat)
        self.assertEqual(sheet.B2, mat**-2)
        self.assertEqual(sheet.C2, imat)
        self.assertEqual(sheet.C2, mat**-1)
        self.assertEqual(sheet.D2, FreeCAD.Matrix())
        self.assertEqual(sheet.D2, mat**0)
        self.assertEqual(sheet.E2, mat)
        self.assertEqual(sheet.E2, mat**1)
        self.assertEqual(sheet.F2, mat * mat)
        self.assertEqual(sheet.F2, mat**2)

        self.assertTrue(sheet.H2.startswith("ERR: Cannot invert singular matrix"))

        self.assertEqual(sheet.A3, rot)

        rtol = 1e-12
        self.assertTrue(sheet.B3.isSame(irot * irot, rtol))
        self.assertTrue(sheet.B3.isSame(rot**-2, rtol))
        self.assertTrue(sheet.C3.isSame(irot, rtol))
        self.assertTrue(sheet.C3.isSame(rot**-1, rtol))
        self.assertTrue(sheet.D3.isSame(FreeCAD.Rotation(), rtol))
        self.assertTrue(sheet.D3.isSame(rot**0, rtol))
        self.assertTrue(sheet.E3.isSame(rot, rtol))
        self.assertTrue(sheet.E3.isSame(rot**1, rtol))
        self.assertTrue(sheet.F3.isSame(rot * rot, rtol))
        self.assertTrue(sheet.F3.isSame(rot**2, rtol))

        self.assertEqual(sheet.A4, pla)

        self.assertTrue(plm_equal(sheet.B4, ipla * ipla))
        self.assertTrue(plm_equal(sheet.B4, pla**-2))
        self.assertTrue(plm_equal(sheet.C4, ipla))
        self.assertTrue(plm_equal(sheet.C4, pla**-1))
        self.assertTrue(plm_equal(sheet.D4, FreeCAD.Placement()))
        self.assertTrue(plm_equal(sheet.D4, pla**0))
        self.assertTrue(plm_equal(sheet.E4, pla))
        self.assertTrue(plm_equal(sheet.E4, pla**1))
        self.assertTrue(plm_equal(sheet.F4, pla * pla))
        self.assertTrue(plm_equal(sheet.F4, pla**2))

        tol = 1e-10

        self.assertLess(
            sheet.A5.distanceToPoint(
                sheet.A2.multiply(sheet.A3.Matrix).multiply(sheet.A4.Matrix).multVec(vec)
            ),
            tol,
        )
        self.assertLess(
            sheet.B5.distanceToPoint(
                sheet.B2.multiply(sheet.B4.Matrix).multiply(sheet.B3.Matrix).multVec(vec)
            ),
            tol,
        )
        self.assertLess(
            sheet.C5.distanceToPoint(
                sheet.C3.Matrix.multiply(sheet.C2).multiply(sheet.C4.Matrix).multVec(vec)
            ),
            tol,
        )
        self.assertLess(
            sheet.D5.distanceToPoint(
                sheet.D3.Matrix.multiply(sheet.D4.Matrix).multiply(sheet.D2).multVec(vec)
            ),
            tol,
        )
        self.assertLess(
            sheet.E5.distanceToPoint(
                sheet.E4.Matrix.multiply(sheet.E2).multiply(sheet.E3.Matrix).multVec(vec)
            ),
            tol,
        )
        self.assertLess(
            sheet.F5.distanceToPoint(
                sheet.F3.Matrix.multiply(sheet.F4.Matrix).multiply(sheet.F2).multVec(vec)
            ),
            tol,
        )

        self.assertLess(sheet.A6.distanceToPoint(vec), tol)
        self.assertLess(sheet.B6.distanceToPoint(vec), tol)
        self.assertLess(sheet.C6.distanceToPoint(vec), tol)
        self.assertLess(sheet.D6.distanceToPoint(vec), tol)
        self.assertLess(sheet.E6.distanceToPoint(vec), tol)
        self.assertLess(sheet.F6.distanceToPoint(vec), tol)

        self.assertTrue(sheet.A7.Base.isEqual(FreeCAD.Vector(1, 2, 3), tol))
        self.assertTrue(sheet.B7.Base.isEqual(FreeCAD.Vector(1, -3, 2), tol))
        self.assertTrue(sheet.C7.Base.isEqual(FreeCAD.Vector(1, -3, 2), tol))
        self.assertTrue(sheet.D7.Base.isEqual(FreeCAD.Vector(3, 2.0, -1), tol))
        self.assertTrue(sheet.E7.Base.isEqual(FreeCAD.Vector(-2, 1, 3.0), tol))
        self.assertTrue(sheet.F7.Base.isEqual(FreeCAD.Vector(2, 4, 6), tol))
        self.assertTrue(sheet.G7.Base.isEqual(FreeCAD.Vector(2, 4, 6), tol))

        self.assertEqual(sheet.A8, vec)
        self.assertEqual(sheet.B8, rot)
        self.assertEqual(sheet.C8, pla)

    def testIssue19517(self):
        """Regression test for issue 19517; mod should work with units"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=mod(7mm;3mm)")
        self.doc.recompute()
        self.assertEqual(sheet.A1, Units.Quantity("1 mm"))
        try:
            sheet.set("A2", "=mod(7kg;3mm)")
            self.doc.recompute()
            self.fail("Units need to be the same or dimensionless")
        except Exception:
            pass

    def testIssue3363(self):
        """Regression test for issue 3363; Nested conditionals statement fails with additional conditional statement in false-branch"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("B1", "=A1==1?11:(A1==2?12:13)")
        sheet.set("C1", "=A1==1?(A1==2?12:13) : 11")
        self.doc.recompute()

        # Save and close first document
        self.doc.saveAs(self.TempPath + os.sep + "conditionals.fcstd")
        FreeCAD.closeDocument(self.doc.Name)

        # Open documents again
        self.doc = FreeCAD.openDocument(self.TempPath + os.sep + "conditionals.fcstd")

        sheet = self.doc.getObject("Spreadsheet")
        self.assertEqual(sheet.getContents("B1"), "=A1 == 1 ? 11 : (A1 == 2 ? 12 : 13)")
        self.assertEqual(sheet.getContents("C1"), "=A1 == 1 ? (A1 == 2 ? 12 : 13) : 11")

    def testIssue3432(self):
        """Regression test for issue 3432; numbers with units are ignored from aggregates"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1mm")
        sheet.set("B1", "2mm")
        sheet.set("C1", "=max(A1:B1;3mm)")
        self.doc.recompute()
        self.assertEqual(sheet.get("C1"), Units.Quantity("3 mm"))

    def testIssue4156(self):
        """Regression test for issue 4156; necessarily use of leading '=' to enter an expression, creates inconsistent behavior depending on the spreadsheet state"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A3", "A1")
        sheet.set("A1", "1000")
        self.doc.recompute()
        sheet.set("A3", "")
        sheet.set("A3", "A1")
        self.assertEqual(sheet.getContents("A3"), "'A1")

    def testInsertRowsAlias(self):
        """Regression test for issue 4429; insert rows to sheet with aliases"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A3", "1")
        sheet.setAlias("A3", "alias1")
        sheet.set("A4", "=alias1 + 1")
        sheet.setAlias("A4", "alias2")
        sheet.set("A5", "=alias2 + 1")
        self.doc.recompute()
        sheet.insertRows("1", 1)
        self.doc.recompute()
        self.assertEqual(sheet.A6, 3)

    def testInsertColumnsAlias(self):
        """Regression test for issue 4429; insert columns to sheet with aliases"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("C1", "1")
        sheet.setAlias("C1", "alias1")
        sheet.set("D1", "=alias1 + 1")
        sheet.setAlias("D1", "alias2")
        sheet.set("E1", "=alias2 + 1")
        self.doc.recompute()
        sheet.insertColumns("A", 1)
        self.doc.recompute()
        self.assertEqual(sheet.F1, 3)

    def testRemoveRowsAlias(self):
        """Regression test for issue 4429; remove rows from sheet with aliases"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A3", "1")
        sheet.setAlias("A3", "alias1")
        sheet.set("A5", "=alias1 + 1")
        sheet.setAlias("A5", "alias2")
        sheet.set("A4", "=alias2 + 1")
        self.doc.recompute()
        sheet.removeRows("1", 1)
        self.doc.recompute()
        self.assertEqual(sheet.A3, 3)

    def testUndoRemoveRowsKeepsAliases(self):
        """Issue #29862: undoing a row removal must not break the aliases
        that move back down"""
        self.doc.UndoMode = 1
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for row, name in ((1, "alias1"), (2, "alias2"), (3, "alias3"), (5, "alias5")):
            sheet.set("B%d" % row, str(row))
            sheet.setAlias("B%d" % row, name)
        self.doc.recompute()
        self.doc.openTransaction("Remove row")
        sheet.removeRows("3", 1)
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(sheet.getCellFromAlias("alias5"), "B4")
        self.doc.undo()
        self.doc.recompute()
        for row, name in ((1, "alias1"), (2, "alias2"), (3, "alias3"), (5, "alias5")):
            self.assertEqual(sheet.getAlias("B%d" % row), name)
            self.assertEqual(sheet.getCellFromAlias(name), "B%d" % row)
            self.assertEqual(getattr(sheet, name), row)
        self.assertEqual(sheet.getAlias("B4"), None)

    def testUndoInsertRowsKeepsAliases(self):
        """Issue #29862: undoing a row insertion must not break the aliases
        that move back up"""
        self.doc.UndoMode = 1
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for row, name in ((1, "alias1"), (2, "alias2"), (4, "alias4"), (5, "alias5")):
            sheet.set("B%d" % row, str(row))
            sheet.setAlias("B%d" % row, name)
        sheet.set("C1", "=alias5 * 2")
        self.doc.recompute()
        self.doc.openTransaction("Insert row")
        sheet.insertRows("3", 1)
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(sheet.getCellFromAlias("alias5"), "B6")
        self.doc.undo()
        self.doc.recompute()
        for row, name in ((1, "alias1"), (2, "alias2"), (4, "alias4"), (5, "alias5")):
            self.assertEqual(sheet.getAlias("B%d" % row), name)
            self.assertEqual(sheet.getCellFromAlias(name), "B%d" % row)
            self.assertEqual(getattr(sheet, name), row)
        self.assertEqual(sheet.getAlias("B6"), None)
        sheet.set("B5", "7")
        self.doc.recompute()
        self.assertEqual(sheet.C1, 14)

    def testRowsAndColumnsMoveAliasDependants(self):
        """A cell referring to an alias must follow the alias when inserting or
        removing rows or columns moves the aliased cell, also after undo/redo,
        and must no longer depend on the address the alias had before"""

        def transaction(doc, name, func):
            doc.openTransaction(name)
            func()
            doc.commitTransaction()
            doc.recompute()

        def check(op, aliasCell, movedE1):
            doc = FreeCAD.newDocument("AliasDeps")
            try:
                doc.UndoMode = 1
                sheet = doc.addObject("Spreadsheet::Sheet", "Sheet")
                for row in range(1, 7):
                    sheet.set("C%d" % row, str(row))
                sheet.setAlias("C4", "cfour")
                sheet.set("A1", "=cfour * 2")  # does not move
                sheet.set("E1", "=cfour * 3")  # moves with the columns
                doc.recompute()
                self.assertEqual((sheet.A1, sheet.E1), (8, 12))

                def values():
                    return (sheet.A1, sheet.get(movedE1))

                transaction(doc, "op", lambda: op(sheet))
                self.assertEqual(sheet.getCellFromAlias("cfour"), aliasCell, aliasCell)
                self.assertEqual(values(), (8, 12), aliasCell)
                # The dependants follow the alias...
                transaction(doc, "value", lambda: sheet.set(aliasCell, "10"))
                self.assertEqual(values(), (20, 30), aliasCell)
                # ...and no longer depend on C4 (that would be a cycle)
                transaction(doc, "C4", lambda: sheet.set("C4", "=A1 + 1"))
                self.assertEqual(sheet.C4, 21, aliasCell)
                for _ in range(3):
                    doc.undo()
                doc.recompute()
                self.assertEqual(sheet.getCellFromAlias("cfour"), "C4", aliasCell)
                self.assertEqual((sheet.A1, sheet.E1), (8, 12), aliasCell)
                doc.redo()  # op
                doc.recompute()
                self.assertEqual(sheet.getCellFromAlias("cfour"), aliasCell, aliasCell)
                self.assertEqual(values(), (8, 12), aliasCell)
                transaction(doc, "value", lambda: sheet.set(aliasCell, "5"))
                self.assertEqual(values(), (10, 15), aliasCell)
                doc.undo()  # value
                doc.undo()  # op
                doc.recompute()
                self.assertEqual(sheet.getCellFromAlias("cfour"), "C4", aliasCell)
                transaction(doc, "value", lambda: sheet.set("C4", "7"))
                self.assertEqual((sheet.A1, sheet.E1), (14, 21), aliasCell)
            finally:
                FreeCAD.closeDocument(doc.Name)

        check(lambda sheet: sheet.removeRows("3", 1), "C3", "E1")
        check(lambda sheet: sheet.insertRows("2", 1), "C5", "E1")
        check(lambda sheet: sheet.removeColumns("B", 1), "B4", "D1")
        check(lambda sheet: sheet.insertColumns("B", 1), "D4", "F1")

    def testUndoKeepsDefaultColors(self):
        """Issue #30477: undo must not give explicit colors to cells that
        use the default ones"""
        self.doc.UndoMode = 1
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.doc.openTransaction("Set A1")
        sheet.set("A1", "1")
        sheet.set("B1", "2")
        sheet.setForeground("B1", (1.0, 0.0, 0.0, 1.0))
        sheet.setBackground("B1", (0.0, 0.0, 1.0, 1.0))
        self.doc.commitTransaction()
        self.doc.openTransaction("Set A2")
        sheet.set("A2", "2")
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertIsNone(sheet.getForeground("A1"))
        self.assertIsNone(sheet.getBackground("A1"))
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A2"), "")
        self.assertIsNone(sheet.getForeground("A1"))
        self.assertIsNone(sheet.getBackground("A1"))
        self.assertEqual(sheet.getForeground("B1"), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(sheet.getBackground("B1"), (0.0, 0.0, 1.0, 1.0))

    def testHugeColorComponentRaisesOverflowError(self):
        """An int color component that does not fit into a C long raised SystemError
        ("returned a result with an exception set") after setting the cell color"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for setter in (sheet.setForeground, sheet.setBackground):
            with self.assertRaises(OverflowError):
                setter("A1", (2**70, 0, 0))
        self.assertIsNone(sheet.getForeground("A1"))
        self.assertIsNone(sheet.getBackground("A1"))

    def testSetBlackForegroundAndWhiteBackground(self):
        """Issue #24481: black text and white background must be settable
        (the default colors depend on the theme), also on a range and after
        a color was cleared"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.setForeground("A1", (0.0, 0.0, 0.0))
        sheet.setBackground("A1", (1.0, 1.0, 1.0))
        self.assertEqual(sheet.getForeground("A1"), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(sheet.getBackground("A1"), (1.0, 1.0, 1.0, 1.0))
        sheet.setForeground("B1:C2", (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(sheet.getForeground("C2"), (0.0, 0.0, 0.0, 1.0))
        sheet.setForeground("D1", (1.0, 0.0, 0.0))
        sheet.clearForeground("D1")
        self.assertIsNone(sheet.getForeground("D1"))
        sheet.setForeground("D1", (1.0, 0.0, 0.0))
        self.assertEqual(sheet.getForeground("D1"), (1.0, 0.0, 0.0, 1.0))
        sheet.setBackground("D1", (0.0, 1.0, 0.0))
        sheet.clearBackground("D1")
        sheet.setBackground("D1", (0.0, 1.0, 0.0))
        self.assertEqual(sheet.getBackground("D1"), (0.0, 1.0, 0.0, 1.0))
        # The explicit colors survive save and restore
        filename = os.path.join(self.TempPath, "SpreadsheetBlackForeground.FCStd")
        self.doc.saveAs(filename)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(filename)
        sheet = self.doc.getObject("Spreadsheet")
        self.assertEqual(sheet.getForeground("A1"), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(sheet.getBackground("A1"), (1.0, 1.0, 1.0, 1.0))

    def testColorRoundTripWithNone(self):
        """Issue #11865: getForeground()/getBackground() return None for a cell
        without a color; passing that back to the setters must reset the color
        instead of raising TypeError"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.setBackground("A1", sheet.getBackground("A1"))
        sheet.setForeground("A1", sheet.getForeground("A1"))
        self.assertIsNone(sheet.getBackground("A1"))
        self.assertIsNone(sheet.getForeground("A1"))
        sheet.setBackground("A1:B2", (1.0, 0.0, 0.0))
        sheet.setForeground("A1:B2", (0.0, 1.0, 0.0))
        sheet.setBackground("A1:B2", None)
        sheet.setForeground("A1:B1", None)
        self.assertIsNone(sheet.getBackground("A1"))
        self.assertIsNone(sheet.getBackground("B2"))
        self.assertIsNone(sheet.getForeground("B1"))
        self.assertEqual(sheet.getForeground("B2"), (0.0, 1.0, 0.0, 1.0))
        with self.assertRaises(TypeError):
            sheet.setBackground("A1", "red")

    def testInsertRemoveZeroRowsColumns(self):
        """Inserting or removing zero (or a negative number of) rows/columns
        used to move every following cell onto itself, which freed the cell
        and crashed (access violation)"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("B2", "=A1 + 1")
        sheet.setAlias("B2", "res")
        for count in (0, -1):
            sheet.insertColumns("A", count)
            sheet.removeColumns("A", count)
            sheet.insertRows("1", count)
            sheet.removeRows("1", count)
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "1")
        self.assertEqual(sheet.getContents("B2"), "=A1 + 1")
        self.assertEqual(sheet.getAlias("B2"), "res")
        self.assertEqual(sheet.res, 2)
        self.assertEqual(sorted(sheet.getUsedCells()), ["A1", "B2"])

    def testRemoveRowsColumnsNextToMergedCells(self):
        """Removing rows/columns that overlap the end of a merged cell, or that
        lie right after it, gave the merged cell a negative span (saved to the
        file as rowSpan="-2"), and later edits of the sheet crashed"""
        import io
        import re
        import zipfile

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        def spans():
            data = bytes(sheet.dumpPropertyContent("cells"))
            archive = zipfile.ZipFile(io.BytesIO(data))
            xml = archive.read(archive.namelist()[0]).decode()
            return {
                m.group(1): (int(m.group(2)), int(m.group(3)))
                for m in re.finditer(r'address="(\w+)"[^>]*rowSpan="(-?\d+)" colSpan="(-?\d+)"', xml)
            }

        sheet.set("B1", "1")
        sheet.mergeCells("B1:B4")
        sheet.set("D1", "2")
        sheet.mergeCells("D1:G1")
        sheet.set("A10", "3")
        sheet.mergeCells("A10:A11")
        sheet.set("C20", "4")
        sheet.mergeCells("C20:C25")
        # Overlaps the end of B1:B4 -> B1:B2 (A10:A11 -> A7:A8, C20:C25 -> C17:C22)
        sheet.removeRows("3", 3)
        # Overlaps the end of D1:G1 -> D1:E1
        sheet.removeColumns("F", 4)
        # Right below A7:A8 -> unchanged (C17:C22 -> C15:C20)
        sheet.removeRows("9", 2)
        # Inside C15:C20 -> C15:C18
        sheet.removeRows("18", 2)
        self.assertEqual(
            spans(), {"B1": (2, 1), "D1": (1, 2), "A7": (2, 1), "C15": (4, 1)}
        )
        # Must not crash on the merged cell bookkeeping
        sheet.insertColumns("A", 2)
        sheet.mergeCells("E2:F3")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("D1"), "1")

    def testInsertRemoveRowsColumnsWithAliasRange(self):
        """Inserting or removing rows/columns moves the aliases before their cells. A range
        made of aliases (sum(first:last)) in a cell moved in between could then not be
        resolved: the operation stopped half-way with "Invalid cell address 'last'" and left
        the sheet half-moved"""
        ops = [
            # operation, formula cells after it, alias cells after it
            (lambda s: s.insertRows("1", 1), ("B3", "D7"), ("C4", "C6")),
            (lambda s: s.removeRows("1", 1), ("B1", "D5"), ("C2", "C4")),
            (lambda s: s.insertColumns("A", 1), ("C2", "E6"), ("D3", "D5")),
            (lambda s: s.removeColumns("A", 1), ("A2", "C6"), ("B3", "B5")),
        ]
        for index, (op, formulas, aliases) in enumerate(ops):
            sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet%d" % index)
            sheet.set("C3", "1")
            sheet.set("C4", "2")
            sheet.set("C5", "3")
            sheet.setAlias("C3", "first")
            sheet.setAlias("C5", "last")
            sheet.set("B2", "=sum(first:last)")  # above/left of the aliases
            sheet.set("D6", "=sum(first:last)")  # below/right of the aliases
            self.doc.recompute()
            op(sheet)
            self.doc.recompute()
            self.assertEqual(
                (sheet.getCellFromAlias("first"), sheet.getCellFromAlias("last")), aliases, index
            )
            for cell in formulas:
                self.assertEqual(sheet.getContents(cell), "=sum(first:last)", (index, cell))
                self.assertEqual(sheet.get(cell), 6, (index, cell))
            self.assertEqual(len(sheet.getNonEmptyCells()), 5, index)
            # The dependencies follow the moved range
            sheet.set(aliases[0], "11")
            self.doc.recompute()
            for cell in formulas:
                self.assertEqual(sheet.get(cell), 16, (index, cell))

    def testAliasRangeBoundThatNamesNoCell(self):
        """A range bound that is an alias naming no cell made the dependency update throw
        "Invalid cell address": removing the row of the bound's cell stopped half-way and
        left the sheet half-moved, and typing =sum(start:stop) before defining the aliases was
        refused. Like a reference to a single unknown alias, such a range is kept, also in the
        file, and is an error until the alias names a cell"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "RemovedBound")
        for row in range(1, 4):
            sheet.set("A%d" % row, str(row))
        sheet.setAlias("A1", "first")
        sheet.setAlias("A3", "last")
        sheet.set("B5", "=sum(first:last)")
        sheet.set("C5", "=first")
        self.doc.recompute()
        sheet.removeRows("1", 1)
        self.doc.recompute()
        self.assertEqual([sheet.get("A%d" % row) for row in (1, 2)], [2, 3])
        self.assertEqual(sheet.getContents("A3"), "")
        self.assertEqual(sheet.getCellFromAlias("last"), "A2")
        self.assertIsNone(sheet.getCellFromAlias("first"))
        self.assertEqual(sheet.getContents("B4"), "=sum(first:last)")
        self.assertEqual(sheet.getContents("C4"), "=first")
        self.assertTrue(sheet.get("B4").startswith("ERR: Invalid cell address 'first'"))
        self.assertTrue(sheet.get("C4").startswith("ERR:"))
        self.assertEqual(sheet.getContents("B5"), "")
        # The range is resolved again once the alias names a cell
        sheet.setAlias("A1", "first")
        self.doc.recompute()
        self.assertEqual((sheet.get("B4"), sheet.get("C4")), (5, 2))

        sheet = self.doc.addObject("Spreadsheet::Sheet", "UnknownBounds")
        sheet.set("B1", "=sum(start:stop)")
        sheet.set("B2", "=B3 * 2")
        sheet.set("B3", "7")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("B1"), "=sum(start:stop)")
        self.assertTrue(sheet.get("B1").startswith("ERR: Invalid cell address 'start'"))
        self.assertEqual(sheet.get("B2"), 14)
        filename = os.path.join(self.TempPath, "SpreadsheetAliasRangeBound.FCStd")
        self.doc.saveAs(filename)
        name = self.doc.Name
        FreeCAD.closeDocument(name)
        self.doc = FreeCAD.openDocument(filename)
        sheet = self.doc.getObject("UnknownBounds")
        self.doc.recompute()
        self.assertEqual(
            [sheet.getContents(cell) for cell in ("B1", "B2", "B3")],
            ["=sum(start:stop)", "=B3 * 2", "7"],
        )
        self.assertEqual(sheet.get("B2"), 14)
        self.assertTrue(sheet.get("B1").startswith("ERR: Invalid cell address 'start'"))
        sheet.set("A1", "1")
        sheet.set("A2", "2")
        sheet.setAlias("A1", "start")
        sheet.setAlias("A2", "stop")
        self.doc.recompute()
        self.assertEqual(sheet.get("B1"), 3)

    def testRemoveRowsColumnsInsideRange(self):
        """A bound of a range inside removed rows/columns moves to the nearest remaining
        row/column of the range. sum(A4:A7) with rows 3-4 removed became sum(A2:A5), adding
        A2; sum(A1:A3) kept A1:A3, adding the old A5; and a range starting at row 1 gave
        A0 when removing row 1, which stopped the removal half-way"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for row in range(1, 8):
            sheet.set("A%d" % row, str(row))
        formulas = {
            "C1": ("=sum(A1:A5)", "=sum(A1:A3)", 8),
            "D1": ("=sum(A4:A7)", "=sum(A3:A5)", 18),
            "E1": ("=sum(A1:A3)", "=sum(A1:A2)", 3),
            "F1": ("=sum(A2:A6)", "=sum(A2:A4)", 13),
            "G1": ("=sum($A$4:$A$7)", "=sum($A$3:$A$5)", 18),
            # Bounds in reverse order keep their order. Only the formula is checked: such a
            # range evaluates its first cell only, which this test is not about
            "H1": ("=sum(A7:A4)", "=sum(A5:A3)", None),
        }
        for cell, (formula, _, _) in formulas.items():
            sheet.set(cell, formula)
        self.doc.recompute()
        sheet.removeRows("3", 2)
        self.doc.recompute()
        for cell, (_, formula, value) in formulas.items():
            if value is None:
                self.assertEqual(sheet.getContents(cell), formula, cell)
            else:
                self.assertEqual((sheet.getContents(cell), sheet.get(cell)), (formula, value), cell)

        # Columns: B10:H10 = 1..7, columns C:D removed
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Columns")
        for col, value in zip("BCDEFGH", range(1, 8)):
            sheet.set("%s10" % col, str(value))
        sheet.set("A12", "=sum(E10:H10)")
        sheet.set("A13", "=sum(B10:D10)")
        self.doc.recompute()
        sheet.removeColumns("C", 2)
        self.doc.recompute()
        self.assertEqual((sheet.getContents("A12"), sheet.get("A12")), ("=sum(C10:F10)", 22))
        self.assertEqual((sheet.getContents("A13"), sheet.get("A13")), ("=sum(B10:B10)", 1))

        # A range starting in the removed first row
        sheet = self.doc.addObject("Spreadsheet::Sheet", "FirstRow")
        for row in range(1, 8):
            sheet.set("A%d" % row, str(row))
        sheet.set("C5", "=sum(A1:A4)")
        sheet.set("D5", "=sum(A1:A1)")  # every cell removed: an error
        self.doc.recompute()
        sheet.removeRows("1", 1)
        self.doc.recompute()
        self.assertEqual((sheet.getContents("C4"), sheet.get("C4")), ("=sum(A1:A3)", 9))
        self.assertEqual(sheet.getContents("D4"), "=sum(REF@)")
        self.assertIn("Reference to a removed cell", sheet.get("D4"))
        self.assertEqual([sheet.get("A%d" % row) for row in range(1, 7)], [2, 3, 4, 5, 6, 7])
        self.assertEqual(sheet.getContents("A7"), "")

    def testReferenceToRemovedCellIsError(self):
        """A reference to a cell whose row or column is removed pointed at another cell: =A3
        with row 3 removed became =A2, other objects' Sheet.A3 read the old A4; =A1 became =A0
        (row 1 removed) or =@1 (column A removed), which read back as text. It becomes an error,
        like #REF! in other spreadsheet programs, that is kept in the file"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        for row in range(1, 6):
            sheet.set("A%d" % row, str(row))
        sheet.set("B5", "10")
        # Another sheet, created after the reference was read: only the cells of this sheet move
        sheet.set("H1", "=Later.A3")
        self.doc.addObject("Spreadsheet::Sheet", "Later")
        formulas = {
            # cell: (before, after removing row 3, value after)
            "C1": ("=A3", "=REF@", None),
            "D1": ("=$A$3 + A4", "=REF@ + A3", None),
            "E1": ("=A2 + A4 + B5", "=A2 + A3 + B4", 16),
            "F1": ("=sum(A3:A3)", "=sum(REF@)", None),
            "G1": ("=sum(A2:A4)", "=sum(A2:A3)", 6),
        }
        for cell, (formula, _, _) in formulas.items():
            sheet.set(cell, formula)
        # References from other objects, to a sheet without errors (the objects that depend
        # on a sheet with errors are not recomputed)
        source = self.doc.addObject("Spreadsheet::Sheet", "Source")
        for row in range(1, 6):
            source.set("A%d" % row, str(row))
        other = self.doc.addObject("Spreadsheet::Sheet", "Other")
        other.set("A1", "=Source.A3")
        other.set("A2", "=Source.A4")
        obj = self.doc.addObject("App::FeaturePython", "Obj")
        obj.addProperty("App::PropertyFloat", "Value")
        obj.setExpression("Value", "Source.A3")
        self.doc.recompute()

        def check():
            for cell, (_, formula, value) in formulas.items():
                self.assertEqual(sheet.getContents(cell), formula, cell)
                if value is None:
                    self.assertIn("Reference to a removed cell", sheet.get(cell), cell)
                else:
                    self.assertEqual(sheet.get(cell), value, cell)
            self.assertEqual(sheet.getContents("H1"), "=Later.A3")
            self.assertEqual(other.getContents("A1"), "=Source.REF@")
            self.assertIn("Reference to a removed cell", other.get("A1"))
            self.assertEqual((other.getContents("A2"), other.A2), ("=Source.A3", 4))
            self.assertEqual(obj.ExpressionEngine, [("Value", "Source.REF@")])
            self.assertIn("Invalid", obj.State)

        sheet.removeRows("3", 1)
        source.removeRows("3", 1)
        self.doc.recompute()
        check()

        # The error is kept in the file
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "removed.FCStd")
            self.doc.saveAs(path)
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
        sheet = self.doc.getObject("Spreadsheet")
        other = self.doc.getObject("Other")
        obj = self.doc.getObject("Obj")
        self.doc.recompute()
        check()
        self.assertEqual(self.doc.getObject("Source").A3, 4)

    def testUndoReferenceToRemovedCell(self):
        """Undoing the removal of a row or column gives back the references to its cells"""
        self.doc.UndoMode = 1
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "1")
        sheet.set("B1", "2")
        sheet.set("C2", "=A1 + B1")
        sheet.set("C3", "=sum(A1:B1)")
        obj = self.doc.addObject("App::FeaturePython", "Obj")
        obj.addProperty("App::PropertyFloat", "Value")
        obj.setExpression("Value", "Spreadsheet.A1")
        self.doc.recompute()
        for op, contents in (
            (
                lambda: sheet.removeRows("1", 1),
                {"C1": "=REF@ + REF@", "C2": "=sum(REF@)"},
            ),
            (
                lambda: sheet.removeColumns("A", 1),
                {"A1": "2", "B2": "=REF@ + A1", "B3": "=sum(A1:A1)"},
            ),
        ):
            self.doc.openTransaction("Remove")
            op()
            self.doc.commitTransaction()
            self.doc.recompute()
            self.assertEqual(
                {cell: sheet.getContents(cell) for cell in sheet.getUsedCells()}, contents
            )
            self.assertEqual(obj.ExpressionEngine, [("Value", "Spreadsheet.REF@")])
            self.doc.undo()
            self.doc.recompute()
            self.assertEqual(sheet.getContents("C2"), "=A1 + B1")
            self.assertEqual(sheet.getContents("C3"), "=sum(A1:B1)")
            self.assertEqual((sheet.C2, sheet.C3), (3, 3))
            self.assertEqual(obj.ExpressionEngine, [("Value", "Spreadsheet.A1")])
            self.assertEqual(obj.Value, 1)

    def testImportXLSXSharedFormulas(self):
        """Issue #20299: cells using a shared formula (formula dragged down
        or across in Excel) must be imported"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1"><v>1</v></c><c r="B1"><v>10</v></c>'
            '<c r="C1"><f t="shared" ref="C1:C3" si="0">A1*B1+$B$1</f><v>20</v></c>'
            '<c r="D1"><f t="shared" ref="D1:E1" si="1">A1+1</f><v>2</v></c>'
            '<c r="E1"><f t="shared" si="1"/><v>11</v></c></row>'
            '<row r="2"><c r="A2"><v>2</v></c><c r="B2"><v>20</v></c>'
            '<c r="C2"><f t="shared" si="0"/><v>50</v></c></row>'
            '<row r="3"><c r="A3"><v>3</v></c><c r="B3"><v>30</v></c>'
            '<c r="C3"><f t="shared" si="0"/><v>100</v></c></row>'
            "</sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetSharedFormulas.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Data")
        self.assertEqual(sheet.getContents("C1"), "=A1 * B1 + $B$1")
        self.assertEqual(sheet.getContents("C2"), "=A2 * B2 + $B$1")
        self.assertEqual(sheet.getContents("C3"), "=A3 * B3 + $B$1")
        self.assertEqual(sheet.getContents("E1"), "=B1 + 1")
        self.assertEqual(sheet.C2, 50)
        self.assertEqual(sheet.C3, 100)
        self.assertEqual(sheet.E1, 11)

    def testImportXLSXLayout(self):
        """Column widths, custom row heights and merged cells of an XLSX file
        are imported"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Layout" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}">'
            '<cols><col min="1" max="1" width="9.140625" customWidth="1"/>'
            '<col min="3" max="4" width="20" customWidth="1"/>'
            '<col min="700" max="16384" width="5"/></cols>'
            "<sheetData>"
            '<row r="1"><c r="A1"><v>1</v></c></row>'
            '<row r="2" ht="30" customHeight="1"><c r="A2"><v>2</v></c></row>'
            '<row r="3" ht="45"><c r="A3"><v>3</v></c></row>'
            "</sheetData>"
            '<mergeCells count="2"><mergeCell ref="A3:B4"/><mergeCell ref="C1:C2"/></mergeCells>'
            "</worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetLayout.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        defaultWidth = self.doc.addObject("Spreadsheet::Sheet", "Default").getColumnWidth("B")
        defaultHeight = self.doc.Default.getRowHeight("3")
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Layout")

        self.assertEqual(sheet.getColumnWidth("A"), 64)
        self.assertEqual(sheet.getColumnWidth("B"), defaultWidth)
        self.assertEqual(sheet.getColumnWidth("C"), 140)
        self.assertEqual(sheet.getColumnWidth("D"), 140)
        self.assertEqual(sheet.getColumnWidth("ZZ"), 35)
        self.assertEqual(sheet.getRowHeight("2"), 40)
        # Heights without customHeight are computed by Excel, not set by the user
        self.assertEqual(sheet.getRowHeight("3"), defaultHeight)
        self.assertEqual(sheet.A3, 3)
        sheet.set("B4", "hidden")
        sheet.set("C2", "hidden")
        self.doc.recompute()
        with self.assertRaises(AttributeError):
            sheet.B4
        with self.assertRaises(AttributeError):
            sheet.C2

    def testImportXLSXRichAndEmptyStrings(self):
        """Text with several formatted runs is read whole, phonetic hints are
        skipped and empty strings are read, without shifting the other strings"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Texts" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        sharedStrings = (
            f'<sst xmlns="{main}" count="4" uniqueCount="4">'
            "<si><t>plain</t></si>"
            '<si><r><t xml:space="preserve">Hello </t></r><r><rPr><b/></rPr><t>World</t></r>'
            '<rPh sb="0" eb="1"><t>hint</t></rPh></si>'
            "<si><t/></si>"
            "<si><t>after</t></si>"
            "</sst>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
            '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
            '<row r="3"><c r="A3" t="s"><v>2</v></c></row>'
            '<row r="4"><c r="A4" t="s"><v>3</v></c></row>'
            '<row r="5"><c r="A5" t="inlineStr"><is><r><t>in</t></r><r><t>line</t></r></is></c>'
            "</row></sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetRichStrings.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/sharedStrings.xml", sharedStrings)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Texts")
        self.doc.recompute()
        self.assertEqual(sheet.A1, "plain")
        self.assertEqual(sheet.A2, "Hello World")
        self.assertEqual(sheet.getContents("A3"), "")
        self.assertEqual(sheet.A4, "after")
        self.assertEqual(sheet.A5, "inline")

    def testImportXLSXFormatsOutsideSheet(self):
        """Formatted empty cells beyond column ZZ or row 16384, which Excel may
        write, are skipped instead of aborting the import"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Outside" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        styles = (
            f'<styleSheet xmlns="{main}">'
            '<fonts count="2"><font><sz val="11"/></font><font><b/><sz val="11"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            "</cellXfs></styleSheet>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1" s="1"><v>5</v></c><c r="AAA1" s="1"/></row>'
            '<row r="20000"><c r="A20000" s="1"/></row>'
            "</sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetFormatsOutside.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/styles.xml", styles)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Outside")
        self.assertEqual(sheet.A1, 5)
        self.assertEqual(sheet.getStyle("A1"), {"bold"})

    def testImportXLSXCellFormats(self):
        """Bold, italic, underline, RGB colors and alignment of XLSX cells are imported"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Formats" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        styles = (
            f'<styleSheet xmlns="{main}">'
            '<fonts count="3">'
            '<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>'
            '<font><b/><i/><sz val="11"/><color rgb="FFFF0000"/><name val="Calibri"/></font>'
            '<font><b val="0"/><u/><color rgb="FF000000"/></font>'
            "</fonts>"
            '<fills count="3">'
            '<fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFF00"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
            "</fills>"
            '<cellXfs count="4">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1">'
            '<alignment horizontal="center" vertical="top"/></xf>'
            '<xf numFmtId="0" fontId="2" fillId="1" borderId="0" xfId="0">'
            '<alignment horizontal="right"/></xf>'
            '<xf numFmtId="0" fontId="0" fillId="2" borderId="0" xfId="0"/>'
            "</cellXfs>"
            '<dxfs count="1"><dxf><font><b/></font></dxf></dxfs>'
            "</styleSheet>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1" s="1"><v>1</v></c><c r="B1" s="2"><v>2</v></c>'
            '<c r="C1" s="0"><v>3</v></c><c r="D1" s="3"/><c r="E1" s="99"><v>5</v></c></row>'
            "</sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetFormats.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/styles.xml", styles)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Formats")

        self.assertEqual(sheet.getStyle("A1"), {"bold", "italic"})
        self.assertEqual(sheet.getForeground("A1"), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(sheet.getBackground("A1"), (1.0, 1.0, 0.0, 1.0))
        self.assertEqual(sheet.getAlignment("A1"), {"center", "top"})

        self.assertEqual(sheet.getStyle("B1"), {"underline"})
        # Black text is the default color, the gray125 pattern is not a fill
        self.assertIsNone(sheet.getForeground("B1"))
        self.assertIsNone(sheet.getBackground("B1"))
        self.assertIn("right", sheet.getAlignment("B1"))
        self.assertNotIn("left", sheet.getAlignment("B1"))

        # The default format and unknown format indexes change nothing
        self.assertFalse(sheet.getStyle("C1"))
        self.assertIsNone(sheet.getBackground("C1"))
        self.assertFalse(sheet.getStyle("E1"))
        self.assertEqual(sheet.E1, 5)
        # Empty cells keep their format
        self.assertEqual(sheet.getBackground("D1"), (1.0, 1.0, 0.0, 1.0))

    def testExportXLSX(self):
        """Values, expressible formulas, aliases, formats and layout are exported
        to XLSX, and read back by the importer"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Exported")
        sheet.set("A1", "1.5")
        sheet.setAlias("A1", "len")
        sheet.set("B1", "=A1*2")
        sheet.set("C1", "10 mm")
        sheet.set("D1", "=C1*2")
        sheet.set("E1", "=len + 1")
        sheet.set("F1", "=sum(A1:B1)")
        sheet.set("G1", "=A1^2")
        sheet.set("H1", "=B1 + C1")
        sheet.set("A2", "<hello> & 'bye'")
        sheet.setStyle("A2", "bold|italic")
        sheet.setAlignment("A2", "center|top")
        sheet.setForeground("A2", (1.0, 0.0, 0.0))
        sheet.setBackground("A2", (0.0, 1.0, 0.0))
        sheet.set("A3", "merged")
        sheet.mergeCells("A3:B4")
        sheet.setColumnWidth("B", 150)
        sheet.setRowHeight("3", 40)
        self.doc.recompute()

        filename = os.path.join(self.TempPath, "SpreadsheetExport.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            worksheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            workbook = z.read("xl/workbook.xml").decode("utf-8")
            self.assertIn("xl/styles.xml", z.namelist())
            self.assertIn("[Content_Types].xml", z.namelist())
        self.assertIn('<c r="B1"><f>A1*2</f><v>3.0</v></c>', worksheet)
        self.assertIn("<f>len+1</f>", worksheet)
        self.assertIn("<f>SUM(A1:B1)</f>", worksheet)
        # Units, '^' and references to quantities are not expressible: values only
        self.assertNotIn("<f>10", worksheet)
        self.assertNotIn("C1*2", worksheet)
        self.assertNotIn("A1^2", worksheet)
        self.assertNotIn("B1+C1", worksheet)
        self.assertIn('<c r="G1"><v>2.25</v></c>', worksheet)
        self.assertIn("&lt;hello&gt; &amp; 'bye'", worksheet)
        self.assertIn('<mergeCell ref="A3:B4"/>', worksheet)
        self.assertIn(
            '<definedName name="len" localSheetId="0">Exported!$A$1</definedName>', workbook
        )

        # Read back by the importer
        doc = FreeCAD.newDocument("ExportXLSXRoundTrip")
        try:
            importXLSX.insert(filename, doc.Name)
            back = doc.getObject("Exported")
            self.assertEqual(back.getContents("B1"), "=A1 * 2")
            self.assertEqual(back.getAlias("A1"), "len")
            self.assertEqual(back.E1, 2.5)
            self.assertEqual(back.F1, 4.5)
            self.assertEqual(back.G1, 2.25)
            self.assertAlmostEqual(back.get("C1").Value, 10.0)
            self.assertAlmostEqual(back.get("D1").Value, 20.0)
            self.assertEqual(back.A2, "<hello> & 'bye'")
            self.assertEqual(back.getStyle("A2"), {"bold", "italic"})
            self.assertEqual(back.getAlignment("A2"), {"center", "top"})
            self.assertEqual(back.getForeground("A2"), (1.0, 0.0, 0.0, 1.0))
            self.assertEqual(back.getBackground("A2"), (0.0, 1.0, 0.0, 1.0))
            self.assertEqual(back.getColumnWidth("B"), 150)
            self.assertEqual(back.getColumnWidth("A"), sheet.getColumnWidth("A"))
            self.assertEqual(back.getRowHeight("3"), 40)
            self.assertEqual(back.getMergedCells(), ["A3:B4"])
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testLayoutGetters(self):
        """The set column widths and row heights, and the merged cells"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Layout")
        self.assertEqual(sheet.getColumnWidths(), {})
        self.assertEqual(sheet.getRowHeights(), {})
        self.assertEqual(sheet.getMergedCells(), [])
        sheet.setColumnWidth("AB", 150)
        sheet.setColumnWidth("B", sheet.getColumnWidth("C"))
        sheet.setRowHeight("12", 40)
        sheet.mergeCells("A3:B4")
        sheet.mergeCells("C1:C2")
        sheet.mergeCells("D5:F5")
        self.assertEqual(sheet.getColumnWidths(), {"AB": 150, "B": sheet.getColumnWidth("C")})
        self.assertEqual(sheet.getRowHeights(), {"12": 40})
        self.assertEqual(sheet.getMergedCells(), ["C1:C2", "A3:B4", "D5:F5"])
        sheet.splitCell("A3")
        self.assertEqual(sheet.getMergedCells(), ["C1:C2", "D5:F5"])

    def testExportXLSXOnlySetSizes(self):
        """The widths and heights set in FreeCAD are exported, whatever the size of
        the last column and row"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Sizes")
        for ref in ("A1", "B1", "C1", "A2"):
            sheet.set(ref, "1")
        sheet.setColumnWidth("ZZ", 150)
        sheet.setRowHeight("16384", 40)
        sheet.setColumnWidth("B", 150)
        sheet.setRowHeight("2", 40)
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetSizes.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            worksheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn(
            '<cols><col min="2" max="2" width="%s" customWidth="1"/></cols>' % repr(150 / 7.0),
            worksheet,
        )
        self.assertIn('<row r="1">', worksheet)
        self.assertIn('<row r="2" ht="30.0" customHeight="1">', worksheet)

    def testExportXLSXDecimals(self):
        """Per-cell decimals are exported as number formats"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Decimals")
        sheet.set("A1", "1.5")
        sheet.setDecimals("A1", 3)
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetDecimals.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            styles = z.read("xl/styles.xml").decode("utf-8")
            worksheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn('<numFmt numFmtId="164" formatCode="0.000"/>', styles)
        self.assertIn('<c r="A1" s="1"><v>1.5</v></c>', worksheet)

    def testExportXLSXNumberFormats(self):
        """Percent and scientific formats are exported as number formats with
        the decimals of the cell, and read back"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Numbers")
        sheet.set("A1", "0.125")
        sheet.setNumberFormat("A1", "percent")
        sheet.setDecimals("A1", 1)
        sheet.set("A2", "12345")
        sheet.setNumberFormat("A2", "scientific")
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetNumberFormats.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            styles = z.read("xl/styles.xml").decode("utf-8")
        default = importXLSX._defaultDecimals()
        self.assertIn('formatCode="0.0%"', styles)
        scientific = ("0." + "0" * default if default else "0") + "E+00"
        self.assertIn('formatCode="%s"' % scientific, styles)

        doc = FreeCAD.newDocument("ExportXLSXNumberFormats")
        try:
            importXLSX.insert(filename, doc.Name)
            back = doc.getObject("Numbers")
            self.assertEqual(back.A1, 0.125)
            self.assertEqual(back.getNumberFormat("A1"), "percent")
            self.assertEqual(back.getDecimals("A1"), 1)
            self.assertEqual(back.getNumberFormat("A2"), "scientific")
            self.assertEqual(back.getDecimals("A2"), default)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testImportXLSXNumberFormats(self):
        """The decimals, percentages and scientific notation of built-in and custom
        XLSX number formats are imported; formats FreeCAD cannot show are not"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Numbers" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        styles = (
            f'<styleSheet xmlns="{main}">'
            '<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.000"/>'
            '<numFmt numFmtId="165" formatCode="yyyy\\-mm\\-dd"/></numFmts>'
            '<fonts count="1"><font><sz val="11"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="11" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            "</cellXfs></styleSheet>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData><row r="1">'
            '<c r="A1" s="1"><v>0.25</v></c><c r="B1" s="2"><v>12345</v></c>'
            '<c r="C1" s="3"><v>1.5</v></c><c r="D1" s="4"><v>45000</v></c>'
            '<c r="E1" s="0"><v>7</v></c>'
            "</row></sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetImportNumberFormats.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/styles.xml", styles)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Numbers")
        self.assertEqual(sheet.A1, 0.25)
        self.assertEqual(sheet.getNumberFormat("A1"), "percent")
        self.assertEqual(sheet.getDecimals("A1"), 2)
        self.assertEqual(sheet.getNumberFormat("B1"), "scientific")
        self.assertEqual(sheet.getDecimals("B1"), 2)
        self.assertIsNone(sheet.getNumberFormat("C1"))
        self.assertEqual(sheet.getDecimals("C1"), 3)
        # A date: the number is kept, without a format
        self.assertIsNone(sheet.getNumberFormat("D1"))
        self.assertIsNone(sheet.getDecimals("D1"))
        self.assertIsNone(sheet.getDecimals("E1"))

    def testExportXLSXFontSize(self):
        """Font sizes are exported and read back; the size of the default font
        of a file is not imported, so that text keeps the size of the view"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Fonts")
        sheet.set("A1", "Title")
        sheet.setFontSize("A1", 18)
        sheet.setStyle("A1", "bold")
        sheet.set("A2", "Text")
        sheet.setStyle("A2", "bold")
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetFontSize.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            styles = z.read("xl/styles.xml").decode("utf-8")
        self.assertIn('<font><b/><sz val="18"/>', styles)
        self.assertIn('<font><b/><sz val="11"/>', styles)

        doc = FreeCAD.newDocument("ExportXLSXFontSize")
        try:
            importXLSX.insert(filename, doc.Name)
            back = doc.getObject("Fonts")
            self.assertEqual(back.getFontSize("A1"), 18)
            self.assertEqual(back.getStyle("A1"), {"bold"})
            self.assertIsNone(back.getFontSize("A2"))
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testExportXLSXBorders(self):
        """Borders are exported as thin lines and read back, those of a merged
        cell on the cells along its edges as Excel expects"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Borders")
        sheet.set("A1", "1")
        sheet.setBorders("A1", "top|right")
        sheet.set("C1", "merged")
        sheet.mergeCells("C1:D2")
        sheet.setBorders("C1:D2", "all", "outline")
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetBorders.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            styles = z.read("xl/styles.xml").decode("utf-8")
            worksheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn(
            '<border><left/><right style="thin"><color auto="1"/></right>'
            '<top style="thin"><color auto="1"/></top><bottom/><diagonal/></border>',
            styles,
        )
        # The covered cells along the edges of the merged cell carry its borders
        self.assertIn('<c r="D2" s="', worksheet)
        self.assertNotIn('<c r="B1"', worksheet)

        doc = FreeCAD.newDocument("ExportXLSXBorders")
        try:
            importXLSX.insert(filename, doc.Name)
            back = doc.getObject("Borders")
            self.assertEqual(back.getBorders("A1"), {"top", "right"})
            self.assertEqual(back.getBorders("C1"), {"top", "left", "bottom", "right"})
            self.assertEqual(back.getMergedCells(), ["C1:D2"])
            self.assertIsNone(back.getBorders("B1"))
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testImportXLSXBorders(self):
        """Sides of XLSX borders with a line style are imported, whatever the style"""
        import zipfile
        import importXLSX

        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        workbook = (
            f'<workbook xmlns="{main}" xmlns:r="{rels}"><sheets>'
            '<sheet name="Lines" sheetId="1" r:id="rId1"/></sheets></workbook>'
        )
        workbookRels = (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        )
        styles = (
            f'<styleSheet xmlns="{main}">'
            '<fonts count="1"><font><sz val="11"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="3"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left style="medium"/><right style="none"/><top/>'
            '<bottom style="double"><color rgb="FFFF0000"/></bottom><diagonal/></border>'
            '<border><left style="thin"/><right style="thin"/><top style="thin"/>'
            '<bottom style="thin"/><diagonal/></border></borders>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1"/>'
            "</cellXfs></styleSheet>"
        )
        worksheet = (
            f'<worksheet xmlns="{main}"><sheetData>'
            '<row r="1"><c r="A1" s="1"><v>5</v></c><c r="B1" s="0"><v>6</v></c>'
            '<c r="C1" s="2"/></row>'
            "</sheetData></worksheet>"
        )
        filename = os.path.join(self.TempPath, "SpreadsheetImportBorders.xlsx")
        with zipfile.ZipFile(filename, "w") as z:
            z.writestr("xl/workbook.xml", workbook)
            z.writestr("xl/_rels/workbook.xml.rels", workbookRels)
            z.writestr("xl/styles.xml", styles)
            z.writestr("xl/worksheets/sheet1.xml", worksheet)
        importXLSX.insert(filename, self.doc.Name)
        sheet = self.doc.getObject("Lines")
        self.assertEqual(sheet.A1, 5)
        self.assertEqual(sheet.getBorders("A1"), {"left", "bottom"})
        self.assertIsNone(sheet.getBorders("B1"))
        self.assertEqual(sheet.getBorders("C1"), {"top", "left", "bottom", "right"})

    def testExportXLSXQuantityPrecision(self):
        """Quantities are exported at full precision, not rounded to the
        decimals of the preferences, and read back as the same quantity"""
        import zipfile
        import importXLSX

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Quantities")
        sheet.set("A1", "=1/3 * 1 mm")
        self.doc.recompute()
        filename = os.path.join(self.TempPath, "SpreadsheetQuantities.xlsx")
        importXLSX.export([sheet], filename)
        with zipfile.ZipFile(filename) as z:
            worksheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn(">%s mm<" % repr(1 / 3), worksheet)

        doc = FreeCAD.newDocument("ExportXLSXQuantities")
        try:
            importXLSX.insert(filename, doc.Name)
            back = doc.Objects[0]
            self.assertAlmostEqual(back.get("A1").Value, 1 / 3, places=12)
            self.assertEqual(back.get("A1").Unit, FreeCAD.Units.Length)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testExportXLSXDefinedNames(self):
        """Aliases are exported as names of their own worksheet, so that sheets
        can share an alias, with the worksheet name quoted when Excel needs it"""
        import zipfile
        import importXLSX

        first = self.doc.addObject("Spreadsheet::Sheet", "First")
        first.Label = "2024"
        first.set("A1", "1")
        first.setAlias("A1", "len")
        first.set("A2", "=len*2")
        second = self.doc.addObject("Spreadsheet::Sheet", "Second")
        second.Label = "AB12"
        second.set("B2", "5")
        second.setAlias("B2", "len")
        second.set("B3", "=len+1")
        second.set("C1", "7")
        second.setAlias("C1", "R1C1")
        self.doc.recompute()

        filename = os.path.join(self.TempPath, "SpreadsheetDefinedNames.xlsx")
        importXLSX.export([first, second], filename)
        with zipfile.ZipFile(filename) as z:
            workbook = z.read("xl/workbook.xml").decode("utf-8")
        self.assertIn(
            '<definedName name="len" localSheetId="0">\'2024\'!$A$1</definedName>', workbook
        )
        self.assertIn(
            '<definedName name="len" localSheetId="1">\'AB12\'!$B$2</definedName>', workbook
        )
        # Not a valid Excel name (an R1C1 reference)
        self.assertNotIn('"R1C1"', workbook)

        doc = FreeCAD.newDocument("ExportXLSXDefinedNames")
        try:
            importXLSX.insert(filename, doc.Name)
            # In the order of the worksheets ("2024" becomes the object "_2024")
            back1, back2 = doc.Objects
            self.assertEqual(back1.getAlias("A1"), "len")
            self.assertEqual(back2.getAlias("B2"), "len")
            self.assertEqual(back1.A2, 2)
            self.assertEqual(back2.B3, 6)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testRemoveRowsAliasReuseName(self):
        """Regression test for issue 4492; deleted aliases remains in database"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.setAlias("B2", "test")
        self.doc.recompute()
        sheet.removeRows("2", 1)
        sheet.setAlias("B3", "test")

    def testRemoveColumnsAlias(self):
        """Regression test for issue 4429; remove columns from sheet with aliases"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("C1", "1")
        sheet.setAlias("C1", "alias1")
        sheet.set("E1", "=alias1 + 1")
        sheet.setAlias("E1", "alias2")
        sheet.set("D1", "=alias2 + 1")
        self.doc.recompute()
        sheet.removeColumns("A", 1)
        self.doc.recompute()
        self.assertEqual(sheet.C1, 3)

    def testRemoveColumnsAliasReuseName(self):
        """Regression test for issue 4492; deleted aliases remains in database"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.setAlias("B2", "test")
        self.doc.recompute()
        sheet.removeColumns("B", 1)
        sheet.setAlias("C3", "test")

    def testUndoAliasCreationReuseName(self):
        """Test deleted aliases by undo remains in database"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        self.doc.openTransaction("create alias")
        sheet.setAlias("B2", "test")
        self.doc.commitTransaction()
        self.doc.recompute()

        self.doc.undo()
        self.doc.recompute()
        sheet.setAlias("C3", "test")

    def test_cross_link_empty_property_name(self):
        # https://forum.freecad.org/viewtopic.php?f=3&t=58603
        base = FreeCAD.newDocument("base")
        sheet = base.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.setAlias("A1", "x")
        sheet.set("x", "42mm")
        base.recompute()

        square = FreeCAD.newDocument("square")
        body = square.addObject("PartDesign::Body", "Body")
        box = square.addObject("PartDesign::AdditiveBox", "Box")
        body.addObject(box)
        box.Length = 10.00
        box.Width = 10.00
        box.Height = 10.00
        square.recompute()

        base_path = self.TempPath + os.sep + "base.FCStd"
        base.saveAs(base_path)
        square_path = self.TempPath + os.sep + "square.FCStd"
        square.saveAs(square_path)

        base.save()
        square.save()

        FreeCAD.closeDocument(square.Name)
        FreeCAD.closeDocument(base.Name)

        ##
        ## preparation done
        base = FreeCAD.openDocument(base_path)
        square = FreeCAD.openDocument(square_path)

        square.Box.setExpression("Length", "base#Spreadsheet.x")
        square.recompute()

        square.save()
        base.save()
        FreeCAD.closeDocument(square.Name)
        FreeCAD.closeDocument(base.Name)

    def test_expression_with_alias(self):
        # https://forum.freecad.org/viewtopic.php?p=564502#p564502
        ss1 = self.doc.addObject("Spreadsheet::Sheet", "Input")
        ss1.setAlias("A1", "one")
        ss1.setAlias("A2", "two")
        ss1.set("A1", "1")
        ss1.set("A2", "2")
        self.doc.recompute()

        ss2 = self.doc.addObject("Spreadsheet::Sheet", "Output")
        ss2.set("A1", "=Input.A1 + Input.A2")
        ss2.set("A2", "=Input.one + Input.two")
        ss2.set("A3", "=<<Input>>.A1 + <<Input>>.A2")
        ss2.set("A4", "=<<Input>>.one + <<Input>>.two")
        self.doc.recompute()

        self.assertEqual(ss2.get("A1"), 3)
        self.assertEqual(ss2.get("A2"), 3)
        self.assertEqual(ss2.get("A3"), 3)
        self.assertEqual(ss2.get("A4"), 3)

        project_path = self.TempPath + os.sep + "alias.FCStd"
        self.doc.saveAs(project_path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(project_path)
        ss1 = self.doc.Input
        ss2 = self.doc.Output

        self.assertEqual(ss2.get("A1"), 3)
        self.assertEqual(ss2.get("A2"), 3)
        self.assertEqual(ss2.get("A3"), 3)
        self.assertEqual(ss2.get("A4"), 3)

        ss1.set("A1", "2")
        self.doc.recompute()

        self.assertEqual(ss1.get("A1"), 2)
        self.assertEqual(ss1.get("one"), 2)

        self.assertEqual(ss2.get("A1"), 4)
        self.assertEqual(ss2.get("A2"), 4)
        self.assertEqual(ss2.get("A3"), 4)
        self.assertEqual(ss2.get("A4"), 4)

    def testIssue6844(self):
        body = self.doc.addObject("App::FeaturePython", "Body")
        body.addProperty("App::PropertyEnumeration", "Configuration")
        body.Configuration = ["Item1", "Item2", "Item3"]

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet")
        sheet.addProperty("App::PropertyString", "A2")
        sheet.A2 = "Item2"
        sheet.addProperty("App::PropertyEnumeration", "body")
        sheet.body = ["Item1", "Item2", "Item3"]

        sheet.setExpression(".body.Enum", "cells[<<A2:|>>]")
        sheet.setExpression(
            ".cells.Bind.B1.ZZ1",
            "tuple(.cells; <<B>> + str(hiddenref(Body.Configuration) + 2); <<ZZ>> + str(hiddenref(Body.Configuration) + 2))",
        )

        self.doc.recompute()
        self.doc.removeObject("Body")
        sheet.clearAll()

    def testIssue6840(self):
        body = self.doc.addObject("App::FeaturePython", "Body")
        body.addProperty("App::PropertyEnumeration", "Configuration")
        body.Configuration = ["Item1", "Item2", "Item3"]

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet")
        sheet.addProperty("App::PropertyString", "A2")
        sheet.A2 = "Item2"
        sheet.addProperty("App::PropertyEnumeration", "body")
        sheet.body = ["Item1", "Item2", "Item3"]

        sheet.setExpression(".body.Enum", "cells[<<A2:|>>]")
        sheet.setExpression(
            ".cells.Bind.B1.ZZ1",
            "tuple(.cells; <<B>> + str(hiddenref(Body.Configuration) + 2); <<ZZ>> + str(hiddenref(Body.Configuration) + 2))",
        )

        self.doc.recompute()
        self.doc.clearDocument()

    def testFixPR6843(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet")
        sheet.set("A5", "a")
        sheet.set("A6", "b")
        self.doc.recompute()
        sheet.insertRows("6", 1)
        self.doc.recompute()
        self.assertEqual(sheet.A5, "a")
        self.assertEqual(sheet.A7, "b")
        with self.assertRaises(AttributeError):
            self.assertEqual(sheet.A6, "")

    def testBindAcrossSheets(self):
        ss1 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet1")
        ss2 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet2")
        ss2.set("B1", "B1")
        ss2.set("B2", "B2")
        ss2.set("C1", "C1")
        ss2.set("C2", "C2")
        ss2.set("D1", "D1")
        ss2.set("D2", "D2")

        ss1.setExpression(".cells.Bind.A3.C4", "tuple(Spreadsheet2.cells, <<B1>>, <<D2>>)")
        self.doc.recompute()

        self.assertEqual(ss1.A3, ss2.B1)
        self.assertEqual(ss1.A4, ss2.B2)
        self.assertEqual(ss1.B3, ss2.C1)
        self.assertEqual(ss1.B4, ss2.C2)
        self.assertEqual(ss1.C3, ss2.D1)
        self.assertEqual(ss1.C4, ss2.D2)

        self.assertEqual(len(ss1.ExpressionEngine), 1)
        ss1.setExpression(".cells.Bind.A3.C4", None)
        self.doc.recompute()

    def testBindHiddenRefAcrossSheets(self):
        ss1 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet1")
        ss2 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet2")
        ss2.set("B1", "B1")
        ss2.set("B2", "B2")
        ss2.set("C1", "C1")
        ss2.set("C2", "C2")
        ss2.set("D1", "D1")
        ss2.set("D2", "D2")

        self.doc.recompute()
        ss1.setExpression(".cells.Bind.A3.C4", None)
        ss1.setExpression(
            ".cells.BindHiddenRef.A3.C4", "hiddenref(tuple(Spreadsheet2.cells, <<B1>>, <<D2>>))"
        )
        self.doc.recompute()

        ss1.recompute()  # True
        self.assertEqual(ss1.A3, ss2.B1)

        ss1.setExpression(".cells.Bind.A3.C4", None)
        ss1.setExpression(".cells.BindHiddenRef.A3.C4", None)
        self.doc.recompute()
        self.assertEqual(len(ss1.ExpressionEngine), 0)

    def testMergeCells(self):
        ss1 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet1")
        ss1.mergeCells("A1:B4")
        ss1.mergeCells("C1:D4")
        self.doc.recompute()
        ss1.set("B1", "fail")
        self.doc.recompute()
        with self.assertRaises(AttributeError):
            self.assertEqual(ss1.B1, "fail")

    def testMergeCellsAndBind(self):
        ss1 = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet1")
        ss1.mergeCells("A1:B1")
        ss1.setExpression(".cells.Bind.A1.A1", "tuple(.cells, <<A2>>, <<A2>>)")
        ss1.set("A2", "test")
        self.doc.recompute()
        self.assertEqual(ss1.A1, ss1.A2)
        ss1.set("B1", "fail")
        self.doc.recompute()
        with self.assertRaises(AttributeError):
            self.assertEqual(ss1.B1, "fail")

    def testGetUsedCells(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        test_cells = ["B13", "C14", "D15"]
        for i, cell in enumerate(test_cells):
            sheet.set(cell, str(i))

        used_cells = sheet.getUsedCells()
        self.assertEqual(len(used_cells), len(test_cells))
        for cell in test_cells:
            self.assertTrue(cell in used_cells)

        for cell in test_cells:
            sheet.set(cell, "")
            sheet.setAlignment(cell, "center")
        non_empty_cells = sheet.getUsedCells()
        self.assertEqual(len(non_empty_cells), len(test_cells))  # Alignment counts as "used"

    def testGetUsedRange(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        test_cells = ["C5", "Z3", "D10", "E20"]
        for i, cell in enumerate(test_cells):
            sheet.set(cell, str(i))
        used_range = sheet.getUsedRange()
        self.assertEqual(used_range, ("C3", "Z20"))

        for i, cell in enumerate(test_cells):
            sheet.set(cell, "")
            sheet.setAlignment(cell, "center")
        used_range = sheet.getUsedRange()
        self.assertEqual(used_range, ("C3", "Z20"))

    def testGetNonEmptyCells(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        test_cells = ["B13", "C14", "D15"]
        for i, cell in enumerate(test_cells):
            sheet.set(cell, str(i))

        non_empty_cells = sheet.getNonEmptyCells()
        self.assertEqual(len(non_empty_cells), len(test_cells))
        for cell in test_cells:
            self.assertTrue(cell in non_empty_cells)

        for cell in test_cells:
            sheet.set(cell, "")
            sheet.setAlignment(cell, "center")
        non_empty_cells = sheet.getNonEmptyCells()
        self.assertEqual(len(non_empty_cells), 0)  # Alignment does not count as "non-empty"

    def testGetNonEmptyRange(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        test_cells = ["C5", "Z3", "D10", "E20"]
        for i, cell in enumerate(test_cells):
            sheet.set(cell, str(i))
        non_empty_range = sheet.getNonEmptyRange()
        self.assertEqual(non_empty_range, ("C3", "Z20"))

        for i, cell in enumerate(test_cells):
            sheet.set(cell, "")
            sheet.setAlignment(cell, "center")
        more_cells = ["D10", "X5", "E10", "K15"]
        for i, cell in enumerate(more_cells):
            sheet.set(cell, str(i))
        non_empty_range = sheet.getNonEmptyRange()
        self.assertEqual(non_empty_range, ("D5", "X15"))

    def testAliasEmptyCell(self):
        # https://github.com/FreeCAD/FreeCAD/issues/7841
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.setAlias("A1", "aliasOfEmptyCell")
        self.assertEqual(sheet.getCellFromAlias("aliasOfEmptyCell"), "A1")

    def testParensAroundCondition(self):
        """Parens around a condition should be accepted"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        sheet.set("A1", "=(1 == 1) ? 1 : 0")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "=1 == 1 ? 1 : 0")
        self.assertEqual(sheet.A1, 1)

    def testIssue6395(self):
        """Testing strings are correctly saved and restored"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "'36C")  # Use a string that may be parsed as a quantity
        self.doc.recompute()

        self.doc.saveAs(self.TempPath + os.sep + "string.fcstd")
        FreeCAD.closeDocument(self.doc.Name)

        self.doc = FreeCAD.openDocument(self.TempPath + os.sep + "string.fcstd")

        sheet = self.doc.getObject("Spreadsheet")
        self.assertEqual(sheet.getContents("A1"), "'36C")
        self.assertEqual(sheet.get("A1"), "36C")

    def testDistantCell(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("ZX12345", "5")
        sheet.set("A1", "=ZX12345")

        self.doc.recompute()

        self.assertEqual(sheet.A1, 5)

    def testVectorFunctions(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

        sheet.set("A1", "=vcross(vector(1; 2; 3); vector(1; 5; 7))")

        sheet.set("B1", "=vdot(vector(1; 2; 3); vector(4; -5; 6))")

        sheet.set("C1", "=vangle(vector(1; 0; 0); vector(0; 1; 0))")

        sheet.set("D1", "=vnormalize(vector(1; 0; 0))")
        sheet.set("D2", "=vnormalize(vector(1; 1; 1))")

        sheet.set("E1", "=vscale(vector(1; 2; 3); 2; 3; 4)")
        sheet.set("E2", "=vscalex(vector(1; 2; 3); -2)")
        sheet.set("E3", "=vscaley(vector(1; 2; 3); -2)")
        sheet.set("E4", "=vscalez(vector(1; 2; 3); -2)")

        sheet.set("F1", "=vlinedist(vector(1; 2; 3); vector(2; 3; 4); vector(3; 4; 5))")
        sheet.set("F2", "=vlinesegdist(vector(1; 2; 3); vector(2; 3; 4); vector(3; 4; 5))")
        sheet.set("F3", "=vlineproj(vector(1; 2; 3); vector(2; 3; 4); vector(3; 4; 5))")
        sheet.set("F4", "=vplanedist(vector(1; 2; 3); vector(2; 3; 4); vector(3; 4; 5))")
        sheet.set("F5", "=vplaneproj(vector(1; 2; 3); vector(2; 3; 4); vector(3; 4; 5))")

        self.doc.recompute()

        tolerance = 1e-10

        self.assertEqual(sheet.A1, FreeCAD.Vector(-1, -4, 3))

        self.assertEqual(sheet.B1, 12)

        self.assertEqual(sheet.C1, 90)

        self.assertEqual(sheet.D1, FreeCAD.Vector(1, 0, 0))
        self.assertLess(
            sheet.D2.distanceToPoint(FreeCAD.Vector(1 / sqrt(3), 1 / sqrt(3), 1 / sqrt(3))),
            tolerance,
        )

        self.assertEqual(sheet.E1, FreeCAD.Vector(2, 6, 12))
        self.assertEqual(sheet.E2, FreeCAD.Vector(-2, 2, 3))
        self.assertEqual(sheet.E3, FreeCAD.Vector(1, -4, 3))
        self.assertEqual(sheet.E4, FreeCAD.Vector(1, 2, -6))

        self.assertLess(abs(sheet.F1.Value - 0.3464), 0.0001)
        self.assertEqual(sheet.F2, FreeCAD.Vector(1, 1, 1))
        self.assertLess(sheet.F3.distanceToPoint(FreeCAD.Vector(0.28, 0.04, -0.2)), tolerance)
        self.assertLess(abs(sheet.F4.Value - -1.6971), 0.0001)
        self.assertEqual(sheet.F5, FreeCAD.Vector(1.72, 2.96, 4.2))

    def testTernaryOperator(self):
        """Testing ternary operator"""
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "= 1 ? 10 : 20")
        sheet.set("A2", "= 0 ? 10 : 20")
        sheet.set("A3", "= True ? 10 : 20")
        sheet.set("A4", "= False ? 10 : 20")
        sheet.set("B1", "= 1mm ? 10 : 20")
        sheet.set("B2", "= 0mm ? 10 : 20")
        sheet.set("C1", "= 2 == 2 ? 10 : 20")
        sheet.set("C2", "= 2 != 2 ? 10 : 20")
        sheet.set("C3", "= 2 > 1 ? 10 : 20")
        sheet.set("C4", "= 1 > 2 ? 10 : 20")

        sheet.set("D1", "= and(1 < 2, 3 < 4) ? 10 : 20")
        sheet.set("D2", "= and(1 < 2, 3 > 4) ? 10 : 20")
        sheet.set("D3", "= and(1 > 2, 3 < 4) ? 10 : 20")
        sheet.set("D4", "= and(1 > 2, 3 > 4) ? 10 : 20")

        sheet.set("E1", "= or(1 < 2, 3 < 4) ? 10 : 20")
        sheet.set("E2", "= or(1 < 2, 3 > 4) ? 10 : 20")
        sheet.set("E3", "= or(1 > 2, 3 < 4) ? 10 : 20")
        sheet.set("E4", "= or(1 > 2, 3 > 4) ? 10 : 20")

        sheet.set("F1", "= not(2 > 1) ? 10 : 20")
        sheet.set("F2", "= not(2 < 1) ? 10 : 20")

        sheet.addProperty("App::PropertyBool", "PropTrue", "", "")
        sheet.PropTrue = True
        sheet.addProperty("App::PropertyBool", "PropFalse", "", "")
        sheet.PropFalse = False
        sheet.addProperty("App::PropertyLength", "PropL", "", "")
        sheet.PropL = "0 mm"
        sheet.addProperty("App::PropertyLength", "PropH", "", "")
        sheet.PropH = "5 mm"
        sheet.addProperty("App::PropertyInteger", "PropI", "", "")
        sheet.PropI = -5
        sheet.addProperty("App::PropertyString", "PropS", "", "")
        sheet.PropS = "This is a test"
        sheet.addProperty("App::PropertyString", "PropSEmpty", "", "")

        sheet.set("G1", "= Spreadsheet.PropTrue ? 10 : 20")
        sheet.set("G2", "= Spreadsheet.PropFalse ? 10 : 20")
        sheet.set("G3", "= Spreadsheet.PropL ? 10 : 20")
        sheet.set("G4", "= Spreadsheet.PropH ? 10 : 20")
        sheet.set("G5", "= Spreadsheet.PropI ? 10 : 20")
        sheet.set("G6", "= Spreadsheet.PropS ? 10 : 20")
        sheet.set("G7", "= Spreadsheet.PropSEmpty ? 10 : 20")
        sheet.set("G8", "= <<Test>> ? 10 : 20")
        sheet.set("G9", "= <<>> ? 10 : 20")
        sheet.set("G10", "= <<Spreadsheet>> ? 10 : 20")

        self.doc.recompute()

        # Constants
        self.assertEqual(sheet.get("A1"), 10)
        self.assertEqual(sheet.get("A2"), 20)
        self.assertEqual(sheet.get("A3"), 10)
        self.assertEqual(sheet.get("A4"), 20)

        # Constant Quantities
        self.assertEqual(sheet.get("B1"), 10)
        self.assertEqual(sheet.get("B2"), 20)

        # Basic Comparisons
        self.assertEqual(sheet.get("C1"), 10)
        self.assertEqual(sheet.get("C2"), 20)
        self.assertEqual(sheet.get("C3"), 10)
        self.assertEqual(sheet.get("C4"), 20)

        # Function calls
        self.assertEqual(sheet.get("D1"), 10)
        self.assertEqual(sheet.get("D2"), 20)
        self.assertEqual(sheet.get("D3"), 20)
        self.assertEqual(sheet.get("D4"), 20)
        self.assertEqual(sheet.get("E1"), 10)
        self.assertEqual(sheet.get("E2"), 10)
        self.assertEqual(sheet.get("E3"), 10)
        self.assertEqual(sheet.get("E4"), 20)
        self.assertEqual(sheet.get("F1"), 20)
        self.assertEqual(sheet.get("F2"), 10)

        # Property lookup
        self.assertEqual(sheet.get("G1"), 10)
        self.assertEqual(sheet.get("G2"), 20)
        self.assertEqual(sheet.get("G3"), 20)
        self.assertEqual(sheet.get("G4"), 10)
        self.assertEqual(sheet.get("G5"), 10)

        # Non numeric conditions
        self.assertEqual(sheet.get("G6"), 10)
        self.assertEqual(sheet.get("G7"), 20)
        self.assertEqual(sheet.get("G8"), 10)
        self.assertEqual(sheet.get("G9"), 20)
        self.assertEqual(sheet.get("G10"), 10)

    def testFineGrainedRecompute(self):
        """Regression test for issue #32088.

        With fine-grained recompute enabled, on reopening a file, the InList of
        properties are defined before the spreadsheet has actually created the
        properties that contain the values.  This causes the alias to be
        registered as the property name of the dependency instead of the actual
        property name.

        This test case tests whether the dependency is correctly registered
        after a document is reopened."""

        NAME_DOC = "cube.FCStd"

        # Turn on fine-grained recompute
        ParamGroup = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/General")
        fineGrainedPref = ParamGroup.GetBool("FineGrainedRecompute")
        ParamGroup.SetBool("FineGrainedRecompute", True)

        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "=20")
        sheet.setAlias("A1", "Length")
        self.doc.recompute()

        box = self.doc.addObject("Part::Box", "Box")
        box.setExpression("Length", "Spreadsheet.Length")
        self.doc.recompute()
        self.assertEqual(box.Length, 20)

        sheet.set("A1", "=30")
        self.doc.recompute()
        self.assertEqual(box.Length, 30)

        self.doc.saveAs(self.TempPath + os.sep + NAME_DOC)
        FreeCAD.closeDocument(self.doc.Name)

        self.doc = FreeCAD.openDocument(self.TempPath + os.sep + NAME_DOC)
        sheet = self.doc.Spreadsheet
        box = self.doc.Box
        self.assertEqual(box.Length, 30)

        sheet.set("A1", "=40")
        self.doc.recompute()
        # this assert would fail before the fix of the above issue.
        self.assertEqual(box.Length, 40)

        # Restore the original fine-grained recompute preference
        ParamGroup.SetBool("FineGrainedRecompute", fineGrainedPref)


#############################################################################################
class SpreadsheetEditing(unittest.TestCase):
    """Editing commands of the sheet: fill, sort."""

    def setUp(self):
        self.doc = FreeCAD.newDocument()
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testFillDown(self):
        sheet = self.sheet
        sheet.set("A1", "1")
        sheet.set("B1", "=A1 * 2")
        sheet.set("C1", "=$A$1 + A1")
        sheet.set("D2", "stale")
        sheet.setStyle("B1", "bold")
        sheet.setAlias("B1", "first")
        sheet.set("A4", "untouched")
        sheet.fillDown("A1:D3")
        self.doc.recompute()

        self.assertEqual(sheet.getContents("A2"), "1")
        self.assertEqual(sheet.getContents("B2"), "=A2 * 2")
        self.assertEqual(sheet.getContents("B3"), "=A3 * 2")
        self.assertEqual(sheet.getContents("C3"), "=$A$1 + A3")
        self.assertEqual(sheet.B3, 2)
        self.assertEqual(sheet.C3, 2)
        # Empty source cells clear their targets
        self.assertEqual(sheet.getContents("D2"), "")
        # Formatting follows, the alias stays unique
        self.assertEqual(sheet.getStyle("B3"), {"bold"})
        self.assertEqual(sheet.getAlias("B1"), "first")
        self.assertIsNone(sheet.getAlias("B2"))
        # Cells outside the range are left alone
        self.assertEqual(sheet.getContents("A4"), "'untouched")

    def testFillRight(self):
        sheet = self.sheet
        sheet.set("A1", "10")
        sheet.set("A2", "=A1 + 1")
        sheet.fillRight("A1:C2")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("C1"), "10")
        self.assertEqual(sheet.getContents("B2"), "=B1 + 1")
        self.assertEqual(sheet.getContents("C2"), "=C1 + 1")
        self.assertEqual(sheet.C2, 11)

    def testFillNormalizesRangeAndIgnoresSingleLine(self):
        sheet = self.sheet
        sheet.set("A1", "5")
        sheet.set("B1", "6")
        sheet.set("A2", "keep")
        # One row: nothing to fill downwards
        sheet.fillDown("A1:B1")
        self.assertEqual(sheet.getContents("A2"), "'keep")
        # A reversed range is the same range
        sheet.fillDown("B2:A1")
        self.assertEqual(sheet.getContents("A2"), "5")
        self.assertEqual(sheet.getContents("B2"), "6")

    def testFillRejectsMergedCellsAndBadRanges(self):
        sheet = self.sheet
        sheet.set("A1", "1")
        sheet.mergeCells("B2:C2")
        with self.assertRaises(ValueError):
            sheet.fillDown("A1:C3")
        self.assertEqual(sheet.getContents("A2"), "")
        with self.assertRaises(ValueError):
            sheet.fillDown("not a range")

    def testFillDownUndo(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "=1 + 1")
        self.doc.recompute()
        self.doc.openTransaction("Fill Down")
        sheet.fillDown("A1:A3")
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(sheet.A3, 2)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A3"), "")
        self.assertEqual(sheet.getContents("A1"), "=1 + 1")

    def _sortSample(self):
        sheet = self.sheet
        sheet.set("A1", "name")
        for row, (key, value) in enumerate(
            [("pear", "3"), ("Apple", "1"), ("", "2"), ("5", "4"), ("banana", "6")], start=2
        ):
            if key:
                sheet.set(f"A{row}", key)
            sheet.set(f"B{row}", value)
        sheet.setStyle("B3", "bold")
        sheet.set("C2", "outside")
        self.doc.recompute()

    def testSortRowsAscending(self):
        sheet = self.sheet
        self._sortSample()
        sheet.sortRows("A2:B6", "A")
        self.doc.recompute()
        # Numbers, then text without case, then empty cells
        self.assertEqual(
            [sheet.getContents(f"A{row}") for row in range(1, 7)],
            ["'name", "5", "'Apple", "'banana", "'pear", ""],
        )
        self.assertEqual([sheet.get(f"B{row}") for row in range(2, 7)], [4, 1, 6, 3, 2])
        # Formatting moves with the cells; cells outside the range stay
        self.assertEqual(sheet.getStyle("B3"), {"bold"})
        self.assertIsNone(sheet.getStyle("B2"))
        self.assertEqual(sheet.getContents("C2"), "'outside")

    def testSortRowsDescending(self):
        sheet = self.sheet
        self._sortSample()
        sheet.sortRows("B6:A2", "A", False)
        self.doc.recompute()
        # Empty cells stay last
        self.assertEqual([sheet.get(f"B{row}") for row in range(2, 7)], [3, 6, 1, 4, 2])
        sheet.sortRows("A2:B6", "B", False)
        self.doc.recompute()
        self.assertEqual([sheet.get(f"B{row}") for row in range(2, 7)], [6, 4, 3, 2, 1])

    def testSortRowsBeforeRecompute(self):
        """Typed numbers and quantities sort by value even before a recompute"""
        sheet = self.sheet
        sheet.set("A1", "10")
        sheet.set("A2", "9")
        sheet.set("A3", "1 m")
        sheet.set("A4", "5 mm")
        sheet.set("A5", "abc")
        sheet.sortRows("A1:A5", "A")
        self.assertEqual(
            [sheet.getContents(f"A{row}") for row in range(1, 6)],
            ["=5 mm", "9", "10", "=1 m", "'abc"],
        )

    def testSortRowsReferences(self):
        sheet = self.sheet
        sheet.set("A1", "100")
        sheet.set("A2", "3")
        sheet.set("A3", "1")
        sheet.set("A4", "2")
        sheet.set("B2", "=A2 * 10")  # same row
        sheet.set("B3", "=A3 + A1")  # outside the range
        sheet.set("B4", "=$A$2")  # another sorted row
        sheet.set("C2", "=sum(A2:B2)")  # range in one sorted row
        sheet.set("C3", "=sum(A2:A4)")  # range over all sorted rows
        sheet.set("D1", "=A2")  # outside: keeps its position
        sheet.set("D2", "=sum(A2:A4)")
        self.doc.recompute()
        self.assertEqual(sheet.C2, 33)

        sheet.sortRows("A2:C4", "A")
        self.doc.recompute()
        self.assertEqual(sheet.getContents("B2"), "=A2 + A1")
        self.assertEqual(sheet.getContents("B3"), "=$A$4")
        self.assertEqual(sheet.getContents("B4"), "=A4 * 10")
        self.assertEqual(sheet.getContents("C4"), "=sum(A4:B4)")
        self.assertEqual(sheet.getContents("C2"), "=sum(A2:A4)")
        self.assertEqual([sheet.get(f"B{row}") for row in range(2, 5)], [101, 3, 30])
        self.assertEqual(sheet.C4, 33)
        self.assertEqual(sheet.C2, 6)
        self.assertEqual(sheet.getContents("D1"), "=A2")
        self.assertEqual(sheet.D1, 1)
        self.assertEqual(sheet.D2, 6)

    def testSortRowsRejectsPartialRangesAliasesAndMerges(self):
        sheet = self.sheet
        sheet.set("A2", "2")
        sheet.set("A3", "1")
        sheet.set("A4", "0")
        sheet.set("B2", "=sum(A2:A3)")
        self.doc.recompute()
        with self.assertRaises(ValueError):
            sheet.sortRows("A2:B4", "A")
        # Nothing changed
        self.assertEqual(sheet.getContents("A2"), "2")
        self.assertEqual(sheet.getContents("B2"), "=sum(A2:A3)")
        # Sorting only column A is fine: B2 is outside the range
        sheet.sortRows("A2:A4", "A")
        self.assertEqual(sheet.getContents("A2"), "0")
        self.assertEqual(sheet.getContents("B2"), "=sum(A2:A3)")
        with self.assertRaises(ValueError):
            sheet.sortRows("A2:A4", "B")
        sheet.setAlias("A3", "middle")
        with self.assertRaises(ValueError):
            sheet.sortRows("A2:A4", "A", False)
        sheet.setAlias("A3", "")
        sheet.mergeCells("C3:D3")
        with self.assertRaises(ValueError):
            sheet.sortRows("A2:D4", "A")
        self.assertEqual(sheet.getContents("A2"), "0")

    def testSortRowsUndo(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "2")
        sheet.set("A2", "1")
        sheet.set("B1", "=A1 * 2")
        self.doc.recompute()
        self.doc.openTransaction("Sort")
        sheet.sortRows("A1:B2", "A")
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(sheet.getContents("B2"), "=A2 * 2")
        self.assertEqual(sheet.B2, 4)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "2")
        self.assertEqual(sheet.getContents("B1"), "=A1 * 2")
        self.assertEqual(sheet.getContents("B2"), "")

    def testDecimals(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "2")
        sheet.set("A2", "=A1 / 3")
        self.doc.recompute()
        self.assertIsNone(sheet.getDecimals("A1"))
        # Formatted values follow the decimals of the cell
        self.assertEqual(sheet.findCells("000", False, False, True), [])
        self.doc.openTransaction("Decimals")
        sheet.setDecimals("A1:A2", 3)
        self.doc.commitTransaction()
        self.assertEqual(sheet.getDecimals("A2"), 3)
        self.doc.undo()
        self.assertIsNone(sheet.getDecimals("A2"))
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(sheet.getDecimals("A2"), 3)
        self.assertEqual(sheet.findCells("000", False, False, True), ["A1"])
        self.assertEqual(sheet.findCells("666", False, False, True), [])
        self.assertEqual(sheet.findCells("667", False, False, True), ["A2"])
        # Only the display changes
        self.assertEqual(sheet.A2, 2 / 3)
        # Copied with the cell
        sheet.fillDown("A1:A3")
        self.assertEqual(sheet.getDecimals("A3"), 3)
        with self.assertRaises(ValueError):
            sheet.setDecimals("A1", 16)
        with self.assertRaises(ValueError):
            sheet.setDecimals("A1", -1)
        with self.assertRaises(TypeError):
            sheet.setDecimals("A1", "3")
        sheet.setDecimals("A1", None)
        self.assertIsNone(sheet.getDecimals("A1"))
        # Clearing does not create cells
        sheet.setDecimals("E1:E5", None)
        self.assertEqual(sheet.getUsedCells().count("E1"), 0)

    def testDecimalsSaveAndRestore(self):
        sheet = self.sheet
        sheet.set("A1", "1.5")
        sheet.setDecimals("A1", 4)
        sheet.setDecimals("B2", 0)
        self.doc.recompute()
        path = os.path.join(tempfile.gettempdir(), "SpreadsheetDecimals.FCStd")
        self.doc.saveAs(path)
        name = self.doc.Name
        FreeCAD.closeDocument(name)
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("Document.xml").decode("utf-8")
            # A plain optional attribute, ignored by versions that do not know it
            self.assertIn('decimals="4"', xml)
            self.doc = FreeCAD.openDocument(path)
            sheet = self.doc.getObject("Spreadsheet")
            self.assertEqual(sheet.getDecimals("A1"), 4)
            self.assertEqual(sheet.getDecimals("B2"), 0)
            self.assertEqual(sheet.getContents("A1"), "1.5")
        finally:
            os.remove(path)

    def testNumberFormat(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "0.125")
        sheet.set("A2", "12345.678")
        sheet.set("A3", "2")
        sheet.set("A4", "=5 mm")
        self.doc.recompute()
        self.assertIsNone(sheet.getNumberFormat("A1"))
        self.assertEqual(sheet.findCells("%", False, False, True), [])
        self.doc.openTransaction("Number format")
        sheet.setNumberFormat("A1", "percent")
        self.doc.commitTransaction()
        self.assertEqual(sheet.getNumberFormat("A1"), "percent")
        self.doc.undo()
        self.assertIsNone(sheet.getNumberFormat("A1"))
        self.doc.redo()
        self.assertEqual(sheet.getNumberFormat("A1"), "percent")
        sheet.setDecimals("A1", 1)
        self.doc.recompute()
        # 12.5% (the decimal separator is the one of the locale)
        self.assertEqual(sheet.findCells("5%", False, False, True), ["A1"])
        # Only the display changes
        self.assertEqual(sheet.A1, 0.125)
        self.assertEqual(sheet.getContents("A1"), "0.125")

        sheet.setNumberFormat("A2:A4", "scientific")
        sheet.setDecimals("A2", 2)
        self.doc.recompute()
        # 1.23E+04, and integers and quantities too
        self.assertEqual(sheet.findCells("E+04", False, False, True), ["A2"])
        self.assertEqual(sheet.findCells("E+00", False, False, True), ["A3", "A4"])
        # A number with a unit is not a percentage
        sheet.setNumberFormat("A4", "percent")
        self.doc.recompute()
        self.assertEqual(sheet.findCells("%", False, False, True), ["A1"])

        sheet.setNumberFormat("A2", None)
        self.assertIsNone(sheet.getNumberFormat("A2"))
        sheet.setNumberFormat("A3", "general")
        self.assertIsNone(sheet.getNumberFormat("A3"))
        # Copied with the cell
        sheet.fillDown("A1:A2")
        self.assertEqual(sheet.getNumberFormat("A2"), "percent")
        # Going back to the default does not create cells
        sheet.setNumberFormat("E1:E5", None)
        self.assertNotIn("E1", sheet.getUsedCells())
        with self.assertRaises(ValueError):
            sheet.setNumberFormat("A1", "currency")
        with self.assertRaises(TypeError):
            sheet.setNumberFormat("A1", 1)

    def testNumberFormatSaveAndRestore(self):
        sheet = self.sheet
        sheet.set("A1", "0.5")
        sheet.setNumberFormat("A1", "percent")
        sheet.setNumberFormat("B1", "scientific")
        self.doc.recompute()
        path = os.path.join(tempfile.gettempdir(), "SpreadsheetNumberFormat.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        try:
            with zipfile.ZipFile(path) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            xml = files["Document.xml"].decode("utf-8")
            # A plain optional attribute, ignored by versions that do not know it
            self.assertIn('numberFormat="percent"', xml)
            # A format a later version may add is shown as General
            files["Document.xml"] = xml.replace(
                'numberFormat="scientific"', 'numberFormat="currency"'
            ).encode("utf-8")
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            self.doc = FreeCAD.openDocument(path)
            sheet = self.doc.getObject("Spreadsheet")
            self.assertEqual(sheet.getNumberFormat("A1"), "percent")
            self.assertIsNone(sheet.getNumberFormat("B1"))
            self.assertEqual(sheet.A1, 0.5)
        finally:
            os.remove(path)

    def testFontSize(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "Title")
        self.assertIsNone(sheet.getFontSize("A1"))
        self.doc.openTransaction("Font size")
        sheet.setFontSize("A1:B1", 16)
        self.doc.commitTransaction()
        self.assertEqual(sheet.getFontSize("A1"), 16)
        self.assertEqual(sheet.getFontSize("B1"), 16)
        self.doc.undo()
        self.assertIsNone(sheet.getFontSize("A1"))
        self.doc.redo()
        self.assertEqual(sheet.getFontSize("A1"), 16)
        # Copied with the cell
        sheet.fillDown("A1:A2")
        self.assertEqual(sheet.getFontSize("A2"), 16)
        sheet.setFontSize("A1", None)
        self.assertIsNone(sheet.getFontSize("A1"))
        # Going back to the default does not create cells
        sheet.setFontSize("E1:E5", None)
        self.assertNotIn("E1", sheet.getUsedCells())
        with self.assertRaises(ValueError):
            sheet.setFontSize("A1", 0)
        with self.assertRaises(ValueError):
            sheet.setFontSize("A1", 410)
        with self.assertRaises(TypeError):
            sheet.setFontSize("A1", 12.5)

    def testFontSizeSaveAndRestore(self):
        sheet = self.sheet
        sheet.set("A1", "Title")
        sheet.setFontSize("A1", 20)
        path = os.path.join(tempfile.gettempdir(), "SpreadsheetFontSize.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("Document.xml").decode("utf-8")
            # A plain optional attribute, ignored by versions that do not know it
            self.assertIn('fontSize="20"', xml)
            self.doc = FreeCAD.openDocument(path)
            self.assertEqual(self.doc.getObject("Spreadsheet").getFontSize("A1"), 20)
        finally:
            os.remove(path)

    def _formatEverything(self, address):
        sheet = self.sheet
        sheet.setStyle(address, "bold|italic")
        sheet.setAlignment(address, "center|top")
        sheet.setForeground(address, (1.0, 0.0, 0.0))
        sheet.setBackground(address, (0.0, 1.0, 0.0))
        sheet.setDisplayUnit(address, "mm")
        sheet.setDecimals(address, 4)
        sheet.setNumberFormat(address, "scientific")
        sheet.setBorders(address, "all")
        sheet.setFontSize(address, 14)

    def _formatOf(self, address):
        sheet = self.sheet
        return (
            sheet.getStyle(address),
            sheet.getAlignment(address),
            sheet.getForeground(address),
            sheet.getBackground(address),
            sheet.getDisplayUnit(address),
            sheet.getDecimals(address),
            sheet.getNumberFormat(address),
            sheet.getBorders(address),
            sheet.getFontSize(address),
        )

    def testClearFormat(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "=2 * 3")
        sheet.setAlias("A1", "six")
        self._formatEverything("A1")
        sheet.set("B1", "merged")
        sheet.mergeCells("B1:C1")
        sheet.setStyle("B1", "bold")
        self.doc.recompute()
        formatted = self._formatOf("A1")
        self.doc.openTransaction("Clear formatting")
        sheet.clearFormat("A1:C1")
        self.doc.commitTransaction()
        self.assertEqual(self._formatOf("A1"), (None,) * 9)
        self.assertIsNone(sheet.getStyle("B1"))
        # The content, alias and merging stay
        self.assertEqual(sheet.getContents("A1"), "=2 * 3")
        self.assertEqual(sheet.getAlias("A1"), "six")
        self.assertEqual(sheet.getMergedCells(), ["B1:C1"])
        self.doc.recompute()
        self.assertEqual(sheet.six, 6)
        self.doc.undo()
        self.assertEqual(self._formatOf("A1"), formatted)
        self.assertEqual(sheet.getStyle("B1"), {"bold"})
        # Does not create cells
        sheet.clearFormat("E1:E3")
        self.assertNotIn("E1", sheet.getUsedCells())

    def testCopyFormat(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "1")
        sheet.setAlias("A1", "first")
        self._formatEverything("A1")
        sheet.set("A2", "0.5")
        sheet.setNumberFormat("A2", "percent")
        sheet.set("C1", "3")
        sheet.setStyle("C1", "underline")
        self.doc.recompute()

        self.doc.openTransaction("Paste formatting")
        sheet.copyFormat("A1:A2", "C1")
        self.doc.commitTransaction()
        # A single target cell receives the size of the source
        self.assertEqual(self._formatOf("C1"), self._formatOf("A1"))
        self.assertEqual(sheet.getNumberFormat("C2"), "percent")
        self.assertIsNone(sheet.getStyle("C2"))
        # Only the formatting
        self.assertEqual(sheet.getContents("C1"), "3")
        self.assertIsNone(sheet.getAlias("C1"))
        self.assertEqual(sheet.getContents("C2"), "")
        self.doc.undo()
        self.assertEqual(sheet.getStyle("C1"), {"underline"})
        self.assertIsNone(sheet.getNumberFormat("C2"))

        # A larger target is filled with whole copies of the source
        sheet.copyFormat("A1:A2", "E1:E5")
        self.assertEqual(sheet.getStyle("E3"), {"bold", "italic"})
        self.assertEqual(sheet.getNumberFormat("E4"), "percent")
        self.assertNotIn("E5", sheet.getUsedCells())
        # An unformatted source cell removes the formatting, without creating cells
        sheet.copyFormat("H1", "E1")
        self.assertEqual(self._formatOf("E1"), (None,) * 9)
        sheet.copyFormat("H1", "J1:J3")
        self.assertNotIn("J1", sheet.getUsedCells())
        # Overlapping ranges use the formatting from before the copy
        sheet.copyFormat("A1:A2", "A2:A3")
        self.assertEqual(sheet.getStyle("A2"), {"bold", "italic"})
        self.assertEqual(sheet.getNumberFormat("A3"), "percent")
        # A merged cell takes the formatting at its first cell
        sheet.mergeCells("K1:L1")
        sheet.copyFormat("A1", "K1:L1")
        self.assertEqual(sheet.getStyle("K1"), {"bold", "italic"})
        self.assertEqual(sheet.getMergedCells(), ["K1:L1"])
        # The cells of a merged source get its borders along their edges only
        sheet.mergeCells("N1:O2")
        sheet.setBorders("N1:O2", "all", "outline")
        sheet.copyFormat("N1:O2", "Q1")
        self.assertEqual(sheet.getBorders("Q1"), {"top", "left"})
        self.assertEqual(sheet.getBorders("R2"), {"bottom", "right"})

    def testBorders(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        sheet.set("A1", "1")
        self.assertIsNone(sheet.getBorders("A1"))
        # Every cell gets exactly the given borders
        self.doc.openTransaction("Borders")
        sheet.setBorders("A1:B2", "top|left")
        self.doc.commitTransaction()
        self.assertEqual(sheet.getBorders("A1"), {"top", "left"})
        self.assertEqual(sheet.getBorders("B2"), {"top", "left"})
        self.doc.undo()
        self.assertIsNone(sheet.getBorders("A1"))
        self.doc.redo()
        self.assertEqual(sheet.getBorders("A1"), {"top", "left"})
        sheet.setBorders("A1", {"bottom"}, "add")
        self.assertEqual(sheet.getBorders("A1"), {"top", "left", "bottom"})
        sheet.setBorders("A1:B2", "top|left", "remove")
        self.assertEqual(sheet.getBorders("A1"), {"bottom"})
        self.assertIsNone(sheet.getBorders("B2"))
        sheet.setBorders("A1", "all")
        self.assertEqual(sheet.getBorders("A1"), {"top", "left", "bottom", "right"})
        sheet.setBorders("A1", "")
        self.assertIsNone(sheet.getBorders("A1"))
        # Only the display changes
        self.assertEqual(sheet.getContents("A1"), "1")

        # A frame around the range
        sheet.setBorders("C3:E5", "all", "outline")
        self.assertEqual(sheet.getBorders("C3"), {"top", "left"})
        self.assertEqual(sheet.getBorders("D3"), {"top"})
        self.assertEqual(sheet.getBorders("E5"), {"bottom", "right"})
        self.assertIsNone(sheet.getBorders("D4"))
        sheet.setBorders("C3:E5", "bottom", "outline")
        self.assertEqual(sheet.getBorders("C5"), {"bottom", "left"})
        self.assertEqual(sheet.getBorders("C4"), {"left"})
        # A merged cell is framed with its whole area
        sheet.mergeCells("G1:H2")
        sheet.setBorders("G1:H2", "all", "outline")
        self.assertEqual(sheet.getBorders("G1"), {"top", "left", "bottom", "right"})
        sheet.setBorders("G1:H2", "")
        sheet.setBorders("F1:H1", "bottom", "outline")
        self.assertEqual(sheet.getBorders("G1"), {"bottom"})

        # Removing or clearing borders does not create cells
        sheet.setBorders("J1:J5", "", "replace")
        sheet.setBorders("J1:J5", "all", "remove")
        self.assertNotIn("J1", sheet.getUsedCells())
        with self.assertRaises(ValueError):
            sheet.setBorders("A1", "thick")
        with self.assertRaises(ValueError):
            sheet.setBorders("A1", "top", "invert")
        with self.assertRaises(TypeError):
            sheet.setBorders("A1", {1})
        with self.assertRaises(TypeError):
            sheet.setBorders("A1", 1)

    def testBordersMoveAndCopyWithTheCell(self):
        sheet = self.sheet
        sheet.set("A1", "1")
        sheet.setBorders("A1", "bottom")
        sheet.fillDown("A1:A2")
        self.assertEqual(sheet.getBorders("A2"), {"bottom"})
        sheet.insertRows("1", 1)
        self.assertIsNone(sheet.getBorders("A1"))
        self.assertEqual(sheet.getBorders("A2"), {"bottom"})
        self.assertEqual(sheet.getBorders("A3"), {"bottom"})

    def testBordersSaveAndRestore(self):
        sheet = self.sheet
        sheet.set("A1", "1.5")
        sheet.setBorders("A1", "top|bottom")
        sheet.setBorders("B2", "right")
        self.doc.recompute()
        path = os.path.join(tempfile.gettempdir(), "SpreadsheetBorders.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        try:
            with zipfile.ZipFile(path) as archive:
                files = {name: archive.read(name) for name in archive.namelist()}
            xml = files["Document.xml"].decode("utf-8")
            # A plain optional attribute, ignored by versions that do not know it
            self.assertIn('borders="top|bottom"', xml)
            # Border names a later version may add are skipped
            files["Document.xml"] = xml.replace(
                'borders="top|bottom"', 'borders="top|double|bottom"'
            ).encode("utf-8")
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            self.doc = FreeCAD.openDocument(path)
            sheet = self.doc.getObject("Spreadsheet")
            self.assertEqual(sheet.getBorders("A1"), {"top", "bottom"})
            self.assertEqual(sheet.getBorders("B2"), {"right"})
            self.assertEqual(sheet.getContents("A1"), "1.5")
        finally:
            os.remove(path)

    def _findSample(self):
        sheet = self.sheet
        sheet.set("B1", "Apple pie")
        sheet.set("A2", "apple")
        sheet.set("C1", "=A3 * 2")
        sheet.set("A3", "21")
        sheet.set("A4", "pear")
        self.doc.recompute()

    def testFindCells(self):
        sheet = self.sheet
        self._findSample()
        # Row by row, without case, in contents
        self.assertEqual(sheet.findCells("apple"), ["B1", "A2"])
        self.assertEqual(sheet.findCells("apple", True), ["A2"])
        self.assertEqual(sheet.findCells("apple", False, True), ["A2"])
        self.assertEqual(sheet.findCells("A3"), ["C1"])
        self.assertEqual(sheet.findCells(""), [])
        self.assertEqual(sheet.findCells("'"), [])
        # In values
        self.assertEqual(sheet.findCells("42", False, False, True), ["C1"])
        self.assertEqual(sheet.findCells("A3", False, False, True), [])

    def testReplaceCells(self):
        sheet = self.sheet
        self._findSample()
        sheet.setStyle("A4", "bold")
        self.assertEqual(sheet.replaceCells("APPLE", "Cherry"), 2)
        self.assertEqual(sheet.getContents("B1"), "'Cherry pie")
        self.assertEqual(sheet.getContents("A2"), "'Cherry")
        # Formulas are edited as text and stay formulas
        self.assertEqual(sheet.replaceCells("A3", "A2"), 1)
        self.assertEqual(sheet.getContents("C1"), "=A2 * 2")
        # Text that looks like a number stays text
        sheet.set("D1", "x")
        self.assertEqual(sheet.replaceCells("x", "12", True, True), 1)
        self.assertEqual(sheet.getContents("D1"), "'12")
        # Limited to a range; an empty result keeps the formatting
        self.assertEqual(sheet.replaceCells("pear", "", False, True, "A1:A3"), 0)
        self.assertEqual(sheet.replaceCells("pear", "", False, True, "A4"), 1)
        self.assertEqual(sheet.getContents("A4"), "")
        self.assertEqual(sheet.getStyle("A4"), {"bold"})
        with self.assertRaises(ValueError):
            sheet.replaceCells("", "x")

    def testReplaceCellsUndo(self):
        sheet = self.sheet
        self.doc.UndoMode = 1
        self._findSample()
        self.doc.openTransaction("Replace All")
        sheet.replaceCells("apple", "plum")
        self.doc.commitTransaction()
        self.assertEqual(sheet.getContents("A2"), "'plum")
        self.doc.undo()
        self.assertEqual(sheet.getContents("A2"), "'apple")
        self.assertEqual(sheet.getContents("B1"), "'Apple pie")
