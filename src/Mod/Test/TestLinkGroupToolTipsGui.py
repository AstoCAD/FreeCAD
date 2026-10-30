# SPDX-License-Identifier: LGPL-2.1-or-later
"""Issue #15077: the three kinds of Std_LinkMakeGroup have their own tooltips,
and LinkMode and LinkTransform have real property descriptions."""

import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the GUI")
class TestLinkGroupToolTipsGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("LinkGroupToolTips")
        self.workbench = None
        self.previous = None

    def tearDown(self):
        if self.workbench:
            if self.previous:
                Gui.activateWorkbench(self.previous)
            Gui.removeWorkbench(self.workbench)
            QtWidgets.QApplication.processEvents()
        App.closeDocument(self.doc.Name)

    def _actions(self):
        command = Gui.Command.get("Std_LinkMakeGroup")
        actions = command.getAction()
        if not actions:
            # The action is created when the command is first added to a toolbar
            token = uuid4().hex[:8]
            self.workbench = "LinkGroupTipWorkbench_" + token
            toolbar = "LinkGroupTipToolbar_" + token
            active = Gui.activeWorkbench()
            self.previous = active.name() if active else None

            def initialize(workbench):
                workbench.appendToolbar(toolbar, ["Std_LinkMakeGroup"])

            cls = type(
                self.workbench,
                (Gui.Workbench,),
                {
                    "MenuText": self.workbench,
                    "ToolTip": self.workbench,
                    "Initialize": initialize,
                    "GetClassName": lambda workbench: "Gui::PythonWorkbench",
                },
            )
            Gui.addWorkbench(cls())
            self.assertTrue(Gui.activateWorkbench(self.workbench))
            QtWidgets.QApplication.processEvents()
            actions = command.getAction()
        return actions

    def testEachGroupKindHasItsOwnToolTip(self):
        actions = self._actions()
        self.assertEqual(len(actions), 3)
        tips = [action.toolTip() for action in actions]
        for action, tip in zip(actions, tips):
            # Without a tooltip, Qt shows the action text again
            self.assertNotEqual(tip, action.text().replace("&", ""))
            self.assertGreater(len(tip), len(action.text()))
        self.assertEqual(len(set(tips)), 3)
        self.assertIn("LinkTransform", tips[2])

    def testLinkGroupPropertyDocumentation(self):
        group = self.doc.addObject("App::LinkGroup", "LinkGroup")
        mode = group.getDocumentationOfProperty("LinkMode")
        self.assertNotEqual(mode, "Link group mode")
        for value in group.getEnumerationsOfProperty("LinkMode"):
            self.assertIn(value + ":", mode)
        link = self.doc.addObject("App::Link", "Link")
        transform = link.getDocumentationOfProperty("LinkTransform")
        self.assertIn("True:", transform)
        self.assertIn("False:", transform)
