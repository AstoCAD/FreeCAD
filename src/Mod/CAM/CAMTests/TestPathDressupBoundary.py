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
