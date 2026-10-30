# SPDX-License-Identifier: LGPL-2.1-or-later
"""The PartDesign_CompSketches drop-down keeps a single title in its tool tip.

Picking a tool from the drop-down of a group command that does not remember the last
used tool wrapped the already formatted child tool tip a second time, so the title was
shown twice. GroupCommand::setup() restores the tool tip only when the group command is
still active, which is not the case once the child opened a task dialog.
https://github.com/FreeCAD/FreeCAD/issues/29587
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesignGui
from PySide import QtCore, QtGui


class _Panel:
    def __init__(self):
        self.form = QtGui.QWidget()

    def accept(self):
        return True

    def reject(self):
        return True


class TestGroupCommandToolTipGui(unittest.TestCase):
    GROUP = "PartDesign_CompSketches"
    CHILD = "Sketcher_ValidateSketch"

    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("GroupCommandToolTipGui")
        App.setActiveDocument(self.doc.Name)
        self.pump()

    def tearDown(self):
        try:
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def group_action(self):
        action = Gui.getMainWindow().findChild(QtGui.QAction, self.GROUP)
        self.assertIsNotNone(action, "no action for " + self.GROUP)
        return action

    def child_action(self):
        child = Gui.Command.get(self.CHILD).getAction()
        self.assertTrue(child, "no action for " + self.CHILD)
        return child[0]

    def test_dropdown_pick_keeps_single_title(self):
        group = self.group_action()
        child = self.child_action()
        self.assertIn(child, Gui.Command.get(self.GROUP).getAction())
        before = group.toolTip()
        self.assertEqual(before.count("<b>"), 1, before)

        # A task dialog makes the group command inactive, as after creating a new sketch.
        Gui.Control.showDialog(_Panel())
        self.pump()
        child.setEnabled(True)
        child.trigger()
        self.pump()

        after = group.toolTip()
        self.assertEqual(after.count("<b>"), 1, after)
        self.assertEqual(after, before)
