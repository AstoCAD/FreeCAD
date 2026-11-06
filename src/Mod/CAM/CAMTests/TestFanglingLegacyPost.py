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

"""Tests for the legacy FangLing plasma post processor (fangling_legacy_post.py)."""

from importlib import reload

import FreeCAD

import Path
import CAMTests.PathTestUtils as PathTestUtils
from Path.Post.scripts import fangling_legacy_post as postprocessor


class TestFanglingLegacyPost(PathTestUtils.PathTestBase):
    @classmethod
    def setUpClass(cls):
        cls.doc = FreeCAD.newDocument("TestFanglingLegacyPost")

    @classmethod
    def tearDownClass(cls):
        FreeCAD.closeDocument(cls.doc.Name)

    def setUp(self):
        reload(postprocessor)
        self.obj = self.doc.addObject("Path::Feature", "testpath")
        # Rapids that move Z only are filtered out by this post.
        self.obj.Path = Path.Path(
            [
                Path.Command("G0", {"X": 0.0, "Y": 0.0, "Z": 10.0}),
                Path.Command("G0", {"Z": 5.0}),
                Path.Command("G0", {"Z": 3.0}),
                Path.Command("G1", {"X": 10.0, "Y": 0.0, "Z": 3.0, "F": 100.0}),
                Path.Command("G1", {"X": 10.0, "Y": 10.0, "Z": 3.0}),
            ]
        )

    def tearDown(self):
        self.doc.removeObject(self.obj.Name)

    def test010_modal_after_filtered_rapids(self):
        """--modal does not fail on consecutive rapids that were filtered out."""
        args = "--no-header --no-comments --no-show-editor"
        plain = postprocessor.export([self.obj], "-", args)
        reload(postprocessor)
        modal = postprocessor.export([self.obj], "-", args + " --modal")

        self.assertIsInstance(modal, str)
        self.assertIn("G1 X10.000 Y10.000", plain.splitlines())
        # only the repeated G1 loses its command word
        self.assertEqual(
            modal.splitlines(),
            [
                "X10.000 Y10.000" if line == "G1 X10.000 Y10.000" else line
                for line in plain.splitlines()
            ],
        )
