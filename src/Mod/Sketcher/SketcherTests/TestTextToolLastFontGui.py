# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Text tool remembers the last font and width/height mode (#28303)."""

import FreeCAD as App
from PySide import QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestTextToolLastFontGui(SketcherGuiTestCase):
    PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/Tools/Text"

    def setUp(self):
        super().setUp()
        self.textParams = App.ParamGet(self.PARAM_PATH)
        self.hadFont = "FontName" in self.textParams.GetStrings()
        self.oldFont = self.textParams.GetString("FontName", "")
        self.hadMode = "HeightMode" in self.textParams.GetBools()
        self.oldMode = self.textParams.GetBool("HeightMode", False)
        self.textParams.RemString("FontName")
        self.textParams.RemBool("HeightMode")

        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("TextToolLastFontTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()
        Gui.getMainWindow().show()

    def tearDown(self):
        try:
            if self.hadFont:
                self.textParams.SetString("FontName", self.oldFont)
            else:
                self.textParams.RemString("FontName")
            if self.hadMode:
                self.textParams.SetBool("HeightMode", self.oldMode)
            else:
                self.textParams.RemBool("HeightMode")
        finally:
            super().tearDown()

    def startTextTool(self):
        """Start the Text tool in a fresh edit session and return its two comboboxes."""
        guiDoc = Gui.getDocument(self.doc.Name)
        if guiDoc.getInEdit() is not None:
            guiDoc.resetEdit()
            self.flush_gui(100)
        self.assertTrue(guiDoc.setEdit(self.sketch.Name))
        self.flush_gui(200)
        Gui.runCommand("Sketcher_CreateText")
        self.flush_gui(200)

        modeCombo = self.visibleCombo("comboBox1")
        fontCombo = self.visibleCombo("comboBox2")
        if modeCombo is None or fontCombo is None:
            self.fail("Text tool widget not found")
        return modeCombo, fontCombo

    def visibleCombo(self, name):
        for combo in Gui.getMainWindow().findChildren(QtWidgets.QComboBox, name):
            try:
                if combo.isVisible():
                    return combo
            except RuntimeError:  # widget of a closed tool, not yet destroyed
                continue
        return None

    def stopTextTool(self):
        Gui.getDocument(self.doc.Name).resetEdit()
        self.flush_gui(100)

    def fontNames(self, fontCombo):
        return [fontCombo.itemText(i) for i in range(fontCombo.count())]

    def otherFont(self, fontCombo):
        others = [name for name in self.fontNames(fontCombo) if name != fontCombo.currentText()]
        if not others:
            self.skipTest("Only one font available")
        return others[-1]

    def testDefaultsWithoutSavedSettings(self):
        modeCombo, fontCombo = self.startTextTool()
        self.assertEqual(modeCombo.currentIndex(), 0)  # Width
        self.assertTrue(fontCombo.currentText())
        self.stopTextTool()
        # Merely opening the tool does not store anything.
        self.assertNotIn("FontName", self.textParams.GetStrings())
        self.assertNotIn("HeightMode", self.textParams.GetBools())

    def testSavedSettingsAreUsed(self):
        _, fontCombo = self.startTextTool()
        font = self.otherFont(fontCombo)
        self.stopTextTool()

        self.textParams.SetString("FontName", font)
        self.textParams.SetBool("HeightMode", True)
        modeCombo, fontCombo = self.startTextTool()
        self.assertEqual(fontCombo.currentText(), font)
        self.assertEqual(modeCombo.currentIndex(), 1)  # Height
        self.stopTextTool()

    def testUnknownSavedFontFallsBack(self):
        _, fontCombo = self.startTextTool()
        defaultFont = fontCombo.currentText()
        self.stopTextTool()

        self.textParams.SetString("FontName", "No Such Font For The Sketcher Test")
        _, fontCombo = self.startTextTool()
        self.assertEqual(fontCombo.currentText(), defaultFont)
        self.stopTextTool()

    def testChangesAreSaved(self):
        modeCombo, fontCombo = self.startTextTool()
        font = self.otherFont(fontCombo)
        fontCombo.setCurrentIndex(fontCombo.findText(font))
        self.flush_gui(100)
        modeCombo.setCurrentIndex(1)
        self.flush_gui(100)
        self.stopTextTool()

        self.assertEqual(self.textParams.GetString("FontName", ""), font)
        self.assertTrue(self.textParams.GetBool("HeightMode", False))

        modeCombo, fontCombo = self.startTextTool()
        self.assertEqual(fontCombo.currentText(), font)
        self.assertEqual(modeCombo.currentIndex(), 1)
        self.stopTextTool()
