# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: the editor font preference is stored as UTF-8.

The Python editor, report view and text editors read "Editor/Font" as UTF-8,
but the preference page stored and read it as Latin-1, so a font family name
outside Latin-1 was saved as '?' characters.

To run tests:
    FreeCAD -t TestEditorFontPreferenceGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestEditorFontPreferenceGui(unittest.TestCase):
    def setUp(self):
        self.results = {}
        self.errors = []
        self.group = App.ParamGet("User parameter:BaseApp/Preferences/Editor")
        self.had = "Font" in self.group.GetStrings()
        self.old = self.group.GetString("Font")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.had:
            self.group.SetString("Font", self.old)
        else:
            self.group.RemString("Font")

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            pages = [
                widget
                for widget in dialog.findChildren(QtWidgets.QWidget)
                if widget.metaObject().className() == "Gui::Dialog::DlgSettingsEditor"
            ]
            if len(pages) != 1:
                self.errors.append("editor preference page not found")
                return
            combo = pages[0].findChild(QtWidgets.QComboBox, "fontFamily")
            self.results["loaded"] = combo.currentText()
            # what OK/Apply does
            QtCore.QMetaObject.invokeMethod(pages[0], "saveSettings")
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testFontNameKeepsNonLatin1Characters(self):
        families = [
            family
            for family in QtGui.QFontDatabase.families()
            if QtGui.QFontDatabase.isFixedPitch(family)
            and any(ord(character) > 255 for character in family)
        ]
        if not families:
            self.skipTest("No installed fixed-pitch font family name outside Latin-1")
        font = families[0]
        self.group.SetString("Font", font)
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.showPreferences("Python")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.results["loaded"], font)
        self.assertEqual(self.group.GetString("Font"), font)
