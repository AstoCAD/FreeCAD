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
"""Unit tests for the Draft Workbench, DWG import and export tests."""

## @package test_dwg
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, DWG import and export tests.

## \addtogroup drafttests
# @{

import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

import FreeCAD as App
import Draft
from drafttests import auxiliary as aux
from drafttests import test_base
from draftutils.messages import _msg


class DraftDWG(test_base.DraftTestCaseDoc):
    """Test reading and writing of DWG files with Draft."""

    def test_read_dwg(self):
        """Read a DWG file and import its elements as Draft objects."""
        operation = "importDWG.import"
        _msg("  Test '{}'".format(operation))
        _msg("  This test requires a DWG file to read.")

        file = "Mod/Draft/drafttest/test.dwg"
        in_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(in_file))
        _msg("  exists={}".format(os.path.exists(in_file)))

        obj = aux.fake_function(in_file)
        self.assertTrue(obj, "'{}' failed".format(operation))

    def test_export_dwg(self):
        """Create some figures and export them to a DWG file."""
        operation = "importDWG.export"
        _msg("  Test '{}'".format(operation))

        file = "Mod/Draft/drafttest/out_test.dwg"
        out_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(out_file))
        _msg("  exists={}".format(os.path.exists(out_file)))

        obj = aux.fake_function(out_file)
        self.assertTrue(obj, "'{}' failed".format(operation))


class DraftDWGConverterFallback(unittest.TestCase):
    """Test the converter fallback of importDWG.convertToDwg (issue #31835)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dxf = os.path.join(self.tmpdir, "drawing.dxf").replace("\\", "/")
        self.dwg = os.path.join(self.tmpdir, "drawing.dwg").replace("\\", "/")
        with open(self.dxf, "w") as f:
            f.write("0\nEOF\n")
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _convert(self, writes_output, stale_output=False):
        """Run convertToDwg in automatic mode with fake LibreDWG and ODA converters.

        `writes_output` lists the fake converters that produce the DWG file.
        """
        import importDWG

        if stale_output:
            with open(self.dwg, "w") as f:
                f.write("old")
            old = os.path.getmtime(self.dwg) - 100
            os.utime(self.dwg, (old, old))

        calls = self.calls
        dwg = self.dwg

        class FakePopen:
            def __init__(self, cmdline, **kwargs):
                calls.append(cmdline[0])
                if cmdline[0] in writes_output:
                    with open(dwg, "w") as f:
                        f.write("dwg")

            def communicate(self):
                return (None, None)

        params = types.SimpleNamespace(get_param=lambda entry, *args, **kwargs: 0)
        with mock.patch.object(importDWG, "params", params), mock.patch.object(
            importDWG, "get_libredwg_converter", lambda typ: "libredwg"
        ), mock.patch.object(importDWG, "get_oda_converter", lambda: "oda"), mock.patch.object(
            importDWG, "get_qcad_converter", lambda: None
        ), mock.patch(
            "subprocess.Popen", FakePopen
        ):
            return importDWG.convertToDwg(self.dxf, self.dwg)

    def test_fallback_when_first_converter_fails(self):
        """A failing LibreDWG conversion falls back to the ODA converter."""
        result = self._convert(writes_output=["oda"])
        self.assertEqual(self.calls, ["libredwg", "oda"])
        self.assertEqual(result, self.dwg)
        self.assertTrue(os.path.exists(self.dwg))

    def test_first_converter_success_stops(self):
        """A successful LibreDWG conversion does not run the other converters."""
        result = self._convert(writes_output=["libredwg"])
        self.assertEqual(self.calls, ["libredwg"])
        self.assertEqual(result, self.dwg)

    def test_all_converters_fail(self):
        """No output file means the conversion is reported as failed."""
        result = self._convert(writes_output=[])
        self.assertEqual(self.calls, ["libredwg", "oda"])
        self.assertIsNone(result)

    def test_stale_output_is_not_success(self):
        """An existing, unchanged output file is not taken as a successful conversion."""
        result = self._convert(writes_output=["oda"], stale_output=True)
        self.assertEqual(self.calls, ["libredwg", "oda"])
        self.assertEqual(result, self.dwg)


## @}
