# SPDX-License-Identifier: LGPL-2.1-or-later

"""User parameters bound to sketch constraints.

The on-view parameters of the drawing tools create, inside the command of the tool, the user
parameter typed as `name = value` on the sketch and bind the new constraint to it (or to
`-(name)` when the tool stores the absolute value with the points swapped). These tests check
that state on the App side: evaluation, recompute, undo as one step, save and restore.
"""

import math
import os
import tempfile
import unittest

import FreeCAD
import Part
import Sketcher


class TestSketchUserParameters(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestSketchUserParameters")
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def add_line_as_tool(self, start, end):
        """Line with length and angle, parameters and bindings in one transaction."""
        sketch = self.sketch
        self.doc.openTransaction("Add sketch line")
        geo = sketch.addGeometry(Part.LineSegment(start, end), False)
        length = sketch.addConstraint(Sketcher.Constraint("Distance", geo, (end - start).Length))
        angle = sketch.addConstraint(
            Sketcher.Constraint("Angle", -1, 1, geo, 1, math.atan2(end.y - start.y, end.x - start.x))
        )
        self.assertEqual(self.doc.addUserParameter(sketch, "len", "30 mm"), "len")
        self.assertEqual(self.doc.addUserParameter(sketch, "theta", "0 deg"), "theta")
        sketch.setExpression(".Constraints[%d]" % length, "len")
        sketch.setExpression(".Constraints[%d]" % angle, "theta")
        self.doc.commitTransaction()
        self.doc.recompute()
        return geo, length, angle

    def direction(self, geo):
        segment = self.sketch.Geometry[geo]
        return segment.EndPoint - segment.StartPoint

    def test_parameter_drives_length_and_angle(self):
        geo, length, angle = self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        self.assertEqual(self.sketch.getGroupOfProperty("len"), "UserParameters")
        self.assertEqual(self.sketch.getTypeIdOfProperty("theta"), "App::PropertyAngle")
        self.assertAlmostEqual(self.sketch.Constraints[length].Value, 30)

        self.sketch.len = 42
        self.sketch.theta = 30
        self.doc.recompute()
        direction = self.direction(geo)
        self.assertAlmostEqual(direction.Length, 42)
        self.assertAlmostEqual(math.degrees(math.atan2(direction.y, direction.x)), 30)
        # angle parameters are degrees, constraint values radians
        self.assertAlmostEqual(self.sketch.Constraints[angle].Value, math.radians(30))

    def test_negated_binding_follows_signed_parameter(self):
        """DistanceX with swapped points holds |w|; the binding is -(w)."""
        sketch = self.sketch
        self.doc.openTransaction("Add sketch line")
        geo = sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 10, 0), FreeCAD.Vector(-20, 10, 0)), False
        )
        cx = sketch.addConstraint(Sketcher.Constraint("DistanceX", geo, 2, geo, 1, 20.0))
        self.doc.addUserParameter(sketch, "w", "-20 mm")
        sketch.setExpression(".Constraints[%d]" % cx, "-(w)")
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).x, -20)

        sketch.w = -35
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).x, -35)

    def test_expression_on_existing_parameter(self):
        """`= 2*base` binds the constraint without creating a parameter."""
        sketch = self.sketch
        self.doc.addUserParameter(sketch, "base", "15 mm")
        geo = sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0)), False
        )
        length = sketch.addConstraint(Sketcher.Constraint("Distance", geo, 30.0))
        sketch.setExpression(".Constraints[%d]" % length, "2 * base")
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).Length, 30)
        sketch.base = 20
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).Length, 40)

    def test_one_undo_removes_parameters_and_bindings(self):
        self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        self.doc.undo()
        self.doc.recompute()
        self.assertFalse(hasattr(self.sketch, "len"))
        self.assertFalse(hasattr(self.sketch, "theta"))
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertEqual(len(self.sketch.ExpressionEngine), 0)

        self.doc.redo()
        self.doc.recompute()
        self.assertTrue(hasattr(self.sketch, "len"))
        self.assertEqual(len(self.sketch.ExpressionEngine), 2)

    def test_save_restore(self):
        geo, length, angle = self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        path = os.path.join(tempfile.gettempdir(), "TestSketchUserParameters.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        try:
            self.doc = FreeCAD.openDocument(path)
            sketch = self.doc.getObject("Sketch")
            self.sketch = sketch
            self.assertEqual(sketch.getGroupOfProperty("len"), "UserParameters")
            self.assertEqual(
                sorted(sketch.ExpressionEngine),
                sorted([(".Constraints[%d]" % length, "len"), (".Constraints[%d]" % angle, "theta")]),
            )
            self.assertEqual(self.doc.findUserParameter("len")[1], "len")
            sketch.len = 50
            self.doc.recompute()
            self.assertAlmostEqual(self.direction(geo).Length, 50)
        finally:
            os.remove(path)
