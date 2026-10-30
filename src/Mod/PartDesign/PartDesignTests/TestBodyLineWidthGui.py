# SPDX-License-Identifier: LGPL-2.1-or-later
"""New Part Design features inherit the line width and point size of their body."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
import Sketcher
from PySide import QtCore


class TestBodyLineWidthGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("BodyLineWidthGui")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        App.setActiveDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.gui_doc.ActiveView.setActiveObject("pdbody", self.body)
        self.doc.recompute()

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.gui_doc.getInEdit():
                self.gui_doc.resetEdit()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def setBodyStyle(self):
        self.body.ViewObject.LineWidth = 5
        self.body.ViewObject.PointSize = 7

    def assertBodyStyle(self, feature):
        self.assertEqual(feature.ViewObject.LineWidth, 5)
        self.assertEqual(feature.ViewObject.PointSize, 7)

    def closeTask(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        self.pump()

    def testAdditivePrimitiveUsesBodyStyle(self):
        # https://github.com/FreeCAD/FreeCAD/issues/31068
        self.setBodyStyle()
        Gui.runCommand("PartDesign_CompPrimitiveAdditive", 0)
        self.pump()
        boxes = [obj for obj in self.body.Group if obj.TypeId == "PartDesign::AdditiveBox"]
        self.assertEqual(len(boxes), 1)
        self.assertBodyStyle(boxes[0])
        self.closeTask()

    def testPadUsesBodyStyle(self):
        box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        self.doc.recompute()
        self.setBodyStyle()
        self.assertBodyStyle(box)

        sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.Placement = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        points = [App.Vector(x, y, 0) for x, y in ((1, 1), (4, 1), (4, 4), (1, 4))]
        sketch.addGeometry(
            [Part.LineSegment(points[i], points[(i + 1) % 4]) for i in range(4)], False
        )
        self.doc.recompute()

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, sketch.Name)
        Gui.runCommand("PartDesign_Pad", 0)
        self.pump()
        pads = [obj for obj in self.body.Group if obj.TypeId == "PartDesign::Pad"]
        self.assertEqual(len(pads), 1)
        self.assertBodyStyle(pads[0])
        self.closeTask()
