# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: the text document editor keeps non-Latin-1 font names.

The FontName view property (UTF-8, like every string property) and the
Editor/Font preference (stored as UTF-8 by the editor preference page) were
decoded as Latin-1, so a font name such as a Cyrillic or Japanese family name
reached the editor widget garbled.

To run tests:
    FreeCAD -t TestTextDocumentFontNameGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest

# Not Latin-1 encodable; QFont keeps the requested family even if it is not installed
FONT_NAME = "Шрифт ゴシック"


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestTextDocumentFontNameGui(unittest.TestCase):
    def setUp(self):
        self.param = App.ParamGet("User parameter:BaseApp/Preferences/Editor")
        had = "Font" in self.param.GetStrings()
        saved = self.param.GetString("Font") if had else None

        def restore():
            if had:
                self.param.SetString("Font", saved)
            else:
                self.param.RemString("Font")

        self.addCleanup(restore)
        self.doc = App.newDocument("TextDocumentFontName")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))

    def _editor(self, note):
        area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        before = list(area.subWindowList())
        self.assertIs(note.ViewObject.doubleClicked(), True)
        QtTest.QTest.qWait(50)
        windows = [w for w in area.subWindowList() if w not in before]
        self.assertEqual(len(windows), 1)
        editors = windows[0].widget().findChildren(QtWidgets.QPlainTextEdit)
        self.assertEqual(len(editors), 1)
        return editors[0]

    def testFontNamePropertyReachesEditor(self):
        note = self.doc.addObject("App::TextDocument", "Note")
        editor = self._editor(note)
        note.ViewObject.FontName = FONT_NAME
        QtTest.QTest.qWait(20)
        self.assertEqual(editor.font().family(), FONT_NAME)

    def testEditorFontPreferenceIsDefault(self):
        self.param.SetString("Font", FONT_NAME)
        note = self.doc.addObject("App::TextDocument", "Note")
        self.assertEqual(note.ViewObject.FontName, FONT_NAME)
        editor = self._editor(note)
        self.assertEqual(editor.font().family(), FONT_NAME)
