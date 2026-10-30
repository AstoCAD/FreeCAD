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

"""GUI tests for Arch_Reference."""

import os
import tempfile

import FreeCAD
import FreeCADGui
import Arch
from bimtests import TestArchBaseGui


def _count_indices(node):
    """Returns the number of coordinate indices of all indexed shapes below node."""
    from pivy import coin

    sa = coin.SoSearchAction()
    sa.setType(coin.SoIndexedShape.getClassTypeId(), True)
    sa.setInterest(coin.SoSearchAction.ALL)
    sa.apply(node)
    paths = sa.getPaths()
    return sum(paths.get(i).getTail().coordIndex.getNum() for i in range(paths.getLength()))


class TestArchReferenceGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        # A source file with a BuildingPart that stores its OpenInventor representation,
        # as needed by the Lightweight reference mode
        src = FreeCAD.newDocument("ReferenceSource")
        try:
            box = src.addObject("Part::Box", "Box")
            self.part = Arch.makeBuildingPart([box])
            src.recompute()
            self.part.ViewObject.SaveInventor = True
            self.part_name = self.part.Name
            fd, self.source_file = tempfile.mkstemp(suffix=".FCStd")
            os.close(fd)
            src.saveAs(self.source_file)
        finally:
            FreeCAD.closeDocument(src.Name)
        FreeCAD.setActiveDocument(self.document.Name)

    def tearDown(self):
        super().tearDown()
        try:
            os.remove(self.source_file)
        except OSError:
            pass

    def test_lightweight_back_to_normal(self):
        """Switching a reference from Lightweight back to Normal must show its shape again.

        https://github.com/FreeCAD/FreeCAD/issues/26091
        """
        ref = Arch.makeReference()
        ref.File = self.source_file
        ref.Part = self.part_name
        self.document.recompute()
        FreeCADGui.updateGui()
        switch = ref.ViewObject.SwitchNode
        self.assertEqual(len(ref.Shape.Faces), 6)
        normal = [_count_indices(switch.getChild(i)) for i in range(3)]
        self.assertTrue(all(normal), "Reference not displayed in Normal mode")

        ref.ReferenceMode = "Lightweight"
        self.document.recompute()
        FreeCADGui.updateGui()
        self.assertTrue(ref.Shape.isNull())
        self.assertTrue(_count_indices(switch.getChild(1)), "Lightweight node not displayed")

        for _cycle in range(2):
            ref.ReferenceMode = "Normal"
            self.document.recompute()
            FreeCADGui.updateGui()
            self.assertEqual(len(ref.Shape.Faces), 6)
            self.assertEqual(
                [_count_indices(switch.getChild(i)) for i in range(3)],
                normal,
                "Reference not displayed again after switching back to Normal mode",
            )
            ref.ReferenceMode = "Lightweight"
            self.document.recompute()
            FreeCADGui.updateGui()
