# SPDX-License-Identifier: LGPL-2.1-or-later
"""Python add/sub features must not crash while their preview is not attached.

Regression for https://github.com/FreeCAD/FreeCAD/issues/33161
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui


class TestPreviewColorPythonGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PreviewColorPythonGui")

    def tearDown(self):
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def testPythonAddSubFeatureGetsPreviewColor(self):
        body = self.doc.addObject("PartDesign::Body", "Body")
        # The Python view provider delays attach(), so the Operation update that
        # sets PreviewColor arrives before the preview node exists.
        additive = body.newObject("PartDesign::FeatureAdditivePython", "Additive")
        subtractive = body.newObject("PartDesign::FeatureSubtractivePython", "Subtractive")
        self.doc.recompute()

        gui_doc = Gui.getDocument(self.doc.Name)
        self.assertIsNotNone(gui_doc.getObject(additive.Name))
        self.assertIsNotNone(gui_doc.getObject(subtractive.Name))
        self.assertTrue(hasattr(subtractive.ViewObject, "PreviewColor"))
