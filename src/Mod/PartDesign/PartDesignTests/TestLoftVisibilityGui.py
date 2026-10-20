# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Loft task closure restores an intermediate feature's visibility."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
import Sketcher
from PySide import QtCore, QtWidgets


class TestLoftVisibilityGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("LoftEditVisibility")
        self.gui_doc = Gui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.view = self.gui_doc.activeView()
        self.view.setActiveObject("pdbody", self.body)
        self.messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                self.messages.append(modal.text())
                modal.reject()

        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                if self.doc.HasPendingTransaction:
                    self.doc.abortTransaction()
                App.closeDocument(self.doc.Name)
        finally:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def visibility(self, obj):
        return (obj.ViewObject.Visibility, obj.ViewObject.isVisible())

    def sectionSketch(self, name, height):
        sketch = self.body.newObject("Sketcher::SketchObject", name)
        sketch.Placement.Base = App.Vector(0, 0, height)
        points = [App.Vector(x, y, 0) for x, y in ((0, 0), (2, 0), (2, 3), (0, 3))]
        sketch.addGeometry([Part.LineSegment(points[index], points[(index + 1) % 4])
                            for index in range(4)], False)
        return sketch

    def fixture(self, downstream):
        profile = self.sectionSketch("Profile", 0)
        section = self.sectionSketch("Section", 10)
        extra = self.sectionSketch("ExtraSection", 20)
        loft = self.body.newObject("PartDesign::AdditiveLoft", "Loft")
        loft.Profile = profile
        loft.Sections = [section]
        self.doc.recompute()
        self.assertFalse(loft.Shape.isNull())
        self.assertTrue(loft.Shape.isValid())
        self.assertAlmostEqual(loft.Shape.Volume, 60)
        if downstream:
            tip = self.body.newObject("PartDesign::AdditiveBox", "DownstreamBox")
            tip.Length = tip.Width = 1
            tip.Height = 2
            tip.Placement.Base = App.Vector(0.5, 1, 9)
            self.doc.recompute()
            self.assertEqual(tip.BaseFeature, loft)
            self.assertFalse(tip.Shape.isNull())
            self.assertTrue(tip.Shape.isValid())
            self.assertAlmostEqual(tip.Shape.Volume, 61)
        else:
            tip = loft
        self.assertEqual(self.body.Tip, tip)
        for sketch in (profile, section, extra):
            sketch.ViewObject.hide()
        self.body.ViewObject.show()
        if downstream:
            loft.ViewObject.hide()
        tip.ViewObject.show()
        self.pump()
        self.assertEqual(self.visibility(loft), (not downstream, not downstream),
                         "The fixture must establish actual and persistent initial Loft visibility")
        self.assertEqual(self.visibility(tip), (True, True))
        return loft, tip, extra

    def checkClosure(self, accept, add=True, downstream=True):
        loft, tip, extra = self.fixture(downstream)
        old_sections = loft.Sections
        original_loft_visibility = self.visibility(loft)
        original_tip_visibility = self.visibility(tip)
        self.doc.openTransaction("Edit Loft")
        self.assertTrue(self.gui_doc.setEdit(loft.Name))
        self.pump()
        self.assertIsNotNone(Gui.Control.activeTaskDialog())
        if add:
            button = Gui.getMainWindow().findChild(QtWidgets.QToolButton, "buttonRefAdd")
            self.assertIsNotNone(button)
            self.assertTrue(button.isEnabled())
            button.click()
            self.pump()
            self.assertTrue(button.isChecked())
            Gui.Selection.addSelection(self.doc.Name, extra.Name)
            self.pump()
            self.assertEqual([entry[0] for entry in loft.Sections],
                             [old_sections[0][0], extra],
                             "The ordinary Add Section interaction must update the real Loft")
            self.assertTrue(loft.Shape.isValid())
            self.assertAlmostEqual(loft.Shape.Volume, 120)
        task = Gui.Control.activeTaskDialog()
        if accept:
            task.accept()
        else:
            task.reject()
        self.pump()
        self.assertIsNone(self.gui_doc.getInEdit())
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))
        self.assertEqual(self.messages, [])
        if accept and add:
            self.assertEqual([entry[0] for entry in loft.Sections],
                             [old_sections[0][0], extra])
        else:
            self.assertEqual(loft.Sections, old_sections)
        self.doc.recompute()
        self.assertTrue(loft.Shape.isValid())
        self.assertTrue(tip.Shape.isValid())
        self.assertEqual(self.body.Tip, tip)
        expected_loft_volume = 120 if accept and add else 60
        self.assertAlmostEqual(loft.Shape.Volume, expected_loft_volume)
        expected_tip_volume = (expected_loft_volume if accept and add or not downstream
                               else expected_loft_volume + 1)
        self.assertAlmostEqual(tip.Shape.Volume, expected_tip_volume)
        self.assertEqual(self.visibility(loft), original_loft_visibility,
                         "Closing an intermediate Loft must restore its original scene visibility")
        self.assertEqual(self.visibility(tip), original_tip_visibility,
                         "Closing the Loft must preserve the previously visible Tip")

    def testHiddenIntermediateAddAccept(self):
        self.checkClosure(True)

    def testHiddenIntermediateAddReject(self):
        self.checkClosure(False)

    def testHiddenIntermediateUnchangedAcceptControl(self):
        self.checkClosure(True, add=False)

    def testHiddenIntermediateUnchangedRejectControl(self):
        self.checkClosure(False, add=False)

    def testVisibleTipAddAcceptControl(self):
        self.checkClosure(True, downstream=False)

    def testVisibleTipAddRejectControl(self):
        self.checkClosure(False, downstream=False)
