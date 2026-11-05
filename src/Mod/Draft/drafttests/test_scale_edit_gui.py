# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 FreeCAD Project Association                        *
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
# *   You should have received a copy of the GNU Lesser General Public     *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft Workbench, edit scale task panel of clones."""

## @package test_scale_edit_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, edit scale task panel of clones.

## \addtogroup drafttests
# @{

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Draft
from draftutils import params


class DraftGuiScaleEdit(unittest.TestCase):
    """The edit task panel of a clone must show the Scale of the clone.

    https://github.com/FreeCAD/FreeCAD/issues/34024
    """

    def setUp(self):
        self.doc = App.newDocument("DraftGuiScaleEdit")
        self.uniform = params.get_param("ScaleUniform")
        self.panel = None

    def tearDown(self):
        if self.panel is not None and self.panel.ghost is not None:
            self.panel.ghost.finalize()
        Gui.Selection.clearSelection()
        params.set_param("ScaleUniform", self.uniform)
        App.closeDocument(self.doc.Name)

    def check_factors(self, uniform):
        from drafttaskpanels import task_scale

        params.set_param("ScaleUniform", uniform)
        rect = Draft.make_rectangle(10, 5)
        clone = Draft.make_clone(rect)
        clone.Scale = App.Vector(1.2, 1.2, 1.0)
        self.doc.recompute()
        Gui.Selection.addSelection(clone)

        self.panel = task_scale.ScaleTaskPanelEdit(clone)
        factors = (
            self.panel.xValue.value(),
            self.panel.yValue.value(),
            self.panel.zValue.value(),
        )
        self.assertAlmostEqual(factors[0], 1.2, msg=f"factors {factors}")
        self.assertAlmostEqual(factors[1], 1.2, msg=f"factors {factors}")
        self.assertAlmostEqual(factors[2], 1.0, msg=f"factors {factors}")
        self.assertFalse(self.panel.lock.isChecked())

    def test_factors_with_uniform_scaling_off(self):
        self.check_factors(False)

    def test_factors_with_uniform_scaling_on(self):
        self.check_factors(True)


## @}
