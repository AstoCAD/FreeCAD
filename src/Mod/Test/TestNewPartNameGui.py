# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test for the name typed in the Std_NewPart task panel.

The name was pasted unescaped into the Python commands that create the part, so a
name with an apostrophe raised a SyntaxError and no part was created.

To run: FreeCAD -t TestNewPartNameGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets

PREFS = "User parameter:BaseApp/Preferences/Commands"
ENTRIES = ("NewObjectAddInNewFile", "NewObjectCreateBody", "NewObjectSaveFile")


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestNewPartNameGui(unittest.TestCase):
    def setUp(self):
        Gui.Control.closeDialog()
        self.group = App.ParamGet(PREFS)
        existing = self.group.GetBools()
        self.saved = {e: self.group.GetBool(e) for e in ENTRIES if e in existing}
        # Create the part in the current, empty document, without a body or a save prompt
        for entry in ENTRIES:
            self.group.SetBool(entry, False)
        self.doc = App.newDocument("TestNewPartName")
        App.setActiveDocument(self.doc.Name)
        Gui.ActiveDocument = Gui.getDocument(self.doc.Name)

    def tearDown(self):
        Gui.Control.closeDialog()
        for entry in ENTRIES:
            if entry in self.saved:
                self.group.SetBool(entry, self.saved[entry])
            else:
                self.group.RemBool(entry)
        App.closeDocument(self.doc.Name)

    def createPart(self, name):
        Gui.runCommand("Std_NewPart")
        Gui.updateGui()
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        edits = Gui.getMainWindow().findChildren(QtWidgets.QLineEdit, "nameLine")
        self.assertTrue(edits)
        edits[-1].setText(name)
        dialog.accept()
        Gui.updateGui()
        return [o for o in self.doc.Objects if o.isDerivedFrom("App::Part")]

    def testPlainName(self):
        parts = self.createPart("Gearbox")
        self.assertEqual([p.Label for p in parts], ["Gearbox"])

    def testNameWithApostropheAndQuotes(self):
        name = "Bob's \"best\" part"
        parts = self.createPart(name)
        self.assertEqual([p.Label for p in parts], [name])
