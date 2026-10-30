# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG cylinders with few facets and one zero radius (pyramids), issue #11900."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG


class TestCsgFrustum(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-frustum-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import_cylinder(self, r1, r2):
        path = Path(self.temp.name) / "Frustum.csg"
        path.write_text(
            "cylinder($fn = 4, $fa = 12, $fs = 2, h = 2, r1 = %g, r2 = %g, center = false);\n"
            % (r1, r2),
            encoding="utf-8",
        )
        doc = importCSG.open(str(path))
        self.assertIsNotNone(doc)
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        shape = roots[0].Shape
        self.assertFalse(shape.isNull(), "cylinder r1=%g r2=%g gave a null shape" % (r1, r2))
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        return shape

    @staticmethod
    def _square_area(circumradius):
        # a square inscribed in a circle of the given radius
        return 2.0 * circumradius**2

    def _expected_volume(self, r1, r2, h=2.0):
        a1 = self._square_area(r1)
        a2 = self._square_area(r2)
        return h / 3.0 * (a1 + a2 + (a1 * a2) ** 0.5)

    def test_pyramid_apex_on_top(self):
        shape = self._import_cylinder(2, 0)
        self.assertAlmostEqual(shape.Volume, self._expected_volume(2, 0), places=6)
        self.assertAlmostEqual(shape.BoundBox.ZMin, 0.0, places=6)
        self.assertAlmostEqual(shape.BoundBox.ZMax, 2.0, places=6)
        self.assertAlmostEqual(shape.BoundBox.XMax, 2.0, places=6)

    def test_pyramid_apex_at_bottom(self):
        shape = self._import_cylinder(0, 2)
        self.assertAlmostEqual(shape.Volume, self._expected_volume(0, 2), places=6)
        self.assertAlmostEqual(shape.BoundBox.ZMin, 0.0, places=6)
        self.assertAlmostEqual(shape.BoundBox.ZMax, 2.0, places=6)

    def test_frustum_control(self):
        shape = self._import_cylinder(2, 1)
        self.assertAlmostEqual(shape.Volume, self._expected_volume(2, 1), places=6)
