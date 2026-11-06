# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Rendering commands of the 3D view context menu write the View rendering preferences."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui

VIEW = "User parameter:BaseApp/Preferences/View"
INT_KEYS = ("RenderQuality", "RenderEnvironment", "RenderKeyLight")
BOOL_KEYS = ("RenderShadows", "RenderAmbientOcclusion", "RenderFxaa")


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestRenderingCommandsGui(unittest.TestCase):
    def setUp(self):
        self.grp = App.ParamGet(VIEW)
        saved = []
        for key in INT_KEYS:
            if key in self.grp.GetInts():
                saved.append((self.grp.SetInt, key, self.grp.GetInt(key)))
            else:
                saved.append((self.grp.RemInt, key, None))
        for key in BOOL_KEYS:
            if key in self.grp.GetBools():
                saved.append((self.grp.SetBool, key, self.grp.GetBool(key)))
            else:
                saved.append((self.grp.RemBool, key, None))

        def restore():
            for setter, key, value in saved:
                if value is None:
                    setter(key)
                else:
                    setter(key, value)

        self.addCleanup(restore)
        self.grp.SetInt("RenderQuality", 0)

    def testCommandsExist(self):
        for name in (
            "Std_RenderEnhanced",
            "Std_RenderShadows",
            "Std_RenderAmbientOcclusion",
            "Std_RenderFxaa",
            "Std_RenderFixedKeyLight",
            "Std_RenderEnvironment",
        ):
            cmd = Gui.Command.get(name)
            self.assertIsNotNone(cmd, name)
            self.assertTrue(cmd.getInfo()["toolTip"], name)

    def testEnhancedToggle(self):
        Gui.runCommand("Std_RenderEnhanced", 1)
        self.assertEqual(self.grp.GetInt("RenderQuality"), 1)
        Gui.runCommand("Std_RenderEnhanced", 0)
        self.assertEqual(self.grp.GetInt("RenderQuality"), 0)

    def testEnhancedOptionsNeedEnhanced(self):
        self.grp.SetBool("RenderShadows", False)
        Gui.runCommand("Std_RenderShadows", 1)  # inactive with Classic
        self.assertFalse(self.grp.GetBool("RenderShadows", False))

    def testEnhancedOptions(self):
        Gui.runCommand("Std_RenderEnhanced", 1)
        Gui.runCommand("Std_RenderShadows", 1)
        self.assertTrue(self.grp.GetBool("RenderShadows", False))
        Gui.runCommand("Std_RenderAmbientOcclusion", 1)
        self.assertTrue(self.grp.GetBool("RenderAmbientOcclusion", False))
        Gui.runCommand("Std_RenderFxaa", 0)
        self.assertFalse(self.grp.GetBool("RenderFxaa", True))
        Gui.runCommand("Std_RenderFixedKeyLight", 1)
        self.assertEqual(self.grp.GetInt("RenderKeyLight"), 1)
        Gui.runCommand("Std_RenderFixedKeyLight", 0)
        self.assertEqual(self.grp.GetInt("RenderKeyLight"), 0)
        Gui.runCommand("Std_RenderEnvironment", 2)
        self.assertEqual(self.grp.GetInt("RenderEnvironment"), 2)
        Gui.runCommand("Std_RenderEnvironment", 0)
        self.assertEqual(self.grp.GetInt("RenderEnvironment"), 0)
