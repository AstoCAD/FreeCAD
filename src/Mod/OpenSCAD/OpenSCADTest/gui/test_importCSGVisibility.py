# SPDX-License-Identifier: LGPL-2.1-or-later
"""Visibility of objects created by the CSG importer."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG


class TestImportCSGVisibility(unittest.TestCase):
    """Issue #13069: a non-uniformly scaled object must not be shown twice."""

    def setUp(self):
        self.before = set(App.listDocuments())
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-visibility-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        self.temp.cleanup()

    def _import(self, csg):
        path = Path(self.temp.name) / "Visibility.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        return importCSG.open(str(path))

    def _visible_shapes(self, doc):
        return [
            obj for obj in doc.Objects
            if hasattr(obj, "Shape") and obj.ViewObject.Visibility
        ]

    def test_scaled_sphere_shown_once(self):
        doc = self._import(
            "multmatrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 29], [0, 0, 0, 1]]) {"
            "multmatrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0.5, 0], [0, 0, 0, 1]]) {"
            "sphere($fn = 0, $fa = 12, $fs = 2, r = 15);}}"
        )
        visible = self._visible_shapes(doc)
        self.assertEqual([obj.TypeId for obj in visible], ["Part::Feature"])
        sphere = [obj for obj in doc.Objects if obj.TypeId == "Part::Sphere"]
        self.assertEqual(len(sphere), 1)
        self.assertFalse(sphere[0].ViewObject.Visibility)
        self.assertAlmostEqual(visible[0].Shape.BoundBox.ZLength, 15.0, places=3)

    def test_unscaled_sphere_control(self):
        doc = self._import(
            "multmatrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 29], [0, 0, 0, 1]]) {"
            "sphere($fn = 0, $fa = 12, $fs = 2, r = 15);}"
        )
        visible = self._visible_shapes(doc)
        self.assertEqual([obj.TypeId for obj in visible], ["Part::Sphere"])
