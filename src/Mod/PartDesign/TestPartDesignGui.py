# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
#                                                                         *
#   This file is part of the FreeCAD CAx development system.              *
#                                                                         *
#   This program is free software; you can redistribute it and/or modify  *
#   it under the terms of the GNU Lesser General Public License (LGPL)    *
#   as published by the Free Software Foundation; either version 2 of     *
#   the License, or (at your option) any later version.                   *
#   for detail see the LICENCE text file.                                 *
#                                                                         *
#   FreeCAD is distributed in the hope that it will be useful,            *
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#   GNU Library General Public License for more details.                  *
#                                                                         *
#   You should have received a copy of the GNU Library General Public     *
#   License along with FreeCAD; if not, write to the Free Software        *
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#   USA                                                                   *
# **************************************************************************

import FreeCAD
import FreeCADGui
import os
import sys
import unittest
import Sketcher
import Part
import PartDesign
import PartDesignGui
import tempfile

from PySide import QtGui, QtCore
from PySide.QtGui import QApplication

from PartDesignTests.TestMaterial import TestMaterial
from PartDesignTests.TestActiveObject import TestActiveObject
from PartDesignTests.TestSuppressed import TestSuppressedStrikethrough
from PartDesignTests.TestLoftSelectionGui import TestLoftSelectionGui
from PartDesignTests.TestLoftVisibilityGui import TestLoftVisibilityGui
from PartDesignTests.TestRevolutionReferencesGui import TestRevolutionReferencesGui
from PartDesignTests.TestTypedUpToFaceReferencesGui import TestTypedUpToFaceReferencesGui
from PartDesignTests.TestDraftUnicodeReferencesGui import TestDraftUnicodeReferencesGui
from PartDesignTests.TestDraftOtherUnicodeReferencesGui import TestDraftOtherUnicodeReferencesGui
from PartDesignTests.TestMoveFeatureSourceTipGui import TestMoveFeatureSourceTipGui
from PartDesignTests.TestShapeBinderHighlightGui import TestShapeBinderHighlightGui
from PartDesignTests.TestBooleanUnicodeNamesGui import TestBooleanUnicodeNamesGui
from PartDesignTests.TestBooleanBoundingBoxGui import TestBooleanBoundingBoxGui
from PartDesignTests.TestBooleanDisplayGui import TestBooleanDisplayGui
from PartDesignTests.TestBooleanDisplayModesGui import TestBooleanDisplayModesGui


# timer runs this class in order to access modal dialog
class CallableCheckWorkflow:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        self.test.assertIsNotNone(dialog, "Dialog box could not be found")
        if dialog is not None:
            dialogcheck = CallableCheckDialogWasClosed(self.test)
            QtCore.QTimer.singleShot(500, dialogcheck)
            QtCore.QTimer.singleShot(0, dialog, QtCore.SLOT("accept()"))


class CallableCheckDialogWasClosed:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        self.test.assertIsNone(dialog, "Dialog box was not closed by accept()")


class CallableCheckWarning:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        self.test.assertIsNotNone(dialog, "Input dialog box could not be found")
        if dialog is not None:
            QtCore.QTimer.singleShot(0, dialog, QtCore.SLOT("accept()"))


class CallableComboBox:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        self.test.assertIsNotNone(dialog, "Warning dialog box could not be found")
        if dialog is not None:
            cbox = dialog.findChild(QtGui.QComboBox)
            self.test.assertIsNotNone(cbox, "ComboBox widget could not be found")
            if cbox is not None:
                QtCore.QTimer.singleShot(0, dialog, QtCore.SLOT("accept()"))


class CallableCheckExemptionDialog:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        if dialog is not None:
            dialogcheck = CallableCheckExemptionDialogWasClosed(self.test)
            QtCore.QTimer.singleShot(100, dialogcheck)
            QtCore.QTimer.singleShot(0, dialog, QtCore.SLOT("accept()"))


