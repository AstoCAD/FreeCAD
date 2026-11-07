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

    def test_fractional_fn_like_cylinder(self):
        """$fn is a number, not always an integer: it used to abort the import (ValueError).
        The importer rounds it, as it does for cylinder() and rotate_extrude()."""
        doc = self._import("circle($fn = 5.6, $fa = 12, $fs = 2, r = 5);")
        self.assertEqual(len(doc.Objects), 1)
        shape = doc.Objects[0].Shape
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Edges), 6)

    def test_fn_below_three_gives_a_circle(self):
        """No polygon has fewer than 3 sides: $fn = 1 or 2 give a circle, as for cylinder()."""
        for fn in (1, 2):
            with self.subTest(fn=fn):
                doc = self._import("circle($fn = %d, $fa = 12, $fs = 2, r = 5);" % fn)
                self.assertEqual(len(doc.Objects), 1)
                shape = doc.Objects[0].Shape
                self.assertFalse(shape.isNull())
                self.assertAlmostEqual(shape.Area, 25.0 * 3.141592653589793, places=6)
                App.closeDocument(doc.Name)

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
