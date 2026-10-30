# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Hole task panel shows the thread pitch of standard profiles (issue #15731)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesignGui
import TestSketcherApp
from PySide import QtWidgets


class TestHolePitchGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("PartDesignTestHolePitchGui")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        body = self.doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 20
        sketch = body.newObject("Sketcher::SketchObject", "SketchHole")
        sketch.AttachmentSupport = (self.doc.getObject("XY_Plane"), [""])
        sketch.MapMode = "FlatFace"
        sketch.MapReversed = True
        TestSketcherApp.CreateCircleSketch(sketch, (10, 10), 1)
        self.doc.recompute()
        self.hole = body.newObject("PartDesign::Hole", "Hole")
        self.hole.Profile = sketch
        self.hole.ThreadType = "ISOMetricProfile"
        self.hole.ThreadSize = "M6x1.0"
        self.doc.recompute()
        self.assertTrue(self.gui_doc.setEdit(self.hole.Name))
        Gui.updateGui()

    def tearDown(self):
        try:
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            Gui.updateGui()

    def widget(self, cls, name):
        widgets = Gui.getMainWindow().findChildren(cls, name)
        self.assertEqual(len(widgets), 1, name)
        return widgets[0]

    def pitchWidget(self):
        return self.widget(QtWidgets.QAbstractSpinBox, "ThreadPitch")

    def selectCombo(self, name, text):
        combo = self.widget(QtWidgets.QComboBox, name)
        index = combo.findText(text)
        self.assertGreaterEqual(index, 0, text)
        combo.setCurrentIndex(index)
        Gui.updateGui()

    def assertPitch(self, expected):
        pitch = self.pitchWidget()
        self.assertTrue(pitch.isVisibleTo(pitch.parentWidget()))
        # Display only: a disabled field, since QuantitySpinBox drops readOnly on resize
        self.assertFalse(pitch.isEnabled())
        self.assertAlmostEqual(pitch.property("rawValue"), expected)

    def testPitchFollowsSize(self):
        self.assertPitch(1.0)
        self.selectCombo("ThreadSize", "M8x1.25")
        self.assertEqual(self.hole.ThreadSize, "M8x1.25")
        self.assertPitch(1.25)

    def testPitchFollowsProfile(self):
        self.selectCombo("ThreadType", QtWidgets.QApplication.translate(
            "PartDesignGui::TaskHoleParameters", "ISO metric fine"))
        self.assertEqual(self.hole.ThreadType, "ISOMetricFineProfile")
        self.selectCombo("ThreadSize", "M8x1.0")
        self.assertPitch(1.0)
        self.selectCombo("ThreadType", QtWidgets.QApplication.translate(
            "PartDesignGui::TaskHoleParameters", "UTS coarse"))
        self.selectCombo("ThreadSize", "1/4")
        self.assertPitch(25.4 / 20)

    def testPitchFollowsPropertyChange(self):
        self.hole.ThreadSize = "M8x1.25"
        Gui.updateGui()
        self.assertPitch(1.25)

    def testPitchHiddenWithoutProfile(self):
        self.selectCombo("ThreadType", QtWidgets.QApplication.translate(
            "PartDesignGui::TaskHoleParameters", "None"))
        self.assertEqual(self.hole.ThreadType, "None")
        pitch = self.pitchWidget()
        self.assertFalse(pitch.isVisibleTo(pitch.parentWidget()))
