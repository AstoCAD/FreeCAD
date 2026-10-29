# SPDX-License-Identifier: LGPL-2.1-or-later
"""Autoconstraints can be disabled by default from the preferences (#21761)."""

import FreeCAD
from PySide import QtCore, QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"


class TestAutoConstraintsPreferenceGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.params = FreeCAD.ParamGet(PARAM_PATH)
        self.hadValue = "AutoConstraints" in self.params.GetBools()
        self.oldValue = self.params.GetBool("AutoConstraints", True)
        self.doc = FreeCAD.newDocument("AutoConstraintsPreference")

    def tearDown(self):
        if self.hadValue:
            self.params.SetBool("AutoConstraints", self.oldValue)
        else:
            self.params.RemBool("AutoConstraints")
        super().tearDown()

    def testNewSketchFollowsPreference(self):
        self.params.SetBool("AutoConstraints", False)
        sketch = self.doc.addObject("Sketcher::SketchObject", "Disabled")
        self.assertFalse(sketch.ViewObject.Autoconstraints)

        self.params.SetBool("AutoConstraints", True)
        sketch = self.doc.addObject("Sketcher::SketchObject", "Enabled")
        self.assertTrue(sketch.ViewObject.Autoconstraints)

    def testPreferencePageHasCheckBox(self):
        found = {}

        def inspect():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                QtCore.QTimer.singleShot(50, inspect)
                return
            boxes = dialog.findChildren(QtWidgets.QCheckBox, "checkBoxAutoConstraints")
            found["count"] = len(boxes)
            dialog.reject()

        QtCore.QTimer.singleShot(0, inspect)
        FreeCADGui.showPreferences("Sketcher", 0)
        self.assertEqual(found.get("count"), 1)
