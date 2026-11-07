# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG polyhedra written with 'faces' and with the old 'triangles' keyword."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import importCSG

POINTS = "points = [[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]]"
FACETS = "[[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]]"


class TestCsgPolyhedron(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-polyhedron-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import(self, csg):
        path = Path(self.temp.name) / "Polyhedron.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        doc = importCSG.open(str(path))
        doc.recompute()
        roots = [obj for obj in doc.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        shape = roots[0].Shape
        self.assertTrue(shape.isValid())
        self.assertEqual(len(shape.Solids), 1)
        return shape

    def test_faces(self):
        shape = self._import("polyhedron(%s, faces = %s, convexity = 1);" % (POINTS, FACETS))
        self.assertAlmostEqual(shape.Volume, 1000.0 / 6.0, places=6)

    def test_triangles(self):
        """CSG files of OpenSCAD before 2014.03 use 'triangles' instead of 'faces'."""
        shape = self._import("polyhedron(%s, triangles = %s, convexity = 1);" % (POINTS, FACETS))
        self.assertAlmostEqual(shape.Volume, 1000.0 / 6.0, places=6)


if __name__ == "__main__":
    unittest.main()
