# SPDX-License-Identifier: LGPL-2.1-or-later
"""Import CSG import() of a mesh file.

The importer reads each mesh file once per import into a Mesh::Feature and
reuses it when the same file is imported again. It must never take an
unrelated object of the document that happens to have the file's name.
"""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import Mesh
import importCSG


class TestCsgImportMeshFile(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-mesh-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _box_file(self, name, size):
        path = Path(self.temp.name) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Mesh.createBox(size, size, size).write(str(path))

    def _csg(self, *files, before=""):
        path = Path(self.temp.name) / "MeshFile.csg"
        path.write_text(
            before + "".join('import(file = "%s", layer = "");\n' % name for name in files),
            encoding="utf-8",
        )
        return str(path)

    def _solid_volumes(self, doc):
        return sorted(
            round(obj.Shape.Volume, 6)
            for obj in doc.Objects
            if obj.TypeId == "Part::Feature" and obj.Name.startswith("Mesh")
        )

    def _meshes(self, doc):
        return [obj for obj in doc.Objects if obj.TypeId == "Mesh::Feature"]

    def test_object_of_the_csg_with_the_name_of_the_file(self):
        self._box_file("cube.stl", 10)
        doc = importCSG.open(
            self._csg("cube.stl", before="cube(size = [1, 1, 1], center = false);\n")
        )
        self.assertEqual(self._solid_volumes(doc), [1000.0])
        self.assertEqual(doc.cube.TypeId, "Part::Box")
        self.assertEqual(len(self._meshes(doc)), 1)

    def test_unrelated_object_of_the_document_with_the_name_of_the_file(self):
        self._box_file("box.stl", 10)
        doc = App.newDocument("MeshFileTarget")
        other = doc.addObject("Mesh::Feature", "box")
        other.Mesh = Mesh.createBox(1, 1, 1)
        importCSG.insert(self._csg("box.stl"), doc.Name)
        self.assertEqual(self._solid_volumes(doc), [1000.0])
        self.assertAlmostEqual(other.Mesh.Volume, 1.0, places=6)
        self.assertEqual(len(self._meshes(doc)), 2)

    def test_files_with_the_same_name_in_other_folders(self):
        self._box_file("a/box.stl", 10)
        self._box_file("b/box.stl", 2)
        doc = importCSG.open(self._csg("a/box.stl", "b/box.stl"))
        self.assertEqual(self._solid_volumes(doc), [8.0, 1000.0])
        self.assertEqual(len(self._meshes(doc)), 2)

    def test_file_name_that_is_not_a_valid_object_name(self):
        self._box_file("my-box.stl", 10)
        doc = importCSG.open(self._csg("my-box.stl"))
        self.assertIsNone(doc.getObject("FailedMeshImport"))
        self.assertEqual(self._solid_volumes(doc), [1000.0])
        self.assertEqual(len(self._meshes(doc)), 1)

    def test_insert_into_a_document_that_is_not_active(self):
        self._box_file("box.stl", 10)
        doc = App.newDocument("MeshFileTarget")
        active = App.newDocument("MeshFileActive")
        App.setActiveDocument(active.Name)
        importCSG.insert(self._csg("box.stl"), doc.Name)
        self.assertEqual(self._solid_volumes(doc), [1000.0])
        self.assertEqual(len(self._meshes(doc)), 1)
        self.assertEqual(active.Objects, [])

    def test_same_file_twice_is_read_once(self):
        self._box_file("box.stl", 10)
        doc = importCSG.open(self._csg("box.stl", "box.stl"))
        self.assertEqual(self._solid_volumes(doc), [1000.0, 1000.0])
        self.assertEqual(len(self._meshes(doc)), 1)


if __name__ == "__main__":
    unittest.main()
