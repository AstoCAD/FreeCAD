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
import Part
import Path
import CAMTests.PathTestUtils as PathTestUtils
import Path.Dressup.Boundary as PathDressupBoundary
import Path.Main.Job as PathJob
import Path.Op.Gui.Array as PathArray
import Path.Op.Profile as PathProfile


class TestDressupBoundaryArray(PathTestUtils.PathTestBase):
    """The Boundary dressup applied to an Array operation."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestDressupBoundaryArray")
        FreeCAD.setActiveDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        self.job = PathJob.Create("Job", [box], None)
        self.profile = PathProfile.Create("Profile")
        self.profile2 = PathProfile.Create("Profile2")
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _array(self, bases):
        array = self.doc.addObject("Path::FeaturePython", "Array")
        PathArray.ObjectArray(array)
        array.Base = bases
        array.Copies = 1
        array.Offset = FreeCAD.Vector(20, 0, 0)
        self.job.Proxy.addOperation(array)
        self.doc.recompute()
        return array

    def test00_array_base(self):
        """An Array has a list of bases and no heights of its own (#11180)."""
        self.profile2.setExpression("SafeHeight", None)
        self.profile2.setExpression("ClearanceHeight", None)
        self.profile2.SafeHeight = self.profile.SafeHeight.Value + 7
        self.profile2.ClearanceHeight = self.profile.ClearanceHeight.Value + 9
        self.doc.recompute()
        array = self._array([self.profile, self.profile2])
        self.assertTrue(array.Path.Commands)

        boundary = Part.makeBox(100, 100, 100, FreeCAD.Vector(-50, -50, -50))
        pb = PathDressupBoundary.PathBoundary(array, boundary)
        commands = pb.execute()

        self.assertTrue(commands)
        # Every base must be cleared, so the highest heights are used.
        self.assertRoughly(pb.safeHeight, self.profile2.SafeHeight.Value)
        self.assertRoughly(pb.clearanceHeight, self.profile2.ClearanceHeight.Value)


class TestDressupBoundaryDrill(PathTestUtils.PathTestBase):
    """The Boundary dressup keeps the drill cycles whose holes it contains."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestDressupBoundaryDrill")
        FreeCAD.setActiveDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        self.job = PathJob.Create("Job", [box], None)
        self.op = PathProfile.Create("Profile")
        self.doc.recompute()
        clearance = self.op.ClearanceHeight.Value
        safe = self.op.SafeHeight.Value
        # Consecutive cycles, as the Drilling operation emits them: no move
        # between the holes, the tool travels at the retract plane.
        self.op.Path = Path.Path(
            [
                Path.Command("G0", {"Z": clearance}),
                Path.Command("G0", {"X": 0, "Y": 0}),
                Path.Command("G0", {"Z": safe}),
                Path.Command("G81", {"X": 0, "Y": 0, "Z": -5, "R": 3, "F": 1}),
                Path.Command("G81", {"X": 20, "Y": 0, "Z": -5, "R": 3, "F": 1}),
                Path.Command("G81", {"X": 40, "Y": 0, "Z": -5, "R": 3, "F": 1}),
                Path.Command("G0", {"Z": clearance}),
            ]
        )

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _holes(self, x0, x1, inside):
        boundary = Part.makeBox(x1 - x0, 100, 200, FreeCAD.Vector(x0, -50, -100))
        commands = PathDressupBoundary.PathBoundary(self.op, boundary, inside).execute()
        return [cmd.x for cmd in commands.Commands if cmd.Name == "G81"]

    def test00_holes_inside(self):
        """Only the holes inside the boundary are drilled."""
        self.assertEqual(self._holes(-10, 50, True), [0, 20, 40])
        self.assertEqual(self._holes(30, 50, True), [40])
        self.assertEqual(self._holes(10, 50, True), [20, 40])

    def test01_holes_outside(self):
        """Only the holes outside an excluding boundary are drilled."""
        self.assertEqual(self._holes(15, 25, False), [0, 40])
        self.assertEqual(self._holes(-10, 10, False), [20, 40])
