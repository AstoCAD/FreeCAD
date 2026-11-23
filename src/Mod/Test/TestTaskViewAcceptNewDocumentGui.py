# SPDX-License-Identifier: LGPL-2.1-or-later
"""A task dialog whose accept() or reject() creates documents closes normally.

TaskView::accept() and reject() kept an iterator into the list of task panels across the
dialog's accept()/reject(). Each new document that gets active adds a task panel to that
list, which can reallocate it: the iterator was then used after its memory was freed
(e.g. Std_NewPart with "add in a new file" from a document that is not empty). This
only crashes reliably with a checking allocator (debug heap, sanitizer).

To run: FreeCAD -t TestTaskViewAcceptNewDocumentGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets

# enough new task panels to make the list grow at least once
NEW_DOCUMENTS = 8


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestTaskViewAcceptNewDocumentGui(unittest.TestCase):
    def setUp(self):
        Gui.Control.closeDialog()
        self.doc = App.newDocument("TaskViewAcceptNewDocument")
        App.setActiveDocument(self.doc.Name)
        Gui.ActiveDocument = Gui.getDocument(self.doc.Name)
        self.created = []
        self.calls = []

    def tearDown(self):
        Gui.Control.closeDialog()
        for name in self.created + [self.doc.Name]:
            if name in App.listDocuments():
                App.closeDocument(name)
        Gui.updateGui()

    def showDialog(self):
        created = self.created
        calls = self.calls

        def createDocuments():
            for _ in range(NEW_DOCUMENTS):
                created.append(App.newDocument("TaskViewAcceptCreated").Name)

        class Panel:
            def __init__(self):
                self.form = QtWidgets.QWidget()

            def accept(self):
                calls.append("accept")
                createDocuments()
                return True

            def reject(self):
                calls.append("reject")
                createDocuments()
                return True

        Gui.Control.showDialog(Panel())
        Gui.updateGui()
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        return dialog

    def checkClosed(self, call):
        Gui.updateGui()
        self.assertEqual(self.calls, [call])
        self.assertEqual(len(self.created), NEW_DOCUMENTS)
        self.assertFalse(
            Gui.Control.activeDialog(Gui.getDocument(self.doc.Name)), "the dialog was not closed"
        )

    def testAcceptCreatesDocuments(self):
        self.showDialog().accept()
        self.checkClosed("accept")

    def testRejectCreatesDocuments(self):
        self.showDialog().reject()
        self.checkClosed("reject")
