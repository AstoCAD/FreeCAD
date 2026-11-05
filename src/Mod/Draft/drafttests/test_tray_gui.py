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

"""Unit tests for the Draft Workbench, Draft tray toolbar."""

## @package test_tray_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, Draft tray toolbar.

## \addtogroup drafttests
# @{

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from draftutils.translate import translate


class DraftGuiTray(unittest.TestCase):
    """The Draft tray must be disabled when no document is open.

    https://github.com/FreeCAD/FreeCAD/issues/33117
    """

    def setUp(self):
        if App.listDocuments():
            self.skipTest("other documents are open")
        if not hasattr(Gui, "draftToolBar"):
            Gui.activateWorkbench("DraftWorkbench")
        self.tray = Gui.draftToolBar.tray

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def test_tray_disabled_without_document(self):
        doc = App.newDocument("DraftGuiTray")
        Gui.updateGui()
        self.assertTrue(self.tray.isEnabled())

        App.closeDocument(doc.Name)
        Gui.updateGui()
        self.assertFalse(self.tray.isEnabled(), "Draft tray still enabled without a document")

        App.newDocument("DraftGuiTray")
        Gui.updateGui()
        self.assertTrue(self.tray.isEnabled(), "Draft tray not enabled for a new document")

    def test_tray_stays_enabled_while_a_document_is_open(self):
        App.newDocument("DraftGuiTray1")
        doc2 = App.newDocument("DraftGuiTray2")
        Gui.updateGui()

        App.closeDocument(doc2.Name)
        Gui.updateGui()
        self.assertTrue(self.tray.isEnabled())

    def test_working_plane_label_dropped_when_object_deleted(self):
        """https://github.com/FreeCAD/FreeCAD/issues/18958"""
        import WorkingPlane

        doc = App.newDocument("DraftGuiTrayWP")
        Gui.updateGui()
        obj = doc.addObject("App::FeaturePython", "Proxy")
        obj.addProperty("App::PropertyPlacement", "Placement")
        obj.Label = "MyProxy"
        doc.recompute()
        wp = WorkingPlane.get_working_plane(update=False)
        wp.align_to_obj_placement(obj)
        Gui.updateGui()
        self.assertEqual(Gui.draftToolBar.wplabel.text(), "MyProxy")

        doc.removeObject(obj.Name)
        Gui.updateGui()
        custom = translate("draft", "Custom")
        self.assertEqual(wp.label, custom)
        self.assertEqual(Gui.draftToolBar.wplabel.text(), custom)


## @}
