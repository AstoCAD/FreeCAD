# SPDX-License-Identifier: LGPL-2.1-or-later

"""Unit tests for the Draft working plane (PlaneGui), without the GUI."""

import unittest

import FreeCAD as App
import WorkingPlane
from FreeCAD import Vector


class DraftWorkingPlane(unittest.TestCase):
    """Tests for the label of a working plane set from an object."""

    def setUp(self):
        self.doc = App.newDocument(self.id().split(".")[-1])
        self.box = self.doc.addObject("App::FeaturePython", "Proxy")
        self.box.addProperty("App::PropertyPlacement", "Placement")
        self.box.Label = "MyProxy"
        self.box.Placement = App.Placement(Vector(0, 0, 0), App.Rotation(Vector(1, 0, 0), 90))
        self.other = self.doc.addObject("App::FeaturePython", "Other")
        self.other.addProperty("App::PropertyPlacement", "Placement")
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_label_dropped_when_object_deleted(self):
        """The WP is no longer named after an object once it is deleted (#18958)."""
        wp = WorkingPlane.PlaneGui()
        wp.align_to_obj_placement(self.box)
        self.assertEqual(wp.label, "MyProxy")
        axis = Vector(wp.axis)

        wp._forget_object(self.other)
        self.assertEqual(wp.label, "MyProxy")

        wp._forget_object(self.box)
        self.assertEqual(wp.label, "Custom")
        self.assertEqual(wp.icon, ":/icons/Draft_SelectPlane.svg")
        self.assertNotIn("MyProxy", wp.tip)
        self.assertTrue(wp.axis.isEqual(axis, 1e-7))
        self.assertEqual(wp._history["data_list"][-1]["label"], "Custom")

    def test_label_dropped_with_offset(self):
        """The '*' that marks an offset WP is kept."""
        wp = WorkingPlane.PlaneGui()
        wp.align_to_obj_placement(self.box, offset=5)
        self.assertEqual(wp.label, "MyProxy*")
        wp._forget_object(self.box)
        self.assertEqual(wp.label, "Custom*")

    def test_history_label_dropped(self):
        """A WP that has moved on keeps its label, its history drops the object."""
        wp = WorkingPlane.PlaneGui()
        wp.align_to_obj_placement(self.box)
        wp.set_to_top()
        top_label = wp.label
        wp._forget_object(self.box)
        self.assertEqual(wp.label, top_label)
        labels = [data["label"] for data in wp._history["data_list"]]
        self.assertNotIn("MyProxy", labels)
        self.assertIn("Custom", labels)

    def test_deleting_object_through_observer(self):
        """Deleting the object updates the registered working planes (#18958)."""
        wp = WorkingPlane.PlaneGui()
        wp.align_to_obj_placement(self.box)
        saved = getattr(App, "draft_working_planes", None)
        App.draft_working_planes = [[None], [wp]]
        try:
            WorkingPlane._forget_deleted_object(self.box)
        finally:
            if saved is None:
                del App.draft_working_planes
            else:
                App.draft_working_planes = saved
        self.assertEqual(wp.label, "Custom")
