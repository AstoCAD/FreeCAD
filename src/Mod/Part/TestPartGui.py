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

import os
import sys
import unittest
import FreeCAD
import FreeCADGui
import Part
import PartGui
import Sketcher
from PySide import QtCore, QtWidgets


def findDockWidget(name):
    """Get a dock widget by name"""
    mw = FreeCADGui.getMainWindow()
    dws = mw.findChildren(QtWidgets.QDockWidget)
    for dw in dws:
        if dw.objectName() == name:
            return dw
    return None


"""
#---------------------------------------------------------------------------
# define the test cases to test the FreeCAD Part module
#---------------------------------------------------------------------------
"""
from parttests.ColorPerFaceTest import ColorPerFaceTest
from parttests.TestBrepFaceOverlayHistory import TestBrepFaceOverlayHistory
from parttests.ColorTransparencyTest import ColorTransparencyTest
from parttests.TaskFaceAppearancesTest import TaskFaceAppearancesGuiTest
from parttests.TestMirrorPlaneReferencesGui import (
    TestMirrorBodyPlaneBoundary,
    TestMirrorAdmittedPlanePaths,
    TestMirrorLabelPathSerialization,
)
from parttests.TestMirrorUnicodeNamesGui import TestMirrorUnicodeNames


# class PartGuiTestCases(unittest.TestCase):
#    def setUp(self):
#        self.Doc = FreeCAD.newDocument("PartGuiTest")
#
#    def testBoxCase(self):
#        self.Box = self.Doc.addObject('Part::SketchObject','SketchBox')
#        self.Box.addGeometry(Part.LineSegment(App.Vector(-99.230339,36.960674,0),App.Vector(69.432587,36.960674,0)))
#        self.Box.addGeometry(Part.LineSegment(App.Vector(69.432587,36.960674,0),App.Vector(69.432587,-53.196629,0)))
#        self.Box.addGeometry(Part.LineSegment(App.Vector(69.432587,-53.196629,0),App.Vector(-99.230339,-53.196629,0)))
#        self.Box.addGeometry(Part.LineSegment(App.Vector(-99.230339,-53.196629,0),App.Vector(-99.230339,36.960674,0)))
#
#    def tearDown(self):
#        #closing doc
#        FreeCAD.closeDocument("PartGuiTest")
class PartGuiViewProviderTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartGuiTest")

    def testCanDropObject(self):
        # https://github.com/FreeCAD/FreeCAD/pull/6850
        box = self.Doc.addObject("Part::Box", "Box")
        with self.assertRaises(TypeError):
            box.ViewObject.canDragObject(0)
        with self.assertRaises(TypeError):
            box.ViewObject.canDropObject(0)
        box.ViewObject.canDropObject()
        with self.assertRaises(TypeError):
            box.ViewObject.dropObject(box, 0)

    def testLineColorArrayShorterThanEdges(self):
        # https://github.com/FreeCAD/FreeCAD/issues/23346
        from pivy import coin

        box = self.Doc.addObject("Part::Box", "Box")
        self.Doc.recompute()
        vo = box.ViewObject
        vo.LineColor = (0.0, 0.0, 1.0)
        vo.LineColorArray = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]

        sa = coin.SoSearchAction()
        sa.setName(coin.SbName("LineMaterial"))
        sa.apply(vo.RootNode)
        material = sa.getPath().getTail()

        # Coin needs one color per line: the 12 edges must not read past the colors.
        self.assertEqual(material.diffuseColor.getNum(), len(box.Shape.Edges))
        expected = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)] + [(0.0, 0.0, 1.0)] * 10
        for i, color in enumerate(expected):
            for actual, wanted in zip(material.diffuseColor[i].getValue(), color):
                self.assertAlmostEqual(actual, wanted, places=5)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartGuiTest")


class ProjectionOnSurfaceTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("ProjectionOnSurface")

    def testSketchInternalFaceAsSupportFace(self):
        sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.MakeInternals = True
        sketch.addGeometry(
            [
                Part.LineSegment(FreeCAD.Vector(0, 0), FreeCAD.Vector(10, 0)),
                Part.LineSegment(FreeCAD.Vector(10, 0), FreeCAD.Vector(10, 10)),
                Part.LineSegment(FreeCAD.Vector(10, 10), FreeCAD.Vector(0, 10)),
                Part.LineSegment(FreeCAD.Vector(0, 10), FreeCAD.Vector(0, 0)),
            ],
            False,
        )
        self.Doc.recompute()

        FreeCADGui.activateWorkbench("PartWorkbench")
        FreeCADGui.updateGui()
        FreeCADGui.runCommand("Part_ProjectionOnSurface")
        FreeCADGui.updateGui()

        taskDialog = FreeCADGui.Control.activeTaskDialog()
        self.assertIsNotNone(taskDialog)
        supportButton = None
        for widget in taskDialog.getDialogContent():
            supportButton = widget.findChild(QtWidgets.QPushButton, "pushButtonAddProjFace")
            if supportButton:
                break
        self.assertIsNotNone(supportButton)
        supportButton.click()
        FreeCADGui.Selection.addSelection(sketch, "InternalFace1")

        projection = self.Doc.getObject("Projection")
        self.assertIsNotNone(projection)
        self.assertEqual(projection.SupportFace[0], sketch)
        self.assertEqual(projection.SupportFace[1], ["InternalFace1"])

    def tearDown(self):
        FreeCADGui.Selection.clearSelection()
        guiDocument = FreeCADGui.getDocument("ProjectionOnSurface")
        if FreeCADGui.Control.activeDialog(guiDocument):
            FreeCADGui.Control.closeDialog(guiDocument)
        FreeCAD.closeDocument("ProjectionOnSurface")


class PartMirrorGuiTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartMirrorGuiTest")

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        FreeCADGui.Selection.clearSelection()
        FreeCAD.closeDocument(self.Doc.Name)

    def mirrorBoxWithLabel(self, label):
        if not FreeCAD.GuiUp:
            self.skipTest("This test requires a graphical user interface (GUI).")

        box = self.Doc.addObject("Part::Box", "Box")
        box.Label = label
        self.Doc.recompute()

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.Doc.Name, box.Name)
        FreeCADGui.runCommand("Part_Mirror")
        self.assertTrue(FreeCADGui.Control.activeDialog(), "Part Mirror task dialog did not open.")

        FreeCADGui.Control.activeTaskDialog().accept()
        QtWidgets.QApplication.processEvents()

        mirrors = [obj for obj in self.Doc.Objects if obj.isDerivedFrom("Part::Mirroring")]
        self.assertEqual(1, len(mirrors))
        return mirrors[0].Label

    def testMirrorLabelWithUnicodeIsNotDoubleEscaped(self):
        self.assertEqual("caf\u00e9 (Mirror #1)", self.mirrorBoxWithLabel("caf\u00e9"))

    def testMirrorLabelEscapesQuotesBeforePythonCommand(self):
        label = 'a");print("Erasing your hard drive, please stand by....")'
        self.assertEqual(f"{label} (Mirror #1)", self.mirrorBoxWithLabel(label))

    def testMirrorLabelWithNewlinesIsNotMangled(self):
        label = "a\nb\nc"
        self.assertEqual(f"{label} (Mirror #1)", self.mirrorBoxWithLabel(label))


class PartExtrudeGuiTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartExtrudeGuiTest")

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        FreeCADGui.Selection.clearSelection()
        FreeCAD.closeDocument(self.Doc.Name)

    def solidCheckBoxFor(self, shape):
        obj = self.Doc.addObject("Part::Feature", "Profile")
        obj.Shape = shape
        self.Doc.recompute()

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.Doc.Name, obj.Name)
        FreeCADGui.runCommand("Part_Extrude")
        QtWidgets.QApplication.processEvents()
        dialog = FreeCADGui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog, "Part Extrude task dialog did not open.")
        checkBox = None
        for widget in dialog.getDialogContent():
            checkBox = widget.findChild(QtWidgets.QCheckBox, "chkSolid")
            if checkBox:
                break
        self.assertIsNotNone(checkBox)
        return checkBox.isChecked()

    def testCreateSolidIsCheckedForFaceProfile(self):
        # https://github.com/FreeCAD/FreeCAD/issues/31754
        V = FreeCAD.Vector
        wire = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0), V(0, 0, 0)])
        self.assertTrue(self.solidCheckBoxFor(Part.Face(wire)))

    def testCreateSolidIsUncheckedForOpenWire(self):
        V = FreeCAD.Vector
        wire = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 10, 0)])
        self.assertFalse(self.solidCheckBoxFor(wire))

    def extrusions(self):
        return [o for o in self.Doc.Objects if o.isDerivedFrom("Part::Extrusion")]

    def clickApplyClosingMessageBoxes(self, button):
        messages = []

        def closeMessageBoxes():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                    messages.append(widget.text())
                    widget.close()

        timer = QtCore.QTimer()
        timer.timeout.connect(closeMessageBoxes)
        timer.start(100)
        try:
            button.click()
            QtWidgets.QApplication.processEvents()
        finally:
            timer.stop()
        return messages

    def testApplyAfterUndo(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33314
        V = FreeCAD.Vector
        wire = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0), V(0, 0, 0)])
        self.solidCheckBoxFor(Part.Face(wire))
        applyButton = None
        for box in FreeCADGui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox):
            button = box.button(QtWidgets.QDialogButtonBox.Apply)
            if button and button.isVisible():
                applyButton = button
                break
        self.assertIsNotNone(applyButton, "Apply button of the Extrude task dialog not found.")

        self.assertEqual(self.clickApplyClosingMessageBoxes(applyButton), [])
        self.assertEqual(len(self.extrusions()), 1)

        FreeCADGui.runCommand("Std_Undo")
        QtWidgets.QApplication.processEvents()
        self.assertEqual(len(self.extrusions()), 0)

        self.assertEqual(self.clickApplyClosingMessageBoxes(applyButton), [])
        extrusions = self.extrusions()
        self.assertEqual(len(extrusions), 1)
        self.assertFalse(extrusions[0].Shape.isNull())
        self.assertAlmostEqual(extrusions[0].Shape.Volume, 1000.0, places=3)


