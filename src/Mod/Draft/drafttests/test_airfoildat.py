# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2013 Yorik van Havre <yorik@uncreated.net>              *
# *   Copyright (c) 2019 Eliud Cabrera Castillo <e.cabrera-castillo@tum.de> *
# *   Copyright (c) 2025 FreeCAD Project Association                        *
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
# ***************************************************************************

"""Unit tests for the Draft Workbench, Airfoil DAT import and export tests."""

## @package test_airfoildat
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, Airfoil DAT tests.

## \addtogroup drafttests
# @{

import os
import shutil
import tempfile
from unittest import mock

import FreeCAD as App
import Draft
from drafttests import auxiliary as aux
from drafttests import test_base
from draftutils.messages import _msg


class DraftAirfoilDAT(test_base.DraftTestCaseDoc):
    """Test reading and writing of AirfoilDAT with Draft."""

    def test_read_airfoildat(self):
        """Read an airfoil DAT file and import its elements as objects."""
        operation = "importAirfoilDAT.import"
        _msg("  Test '{}'".format(operation))
        _msg("  This test requires a DAT file with airfoil data to read.")

        file = "Mod/Draft/drafttest/test.dat"
        in_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(in_file))
        _msg("  exists={}".format(os.path.exists(in_file)))

        obj = aux.fake_function(in_file)
        self.assertTrue(obj, "'{}' failed".format(operation))

    def test_export_airfoildat(self):
        """Create some figures and export them to an airfoil DAT file."""
        operation = "importAirfoilDAT.export"
        _msg("  Test '{}'".format(operation))

        file = "Mod/Draft/drafttest/out_test.dat"
        out_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(out_file))
        _msg("  exists={}".format(os.path.exists(out_file)))

        obj = aux.fake_function(out_file)
        self.assertTrue(obj, "'{}' failed".format(operation))


class DraftAirfoilDATEncoding(test_base.DraftTestCaseDoc):
    """Test reading airfoil DAT files whose name line is not ASCII."""

    NAME = "Profil_Größe"
    COORDS = "1.0 0.0\n0.5 0.08\n0.0 0.0\n0.5 -0.04\n1.0 0.0\n"

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def _read(self, encoding):
        """Write the airfoil in `encoding`, import it and check the result."""
        import importAirfoilDAT

        path = os.path.join(self.tmpdir, "airfoil.dat")
        with open(path, "wb") as f:
            f.write((self.NAME + "\n" + self.COORDS).encode(encoding))

        wire = importAirfoilDAT.process(path)
        self.assertIsNotNone(wire)
        self.doc.recompute()
        self.assertEqual(len(wire.Shape.Vertexes), 4)
        self.assertTrue(wire.Points[1].isEqual(App.Vector(0.5, 0.08, 0), 1e-9))
        self.assertTrue(wire.Points[3].isEqual(App.Vector(0.5, -0.04, 0), 1e-9))

        # The Part::Feature variant names the object after the name line
        with mock.patch.object(importAirfoilDAT, "useDraftWire", False):
            face = importAirfoilDAT.process(path)
        self.assertIsNotNone(face)
        self.assertEqual(face.Label, self.NAME)

    def test_read_latin1_name(self):
        """A Latin-1 name line is decoded, not an import error."""
        self._read("latin-1")

    def test_read_utf8_name(self):
        """A UTF-8 name line is decoded."""
        self._read("utf-8")

    def test_read_utf8_bom_name(self):
        """A UTF-8 byte order mark is not part of the name."""
        self._read("utf-8-sig")


class DraftAirfoilDATNumbers(test_base.DraftTestCaseDoc):
    """Test reading the number formats of airfoil DAT files."""

    def test_read_signed_numbers_and_exponents(self):
        """Coordinates like 1.0e+00 (numpy.savetxt) or +0.08 are read, not skipped."""
        import importAirfoilDAT

        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        path = os.path.join(tmpdir, "airfoil.dat")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "Profile\n"
                "1.000000000000000000e+00 0.000000000000000000e+00\n"
                "5.000000000000000000e-01 +8.000000000000000167e-02\n"
                "0.000000000000000000e+00 0.000000000000000000e+00\n"
                "+5.0E-01 -4.0E-02\n"
                "1.0E+00 0.0E+00\n"
            )
        wire = importAirfoilDAT.process(path)
        self.assertIsNotNone(wire)
        self.doc.recompute()
        self.assertEqual(len(wire.Shape.Vertexes), 4)
        expected = [(1, 0), (0.5, 0.08), (0, 0), (0.5, -0.04)]
        for point, (x, y) in zip(wire.Points, expected):
            self.assertTrue(point.isEqual(App.Vector(x, y, 0), 1e-9), point)


## @}
