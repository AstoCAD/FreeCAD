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

"""Unit tests for the Draft Workbench, tools that wait for a selection."""

## @package test_selection_tools_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, tools that wait for a selection.

## \addtogroup drafttests
# @{

import unittest
from unittest import mock

import FreeCAD as App
import FreeCADGui as Gui
from draftutils.todo import ToDo


class DraftGuiSelectionTools(unittest.TestCase):
    """Closing the 'select an object' task panel must remove the 3D view callback.

    Otherwise the next selection calls proceed() on App.activeDraftCommand,
    which is None by then (https://github.com/FreeCAD/FreeCAD/issues/33096).
    """

    def setUp(self):
        if not hasattr(Gui, "draftToolBar"):
            Gui.activateWorkbench("DraftWorkbench")
        self.doc = App.newDocument("DraftGuiSelectionTools")
        Gui.Selection.clearSelection()

    def tearDown(self):
        if App.activeDraftCommand:
            App.activeDraftCommand.finish()
        ToDo.doTasks()
        App.closeDocument(self.doc.Name)

    def _check_close_removes_callback(self, command):
        command.Activated()
        call = command.call
        self.assertIsNotNone(call, "the command does not wait for a selection")
        view = command.view
        spy = mock.Mock(wraps=view)
        command.view = spy
        try:
            # What the Close button of the task panel calls.
            command.finish()
            self.assertIsNone(App.activeDraftCommand)
            spy.removeEventCallback.assert_called_once_with("SoEvent", call)
        finally:
            if not spy.removeEventCallback.called:
                view.removeEventCallback("SoEvent", call)

    def test_downgrade_after_selection_removes_callback_once(self):
        """The callback is removed once when the selection is made afterwards."""
        import Draft
        from draftguitools import gui_downgrade

        line = Draft.make_line(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
        self.doc.recompute()
        Gui.Selection.clearSelection()
        command = gui_downgrade.Downgrade()
        command.Activated()
        call = command.call
        self.assertIsNotNone(call)
        view = command.view
        spy = mock.Mock(wraps=view)
        command.view = spy
        try:
            Gui.Selection.addSelection(line)
            # What gui_tool_utils.select_object calls once something is selected.
            command.proceed()
            self.assertIsNone(App.activeDraftCommand)
            spy.removeEventCallback.assert_called_once_with("SoEvent", call)
        finally:
            if not spy.removeEventCallback.called:
                view.removeEventCallback("SoEvent", call)

    def test_upgrade_close_removes_selection_callback(self):
        from draftguitools import gui_upgrade

        self._check_close_removes_callback(gui_upgrade.Upgrade())

    def test_downgrade_close_removes_selection_callback(self):
        from draftguitools import gui_downgrade

        self._check_close_removes_callback(gui_downgrade.Downgrade())

    def test_join_close_removes_selection_callback(self):
        from draftguitools import gui_join

        self._check_close_removes_callback(gui_join.Join())

    def test_draft2sketch_close_removes_selection_callback(self):
        from draftguitools import gui_draft2sketch

        self._check_close_removes_callback(gui_draft2sketch.Draft2Sketch())

    def test_facebinder_close_removes_selection_callback(self):
        from draftguitools import gui_facebinders

        self._check_close_removes_callback(gui_facebinders.Facebinder())


## @}
