# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sources of non-parametric copies made by the CSG importer stay hidden.

The importer copies the shape of some objects into a non-parametric feature
(e.g. the "Matrix Deformation" of a non-uniform scale or of a resize). The
source is then an orphaned root object, which must be remembered in
importCSG.consumed_objects, or fixVisibility() shows it again after a GUI
import. fixVisibility() needs the GUI, so these tests check what it is given:
the new root objects that are not consumed are the ones shown.
"""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import FreeCAD as App
import Mesh
import importCSG


CUBE = "cube(size = [10, 5, 2], center = false);"


class _RecordingList(list):
    """Keeps a copy of its content when processcsg() clears it."""

    def clear(self):
        self.recorded = list(self)
        super().clear()


class TestCsgConsumedSources(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-sources-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _import(self, csg):
        """Import csg, return the document, the consumed and the shown root objects."""
        path = Path(self.temp.name) / "Sources.csg"
        path.write_text(csg + "\n", encoding="utf-8")
        consumed = _RecordingList()
        with mock.patch.object(importCSG, "consumed_objects", consumed):
            doc = importCSG.open(str(path))
        consumed = [obj.Name for obj in consumed.recorded]
        shown = [obj.Name for obj in doc.RootObjects if obj.Name not in consumed]
        return doc, consumed, shown

    def test_multmatrix_scale_source(self):
        doc, consumed, shown = self._import(
            "multmatrix([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0.5, 0], [0, 0, 0, 1]]) {%s}" % CUBE
        )
        self.assertEqual(consumed, ["cube"])
        self.assertEqual(shown, ["Matrix_Deformation"])

    def test_resize_source(self):
        doc, consumed, shown = self._import(
            "resize(newsize = [20, 0, 0], auto = [0, 0, 0], convexity = 2) {%s}" % CUBE
        )
        self.assertEqual(consumed, ["cube"])
        self.assertEqual(shown, ["Matrix_Deformation"])
        self.assertAlmostEqual(doc.Matrix_Deformation.Shape.BoundBox.XLength, 20.0, places=6)

    def test_resize_several_children_source(self):
        doc, consumed, shown = self._import(
            "resize(newsize = [20, 0, 0], auto = [0, 0, 0], convexity = 2) {%s %s}"
            % (CUBE, "sphere($fn = 0, $fa = 12, $fs = 2, r = 1);")
        )
        # the union of the children is resized: it is the consumed source
        self.assertEqual(consumed, ["Resize_Union"])
        self.assertEqual(shown, ["Matrix_Deformation"])

    def test_imported_mesh_source(self):
        Mesh.createBox(10, 10, 10).write(str(Path(self.temp.name) / "box.stl"))
        doc, consumed, shown = self._import('import(file = "box.stl", layer = "");')
        # the mesh is copied into a solid, only the solid is shown
        self.assertEqual(consumed, ["box"])
        self.assertEqual(doc.box.TypeId, "Mesh::Feature")
        self.assertEqual(shown, ["Mesh"])
        self.assertAlmostEqual(doc.Mesh.Shape.Volume, 1000.0, places=6)


if __name__ == "__main__":
    unittest.main()
