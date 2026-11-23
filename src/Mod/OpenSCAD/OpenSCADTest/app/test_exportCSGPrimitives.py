# SPDX-License-Identifier: LGPL-2.1-or-later
"""Round-trip tests for the CSG export of Part primitives."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import exportCSG
import importCSG


class TestExportCSGPrimitives(unittest.TestCase):
    """Length properties must be written as numbers, without unit."""

    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-export-")
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("ExportCSGPrimitives")

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        self.temp.cleanup()

    def _roundtrip(self, obj, placement=None, meshed=False):
        """meshed: the shape is written as a polyhedron, which only
        approximates curved faces."""
        if placement:
            obj.Placement = placement
        self.doc.recompute()
        path = Path(self.temp.name) / (obj.Name + ".csg")
        if meshed:
            # use a fine mesh to compare volumes
            params = App.ParamGet("User parameter:BaseApp/Preferences/Mod/OpenSCAD")
            if "meshdeflection" in params.GetFloats():
                deflection = params.GetFloat("meshdeflection")
                self.addCleanup(params.SetFloat, "meshdeflection", deflection)
            else:
                self.addCleanup(params.RemFloat, "meshdeflection")
            params.SetFloat("meshdeflection", 0.01)
        exportCSG.export([obj], str(path))
        text = path.read_text(encoding="utf-8")
        self.assertNotIn(" mm", text)
        imported = importCSG.open(str(path))
        imported.recompute()
        roots = [o for o in imported.RootObjects if hasattr(o, "Shape")]
        self.assertEqual(len(roots), 1, text)
        shape = roots[0].Shape
        self.assertFalse(shape.isNull(), text)
        expected = obj.Shape
        expected_box = expected.BoundBox
        if meshed:
            # the box of a curved shape is not tight, that of its mesh is
            expected_box = expected.optimalBoundingBox()
            volume_tolerance = {"delta": 0.02 * expected.Volume}
            tolerance = {"delta": 0.01 * expected_box.DiagonalLength}
        else:
            volume_tolerance = tolerance = {"places": 4}
        if expected.Volume > 0:
            self.assertAlmostEqual(shape.Volume, expected.Volume, **volume_tolerance)
        else:
            # OpenSCAD has no wires: a closed wire comes back as a face
            import Part
            self.assertAlmostEqual(shape.Area, Part.Face(expected.Wires[0]).Area, places=4)
        for name in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"):
            self.assertAlmostEqual(getattr(shape.BoundBox, name),
                                   getattr(expected_box, name), msg=name, **tolerance)

    def test_sphere(self):
        obj = self.doc.addObject("Part::Sphere", "Sphere")
        obj.Radius = 10
        self._roundtrip(obj)

    def test_placed_sphere(self):
        obj = self.doc.addObject("Part::Sphere", "Sphere")
        obj.Radius = 3
        self._roundtrip(obj, App.Placement(App.Vector(10, 0, 0), App.Rotation()))

    def test_torus(self):
        obj = self.doc.addObject("Part::Torus", "Torus")
        obj.Radius1 = 10
        obj.Radius2 = 2
        self._roundtrip(obj)

    def test_placed_torus(self):
        obj = self.doc.addObject("Part::Torus", "Torus")
        obj.Radius1 = 10
        obj.Radius2 = 2
        self._roundtrip(obj, App.Placement(App.Vector(0, 0, 5), App.Rotation()))

    def test_prism(self):
        obj = self.doc.addObject("Part::Prism", "Prism")
        obj.Polygon = 6
        obj.Circumradius = 5
        obj.Height = 3
        self._roundtrip(obj)

    def test_regular_polygon(self):
        obj = self.doc.addObject("Part::RegularPolygon", "RegularPolygon")
        obj.Polygon = 6
        obj.Circumradius = 4
        self._roundtrip(obj)

    def test_placed_regular_polygon(self):
        obj = self.doc.addObject("Part::RegularPolygon", "RegularPolygon")
        obj.Polygon = 6
        obj.Circumradius = 2
        self._roundtrip(obj, App.Placement(App.Vector(0, 5, 0), App.Rotation()))

    # OpenSCAD has no partial or skewed primitives: these are written as
    # polyhedra, never as the whole straight primitive.

    def test_partial_sphere(self):
        obj = self.doc.addObject("Part::Sphere", "Sphere")
        obj.Radius = 5
        obj.Angle1 = 0
        obj.Angle3 = 180
        self._roundtrip(obj, meshed=True)

    def test_partial_placed_cylinder(self):
        obj = self.doc.addObject("Part::Cylinder", "Cylinder")
        obj.Radius = 5
        obj.Height = 4
        obj.Angle = 90
        self._roundtrip(obj, App.Placement(App.Vector(10, 0, 0), App.Rotation()), meshed=True)

    def test_skewed_cylinder(self):
        obj = self.doc.addObject("Part::Cylinder", "Cylinder")
        obj.Radius = 5
        obj.Height = 4
        obj.FirstAngle = 30
        self._roundtrip(obj, meshed=True)

    def test_partial_cone(self):
        obj = self.doc.addObject("Part::Cone", "Cone")
        obj.Radius1 = 5
        obj.Radius2 = 2
        obj.Height = 4
        obj.Angle = 180
        self._roundtrip(obj, meshed=True)

    def test_skewed_prism(self):
        obj = self.doc.addObject("Part::Prism", "Prism")
        obj.Polygon = 6
        obj.Circumradius = 5
        obj.Height = 4
        obj.SecondAngle = 20
        self._roundtrip(obj)

    def test_partial_torus_section(self):
        obj = self.doc.addObject("Part::Torus", "Torus")
        obj.Radius1 = 10
        obj.Radius2 = 2
        obj.Angle1 = 0
        self._roundtrip(obj, meshed=True)


if __name__ == "__main__":
    unittest.main()
