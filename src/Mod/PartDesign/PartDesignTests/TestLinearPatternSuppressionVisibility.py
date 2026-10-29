# SPDX-License-Identifier: LGPL-2.1-or-later
"""Linear Pattern exposes its supported flat suppression property.

Use an explicitly selected disposable profile. No GUI is required.
"""

import math
import os
from pathlib import Path
import tempfile
import unittest
import uuid

import FreeCAD as App


def owned_profile():
    selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
    if not selected:
        raise unittest.SkipTest("Requires an explicitly selected disposable test profile")
    import stat

    def plain_path(path):
        for component in (path, *path.parents):
            try:
                if component.is_symlink():
                    return False
                is_junction = getattr(component, "is_junction", None)
                if is_junction is not None and is_junction():
                    return False
                attributes = getattr(component.lstat(), "st_file_attributes", 0)
                if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    return False
            except FileNotFoundError:
                continue
            except OSError:
                return False
        return True

    raw = Path(selected)
    if not raw.is_absolute() or not plain_path(raw):
        raise unittest.SkipTest("Disposable profile must be an absolute directory without links")
    try:
        profile = raw.resolve(strict=True)
    except OSError:
        raise unittest.SkipTest("Disposable test profile must already exist")
    if not profile.is_dir():
        raise unittest.SkipTest("Disposable test profile must be a directory")
    configured_home = os.environ.get("FREECAD_USER_HOME")
    if not configured_home:
        raise unittest.SkipTest("FREECAD_USER_HOME must select the disposable profile")
    home = Path(configured_home)
    if not home.is_absolute() or not plain_path(home):
        raise unittest.SkipTest("FREECAD_USER_HOME must be absolute and free of links")
    try:
        matching_home = home.resolve(strict=True) == profile
    except OSError:
        matching_home = False
    if not matching_home:
        raise unittest.SkipTest("FREECAD_USER_HOME does not match the selected profile")
    parameter_file = Path(App.ConfigGet("UserParameter"))
    data_directory = Path(App.getUserAppDataDir())
    paths = (parameter_file, data_directory)
    if not all(path.is_absolute() and plain_path(path) for path in paths):
        raise unittest.SkipTest("Active profile paths must be absolute and free of links")
    if parameter_file.resolve() != profile / "user.cfg":
        raise unittest.SkipTest("Active user configuration is outside the selected profile")
    if not all(path.resolve().is_relative_to(profile) for path in paths):
        raise unittest.SkipTest("Active configuration and data must stay in the test profile")
    return profile


def shape_data(shape):
    if shape.isNull():
        return {"null": True}
    box = shape.BoundBox
    return {
        "null": False,
        "valid": bool(shape.isValid()),
        "volume": float(shape.Volume),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertices": len(shape.Vertexes),
        "bounds": (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax),
    }


def link_sub(value):
    return (value[0].Name, tuple(value[1]))


def model_data(doc, pattern):
    return {
        "objects": [(obj.Name, obj.TypeId, obj.Label) for obj in doc.Objects],
        "body_group": [obj.Name for obj in doc.Body.Group],
        "body_placement": tuple(doc.Body.Placement.toMatrix().A),
        "box_placement": tuple(doc.Box.Placement.toMatrix().A),
        "box_shape": shape_data(doc.Box.Shape),
        "pattern_placement": tuple(pattern.Placement.toMatrix().A),
        "pattern_shape": shape_data(pattern.Shape),
        "originals": [obj.Name for obj in pattern.Originals],
        "transform_mode": str(pattern.TransformMode),
        "direction": link_sub(pattern.Direction),
        "direction2": link_sub(pattern.Direction2),
        "mode": str(pattern.Mode),
        "mode2": str(pattern.Mode2),
        "occurrences": pattern.Occurrences,
        "occurrences2": pattern.Occurrences2,
        "offset": pattern.Offset.Value,
        "offset2": pattern.Offset2.Value,
        "spacings": list(pattern.Spacings),
        "spacings2": list(pattern.Spacings2),
        "suppressed_indices": list(pattern.SuppressedIndices),
        "suppressed_positions": list(pattern.SuppressedPositions),
    }


