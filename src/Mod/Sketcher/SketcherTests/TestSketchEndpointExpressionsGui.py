# SPDX-License-Identifier: LGPL-2.1-or-later
"""Transforms preserve the distinct expressions of each dimension endpoint."""

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtWidgets
from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestSketchEndpointExpressionsGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("EndpointExpressions")
        self.variables = self.doc.addObject("App::VarSet", "Variables")
        for name, value in (("StartGap", 10), ("EndGap", 15)):
            self.variables.addProperty("App::PropertyLength", name)
            setattr(self.variables, name, value)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry([
            Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 20, 0)),
            Part.LineSegment(App.Vector(10, 0, 0), App.Vector(15, 20, 0)),
        ], False)
        self.view = Gui.activeDocument().activeView()
        self.original_navigation = self.view.getNavigationType()
        self.modal_messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            widget = QtWidgets.QApplication.activeModalWidget()
            if widget is not None:
                self.modal_messages.append(widget.windowTitle())
                widget.reject()

        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)

    def tearDown(self):
        try:
            self.key_click(self.view.graphicsView().viewport(), QtCore.Qt.Key_Escape)
            self.view.setNavigationType(self.original_navigation)
            super().tearDown()
        finally:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if self.previous_workbench is not None:
                Gui.activateWorkbench(self.previous_workbench)

    def geometricDistance(self, constraint):
        first = self.sketch.Geometry[constraint.First]
        second = self.sketch.Geometry[constraint.Second]
        point1 = first.StartPoint if int(constraint.FirstPos) == 1 else first.EndPoint
        point2 = second.StartPoint if int(constraint.SecondPos) == 1 else second.EndPoint
        return (point1 - point2).Length

    def checkTranslate(self, copy, both_endpoints, command="Translate"):
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 1, 1, 1, 10.0))
        self.sketch.setExpression("Constraints[0]", "Variables.StartGap")
        if both_endpoints:
            self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 2, 1, 2, 15.0))
            self.sketch.setExpression("Constraints[1]", "Variables.EndGap")
        self.doc.recompute()
        original_expressions = dict(self.sketch.ExpressionEngine)
        dimension_count = 2 if both_endpoints else 1
        original_points = [(g.StartPoint, g.EndPoint) for g in self.sketch.Geometry]
        expected_values = [10, 15] if both_endpoints else [10]
        for constraint, value in zip(self.sketch.Constraints, expected_values):
            self.assertAlmostEqual(constraint.Value, value)
            self.assertAlmostEqual(self.geometricDistance(constraint), value)
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        self.view.setNavigationType("Gui::CADNavigationStyle")
        self.view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
            "orientation 0 0 1 0 focalDistance 100 height 100 }"
        )
        self.flush_gui(150)
        viewport = self.view.graphicsView().viewport()
        Gui.Selection.clearSelection()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(self.sketch, edge)
        Gui.runCommand("Sketcher_" + command)
        self.flush_gui(150)
        points = [(0, 0), (20, 0)]
        if command == "Rotate":
            points.append((0, 20))
        for index, (x, y) in enumerate(points):
            point = self.viewport_to_qpoint(
                self.view, viewport, self.view.getPointOnScreen(App.Vector(x, y, 0))
            )
            self.move(viewport, point)
            self.click(viewport, point)
            if index == 0 and copy:
                self.key_click(viewport, QtCore.Qt.Key_U, "u")
        self.flush_gui(150)
        factor = 2 if copy else 1
        self.assertEqual(self.modal_messages, [])
        self.assertEqual(self.sketch.GeometryCount, 2 * factor)
        self.assertEqual(self.sketch.ConstraintCount, dimension_count * factor)
        self.assertEqual(self.sketch.solve(), 0)
        first_new_geometry = 2 if copy else 0
        movement = (self.sketch.Geometry[first_new_geometry].StartPoint - original_points[0][0]).Length
        if command == "Rotate":
            # The first line starts at the chosen rotation center, so its
            # other endpoint must prove that an actual rotation occurred.
            movement = max(movement,
                (self.sketch.Geometry[first_new_geometry].EndPoint - original_points[0][1]).Length)
        self.assertGreater(
            movement, 10, "The actual transform command must move the selected pair"
        )
        for constraint, value in zip(self.sketch.Constraints, expected_values * factor):
            self.assertAlmostEqual(constraint.Value, value,
                                   msg="Distinct endpoint dimensions must retain their own value")
            self.assertAlmostEqual(self.geometricDistance(constraint), value)
        expected_expressions = dict(original_expressions)
        if copy:
            for index, expression in enumerate(original_expressions.values()):
                expected_expressions["Constraints[%d]" % (dimension_count + index)] = expression
        self.assertEqual(dict(self.sketch.ExpressionEngine), expected_expressions)

        self.doc.undo()
        self.flush_gui(100)
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount),
                         (2, dimension_count))
        self.assertEqual(dict(self.sketch.ExpressionEngine), original_expressions)
        for geometry, (start, end) in zip(self.sketch.Geometry, original_points):
            self.assertLess((geometry.StartPoint - start).Length, 1e-6)
            self.assertLess((geometry.EndPoint - end).Length, 1e-6)
        self.doc.redo()
        self.flush_gui(100)
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount),
                         (2 * factor, dimension_count * factor))
        self.assertEqual(dict(self.sketch.ExpressionEngine), expected_expressions)
        self.variables.StartGap = 12
        self.variables.EndGap = 18
        self.doc.recompute()
        self.assertNotIn("Invalid", self.sketch.State)
        updated_values = [12, 18] if both_endpoints else [12]
        for constraint, value in zip(self.sketch.Constraints, updated_values * factor):
            self.assertAlmostEqual(constraint.Value, value)
            self.assertAlmostEqual(self.geometricDistance(constraint), value)
        self.assertEqual(dict(self.sketch.ExpressionEngine), expected_expressions)

    def testMovedDistinctEndpointExpressions(self):
        self.checkTranslate(copy=False, both_endpoints=True)

    def testCopiedDistinctEndpointExpressions(self):
        self.checkTranslate(copy=True, both_endpoints=True)

    def testMovedSingleEndpointExpressionControl(self):
        self.checkTranslate(copy=False, both_endpoints=False)

    def testCopiedSingleEndpointExpressionControl(self):
        self.checkTranslate(copy=True, both_endpoints=False)

    def testRotatedDistinctEndpointExpressions(self):
        self.checkTranslate(copy=False, both_endpoints=True, command="Rotate")

    def testRotatedCopiedDistinctEndpointExpressions(self):
        self.checkTranslate(copy=True, both_endpoints=True, command="Rotate")

    def testRotatedSingleEndpointExpressionControl(self):
        self.checkTranslate(copy=False, both_endpoints=False, command="Rotate")

    def testRotatedCopiedSingleEndpointExpressionControl(self):
        self.checkTranslate(copy=True, both_endpoints=False, command="Rotate")
