# SPDX-License-Identifier: LGPL-2.1-or-later
"""Revolution task acceptance preserves references in Unicode-named documents."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestRevolutionReferencesGui(unittest.TestCase):
    def setUp(self):
        self.doc = None

    def tearDown(self):
        if self.doc is not None:
            Gui.getDocument(self.doc.Name).resetEdit()
            if Gui.Control.activeDialog(Gui.getDocument(self.doc.Name)):
                Gui.Control.closeDialog(Gui.getDocument(self.doc.Name))
            App.closeDocument(self.doc.Name)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(120, loop.quit)
        loop.exec_()

    def checkAcceptance(self, name, two_sides=False, angle=False):
        self.doc = App.newDocument(name)
        self.assertEqual(self.doc.Name, name, "Document name must exercise the requested encoding")
        body = self.doc.addObject("PartDesign::Body", "Body")
        # Revolve the solid's YZ side about its boundary axis, up to an
        # intersecting datum plane, so both reference modes produce valid solids.
        base = body.newObject("PartDesign::AdditiveBox", "Box")
        base.Length = 1
        base.Width = 10
        base.Height = 10
        plane = body.newObject("PartDesign::Plane", "Limit")
        plane.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 1, 0), 45))
        plane2 = None
        if two_sides:
            plane2 = body.newObject("PartDesign::Plane", "Limit2")
            plane2.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 1, 0), -45))
        feature = body.newObject("PartDesign::Revolution", "Revolution")
        feature.Profile = (base, ["Face1"])
        axis = self.doc.getObject("Y_Axis")
        self.assertIsNotNone(axis)
        feature.ReferenceAxis = (axis, [""])
        feature.Angle = 30
        feature.Reversed = True
        if angle:
            feature.Type = "Angle"
        else:
            feature.Type = "UpToFace"
            feature.UpToFace = (plane, [""])
        if two_sides:
            feature.SideType = "Two sides"
            feature.Type2 = "UpToFace"
            feature.UpToFace2 = (plane2, [""])
        self.doc.recompute()
        self.assertFalse(feature.Shape.isNull(), "Backend fixture must create a real solid")
        self.assertTrue(feature.Shape.isValid(), "Backend fixture must be valid before opening GUI")
        self.assertGreater(feature.Shape.Volume, 0)
        self.assertNotIn("Invalid", feature.State)
        volume = feature.Shape.Volume
        references = feature.UpToFace, feature.UpToFace2
        self.assertTrue(Gui.getDocument(name).setEdit(feature.Name))
        self.pump()
        if not angle:
            field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "lineFaceName")
            self.assertIsNotNone(field)
            self.assertEqual(bytes(field.property("FeatureName")), plane.Name.encode())
            self.assertTrue(field.text())
        if two_sides:
            field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "lineFaceName2")
            self.assertIsNotNone(field)
            self.assertEqual(bytes(field.property("FeatureName")), plane2.Name.encode())
            self.assertTrue(field.text())
        # This public wrapper clicks the ordinary task's actual AcceptRole
        # button and therefore exercises TaskRevolutionParameters::apply.
        Gui.Control.activeTaskDialog().accept()
        self.pump()
        self.assertIsNone(Gui.getDocument(name).getInEdit(),
                          "Unchanged valid Revolution task must accept its reference")
        self.assertFalse(Gui.Control.activeDialog())
        self.doc.recompute()
        self.assertEqual((feature.UpToFace, feature.UpToFace2), references)
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, volume)

    def testAsciiUpToFaceAccept(self):
        self.checkAcceptance("RevolutionAscii")

    def testUmlautUpToFaceAccept(self):
        self.checkAcceptance("Revolution\u00fc")

    def testChineseUpToFaceAccept(self):
        self.checkAcceptance("Revolution\u6f22\u5b57")

    def testUnicodeAngleAcceptControl(self):
        self.checkAcceptance("RevolutionAngle\u6f22\u5b57", angle=True)

    def testAsciiTwoSidedUpToFaceAccept(self):
        self.checkAcceptance("RevolutionTwoAscii", two_sides=True)

    def testUnicodeTwoSidedUpToFaceAccept(self):
        self.checkAcceptance("RevolutionTwo\u6f22\u5b57", two_sides=True)

    def testAsciiSecondSideOnlyFaceAccept(self):
        self.checkAcceptance("RevolutionSecondAscii", two_sides=True, angle=True)

    def testUnicodeSecondSideOnlyFaceAccept(self):
        self.checkAcceptance("RevolutionSecond\u6f22\u5b57", two_sides=True, angle=True)
