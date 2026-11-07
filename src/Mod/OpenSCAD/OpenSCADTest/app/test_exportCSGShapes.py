# SPDX-License-Identifier: LGPL-2.1-or-later
"""Round-trip tests for the CSG export of shapes written as polyhedra and of extrusions."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import Part
import exportCSG
import importCSG


class TestExportCSGShapes(unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-export-shapes-")
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("ExportCSGShapes")
        # curved shapes are meshed: use a fine mesh to compare volumes
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/Mod/OpenSCAD")
        self.deflection = self.params.GetFloat("meshdeflection", 0.0)
        self.had_deflection = "meshdeflection" in self.params.GetFloats()
        self.params.SetFloat("meshdeflection", 0.01)

    def _cleanup(self):
        if self.had_deflection:
            self.params.SetFloat("meshdeflection", self.deflection)
        else:
            self.params.RemFloat("meshdeflection")
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _roundtrip(self, obj, rel_volume=1e-6):
        self.doc.recompute()
        expected = obj.Shape
        self.assertFalse(expected.isNull())
        path = Path(self.temp.name) / (obj.Name + ".csg")
        exportCSG.export([obj], str(path))
        text = path.read_text(encoding="utf-8")
        imported = importCSG.open(str(path))
        imported.recompute()
        roots = [o for o in imported.RootObjects if hasattr(o, "Shape")]
        self.assertEqual(len(roots), 1, text[:500])
        shape = roots[0].Shape
        self.assertFalse(shape.isNull(), text[:500])
        self.assertAlmostEqual(shape.Volume / expected.Volume, 1.0, delta=rel_volume)
        tol = 1e-4 if rel_volume < 1e-3 else 0.2
        # BoundBox of curved shapes is loose: compare the tight boxes
        got, want = shape.optimalBoundingBox(), expected.optimalBoundingBox()
        for name in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"):
            self.assertAlmostEqual(getattr(got, name), getattr(want, name), delta=tol, msg=name)
        return text

    def test_shape_feature(self):
        """A plain Part::Feature is written as a polyhedron the importer can read."""
        obj = self.doc.addObject("Part::Feature", "Feature")
        obj.Shape = Part.makeBox(1, 2, 3)
        self._roundtrip(obj)

    def test_placed_shape_feature(self):
        """The mesh is made of the placed shape: its Placement must not be applied twice."""
        obj = self.doc.addObject("Part::Feature", "Feature")
        obj.Shape = Part.makeBox(1, 2, 3)
        obj.Placement = App.Placement(App.Vector(10, 0, 0), App.Rotation(App.Vector(0, 0, 1), 30))
        self._roundtrip(obj)

    def test_shape_feature_in_boolean(self):
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 4
        feat = self.doc.addObject("Part::Feature", "Feature")
        # the tool reaches 1 into the box only where it is placed
        feat.Shape = Part.makeBox(1, 1, 3)
        feat.Placement = App.Placement(App.Vector(1, 1, -2), App.Rotation())
        cut = self.doc.addObject("Part::Cut", "Cut")
        cut.Base = box
        cut.Tool = feat
        self._roundtrip(cut)

    def test_extruded_plane(self):
        plane = self.doc.addObject("Part::Plane", "Plane")
        plane.Length = 4
        plane.Width = 3
        ext = self.doc.addObject("Part::Extrusion", "Extrusion")
        ext.Base = plane
        ext.Dir = App.Vector(0, 0, 5)
        text = self._roundtrip(ext)
        self.assertIn("linear_extrude", text)
        self.assertEqual(ext.Dir, App.Vector(0, 0, 5))

    def test_symmetric_extruded_plane(self):
        plane = self.doc.addObject("Part::Plane", "Plane")
        plane.Length = 4
        plane.Width = 3
        ext = self.doc.addObject("Part::Extrusion", "Extrusion")
        ext.Base = plane
        ext.Dir = App.Vector(0, 0, 1)
        ext.LengthFwd = 6
        ext.Symmetric = True
        text = self._roundtrip(ext)
        self.assertIn("linear_extrude", text)

    def test_negative_length_extruded_plane(self):
        """OpenSCAD makes nothing of a negative height: export the shape as a polyhedron."""
        plane = self.doc.addObject("Part::Plane", "Plane")
        plane.Length = 4
        plane.Width = 3
        ext = self.doc.addObject("Part::Extrusion", "Extrusion")
        ext.Base = plane
        ext.Dir = App.Vector(0, 0, 1)
        ext.LengthFwd = -5
        text = self._roundtrip(ext)
        self.assertNotIn("linear_extrude", text)

    def test_placed_extruded_plane(self):
        """linear_extrude() can't describe this one: it is exported as a polyhedron."""
        plane = self.doc.addObject("Part::Plane", "Plane")
        plane.Length = 4
        plane.Width = 3
        plane.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation(App.Vector(1, 0, 0), 90))
        ext = self.doc.addObject("Part::Extrusion", "Extrusion")
        ext.Base = plane
        ext.DirMode = "Normal"
        ext.LengthFwd = 2
        self._roundtrip(ext)

    def test_extruded_circle(self):
        """Extrusions of other profiles used to be left out of the file."""
        circle = self.doc.addObject("Part::Circle", "Circle")
        circle.Radius = 2
        ext = self.doc.addObject("Part::Extrusion", "Extrusion")
        ext.Base = circle
        ext.Dir = App.Vector(0, 0, 5)
        ext.Solid = True
        self._roundtrip(ext, rel_volume=0.05)

    def test_partial_torus(self):
        obj = self.doc.addObject("Part::Torus", "Torus")
        obj.Radius1 = 10
        obj.Radius2 = 2
        obj.Angle3 = 180
        self._roundtrip(obj, rel_volume=0.05)


if __name__ == "__main__":
    unittest.main()
