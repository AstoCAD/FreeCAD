# SPDX-License-Identifier: LGPL-2.1-or-later
"""Status bar tips derived from rich text tool tips must be plain, single line text.

https://github.com/FreeCAD/FreeCAD/issues/9296
"""

import re
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestStatusTipGui(unittest.TestCase):
    def setUp(self):
        if "AssemblyWorkbench" not in Gui.listWorkbenches():
            self.skipTest("Assembly workbench is not available")
        previous = Gui.activeWorkbench().name()
        self.addCleanup(Gui.activateWorkbench, previous)
        # the command actions are created when the workbench is activated
        Gui.activateWorkbench("AssemblyWorkbench")

    def _tips(self, name):
        cmd = Gui.Command.get(name)
        self.assertIsNotNone(cmd)
        actions = cmd.getAction()
        self.assertTrue(actions, f"{name} has no action")
        tooltip = QtCore.QCoreApplication.translate(name, cmd.getInfo()["toolTip"])
        return tooltip, actions[0].statusTip()

    def testRichTextToolTipGivesFirstParagraph(self):
        # the tool tip of this command has two <p> paragraphs and no explicit status tip
        tooltip, tip = self._tips("Assembly_CreateJointFixed")
        first = re.match(r"\s*<p>(.*?)</p>", tooltip, re.S)
        self.assertIsNotNone(first)
        self.assertEqual(tip, " ".join(first.group(1).split()))
        self.assertNotIn("<", tip)

    def testPlainToolTipIsUnchanged(self):
        tooltip, tip = self._tips("Assembly_CreateJointRevolute")
        self.assertNotIn("<", tooltip)
        self.assertEqual(tip, tooltip)
