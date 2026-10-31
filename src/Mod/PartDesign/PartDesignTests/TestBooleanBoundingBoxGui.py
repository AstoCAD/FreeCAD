# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI bounding-box regressions for FreeCAD/FreeCAD#33335.

The full Boolean result is a long solid, while its tool only intersects near
one end.  Query the real scene-graph bounding boxes, independently of model
bounds, with the Boolean explicitly displaying its result.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets
from pivy import coin


class TestBooleanBoundingBoxGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.previous_cursor = QtGui.QCursor.pos()
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("BooleanBounds")
        self.body = self.doc.addObject("PartDesign::Body", "ResultBody")
        self.base = self.doc.addObject("PartDesign::AdditiveBox", "LongBox")
        self.body.addObject(self.base)
        self.base.Length = 100
        self.base.Width = 100
        self.base.Height = 1000
        self.tool = self.doc.addObject("PartDesign::Body", "ToolBody")
        self.tool_box = self.doc.addObject("PartDesign::AdditiveBox", "ToolBox")
        self.tool.addObject(self.tool_box)
        self.tool_box.Length = 20
        self.tool_box.Width = 20
        self.tool_box.Height = 20
        self.tool_box.Placement.Base = App.Vector(40, 40, 980)
        self.doc.recompute()
        self.view = Gui.activeDocument().activeView()
        self.view.viewAxonometric()
        self.view.fitAll()
        self.pump()

    def tearDown(self):
        Gui.Selection.clearSelection()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        QtGui.QCursor.setPos(self.previous_cursor)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        self.view.redraw()
        Gui.updateGui()

    @staticmethod
    def coordinates(bounds):
        return (bounds.XMin, bounds.YMin, bounds.ZMin,
                bounds.XMax, bounds.YMax, bounds.ZMax)

    def assertSameBounds(self, actual, expected):
        self.assertTrue(actual.isValid(), "The displayed result needs a valid bounding box")
        for coordinate, reference in zip(self.coordinates(actual), self.coordinates(expected)):
            self.assertAlmostEqual(coordinate, reference, delta=1e-4)

    def checkBooleanResultBounds(self, tool_visible):
        boolean = self.doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.body.addObject(boolean)
        boolean.Type = 1
        boolean.setObjects([self.tool])
        boolean.ViewObject.Display = "Result"
        self.doc.recompute()
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, 10000000 - 8000, places=4)
        self.assertAlmostEqual(boolean.Shape.BoundBox.ZLength, 1000)
        self.assertEqual(self.body.Tip, boolean)
        self.base.ViewObject.hide()
        self.tool.ViewObject.Visibility = tool_visible
        self.tool_box.ViewObject.show()
        self.body.ViewObject.show()
        boolean.ViewObject.show()
        self.pump()
        actual_boolean = boolean.ViewObject.getBoundingBox(view=self.view)
        actual_body = self.body.ViewObject.getBoundingBox(view=self.view)
        self.assertEqual(boolean.ViewObject.Display, "Result")
        self.assertSameBounds(actual_boolean, boolean.Shape.BoundBox)
        self.assertSameBounds(actual_body, self.body.Shape.BoundBox)

    def testBooleanResultWithVisibleTool(self):
        self.checkBooleanResultBounds(True)

    def testBooleanResultWithHiddenTool(self):
        self.checkBooleanResultBounds(False)

    def testOrdinaryBodyBoundsControl(self):
        self.tool.ViewObject.hide()
        self.base.ViewObject.show()
        self.body.ViewObject.show()
        self.pump()
        self.assertSameBounds(self.base.ViewObject.getBoundingBox(view=self.view),
                              self.base.Shape.BoundBox)
        self.assertSameBounds(self.body.ViewObject.getBoundingBox(view=self.view),
                              self.body.Shape.BoundBox)

    def createBoolean(self, tool_visible=False):
        boolean = self.doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.body.addObject(boolean)
        boolean.Type = 1
        boolean.setObjects([self.tool])
        boolean.ViewObject.Display = "Result"
        self.doc.recompute()
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, 9992000, places=4)
        self.assertAlmostEqual(boolean.Shape.BoundBox.ZLength, 1000)
        self.assertEqual(self.body.Tip, boolean)
        self.base.ViewObject.hide()
        self.tool.ViewObject.Visibility = tool_visible
        self.tool_box.ViewObject.show()
        self.body.ViewObject.show()
        boolean.ViewObject.show()
        self.pump()
        return boolean

    def sceneBounds(self, obj):
        """Query the actual displayed Coin root, independently of VP bbox routing."""
        manager = self.view.getViewer().getSoRenderManager()
        action = coin.SoGetBoundingBoxAction(manager.getViewportRegion())
        action.apply(obj.ViewObject.RootNode)
        bounds = action.getBoundingBox()
        if bounds.isEmpty():
            return App.BoundBox()
        lower, upper = bounds.getMin(), bounds.getMax()
        return App.BoundBox(lower[0], lower[1], lower[2], upper[0], upper[1], upper[2])

    def testResultCoinSceneControl(self):
        boolean = self.createBoolean()
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
        self.assertSameBounds(self.sceneBounds(self.body), self.body.Shape.BoundBox)

    def testBodyResultWithHiddenTool(self):
        boolean = self.createBoolean()
        self.assertSameBounds(self.sceneBounds(boolean), boolean.Shape.BoundBox)
        self.assertSameBounds(self.body.ViewObject.getBoundingBox(view=self.view),
                              self.body.Shape.BoundBox)

    def testToolsDisplayVisibleSourceMatchesScene(self):
        boolean = self.createBoolean(True)
        boolean.ViewObject.Display = "Tools"
        self.pump()
        self.assertEqual(boolean.ViewObject.Display, "Tools")
        actual_scene = self.sceneBounds(boolean)
        self.assertTrue(actual_scene.isValid())
        self.assertSameBounds(boolean.ViewObject.getBoundingBox(view=self.view), actual_scene)

    def testToolsDisplayHiddenSourceMatchesScene(self):
        boolean = self.createBoolean(False)
        boolean.ViewObject.Display = "Tools"
        self.pump()
        self.assertFalse(self.tool.ViewObject.Visibility)
        self.assertEqual(boolean.ViewObject.Display, "Tools")
        actual_scene = self.sceneBounds(boolean)
        self.assertTrue(actual_scene.isValid())
        self.assertSameBounds(boolean.ViewObject.getBoundingBox(view=self.view), actual_scene)

    def testGroupDisplaySceneControl(self):
        boolean = self.createBoolean(True)
        self.assertIn("Group", boolean.ViewObject.listDisplayModes())
        boolean.ViewObject.DisplayMode = "Group"
        self.pump()
        self.assertEqual(boolean.ViewObject.DisplayMode, "Group")
        actual_scene = self.sceneBounds(boolean)
        self.assertSameBounds(actual_scene, self.tool.Shape.BoundBox)
        self.assertSameBounds(boolean.ViewObject.getBoundingBox(view=self.view), actual_scene)

    def testExplicitResultFaceControl(self):
        boolean = self.createBoolean()
        reference = self.doc.addObject("Part::Feature", "OrdinaryResult")
        reference.Shape = boolean.Shape.copy()
        self.doc.recompute()
        reference.ViewObject.hide()
        self.pump()
        reference_bounds = reference.ViewObject.getBoundingBox(subname="Face1", view=self.view)
        face_bounds = boolean.Shape.Faces[0].BoundBox
        # The existing Part face scene can return a conservative whole-shape
        # box. Compare the unchanged ordinary Part path, rather than assume
        # that its visual bbox is a tight topological-face bbox.
        self.assertTrue(reference_bounds.isValid())
        for x in (face_bounds.XMin, face_bounds.XMax):
            for y in (face_bounds.YMin, face_bounds.YMax):
                for z in (face_bounds.ZMin, face_bounds.ZMax):
                    self.assertTrue(reference_bounds.isInside(App.Vector(x, y, z)))
        self.assertSameBounds(
            boolean.ViewObject.getBoundingBox(subname="Face1", view=self.view), reference_bounds
        )
        self.assertSameBounds(
            self.body.ViewObject.getBoundingBox(subname=boolean.Name + ".Face1", view=self.view),
            reference_bounds
        )

    def testExplicitToolPathControl(self):
        boolean = self.createBoolean(True)
        tool_path = self.tool.Name + "."
        self.assertSameBounds(
            boolean.ViewObject.getBoundingBox(subname=tool_path, view=self.view),
            self.tool.Shape.BoundBox
        )
        self.assertSameBounds(
            self.body.ViewObject.getBoundingBox(
                subname=boolean.Name + "." + tool_path, view=self.view
            ), self.tool.Shape.BoundBox
        )

    def testRigidParentPlacementResultBounds(self):
        boolean = self.createBoolean()
        placement = App.Placement(App.Vector(31, -12, 7), App.Rotation(App.Vector(0, 0, 1), 37))
        self.body.Placement = placement
        self.tool.Placement = placement
        self.doc.recompute()
        self.pump()
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, 9992000, places=4)
        expected = App.BoundBox()
        for x in (0, 100):
            for y in (0, 100):
                for z in (0, 1000):
                    expected.add(placement.multVec(App.Vector(x, y, z)))
        self.assertSameBounds(self.sceneBounds(self.body), expected)
        self.assertSameBounds(self.body.ViewObject.getBoundingBox(view=self.view), expected)
        self.assertSameBounds(
            boolean.ViewObject.getBoundingBox(view=self.view, mat=placement.toMatrix()), expected
        )
        self.assertSameBounds(
            boolean.ViewObject.getBoundingBox(view=self.view, transform=False),
            App.BoundBox(0, 0, 0, 100, 100, 1000)
        )

    def testFullBodyBoxSelectionWithHiddenTool(self):
        boolean = self.createBoolean()
        self.boxSelectWholeBody()
        self.assertTrue(boolean.Shape.isValid())
        self.assertAlmostEqual(boolean.Shape.Volume, 9992000, places=4)

    def testOrdinaryBodyBoxSelectionControl(self):
        self.tool.ViewObject.hide()
        self.base.ViewObject.show()
        self.body.ViewObject.show()
        self.pump()
        self.boxSelectWholeBody()

    def boxSelectWholeBody(self):
        # This camera is independent of the defective view-provider bbox.
        self.view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 50 -1500 500 "
            "orientation 1 0 0 1.57079632679 focalDistance 1500 height 1300 }"
        )
        self.pump()
        viewport = self.view.graphicsView().viewport()
        points = []
        scale = viewport.devicePixelRatioF()
        _, height = self.view.getSize()
        for x in (0, 100):
            for y in (0, 100):
                for z in (0, 1000):
                    point = self.view.getPointOnScreen(App.Vector(x, y, z))
                    points.append(QtCore.QPoint(round(point[0] / scale),
                                                round((height - point[1] - 1) / scale)))
        start = QtCore.QPoint(min(p.x() for p in points) - 15, min(p.y() for p in points) - 15)
        end = QtCore.QPoint(max(p.x() for p in points) + 15, max(p.y() for p in points) + 15)
        self.assertTrue(viewport.rect().contains(start))
        self.assertTrue(viewport.rect().contains(end))
        # The dock overlay manager routes mouse events by the real cursor position.
        # Keep the cursor on the viewport so a transparent overlay panel under it
        # cannot forward these events a second time.
        QtGui.QCursor.setPos(viewport.mapToGlobal(start))
        Gui.Selection.clearSelection()
        Gui.runCommand("Std_BoxSelection")
        self.pump()

        def send(kind, point, button, buttons):
            event = QtGui.QMouseEvent(kind, QtCore.QPointF(point),
                                     QtCore.QPointF(viewport.mapToGlobal(point)),
                                     button, buttons, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(viewport, event)

        send(QtCore.QEvent.MouseMove, start, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        send(QtCore.QEvent.MouseButtonPress, start, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        send(QtCore.QEvent.MouseMove, QtCore.QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2), QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        send(QtCore.QEvent.MouseMove, end, QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        send(QtCore.QEvent.MouseButtonRelease, end, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.pump()
        selection = Gui.Selection.getSelectionEx("*", 0)
        self.assertEqual(len(selection), 1)
        self.assertEqual(selection[0].Object, self.body)
        self.assertEqual(tuple(selection[0].SubElementNames), ())
