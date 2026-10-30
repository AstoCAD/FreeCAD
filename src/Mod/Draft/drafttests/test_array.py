# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2023 Werner Mayer <wmayer[at]users.sourceforge.net>     *
# *   Copyright (c) 2025 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft Workbench, array tests."""

## @package test_array
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, array tests.

## \addtogroup drafttests
# @{

import Draft
from FreeCAD import Vector
from drafttests import test_base


class DraftArray(test_base.DraftTestCaseDoc):
    """Test Draft array functions."""

    def test_link_array(self):
        """Create a link array."""
        box = self.doc.addObject("Part::Box", "Box")
        box.Label = "Box"
        self.doc.recompute()

        array = Draft.make_ortho_array(
            box,
            v_x=Vector(100.0, 0.0, 0.0),
            v_y=Vector(0.0, 100.0, 0.0),
            v_z=Vector(0.0, 0.0, 100.0),
            n_x=12,
            n_y=1,
            n_z=1,
            use_link=True,
        )

        Draft.autogroup(array)
        array.ExpandArray = True
        array.Fuse = False
        self.doc.recompute(None, True, True)

        array.NumberX = 6
        self.doc.recompute(None, True, True)
        self.assertEqual(array.Count, array.NumberX)

        array.NumberX = 24
        self.doc.recompute(None, True, True)
        self.assertEqual(array.Count, array.NumberX)

        self.doc.recompute(None, True, True)
        self.assertEqual(array.Count, array.NumberX)

    def test_link_array_self_base(self):
        """A link array must not accept itself as Base.

        Linking to itself used to overflow the stack on the next recompute.
        """
        box = self.doc.addObject("Part::Box", "Box")
        wire = Draft.make_wire([Vector(0, 0, 0), Vector(10, 0, 0), Vector(20, 5, 0)])
        point = Draft.make_point(0, 0, 0)
        self.doc.recompute()
        arrays = [
            Draft.make_ortho_array(box, Vector(10, 0, 0), Vector(0, 10, 0), Vector(0, 0, 10), 2, 1, 1),
            Draft.make_path_array(box, wire, 3),
            Draft.make_point_array(box, point),
        ]
        self.doc.recompute()
        for array in arrays:
            array.Base = array
            self.assertIsNone(array.Base, array.Name)
        self.doc.addObject("Part::Box", "Box001")
        self.doc.recompute()
        self.doc.Box001.touch()
        self.doc.recompute()
        for array in arrays:
            array.Base = box
        self.doc.recompute()
        for array in arrays:
            self.assertEqual(array.Base, box, array.Name)
            self.assertFalse(array.Shape.isNull(), array.Name)


## @}
