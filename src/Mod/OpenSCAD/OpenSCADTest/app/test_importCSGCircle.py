# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG circles: one document object per circle."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG


class TestCsgCircle(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-circle-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import(self, csg):
        path = Path(self.temp.name) / "Circle.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        doc = importCSG.open(str(path))
        self.assertIsNotNone(doc)
        doc.recompute()
        return doc

    def test_circle_creates_one_object(self):
        doc = self._import("circle($fn = 0, $fa = 12, $fs = 2, r = 5);")
        self.assertEqual(len(doc.Objects), 1)
        circle = doc.Objects[0]
        self.assertAlmostEqual(circle.Radius.Value, 5.0)
        self.assertAlmostEqual(circle.Shape.Area, 25.0 * 3.141592653589793, places=6)

    def test_moved_circle_leaves_no_copy_at_origin(self):
        doc = self._import(
            "multmatrix([[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) {\n"
            " circle($fn = 0, $fa = 12, $fs = 2, r = 5);\n}"
        )
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(roots[0].Shape.BoundBox.Center.x, 10.0, places=6)


if __name__ == "__main__":
    unittest.main()
