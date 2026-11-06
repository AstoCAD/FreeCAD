# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG polygons with several paths (holes and separate areas)."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG


SQUARE_WITH_HOLE = (
    "polygon(points = [[0, 0], [10, 0], [10, 10], [0, 10], [2, 2], [8, 2], [8, 8], [2, 8]], "
    "paths = [[0, 1, 2, 3], [4, 5, 6, 7]], convexity = 1);"
)


class TestCsgPolygonPaths(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-polygon-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import(self, csg):
        path = Path(self.temp.name) / "PolygonPaths.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        doc = importCSG.open(str(path))
        self.assertIsNotNone(doc)
        doc.recompute()
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        shape = roots[0].Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        return shape

    def test_single_path(self):
        shape = self._import(
            "polygon(points = [[0, 0], [10, 0], [10, 10], [0, 10]], "
            "paths = [[0, 1, 2, 3]], convexity = 1);"
        )
        self.assertEqual(len(shape.Faces), 1)
        self.assertAlmostEqual(shape.Area, 100.0, places=6)

    def test_inner_path_is_a_hole(self):
        shape = self._import(SQUARE_WITH_HOLE)
        self.assertEqual(len(shape.Faces), 1)
        self.assertEqual(len(shape.Faces[0].Wires), 2)
        self.assertAlmostEqual(shape.Area, 100.0 - 36.0, places=6)

    def test_separate_paths_are_kept(self):
        shape = self._import(
            "polygon(points = [[0, 0], [10, 0], [10, 10], [0, 10], [20, 0], [30, 0], [30, 10]], "
            "paths = [[0, 1, 2, 3], [4, 5, 6]], convexity = 1);"
        )
        self.assertEqual(len(shape.Faces), 2)
        self.assertAlmostEqual(shape.Area, 100.0 + 50.0, places=6)

    def test_extruded_polygon_with_hole(self):
        shape = self._import(
            "linear_extrude(height = 5, center = false, convexity = 1, scale = [1, 1], "
            "$fn = 0, $fa = 12, $fs = 2) {\n" + SQUARE_WITH_HOLE + "\n}"
        )
        self.assertEqual(len(shape.Solids), 1)
        self.assertAlmostEqual(shape.Volume, 64.0 * 5.0, places=6)


if __name__ == "__main__":
    unittest.main()
