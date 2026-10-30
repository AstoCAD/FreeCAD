# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
import FreeCADGui
import Path.Main.Gui.Job as PathJobGui
import Path.Tool.Controller as PathToolController


class TestPathJobTaskPanel(unittest.TestCase):
    """Tests for the Job task panel."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestPathJobGui")
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.job = PathJobGui.Create([box], openTaskPanel=False)
        self.panel = None

    def tearDown(self):
        if self.panel is not None and getattr(self.panel, "tcListenerConnected", False):
            self.panel.preCleanup()
        FreeCADGui.Control.closeDialog()
        FreeCAD.closeDocument(self.doc.Name)

    def _addToolController(self, name, number):
        tc = PathToolController.Create(name, toolNumber=number)
        self.job.Proxy.addToolController(tc)
        return tc

    def test00_tool_table_follows_external_additions(self):
        """A tool added to the job from outside the panel shows up in its table (#33773)."""
        self.panel = PathJobGui.TaskPanel(self.job.ViewObject, False)
        self.panel.setupUi(None)
        table = self.panel.form.toolControllerList
        self.assertEqual(table.rowCount(), len(self.job.Tools.Group))

        # This is what the toolbit library opened from the toolbar does.
        self._addToolController("TC: external", 7)
        self.assertEqual(len(self.job.Tools.Group), 2)
        self.assertEqual(table.rowCount(), 2)

        # Once the panel is closed it no longer listens.
        self.panel.preCleanup()
        self.assertFalse(self.panel.tcListenerConnected)
        self._addToolController("TC: after close", 8)
        self.assertEqual(table.rowCount(), 2)
