# SPDX-License-Identifier: LGPL-2.1-or-later
"""Offset with "Add offset constraint" must keep each copy on its own source (#28115)."""

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtGui

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestOffsetConstraintGui(SketcherGuiTestCase):
    OFFSET = 3.0
    # Two separate squares (x0, y0, size). The top side of the second one (added first) lies on
    # a line that is closer than the offset to the offset of the top side of the other one.
    SQUARES = ((20.0, 1.0, 10.0), (0.0, 0.0, 10.0))

    def setUp(self):
        super().setUp()
        self.toolParams = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/Tools")
        self.hadVisibility = "OnViewParameterVisibility" in self.toolParams.GetInts()
        self.oldVisibility = self.toolParams.GetInt("OnViewParameterVisibility", 1)
        self.toolParams.SetInt("OnViewParameterVisibility", 1)

        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("OffsetConstraintTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x0, y0, size in self.SQUARES:
            corners = [
                App.Vector(x0, y0, 0),
                App.Vector(x0 + size, y0, 0),
                App.Vector(x0 + size, y0 + size, 0),
                App.Vector(x0, y0 + size, 0),
            ]
            first = self.sketch.GeometryCount
            for i in range(4):
                self.sketch.addGeometry(Part.LineSegment(corners[i], corners[(i + 1) % 4]))
            for i in range(4):
                self.sketch.addConstraint(
                    Sketcher.Constraint("Coincident", first + i, 2, first + (i + 1) % 4, 1)
                )
        self.doc.recompute()
        Gui.getMainWindow().show()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)

    def tearDown(self):
        try:
            if self.hadVisibility:
                self.toolParams.SetInt("OnViewParameterVisibility", self.oldVisibility)
            else:
                self.toolParams.RemInt("OnViewParameterVisibility")
        finally:
            super().tearDown()

    def visibleSpinBoxes(self):
        return [
            spinbox
            for spinbox in Gui.getMainWindow().findChildren(QtGui.QAbstractSpinBox)
            if spinbox.isVisible() and spinbox.objectName() not in ("parameterOne", "parameterTwo")
        ]

    def testOffsetConstraintOfSeparateSquares(self):
        view = Gui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.flush_gui(150)
        viewport = view.graphicsView().viewport()

        sourceCount = self.sketch.GeometryCount
        Gui.Selection.clearSelection()
        for i in range(sourceCount):
            Gui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Edge%d" % (i + 1))
        Gui.runCommand("Sketcher_Offset")
        self.flush_gui(200)

        checkbox = Gui.getMainWindow().findChild(QtGui.QCheckBox, "checkBoxTS2")
        self.assertIsNotNone(checkbox)
        self.assertTrue(checkbox.isVisible())
        checkbox.setChecked(True)
        self.flush_gui(50)

        # Hover left of the first square so that the offset grows outwards.
        target = self.clamp_to_widget(
            viewport,
            self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(App.Vector(-self.OFFSET, 5, 0))
            ),
        )
        self.move(viewport, target)
        self.assertTrue(
            self.wait_until(lambda: len(self.visibleSpinBoxes()) == 1, timeout_ms=2000),
            "Expected the offset on-view parameter to become visible",
        )
        spinbox = self.visibleSpinBoxes()[0]
        mainWindow = Gui.getMainWindow()
        mainWindow.raise_()
        mainWindow.activateWindow()
        spinbox.setFocus(QtCore.Qt.OtherFocusReason)
        self.flush_gui(50)
        lineEdit = spinbox.findChild(QtGui.QLineEdit)
        self.assertIsNotNone(lineEdit)
        lineEdit.selectAll()
        self.key_click(spinbox, QtCore.Qt.Key_3, "3")
        self.key_click(spinbox, QtCore.Qt.Key_Return, "\r")

        self.assertTrue(
            self.wait_until(lambda: self.sketch.GeometryCount > sourceCount, timeout_ms=3000),
            "Expected the offset to create geometry",
        )
        self.flush_gui(200)

        # The offset geometry is created at the right place: solving with the constraints
        # added by the tool must not move it.
        self.assertEqual(self.sketch.solve(), 0)
        horizontal = []
        vertical = []
        for index, geo in enumerate(self.sketch.Geometry):
            if index < sourceCount or not isinstance(geo, Part.LineSegment):
                continue
            if self.sketch.getConstruction(index):
                continue
            if abs(geo.StartPoint.y - geo.EndPoint.y) < 1e-6:
                horizontal.append(round(geo.StartPoint.y, 6))
            elif abs(geo.StartPoint.x - geo.EndPoint.x) < 1e-6:
                vertical.append(round(geo.StartPoint.x, 6))
            else:
                self.fail("Unexpected slanted offset line %s" % geo)

        d = self.OFFSET
        expectedHorizontal = []
        expectedVertical = []
        for x0, y0, size in self.SQUARES:
            expectedHorizontal += [y0 - d, y0 + size + d]
            expectedVertical += [x0 - d, x0 + size + d]
        self.assertEqual(sorted(horizontal), sorted(expectedHorizontal))
        self.assertEqual(sorted(vertical), sorted(expectedVertical))

        Gui.ActiveDocument.resetEdit()
        self.flush_gui(100)