class AttachmentEditorGuiTestCases(unittest.TestCase):
    # https://github.com/FreeCAD/FreeCAD/issues/33389
    def setUp(self):
        self.Doc = FreeCAD.newDocument("AttachmentEditorGuiTest")
        self.feature = self.Doc.addObject("Part::Feature", "Feature")
        self.feature.Shape = Part.makeBox(1, 1, 1)
        self.Doc.recompute()
        self.assertFalse(self.feature.hasExtension("Part::AttachExtension"))

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        FreeCADGui.Selection.clearSelection()
        FreeCAD.closeDocument(self.Doc.Name)

    def openEditor(self):
        import AttachmentEditor.TaskAttachmentEditor as TaskAttachmentEditor

        panel = TaskAttachmentEditor.AttachmentEditorTaskPanel(self.feature)
        FreeCADGui.Control.showDialog(panel)
        QtWidgets.QApplication.processEvents()
        return panel

    def testCancelDoesNotAddAttachment(self):
        self.openEditor().reject()
        self.assertFalse(self.feature.hasExtension("Part::AttachExtension"))
        self.assertFalse(hasattr(self.feature, "AttachmentSupport"))

    def testOkWithoutReferencesDoesNotAddAttachment(self):
        self.openEditor().accept()
        self.assertFalse(self.feature.hasExtension("Part::AttachExtension"))

    def testOkWithReferenceAddsAttachment(self):
        support = self.Doc.addObject("Part::Box", "Support")
        support.Placement.Base = FreeCAD.Vector(0, 0, 20)
        self.Doc.recompute()
        panel = self.openEditor()
        panel.attacher.References = [(support, "Face6")]
        panel.attacher.Mode = "FlatFace"
        panel.accept()
        self.assertTrue(self.feature.hasExtension("Part::AttachExtension"))
        self.assertEqual(self.feature.MapMode, "FlatFace")
        self.Doc.recompute()
        self.assertAlmostEqual(self.feature.Placement.Base.z, 30.0)


class PartPreferencesTessellationGuiTestCases(unittest.TestCase):
    # https://github.com/FreeCAD/FreeCAD/issues/33020
    ParamPath = "User parameter:BaseApp/Preferences/Mod/Part"
    Entries = ("MeshDeviation", "MeshAngularDeflection")

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartPrefsTessellationTest")
        self.box = self.Doc.addObject("Part::Box", "Box")
        self.Doc.recompute()
        grp = FreeCAD.ParamGet(self.ParamPath)
        self.savedParams = {
            name: (grp.GetFloat(name) if name in grp.GetFloats() else None)
            for name in self.Entries
        }

    def tearDown(self):
        grp = FreeCAD.ParamGet(self.ParamPath)
        for name, value in self.savedParams.items():
            if value is None:
                grp.RemFloat(name)
            else:
                grp.SetFloat(name, value)
        FreeCAD.closeDocument(self.Doc.Name)

    def acceptPreferences(self):
        from PySide import QtCore

        seen = []

        def accept():
            dialog = QtWidgets.QApplication.activeModalWidget()
            seen.append(dialog)
            if dialog is not None:
                dialog.accept()

        QtCore.QTimer.singleShot(500, accept)
        FreeCADGui.runCommand("Std_DlgPreferences")
        QtWidgets.QApplication.processEvents()
        self.assertTrue(seen and seen[0] is not None, "Preferences dialog did not open.")

    def testOkKeepsCustomTessellation(self):
        vo = self.box.ViewObject
        vo.Deviation = 0.05
        vo.AngularDeflection = 10
        self.acceptPreferences()
        self.assertAlmostEqual(vo.Deviation, 0.05, places=5)
        self.assertAlmostEqual(vo.AngularDeflection.Value, 10, places=5)


class SectionCutTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("SectionCut")

    def testOpenDialog(self):
        box = self.Doc.addObject("Part::Box", "SectionCutBoxX")
        comp = self.Doc.addObject("Part::Compound", "SectionCutCompound")
        comp.Links = box
        grp = self.Doc.addObject("App::DocumentObjectGroup", "SectionCutX")
        grp.addObject(comp)
        self.Doc.recompute()

        FreeCADGui.runCommand("Part_SectionCut")
        dw = findDockWidget("Section Cutting")
        if dw:
            box = dw.findChild(QtWidgets.QDialogButtonBox)
            button = box.button(QtWidgets.QDialogButtonBox.Close)
            button.click()
        else:
            print("No section cutting panel found")

    def tearDown(self):
        FreeCAD.closeDocument("SectionCut")
