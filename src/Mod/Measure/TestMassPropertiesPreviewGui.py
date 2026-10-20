# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Mass Properties task owns only the preview object that it creates."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Materials
import Measure
import Part
from PySide import QtCore, QtWidgets


class TestMassPropertiesPreviewGui(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        previous_name = previous.Name if previous else None

        def restoreActive():
            if previous_name in App.listDocuments():
                App.setActiveDocument(previous_name)

        self.addCleanup(restoreActive)
        self.doc = App.newDocument("MassPropertiesPreviewRegression")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(Gui.Selection.clearSelection)

        def closeDialog():
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()

        self.addCleanup(closeDialog)

    @staticmethod
    def _pump():
        Gui.updateGui()
        QtCore.QCoreApplication.processEvents()

    @staticmethod
    def _snapshot(doc, name):
        obj = doc.getObject(name)
        if obj is None:
            return None
        result = {"type": obj.TypeId, "label": obj.Label,
                  "visible": obj.ViewObject.Visibility,
                  "show_in_tree": obj.ViewObject.ShowInTree,
                  "marker": obj.OwnershipMarker if "OwnershipMarker" in obj.PropertiesList else None}
        if "Shape" in obj.PropertiesList:
            result["volume"] = obj.Shape.Volume
        return result

    def _checkPreviewOwnership(self, sentinel_type=None):
        material = Materials.Material()
        material.Name = "Preview test material"
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        sample = self.doc.addObject("Part::Feature", "Sample")
        sample.Shape = Part.makeBox(10, 10, 10)
        sample.ShapeMaterial = material
        if sentinel_type:
            sentinel = self.doc.addObject(sentinel_type, "MassPropertiesPreview")
            sentinel.Label = "Pre-existing user object"
            sentinel.addProperty("App::PropertyString", "OwnershipMarker")
            sentinel.OwnershipMarker = "user-owned-data"
            if sentinel_type == "Part::Feature":
                sentinel.Shape = Part.makeBox(7, 8, 9)
            sentinel.ViewObject.Visibility = False
            sentinel.ViewObject.ShowInTree = True
        self.doc.recompute()
        before_names = {obj.Name for obj in self.doc.Objects}
        before_sentinel = self._snapshot(self.doc, "MassPropertiesPreview")
        before_sample = self._snapshot(self.doc, sample.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sample)
        Gui.runCommand("Std_MassProperties")
        self._pump()
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        while_open = self._snapshot(self.doc, "MassPropertiesPreview")
        new_objects = [(obj.Name, obj.TypeId) for obj in self.doc.Objects
                       if obj.Name not in before_names]

        panel = task.getDialogContent()[0]
        while panel.parentWidget() is not None and not isinstance(
                panel.parentWidget(), QtWidgets.QStackedWidget):
            panel = panel.parentWidget()
        self.assertIsInstance(panel.parentWidget(), QtWidgets.QStackedWidget)
        buttons = panel.findChild(QtWidgets.QDialogButtonBox)
        self.assertIsNotNone(buttons)
        close_button = buttons.button(QtWidgets.QDialogButtonBox.Abort)
        self.assertIsNotNone(close_button)
        close_button.click()
        self._pump()
        self.assertFalse(Gui.Control.activeDialog())

        self.assertEqual(len(new_objects), 1, "The task must create its own preview")
        self.assertEqual(new_objects[0][1], "Measure::Result")
        if sentinel_type:
            self.assertNotEqual(new_objects[0][0], "MassPropertiesPreview")
            self.assertEqual(while_open, before_sentinel,
                             "A pre-existing object's display state must remain unchanged")
            self.assertEqual(self._snapshot(self.doc, "MassPropertiesPreview"), before_sentinel)
        else:
            self.assertEqual(while_open["type"], "Measure::Result")
            self.assertIsNone(self.doc.getObject(new_objects[0][0]))
        self.assertEqual({obj.Name for obj in self.doc.Objects}, before_names)
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)

    def testOrdinaryPreviewCreationAndCleanup(self):
        self._checkPreviewOwnership()

    def testPreservesExistingPartFeature(self):
        self._checkPreviewOwnership("Part::Feature")

    def testPreservesExistingFeaturePython(self):
        self._checkPreviewOwnership("App::FeaturePython")

    def testPreservesExistingMeasureResult(self):
        self._checkPreviewOwnership("Measure::Result")
