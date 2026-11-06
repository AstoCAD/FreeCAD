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

"""Tests for the legacy Roland Modela post processor (rml_legacy_post.py)."""

import os
import tempfile
from importlib import reload

import FreeCAD

import Path
import CAMTests.PathTestUtils as PathTestUtils
from Path.Post.scripts import rml_legacy_post as postprocessor

EXPECTED = "\n".join(
    [
        "PA;PA;",
        "!MC1;",
        "VS2.0;",
        "!VZ1.0;",
        "PU0,0;",
        "PU;",
        "VS100.0;",
        "!VZ100.0;",
        "Z400,400,-40;",
        "!MC0;",
        "H;",
    ]
)


class TestRmlLegacyPost(PathTestUtils.PathTestBase):
    @classmethod
    def setUpClass(cls):
        cls.doc = FreeCAD.newDocument("TestRmlLegacyPost")

    @classmethod
    def tearDownClass(cls):
        FreeCAD.closeDocument(cls.doc.Name)

    def setUp(self):
        reload(postprocessor)
        self.obj = self.doc.addObject("Path::Feature", "testpath")
        self.obj.Path = Path.Path(
            [
                Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 5.0}),
                Path.Command("G1", {"X": 10.0, "Y": 10.0, "Z": -1.0, "F": 100.0}),
            ]
        )

    def tearDown(self):
        self.doc.removeObject(self.obj.Name)

    def test010_dash_returns_the_code(self):
        """With "-" as file name the code is returned, as the post-processing command expects."""
        self.assertEqual(postprocessor.export([self.obj], "-", ""), EXPECTED)

    def test020_file_is_written(self):
        """With a file name the code is written there."""
        with tempfile.TemporaryDirectory() as folder:
            filename = os.path.join(folder, "out.rml")
            postprocessor.export([self.obj], filename, "")
            with open(filename) as f:
                self.assertEqual(f.read(), EXPECTED)
