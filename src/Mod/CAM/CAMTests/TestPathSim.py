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
# ***************************************************************************

import FreeCAD
import Part
import Path
from CAMTests.PathTestUtils import PathTestBase


class TestPathSim(PathTestBase):
    """Tests of the voxel simulator PathSimulator.PathSim"""

    def setUp(self):
        try:
            import PathSimulator
        except ImportError:
            self.skipTest("PathSimulator is not available")
        self.sim = PathSimulator.PathSim()
        self.tool = Part.makeCylinder(1, 5)

    def test_cut_without_stock_raises(self):
        """A tool cutting before BeginSimulation raises instead of crashing"""
        self.sim.SetToolShape(self.tool, 0.5)
        with self.assertRaises(RuntimeError):
            self.sim.ApplyCommand(FreeCAD.Placement(), Path.Command("G1", {"X": 1}))
        with self.assertRaises(RuntimeError):
            self.sim.ApplyCommand(
                FreeCAD.Placement(), Path.Command("G2", {"X": 1, "I": 0.5})
            )
        # a command that does not cut only moves the position
        pos = self.sim.ApplyCommand(FreeCAD.Placement(), Path.Command("G90"))
        self.assertRoughly(pos.Base.Length, 0)

    def test_cut_with_stock(self):
        """With a stock and a tool the commands cut the stock"""
        self.sim.BeginSimulation(Part.makeBox(10, 10, 10), 1.0)
        self.sim.SetToolShape(self.tool, 0.5)
        pos = FreeCAD.Placement(FreeCAD.Vector(0, 5, 9), FreeCAD.Rotation())
        pos = self.sim.ApplyCommand(pos, Path.Command("G1", {"X": 10, "Y": 5, "Z": 9}))
        self.assertRoughly(pos.Base.x, 10)
        outer, inner = self.sim.GetResultMesh()
        self.assertGreater(outer.CountFacets, 0)
