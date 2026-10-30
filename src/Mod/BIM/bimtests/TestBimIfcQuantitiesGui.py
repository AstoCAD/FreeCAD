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

"""GUI tests for the BIM_IfcQuantities command."""

import FreeCAD as App
import FreeCADGui as Gui
import Arch
from PySide import QtCore
from bimcommands.BimIfcQuantities import BIM_IfcQuantities, QPROPS
from bimtests import TestArchBaseGui


class TestBimIfcQuantitiesGui(TestArchBaseGui.TestArchBaseGui):

    def _close(self, cmd):
        # Destroy the dialog before the command instance (which owns its
        # models and delegate) goes away
        form = getattr(cmd, "form", None)
        if form is not None:
            cmd.reject()
        else:
            form = self._form
        form.deleteLater()
        self.pump_gui_events()
        Gui.Selection.clearSelection()

    def test_only_checked_quantities_are_exported(self):
        """Only the quantities checked in the dialog are flagged for export.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/21361
        """
        self.printTestMessage("BIM_IfcQuantities saves only checked quantities...")
        wall = Arch.makeWall(length=1000, width=200, height=3000)
        self.document.recompute()
        cmd = BIM_IfcQuantities()
        cmd.Activated()
        self._form = cmd.form
        try:
            row = cmd.get_row(wall.Name)
            self.assertGreater(row, -1)
            length_col = QPROPS.index("Length") + 1
            item = cmd.qmodel.item(row, length_col)
            self.assertTrue(item.isCheckable())
            item.setCheckState(QtCore.Qt.Checked)
            cmd.accept()
        finally:
            self._close(cmd)
        data = wall.IfcData
        self.assertEqual(data.get("ExportLength"), "True")
        for prop in QPROPS:
            if prop != "Length":
                self.assertNotEqual(
                    data.get("Export" + prop), "True", f"{prop} is exported but was not checked"
                )
