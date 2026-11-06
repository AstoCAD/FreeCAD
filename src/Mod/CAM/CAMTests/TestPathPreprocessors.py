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
#   See the GNU Library General Public License for more details.               #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""Tests for the gcode import preprocessors (Path/Post/scripts/*_pre.py)."""

import unittest

from Path.Post.scripts import gcode_pre
from Path.Post.scripts import slic3r_pre


class TestPathPreprocessors(unittest.TestCase):
    def test_gcode_pre_line_numbers(self):
        """gcode_pre strips line numbers, with or without a space after them."""
        gcode = "\n".join(
            [
                "N10 G0 X0 Y0",
                "N20",
                "N30G1 X3 F100",
                "N40 Y4",
                "n50 G1 Z-1",
                "G1 X6",
            ]
        )
        self.assertEqual(
            gcode_pre.parse(gcode),
            ["G0 X0 Y0", "G1 X3 F100", "G1 Y4", "G1 Z-1", "G1 X6"],
        )

    def test_slic3r_pre_line_numbers(self):
        """slic3r_pre strips line numbers, with or without a space after them."""
        gcode = "\n".join(["N10 G1 X1 Y1", "N20", "N30G1 X2", "N40 Y3"])
        self.assertEqual(slic3r_pre.parse(gcode), "G1 X1 Y1\nG1 X2\nG1 Y3\n")