class CallableCheckExemptionDialogWasClosed:
    def __init__(self, test):
        self.test = test

    def __call__(self):
        dialog = QApplication.activeModalWidget()
        self.test.assertIsNone(dialog, "Dialog box was not closed by accept()")


App = FreeCAD
Gui = FreeCADGui


# ---------------------------------------------------------------------------
# define the test cases to test the FreeCAD PartDesign module
# ---------------------------------------------------------------------------
class PartDesignGuiTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("SketchGuiTest")

    def makeLcsPlaneExtrusion(self, feature_type):
        Gui.activateWorkbench("PartDesignWorkbench")
        body = self.Doc.addObject("PartDesign::Body", "Body")
        lcs = body.newObject("App::LocalCoordinateSystem", "LCS")
        lcs.Placement = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        if feature_type == "Pocket":
            box = body.newObject("PartDesign::AdditiveBox", "Box")
            box.Length = 2
            box.Width = 3
            box.Height = 20
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        if feature_type == "Pocket":
            sketch.Placement = App.Placement(App.Vector(0, 0, 20), App.Rotation())
        points = [App.Vector(0, 0, 0), App.Vector(2, 0, 0),
                  App.Vector(2, 3, 0), App.Vector(0, 3, 0)]
        sketch.addGeometry([
            Part.LineSegment(points[i], points[(i + 1) % 4]) for i in range(4)
        ], False)
        self.Doc.recompute()
        feature = body.newObject("PartDesign::" + feature_type, feature_type)
        feature.Profile = sketch
        feature.Type = "UpToFace"
        feature.UpToFace = (lcs, ["XY_Plane"])
        self.Doc.recompute()
        self.assertFalse(feature.Shape.isNull())
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, 60)
        return feature, lcs

    def checkUpToLcsPlaneReferenceSurvivesDialog(self, feature_type):
        feature, lcs = self.makeLcsPlaneExtrusion(feature_type)
        expected = feature.UpToFace
        try:
            self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
            Gui.updateGui()
            field = Gui.getMainWindow().findChild(QtGui.QLineEdit, "lineFaceName")
            self.assertIsNotNone(field)
            self.assertTrue(field.text(), "Existing LCS plane reference disappeared")
            self.assertEqual(bytes(field.property("FeatureName")), lcs.Name.encode())
            self.assertEqual(bytes(field.property("FaceName")), b"XY_Plane")
            Gui.Control.activeTaskDialog().accept()
            Gui.updateGui()
            self.assertIsNone(Gui.getDocument(self.Doc.Name).getInEdit())
            self.Doc.recompute()
            self.assertEqual(feature.UpToFace, expected)
            self.assertTrue(feature.Shape.isValid())
            self.assertAlmostEqual(feature.Shape.Volume, 60)
        finally:
            Gui.getDocument(self.Doc.Name).resetEdit()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()

    def testPadUpToLcsPlaneReferenceSurvivesDialog(self):
        self.checkUpToLcsPlaneReferenceSurvivesDialog("Pad")

    def testPocketUpToLcsPlaneReferenceSurvivesDialog(self):
        self.checkUpToLcsPlaneReferenceSurvivesDialog("Pocket")

    def testPadLcsPlaneSelectionKeepsNormalizedReference(self):
        feature, lcs = self.makeLcsPlaneExtrusion("Pad")
        feature.Type = "Length"
        feature.UpToFace = None
        self.Doc.recompute()
        try:
            self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
            Gui.updateGui()
            mode = Gui.getMainWindow().findChild(QtGui.QComboBox, "changeMode")
            self.assertIsNotNone(mode)
            mode.setCurrentIndex(3)  # TaskExtrudeParameters::Mode::ToFace
            Gui.updateGui()
            plane = lcs.OriginFeatures[3]
            Gui.Selection.addSelection(self.Doc.Name, plane.Name)
            Gui.updateGui()
            expected = feature.UpToFace
            self.assertEqual(expected[0], lcs)
            self.assertTrue(expected[1][0].startswith("XY_Plane"))
            Gui.Control.activeTaskDialog().accept()
            Gui.updateGui()
            self.assertIsNone(Gui.getDocument(self.Doc.Name).getInEdit())
            self.Doc.recompute()
            self.assertEqual(feature.UpToFace, expected)
            self.assertTrue(feature.Shape.isValid())
            self.assertAlmostEqual(feature.Shape.Volume, 60)
        finally:
            Gui.Selection.clearSelection()
            Gui.getDocument(self.Doc.Name).resetEdit()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()

    def dressUpGizmoSwitches(self):
        from pivy import coin

        root = Gui.activeDocument().activeView().getViewer().getSoRenderManager().getSceneGraph()
        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoToggleSwitch"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(root)
        found = []
        for path in search.getPaths():
            node = path.getTail()
            children = coin.SoSearchAction()
            children.setType(coin.SoType.fromName("SoLinearDraggerContainer"))
            children.setSearchingAll(True)
            children.apply(node)
            if children.getPath() is not None:
                found.append(node)
        return found

    def dressUpGizmoPositions(self, switch):
        from pivy import coin

        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoLinearDraggerContainer"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(switch)
        return [tuple(path.getTail().getField("translation").getValue().getValue())
                for path in search.getPaths()]

    def checkDressUpGizmoRecovery(self, initially_valid, enabled):
        Gui.activateWorkbench("PartDesignWorkbench")
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Gui/Gizmos")
        had_enabled = "EnableGizmos" in preferences.GetBools()
        old_enabled = preferences.GetBool("EnableGizmos", True)
        preferences.SetBool("EnableGizmos", enabled)
        try:
            for feature_type, size_property, editor_name in (
                ("Fillet", "Radius", "filletRadius"),
                ("Chamfer", "Size", "chamferSize"),
            ):
                with self.subTest(feature=feature_type, enabled=enabled,
                                  initially_valid=initially_valid):
                    body = self.Doc.addObject("PartDesign::Body", "Body")
                    box = body.newObject("PartDesign::AdditiveBox", "Box")
                    box.Length = box.Width = box.Height = 1
                    self.Doc.recompute()
                    feature = body.newObject("PartDesign::" + feature_type, feature_type)
                    feature.Base = (box, ["Edge1"])
                    setattr(feature, size_property, 0.2 if initially_valid else 1)
                    self.Doc.recompute()
                    self.assertEqual(feature.isValid(), initially_valid)
                    try:
                        self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
                        Gui.updateGui()
                        switches = self.dressUpGizmoSwitches()
                        self.assertEqual(len(switches), 1 if enabled else 0)
                        switch = switches[0] if enabled else None
                        if switch is not None:
                            self.assertEqual(bool(switch.getField("on").getValue()), initially_valid)
                        editors = [widget for widget in Gui.getMainWindow().findChildren(
                            QtGui.QAbstractSpinBox, editor_name) if widget.isVisible()]
                        self.assertEqual(len(editors), 1)
                        editor = editors[0]

                        def change_size(size):
                            self.assertTrue(editor.setProperty("rawValue", size))
                            Gui.updateGui()
                            self.assertAlmostEqual(getattr(feature, size_property).Value, size)

                        if initially_valid:
                            positions = self.dressUpGizmoPositions(switch)
                            self.assertTrue(positions)
                            change_size(0.3)
                            self.assertTrue(feature.isValid(), feature.State)
                            self.assertTrue(switch.getField("on").getValue())
                            self.assertEqual(self.dressUpGizmoPositions(switch), positions)
                            # Existing visible draggers remain available when a size is invalid.
                            change_size(1)
                            self.assertFalse(feature.isValid())
                            self.assertTrue(switch.getField("on").getValue())
                        else:
                            change_size(1.1)
                            self.assertFalse(feature.isValid())
                            if switch is not None:
                                self.assertFalse(switch.getField("on").getValue())

                        change_size(0.2)
                        self.assertTrue(feature.isValid(), feature.State)
                        self.assertFalse(feature.Shape.isNull())
                        self.assertTrue(feature.Shape.isValid())
                        if enabled:
                            self.assertTrue(switch.getField("on").getValue(),
                                            "Recovered valid feature retains hidden gizmos")
                            self.assertTrue(self.dressUpGizmoPositions(switch))
                            change_size(0.25)
                            self.assertTrue(feature.isValid(), feature.State)
                            self.assertTrue(switch.getField("on").getValue())
                        else:
                            self.assertEqual(self.dressUpGizmoSwitches(), [])
                    finally:
                        Gui.getDocument(self.Doc.Name).resetEdit()
                        if Gui.Control.activeDialog():
                            Gui.Control.closeDialog()
        finally:
            if had_enabled:
                preferences.SetBool("EnableGizmos", old_enabled)
            else:
                preferences.RemBool("EnableGizmos")

    def testDressUpGizmosRecoverFromInitiallyInvalidSize(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33588
        self.checkDressUpGizmoRecovery(initially_valid=False, enabled=True)

    def testDressUpInitiallyVisibleGizmosRemainAvailable(self):
        self.checkDressUpGizmoRecovery(initially_valid=True, enabled=True)

    def testDressUpGizmoRecoveryRespectsDisabledPreference(self):
        self.checkDressUpGizmoRecovery(initially_valid=False, enabled=False)

    def testChamferGizmosRecoverWhenOtherParametersBecomeValid(self):
        Gui.activateWorkbench("PartDesignWorkbench")
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Gui/Gizmos")
        had_enabled = "EnableGizmos" in preferences.GetBools()
        old_enabled = preferences.GetBool("EnableGizmos", True)
        preferences.SetBool("EnableGizmos", True)
        try:
            for changed in ("second distance", "angle", "type"):
                with self.subTest(changed=changed):
                    body = self.Doc.addObject("PartDesign::Body", "Body")
                    box = body.newObject("PartDesign::AdditiveBox", "Box")
                    box.Length = box.Width = box.Height = 1
                    self.Doc.recompute()
                    feature = body.newObject("PartDesign::Chamfer", "Chamfer")
                    feature.Base = (box, ["Edge1"])
                    feature.Size = 0.2
                    feature.ChamferType = 2 if changed == "angle" else 1
                    feature.Size2 = 1
                    if changed == "angle":
                        # At either extreme one leg exceeds the unit cube. Pick
                        # a verified invalid input before opening the dialog.
                        for angle in (1, 89):
                            feature.Angle = angle
                            self.Doc.recompute()
                            if not feature.isValid():
                                break
                    self.Doc.recompute()
                    self.assertFalse(feature.isValid(), "Test requires initially invalid chamfer")
                    try:
                        self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
                        Gui.updateGui()
                        switches = self.dressUpGizmoSwitches()
                        self.assertEqual(len(switches), 1)
                        switch = switches[0]
                        self.assertFalse(switch.getField("on").getValue())
                        if changed == "type":
                            combos = [widget for widget in Gui.getMainWindow().findChildren(
                                QtGui.QComboBox, "chamferType") if widget.isVisible()]
                            self.assertEqual(len(combos), 1)
                            combos[0].setCurrentIndex(0)  # Equal distance: Size2 is not used.
                        else:
                            name = "chamferAngle" if changed == "angle" else "chamferSize2"
                            editors = [widget for widget in Gui.getMainWindow().findChildren(
                                QtGui.QAbstractSpinBox, name) if widget.isVisible()]
                            self.assertEqual(len(editors), 1)
                            value = 45 if changed == "angle" else 0.2
                            self.assertTrue(editors[0].setProperty("rawValue", value))
                        Gui.updateGui()
                        self.assertTrue(feature.isValid(), feature.State)
                        self.assertTrue(feature.Shape.isValid())
                        self.assertTrue(switch.getField("on").getValue(),
                                        "Recovered valid chamfer retains hidden gizmos")
                        self.assertTrue(self.dressUpGizmoPositions(switch))
                    finally:
                        Gui.getDocument(self.Doc.Name).resetEdit()
                        if Gui.Control.activeDialog():
                            Gui.Control.closeDialog()
        finally:
            if had_enabled:
                preferences.SetBool("EnableGizmos", old_enabled)
            else:
                preferences.RemBool("EnableGizmos")

    def testAllEdgesDressUpDoesNotWarnEmpty(self):
        Gui.activateWorkbench("PartDesignWorkbench")

        def accept_and_capture_report():
            reports = [
                widget for widget in Gui.getMainWindow().findChildren(QtGui.QTextEdit)
                if widget.metaObject().className().endswith("ReportOutput")
            ]
            self.assertTrue(reports, "Report output widget was not found")
            before = [report.toPlainText() for report in reports]
            Gui.Control.activeTaskDialog().accept()
            QApplication.processEvents()
            Gui.updateGui()
            return "\n".join(
                report.toPlainText()[len(old):] for report, old in zip(reports, before)
            )

        for feature_type, size_property in (("Chamfer", "Size"), ("Fillet", "Radius")):
            with self.subTest(feature=feature_type):
                body = self.Doc.addObject("PartDesign::Body", "Body")
                box = body.newObject("PartDesign::AdditiveBox", "Box")
                box.Length = box.Width = box.Height = 10
                self.Doc.recompute()
                feature = body.newObject("PartDesign::" + feature_type, feature_type)
                feature.Base = (box, [])
                feature.UseAllEdges = True
                setattr(feature, size_property, 1)
                self.Doc.recompute()
                self.assertFalse(feature.Shape.isNull())
                self.assertTrue(feature.Shape.isValid())
                self.assertLess(feature.Shape.Volume, box.Shape.Volume)
                message = QtCore.QCoreApplication.translate(
                    "PartDesignGui::Task" + feature_type + "Parameters",
                    "Empty chamfer created!\n" if feature_type == "Chamfer"
                    else "Empty fillet created!",
                ).strip()
                try:
                    self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
                    Gui.updateGui()
                    self.assertNotIn(message, accept_and_capture_report())
                    self.assertIsNone(Gui.getDocument(self.Doc.Name).getInEdit())
                    self.assertFalse(feature.Shape.isNull())
                    self.assertTrue(feature.Shape.isValid())
                    self.assertTrue(feature.UseAllEdges)

                    # A genuinely empty feature must retain the existing warning.
                    self.assertTrue(Gui.getDocument(self.Doc.Name).setEdit(feature.Name))
                    Gui.updateGui()
                    checkbox = Gui.getMainWindow().findChild(QtGui.QCheckBox, "checkBoxUseAllEdges")
                    self.assertIsNotNone(checkbox)
                    checkbox.setChecked(False)
                    Gui.updateGui()
                    self.assertFalse(feature.UseAllEdges)
                    self.assertIn(message, accept_and_capture_report())
                finally:
                    Gui.getDocument(self.Doc.Name).resetEdit()
                    if Gui.Control.activeDialog():
                        Gui.Control.closeDialog()

    def testRefuseToMoveSingleFeature(self):
        FreeCAD.Console.PrintMessage(
            "Testing refuse to move the feature with dependencies from one body to another\n"
        )
        self.BodySource = self.Doc.addObject("PartDesign::Body", "Body")
        Gui.activateView("Gui::View3DInventor", True)
        Gui.activeView().setActiveObject("pdbody", self.BodySource)

        self.BoxObj = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.BoxObj.Length = 10.0
        self.BoxObj.Width = 10.0
        self.BoxObj.Height = 10.0
        self.BodySource.addObject(self.BoxObj)

        App.ActiveDocument.recompute()

        self.Sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        self.Sketch.AttachmentSupport = (self.BoxObj, ("Face3",))
        self.Sketch.MapMode = "FlatFace"
        self.BodySource.addObject(self.Sketch)

        geoList = []
        geoList.append(Part.LineSegment(App.Vector(2.0, 8.0, 0), App.Vector(8.0, 8.0, 0)))
        geoList.append(Part.LineSegment(App.Vector(8.0, 8.0, 0), App.Vector(8.0, 2.0, 0)))
        geoList.append(Part.LineSegment(App.Vector(8.0, 2.0, 0), App.Vector(2.0, 2.0, 0)))
        geoList.append(Part.LineSegment(App.Vector(2.0, 2.0, 0), App.Vector(2.0, 8.0, 0)))
        self.Sketch.addGeometry(geoList, False)
        conList = []
        conList.append(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        conList.append(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
        conList.append(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
        conList.append(Sketcher.Constraint("Coincident", 3, 2, 0, 1))
        conList.append(Sketcher.Constraint("Horizontal", 0))
        conList.append(Sketcher.Constraint("Horizontal", 2))
        conList.append(Sketcher.Constraint("Vertical", 1))
        conList.append(Sketcher.Constraint("Vertical", 3))
        self.Sketch.addConstraint(conList)

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.Sketch
        self.Pad.Length = 10.000000
        self.Pad.Length2 = 100.000000
        self.Pad.Type = 0
        self.Pad.UpToFace = None
        self.Pad.Reversed = 0
        self.Pad.SideType = "One side"
        self.Pad.Offset = 0.000000

        self.BodySource.addObject(self.Pad)

        self.Doc.recompute()
        Gui.ActiveDocument.ActiveView.sendMessage("ViewFit")

        self.BodyTarget = self.Doc.addObject("PartDesign::Body", "Body")

        Gui.Selection.addSelection(App.ActiveDocument.Pad)
        cobj = CallableCheckWarning(self)
        QtCore.QTimer.singleShot(500, cobj)
        Gui.runCommand("PartDesign_MoveFeature")
        # assert dependencies of the Sketch
        self.assertEqual(len(self.BodySource.Group), 3, "Source body feature count is wrong")
        self.assertEqual(len(self.BodyTarget.Group), 0, "Target body feature count is wrong")

    def testMoveSingleFeature(self):
        FreeCAD.Console.PrintMessage("Testing moving one feature from one body to another\n")
        self.BodySource = self.Doc.addObject("PartDesign::Body", "Body")
        Gui.activateView("Gui::View3DInventor", True)
        Gui.activeView().setActiveObject("pdbody", self.BodySource)

        self.Sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        self.BodySource.addObject(self.Sketch)
        self.Sketch.AttachmentSupport = (self.BodySource.Origin.OriginFeatures[3], [""])
        self.Sketch.MapMode = "FlatFace"

        geoList = []
        geoList.append(
            Part.LineSegment(
                App.Vector(-10.000000, 10.000000, 0), App.Vector(10.000000, 10.000000, 0)
            )
        )
        geoList.append(
            Part.LineSegment(
                App.Vector(10.000000, 10.000000, 0), App.Vector(10.000000, -10.000000, 0)
            )
        )
        geoList.append(
            Part.LineSegment(
                App.Vector(10.000000, -10.000000, 0), App.Vector(-10.000000, -10.000000, 0)
            )
        )
        geoList.append(
            Part.LineSegment(
                App.Vector(-10.000000, -10.000000, 0), App.Vector(-10.000000, 10.000000, 0)
            )
        )
        self.Sketch.addGeometry(geoList, False)
        conList = []
        conList.append(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        conList.append(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
        conList.append(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
        conList.append(Sketcher.Constraint("Coincident", 3, 2, 0, 1))
        conList.append(Sketcher.Constraint("Horizontal", 0))
        conList.append(Sketcher.Constraint("Horizontal", 2))
        conList.append(Sketcher.Constraint("Vertical", 1))
        conList.append(Sketcher.Constraint("Vertical", 3))
        self.Sketch.addConstraint(conList)

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.BodySource.addObject(self.Pad)
        self.Pad.Profile = self.Sketch
        self.Pad.Length = 10.000000
        self.Pad.Length2 = 100.000000
        self.Pad.Type = 0
        self.Pad.UpToFace = None
        self.Pad.Reversed = 0
        self.Pad.SideType = "One side"
        self.Pad.Offset = 0.000000

        self.Doc.recompute()
        Gui.ActiveDocument.ActiveView.sendMessage("ViewFit")

        self.BodyTarget = self.Doc.addObject("PartDesign::Body", "Body")

        Gui.Selection.addSelection(App.ActiveDocument.Pad)
        cobj = CallableComboBox(self)
        QtCore.QTimer.singleShot(500, cobj)
        Gui.runCommand("PartDesign_MoveFeature")
        # assert dependencies of the Sketch
        self.Doc.recompute()

        self.assertFalse(
            self.Sketch.AttachmentSupport[0][0] in self.BodySource.Origin.OriginFeatures
        )
        self.assertTrue(
            self.Sketch.AttachmentSupport[0][0] in self.BodyTarget.Origin.OriginFeatures
        )
        self.assertEqual(len(self.BodySource.Group), 0, "Source body feature count is wrong")
        self.assertEqual(len(self.BodyTarget.Group), 2, "Target body feature count is wrong")

    def tearDown(self):
        FreeCAD.closeDocument("SketchGuiTest")


class PartDesignTransformed(unittest.TestCase):
    def setUp(self):
        self.Doc = App.newDocument("PartDesignTransformed")
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.BoxObj = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.BoxObj.Length = 10.0
        self.BoxObj.Width = 10.0
        self.BoxObj.Height = 10.0
        App.ActiveDocument.recompute()
        # not adding box to the body to imitate undertermined workflow
        tempDir = tempfile.gettempdir()
        self.TempDoc = os.path.join(tempDir, "PartDesignTransformed.FCStd")
        if os.path.exists(self.TempDoc):
            os.remove(self.TempDoc)
        App.ActiveDocument.saveAs(self.TempDoc)
        App.closeDocument("PartDesignTransformed")

    def tearDown(self):
        # closing doc
        if App.ActiveDocument is not None and App.ActiveDocument.Name == PartDesignTransformed:
            App.closeDocument("PartDesignTransformed")
        # print ("omit closing document for debugging")

    def testMultiTransformCase(self):
        App.Console.PrintMessage("Testing applying MultiTransform to the Box outside the body\n")
        App.open(self.TempDoc)
        App.setActiveDocument("PartDesignTransformed")
        Gui.Selection.addSelection(App.ActiveDocument.Box)

        workflowcheck = CallableCheckWorkflow(self)
        QtCore.QTimer.singleShot(500, workflowcheck)
        Gui.runCommand("PartDesign_MultiTransform")

        App.closeDocument("PartDesignTransformed")


class CreateSketch(unittest.TestCase):

    def testPDCreateSketch(self):
        App.Console.PrintMessage("Testing the creation of a sketch\n")
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/PartDesign")
        useAttachmentSaved = param.GetBool("NewSketchUseAttachmentDialog", False)
        param.SetBool("NewSketchUseAttachmentDialog", False)
        App.newDocument()
        App.activeDocument().addObject("PartDesign::Body", "Body")
        App.ActiveDocument.getObject("Body").Label = "Body"
        App.ActiveDocument.getObject("Body").AllowCompound = True
        FreeCADGui.activateView("Gui::View3DInventor", True)
        FreeCADGui.activeView().setActiveObject("pdbody", App.activeDocument().Body)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.runCommand("Std_OrthographicCamera", 1)
        workflowcheck = CallableCheckExemptionDialog(self)
        QtCore.QTimer.singleShot(100, workflowcheck)
        FreeCADGui.runCommand("PartDesign_CompSketches", 0)
        activeDialog = FreeCADGui.Control.activeDialog()
        self.assertIsNotNone(activeDialog)
        if activeDialog is not None:
            FreeCADGui.Control.closeDialog()
        App.closeDocument(App.ActiveDocument.Name)
        param.SetBool("NewSketchUseAttachmentDialog", useAttachmentSaved)


# class PartDesignGuiTestCases(unittest.TestCase):
#   def setUp(self):
#       self.Doc = FreeCAD.newDocument("SketchGuiTest")
#
#   def testBoxCase(self):
#       self.Box = self.Doc.addObject('PartDesign::SketchObject','SketchBox')
#       self.Box.addGeometry(Part.LineSegment(App.Vector(-99.230339,36.960674,0),App.Vector(69.432587,36.960674,0)))
#       self.Box.addGeometry(Part.LineSegment(App.Vector(69.432587,36.960674,0),App.Vector(69.432587,-53.196629,0)))
#       self.Box.addGeometry(Part.LineSegment(App.Vector(69.432587,-53.196629,0),App.Vector(-99.230339,-53.196629,0)))
#       self.Box.addGeometry(Part.LineSegment(App.Vector(-99.230339,-53.196629,0),App.Vector(-99.230339,36.960674,0)))
#
#   def tearDown(self):
#       #closing doc
#       FreeCAD.closeDocument("SketchGuiTest")


class TestShapeBinder(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestShapeBinder")

    def testDefaultColor(self):
        """
        A shape binder uses a different default color than a Part feature.
        This color must still be set after its creation.
        """
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Doc.recompute()
        binder = self.Doc.addObject("PartDesign::ShapeBinder", "ShapeBinder")
        binder.Support = [(self.Box, "Face1")]

        grp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/PartDesign")
        packed_color = grp.GetUnsigned("DefaultDatumColor", 0xFFD70099)
        r, g, b, a = binder.ViewObject.ShapeColor
        color = (
            int(r * 255.0 + 0.5) << 24
            | int(g * 255.0 + 0.5) << 16
            | int(b * 255.0 + 0.5) << 8
            | int(a * 255.0 + 0.5)
        )

        self.assertEqual(packed_color, color)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)


class TestSubShapeBinder(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestSubShapeBinder")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def testDefaultColor(self):
        """
        A sub-shape binder uses a different default color than a Part feature.
        This color must still be set after its creation.
        """
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        body.addObject(box)

        self.Doc.recompute()
        binder = body.newObject("PartDesign::SubShapeBinder", "Binder")
        binder.Support = [(box, ("Face1"))]

        grp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/PartDesign")
        packed_color = grp.GetUnsigned("DefaultDatumColor", 0xFFD70099)
        r, g, b, a = binder.ViewObject.ShapeColor
        color = (
            int(r * 255.0 + 0.5) << 24
            | int(g * 255.0 + 0.5) << 16
            | int(b * 255.0 + 0.5) << 8
            | int(a * 255.0 + 0.5)
        )

        self.assertEqual(packed_color, color)


class TestDatumPlane(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestDatumPlane")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def testDefaultColor(self):
        """
        A datum object uses a different default color than a Part feature.
        This color must still be set after its creation.
        """
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        body.addObject(box)

        self.Doc.recompute()
        datum = body.newObject("PartDesign::Plane", "DatumPlane")
        datum.AttachmentSupport = [(box, "Face6")]
        datum.MapMode = "FlatFace"
        self.Doc.recompute()

        grp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/PartDesign")
        packed_color = grp.GetUnsigned("DefaultDatumColor", 0xFFD70099)
        r, g, b, a = datum.ViewObject.ShapeColor
        color = (
            int(r * 255.0 + 0.5) << 24
            | int(g * 255.0 + 0.5) << 16
            | int(b * 255.0 + 0.5) << 8
            | int(a * 255.0 + 0.5)
        )

        self.assertEqual(packed_color, color)
