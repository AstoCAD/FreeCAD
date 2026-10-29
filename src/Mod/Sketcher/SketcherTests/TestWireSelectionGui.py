# SPDX-License-Identifier: LGPL-2.1-or-later
"""Double-click wire selection must stay on geometry of the clicked kind (#32248)."""

import FreeCAD as App
import Part
from PySide import QtCore, QtGui

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestWireSelectionGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("WireSelectionTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        points = [(-10, 5), (0, 5), (10, 5), (10, -5), (-10, -5)]
        construction = [False, False, True, False]
        for i, isConstruction in enumerate(construction):
            start, end = points[i], points[i + 1]
            self.sketch.addGeometry(
                Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), isConstruction
            )
        self.sketch.ViewObject.ShowGrid = False
        self.doc.recompute()
        self.view = Gui.activeDocument().activeView()
        self.view.setNavigationType("Gui::CADNavigationStyle")
        self.view.viewTop()
        self.view.fitAll()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)
        self.viewport = self.view.graphicsView().viewport()

    def screenPoint(self, vector):
        point = self.view.getPointOnScreen(vector)
        _, height = self.view.getSize()
        scale = self.viewport.devicePixelRatioF()
        return QtCore.QPoint(round(point[0] / scale), round((height - point[1] - 1) / scale))

    def send(self, kind, point, button, buttons):
        event = QtGui.QMouseEvent(
            kind,
            QtCore.QPointF(point),
            QtCore.QPointF(self.viewport.mapToGlobal(point)),
            button,
            buttons,
            QtCore.Qt.NoModifier,
        )
        QtGui.QApplication.sendEvent(self.viewport, event)

    def leftClick(self, point):
        self.send(QtCore.QEvent.MouseButtonPress, point, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self.send(QtCore.QEvent.MouseButtonRelease, point, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self.flush_gui(30)

    def selected(self):
        return {
            name
            for selection in Gui.Selection.getSelectionEx(self.doc.Name)
            for name in selection.SubElementNames
        }

    def testDoubleClickStopsAtConstruction(self):
        Gui.Selection.clearSelection()
        point = self.screenPoint(App.Vector(-5, 5, 0))
        self.send(QtCore.QEvent.MouseMove, point, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self.flush_gui(100)
        self.leftClick(point)
        self.assertEqual(self.selected(), {"Edge1"})
        self.leftClick(point)
        self.flush_gui(100)
        # Edge3 is construction: neither it nor the normal Edge4 beyond it belong
        # to the wire of Edge1.
        self.assertEqual(self.selected(), {"Edge1", "Edge2"})
