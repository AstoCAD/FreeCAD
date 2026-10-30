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

"""GUI tests for the BIM_TDView command."""

import os
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
import Draft
from bimcommands.BimTDView import BIM_TDView
from bimtests import TestArchBaseGui


class TestBimTDViewGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory(prefix="bim-tdview-")
        path = os.path.join(self.tempdir.name, "template.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'width="100mm" height="80mm" viewBox="0 0 100 80"></svg>\n'
            )
        self.pages = []
        for index in range(2):
            page = self.document.addObject("TechDraw::DrawPage", "Page%d" % index)
            template = self.document.addObject("TechDraw::DrawSVGTemplate", "Template%d" % index)
            template.Template = path
            page.Template = template
            self.pages.append(page)
        self.wire = Draft.make_wire([App.Vector(0, 0, 0), App.Vector(1000, 0, 0)])
        self.document.recompute()

    def tearDown(self):
        Gui.Selection.clearSelection()
        super().tearDown()
        self.tempdir.cleanup()

    def draftViewPages(self):
        return [
            page.Name
            for page in self.pages
            for view in page.Views
            if view.TypeId == "TechDraw::DrawViewDraft"
        ]

    def test_view_goes_to_active_page(self):
        """The view is inserted on the page shown in the active window, not on the first page.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/19469
        """
        self.printTestMessage("BIM_TDView inserts on the active page...")
        self.pages[1].ViewObject.doubleClicked()
        self.pump_gui_events()
        self.assertEqual(Gui.activeView().getPage().Name, self.pages[1].Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.wire)
        BIM_TDView().Activated()
        self.assertEqual(self.draftViewPages(), [self.pages[1].Name])

    def test_view_goes_to_selected_page(self):
        """A selected page still wins."""
        self.printTestMessage("BIM_TDView inserts on the selected page...")
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.wire)
        Gui.Selection.addSelection(self.pages[1])
        BIM_TDView().Activated()
        self.assertEqual(self.draftViewPages(), [self.pages[1].Name])
