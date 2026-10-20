# SPDX-License-Identifier: LGPL-2.1-or-later
"""Separate face and sketch-plane reference branches of the actual Draft task."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
import Sketcher
from PySide import QtCore, QtWidgets

class TestDraftOtherUnicodeReferencesGui(unittest.TestCase):
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


    def fixture(self, kind, name, unicode_label):
        body = self.doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 10
        self.doc.recompute()
        if kind == "face":
            # A standard ShapeBinder of the box's X0 face gives a separate,
            # meaningful planar-face reference without changing Base's name.
            faces = box.Shape.Faces
            candidates = [index for index, face in enumerate(faces)
                          if abs(abs(face.Surface.Axis.x) - 1) < 1e-8]
            self.assertEqual(len(candidates), 2)
            plane_index = min(candidates, key=lambda index: faces[index].CenterOfMass.x)
            reference = body.newObject("PartDesign::ShapeBinder", name)
            reference.Support = [(box, ["Face%d" % (plane_index + 1)])]
            self.doc.recompute()
            self.assertEqual(len(reference.Shape.Faces), 1)
            self.assertAlmostEqual(reference.Shape.BoundBox.XLength, 0)
            sub = ["Face1"]
        else:
            self.assertEqual(kind, "sketch")
            reference = body.newObject("Sketcher::SketchObject", name)
            reference.Placement = App.Placement(
                App.Vector(), App.Rotation(App.Vector(0, 0, 1), App.Vector(1, 0, 0)))
            points = [App.Vector(x, y, 0)
                      for x, y in ((0, 0), (10, 0), (10, 10), (0, 10))]
            reference.addGeometry([Part.LineSegment(points[index], points[(index + 1) % 4])
                                   for index in range(4)], False)
            self.doc.recompute()
            self.assertAlmostEqual(reference.Shape.BoundBox.XLength, 0)
            sub = [""]
        self.assertEqual(reference.Name, name)
        if unicode_label:
            reference.Label = "中立面の参照"
        axis = body.newObject("PartDesign::Line", "PullAxis")
        axis.AttachmentSupport = [(self.doc.X_Axis, "")]
        axis.MapMode = "TwoPointLine"
        self.doc.recompute()
        faces = box.Shape.Faces
        z_faces = [index for index, face in enumerate(faces)
                   if face.Surface.Axis == App.Vector(0, 0, 1)]
        self.assertEqual(len(z_faces), 2)
        top_index = max(z_faces, key=lambda index: faces[index].CenterOfMass.z)
        feature = body.newObject("PartDesign::Draft", "Draft")
        feature.Base = (box, ["Face%d" % (top_index + 1)])
        feature.NeutralPlane = (reference, sub)
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
        self.assertAlmostEqual(feature.Shape.Volume, 1500,
                               msg="The actual reference must produce a valid independent Draft")
        return feature, reference, axis, sub

    def checkClosure(self, kind, name, unicode_label=False, accept=True):
        feature, reference, axis, sub = self.fixture(kind, name, unicode_label)
        original_plane = feature.NeutralPlane
        original_axis = feature.PullDirection
        original_base = feature.Base
        self.doc.openTransaction("Edit Draft")
        self.assertTrue(self.gui_doc.setEdit(feature.Name))
        self.pump()
        field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "linePlane")
        self.assertIsNotNone(field)
        text = field.text()
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        if accept:
            task.accept()
        else:
            task.reject()
        self.pump()
        self.assertIsNone(self.gui_doc.getInEdit())
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))
        self.assertEqual(feature.NeutralPlane, original_plane)
        self.assertEqual(feature.PullDirection, original_axis)
        self.assertEqual(feature.Base, original_base)
        self.doc.recompute()
        self.assertNotIn("Invalid", feature.State)
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 1500)
        self.assertEqual(self.messages, [])
        if accept:
            self.assertEqual(text, name + (":" + sub[0] if sub[0] else ""))

    def testFaceAsciiAcceptControl(self):
        self.checkClosure("face", "NeutralReference")

    def testFaceUnicodeNameAccept(self):
        self.checkClosure("face", "中立参照")

    def testFaceUnicodeLabelAcceptControl(self):
        self.checkClosure("face", "NeutralReference", unicode_label=True)

    def testFaceUnicodeNameCancelControl(self):
        self.checkClosure("face", "中立参照", accept=False)

    def testSketchAsciiAcceptControl(self):
        self.checkClosure("sketch", "NeutralReference")

    def testSketchUnicodeNameAccept(self):
        self.checkClosure("sketch", "中立参照")

    def testSketchUnicodeLabelAcceptControl(self):
        self.checkClosure("sketch", "NeutralReference", unicode_label=True)

    def testSketchUnicodeNameCancelControl(self):
        self.checkClosure("sketch", "中立参照", accept=False)
