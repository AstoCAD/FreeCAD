# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG resize() of 3D and 2D objects, including the auto option."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG


CUBE = "cube(size = [10, 5, 2], center = false);"
SQUARE = "square(size = [10, 5], center = false);"


class TestCsgResize(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-resize-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _resize(self, newsize, auto, child):
        # Same syntax as the CSG output of OpenSCAD
        csg = "resize(newsize = [%s], auto = [%s], convexity = 2) {\n %s\n}\n" % (
            ",".join(str(v) for v in newsize),
            ",".join(str(v) for v in auto),
            child,
        )
        path = Path(self.temp.name) / "Resize.csg"
        path.write_text(csg, encoding="utf-8")
        doc = importCSG.open(str(path))
        self.assertIsNotNone(doc)
        doc.recompute()
        shape = doc.ActiveObject.Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        return shape

    def _assertSize(self, shape, size):
        box = shape.BoundBox
        for actual, expected in zip((box.XLength, box.YLength, box.ZLength), size):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_resize_without_auto(self):
        self._assertSize(self._resize((20, 10, 0), (0, 0, 0), CUBE), (20, 10, 2))

    def test_auto_scales_like_the_given_size(self):
        self._assertSize(self._resize((20, 0, 0), (1, 1, 1), CUBE), (20, 10, 4))

    def test_auto_keeps_the_other_given_sizes(self):
        self._assertSize(self._resize((20, 30, 0), (1, 1, 1), CUBE), (20, 30, 12))

    def test_auto_for_one_axis_only(self):
        self._assertSize(self._resize((20, 0, 0), (0, 0, 1), CUBE), (20, 5, 4))

    def test_auto_from_last_axis(self):
        self._assertSize(self._resize((0, 0, 10), (1, 1, 1), CUBE), (50, 25, 10))

    def test_resize_2d(self):
        shape = self._resize((20, 10, 0), (0, 0, 0), SQUARE)
        self._assertSize(shape, (20, 10, 0))
        self.assertAlmostEqual(shape.Area, 200.0, places=6)

    def test_resize_2d_auto(self):
        shape = self._resize((20, 0, 0), (1, 1, 0), SQUARE)
        self._assertSize(shape, (20, 10, 0))
        self.assertAlmostEqual(shape.Area, 200.0, places=6)


if __name__ == "__main__":
    unittest.main()
