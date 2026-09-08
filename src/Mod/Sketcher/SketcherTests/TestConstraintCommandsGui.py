# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD as App
import os
import tempfile
import Part
import Sketcher
from PySide import QtCore
from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestConstraintCommandsGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        Gui.activateWorkbench("SketcherWorkbench")
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher")
        self.saved_params = {
            key: self.params.GetBool(key, True)
            for key in ("ContinuousConstraintMode", "ShowDialogOnDistanceConstraint")
        }
        self.params.SetBool("ContinuousConstraintMode", True)
        self.params.SetBool("ShowDialogOnDistanceConstraint", False)
        self.doc = App.newDocument("ConstraintCommands")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(
            Part.LineSegment(App.Vector(50, 45, 0), App.Vector(10, 15, 0)), False
        )
        self.doc.recompute()
        Gui.activeDocument().setEdit(self.sketch.Name)
        self.view = Gui.activeDocument().activeView()
        self.view.viewTop()
        self.view.fitAll()
        self.flush_gui(150)
        self.viewport = self.view.graphicsView().viewport()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            for key, value in getattr(self, "saved_params", {}).items():
                self.params.SetBool(key, value)

    def select(self, *names):
        Gui.Selection.clearSelection()
        for name in names:
            Gui.Selection.addSelection(self.sketch, name)

    def assert_distance(self, axis, value, driving=True):
        self.assertEqual(self.sketch.ConstraintCount, 1)
        constraint = self.sketch.Constraints[0]
        self.assertEqual(constraint.Type, "Distance" + axis)
        self.assertAlmostEqual(constraint.Value, value, places=6)
        self.assertEqual(self.sketch.getDriving(0), driving)
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(Gui.Selection.getSelectionEx(), [])
        self.doc.undo()
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.doc.redo()
        self.assertEqual(self.sketch.ConstraintCount, 1)
        self.assertEqual(self.sketch.getDriving(0), driving)
        self.doc.undo()

    def click_world(self, point):
        pos = self.viewport_to_qpoint(
            self.view, self.viewport, self.view.getPointOnScreen(point)
        )
        self.move(self.viewport, pos)
        self.click(self.viewport, pos)

    def test_coordinate_distances_from_selection(self):
        for axis, value in (("X", 40), ("Y", 30)):
            for selection in (("Edge1",), ("Vertex1", "Vertex2")):
                with self.subTest(axis=axis, selection=selection):
                    self.select(*selection)
                    Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                    self.assert_distance(axis, value)

    def test_coordinate_distances_from_continuous_picking(self):
        for axis, value in (("X", 40), ("Y", 30)):
            for points in (
                (App.Vector(30, 30, 0),),
                (App.Vector(50, 45, 0), App.Vector(10, 15, 0)),
            ):
                with self.subTest(axis=axis, points=points):
                    Gui.Selection.clearSelection()
                    Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                    for point in points:
                        self.click_world(point)
                    self.assert_distance(axis, value)

    def test_reference_coordinate_distances(self):
        Gui.runCommand("Sketcher_ToggleDrivingConstraint")
        try:
            for axis, value in (("X", 40), ("Y", 30)):
                with self.subTest(axis=axis):
                    self.select("Edge1")
                    Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                    self.assert_distance(axis, value, driving=False)
        finally:
            Gui.runCommand("Sketcher_ToggleDrivingConstraint")

    def test_fixed_geometry_produces_reference_datum(self):
        self.sketch.addConstraint(Sketcher.Constraint("Block", 0))
        self.select("Edge1")
        Gui.runCommand("Sketcher_ConstrainDistanceX")
        self.assertEqual(self.sketch.ConstraintCount, 2)
        self.assertFalse(self.sketch.getDriving(1))
        self.assertEqual(self.sketch.solve(), 0)

    def test_single_vertex_coordinates(self):
        for axis, value in (("X", 50), ("Y", 45)):
            with self.subTest(axis=axis):
                self.select("Vertex1")
                Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                self.assert_distance(axis, value)

    def test_fixed_vertex_coordinates_are_reference(self):
        self.sketch.addConstraint(Sketcher.Constraint("Block", 0))
        for axis, value in (("X", 50), ("Y", 45)):
            with self.subTest(axis=axis):
                self.select("Vertex1")
                Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                self.assertEqual(self.sketch.ConstraintCount, 2)
                self.assertEqual(self.sketch.Constraints[1].Type, "Distance" + axis)
                self.assertAlmostEqual(self.sketch.Constraints[1].Value, value)
                self.assertFalse(self.sketch.getDriving(1))
                self.assertEqual(self.sketch.solve(), 0)
                self.doc.undo()
                self.assertEqual(self.sketch.ConstraintCount, 1)

    def test_coordinate_distances_to_axes(self):
        for axis, name, value in (("X", "V_Axis", 50), ("Y", "H_Axis", 45)):
            for selection in ((name, "Vertex1"), ("Vertex1", name)):
                with self.subTest(axis=axis, selection=selection):
                    self.select(*selection)
                    Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                    self.assert_distance(axis, value)

    def test_external_vertex_coordinates(self):
        source = self.doc.addObject("Part::Feature", "ExternalLine")
        source.Shape = Part.makeLine(App.Vector(-20, -25, 0), App.Vector(-10, -15, 0))
        self.doc.recompute()
        self.sketch.addExternal(source.Name, "Edge1")
        self.doc.recompute()
        self.assertEqual(self.sketch.getGeoVertexIndex(2)[0], -3)
        for axis, value in (("X", -20), ("Y", -25)):
            with self.subTest(axis=axis):
                self.select("Vertex3")
                Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                self.assert_distance(axis, value, driving=False)
                # One external point must not force a movable point's distance to be reference.
                for selection in (("Vertex3", "Vertex1"), ("Vertex1", "Vertex3")):
                    self.select(*selection)
                    Gui.runCommand("Sketcher_ConstrainDistance" + axis)
                    self.assert_distance(axis, 70, driving=True)

    def test_radial_dimensions(self):
        circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10)
        self.sketch.addGeometry(circle, False)
        self.sketch.addGeometry(Part.ArcOfCircle(circle, 0.2, 2.0), False)
        self.doc.recompute()
        for command in ("Radius", "Diameter", "Radiam"):
            for edge, kind, value in (
                ("Edge2", "Radius" if command == "Radius" else "Diameter",
                 10 if command == "Radius" else 20),
                ("Edge3", "Diameter" if command == "Diameter" else "Radius",
                 20 if command == "Diameter" else 10),
            ):
                for reference in (False, True):
                    with self.subTest(command=command, edge=edge, reference=reference):
                        if reference:
                            Gui.runCommand("Sketcher_ToggleDrivingConstraint")
                        try:
                            self.select(edge)
                            Gui.runCommand("Sketcher_Constrain" + command)
                            self.assertEqual(self.sketch.ConstraintCount, 1)
                            self.assertEqual(self.sketch.Constraints[0].Type, kind)
                            self.assertAlmostEqual(self.sketch.Constraints[0].Value, value)
                            self.assertEqual(self.sketch.getDriving(0), not reference)
                            self.assertEqual(self.sketch.solve(), 0)
                            self.doc.undo()
                            self.assertEqual(self.sketch.ConstraintCount, 0)
                            self.doc.redo()
                            self.assertEqual(self.sketch.Constraints[0].Type, kind)
                            self.doc.undo()
                        finally:
                            if reference:
                                Gui.runCommand("Sketcher_ToggleDrivingConstraint")

    def test_radial_dimensions_from_continuous_picking(self):
        self.sketch.addGeometry(
            Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), False
        )
        self.doc.recompute()
        self.view.fitAll()
        self.flush_gui(150)
        for command in ("Radius", "Diameter", "Radiam"):
            with self.subTest(command=command):
                Gui.Selection.clearSelection()
                Gui.runCommand("Sketcher_Constrain" + command)
                # Pick away from the sketch axes so the circle is unambiguous.
                self.click_world(App.Vector(-8, 6, 0))
                self.assertEqual(self.sketch.ConstraintCount, 1)
                expected = "Radius" if command == "Radius" else "Diameter"
                self.assertEqual(self.sketch.Constraints[0].Type, expected)
                self.assertAlmostEqual(self.sketch.Constraints[0].Value,
                                       10 if command == "Radius" else 20)
                self.assertTrue(self.sketch.getDriving(0))
                self.assertEqual(self.sketch.solve(), 0)
                self.doc.undo()
                self.assertEqual(self.sketch.ConstraintCount, 0)

    def test_multiple_radial_dimensions(self):
        circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10)
        self.sketch.addGeometry(circle, False)
        self.sketch.addGeometry(Part.ArcOfCircle(circle, 0.2, 2.0), False)
        self.doc.recompute()
        for command in ("Radius", "Diameter", "Radiam"):
            for edges in (("Edge2", "Edge3"), ("Edge3", "Edge2")):
                for reference in (False, True):
                    with self.subTest(command=command, edges=edges, reference=reference):
                        if reference:
                            Gui.runCommand("Sketcher_ToggleDrivingConstraint")
                        try:
                            self.select(*edges)
                            Gui.runCommand("Sketcher_Constrain" + command)
                            expected = [
                                "Diameter" if command == "Diameter" or
                                (command == "Radiam" and edge == "Edge2") else "Radius"
                                for edge in edges
                            ]
                            if not reference:
                                expected = ["Equal", expected[0]]
                            self.assertEqual([c.Type for c in self.sketch.Constraints], expected)
                            self.assertEqual(self.sketch.solve(), 0)
                            for index in (range(2) if reference else (1,)):
                                self.assertEqual(self.sketch.getDriving(index), not reference)
                            self.doc.undo()
                            self.assertEqual(self.sketch.ConstraintCount, 0)
                        finally:
                            if reference:
                                Gui.runCommand("Sketcher_ToggleDrivingConstraint")

    def test_fixed_and_external_radial_dimensions(self):
        circle = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10)
        self.sketch.addGeometry(circle, False)
        self.sketch.addConstraint(Sketcher.Constraint("Block", 1))
        source = self.doc.addObject("Part::Feature", "ExternalCircle")
        source.Shape = circle.toShape()
        self.doc.recompute()
        self.sketch.addExternal(source.Name, "Edge1")
        self.doc.recompute()
        for command in ("Radius", "Diameter", "Radiam"):
            for edge in ("Edge2", "ExternalEdge1"):
                with self.subTest(command=command, edge=edge):
                    self.select(edge)
                    Gui.runCommand("Sketcher_Constrain" + command)
                    self.assertEqual(self.sketch.ConstraintCount, 2)
                    expected = "Radius" if command == "Radius" else "Diameter"
                    self.assertEqual(self.sketch.Constraints[1].Type, expected)
                    self.assertFalse(self.sketch.getDriving(1))
                    self.assertEqual(self.sketch.solve(), 0)
                    self.doc.undo()
                    self.assertEqual(self.sketch.ConstraintCount, 1)

    def test_radial_dimensions_on_bspline_weights(self):
        spline = Part.BSplineCurve()
        spline.interpolate([App.Vector(0, 0, 0), App.Vector(10, 20, 0), App.Vector(30, 0, 0)])
        self.sketch.addGeometry(spline, False)
        self.sketch.exposeInternalGeometry(1)
        self.doc.recompute()
        pole = next(index for index, geo in enumerate(self.sketch.Geometry)
                    if isinstance(geo, Part.Circle))
        # Exposing a non-rational spline fixes its first weight automatically.
        weight = next(index for index, constraint in enumerate(self.sketch.Constraints)
                      if constraint.Type == "Weight" and constraint.First == pole)
        self.sketch.delConstraint(weight)
        count = self.sketch.ConstraintCount
        for command in ("Radius", "Radiam"):
            with self.subTest(command=command):
                self.select("Edge" + str(pole + 1))
                Gui.runCommand("Sketcher_Constrain" + command)
                self.assertEqual(self.sketch.ConstraintCount, count + 1)
                self.assertEqual(self.sketch.Constraints[-1].Type, "Weight")
                self.assertTrue(self.sketch.getDriving(count))
                self.assertEqual(self.sketch.solve(), 0)
                self.doc.undo()
                self.assertEqual(self.sketch.ConstraintCount, count)

    def test_disabled_continuous_mode_releases_previous_handler(self):
        notifications = App.ParamGet("User parameter:BaseApp/Preferences/NotificationArea")
        saved = notifications.GetBool("NonIntrusiveNotificationsEnabled", True)
        notifications.SetBool("NonIntrusiveNotificationsEnabled", True)
        try:
            for name in ("DistanceX", "Perpendicular", "Tangent", "Equal", "Symmetric"):
                with self.subTest(command=name):
                    self.params.SetBool("ContinuousConstraintMode", True)
                    Gui.Selection.clearSelection()
                    Gui.runCommand("Sketcher_ConstrainDistanceX")
                    self.params.SetBool("ContinuousConstraintMode", False)
                    Gui.runCommand("Sketcher_Constrain" + name)
                    self.flush_gui()
                    self.assertEqual(self.sketch.ConstraintCount, 0)
                    self.assertEqual(self.viewport.cursor().shape(), QtCore.Qt.ArrowCursor)
        finally:
            notifications.SetBool("NonIntrusiveNotificationsEnabled", saved)

    def test_converting_existing_bspline_preserves_constraints(self):
        spline = Part.BSplineCurve()
        spline.interpolate([App.Vector(0, 0, 0), App.Vector(10, 20, 0), App.Vector(30, 0, 0)])
        self.sketch.addGeometry(spline, False)
        self.sketch.exposeInternalGeometry(1)
        self.doc.recompute()
        constraints = [c.Content for c in self.sketch.Constraints]
        geometry = [g.Content for g in self.sketch.Geometry]

        # The API must also be safe for scripts that do not pre-filter their geometry.
        self.sketch.convertToNURBS(1)
        self.assertEqual([c.Content for c in self.sketch.Constraints], constraints)
        self.assertEqual([g.Content for g in self.sketch.Geometry], geometry)

        self.select("Edge2")
        Gui.runCommand("Sketcher_BSplineConvertToNURBS")
        self.assertEqual([c.Content for c in self.sketch.Constraints], constraints)
        self.assertEqual([g.Content for g in self.sketch.Geometry], geometry)
        self.assertEqual(self.sketch.solve(), 0)

        # A mixed selection must still convert the line while leaving the spline intact.
        self.select("Edge1", "Edge2")
        Gui.runCommand("Sketcher_BSplineConvertToNURBS")
        self.assertIsInstance(self.sketch.Geometry[0], Part.BSplineCurve)
        self.assertEqual(self.sketch.Geometry[1].Content, geometry[1])
        self.assertEqual([c.Content for c in self.sketch.Constraints[:len(constraints)]], constraints)
        self.assertEqual(self.sketch.solve(), 0)
        self.doc.undo()
        self.assertEqual([g.Content for g in self.sketch.Geometry], geometry)
        self.assertEqual([c.Content for c in self.sketch.Constraints], constraints)

    def test_nurbs_conversion_preserves_conic_shape(self):
        circle = Part.Circle(App.Vector(12, 15, 0), App.Vector(0, 0, 1), 10)
        ellipse = Part.Ellipse(App.Vector(12, 15, 0), 10, 5)
        curves = [circle, ellipse, Part.ArcOfCircle(circle, 0.3, 2.4),
                  Part.ArcOfEllipse(ellipse, 0.3, 2.4)]
        for curve in curves[2:].copy():
            reversed_curve = curve.copy()
            reversed_curve.reverse()
            curves.append(reversed_curve)
        for curve in curves:
            with self.subTest(curve=type(curve).__name__):
                sketch = self.doc.addObject("Sketcher::SketchObject", "Conversion")
                sketch.addGeometry(curve, False)
                if isinstance(curve, (Part.Ellipse, Part.ArcOfEllipse)):
                    sketch.exposeInternalGeometry(0)
                line = sketch.addGeometry(
                    Part.LineSegment(App.Vector(40, 40, 0), App.Vector(60, 40, 0)), False)
                sketch.addConstraint(Sketcher.Constraint("Distance", line, 20))
                self.doc.recompute()
                original = sketch.Geometry[0].toShape()
                endpoints = [sketch.getPoint(0, pos) for pos in (1, 2)]
                sketch.convertToNURBS(0)
                self.assertEqual(sketch.GeometryCount, 2)
                self.assertEqual(sketch.ConstraintCount, 1)
                self.assertEqual(sketch.Constraints[0].First, 1)
                converted = sketch.Geometry[0]
                self.assertIsInstance(converted, Part.BSplineCurve)
                self.assertEqual(converted.isPeriodic(), isinstance(curve, (Part.Circle, Part.Ellipse)))
                result = converted.toShape()
                if not converted.isPeriodic():
                    for pos, point in enumerate(endpoints, 1):
                        self.assertLess((sketch.getPoint(0, pos) - point).Length, 1e-7)
                for point in original.discretize(Number=25):
                    self.assertLess(Part.Vertex(point).distToShape(result)[0], 1e-7)
                self.assertAlmostEqual(original.Length, result.Length, places=6)
                self.assertEqual(sketch.solve(), 0)
                self.doc.removeObject(sketch.Name)

    def test_nurbs_conversion_mixed_selection_and_undo(self):
        ellipse = self.sketch.addGeometry(Part.Ellipse(App.Vector(0, 0, 0), 10, 5), False)
        self.sketch.exposeInternalGeometry(ellipse)
        circle = self.sketch.addGeometry(
            Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 5), False)
        circle_id = self.sketch.getGeometryId(circle)
        ellipse_id = self.sketch.getGeometryId(ellipse)
        self.doc.recompute()
        geometry = [g.Content for g in self.sketch.Geometry]
        constraints = [c.Content for c in self.sketch.Constraints]
        for selection in (("Edge3", "Edge2", "Edge" + str(circle + 1)),
                          ("Edge" + str(circle + 1), "Edge2", "Edge3")):
            with self.subTest(selection=selection):
                self.select(*selection)
                Gui.runCommand("Sketcher_BSplineConvertToNURBS")
                for stable_id in (ellipse_id, circle_id):
                    index = next(i for i in range(self.sketch.GeometryCount)
                                 if self.sketch.getGeometryId(i) == stable_id)
                    self.assertTrue(self.sketch.Geometry[index].isPeriodic())
                # Only the original unrelated line remains; ellipse axes have gone.
                self.assertEqual(sum(isinstance(g, Part.LineSegment)
                                     for g in self.sketch.Geometry), 1)
                self.assertEqual(self.sketch.solve(), 0)
                converted = [g.Content for g in self.sketch.Geometry]
                self.doc.undo()
                self.assertEqual([g.Content for g in self.sketch.Geometry], geometry)
                self.assertEqual([c.Content for c in self.sketch.Constraints], constraints)
                self.doc.redo()
                self.assertEqual([g.Content for g in self.sketch.Geometry], converted)
                self.doc.undo()

    def test_nurbs_conversion_external_circle(self):
        source = self.doc.addObject("Part::Feature", "ExternalCircle")
        source.Shape = Part.Circle(App.Vector(30, 0, 0), App.Vector(0, 0, 1), 5).toShape()
        self.doc.recompute()
        self.sketch.addExternal(source.Name, "Edge1")
        self.doc.recompute()
        external = self.sketch.ExternalGeometry
        self.select("ExternalEdge1")
        Gui.runCommand("Sketcher_BSplineConvertToNURBS")
        self.assertIsInstance(self.sketch.Geometry[1], Part.BSplineCurve)
        self.assertTrue(self.sketch.Geometry[1].isPeriodic())
        self.assertGreater(self.sketch.GeometryCount, 2)  # Poles and knots were exposed.
        self.assertEqual(self.sketch.ExternalGeometry, external)
        self.assertEqual(self.sketch.solve(), 0)
        self.doc.undo()
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertEqual(self.sketch.ExternalGeometry, external)

    def test_nurbs_conversion_preserves_shared_internal_geometry(self):
        ellipse = Part.Ellipse(App.Vector(0, 0, 0), 10, 5)
        first = self.sketch.addGeometry(Part.ArcOfEllipse(ellipse, 0.2, 2.8), False)
        second = self.sketch.addGeometry(Part.ArcOfEllipse(ellipse, 3.2, 5.8), False)
        self.sketch.exposeInternalGeometry(first)
        shared_ids = []
        for constraint in self.sketch.Constraints:
            if constraint.Type == "InternalAlignment" and constraint.Second == first:
                shared_ids.append(self.sketch.getGeometryId(constraint.First))
                constraint.Second = second
                self.sketch.addConstraint(constraint)
        self.assertEqual(self.sketch.solve(), 0)
        self.sketch.convertToNURBS(first)
        self.assertIsInstance(self.sketch.Geometry[first], Part.BSplineCurve)
        remaining_ids = [self.sketch.getGeometryId(i) for i in range(self.sketch.GeometryCount)]
        self.assertTrue(set(shared_ids).issubset(remaining_ids))
        self.assertEqual(self.sketch.solve(), 0)

    def test_nurbs_conversion_save_restore(self):
        index = self.sketch.addGeometry(Part.Ellipse(App.Vector(0, 0, 0), 10, 5), False)
        self.sketch.exposeInternalGeometry(index)
        self.select("Edge2")
        Gui.runCommand("Sketcher_BSplineConvertToNURBS")
        Gui.activeDocument().resetEdit()
        self.doc.recompute()
        count = self.sketch.GeometryCount
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Converted.FCStd")
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.sketch = self.doc.getObject("Sketch")
            self.assertEqual(self.sketch.GeometryCount, count)
            self.assertTrue(self.sketch.Geometry[1].isPeriodic())
            self.assertEqual(self.sketch.solve(), 0)
            App.closeDocument(self.doc.Name)
            self.doc = None

    def test_switching_continuous_commands_preserves_sketch(self):
        for name in (
            "Horizontal", "Vertical", "HorVer", "Lock", "Block", "Coincident",
            "PointOnObject", "Distance", "DistanceX", "DistanceY", "Parallel",
            "Perpendicular", "Tangent", "Radius", "Diameter", "Radiam", "Angle",
            "Equal", "Symmetric",
        ):
            with self.subTest(command=name):
                Gui.Selection.clearSelection()
                Gui.runCommand("Sketcher_Constrain" + name)
                self.flush_gui()
                self.assertEqual(self.sketch.ConstraintCount, 0)
                self.assertIsNotNone(Gui.activeDocument().getInEdit())
                self.assertEqual(self.viewport.cursor().shape(), QtCore.Qt.BitmapCursor)

