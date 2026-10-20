# SPDX-License-Identifier: LGPL-2.1-or-later
"""A real Sketcher datum modal must release navigation pointer state (#33403)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher
from pivy import coin
from PySide import QtCore, QtGui, QtWidgets


class TestSketchDatumNavigationGui(unittest.TestCase):

    def pump(self, milliseconds=120):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        self.view.redraw()
        Gui.updateGui()

    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous is not None else None
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("InventorDatumModal")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(), App.Vector(20, 0, 0)), False)
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 20))
        self.sketch.setLabelPosition(0, 0)
        self.sketch.setLabelDistance(0, 5)
        self.doc.recompute()
        self.view = Gui.activeDocument().activeView()
        self.original_navigation = self.view.getNavigationType()
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        self.view.viewTop()
        self.view.fitAll()
        self.pump()
        self.viewport = self.view.graphicsView().viewport()
        self.manager = self.view.getViewer().getSoRenderManager()

    def tearDown(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        if dialog is not None:
            dialog.reject()
        # A failed fixture can leave a deferred second DOWN in navigation.
        # Its cleanup UP can replay that DOWN and open the datum modal, so keep
        # a modal closer active while draining the gesture and leaving edit.
        closer = QtCore.QTimer(Gui.getMainWindow())
        def rejectPendingModal():
            pending = QtWidgets.QApplication.activeModalWidget()
            if pending is not None:
                pending.reject()
        closer.timeout.connect(rejectPendingModal)
        closer.start(25)
        try:
            self.send(self.viewport, QtCore.QEvent.MouseButtonRelease,
                      QtCore.QPoint(20, 20), QtCore.Qt.LeftButton, QtCore.Qt.NoButton,
                      QtCore.Qt.NoModifier)
            self.view.setNavigationType(self.original_navigation)
            Gui.activeDocument().resetEdit()
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
        finally:
            closer.stop()
            closer.deleteLater()
            if self.previous_workbench is not None:
                Gui.activateWorkbench(self.previous_workbench)

    @staticmethod
    def send(target, kind, point, button, buttons, modifiers):
        event = QtGui.QMouseEvent(kind, QtCore.QPointF(point),
            QtCore.QPointF(target.mapToGlobal(point)), button, buttons, modifiers)
        QtWidgets.QApplication.sendEvent(target, event)

    def labelPoint(self):
        region = self.manager.getViewportRegion()
        size = region.getViewportSizePixels()
        width, height = int(size[0]), int(size[1])
        center = self.view.getPointOnScreen(App.Vector(10, 5, 0))
        for radius in (0, 3, 6, 10, 16, 24, 36, 50):
            for dx in range(-radius, radius + 1, 2):
                for dy in range(-radius, radius + 1, 2):
                    x, y = int(center[0] + dx), int(center[1] + dy)
                    if not (0 <= x < width and 0 <= y < height):
                        continue
                    pick = coin.SoRayPickAction(region)
                    pick.setPoint(coin.SbVec2s(x, y))
                    pick.setRadius(1.0)
                    pick.apply(self.manager.getSceneGraph())
                    picked = pick.getPickedPoint()
                    if picked is None:
                        continue
                    path = coin.SoFullPath.fromSoPath(picked.getPath())
                    types = [str(path.getNode(i).getTypeId().getName())
                             for i in range(path.getLength())]
                    if "SoDatumLabel" in types:
                        point = QtCore.QPoint(round(x * self.viewport.width() / width),
                            round((height - 1 - y) * self.viewport.height() / height))
                        return point
        self.fail("Could not ray-pick a real SoDatumLabel; no navigation claim")

    def orientation(self):
        return tuple(float(value) for value in self.manager.getCamera().orientation.getValue().getValue())

    def checkModal(self, navigation, accept, restore_release=False):
        self.view.setNavigationType(navigation)
        self.pump()
        point = self.labelPoint()
        self.pump(QtWidgets.QApplication.doubleClickInterval() + 50)
        modifier = QtCore.Qt.ShiftModifier
        self.send(self.viewport, QtCore.QEvent.MouseMove, point,
                  QtCore.Qt.NoButton, QtCore.Qt.NoButton, modifier)
        self.send(self.viewport, QtCore.QEvent.MouseButtonPress, point,
                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, modifier)
        self.send(self.viewport, QtCore.QEvent.MouseButtonRelease, point,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton, modifier)
        errors = []
        handled = []
        timer = QtCore.QTimer(Gui.getMainWindow())

        def finish():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                return
            timer.stop()
            handled.append(True)
            try:
                editor = dialog.findChild(QtWidgets.QWidget, "labelEdit")
                self.assertIsNotNone(editor, "Actual viewport double-click must open the datum editor")
                self.assertTrue(editor.property("binding"))
                self.assertAlmostEqual(editor.property("rawValue"), 20)
                # Mouse release belongs to the modal dialog, exactly as when
                # the second physical click opens the editor on mouse-down.
                self.send(dialog, QtCore.QEvent.MouseButtonRelease, QtCore.QPoint(5, 5),
                          QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
                buttons = dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
                self.assertIsNotNone(buttons)
                role = QtWidgets.QDialogButtonBox.Ok if accept else QtWidgets.QDialogButtonBox.Cancel
                buttons.button(role).click()
            except BaseException as error:
                errors.append(error)
                dialog.reject()

        timer.timeout.connect(finish)
        timer.start(25)
        try:
            self.send(self.viewport, QtCore.QEvent.MouseButtonPress, point,
                      QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, modifier)
            if not handled:
                # Current NavigationStyle postpones a second click's DOWN
                # until UP. Complete that native pointer stream. If the
                # modal already opened on DOWN, its timer consumed the UP and
                # this viewport release must not mask a possible stuck button.
                self.send(self.viewport, QtCore.QEvent.MouseButtonRelease, point,
                          QtCore.Qt.LeftButton, QtCore.Qt.NoButton, modifier)
        finally:
            timer.stop()
            timer.deleteLater()
        if errors:
            raise errors[0]
        self.assertTrue(handled, "A real dimension modal must open before testing lost release")
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.pump()
        if restore_release:
            self.send(self.viewport, QtCore.QEvent.MouseButtonRelease, point,
                      QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        before = self.orientation()
        for offset in (QtCore.QPoint(15, 8), QtCore.QPoint(45, 25), QtCore.QPoint(80, 40)):
            self.send(self.viewport, QtCore.QEvent.MouseMove, point + offset,
                      QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
            self.pump(40)
        after = self.orientation()
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 20)
        self.assertAlmostEqual((self.sketch.Geometry[0].EndPoint -
                                self.sketch.Geometry[0].StartPoint).Length, 20)
        self.assertAlmostEqual(self.sketch.getLabelDistance(0), 5)
        self.assertLessEqual(max(abs(a-b) for a, b in zip(before, after)), 1e-6,
                             "Unpressed pointer movement after a datum dialog must not rotate the view")

    def testCadAcceptControl(self):
        self.checkModal("Gui::CADNavigationStyle", True)

    def testCadCancelControl(self):
        self.checkModal("Gui::CADNavigationStyle", False)

    def testInventorAccept(self):
        self.checkModal("Gui::InventorNavigationStyle", True)

    def testInventorCancel(self):
        self.checkModal("Gui::InventorNavigationStyle", False)

    def testInventorViewportReleaseControl(self):
        self.checkModal("Gui::InventorNavigationStyle", True, restore_release=True)

    def testInventorFreshRotationAfterModalControl(self):
        # The explicit viewport release makes this a positive control on the
        # original implementation too. A new ordinary drag must still rotate
        # after the modal boundary, without modifying sketch geometry.
        self.checkModal("Gui::InventorNavigationStyle", True, restore_release=True)
        start = QtCore.QPoint(140, 90)
        self.assertTrue(self.viewport.rect().contains(start + QtCore.QPoint(220, 110)))
        before = self.orientation()
        self.send(self.viewport, QtCore.QEvent.MouseButtonPress, start,
                  QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        for offset in (QtCore.QPoint(50, 25), QtCore.QPoint(130, 65), QtCore.QPoint(220, 110)):
            self.send(self.viewport, QtCore.QEvent.MouseMove, start + offset,
                      QtCore.Qt.NoButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
            self.pump(40)
        after = self.orientation()
        self.send(self.viewport, QtCore.QEvent.MouseButtonRelease, start + offset,
                  QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
        self.assertGreater(max(abs(a-b) for a,b in zip(before,after)), 0.01,
                           "A fresh normal Inventor drag must still rotate after the dialog")
        self.assertAlmostEqual(self.sketch.Constraints[0].Value, 20)
        self.assertAlmostEqual((self.sketch.Geometry[0].EndPoint -
                                self.sketch.Geometry[0].StartPoint).Length, 20)
