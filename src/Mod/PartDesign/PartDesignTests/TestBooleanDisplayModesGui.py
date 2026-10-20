# SPDX-License-Identifier: LGPL-2.1-or-later
"""Body display styles preserve each feature's supported display-mode options."""

import unittest

from PartDesignTests import TestBooleanBoundingBoxGui as _bounds


class TestBooleanDisplayModesGui(unittest.TestCase):
    setUp = _bounds.TestBooleanBoundingBoxGui.setUp
    tearDown = _bounds.TestBooleanBoundingBoxGui.tearDown
    pump = _bounds.TestBooleanBoundingBoxGui.pump
    createBoolean = _bounds.TestBooleanBoundingBoxGui.createBoolean

    def snapshot(self, stage, boolean):
        vp = boolean.ViewObject
        data = {
            "stage": stage,
            "body_options": self.body.ViewObject.getEnumerationsOfProperty("DisplayMode"),
            "body_mode": self.body.ViewObject.DisplayMode,
            "boolean_options": vp.getEnumerationsOfProperty("DisplayMode"),
            "virtual_options": vp.listDisplayModes(),
            "boolean_mode": vp.DisplayMode, "boolean_display": vp.Display,
            "default": vp.DefaultMode, "switch": vp.SwitchNode.whichChild.getValue(),
            "boolean_app_visible": vp.Visibility, "boolean_native_visible": vp.isVisible(),
            "base_app_visible": self.base.ViewObject.Visibility,
        }
        return data

    def testBodyStylePreservesBooleanOptions(self):
        boolean = self.createBoolean(False)
        expected = boolean.ViewObject.listDisplayModes()
        self.assertIn("Group", expected)
        self.snapshot("before-body-style", boolean)
        observations = []
        for style in ("Wireframe", "Flat Lines"):
            self.body.ViewObject.DisplayMode = style
            self.pump()
            observations.append(self.snapshot("after-body-" + style, boolean))
        for observation in observations:
            self.assertEqual(observation["boolean_options"], expected,
                             "Propagating a style must preserve the target option list")

    def testGroupAssignmentSurvivesBodyStyle(self):
        boolean = self.createBoolean(False)
        vp = boolean.ViewObject
        initial_options = vp.getEnumerationsOfProperty("DisplayMode")
        self.assertIn("Group", initial_options)
        vp.DisplayMode = "Group"
        self.assertEqual(vp.DisplayMode, "Group")
        vp.DisplayMode = "Flat Lines"
        self.body.ViewObject.DisplayMode = "Wireframe"
        self.pump()
        error = None
        try:
            vp.DisplayMode = "Group"
        except ValueError as exception:
            error = str(exception)
        self.snapshot("after-group-assignment", boolean)
        self.assertIsNone(error, "A supported Boolean Group option must remain assignable")
        self.assertEqual(vp.DisplayMode, "Group")

    def testOrdinaryFeatureStylePropagationControl(self):
        boolean = self.createBoolean(False)
        expected = self.base.ViewObject.getEnumerationsOfProperty("DisplayMode")
        for style in ("Wireframe", "Flat Lines", "Shaded", "Points"):
            self.body.ViewObject.DisplayMode = style
            self.pump()
            self.assertEqual(self.base.ViewObject.DisplayMode, style)
            self.assertEqual(self.base.ViewObject.getEnumerationsOfProperty("DisplayMode"), expected)
        self.snapshot("ordinary-feature-style-control", boolean)


    def testUnsupportedTargetModeKeepsLegacyPropagationControl(self):
        boolean = self.createBoolean(False)
        view_object = boolean.ViewObject
        # Public enum assignment models a scripted feature with a custom mode list.
        view_object.DisplayMode = ["CustomOnly"]
        self.assertEqual(view_object.getEnumerationsOfProperty("DisplayMode"), ["CustomOnly"])
        self.assertEqual(view_object.DisplayMode, "CustomOnly")
        self.body.ViewObject.DisplayMode = "Wireframe"
        self.pump()
        self.assertEqual(view_object.DisplayMode, "Wireframe")
        self.assertEqual(view_object.getEnumerationsOfProperty("DisplayMode"),
                         self.body.ViewObject.getEnumerationsOfProperty("DisplayMode"))
