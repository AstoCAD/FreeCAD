# SPDX-License-Identifier: LGPL-2.1-or-later
"""Std_NewPart and Std_NewAssembly do not replace an open task dialog.

Both commands were always active. In the "New..." group of the File toolbar a tool is
enabled by its isActive() alone, so while a task dialog was open (e.g. a sketch in edit)
"New part" opened its own task panel, which removed the open dialog without closing it.

To run: FreeCAD -t TestNewObjectTaskDialogGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestNewObjectTaskDialogGui(unittest.TestCase):
    def setUp(self):
        Gui.Control.closeDialog()
        self.doc = App.newDocument("TestNewObjectTaskDialog")
        App.setActiveDocument(self.doc.Name)
        Gui.ActiveDocument = Gui.getDocument(self.doc.Name)
        self.form = QtWidgets.QWidget()
        self.form.setObjectName("TestNewObjectTaskDialogForm")
        self.closed = []
        closed = self.closed

        class Panel:
            def __init__(self, form):
                self.form = form

            def accept(self):
                closed.append("accept")
                return True

            def reject(self):
                closed.append("reject")
                return True

        Gui.Control.showDialog(Panel(self.form))
        Gui.updateGui()

    def tearDown(self):
        Gui.Control.closeDialog()
        Gui.updateGui()
        App.closeDocument(self.doc.Name)

    def checkCommand(self, name):
        command = Gui.Command.get(name)
        self.assertIsNotNone(command)
        self.assertFalse(command.isActive(), name + " is active while a task dialog is open")

        before = self.nameEdits()
        Gui.runCommand(name)
        Gui.updateGui()
        self.assertEqual(
            self.nameEdits(), before, name + " opened its task panel over the open task dialog"
        )
        self.assertEqual(self.closed, [])
        self.assertTrue(Gui.Control.activeDialog())

    @staticmethod
    def nameEdits():
        # the name field of the New part / New assembly task panel
        return len(Gui.getMainWindow().findChildren(QtWidgets.QLineEdit, "nameLine"))

    def testNewPart(self):
        self.checkCommand("Std_NewPart")

    def testNewAssembly(self):
        self.checkCommand("Std_NewAssembly")
