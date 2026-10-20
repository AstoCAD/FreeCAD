# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Draft task acceptance preserves Unicode datum plane/axis references."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestDraftUnicodeReferencesGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("DraftUnicodeReferences")
        self.gui_doc = Gui.getDocument(self.doc.Name)
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

    def fixture(self, plane_name, axis_name, unicode_labels):
        # Reuse the same geometry and exact volume oracle as the existing
        # PartDesignTests.TestDraft.testSimpleDraft backend regression.
        body = self.doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 10
        self.doc.recompute()
        plane = body.newObject("PartDesign::Plane", plane_name)
        self.assertEqual(plane.Name, plane_name)
        plane.AttachmentSupport = [(self.doc.YZ_Plane, "")]
        plane.MapMode = "FlatFace"
        self.doc.recompute()
        axis = body.newObject("PartDesign::Line", axis_name)
        self.assertEqual(axis.Name, axis_name)
        axis.AttachmentSupport = [(self.doc.X_Axis, "")]
        axis.MapMode = "TwoPointLine"
        if unicode_labels:
            plane.Label = "中立面"
            axis.Label = "抜き方向"
        self.doc.recompute()
        faces = box.Shape.Faces
        indices = [index for index, face in enumerate(faces)
                   if face.Surface.Axis == App.Vector(0, 0, 1)]
        self.assertEqual(len(indices), 2)
        top_index = max(indices, key=lambda index: faces[index].CenterOfMass.z)
        feature = body.newObject("PartDesign::Draft", "Draft")
        feature.Base = (box, ["Face%d" % (top_index + 1)])
        feature.NeutralPlane = (plane, [""])
        feature.PullDirection = (axis, [""])
        feature.Angle = 45
        feature.Reversed = True
        self.doc.recompute()
        if "Invalid" in feature.State:
            feature.Reversed = False
            self.doc.recompute()
        self.assertNotIn("Invalid", feature.State)
        self.assertFalse(feature.Shape.isNull())
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 1500)
        return feature, plane, axis

    def checkClosure(self, plane_name, axis_name, unicode_labels=False, accept=True):
        feature, plane, axis = self.fixture(plane_name, axis_name, unicode_labels)
        old_plane = feature.NeutralPlane
        old_axis = feature.PullDirection
        old_base = feature.Base
        self.doc.openTransaction("Edit Draft")
        self.assertTrue(self.gui_doc.setEdit(feature.Name))
        self.pump()
        plane_field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "linePlane")
        axis_field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "lineLine")
        self.assertIsNotNone(plane_field)
        self.assertIsNotNone(axis_field)
        text = (plane_field.text(), axis_field.text())
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        if accept:
            task.accept()
        else:
            task.reject()
        self.pump()
        self.assertIsNone(self.gui_doc.getInEdit(),
                          "An unchanged valid Draft reference must be accepted or cancelled")
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))
        self.assertEqual(feature.NeutralPlane, old_plane)
        self.assertEqual(feature.PullDirection, old_axis)
        self.assertEqual(feature.Base, old_base)
        self.doc.recompute()
        self.assertNotIn("Invalid", feature.State)
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 1500)
        self.assertEqual(self.messages, [])
        if accept:
            self.assertEqual(text, (plane.Name, axis.Name),
                             "Displayed internal references must use the actual UTF-8 identifiers")

    def testAsciiReferencesAcceptControl(self):
        self.checkClosure("NeutralPlane", "PullAxis")

    def testUnicodeNeutralPlaneAccept(self):
        self.checkClosure("中立平面", "PullAxis")

    def testUnicodePullDirectionAccept(self):
        self.checkClosure("NeutralPlane", "抜き方向軸")

    def testUnicodeBothReferencesAccept(self):
        self.checkClosure("中立平面", "抜き方向軸")

    def testUnicodeLabelsAcceptControl(self):
        self.checkClosure("NeutralPlane", "PullAxis", unicode_labels=True)

    def testUnicodeReferencesCancelControl(self):
        self.checkClosure("中立平面", "抜き方向軸", accept=False)
