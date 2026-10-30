# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 The FreeCAD project association AISBL
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

__title__ = "FEM App post-processing object unit tests"

import unittest

import FreeCAD
import Fem  # noqa: F401 (registers the FEM document object types)

from .support_utils import fcc_print


class TestPostGroups(unittest.TestCase):
    fcc_print("import TestPostGroups")

    def setUp(self):
        self.document = FreeCAD.newDocument(self.__class__.__name__)
        if "Fem::FemPostBranchFilter" not in self.document.supportedTypes():
            FreeCAD.closeDocument(self.document.Name)
            self.skipTest("FEM was built without VTK post-processing")

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_00print(self):
        fcc_print(
            "\n{0}\n{1} run FEM TestPostGroups tests {2}\n{0}".format(
                100 * "*", 10 * "*", 55 * "*"
            )
        )

    def test_branch_filter_with_non_filter_child(self):
        # The Group property of a branch filter can hold any object when it is set from
        # Python. Setting up the VTK pipeline used to treat every child as a post filter,
        # which crashed (access violation) as soon as a non-filter object was in the group.
        branch = self.document.addObject("Fem::FemPostBranchFilter", "Branch")
        other = self.document.addObject("App::DocumentObjectGroup", "Other")
        clip = self.document.addObject("Fem::FemPostScalarClipFilter", "Clip")

        branch.Group = [other]
        self.document.recompute()
        self.assertEqual(branch.Group, [other])

        branch.Group = [other, clip]
        branch.Mode = "Parallel"
        branch.Mode = "Serial"
        self.document.recompute()
        self.assertIn(clip, branch.Group)
        self.assertIn(other, branch.Group)
