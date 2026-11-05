# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

"""Unit tests for the non-IFC importers and exporters of the BIM workbench."""

import os
import tempfile

import FreeCAD
from bimtests import TestArchBase


class TestArchImporters(TestArchBase.TestArchBase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)
        super().tearDown()

    def _import_obj(self, text):
        from importers import importOBJ

        filename = os.path.join(self.tmpdir, "test.obj")
        with open(filename, "w", encoding="utf8") as f:
            f.write(text)
        importOBJ.insert(filename, self.document.Name)
        return [o for o in self.document.Objects if o.isDerivedFrom("Mesh::Feature")]

    def _points(self, mesh_obj):
        return sorted(tuple(round(c, 6) for c in p.Vector) for p in mesh_obj.Mesh.Points)

    def test_obj_import_negative_indices(self):
        """Negative OBJ indices are relative to the last vertex read."""
        text = "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 5 5 5\no A\nf -5 -4 -3\no B\nf -5 -3 -2\n"
        meshes = self._import_obj(text)
        self.assertEqual(len(meshes), 2)
        by_label = {m.Label: self._points(m) for m in meshes}
        self.assertEqual(by_label["A"], [(0, 0, 0), (1, 0, 0), (1, 1, 0)])
        self.assertEqual(by_label["B"], [(0, 0, 0), (0, 1, 0), (1, 1, 0)])

    def test_obj_import_vertex_colors(self):
        """Vertex lines with extra values (vertex colors) are imported."""
        text = (
            "v 0 0 0 1 0 0\nv 1 0 0 1 0 0\nv 1 1 0 1 0 0\nv 0 1 0 1 0 0\n"
            "o A\nf 1 2 3\no B\nf 1 2 3 4\n"
        )
        meshes = self._import_obj(text)
        self.assertEqual(len(meshes), 2)
        by_label = {m.Label: m for m in meshes}
        self.assertEqual(by_label["A"].Mesh.CountFacets, 1)
        self.assertEqual(by_label["B"].Mesh.CountFacets, 2)
        self.assertEqual(self._points(by_label["B"]), [(0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0)])

    def test_obj_export_app_part(self):
        """Exporting an App::Part exports its contents at their global placement."""
        from importers import importOBJ

        box = self.document.addObject("Part::Box", "Box")
        link = self.document.addObject("App::Link", "Link")
        link.LinkedObject = box
        link.Placement.Base = FreeCAD.Vector(100, 0, 0)
        part = self.document.addObject("App::Part", "Part")
        part.addObjects([box, link])
        part.Placement.Base = FreeCAD.Vector(0, 0, 1000)
        self.document.recompute()
        filename = os.path.join(self.tmpdir, "test.obj")
        importOBJ.export([part], filename)
        with open(filename, encoding="utf8") as f:
            lines = f.read().splitlines()
        self.assertEqual([l for l in lines if l.startswith("o ")], ["o Box", "o " + link.Label])
        verts = [tuple(float(c) for c in l.split()[1:]) for l in lines if l.startswith("v ")]
        self.assertEqual(len(verts), 16)
        self.assertIn((0.0, 0.0, 1000.0), verts)
        self.assertIn((110.0, 10.0, 1010.0), verts)

    def test_json_export_names_and_groups(self):
        """The JSON exporter writes plain labels and skips objects without geometry."""
        import json
        from importers import importJSON

        box = self.document.addObject("Part::Box", "Box")
        box.Label = "Box é"
        group = self.document.addObject("App::DocumentObjectGroup", "Group")
        self.document.recompute()
        filename = os.path.join(self.tmpdir, "test.json")
        importJSON.export([box, group], filename)
        with open(filename, encoding="utf8") as f:
            data = json.load(f)
        self.assertEqual([o["name"] for o in data["objects"]], ["Box é"])
        self.assertTrue(data["objects"][0]["vertices"])
        self.assertTrue(data["objects"][0]["facets"])
