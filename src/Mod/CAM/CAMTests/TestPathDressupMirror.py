# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import FreeCAD
import Path
import Path.Dressup.Gui.Mirror as PathDressupMirror

from CAMTests.PathTestUtils import PathTestBase


class TestDressupMirror(PathTestBase):
    """Unit tests for the Mirror dressup."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestDressupMirror")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _mirror(self, gcode, axis, offset):
        base = self.doc.addObject("Path::Feature", "Base")
        base.Path = Path.Path([Path.Command(line) for line in gcode])
        obj = self.doc.addObject("Path::FeaturePython", "Mirror")
        PathDressupMirror.ObjectDressup(obj, base)
        obj.MirrorAxis = axis
        obj.Offset = offset
        obj.Proxy.execute(obj)
        return obj.Path.Commands

    def test00(self):
        """A Z offset moves the retract plane of a canned cycle with its bottom."""
        commands = self._mirror(
            ["G0 X1 Y2 Z10", "G81 X1 Y2 Z-3 R2 F100", "G83 X4 Y2 Z-3 R2 Q1 F100", "G80"],
            "X",
            FreeCAD.Vector(0, 0, 5),
        )
        drills = [c for c in commands if c.Name in ("G81", "G83")]
        self.assertEqual(len(drills), 2)
        for cmd in drills:
            self.assertRoughly(cmd.Parameters["Z"], 2)
            self.assertRoughly(cmd.Parameters["R"], 7)
            self.assertRoughly(cmd.Parameters["Y"], -2)
