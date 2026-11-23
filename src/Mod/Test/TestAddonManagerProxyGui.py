# SPDX-License-Identifier: LGPL-2.1-or-later
"""Std_AddonManager (Tools group of the File toolbar) runs the registered Std_AddonMgr.

It used to create another AddonManager.CommandAddonManager each time, whose constructor
registers the "Addon Manager" preference page again, so the page showed up once more in
the preferences dialog after each use.
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestAddonManagerProxyGui(unittest.TestCase):
    def setUp(self):
        if Gui.Command.get("Std_AddonMgr") is None:
            self.skipTest("the Addon Manager is not installed")
        import AddonManager

        self.module = AddonManager
        self.commandClass = AddonManager.CommandAddonManager
        self.activations = []
        self.newInstances = []

        activations = self.activations
        newInstances = self.newInstances

        # The registered Std_AddonMgr object is a CommandAddonManager: record its activation
        # instead of opening the Addon Manager
        def activated(cmd):
            activations.append(cmd)

        class NewCommandAddonManager:
            def __init__(self):
                newInstances.append(self)

            def Activated(self):
                pass

        self.savedActivated = self.commandClass.__dict__["Activated"]
        self.commandClass.Activated = activated
        self.module.CommandAddonManager = NewCommandAddonManager

    def tearDown(self):
        if hasattr(self, "savedActivated"):
            self.commandClass.Activated = self.savedActivated
            self.module.CommandAddonManager = self.commandClass

    def testRunsTheRegisteredCommand(self):
        command = Gui.Command.get("Std_AddonManager")
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())

        Gui.runCommand("Std_AddonManager")

        self.assertEqual(len(self.newInstances), 0, "a new CommandAddonManager was created")
        self.assertEqual(len(self.activations), 1, "Std_AddonMgr was not run")
        self.assertIsInstance(self.activations[0], self.commandClass)
