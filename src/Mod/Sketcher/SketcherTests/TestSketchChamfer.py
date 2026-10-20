# SPDX-License-Identifier: LGPL-2.1-or-later

"""Preserved-corner chamfer endpoint regressions for FreeCAD#33397 and #33522."""

import unittest

import FreeCAD as App
import Part
import Sketcher


class TestChamferPreservedCornerEndpoints(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ChamferEndpoints33397")
        self.doc.UndoMode = 1
        self.addCleanup(App.closeDocument, self.doc.Name)

    @staticmethod
    def _line_coordinates(sketch):
        return [
            (g.StartPoint.x, g.StartPoint.y, g.StartPoint.z,
             g.EndPoint.x, g.EndPoint.y, g.EndPoint.z)
            for g in sketch.Geometry
        ]

    def _square(self, reversed_winding):
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        points = [(0, 0), (10, 0), (10, 10), (0, 10)]
        if reversed_winding:
            points = [points[0], points[3], points[2], points[1]]
        vectors = [App.Vector(x, y, 0) for x, y in points]
        sketch.addGeometry([
            Part.LineSegment(vectors[i], vectors[(i + 1) % 4]) for i in range(4)
        ], False)
        sketch.addConstraint([
            Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1) for i in range(4)
        ])
        sketch.addConstraint([
            Sketcher.Constraint("Horizontal" if points[i][1] == points[(i + 1) % 4][1]
                                else "Vertical", i)
            for i in range(4)
        ])
        self.doc.recompute()
        self.assertEqual(sketch.getStatusString(), "Valid")
        self.assertEqual(sketch.GeometryCount, 4)
        self.assertEqual(len(sketch.Shape.Edges), 4)
        self.assertEqual(len(sketch.Shape.Wires), 1)
        self.assertTrue(sketch.Shape.isValid())
        self.assertTrue(sketch.Shape.Wires[0].isClosed())
        self.assertEqual(self._line_coordinates(sketch), [
            (vectors[i].x, vectors[i].y, vectors[i].z,
             vectors[(i + 1) % 4].x, vectors[(i + 1) % 4].y, vectors[(i + 1) % 4].z)
            for i in range(4)
        ])
        return sketch

    def _assert_corner_result(self, sketch, chamfer, phase):
        defining = [(i, g) for i, g in enumerate(sketch.Geometry)
                    if not sketch.getConstruction(i)]
        with self.subTest(phase=phase, oracle="valid_status"):
            self.assertEqual(sketch.getStatusString(), "Valid")
        with self.subTest(phase=phase, oracle="defining_geometry_count"):
            self.assertEqual(len(defining), 5)
        with self.subTest(phase=phase, oracle="valid_shape"):
            self.assertTrue(sketch.Shape.isValid())
        with self.subTest(phase=phase, oracle="single_closed_wire"):
            self.assertEqual(len(sketch.Shape.Wires), 1)
            self.assertTrue(sketch.Shape.Wires[0].isClosed())
        bridge_type = "Part::GeomLineSegment" if chamfer else "Part::GeomArcOfCircle"
        if chamfer:
            bridge_index = sketch.GeometryCount - 1
            bridge = sketch.Geometry[bridge_index]
        else:
            arcs = [(i, g) for i, g in defining if g.TypeId == bridge_type]
            self.assertEqual(len(arcs), 1)
            bridge_index, bridge = arcs[0]
        self.assertEqual(bridge.TypeId, bridge_type)
        other_ends = [point for i, g in defining if i != bridge_index
                      for point in (g.StartPoint, g.EndPoint)]
        for label, point in (("start", bridge.StartPoint), ("end", bridge.EndPoint)):
            with self.subTest(phase=phase, oracle="bridge_endpoint_join", endpoint=label):
                self.assertLess(min((point - other).Length for other in other_ends), 1e-7)
        if chamfer:
            for axis in ("x", "y"):
                with self.subTest(phase=phase, oracle="diagonal_bridge", axis=axis):
                    self.assertGreater(abs(getattr(bridge.EndPoint - bridge.StartPoint, axis)), 1e-7)

    def _exercise(self, preserve_corner, chamfer, reversed_winding=False):
        sketch = self._square(reversed_winding)
        before = self._line_coordinates(sketch)
        self.doc.openTransaction("Chamfer endpoint diagnostic")
        try:
            sketch.fillet(0, 2, 1.0, True, preserve_corner, chamfer)
        except Exception as error:
            self.doc.abortTransaction()
            self.fail(f"Valid corner operation raised {type(error).__name__}: {error}")
        self.doc.recompute()
        self.doc.commitTransaction()
        self._assert_corner_result(sketch, chamfer, "post")
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(sketch.GeometryCount, 4)
        self.assertEqual(self._line_coordinates(sketch), before)
        self.assertTrue(sketch.Shape.isValid())
        self.assertEqual(len(sketch.Shape.Wires), 1)
        self.assertTrue(sketch.Shape.Wires[0].isClosed())
        self.doc.redo()
        self.doc.recompute()
        self._assert_corner_result(sketch, chamfer, "redo")

    def test_chamfer_preserved_corner_endpoint_topology(self):
        self._exercise(True, True)

    def test_chamfer_trimmed_without_preserved_corner_control(self):
        self._exercise(False, True)

    def test_chamfer_preserved_corner_reversed_winding(self):
        self._exercise(True, True, True)

    def test_fillet_preserved_corner_control(self):
        self._exercise(True, False)
