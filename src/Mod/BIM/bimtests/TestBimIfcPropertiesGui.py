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

"""GUI tests for the BIM_IfcProperties command."""

import os
import shutil
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
import Arch
from bimcommands.BimIfcProperties import BIM_IfcProperties
from bimtests import TestArchBaseGui


class TestBimIfcPropertiesGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        # Use a temporary user data dir holding a CustomPsets.csv
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, "BIM"))
        with open(os.path.join(self.tmpdir, "BIM", "CustomPsets.csv"), "w") as f:
            f.write("MyCustomSet;Color;IfcLabel;Weight;IfcMassMeasure\n")
            f.write("Pset_FreeCADCustom;Note;IfcText\n")
        self.orig_userdir = App.getUserAppDataDir
        App.getUserAppDataDir = lambda: self.tmpdir

    def tearDown(self):
        App.getUserAppDataDir = self.orig_userdir
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    def _added_pset(self, cmd, name):
        """Selects the pset with the given name in the combo and returns
        the (name, property names) of the resulting tree item"""
        self.assertTrue(name in cmd.psetkeys, f"'{name}' is not in the property set list")
        idx = cmd.psetkeys.index(name) + 2
        self.assertEqual(cmd.form.comboPset.itemText(idx), name)
        cmd.addPset(idx)
        model = cmd.propmodel
        self.assertEqual(model.rowCount(), 1)
        top = model.item(0, 0)
        return top.text(), [top.child(i, 0).text() for i in range(top.rowCount())]

    def test_custom_pset_without_prefix(self):
        """A custom pset whose name does not start with Pset_ can be added.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/20352
        """
        self.printTestMessage("BIM_IfcProperties with custom psets...")
        wall = Arch.makeWall(length=1000, width=200, height=3000)
        self.document.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(wall)
        cmd = BIM_IfcProperties()
        cmd.Activated()
        try:
            # psets can only be added when objects are selected in the dialog
            cmd.form.tree.selectAll()
            self.assertTrue(cmd.form.tree.selectedIndexes())
            name, props = self._added_pset(cmd, "MyCustomSet")
            self.assertEqual(name, "MyCustomSet")
            self.assertEqual(props, ["Color", "Weight"])
            cmd.propmodel.clear()
            name, props = self._added_pset(cmd, "Pset_FreeCADCustom")
            self.assertEqual(name, "Pset_FreeCADCustom")
            self.assertEqual(props, ["Note"])
        finally:
            cmd.reject()
            Gui.Selection.clearSelection()
