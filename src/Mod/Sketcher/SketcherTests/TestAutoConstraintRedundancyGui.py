# SPDX-License-Identifier: LGPL-2.1-or-later
"""Redundant autoconstraints are filtered when a tool creates geometry (#32680)."""

import FreeCAD
import Part
import Sketcher
from PySide import QtCore

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

TOOLS_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/Tools"
SKETCHER_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher"


class TestAutoConstraintRedundancyGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.tools = FreeCAD.ParamGet(TOOLS_PATH)
        self.hadOvp = "OnViewParameterVisibility" in self.tools.GetInts()
        self.oldOvp = self.tools.GetInt("OnViewParameterVisibility", 1)
        self.tools.SetInt("OnViewParameterVisibility", 0)
        self.sketcher = FreeCAD.ParamGet(SKETCHER_PATH)
        self.hadContinuous = "ContinuousCreationMode" in self.sketcher.GetBools()
        self.oldContinuous = self.sketcher.GetBool("ContinuousCreationMode", True)
        self.sketcher.SetBool("ContinuousCreationMode", False)
        self.hadAutoRemove = "AutoRemoveRedundants" in self.sketcher.GetBools()
        self.oldAutoRemove = self.sketcher.GetBool("AutoRemoveRedundants", False)

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("AutoConstraintRedundancy")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        # A line starting on the vertical axis, and two lines starting at points symmetric about
        # this axis.
        V = FreeCAD.Vector
        self.sketch.addGeometry(Part.LineSegment(V(0, -10, 0), V(-5, -20, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(10, 0, 0), V(20, 5, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(-10, 0, 0), V(-20, 5, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("PointOnObject", 0, 1, -2))
        self.sketch.addConstraint(Sketcher.Constraint("Symmetric", 1, 1, 2, 1, -2))
        self.doc.recompute()
        self.sketch.ViewObject.Autoconstraints = True
        self.sketch.ViewObject.AvoidRedundant = True

    def tearDown(self):
        try:
            if self.hadOvp:
                self.tools.SetInt("OnViewParameterVisibility", self.oldOvp)
            else:
                self.tools.RemInt("OnViewParameterVisibility")
            if self.hadContinuous:
                self.sketcher.SetBool("ContinuousCreationMode", self.oldContinuous)
            else:
                self.sketcher.RemBool("ContinuousCreationMode")
            if self.hadAutoRemove:
                self.sketcher.SetBool("AutoRemoveRedundants", self.oldAutoRemove)
            else:
                self.sketcher.RemBool("AutoRemoveRedundants")
        finally:
            super().tearDown()

    def coincidentPartners(self, geoId):
        partners = set()
        for constraint in self.sketch.Constraints:
            if constraint.Type != "Coincident":
                continue
            if constraint.First == geoId:
                partners.add((constraint.Second, constraint.SecondPos))
            elif constraint.Second == geoId:
                partners.add((constraint.First, constraint.FirstPos))
        return partners

    def drawArcByCenterBetweenSymmetricPoints(self):
        FreeCADGui.getMainWindow().show()
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.pump(200)
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(150)
        viewport = view.graphicsView().viewport()

        def screen(x, y):
            return self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(FreeCAD.Vector(x, y, 0))
            )

        FreeCADGui.runCommand("Sketcher_CreateArc")
        self.pump(200)

        center = screen(0, -10)
        self.move(viewport, center)
        self.click(viewport, center)
        start = screen(10, 0)
        self.move(viewport, start)
        self.click(viewport, start)
        # sweep counterclockwise over the top to the left point
        for x, y in ((8, 6), (4, 9), (0, 10), (-4, 9), (-8, 6)):
            self.move(viewport, screen(x, y))
        end = screen(-10, 0)
        self.move(viewport, end)
        self.click(viewport, end)
        self.pump(200)
        viewport.setFocus()
        self.key_click(viewport, QtCore.Qt.Key_Escape)
        self.pump(100)

        self.assertEqual(self.sketch.GeometryCount, 4, "Expected the arc to be created")
        self.assertIsInstance(self.sketch.Geometry[3], Part.ArcOfCircle)

    def checkResult(self):
        # the constraints of the sketch are kept
        self.assertGreaterEqual(self.sketch.ConstraintCount, 2)
        self.assertEqual(self.sketch.Constraints[0].Type, "PointOnObject")
        self.assertEqual(self.sketch.Constraints[1].Type, "Symmetric")

        # the arc endpoints are connected to the two symmetric points
        connected = self.coincidentPartners(3)
        self.assertIn((1, 1), connected, "Expected the arc to be connected to the right point")
        self.assertIn((2, 1), connected, "Expected the arc to be connected to the left point")

        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(list(self.sketch.RedundantConstraints), [])
        self.assertEqual(list(self.sketch.ConflictingConstraints), [])

    def testRedundantAutoconstraintIsNotAdded(self):
        self.sketcher.SetBool("AutoRemoveRedundants", False)
        self.drawArcByCenterBetweenSymmetricPoints()
        self.checkResult()

    def testSketchConstraintIsNotAutoRemoved(self):
        self.sketcher.SetBool("AutoRemoveRedundants", True)
        self.drawArcByCenterBetweenSymmetricPoints()
        self.doc.recompute()
        self.pump(100)
        self.checkResult()
