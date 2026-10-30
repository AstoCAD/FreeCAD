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

"""GUI tests for the BIM_Box command."""

import FreeCAD as App
import FreeCADGui as Gui
from bimcommands.BimBox import BIM_Box
from bimtests import TestArchBaseGui


class TestBimBoxGui(TestArchBaseGui.TestArchBaseGui):

    def test_numeric_height_input_ends_command(self):
        """Entering the height numerically must create the box and end the point input.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/33665
        """
        self.printTestMessage("BIM_Box with numeric height input...")
        cmd = BIM_Box()
        cmd.Activated()
        try:
            # Pick the base rectangle in the 3D view
            for point in (App.Vector(0, 0, 0), App.Vector(1000, 0, 0), App.Vector(1000, 500, 0)):
                cmd.MoveCallback(point, None)
                cmd.PointCallback(point, None)

            # Type the height in the task panel and press Enter
            cmd.HeightValue = 300.0
            cmd.setHeightUI()
            self.pump_gui_events()

            boxes = [o for o in self.document.Objects if o.TypeId == "Part::Box"]
            self.assertEqual(len(boxes), 1)
            self.assertAlmostEqual(boxes[0].Height.Value, 300.0)
            self.assertIsNone(App.activeDraftCommand)
            # The point input of the Snapper must be closed, otherwise a further
            # numeric input would call back into the finished command.
            self.assertIsNone(Gui.Snapper.callbackClick)
            self.assertIsNone(Gui.draftToolBar.cancel)
        finally:
            if Gui.draftToolBar.cancel:
                Gui.draftToolBar.escape()
            App.activeDraftCommand = None
