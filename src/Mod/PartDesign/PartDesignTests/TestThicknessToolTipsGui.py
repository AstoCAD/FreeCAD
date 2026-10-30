# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Thickness task panel explains its Mode, Join type and Intersection controls (issue #23801)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesignGui
from PySide import QtWidgets


class TestThicknessToolTipsGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("PartDesignTestThicknessToolTipsGui")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        body = self.doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 20
        self.doc.recompute()
        self.thickness = body.newObject("PartDesign::Thickness", "Thickness")
        self.thickness.Base = (box, ["Face6"])
        self.doc.recompute()
        self.assertTrue(self.gui_doc.setEdit(self.thickness.Name))
        Gui.updateGui()

    def tearDown(self):
        try:
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            Gui.updateGui()

    def widget(self, cls, name):
        widgets = Gui.getMainWindow().findChildren(cls, name)
        self.assertEqual(len(widgets), 1, name)
        return widgets[0]

    def assertComboExplained(self, name):
        combo = self.widget(QtWidgets.QComboBox, name)
        tip = combo.toolTip()
        self.assertTrue(tip, name)
        view = combo.view()
        for row in range(combo.count()):
            if view.isRowHidden(row):
                continue
            self.assertIn(combo.itemText(row), tip)

    def testModeToolTip(self):
        self.assertComboExplained("modeComboBox")

    def testJoinToolTip(self):
        self.assertComboExplained("joinComboBox")

    def testIntersectionToolTip(self):
        check = self.widget(QtWidgets.QCheckBox, "checkIntersection")
        self.assertTrue(check.toolTip())
