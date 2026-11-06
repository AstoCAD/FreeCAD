# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""Tests for the legacy Heidenhain post processor (heidenhain_legacy_post.py)."""

from importlib import reload

import FreeCAD

import Path
import CAMTests.PathTestUtils as PathTestUtils
from Path.Post.scripts import heidenhain_legacy_post as postprocessor

ARGS = "--no-show-editor --no-warns"


class _OperationProxy:
    """Proxy of an operation that is neither a tool controller nor a known op kind."""


class TestHeidenhainLegacyPost(PathTestUtils.PathTestBase):
    @classmethod
    def setUpClass(cls):
        cls.doc = FreeCAD.newDocument("TestHeidenhainLegacyPost")

    @classmethod
    def tearDownClass(cls):
        FreeCAD.closeDocument(cls.doc.Name)

    def setUp(self):
        reload(postprocessor)
        self.op = self.doc.addObject("Path::FeaturePython", "op")
        self.op.Proxy = _OperationProxy()
        self.op.Path = Path.Path(
            [
                Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 5.0}),
                Path.Command("G1", {"X": 10.0, "Y": 0.0, "Z": -1.0, "F": 100.0}),
                Path.Command("G1", {"X": 10.0, "Y": 10.0, "Z": -1.0}),
                Path.Command("G0", {"Z": 5.0}),
            ]
        )

    def tearDown(self):
        self.doc.removeObject(self.op.Name)

    def test010_operation_moves_are_posted(self):
        """The moves of an operation are output, and "-" returns the program."""
        gcode = postprocessor.export([self.op], "-", ARGS)

        self.assertIsInstance(gcode, str)
        lines = gcode.splitlines()
        self.assertEqual(lines[0], "0 BEGIN PGM MM")
        self.assertEqual(lines[-1].split(" ", 1)[1], "END PGM MM")
        moves = [line.split(" ", 1)[1] for line in lines if line.split(" ", 1)[1].startswith("L ")]
        self.assertEqual(
            moves,
            [
                "L X0.000 Y0.000 Z5.000 R0 F8000 M3",
                "L X10.000 Z-1.000 R0 F100 M",
                "L Y10.000 R0 F100 M",
                "L Z5.000 R0 F8000 M5",
            ],
        )

    def test020_each_export_is_a_program_of_its_own(self):
        """A second export does not repeat the output of the first one."""
        first = postprocessor.export([self.op], "-", ARGS)
        second = postprocessor.export([self.op], "-", ARGS)

        self.assertEqual(second.count("BEGIN PGM"), 1)
        self.assertEqual(second.count("END PGM"), 1)
        self.assertEqual(len(second.splitlines()), len(first.splitlines()))