class TestLinearPatternSuppressionVisibility(unittest.TestCase):
    def setUp(self):
        self.profile = owned_profile()
        self.assertFalse(App.listDocuments(), "Requires a disposable process without documents")
        self.directory = tempfile.TemporaryDirectory(
            prefix="freecad_linear_visibility_", dir=str(self.profile)
        )
        self.addCleanup(self.directory.cleanup)
        self.owned_documents = {}
        self.addCleanup(self._close_owned_documents)
        from PartDesignTests import TestLinearPattern as linear_pattern_module

        # Contain the existing test case rather than importing another discoverable class.
        self.case = linear_pattern_module.TestLinearPattern("testSuppressionKeepsGridPosition")
        self.addCleanup(self.case.doCleanups)
        self.case.Doc = App.newDocument("LinearSuppressionVisibility" + uuid.uuid4().hex[:8])
        self._remember_document(self.case.Doc)

    def _remember_document(self, doc):
        self.assertNotIn(doc.Name, self.owned_documents)
        self.owned_documents[doc.Name] = str(doc.Uid)

    def _close_owned_document(self, name):
        if name not in App.listDocuments():
            self.owned_documents.pop(name, None)
            return
        doc = App.getDocument(name)
        self.assertEqual(str(doc.Uid), self.owned_documents[name], "Owned document identity changed")
        if doc.HasPendingTransaction:
            doc.abortTransaction()
        App.closeDocument(name)
        self.owned_documents.pop(name)

    def _close_owned_documents(self):
        for name in list(self.owned_documents):
            self._close_owned_document(name)

    def _new_pattern(self):
        pattern = self.case.makeSuppressionPattern()
        self.assertFalse(pattern.Shape.isNull())
        self.assertTrue(pattern.Shape.isValid())
        self.assertAlmostEqual(pattern.Shape.Volume, 9000)
        self.assertEqual(pattern.SuppressedIndices, [])
        self.assertEqual(pattern.SuppressedPositions, [])
        return pattern

    def _save_reopen(self):
        path = Path(self.directory.name) / "pattern.FCStd"
        self.case.Doc.saveAs(str(path))
        self.assertTrue(path.is_file(), "Normal owned document save did not produce its file")
        old_name = self.case.Doc.Name
        self.case.Doc = None
        self._close_owned_document(old_name)
        reopened = App.openDocument(str(path))
        self._remember_document(reopened)
        self.case.Doc = reopened
        self.assertEqual(Path(reopened.FileName).resolve(), path.resolve())
        pattern = reopened.getObject("LinearPattern")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.TypeId, "PartDesign::LinearPattern")
        return pattern

    def _assert_reopened_model_equal(self, actual, expected):
        shape_names = ("box_shape", "pattern_shape")
        self.assertEqual(
            {key: value for key, value in actual.items() if key not in shape_names},
            {key: value for key, value in expected.items() if key not in shape_names},
        )
        for name in shape_names:
            actual_shape, expected_shape = actual[name], expected[name]
            float_fields = ("volume", "bounds")
            self.assertEqual(
                {key: value for key, value in actual_shape.items() if key not in float_fields},
                {key: value for key, value in expected_shape.items() if key not in float_fields},
                "Saved shape topology changed: " + name,
            )
            if expected_shape["null"]:
                continue
            self.assertTrue(
                math.isclose(actual_shape["volume"], expected_shape["volume"],
                             rel_tol=1e-12, abs_tol=1e-9),
                "Saved shape volume changed: " + name,
            )
            self.assertEqual(len(actual_shape["bounds"]), len(expected_shape["bounds"]))
            for actual_bound, expected_bound in zip(actual_shape["bounds"], expected_shape["bounds"]):
                self.assertTrue(
                    math.isclose(actual_bound, expected_bound, rel_tol=1e-12, abs_tol=1e-9),
                    "Saved shape bounds changed: " + name,
                )

    def _assert_visible_without_model_change(self, pattern):
        before = model_data(self.case.Doc, pattern)
        editor_mode = pattern.getEditorMode("SuppressedIndices")
        status = pattern.getPropertyStatus("SuppressedIndices")
        self.assertEqual(model_data(self.case.Doc, pattern), before)
        self.assertNotIn("Hidden", editor_mode, "SuppressedIndices must be visible in the Data editor")
        self.assertNotIn("Hidden", status)

    def test_control_grid_position_suppression(self):
        self.case.testSuppressionKeepsGridPosition()

    def test_control_coordinate_suppression_undo_redo(self):
        self.case.testCoordinateSuppressionUndoRedo()

    def test_control_suppression_persistence(self):
        # The existing persistence control resizes a valid grid before saving;
        # retain its inactive suppression position for a later ordinary resize.
        pattern = self.case.makeSuppressionPattern()
        pattern.SuppressedIndices = [5]
        pattern.Occurrences2 = 1
        self.case.Doc.recompute()
        pattern = None
        pattern = self._save_reopen()
        pattern.Occurrences2 = 4
        pattern.Spacings2 = [-1, -1, -1]
        self.case.Doc.recompute()
        self.assertEqual(pattern.SuppressedIndices, [6])
        self.assertAlmostEqual(pattern.Shape.Volume, 11000)

    def test_new_pattern_exposes_suppressed_indices(self):
        pattern = self._new_pattern()
        self._assert_visible_without_model_change(pattern)

    def test_reopened_pattern_exposes_suppressed_indices(self):
        pattern = self._new_pattern()
        pattern.SuppressedIndices = [5]
        self.case.Doc.recompute()
        self.assertEqual(pattern.SuppressedPositions, [(1, 2)])
        self.assertAlmostEqual(pattern.Shape.Volume, 8000)
        before = model_data(self.case.Doc, pattern)
        pattern = None
        pattern = self._save_reopen()
        self._assert_reopened_model_equal(model_data(self.case.Doc, pattern), before)
        self._assert_visible_without_model_change(pattern)
