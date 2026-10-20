# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI framebuffer regressions for Sketcher rubberbands (FreeCAD/FreeCAD#29122).

Cover interrupted-edit cleanup and actual Blender pan button release orders,
including fresh selection interactions and camera/geometry preservation.
"""

from pathlib import Path
import os
import tempfile
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from PySide import QtCore, QtGui


class TestSketchRubberbandGui(unittest.TestCase):
    def setUp(self):
        self.output = Path(os.environ.get("FC_VISUAL_OUT_DIR", str(
            Path(tempfile.gettempdir()) / "FreeCADTesting" / "SketchRubberbandGui"))) / str(os.getpid())
        self.output.mkdir(parents=True, exist_ok=True)
        self.doc = App.newDocument("SketchRubberbandReopen")
        self.sketch = self.makeSketch("Sketch")
        self.other = self.makeSketch("OtherSketch")
        self.doc.recompute()
        self.view = Gui.activeDocument().activeView()
        self.viewer = self.view.getViewer()
        self.viewer.setEnabledNaviCube(False)
        self.view.setAxisCross(False)
        self.viewer.setGradientBackground("NONE")
        self.viewer.setBackgroundColor(0.15, 0.15, 0.15)
        self.view.setNavigationType("Gui::CADNavigationStyle")
        self.start = QtCore.QPoint(130, 55)
        self.end = QtCore.QPoint(40, 150)
        self.enter(self.sketch)

    def tearDown(self):
        Gui.activeDocument().resetEdit()
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def makeSketch(self, name):
        # Offset the test edge from the axes for unambiguous fresh-click controls.
        sketch = self.doc.addObject("Sketcher::SketchObject", name)
        sketch.addGeometry(Part.LineSegment(App.Vector(-10, 3, 0), App.Vector(10, 3, 0)), False)
        sketch.ViewObject.ShowGrid = False
        return sketch

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(160, loop.quit)
        loop.exec_()
        self.view.redraw()
        Gui.updateGui()

    def enter(self, sketch):
        self.assertTrue(Gui.activeDocument().setEdit(sketch.Name))
        self.pump()
        self.viewport = self.view.graphicsView().viewport()

    def send(self, kind, point, button, buttons):
        event = QtGui.QMouseEvent(kind, QtCore.QPointF(point),
            QtCore.QPointF(self.viewport.mapToGlobal(point)), button, buttons,
            QtCore.Qt.NoModifier)
        QtGui.QApplication.sendEvent(self.viewport, event)

    def move(self, point, buttons):
        self.send(QtCore.QEvent.MouseMove, point, QtCore.Qt.NoButton, buttons)

    def capture(self, name):
        self.pump()
        image = self.viewer.grabFramebuffer()
        self.assertFalse(image.isNull())
        image.save(str(self.output / (self._testMethodName + "-" + name + ".png")))
        # This corner is empty geometry and lies inside the deliberate drag.
        # Normalize only this fixed logical-widget crop for high-DPI captures.
        sx = image.width() / self.viewport.width()
        sy = image.height() / self.viewport.height()
        rectangle = QtCore.QRect(round(20 * sx), round(35 * sy),
                                 round(125 * sx), round(130 * sy))
        return image.copy(rectangle).scaled(125, 130)

    @staticmethod
    def different(a, b):
        return sum(max(abs(a.pixelColor(x, y).red() - b.pixelColor(x, y).red()),
                       abs(a.pixelColor(x, y).green() - b.pixelColor(x, y).green()),
                       abs(a.pixelColor(x, y).blue() - b.pixelColor(x, y).blue())) > 15
                   for y in range(130) for x in range(125))

    def startSelection(self):
        baseline = self.capture("fresh")
        self.send(QtCore.QEvent.MouseButtonPress, self.start,
                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.move(QtCore.QPoint(100, 90), QtCore.Qt.LeftButton)
        self.move(self.end, QtCore.Qt.LeftButton)
        active = self.capture("active")
        changed = self.different(baseline, active)
        self.assertGreater(changed, 1000, "Control must show an actual Sketcher rubberband")
        return baseline

    def closeAndRelease(self):
        Gui.activeDocument().resetEdit()
        self.pump()
        # Release after the sketch handler and its graphics item have left the
        # viewer; this clears navigation state without completing that sketch's
        # interrupted selection operation.
        self.send(QtCore.QEvent.MouseButtonRelease, self.end,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.pump()

    def assertFreshOverlay(self, baseline, name):
        current = self.capture(name)
        stable = self.capture(name + "-stable")
        self.assertEqual(self.different(current, stable), 0,
                         "Freshly captured corner must be stable")
        changed = self.different(baseline, current)
        self.assertLessEqual(changed, 16,
                             "A closed selection must not leave its rectangle in a later edit")

    def testCompletedSelectionDoesNotReappear(self):
        baseline = self.startSelection()
        self.send(QtCore.QEvent.MouseButtonRelease, self.end,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.closeAndRelease()
        self.enter(self.sketch)
        self.assertFreshOverlay(baseline, "completed-reopen")

    def testInterruptedSelectionDoesNotReappear(self):
        baseline = self.startSelection()
        self.closeAndRelease()
        self.enter(self.sketch)
        self.assertFreshOverlay(baseline, "interrupted-reopen")

    def testOtherSketchDoesNotInheritInterruptedSelection(self):
        baseline = self.startSelection()
        self.closeAndRelease()
        self.enter(self.other)
        self.assertFreshOverlay(baseline, "other-sketch")

    def reopen(self, completed):
        self.startSelection()
        if completed:
            self.send(QtCore.QEvent.MouseButtonRelease, self.end,
                      QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.closeAndRelease()
        self.enter(self.sketch)
        Gui.Selection.clearSelection()
        self.pump()

    def selected(self):
        return {name for selection in Gui.Selection.getSelectionEx()
                for name in selection.SubElementNames}

    def screenPoint(self, vector):
        point = self.view.getPointOnScreen(vector)
        _, height = self.view.getSize()
        scale = self.viewport.devicePixelRatioF()
        return QtCore.QPoint(round(point[0] / scale),
                             round((height - point[1] - 1) / scale))

    def normalPointerMovement(self, completed):
        self.reopen(completed)
        before = self.capture("before-no-button-move")
        self.move(QtCore.QPoint(110, 125), QtCore.Qt.NoButton)
        after = self.capture("after-no-button-move")
        changed = self.different(before, after)
        self.assertEqual(self.selected(), set())
        self.assertEqual(changed, 0,
                         "Moving an unpressed pointer must not continue an old box")

    def freshEdgeClick(self, completed):
        self.reopen(completed)
        point = self.screenPoint(App.Vector(5, 3, 0))
        self.move(point, QtCore.Qt.NoButton)
        self.send(QtCore.QEvent.MouseButtonPress, point,
                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.send(QtCore.QEvent.MouseButtonRelease, point,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.pump()
        selected = self.selected()
        self.assertEqual(selected, {"Edge1"},
                         "The first fresh click must select the clicked edge alone")
        self.assertEqual(self.sketch.Geometry[0].StartPoint, App.Vector(-10, 3, 0))
        self.assertEqual(self.sketch.Geometry[0].EndPoint, App.Vector(10, 3, 0))

    def boxImage(self, name, rectangle):
        self.pump()
        image = self.viewer.grabFramebuffer()
        self.assertFalse(image.isNull())
        image.save(str(self.output / (self._testMethodName + "-" + name + ".png")))
        scale = self.viewport.devicePixelRatioF()
        crop = QtCore.QRect(round(rectangle.x() * scale), round(rectangle.y() * scale),
                            round(rectangle.width() * scale), round(rectangle.height() * scale))
        return image.copy(crop).scaled(rectangle.width(), rectangle.height())

    def freshBoxSelection(self, completed):
        self.reopen(completed)
        start = self.screenPoint(App.Vector(-10, 3, 0)) - QtCore.QPoint(25, 35)
        end = self.screenPoint(App.Vector(10, 3, 0)) + QtCore.QPoint(25, 35)
        self.assertTrue(self.viewport.rect().contains(start))
        self.assertTrue(self.viewport.rect().contains(end))
        rectangle = QtCore.QRect(start, end).normalized()
        self.move(start, QtCore.Qt.NoButton)
        before = self.boxImage("fresh-box-before", rectangle)
        self.send(QtCore.QEvent.MouseButtonPress, start,
                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.move(QtCore.QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2),
                  QtCore.Qt.LeftButton)
        self.move(end, QtCore.Qt.LeftButton)
        active = self.boxImage("fresh-box-active", rectangle)
        changed = sum(max(abs(before.pixelColor(x, y).red() - active.pixelColor(x, y).red()),
                          abs(before.pixelColor(x, y).green() - active.pixelColor(x, y).green()),
                          abs(before.pixelColor(x, y).blue() - active.pixelColor(x, y).blue())) > 15
                      for y in range(before.height()) for x in range(before.width()))
        self.send(QtCore.QEvent.MouseButtonRelease, end,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.pump()
        selected = self.selected()
        self.assertIn("Edge1", selected)
        self.assertGreater(changed, 1000,
                           "A fresh selection must render a live rubberband after reopening")
        self.assertEqual(self.sketch.Geometry[0].StartPoint, App.Vector(-10, 3, 0))
        self.assertEqual(self.sketch.Geometry[0].EndPoint, App.Vector(10, 3, 0))

    def testCompletedNormalPointerMovement(self):
        self.normalPointerMovement(True)

    def testInterruptedNormalPointerMovement(self):
        self.normalPointerMovement(False)

    def testCompletedFreshEdgeClick(self):
        self.freshEdgeClick(True)

    def testInterruptedFreshEdgeClick(self):
        self.freshEdgeClick(False)

    def testCompletedFreshBoxSelection(self):
        self.freshBoxSelection(True)

    def testInterruptedFreshBoxSelection(self):
        self.freshBoxSelection(False)

    def cameraPosition(self):
        position = self.viewer.getSoRenderManager().getCamera().position.getValue()
        return tuple(float(position[i]) for i in range(3))

    def checkPan(self, right_first=False, release_right_first=False, selection_move=False):
        self.view.setNavigationType("Gui::BlenderNavigationStyle")
        self.pump()
        # Avoid a previous case's shared native double-click candidate being
        # mistaken for the first press in this independent pan gesture.
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(QtGui.QApplication.doubleClickInterval() + 50, loop.quit)
        loop.exec_()
        baseline = self.capture("before-pan")
        camera_before = self.cameraPosition()
        both = QtCore.Qt.LeftButton | QtCore.Qt.RightButton
        first, second = ((QtCore.Qt.RightButton, QtCore.Qt.LeftButton) if right_first
                         else (QtCore.Qt.LeftButton, QtCore.Qt.RightButton))
        self.send(QtCore.QEvent.MouseButtonPress, self.start, first, first)
        if selection_move:
            self.assertFalse(right_first)
            self.move(self.start + QtCore.QPoint(15, 10), QtCore.Qt.LeftButton)
            self.move(self.start + QtCore.QPoint(25, 15), QtCore.Qt.LeftButton)
        self.send(QtCore.QEvent.MouseButtonPress, self.start, second, both)
        midpoint = self.start + QtCore.QPoint(45, 30)
        end = self.start + QtCore.QPoint(90, 55)
        self.move(midpoint, both)
        self.move(end, both)
        self.pump()
        camera_after = self.cameraPosition()
        release1, release2 = ((QtCore.Qt.RightButton, QtCore.Qt.LeftButton) if release_right_first
                             else (QtCore.Qt.LeftButton, QtCore.Qt.RightButton))
        self.send(QtCore.QEvent.MouseButtonRelease, end, release1, release2)
        self.send(QtCore.QEvent.MouseButtonRelease, end, release2, QtCore.Qt.NoButton)
        released = self.capture("buttons-released")
        # Two unpressed movements exercise both the start-box and active-box
        # states without fabricating an extra press or resetting sketch edit.
        self.move(QtCore.QPoint(100, 90), QtCore.Qt.NoButton)
        self.move(QtCore.QPoint(40, 150), QtCore.Qt.NoButton)
        moved = self.capture("unpressed-after-pan")
        released_diff = self.different(baseline, released)
        moved_diff = self.different(baseline, moved)
        selected = {name for selection in Gui.Selection.getSelectionEx()
                    for name in selection.SubElementNames}
        self.assertGreater(max(abs(a-b) for a,b in zip(camera_before,camera_after)), 0.001,
                           "Control must execute a real Blender pan, not merely a box selection")
        self.assertEqual(selected, set())
        self.assertEqual(self.sketch.Geometry[0].StartPoint, App.Vector(-10, 3, 0))
        self.assertEqual(self.sketch.Geometry[0].EndPoint, App.Vector(10, 3, 0))
        self.assertLessEqual(released_diff, 16,
                             "Releasing both pan buttons must not leave a sketch box")
        self.assertLessEqual(moved_diff, 16,
                             "Unpressed movement after panning must not start a sketch box")

    def testLeftThenRightReleaseLeftFirst(self):
        self.checkPan()

    def testLeftThenRightReleaseRightFirst(self):
        self.checkPan(release_right_first=True)

    def testRightThenLeftReleaseLeftFirst(self):
        self.checkPan(right_first=True)

    def testRightThenLeftReleaseRightFirst(self):
        self.checkPan(right_first=True, release_right_first=True)

    def testMovedLeftSelectionThenPanReleaseLeftFirst(self):
        self.checkPan(selection_move=True)

    def testMovedLeftSelectionThenPanReleaseRightFirst(self):
        self.checkPan(selection_move=True, release_right_first=True)

    def testOrdinaryLeftBoxSelectionControl(self):
        self.view.setNavigationType("Gui::BlenderNavigationStyle")
        self.pump()
        self.startSelection()
        self.send(QtCore.QEvent.MouseButtonRelease, self.end,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        cleared = self.capture("ordinary-selection-ended")
        self.move(QtCore.QPoint(110, 125), QtCore.Qt.NoButton)
        self.assertEqual(self.different(cleared, self.capture("ordinary-unpressed-move")), 0)
