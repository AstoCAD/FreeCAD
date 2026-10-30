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

"""Unit tests for the Draft Workbench, AddToGroup and AddToLayer menus."""

## @package test_groups_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, AddToGroup and AddToLayer menus.

## \addtogroup drafttests
# @{

import unittest

import FreeCAD as App
import FreeCADGui as Gui


class DraftGuiGroups(unittest.TestCase):
    """Invalid targets are greyed out, not removed, from the popup menu.

    https://github.com/FreeCAD/FreeCAD/issues/28476
    """

    def setUp(self):
        if not hasattr(Gui, "draftToolBar"):
            Gui.activateWorkbench("DraftWorkbench")
        self.doc = App.newDocument("DraftGuiGroups")
        Gui.Selection.clearSelection()

    def tearDown(self):
        menu = getattr(Gui.draftToolBar, "groupmenu", None)
        if menu is not None:
            menu.close()
        Gui.draftToolBar.sourceCmd = None
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def _menu_state(self):
        """Return {label: enabled} for the entries of the popup menu."""
        return {
            action.text(): action.isEnabled()
            for action in Gui.draftToolBar.groupmenu.actions()
            if not action.isSeparator()
        }

    def test_add_to_group_greys_out_selected_group(self):
        from draftguitools import gui_groups

        grp = self.doc.addObject("App::DocumentObjectGroup", "Group")
        other = self.doc.addObject("App::DocumentObjectGroup", "Other")
        self.doc.recompute()
        Gui.Selection.addSelection(grp)
        gui_groups.AddToGroup().Activated()
        state = self._menu_state()
        self.assertIn(grp.Label, state, "the selected group must still be listed")
        self.assertFalse(state[grp.Label])
        self.assertTrue(state[other.Label])

    def test_add_to_group_greys_out_groups_inside_selection(self):
        from draftguitools import gui_groups

        top = self.doc.addObject("App::DocumentObjectGroup", "Top")
        part = self.doc.addObject("App::Part", "Part")
        inner = self.doc.addObject("App::DocumentObjectGroup", "Inner")
        nested = self.doc.addObject("App::DocumentObjectGroup", "Nested")
        top.addObject(part)
        part.addObject(inner)
        inner.addObject(nested)
        self.doc.recompute()
        Gui.Selection.addSelection(part)
        gui_groups.AddToGroup().Activated()
        state = self._menu_state()
        # Adding the Part to a group it contains would create a cycle.
        self.assertFalse(state[inner.Label])
        self.assertFalse(state[nested.Label])
        # Its parent group stays a valid target.
        self.assertTrue(state[top.Label])

    def test_add_to_group_plain_object_keeps_all_groups(self):
        from draftguitools import gui_groups

        top = self.doc.addObject("App::DocumentObjectGroup", "Top")
        sub = self.doc.addObject("App::DocumentObjectGroup", "Sub")
        top.addObject(sub)
        box = self.doc.addObject("Part::Box", "Box")
        sub.addObject(box)
        self.doc.recompute()
        Gui.Selection.addSelection(box)
        gui_groups.AddToGroup().Activated()
        state = self._menu_state()
        self.assertTrue(state[top.Label])
        self.assertTrue(state[sub.Label])

    def test_add_to_layer_greys_out_selected_layer(self):
        import Draft
        from draftguitools import gui_layers

        layer = Draft.make_layer("LayerA")
        other = Draft.make_layer("LayerB")
        self.doc.recompute()
        Gui.Selection.addSelection(layer)
        gui_layers.AddToLayer().Activated()
        state = self._menu_state()
        self.assertIn(layer.Label, state, "the selected layer must still be listed")
        self.assertFalse(state[layer.Label])
        self.assertTrue(state[other.Label])


## @}
