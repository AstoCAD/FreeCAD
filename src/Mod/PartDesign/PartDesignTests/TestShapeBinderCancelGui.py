# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cancelling the task dialog of a new PartDesign ShapeBinder must not crash.

TaskDlgShapeBinder::reject() aborted the transaction, which deletes the new binder and
its view provider, and then read the document through the dead view provider.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesignGui
from PySide import QtCore


class TestShapeBinderCancelGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("ShapeBinderCancelGui")
        App.setActiveDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        self.doc.recompute()
        Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)
        self.pump()

    def tearDown(self):
        try:
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def test_cancel_new_shape_binder(self):
        Gui.Selection.clearSelection()
        before = {obj.Name for obj in self.doc.Objects}
        Gui.runCommand("PartDesign_ShapeBinder", 0)
        self.pump()
        self.assertTrue(Gui.Control.activeDialog(), "no ShapeBinder task dialog")
        added = [obj.TypeId for obj in self.doc.Objects if obj.Name not in before]
        self.assertIn("PartDesign::ShapeBinder", added)

        Gui.Control.activeTaskDialog().reject()
        self.pump()

        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual({obj.Name for obj in self.doc.Objects}, before)
        self.assertEqual(self.body.Tip, self.box)
