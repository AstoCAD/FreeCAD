# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Pad/Pocket typed UpToFace acceptance with Unicode names and labels."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestTypedUpToFaceReferencesGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.modal_messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                self.modal_messages.append(modal.text())
                modal.reject()

        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)

    def tearDown(self):
        try:
            if self.doc is not None and self.doc.Name in App.listDocuments():
                gui_document = Gui.getDocument(self.doc.Name)
                gui_document.resetEdit()
                if Gui.Control.activeDialog(gui_document):
                    Gui.Control.closeDialog(gui_document)
                App.closeDocument(self.doc.Name)
        finally:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(120, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def checkAcceptance(self, operation, internal_name, label, typed=True):
        self.doc = App.newDocument("TypedUpToFace")
        target = self.doc.addObject("Part::Feature", internal_name)
        self.assertEqual(target.Name, internal_name,
                         "The branch must preserve the requested Unicode internal identifier")
        target.Label = label
        self.assertEqual(target.Label, label)
        target.Shape = Part.makeBox(10, 10, 1, App.Vector(-2, -2, 10))
        self.doc.recompute()
        faces = ["Face%d" % (index + 1) for index, face in enumerate(target.Shape.Faces)
                 if all(abs(vertex.Point.z - 10) < 1e-8 for vertex in face.Vertexes)]
        self.assertEqual(len(faces), 1, "The independent target must have one bottom face at Z10")
        face_name = faces[0]
        body = self.doc.addObject("PartDesign::Body", "Body")
        if operation == "Pocket":
            base = body.newObject("PartDesign::AdditiveBox", "Base")
            base.Length = 2
            base.Width = 3
            base.Height = 20
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        if operation == "Pocket":
            sketch.Placement.Base = App.Vector(0, 0, 20)
        points = [App.Vector(0, 0, 0), App.Vector(2, 0, 0),
                  App.Vector(2, 3, 0), App.Vector(0, 3, 0)]
        sketch.addGeometry([Part.LineSegment(points[index], points[(index + 1) % 4])
                            for index in range(4)], False)
        feature = body.newObject("PartDesign::" + operation, operation)
        feature.Profile = sketch
        feature.Type = "UpToFace"
        feature.UpToFace = (target, [face_name])
        self.doc.recompute()
        self.assertFalse(feature.Shape.isNull(), "Backend fixture must be valid before GUI")
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 60)
        self.assertNotIn("Invalid", feature.State)
        reference = feature.UpToFace
        self.assertEqual(reference[0], target)
        self.assertEqual(reference[1], [face_name])
        gui_document = Gui.getDocument(self.doc.Name)
        self.assertTrue(gui_document.setEdit(feature.Name))
        self.pump()
        field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "lineFaceName")
        self.assertIsNotNone(field)
        self.assertTrue(field.isEnabled())
        original_text = field.text()
        self.assertTrue(original_text.startswith(label + ":"))
        self.assertTrue(original_text.endswith(face_name[4:]))
        self.assertEqual(bytes(field.property("FeatureName")), target.Name.encode("utf-8"))
        self.assertEqual(bytes(field.property("FaceName")), face_name.encode("utf-8"))
        edited = []
        field.textEdited.connect(edited.append)
        if typed:
            # Editing the actual native widget emits textEdited and invokes the normal handler.
            field.setFocus()
            field.selectAll()
            field.insert(original_text)
            self.pump()
            self.assertIn(original_text, edited, "Actual native textEdited must reach the task")
            self.assertEqual(field.text(), original_text)
        # Accept the actual ordinary task before judging cached/model results.
        Gui.Control.activeTaskDialog().accept()
        self.pump()
        self.assertIsNone(gui_document.getInEdit(), "Typed valid reference must be accepted")
        self.assertFalse(Gui.Control.activeDialog(gui_document))
        self.assertEqual(feature.UpToFace, reference)
        self.doc.recompute()
        self.assertNotIn("Invalid", feature.State)
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 60)
        self.assertEqual(self.modal_messages, [])

    def testPadAsciiTypedControl(self):
        self.checkAcceptance("Pad", "Limit", "End face")

    def testPadUnicodeInternalTyped(self):
        self.checkAcceptance("Pad", "限界面", "End face")

    def testPadUnicodeLabelTypedControl(self):
        self.checkAcceptance("Pad", "Limit", "停止面")

    def testPadUnicodeUneditedControl(self):
        self.checkAcceptance("Pad", "限界面", "停止面", typed=False)

    def testPocketAsciiTypedControl(self):
        self.checkAcceptance("Pocket", "Limit", "End face")

    def testPocketUnicodeInternalTyped(self):
        self.checkAcceptance("Pocket", "限界面", "End face")

    def testPocketUnicodeLabelTypedControl(self):
        self.checkAcceptance("Pocket", "Limit", "停止面")

    def testPocketUnicodeUneditedControl(self):
        self.checkAcceptance("Pocket", "限界面", "停止面", typed=False)
