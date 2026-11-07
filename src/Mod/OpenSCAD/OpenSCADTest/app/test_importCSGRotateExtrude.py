# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG rotate_extrude() with a $fn small enough to give a prismatic toroid."""

from pathlib import Path
import math
import tempfile
import unittest

import FreeCAD as App
import importCSG


class TestCsgRotateExtrudePrism(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-rotext-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import(self, angle, fn=8):
        # square [5, 7] x [0, 2] swept around the Z axis
        path = Path(self.temp.name) / "RotateExtrude.csg"
        path.write_text(
            "rotate_extrude(angle = %g, convexity = 2, $fn = %d, $fa = 12, $fs = 2) {\n"
            "multmatrix([[1, 0, 0, 5], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) {\n"
            "square(size = [2, 2], center = false);\n}\n}\n" % (angle, fn),
            encoding="utf-8",
        )
        doc = importCSG.open(str(path))
        doc.recompute()
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        self.assertNotIn("Invalid", roots[0].State)
        shape = roots[0].Shape
        self.assertFalse(shape.isNull())
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        return shape

    @staticmethod
    def _segment_volume(sweep_degrees):
        # one flat-sided segment: the cross section is the trapezoid between the
        # profile and its rotated copy, swept over the height of 2
        return 0.5 * math.sin(math.radians(sweep_degrees)) * (7.0**2 - 5.0**2) * 2.0

    def test_angle_smaller_than_one_segment(self):
        """$fn = 8 gives 45 degree steps: a 30 degree sweep is still one segment (as in OpenSCAD)."""
        shape = self._import(30)
        self.assertAlmostEqual(shape.Volume, self._segment_volume(30), places=6)
        self.assertAlmostEqual(shape.BoundBox.YMax, 7.0 * math.sin(math.radians(30)), places=6)

    def test_angle_of_two_segments(self):
        shape = self._import(90)
        self.assertAlmostEqual(shape.Volume, 2 * self._segment_volume(45), places=6)


if __name__ == "__main__":
    unittest.main()
