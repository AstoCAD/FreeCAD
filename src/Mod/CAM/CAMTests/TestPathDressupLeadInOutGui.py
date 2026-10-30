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
import Path.Dressup.Gui.LeadInOut as PathDressupLeadInOutGui
import Path.Main.Gui.Job as PathJobGui
import Path.Op.Profile as PathProfile


class TestDressupLeadInOutTaskPanel(unittest.TestCase):
    """Tests for the LeadInOut dressup task panel."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestDressupLeadInOutGui")
        FreeCAD.setActiveDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.job = PathJobGui.Create([box], openTaskPanel=False)
        self.profile = PathProfile.Create("Profile")
        self.doc.recompute()

    def tearDown(self):
        FreeCADGui.Control.closeDialog()
        FreeCAD.closeDocument(self.doc.Name)

    def _create(self):
        dressup = PathDressupLeadInOutGui.Create(self.profile)
        self.assertIsNotNone(dressup)
        dialog = FreeCADGui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        return dressup, dialog

    def test00_cancel_new_dressup(self):
        """Cancelling the panel of a new dressup does not create it (#6849)."""
        dressup, dialog = self._create()
        name = dressup.Name
        dialog.reject()

        self.assertIsNone(self.doc.getObject(name))
        self.assertIn(self.profile, self.job.Operations.Group)
        self.assertTrue(self.profile.ViewObject.Visibility)
        self.assertIsNone(FreeCADGui.Control.activeTaskDialog())
        self.assertIsNone(FreeCADGui.getDocument(self.doc.Name).getInEdit())

    def test01_ok_new_dressup(self):
        """Accepting the panel of a new dressup keeps it."""
        dressup, dialog = self._create()
        name = dressup.Name
        dialog.accept()

        self.assertIsNotNone(self.doc.getObject(name))
        self.assertIn(dressup, self.job.Operations.Group)
        self.assertNotIn(self.profile, self.job.Operations.Group)

    def test02_cancel_edit_keeps_dressup(self):
        """Cancelling a later edit of the dressup keeps it."""
        dressup, dialog = self._create()
        name = dressup.Name
        dialog.accept()

        dressup.ViewObject.Document.setEdit(dressup.ViewObject, 0)
        dialog = FreeCADGui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        dialog.reject()

        self.assertIsNotNone(self.doc.getObject(name))
        self.assertIn(dressup, self.job.Operations.Group)
