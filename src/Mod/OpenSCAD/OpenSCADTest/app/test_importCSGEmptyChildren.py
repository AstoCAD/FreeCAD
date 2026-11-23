# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG operations whose children are all empty (e.g. empty groups)."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG

CUBE = "cube(size = [1, 1, 1], center = false);"


class TestCsgEmptyChildren(unittest.TestCase):
    """An operation on nothing gives nothing: the rest of the file is still
    imported. These used to abort the import (TypeError, IndexError,
    AttributeError)."""

    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-empty-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import_beside_cube(self, operation):
        path = Path(self.temp.name) / "Empty.csg"
        path.write_text("union() {\n%s\n%s\n}\n" % (CUBE, operation), encoding="utf-8")
        doc = importCSG.open(str(path))
        doc.recompute()
        roots = [o for o in doc.RootObjects if hasattr(o, "Shape")]
        self.assertEqual(len(roots), 1)
        self.assertAlmostEqual(roots[0].Shape.Volume, 1.0, places=6)

    def test_difference(self):
        self._import_beside_cube("difference() { group(); }")

    def test_rotate_extrude(self):
        self._import_beside_cube(
            "rotate_extrude(angle = 360, convexity = 2, $fn = 0, $fa = 12, $fs = 2) { group(); }")

    def test_offset(self):
        self._import_beside_cube("offset(r = 1, $fn = 0, $fa = 12, $fs = 2) { group(); }")

    def test_projection(self):
        self._import_beside_cube("projection(cut = true, convexity = 0) { group(); }")


if __name__ == "__main__":
    unittest.main()
