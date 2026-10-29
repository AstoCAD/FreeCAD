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

"""Unit tests for the Draft Workbench, ShapeString task panel."""

## @package test_shapestring_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, ShapeString task panel.

## \addtogroup drafttests
# @{

import os
import unittest
from types import SimpleNamespace

import FreeCAD as App
import Draft
import WorkingPlane


class DraftGuiShapeString(unittest.TestCase):
    """The commands written by the Draft_ShapeString task panel must run."""

    def setUp(self):
        self.doc = App.newDocument("DraftGuiShapeString")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_create_object_commands_run(self):
        """https://github.com/FreeCAD/FreeCAD/issues/33306"""
        from drafttaskpanels import task_shapestring

        font_file = os.path.join(
            App.getResourceDir(), "Mod", "TechDraw", "Resources", "fonts", "osifont-lgpl3fe.ttf"
        )
        self.assertTrue(os.path.exists(font_file), font_file)

        commits = []
        panel = SimpleNamespace(
            text="AB",
            font_file=font_file,
            height=10.0,
            point=App.Vector(1, 2, 0),
            quote_string=task_shapestring.ShapeStringTaskPanel.quote_string,
            sourceCmd=SimpleNamespace(commit=lambda name, cmds: commits.append(cmds)),
        )
        task_shapestring.ShapeStringTaskPanelCmd.create_object(panel)
        self.assertEqual(len(commits), 1)

        namespace = {"FreeCAD": App, "Draft": Draft, "WorkingPlane": WorkingPlane}
        for line in commits[0]:
            exec(line, namespace)

        shape_string = namespace["ss"]
        self.assertEqual(shape_string.String, "AB")
        self.assertEqual(shape_string.Size.Value, 10.0)
        self.assertTrue(shape_string.Placement.Base.isEqual(App.Vector(1, 2, 0), 1e-9))
        self.assertFalse(shape_string.Shape.isNull())


## @}
