# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Boolean task add/remove/accept with Unicode internal Body identifiers."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestBooleanUnicodeNamesGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("BooleanUnicodeTask")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        self.modal_messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                self.modal_messages.append(modal.text())
                modal.reject()

        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)
        self.body = self.doc.addObject("PartDesign::Body", "ResultBody")
        self.base = self.body.newObject("PartDesign::AdditiveBox", "Base")
        self.base.Length = self.base.Width = self.base.Height = 10

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                if self.doc.HasPendingTransaction:
                    self.doc.abortTransaction()
                App.closeDocument(self.doc.Name)
        finally:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def makeTool(self, name, label, retained=False):
        tool = self.doc.addObject("PartDesign::Body", name)
        self.assertEqual(tool.Name, name,
                         "The branch must preserve the requested internal Unicode identifier")
        tool.Label = label
        box = tool.newObject("PartDesign::AdditiveBox", "ToolBox")
        if retained:
            box.Length = box.Width = box.Height = 4
            box.Placement.Base = App.Vector(-2, 4, 4)
        else:
            box.Length = box.Width = box.Height = 5
            box.Placement.Base = App.Vector(8, 0, 0)
        self.doc.recompute()
        self.assertFalse(tool.Shape.isNull())
        self.assertTrue(tool.Shape.isValid())
        self.assertAlmostEqual(tool.Shape.Volume, 64 if retained else 125)
        return tool

    def makeBoolean(self, tools, volume):
        boolean = self.body.newObject("PartDesign::Boolean", "BooleanFuse")
        boolean.Type = "Fuse"
        boolean.setObjects(tools)
        self.doc.recompute()
        self.assertEqual(list(boolean.Group), tools)
        self.assertFalse(boolean.Shape.isNull())
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, volume)
        self.assertEqual(self.body.Tip, boolean)
        self.doc.openTransaction("Edit Boolean")
        self.assertTrue(self.gui_doc.setEdit(boolean.Name))
        self.pump()
        self.assertIsNotNone(Gui.Control.activeTaskDialog())
        listing = Gui.getMainWindow().findChild(QtWidgets.QListWidget, "listWidgetBodies")
        self.assertIsNotNone(listing)
        self.assertEqual(listing.count(), len(tools))
        return boolean, listing

    def clickToolButton(self, name):
        button = Gui.getMainWindow().findChild(QtWidgets.QToolButton, name)
        self.assertIsNotNone(button)
        self.assertTrue(button.isEnabled())
        button.click()
        self.pump()
        self.assertTrue(button.isChecked())

    def acceptAndCheck(self, boolean, tools, volume):
        # Accept the ordinary task before checking reference and shape results.
        Gui.Control.activeTaskDialog().accept()
        self.pump()
        self.assertIsNone(self.gui_doc.getInEdit(),
                          "An existing valid Body reference must be accepted by the task")
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))
        self.assertEqual(list(boolean.Group), tools)
        self.doc.recompute()
        self.assertNotIn("Invalid", boolean.State)
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, volume)
        self.assertEqual(self.modal_messages, [])

    def checkReopen(self, name, label):
        tool = self.makeTool(name, label)
        boolean, listing = self.makeBoolean([tool], 1075)
        self.acceptAndCheck(boolean, [tool], 1075)

    def checkAdd(self, name, label):
        retained = self.makeTool("RetainedTool", "Retained tool", retained=True)
        tool = self.makeTool(name, label)
        boolean, listing = self.makeBoolean([retained], 1032)
        self.clickToolButton("buttonBodyAdd")
        Gui.Selection.addSelection(self.doc.Name, tool.Name)
        self.pump()
        self.assertEqual(list(boolean.Group), [retained, tool],
                         "Actual Add Body selection must reach the feature before acceptance")
        self.assertEqual(listing.count(), 2)
        self.acceptAndCheck(boolean, [retained, tool], 1107)

    def checkRemove(self, name, label, context=False):
        tool = self.makeTool(name, label)
        retained = self.makeTool("RetainedTool", "Retained tool", retained=True)
        boolean, listing = self.makeBoolean([tool, retained], 1107)
        if context:
            listing.setCurrentRow(0)
            self.assertEqual(listing.currentRow(), 0)
            actions = listing.actions()
            self.assertEqual(len(actions), 1)
            actions[0].trigger()
        else:
            self.clickToolButton("buttonBodyRemove")
            Gui.Selection.addSelection(self.doc.Name, tool.Name)
        self.pump()
        self.assertEqual(list(boolean.Group), [retained],
                         "Actual Remove Body interaction must change the feature before acceptance")
        self.acceptAndCheck(boolean, [retained], 1032)

    def testReopenAcceptUnicodeName(self):
        self.checkReopen("工具本体", "Tool body")

    def testReopenAcceptAsciiControl(self):
        self.checkReopen("ToolBody", "Tool body")

    def testReopenAcceptUnicodeLabelControl(self):
        self.checkReopen("ToolBody", "工具本体")

    def testAddUnicodeNameAccept(self):
        self.checkAdd("工具本体", "Tool body")

    def testAddUnicodeLabelAcceptControl(self):
        self.checkAdd("ToolBody", "工具本体")

    def testRemoveUnicodeNameSelectionAndAccept(self):
        self.checkRemove("工具本体", "Tool body")

    def testRemoveUnicodeLabelSelectionAndAcceptControl(self):
        self.checkRemove("ToolBody", "工具本体")

    def testContextRemoveUnicodeNameControl(self):
        self.checkRemove("工具本体", "Tool body", context=True)
