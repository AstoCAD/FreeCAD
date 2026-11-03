# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Move Feature acceptance, including the established Pad/Sketch workflow."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestMoveFeatureSourceTipGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = None

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc is not None and self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def runEstablishedPadWorkflow(self, selection_names=None):
        import TestPartDesignGui

        workflow = TestPartDesignGui.PartDesignGuiTestCases("testMoveSingleFeature")
        workflow.setUp()
        self.doc = workflow.Doc
        self.doc.UndoMode = 1
        if selection_names is None:
            workflow.testMoveSingleFeature()
        else:
            Gui.Selection.clearSelection(self.doc.Name)
            workflow.movePadToBody(selection_names)
        return workflow.BodySource, workflow.BodyTarget, workflow.Sketch, workflow.Pad

    def assertSourceTipCleared(self, source, moved):
        with self.subTest(invariant="Source Tip cleared"):
            self.assertIsNone(source.Tip, "The empty source Body must not retain the moved Tip")
        for feature in moved:
            with self.subTest(invariant="No stale source OutList", feature=feature.Name):
                self.assertNotIn(feature, source.OutList)

    def testEstablishedPadMoveClearsSourceTip(self):
        source, target, sketch, pad = self.runEstablishedPadWorkflow()
        self.assertEqual(target.Tip, pad)
        self.assertAlmostEqual(target.Shape.Volume, 4000)
        self.assertSourceTipCleared(source, [sketch, pad])

    def testEstablishedPadMoveUndoRedo(self):
        source, target, sketch, pad = self.runEstablishedPadWorkflow()
        with self.subTest(stage="accepted"):
            self.assertSourceTipCleared(source, [sketch, pad])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(source.Group, [sketch, pad])
        self.assertEqual(source.Tip, pad)
        self.assertEqual(target.Group, [])
        self.assertIsNone(target.Tip)
        self.assertIn(sketch.AttachmentSupport[0][0], source.Origin.OriginFeatures)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(source.Group, [])
        self.assertEqual(target.Group, [sketch, pad])
        self.assertEqual(target.Tip, pad)
        self.assertIn(sketch.AttachmentSupport[0][0], target.Origin.OriginFeatures)
        self.assertAlmostEqual(target.Shape.Volume, 4000)
        with self.subTest(stage="redone"):
            self.assertSourceTipCleared(source, [sketch, pad])

    def checkMoveWithSelectedProfile(self, selection_names):
        source, target, sketch, pad = self.runEstablishedPadWorkflow(selection_names)

        def assertMoved():
            self.assertEqual(source.Group, [])
            self.assertEqual(target.Group, [sketch, pad])
            self.assertEqual(target.Tip, pad)
            self.assertEqual(pad.Profile[0], sketch)
            self.assertIn(sketch.AttachmentSupport[0][0], target.Origin.OriginFeatures)
            self.assertTrue(target.Shape.isValid())
            self.assertAlmostEqual(target.Shape.Volume, 4000)
            self.assertSourceTipCleared(source, [sketch, pad])

        with self.subTest(stage="accepted"):
            assertMoved()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(source.Group, [sketch, pad])
        self.assertEqual(source.Tip, pad)
        self.assertEqual(target.Group, [])
        self.assertIsNone(target.Tip)
        self.assertIn(sketch.AttachmentSupport[0][0], source.Origin.OriginFeatures)
        self.doc.redo()
        self.doc.recompute()
        with self.subTest(stage="redone"):
            assertMoved()

    def testMovePadThenSelectedProfile(self):
        self.checkMoveWithSelectedProfile(("Pad", "Sketch"))

    def testMoveSelectedProfileThenPad(self):
        self.checkMoveWithSelectedProfile(("Sketch", "Pad"))

    def runPrimitiveCommand(self, accept):
        self.doc = App.newDocument("MovePrimitive14516")
        self.doc.UndoMode = 1
        source = self.doc.addObject("PartDesign::Body", "Source")
        feature = source.newObject("PartDesign::AdditiveBox", "Box")
        feature.Length = 2
        feature.Width = 3
        feature.Height = 5
        target = self.doc.addObject("PartDesign::Body", "Target")
        self.doc.recompute()
        self.assertEqual(source.Tip, feature)
        self.assertAlmostEqual(source.Shape.Volume, 30)
        Gui.activeView().setActiveObject("pdbody", source)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(feature)
        dialog_seen = []
        unexpected_messages = []
        timer = QtCore.QTimer(Gui.getMainWindow())

        def finishDialog():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QInputDialog):
                choices = modal.findChild(QtWidgets.QComboBox)
                if choices is not None and choices.findText(target.Label) >= 0:
                    choices.setCurrentText(target.Label)
                    dialog_seen.append(choices.currentText())
                    modal.accept() if accept else modal.reject()
                else:
                    unexpected_messages.append("Target body missing from ordinary chooser")
                    modal.reject()
            elif isinstance(modal, QtWidgets.QMessageBox):
                unexpected_messages.append(modal.text())
                modal.reject()

        timer.timeout.connect(finishDialog)
        timer.start(30)
        try:
            Gui.runCommand("PartDesign_MoveFeature")
        finally:
            timer.stop()
            timer.deleteLater()
        self.assertEqual(dialog_seen, [target.Label])
        self.assertEqual(unexpected_messages, [])
        self.doc.recompute()
        return source, target, feature

    def testPrimitiveMoveClearsSourceTip(self):
        source, target, feature = self.runPrimitiveCommand(True)
        self.assertEqual(source.Group, [])
        self.assertEqual(target.Group, [feature])
        self.assertEqual(target.Tip, feature)
        self.assertIsNone(feature.BaseFeature)
        self.assertAlmostEqual(target.Shape.Volume, 30)
        self.assertSourceTipCleared(source, [feature])

    def testCancelledPrimitiveMovePreservesSourceControl(self):
        source, target, feature = self.runPrimitiveCommand(False)
        self.assertEqual(source.Group, [feature])
        self.assertEqual(source.Tip, feature)
        self.assertEqual(target.Group, [])
        self.assertIsNone(target.Tip)
        self.assertIsNone(feature.BaseFeature)
        self.assertAlmostEqual(source.Shape.Volume, 30)
