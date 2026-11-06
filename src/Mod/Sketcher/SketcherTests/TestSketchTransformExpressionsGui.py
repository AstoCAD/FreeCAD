# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sketcher transformations preserve expression text and live dependencies."""

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtWidgets
from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestSketchTransformExpressionsGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        active = Gui.activeWorkbench()
        self.previous_workbench = active.name() if active else None
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("TransformExpression")
        self.variables = self.doc.addObject("App::VarSet", "Variables")
        self.variables.addProperty("App::PropertyLength", "Span")
        self.variables.Span = 10
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.original_center = App.Vector(12, 14, 0)
        self.sketch.addGeometry(
            Part.Circle(self.original_center, App.Vector(0, 0, 1), 10), False
        )
        self.sketch.addConstraint(Sketcher.Constraint("Radius", 0, 10))
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
            view = Gui.activeDocument().activeView() if Gui.activeDocument() else None
            if view is not None:
                viewport = view.graphicsView().viewport()
                self.key_click(viewport, QtCore.Qt.Key_Escape)
            if view is not None:
                view.setNavigationType(self.original_navigation)
            super().tearDown()
        finally:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if self.previous_workbench is not None:
                Gui.activateWorkbench(self.previous_workbench)

    def expressions(self):
        return dict(self.sketch.ExpressionEngine)

    def checkTransform(self, command, label, expression=None):
        self.variables.Label = label
        if expression is None:
            expression = "<<%s>>.Span" % label
        self.sketch.setExpression("Constraints[0]", expression)
        self.doc.recompute()
        original_expressions = self.expressions()
        self.assertEqual(len(original_expressions), 1)
        canonical_expression = next(iter(original_expressions.values()))
        # Reject a fixture that silently normalizes away the character under test.
        if "'" in label:
            self.assertIn("'", canonical_expression)
        if any(ord(character) > 127 for character in label):
            self.assertIn(label, canonical_expression)
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 10)
        self.assertAlmostEqual(self.sketch.Geometry[0].Radius, 10)
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        view = Gui.activeDocument().activeView()
        view.setNavigationType("Gui::CADNavigationStyle")
        view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
            "orientation 0 0 1 0 focalDistance 100 height 100 }"
        )
        self.flush_gui(150)
        viewport = view.graphicsView().viewport()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.sketch, "Edge1")
        Gui.runCommand("Sketcher_" + command)
        self.flush_gui(150)
        points = [(0, 0), (20, 0)]
        if command == "Rotate":
            points.append((0, 20))
        for x, y in points:
            point = self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(App.Vector(x, y, 0))
            )
            self.move(viewport, point)
            self.click(viewport, point)
        self.flush_gui(150)
        self.assertEqual(self.modal_messages, [])
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount), (1, 1))
        self.assertEqual(self.sketch.solve(), 0)
        transformed_center = self.sketch.Geometry[0].Center
        self.assertGreater((transformed_center - self.original_center).Length, 10,
                           "The actual transform must complete, not abort and retain the input")
        transformed_expressions = self.expressions()
        self.assertAlmostEqual(self.sketch.Geometry[0].Radius, 10)
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 10)

        self.doc.undo()
        self.flush_gui(100)
        self.assertLess((self.sketch.Geometry[0].Center - self.original_center).Length, 1e-6)
        self.assertEqual(self.expressions(), original_expressions)
        self.doc.redo()
        self.flush_gui(100)
        self.assertLess((self.sketch.Geometry[0].Center - transformed_center).Length, 1e-6)
        redone_expressions = self.expressions()

        self.variables.Span = 12.5
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 12.5)
        self.assertAlmostEqual(self.sketch.Geometry[0].Radius, 12.5)
        self.assertLess((self.sketch.Geometry[0].Center - transformed_center).Length, 1e-6)
        self.assertEqual(transformed_expressions, original_expressions)
        self.assertEqual(redone_expressions, original_expressions)
        self.assertEqual(self.expressions(), original_expressions)

    def testTranslateAsciiExpressionControl(self):
        self.checkTransform("Translate", "Sizes")

    def testRotateAsciiExpressionControl(self):
        self.checkTransform("Rotate", "Sizes")

    def testTranslateApostropheExpression(self):
        self.checkTransform("Translate", "O'Brien")

    def testRotateApostropheExpression(self):
        self.checkTransform("Rotate", "O'Brien")

    def testTranslateUnicodeExpressionControl(self):
        self.checkTransform("Translate", "Maße四")

    def testRotateUnicodeExpressionControl(self):
        self.checkTransform("Rotate", "Maße四")

    def checkCopy(self, command, label, expression=None):
        self.variables.Label = label
        if expression is None:
            expression = "<<%s>>.Span" % label
        self.sketch.setExpression("Constraints[0]", expression)
        self.doc.recompute()
        original_expressions = self.expressions()
        self.assertEqual(len(original_expressions), 1)
        canonical_expression = next(iter(original_expressions.values()))
        if "'" in label:
            self.assertIn("'", canonical_expression)
        if any(ord(character) > 127 for character in label):
            self.assertIn(label, canonical_expression)
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 10)
        self.assertAlmostEqual(self.sketch.Geometry[0].Radius, 10)
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        view = Gui.activeDocument().activeView()
        view.setNavigationType("Gui::CADNavigationStyle")
        view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
            "orientation 0 0 1 0 focalDistance 100 height 100 }"
        )
        self.flush_gui(150)
        viewport = view.graphicsView().viewport()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.sketch, "Edge1")
        Gui.runCommand("Sketcher_" + command)
        self.flush_gui(150)
        points = [(0, 0), (20, 0)]
        if command == "Rotate":
            points.append((0, 20))
        for index, (x, y) in enumerate(points):
            point = self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(App.Vector(x, y, 0))
            )
            self.move(viewport, point)
            self.click(viewport, point)
            if index == 0:
                # Existing tool shortcut increases elements1->2, retaining the
                # original and creating a genuinely new geometry/constraint.
                self.key_click(viewport, QtCore.Qt.Key_U, "u")
        self.flush_gui(150)
        self.assertEqual(self.modal_messages, [])
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount), (2, 2),
                         "The copy tool must create a new circle and radius constraint")
        self.assertTrue(all(c.Type == "Radius" for c in self.sketch.Constraints))
        self.assertEqual(self.sketch.solve(), 0)
        self.assertLess((self.sketch.Geometry[0].Center - self.original_center).Length, 1e-6)
        copied_center = self.sketch.Geometry[1].Center
        self.assertGreater((copied_center - self.original_center).Length, 10)
        expected_expressions = dict(original_expressions)
        expected_expressions["Constraints[1]"] = canonical_expression
        copied_expressions = self.expressions()
        if "'" in label:
            self.assertIn("'", self.expressions()["Constraints[1]"])
        for circle, constraint in zip(self.sketch.Geometry, self.sketch.Constraints):
            self.assertAlmostEqual(circle.Radius, 10)
            self.assertAlmostEqual(constraint.Value, 10)

        self.doc.undo()
        self.flush_gui(100)
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount), (1, 1))
        self.assertLess((self.sketch.Geometry[0].Center - self.original_center).Length, 1e-6)
        self.assertEqual(self.expressions(), original_expressions)
        self.doc.redo()
        self.flush_gui(100)
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount), (2, 2))
        redone_expressions = self.expressions()
        self.assertLess((self.sketch.Geometry[1].Center - copied_center).Length, 1e-6)

        self.variables.Span = 12.5
        self.doc.recompute()
        for circle, constraint in zip(self.sketch.Geometry, self.sketch.Constraints):
            self.assertAlmostEqual(circle.Radius, 12.5)
            self.assertAlmostEqual(constraint.Value, 12.5)
        self.assertLess((self.sketch.Geometry[0].Center - self.original_center).Length, 1e-6)
        self.assertLess((self.sketch.Geometry[1].Center - copied_center).Length, 1e-6)
        self.assertEqual(copied_expressions, expected_expressions,
                         "The new radius must retain the canonical original expression")
        self.assertEqual(redone_expressions, expected_expressions)
        self.assertEqual(self.expressions(), expected_expressions)

    def testTranslateCopyAsciiExpressionControl(self):
        self.checkCopy("Translate", "Sizes")

    def testRotateCopyAsciiExpressionControl(self):
        self.checkCopy("Rotate", "Sizes")

    def testTranslateCopyApostropheExpression(self):
        self.checkCopy("Translate", "O'Brien")

    def testRotateCopyApostropheExpression(self):
        self.checkCopy("Rotate", "O'Brien")

    def testTranslateCopyUnicodeExpressionControl(self):
        self.checkCopy("Translate", "Maße四")

    def testRotateCopyUnicodeExpressionControl(self):
        self.checkCopy("Rotate", "Maße四")

    def testTranslateBackslashExpressionControl(self):
        self.checkTransform("Translate", r"Path\name", r"<<Path\\name>>.Span")

    def testRotateBackslashExpressionControl(self):
        self.checkTransform("Rotate", r"Path\name", r"<<Path\\name>>.Span")

    def testTranslateCopyBackslashExpression(self):
        self.checkCopy("Translate", r"Path\name", r"<<Path\\name>>.Span")

    def testRotateCopyBackslashExpression(self):
        self.checkCopy("Rotate", r"Path\name", r"<<Path\\name>>.Span")

    # https://github.com/FreeCAD/FreeCAD/issues/34161: Rotate cloned distances to geometry it
    # does not rotate. A distance from the circle centre to the X axis dragged the rotated copy
    # off its position, and with "Apply equal constraints" each such distance (and a DistanceY
    # locking the centre) became a second Equal next to the one made from the radius.
    def testRotateCopyDropsDistanceToAxis(self):
        self.checkRotateCopyPosition(
            Sketcher.Constraint("Distance", 0, 3, -1, 14), False,
            ["Radius", "Distance", "Radius"])

    def testRotateCopyEqualIgnoresDistanceToAxis(self):
        self.checkRotateCopyPosition(
            Sketcher.Constraint("Distance", 0, 3, -1, 14), True,
            ["Radius", "Distance", "Equal"])

    def testRotateCopyEqualIgnoresLockedCoordinate(self):
        self.checkRotateCopyPosition(
            Sketcher.Constraint("DistanceY", 0, 3, 14), True,
            ["Radius", "DistanceY", "Equal"])

    def checkRotateCopyPosition(self, positionConstraint, applyEqual, expectedTypes):
        self.sketch.addConstraint(positionConstraint)
        self.doc.recompute()
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        view = Gui.activeDocument().activeView()
        view.setNavigationType("Gui::CADNavigationStyle")
        view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
            "orientation 0 0 1 0 focalDistance 100 height 100 }"
        )
        self.flush_gui(150)
        viewport = view.graphicsView().viewport()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.sketch, "Edge1")
        Gui.runCommand("Sketcher_Rotate")
        self.flush_gui(150)
        if applyEqual:
            # "Apply equal constraints" is not stored in the preferences.
            checkbox = Gui.getMainWindow().findChild(QtWidgets.QCheckBox, "checkBoxTS1")
            self.assertIsNotNone(checkbox)
            checkbox.setChecked(True)
            self.flush_gui(50)
        for index, (x, y) in enumerate([(0, 0), (20, 0), (0, 20)]):
            point = self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(App.Vector(x, y, 0))
            )
            self.move(viewport, point)
            self.click(viewport, point)
            if index == 0:
                self.key_click(viewport, QtCore.Qt.Key_U, "u")
        self.flush_gui(150)
        self.assertEqual(self.modal_messages, [])
        self.assertEqual(self.sketch.GeometryCount, 2)
        self.assertEqual([c.Type for c in self.sketch.Constraints], expectedTypes)
        self.assertEqual(self.sketch.solve(), 0)
        self.assertLess((self.sketch.Geometry[0].Center - self.original_center).Length, 1e-6)
        # 90 degrees about the origin: (12, 14) -> (-14, 12)
        self.assertLess((self.sketch.Geometry[1].Center - App.Vector(-14, 12, 0)).Length, 1e-6)
