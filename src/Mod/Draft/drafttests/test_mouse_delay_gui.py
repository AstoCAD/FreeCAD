# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2026 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This file is free software; you can redistribute it and/or modify it  *
# *   under the terms of the GNU Lesser General Public License (LGPL)       *
# *   as published by the Free Software Foundation; either version 2.1 of  *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft MouseDelay handling of GUI commands."""

from unittest import mock

import DraftGui
import FreeCAD as App
import FreeCADGui as Gui

from draftguitools import gui_dimensions
from draftguitools import gui_stretch
from drafttests import test_base


def _event(event_type, **kwargs):
    """Return a fake Coin event dictionary as passed to the action callbacks."""
    event = {
        "Type": event_type,
        "Position": (10, 10),
        "ShiftDown": False,
        "CtrlDown": False,
        "AltDown": False,
    }
    event.update(kwargs)
    return event


class DraftGuiMouseDelay(test_base.DraftTestCaseDoc):
    """While the MouseDelay blocks the mouse, commands must ignore mouse events.

    gui_tool_utils.get_point() returns None while Gui.draftToolBar.mouse is
    False (a value was just typed in the task panel). Commands that used that
    None point raised AttributeErrors (#19531).
    """

    def setUp(self):
        super().setUp()
        self.ui = Gui.draftToolBar
        patcher = mock.patch.object(self.ui, "mouse", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_dimension_ignores_mouse_while_blocked(self):
        """Draft_Dimension must not use the blocked (None) point."""
        cmd = gui_dimensions.Dimension()
        cmd.ui = self.ui
        cmd.node = [App.Vector(0, 0, 0)]
        cmd.dir = App.Vector(1, 0, 0)
        cmd.arcmode = False
        cmd.point1 = None
        cmd.point2 = None
        cmd.selectmode = False
        cmd.altdown = False
        cmd.edges = []
        cmd.dimtrack = mock.Mock()
        cmd.point = App.Vector(5, 0, 0)

        cmd.action(_event("SoLocation2Event"))
        cmd.action(_event("SoMouseButtonEvent", State="DOWN", Button="BUTTON1"))

        self.assertEqual(cmd.node, [App.Vector(0, 0, 0)])
        self.assertEqual(cmd.point, App.Vector(5, 0, 0))
        cmd.dimtrack.update.assert_not_called()

    def test_stretch_ignores_mouse_while_blocked(self):
        """Draft_Stretch must not pass the blocked (None) point to its trackers."""
        cmd = gui_stretch.Stretch()
        cmd.ui = self.ui
        cmd.node = []
        cmd.step = 2
        cmd.pos = None
        cmd.rectracker = mock.Mock()
        cmd.planetrack = None

        cmd.action(_event("SoLocation2Event"))
        cmd.action(_event("SoMouseButtonEvent", State="DOWN", Button="BUTTON1"))

        cmd.rectracker.update.assert_not_called()
        cmd.rectracker.off.assert_not_called()
        self.assertEqual(cmd.step, 2)

        cmd.step = 1
        cmd.action(_event("SoMouseButtonEvent", State="DOWN", Button="BUTTON1"))

        cmd.rectracker.setorigin.assert_not_called()
        self.assertEqual(cmd.step, 1)
