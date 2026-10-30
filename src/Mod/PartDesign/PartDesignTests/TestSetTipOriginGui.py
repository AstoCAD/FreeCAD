# SPDX-License-Identifier: LGPL-2.1-or-later
"""Set Tip on the Body's Origin from the tree context menu and the command (issue #25185)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesignGui
from PySide import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


def pump(count=10):
    for _ in range(count):
        QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(10)


class TestSetTipOriginGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("PartDesignTestSetTipOriginGui")
        self.doc.UndoMode = 1
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        self.doc.recompute()
        Gui.activeView().setActiveObject("pdbody", self.body)
        pump()

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def treeWidget(self):
        for widget in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            if widget.metaObject().className() == "Gui::TreeWidget":
                return widget
        self.fail("No tree widget")

    def treeItem(self, tree, label):
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            if iterator.value().text(0) == label:
                return iterator.value()
            iterator += 1
        self.fail("No tree item " + label)

    def contextMenuTexts(self, label):
        tree = self.treeWidget()
        item = self.treeItem(tree, label)
        tree.scrollToItem(item)
        pump()
        center = tree.visualItemRect(item).center()
        Gui.Selection.clearSelection()
        pump()
        QtTest.QTest.mouseClick(
            tree.viewport(), QtCore.Qt.RightButton, QtCore.Qt.NoModifier, center
        )
        pump()
        self.assertEqual([obj.Label for obj in Gui.Selection.getSelection()], [label])
        seen = []
        timer = QtCore.QTimer(Gui.getMainWindow())

        def grabMenu():
            menu = QtWidgets.QApplication.activePopupWidget()
            if menu is not None:
                seen.extend(action.text() for action in menu.actions())
                menu.close()

        timer.timeout.connect(grabMenu)
        timer.start(50)
        try:
            event = QtGui.QContextMenuEvent(
                QtGui.QContextMenuEvent.Mouse, center, tree.viewport().mapToGlobal(center)
            )
            QtWidgets.QApplication.sendEvent(tree.viewport(), event)
        finally:
            timer.stop()
            timer.deleteLater()
        return seen

    def setTipText(self):
        return QtWidgets.QApplication.translate("CmdPartDesignMoveTip", "Set Tip")

    def testContextMenuOffersSetTipOnOrigin(self):
        self.assertIn(self.setTipText(), self.contextMenuTexts(self.box.Label))
        self.assertIn(self.setTipText(), self.contextMenuTexts(self.body.Origin.Label))

    def runMoveTipOnOrigin(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.body.Name, self.body.Origin.Name + ".")
        self.assertEqual(Gui.Selection.getSelection(), [self.body.Origin])
        messages = []
        timer = QtCore.QTimer(Gui.getMainWindow())

        def rejectMessage():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                messages.append(modal.text())
                modal.reject()

        timer.timeout.connect(rejectMessage)
        timer.start(30)
        try:
            Gui.runCommand("PartDesign_MoveTip")
            pump()
        finally:
            timer.stop()
            timer.deleteLater()
        return messages

    def testCommandOnOriginClearsTip(self):
        self.assertEqual(self.body.Tip, self.box)
        self.assertEqual(self.runMoveTipOnOrigin(), [])
        self.assertIsNone(self.body.Tip)

        # The next feature goes to the start of the body
        cylinder = self.body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.doc.recompute()
        self.assertEqual(self.body.Group, [cylinder, self.box])
        self.assertEqual(self.body.Tip, cylinder)

    def testCommandOnOriginUndo(self):
        self.runMoveTipOnOrigin()
        self.assertIsNone(self.body.Tip)
        self.doc.undo()
        self.assertEqual(self.body.Tip, self.box)
        self.doc.redo()
        self.assertIsNone(self.body.Tip)

    def testCommandOnOriginWithoutTipIsNoOp(self):
        self.runMoveTipOnOrigin()
        undo_count = self.doc.UndoCount
        self.assertEqual(self.runMoveTipOnOrigin(), [])
        self.assertIsNone(self.body.Tip)
        self.assertEqual(self.doc.UndoCount, undo_count)
