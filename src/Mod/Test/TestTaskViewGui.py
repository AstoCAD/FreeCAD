# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regression coverage for document-specific task panels after sketch close.

TaskDialog.accept/reject click the actual standard task-panel buttons.  Compare
the displayed Qt panel separately from the document-specific Control lookup:
the latter can remain correct while another document's panel is displayed.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui


class PythonTaskPanel:
    """A generic panel without an object or a TaskDialog document name."""

    def __init__(self):
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Generic task panel")
        self.accepts = 0
        self.rejects = 0

    def getStandardButtons(self):
        return QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel

    def accept(self):
        self.accepts += 1
        return True

    def reject(self):
        self.rejects += 1
        return True


class TestTaskViewGui(unittest.TestCase):
    def setUp(self):
        Gui.Selection.clearSelection()
        self.documents = []

    def pump(self):
        Gui.updateGui()
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(120, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def tearDown(self):
        Gui.Selection.clearSelection()
        for doc in reversed(self.documents):
            if doc.Name not in App.listDocuments():
                continue
            gui_doc = Gui.getDocument(doc.Name)
            if gui_doc.getInEdit():
                gui_doc.resetEdit()
            if Gui.Control.activeDialog(gui_doc):
                Gui.Control.closeDialog(gui_doc)
            App.closeDocument(doc.Name)
            self.pump()

    def activate(self, doc):
        App.setActiveDocument(doc.Name)
        self.pump()
        self.assertEqual(App.ActiveDocument.Name, doc.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, doc.Name)

    def dialog(self, doc):
        return Gui.Control.activeTaskDialog(Gui.getDocument(doc.Name))

    def taskPanel(self, dialog):
        self.assertIsNotNone(dialog)
        content = dialog.getDialogContent()
        self.assertTrue(content)
        widget = content[0]
        while widget is not None:
            parent = widget.parentWidget()
            if isinstance(parent, QtGui.QStackedWidget):
                return parent, widget
            widget = parent
        self.fail("Task dialog content has no QStackedWidget task-panel parent")

    def makeEditedSketch(self, name, circle):
        try:
            import Part
            import Sketcher
        except ImportError:
            self.skipTest("Part and Sketcher modules are required")
        Gui.activateWorkbench("SketcherWorkbench")
        doc = App.newDocument(name)
        self.documents.append(doc)
        doc.UndoMode = 1
        sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        doc.recompute()
        self.activate(doc)
        self.assertTrue(Gui.getDocument(doc.Name).setEdit(sketch.Name))
        self.pump()
        dialog = self.dialog(doc)
        self.assertEqual(dialog.getDocumentName(), doc.Name)
        stack, panel = self.taskPanel(dialog)
        self.assertEqual(stack.currentWidget(), panel)
        if circle:
            sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5), False)
        else:
            sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 3, 0)), False)
        self.pump()
        self.assertEqual(sketch.GeometryCount, 1)
        return doc, sketch, stack, panel

    def twoEditedSketches(self):
        first = self.makeEditedSketch("TaskPanelFirst", True)
        second = self.makeEditedSketch("TaskPanelSecond", False)
        self.assertEqual(first[2], second[2], "Both dialogs must share the same task stack")
        self.assertNotEqual(first[3], second[3])
        for doc, sketch, stack, panel in (first, second):
            self.assertIsNotNone(Gui.getDocument(doc.Name).getInEdit())
            self.assertIsNotNone(self.dialog(doc))
            self.assertEqual(sketch.GeometryCount, 1)
            self.activate(doc)
            self.assertEqual(stack.currentWidget(), panel)
        return first, second

    def checkCloseActive(self, first_opened, accept):
        first, second = self.twoEditedSketches()
        current, other = (first, second) if first_opened else (second, first)
        doc, sketch, stack, _panel = current
        other_doc, other_sketch, _other_stack, other_panel = other
        self.activate(doc)
        if accept:
            self.dialog(doc).accept()
        else:
            self.dialog(doc).reject()
        self.pump()

        self.assertEqual(App.ActiveDocument.Name, doc.Name)
        self.assertIsNone(Gui.getDocument(doc.Name).getInEdit())
        self.assertIsNone(self.dialog(doc))
        self.assertEqual(sketch.GeometryCount, 1 if accept else 0)
        self.assertIsNotNone(Gui.getDocument(other_doc.Name).getInEdit())
        self.assertIsNotNone(self.dialog(other_doc))
        self.assertEqual(other_sketch.GeometryCount, 1)
        # A task watcher may be shown here.  The other document's live dialog
        # must remain hidden until that document is activated.
        self.assertNotEqual(stack.currentWidget(), other_panel,
                            "Closing the current sketch displayed the other document's task panel")
        self.activate(other_doc)
        self.assertEqual(stack.currentWidget(), other_panel)
        self.assertEqual(other_sketch.GeometryCount, 1)

    def testCancelFirstOpenedSketch(self):
        self.checkCloseActive(first_opened=True, accept=False)

    def testCancelLastOpenedSketch(self):
        self.checkCloseActive(first_opened=False, accept=False)

    def testAcceptFirstOpenedSketch(self):
        self.checkCloseActive(first_opened=True, accept=True)

    def testAcceptLastOpenedSketch(self):
        self.checkCloseActive(first_opened=False, accept=True)

    def testClosingBackgroundSketchPreservesCurrentPanel(self):
        first, second = self.twoEditedSketches()
        first_doc, first_sketch, _first_stack, _first_panel = first
        second_doc, second_sketch, stack, second_panel = second
        self.activate(second_doc)
        self.dialog(first_doc).reject()
        self.pump()
        self.assertEqual(App.ActiveDocument.Name, second_doc.Name)
        self.assertIsNone(Gui.getDocument(first_doc.Name).getInEdit())
        self.assertIsNone(self.dialog(first_doc))
        self.assertEqual(first_sketch.GeometryCount, 0)
        self.assertIsNotNone(Gui.getDocument(second_doc.Name).getInEdit())
        self.assertIsNotNone(self.dialog(second_doc))
        self.assertEqual(second_sketch.GeometryCount, 1)
        self.assertEqual(stack.currentWidget(), second_panel)

    def makeGenericPanel(self, name):
        doc = App.newDocument(name)
        self.documents.append(doc)
        self.activate(doc)
        python_panel = PythonTaskPanel()
        # Exercise default active-document attachment. Generic task dialogs
        # need not associate themselves with an object or set a document name.
        dialog = Gui.Control.showDialog(python_panel)
        self.pump()
        self.assertEqual(dialog.getDocumentName(), "")
        self.assertIsNotNone(Gui.Control.activeTaskDialog())
        self.assertIsNotNone(self.dialog(doc))
        stack, panel = self.taskPanel(dialog)
        self.assertEqual(stack.currentWidget(), panel)
        return doc, python_panel, stack, panel

    def testClosingVisibleGenericPanelDoesNotExposeAnotherDocument(self):
        other_doc, other_python, stack, other_panel = self.makeGenericPanel("OtherGenericTask")
        current_doc, current_python, current_stack, _current_panel = self.makeGenericPanel(
            "CurrentGenericTask")
        self.assertEqual(stack, current_stack)
        self.dialog(current_doc).accept()
        self.pump()
        self.assertEqual(App.ActiveDocument.Name, current_doc.Name)
        self.assertIsNone(self.dialog(current_doc))
        self.assertEqual(current_python.accepts, 1)
        self.assertEqual(current_python.rejects, 0)
        self.assertIsNotNone(self.dialog(other_doc))
        self.assertEqual(other_python.accepts, 0)
        self.assertEqual(other_python.rejects, 0)
        self.assertNotEqual(stack.currentWidget(), other_panel)
        self.activate(other_doc)
        self.assertEqual(stack.currentWidget(), other_panel)

    def testClosingBackgroundGenericPanelPreservesCurrentPanel(self):
        background_doc, background_python, stack, _background_panel = self.makeGenericPanel(
            "BackgroundGenericTask")
        current_doc, current_python, current_stack, current_panel = self.makeGenericPanel(
            "ForegroundGenericTask")
        self.assertEqual(stack, current_stack)
        self.dialog(background_doc).reject()
        self.pump()
        self.assertEqual(App.ActiveDocument.Name, current_doc.Name)
        self.assertIsNone(self.dialog(background_doc))
        self.assertEqual(background_python.rejects, 1)
        self.assertEqual(background_python.accepts, 0)
        self.assertIsNotNone(self.dialog(current_doc))
        self.assertEqual(current_python.accepts, 0)
        self.assertEqual(current_python.rejects, 0)
        self.assertEqual(stack.currentWidget(), current_panel)

    def testClosingOnlyGenericPanelRestoresWatcher(self):
        doc, python_panel, stack, _panel = self.makeGenericPanel("OnlyGenericTask")
        Gui.Control.closeDialog()
        self.pump()
        self.assertEqual(App.ActiveDocument.Name, doc.Name)
        self.assertIsNone(self.dialog(doc))
        self.assertEqual(python_panel.accepts, 0)
        self.assertEqual(python_panel.rejects, 0)
        self.assertEqual(stack.currentIndex(), 0)
