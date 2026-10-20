# SPDX-License-Identifier: LGPL-2.1-or-later
"""Boolean Display selects the existing result/tool scene and preserves visibility."""

import unittest

from pivy import coin
from PartDesignTests import TestBooleanBoundingBoxGui as _bounds


class TestBooleanDisplayGui(unittest.TestCase):
    setUp = _bounds.TestBooleanBoundingBoxGui.setUp
    tearDown = _bounds.TestBooleanBoundingBoxGui.tearDown
    pump = _bounds.TestBooleanBoundingBoxGui.pump
    createBoolean = _bounds.TestBooleanBoundingBoxGui.createBoolean
    sceneBounds = _bounds.TestBooleanBoundingBoxGui.sceneBounds
    coordinates = staticmethod(_bounds.TestBooleanBoundingBoxGui.coordinates)
    assertSameBounds = _bounds.TestBooleanBoundingBoxGui.assertSameBounds

    def toolsMaskIndex(self, view_object):
        preview_type = coin.SoType.fromName("SoPreviewShape")
        self.assertEqual(str(preview_type.getName()), "SoPreviewShape")
        candidates = []
        for index in range(view_object.SwitchNode.getNumChildren()):
            search = coin.SoSearchAction()
            search.setType(preview_type)
            search.setInterest(coin.SoSearchAction.ALL)
            search.setSearchingAll(True)
            search.apply(view_object.SwitchNode.getChild(index))
            if search.getPaths().getLength():
                candidates.append(index)
        self.assertEqual(len(candidates), 1)
        return candidates[0]

    def selectMask(self, view_object, index):
        view_object.DefaultMode = index
        view_object.hide()
        view_object.show()
        self.pump()
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), index)

    def configureResultStyle(self, boolean, style):
        self.body.ViewObject.DisplayMode = style
        boolean.ViewObject.DisplayMode = style
        boolean.ViewObject.Display = "Result"
        self.pump()
        self.assertEqual(self.body.ViewObject.DisplayMode, style)
        self.assertEqual(boolean.ViewObject.DisplayMode, style)
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
        return boolean.ViewObject.SwitchNode.whichChild.getValue()

    def checkPropertyTools(self, style):
        boolean = self.createBoolean(False)
        view_object = boolean.ViewObject
        tools_index = self.toolsMaskIndex(view_object)
        result_index = self.configureResultStyle(boolean, style)
        self.assertNotEqual(result_index, tools_index)
        old_volume = boolean.Shape.Volume
        view_object.Display = "Tools"
        self.pump()
        self.assertEqual(view_object.Display, "Tools")
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), tools_index,
                         "Display=Tools must select the existing custom preview mask")
        self.assertEqual(view_object.DefaultMode, tools_index)
        self.assertFalse(self.tool.ViewObject.Visibility)
        self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
        self.assertSameBounds(view_object.getBoundingBox(view=self.view), self.tool.Shape.BoundBox)
        self.assertAlmostEqual(boolean.Shape.Volume, old_volume)
        view_object.Display = "Result"
        self.pump()
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), result_index)
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)

    def testFlatLinesResultToToolsProperty(self):
        self.checkPropertyTools("Flat Lines")

    def testWireframeResultToToolsProperty(self):
        self.checkPropertyTools("Wireframe")

    def testResultRestoresConfiguredStylesControl(self):
        boolean = self.createBoolean(False)
        view_object = boolean.ViewObject
        tools_index = self.toolsMaskIndex(view_object)
        for style in ("Flat Lines", "Wireframe"):
            with self.subTest(style=style):
                result_index = self.configureResultStyle(boolean, style)
                view_object.Display = "Tools"
                self.selectMask(view_object, tools_index)
                self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
                view_object.Display = "Result"
                self.pump()
                self.assertEqual(view_object.SwitchNode.whichChild.getValue(), result_index)
                self.assertEqual(view_object.DefaultMode, result_index)
                self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
                self.assertFalse(self.tool.ViewObject.Visibility)

    def testGroupDisplayModeControl(self):
        boolean = self.createBoolean(True)
        boolean.ViewObject.DisplayMode = "Group"
        self.pump()
        self.assertEqual(boolean.ViewObject.DisplayMode, "Group")
        self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
        self.assertSameBounds(boolean.ViewObject.getBoundingBox(view=self.view),
                              self.tool.Shape.BoundBox)

    def testActiveBodyExposureRestoresResultModeControl(self):
        boolean = self.createBoolean(False)
        result_index = boolean.ViewObject.SwitchNode.whichChild.getValue()
        tool_mode = self.tool.ViewObject.DefaultMode
        old_volume = boolean.Shape.Volume
        try:
            self.view.setActiveObject("pdbody", self.tool)
            self.pump()
            self.assertTrue(self.tool.ViewObject.isVisible())
            self.assertEqual(boolean.ViewObject.SwitchNode.whichChild.getValue(), result_index)
            self.assertAlmostEqual(boolean.Shape.Volume, old_volume)
        finally:
            self.view.setActiveObject("pdbody", None)
            self.pump()
        self.assertFalse(self.tool.ViewObject.isVisible())
        self.assertEqual(self.tool.ViewObject.DefaultMode, tool_mode)
        self.assertEqual(boolean.ViewObject.SwitchNode.whichChild.getValue(), result_index)
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
        self.assertSameBounds(boolean.ViewObject.getBoundingBox(view=self.view),
                              boolean.Shape.BoundBox)

    def testHiddenBooleanStaysHiddenControl(self):
        boolean = self.createBoolean(False)
        boolean.ViewObject.hide()
        self.pump()
        self.assertFalse(boolean.ViewObject.Visibility)
        self.assertFalse(boolean.ViewObject.isVisible())
        self.assertEqual(boolean.ViewObject.SwitchNode.whichChild.getValue(), -1)
        old_volume = boolean.Shape.Volume
        boolean.ViewObject.Display = "Tools"
        self.pump()
        self.assertEqual(boolean.ViewObject.Display, "Tools")
        self.assertFalse(boolean.ViewObject.Visibility)
        self.assertFalse(boolean.ViewObject.isVisible())
        self.assertEqual(boolean.ViewObject.SwitchNode.whichChild.getValue(), -1)
        self.assertAlmostEqual(boolean.Shape.Volume, old_volume)

    def testHiddenToolsToResultStaysHidden(self):
        boolean = self.createBoolean(False)
        view_object = boolean.ViewObject
        result_index = self.configureResultStyle(boolean, "Flat Lines")
        tools_index = self.toolsMaskIndex(view_object)
        view_object.Display = "Tools"
        # Establish the existing real Tools scene independently of the bug.
        self.selectMask(view_object, tools_index)
        self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
        view_object.hide()
        self.pump()
        self.assertFalse(view_object.Visibility)
        self.assertFalse(view_object.isVisible())
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), -1)
        view_object.Display = "Result"
        self.pump()
        self.assertEqual(view_object.Display, "Result")
        self.assertFalse(view_object.Visibility)
        self.assertFalse(view_object.isVisible(), "Changing Display must not unhide the scene")
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), -1)
        self.assertEqual(view_object.DefaultMode, result_index)
        view_object.show()
        self.pump()
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)


    def testToolsTransitionDuringActiveBodyExposure(self):
        boolean = self.createBoolean(False)
        view_object = boolean.ViewObject
        result_index = self.configureResultStyle(boolean, "Flat Lines")
        tools_index = self.toolsMaskIndex(view_object)
        tool_mode = self.tool.ViewObject.DefaultMode
        old_volume = boolean.Shape.Volume
        self.assertFalse(self.tool.ViewObject.Visibility)
        try:
            self.view.setActiveObject("pdbody", self.tool)
            self.pump()
            self.assertTrue(self.tool.ViewObject.isVisible())
            view_object.Display = "Tools"
            self.pump()
            self.assertTrue(self.tool.ViewObject.isVisible())
            self.assertFalse(self.tool.ViewObject.Visibility)
            self.assertEqual(view_object.SwitchNode.whichChild.getValue(), tools_index)
            self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
            self.assertAlmostEqual(boolean.Shape.Volume, old_volume)
        finally:
            self.view.setActiveObject("pdbody", None)
            self.pump()
        self.assertFalse(self.tool.ViewObject.isVisible())
        self.assertFalse(self.tool.ViewObject.Visibility)
        self.assertEqual(self.tool.ViewObject.DefaultMode, tool_mode)
        self.assertEqual(view_object.DefaultMode, tools_index)
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), tools_index)
        self.assertSameBounds(self.sceneBounds(boolean), self.tool.Shape.BoundBox)
        view_object.Display = "Result"
        self.pump()
        self.assertEqual(view_object.SwitchNode.whichChild.getValue(), result_index)
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
