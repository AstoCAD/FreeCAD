# SPDX-License-Identifier: LGPL-2.1-or-later

"""User parameters bound to sketch constraints.

The on-view parameters of the drawing tools create, inside the command of the tool, the user
parameter typed as `name = value` and bind the new constraint to it (or to `-(name)` when the
tool stores the absolute value with the points swapped). The parameter is not a property of the
sketch: it is created on the variable set holding the user parameters of the document
(`UserParameters`, created with the first parameter), and the sketch refers to it qualified
(`UserParameters.name`). These tests check that state on the App side: evaluation, recompute,
undo as one step, save and restore.
"""

import math
import os
import tempfile
import unittest

import FreeCAD
import Part
import Sketcher

# The object holding the user parameters of a document (App::UserParameters::HolderName).
HOLDER = "UserParameters"


class TestSketchUserParameters(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestSketchUserParameters")
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def holder(self):
        """The object holding the user parameters of the document, None when it has none."""
        return self.doc.getObject(HOLDER)

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
        sketch.setExpression(".Constraints[%d]" % length, HOLDER + ".len")
        sketch.setExpression(".Constraints[%d]" % angle, HOLDER + ".theta")
        self.doc.commitTransaction()
        self.doc.recompute()
        return geo, length, angle

    def direction(self, geo):
        segment = self.sketch.Geometry[geo]
        return segment.EndPoint - segment.StartPoint

    def test_parameter_drives_length_and_angle(self):
        geo, length, angle = self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        holder = self.holder()
        self.assertIsNotNone(holder, "Expected the first parameter to create the holder")
        self.assertEqual(holder.TypeId, "App::VarSet")
        self.assertEqual(holder.getGroupOfProperty("len"), "UserParameters")
        self.assertEqual(holder.getTypeIdOfProperty("theta"), "App::PropertyAngle")
        self.assertNotIn("len", self.sketch.PropertiesList)
        self.assertNotIn("theta", self.sketch.PropertiesList)
        self.assertAlmostEqual(self.sketch.Constraints[length].Value, 30)

        holder.len = 42
        holder.theta = 30
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
        sketch.setExpression(".Constraints[%d]" % cx, "-(" + HOLDER + ".w)")
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).x, -20)

        self.holder().w = -35
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
        sketch.setExpression(".Constraints[%d]" % length, "2 * " + HOLDER + ".base")
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).Length, 30)
        self.assertEqual(
            [(obj.Name, name) for obj, name in self.doc.getUserParameters()], [(HOLDER, "base")]
        )
        self.holder().base = 20
        self.doc.recompute()
        self.assertAlmostEqual(self.direction(geo).Length, 40)

    def test_parameter_using_a_parameter_of_the_same_command(self):
        """`boxH = 10 mm` and `boxW = 2 * boxH` typed in two on-view parameters of one tool:
        both are created on the holder, `boxW` follows `boxH`, and so do the constraints bound
        to them."""
        sketch = self.sketch
        self.doc.openTransaction("Add sketch rectangle")
        first = sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0)), False
        )
        second = sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 5, 0), FreeCAD.Vector(0, 15, 0)), False
        )
        width = sketch.addConstraint(Sketcher.Constraint("Distance", first, 20.0))
        height = sketch.addConstraint(Sketcher.Constraint("Distance", second, 10.0))
        self.doc.addUserParameter(sketch, "boxH", "10 mm")
        sketch.setExpression(".Constraints[%d]" % height, HOLDER + ".boxH")
        # As typed in the sketch: the bare name of a parameter that is on the holder.
        self.doc.addUserParameter(sketch, "boxW", "2 * boxH")
        sketch.setExpression(".Constraints[%d]" % width, HOLDER + ".boxW")
        self.doc.commitTransaction()
        self.doc.recompute()

        holder = self.holder()
        self.assertEqual(
            sorted((obj.Name, name) for obj, name in self.doc.getUserParameters()),
            [(HOLDER, "boxH"), (HOLDER, "boxW")],
        )
        self.assertAlmostEqual(holder.boxW.Value, 20)
        self.assertEqual(len(holder.ExpressionEngine), 1, holder.ExpressionEngine)
        self.assertIn("boxH", holder.ExpressionEngine[0][1])
        self.assertAlmostEqual(self.direction(first).Length, 20)
        self.assertAlmostEqual(self.direction(second).Length, 10)

        holder.boxH = 15
        self.doc.recompute()
        self.assertAlmostEqual(holder.boxW.Value, 30)
        self.assertAlmostEqual(self.direction(first).Length, 30)
        self.assertAlmostEqual(self.direction(second).Length, 15)

        # One undo step for all of it; the holder goes with the first parameters.
        self.doc.undo()
        self.doc.recompute()
        self.assertIsNone(self.holder())
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertEqual(sketch.GeometryCount, 0)
        self.assertEqual(len(sketch.ExpressionEngine), 0)

    def test_one_undo_removes_parameters_and_bindings(self):
        self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.doc.getUserParameters(), [])
        # The command created the first parameters of the document, hence their holder too.
        self.assertIsNone(self.holder())
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertEqual(len(self.sketch.ExpressionEngine), 0)

        self.doc.redo()
        self.doc.recompute()
        self.assertIsNotNone(self.holder())
        self.assertTrue(hasattr(self.holder(), "len"))
        self.assertTrue(hasattr(self.holder(), "theta"))
        self.assertEqual(len(self.sketch.ExpressionEngine), 2)

    def test_parameter_taken_back_inside_the_command_frees_its_name(self):
        """The polyline undoing its last point removes, inside its open command, the segment
        and the parameter that the segment created, not the object holding the parameters. The
        name can then be typed again, and the command is still one undo step."""
        sketch = self.sketch

        def add_segment():
            geo = sketch.addGeometry(
                Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0)), False
            )
            length = sketch.addConstraint(Sketcher.Constraint("Distance", geo, 30.0))
            self.assertEqual(self.doc.addUserParameter(sketch, "seg", "30 mm"), "seg")
            sketch.setExpression(".Constraints[%d]" % length, HOLDER + ".seg")
            return geo

        self.doc.openTransaction("Add sketch polyline")
        geo = add_segment()
        sketch.delGeometries([geo])
        self.assertEqual(len(sketch.ExpressionEngine), 0)
        self.holder().removeProperty("seg")
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertIsNotNone(self.holder(), "Expected the holder to stay, empty")

        add_segment()
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(sketch.ExpressionEngine, [(".Constraints[0]", HOLDER + ".seg")])

        self.doc.undo()
        self.doc.recompute()
        self.assertIsNone(self.doc.findUserParameter("seg"))
        self.assertIsNone(self.holder())
        self.assertEqual(sketch.GeometryCount, 0)
        self.assertEqual(len(sketch.ExpressionEngine), 0)

        self.doc.redo()
        self.doc.recompute()
        self.assertAlmostEqual(self.holder().seg.Value, 30)
        self.assertEqual(sketch.ExpressionEngine, [(".Constraints[0]", HOLDER + ".seg")])

    def test_save_restore(self):
        geo, length, angle = self.add_line_as_tool(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        path = os.path.join(tempfile.gettempdir(), "TestSketchUserParameters.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        try:
            self.doc = FreeCAD.openDocument(path)
            sketch = self.doc.getObject("Sketch")
            self.sketch = sketch
            holder = self.holder()
            self.assertIsNotNone(holder)
            self.assertEqual(holder.getGroupOfProperty("len"), "UserParameters")
            self.assertEqual(
                sorted(sketch.ExpressionEngine),
                sorted(
                    [
                        (".Constraints[%d]" % length, HOLDER + ".len"),
                        (".Constraints[%d]" % angle, HOLDER + ".theta"),
                    ]
                ),
            )
            found = self.doc.findUserParameter("len")
            self.assertEqual((found[0].Name, found[1]), (HOLDER, "len"))
            holder.len = 50
            self.doc.recompute()
            self.assertAlmostEqual(self.direction(geo).Length, 50)
        finally:
            os.remove(path)
