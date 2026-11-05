# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test for restoring camera settings with deeply nested nodes."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestCameraSettingsNestingGui(unittest.TestCase):
    """Issue #34079: camera settings are parsed by Coin, which recurses for
    every nested node. A project file with deeply nested camera settings
    crashed FreeCAD instead of reporting invalid settings."""

    def setUp(self):
        self.doc = App.newDocument("CameraSettingsNesting")
        self.view = Gui.getDocument(self.doc.Name).activeView()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def testDeeplyNestedSettingsAreRejected(self):
        depth = 200000
        settings = "#Inventor V2.1 ascii\n" + "Separator {\n" * depth + "}\n" * depth
        with self.assertRaises(RuntimeError):
            self.view.setCamera(settings)

    def testCameraSettingsStillApply(self):
        settings = self.view.getCamera()
        orientation = self.view.getCameraOrientation()
        self.assertIn("{", settings)
        self.view.setCamera(settings)
        self.assertTrue(self.view.getCameraOrientation().isSame(orientation, 1e-7))
