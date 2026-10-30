# SPDX-License-Identifier: LGPL-2.1-or-later
"""New pads and pockets can start with the last accepted length (issue #29660)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesignGui
from PySide import QtCore, QtWidgets

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/PartDesign"


class TestRememberLastLengthGui(unittest.TestCase):
    def setUp(self):
        self.params = App.ParamGet(PARAM_PATH)
        self.saved_bools = {
            name: self.params.GetBool(name)
            for name in ("RememberLastLength",)
            if name in self.params.GetBools()
        }
        self.saved_floats = {
            name: self.params.GetFloat(name)
            for name in ("LastPadLength", "LastPocketLength")
            if name in self.params.GetFloats()
        }
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("PartDesignTestRememberLastLengthGui")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        App.setActiveDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.gui_doc.ActiveView.setActiveObject("pdbody", self.body)
        self.doc.recompute()

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog():
                    Gui.Control.closeDialog()
                App.closeDocument(self.doc.Name)
        finally:
            self.params.RemBool("RememberLastLength")
            for name, value in self.saved_bools.items():
                self.params.SetBool(name, value)
            for name in ("LastPadLength", "LastPocketLength"):
                self.params.RemFloat(name)
            for name, value in self.saved_floats.items():
                self.params.SetFloat(name, value)
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            Gui.updateGui()

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def setRemember(self, on):
        self.params.SetBool("RememberLastLength", on)
        self.params.RemFloat("LastPadLength")
        self.params.RemFloat("LastPocketLength")

    def makeSketch(self, x, y, z):
        sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.Placement = App.Placement(App.Vector(x, y, z), App.Rotation())
        points = [App.Vector(px, py, 0) for px, py in ((0, 0), (4, 0), (4, 4), (0, 4))]
        sketch.addGeometry(
            [Part.LineSegment(points[i], points[(i + 1) % 4]) for i in range(4)], False
        )
        self.doc.recompute()
        return sketch

    def makeBox(self):
        box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 20
        self.doc.recompute()

    def create(self, command, typeId, sketch):
        before = {obj.Name for obj in self.doc.Objects}
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, sketch.Name)
        Gui.runCommand(command, 0)
        self.pump()
        created = [
            obj for obj in self.doc.Objects if obj.Name not in before and obj.TypeId == typeId
        ]
        self.assertEqual(len(created), 1)
        self.assertTrue(Gui.Control.activeDialog())
        return created[0]

    def setPanelLength(self, length):
        edits = Gui.getMainWindow().findChildren(QtWidgets.QAbstractSpinBox, "lengthEdit")
        self.assertEqual(len(edits), 1)
        edits[0].setProperty("rawValue", length)
        self.pump()

    def accept(self):
        Gui.Control.activeTaskDialog().accept()
        self.pump()
        self.assertFalse(Gui.Control.activeDialog())

    def testDisabledKeepsBuiltInDefaults(self):
        self.setRemember(False)
        self.params.SetFloat("LastPadLength", 33.0)
        self.params.SetFloat("LastPocketLength", 3.0)
        self.makeBox()
        pad = self.create("PartDesign_Pad", "PartDesign::Pad", self.makeSketch(2, 2, 20))
        self.assertAlmostEqual(pad.Length.Value, 10.0)
        self.setPanelLength(7.0)
        self.accept()
        self.assertAlmostEqual(pad.Length.Value, 7.0)
        self.assertAlmostEqual(self.params.GetFloat("LastPadLength"), 33.0)
        pocket = self.create("PartDesign_Pocket", "PartDesign::Pocket", self.makeSketch(10, 10, 20))
        self.assertAlmostEqual(pocket.Length.Value, 5.0)
        self.accept()
        self.assertAlmostEqual(self.params.GetFloat("LastPocketLength"), 3.0)

    def testPadRemembersAcceptedLength(self):
        self.setRemember(True)
        pad = self.create("PartDesign_Pad", "PartDesign::Pad", self.makeSketch(0, 0, 0))
        self.assertAlmostEqual(pad.Length.Value, 10.0)
        self.setPanelLength(12345.25)
        self.accept()
        self.assertAlmostEqual(self.params.GetFloat("LastPadLength"), 12345.25)
        self.assertNotIn("LastPocketLength", self.params.GetFloats())

        pad2 = self.create("PartDesign_Pad", "PartDesign::Pad", self.makeSketch(10, 10, 0))
        self.assertAlmostEqual(pad2.Length.Value, 12345.25)
        Gui.Control.activeTaskDialog().reject()
        self.pump()

    def testPocketRemembersAcceptedLength(self):
        self.setRemember(True)
        self.makeBox()
        pocket = self.create("PartDesign_Pocket", "PartDesign::Pocket", self.makeSketch(2, 2, 20))
        self.assertAlmostEqual(pocket.Length.Value, 5.0)
        self.setPanelLength(2.5)
        self.accept()
        self.assertAlmostEqual(self.params.GetFloat("LastPocketLength"), 2.5)
        self.assertNotIn("LastPadLength", self.params.GetFloats())

        pocket2 = self.create(
            "PartDesign_Pocket", "PartDesign::Pocket", self.makeSketch(10, 10, 20)
        )
        self.assertAlmostEqual(pocket2.Length.Value, 2.5)
        Gui.Control.activeTaskDialog().reject()
        self.pump()
        pad = self.create("PartDesign_Pad", "PartDesign::Pad", self.makeSketch(2, 10, 20))
        self.assertAlmostEqual(pad.Length.Value, 10.0)
