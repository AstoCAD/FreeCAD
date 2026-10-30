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

"""GUI tests for the BIM_Library command."""

import os
import shutil
import tempfile
import types

import FreeCAD as App
from bimcommands.BimLibrary import BIM_Library_TaskPanel
from bimtests import TestArchBaseGui


class TestBimLibraryGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    def test_insert_fcstd_can_be_undone(self):
        """Inserting a library object must be recorded as one undoable transaction.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/31879
        """
        self.printTestMessage("BIM_Library insert and undo...")

        # a small library file
        libdoc = App.newDocument("TestBimLibraryGuiSource")
        libdoc.addObject("Part::Box", "LibBox")
        libdoc.addObject("Part::Cylinder", "LibCylinder")
        libdoc.recompute()
        path = os.path.join(self.tmpdir, "LibObject.FCStd")
        libdoc.saveAs(path)
        App.closeDocument(libdoc.Name)
        App.setActiveDocument(self.document.Name)

        self.document.UndoMode = 1
        self.document.openTransaction("line")
        self.document.addObject("Part::Box", "Existing")
        self.document.commitTransaction()
        before = [o.Name for o in self.document.Objects]

        # stand-in for the task panel, without its file browser
        panel = types.SimpleNamespace(
            mainDocName=self.document.Name,
            modelmode=1,
            dirmodel=types.SimpleNamespace(filePath=lambda index: path),
            reject=lambda: True,
        )
        BIM_Library_TaskPanel.insert(panel, index="dummy")
        self.pump_gui_events()

        inserted = [o.Name for o in self.document.Objects if o.Name not in before]
        self.assertEqual(len(inserted), 2)

        self.document.undo()
        self.assertEqual(sorted(o.Name for o in self.document.Objects), sorted(before))
