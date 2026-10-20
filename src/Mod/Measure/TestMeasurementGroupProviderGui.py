# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual save/reopen regressions for the shared Measurements folder provider."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Materials
import Measure  # noqa: F401
import Part
from PySide import QtCore, QtWidgets


class TestMeasurementGroupProvider(unittest.TestCase):
    def setUp(self):
        self.previous = App.activeDocument().Name if App.activeDocument() else None
        self.doc = App.newDocument("MeasurementGroup28644")
        self.retained = []
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self._cleanup)
        material = Materials.Material()
        material.Name = "Group provider test material"
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        self.sample = self.doc.addObject("Part::Feature", "Sample")
        self.sample.Shape = Part.makeBox(10, 10, 10)
        self.sample.ShapeMaterial = material
        self.doc.recompute()
        Gui.Selection.clearSelection()

    def _cleanup(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    def _buttons(self):
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        contents = task.getDialogContent()
        self.assertTrue(contents)
        self.retained.extend([task, *contents])
        panel = contents[0]
        while True:
            parent = panel.parentWidget()
            self.assertIsNotNone(parent)
            self.retained.append(parent)
            if isinstance(parent, QtWidgets.QStackedWidget):
                break
            panel = parent
        buttons = panel.findChild(QtWidgets.QDialogButtonBox)
        self.assertIsNotNone(buttons)
        self.retained.extend([buttons, *buttons.buttons()])
        return buttons

    def _save(self, command):
        self.assertFalse(Gui.Control.activeDialog())
        group_before = self.doc.getObject("Measurements")
        previous_members = set(obj.Name for obj in group_before.Group) if group_before else set()
        Gui.Selection.clearSelection()
        if command == "Std_Measure":
            Gui.Selection.addSelection(self.doc.Name, self.sample.Name, "Edge1")
        else:
            Gui.Selection.addSelection(self.sample)
        Gui.runCommand(command)
        Gui.updateGui()
        save = self._buttons().button(QtWidgets.QDialogButtonBox.Apply)
        self.assertIsNotNone(save)
        self.assertTrue(save.isEnabled(), "Real selected shape must produce savable results")
        save.click()
        Gui.updateGui()
        group = self.doc.getObject("Measurements")
        self.assertIsNotNone(group)
        self.assertEqual(group.TypeId, "App::DocumentObjectGroup")
        new_members = [obj for obj in group.Group if obj.Name not in previous_members]
        self.assertEqual(len(new_members), 1, "Save must add exactly one ordinary measurement")
        saved = new_members[0]
        if command == "Std_Measure":
            self.assertEqual(saved.TypeId, "Measure::MeasureLength")
            self.assertAlmostEqual(saved.Length.Value, 10, places=8)
        else:
            self.assertEqual(saved.TypeId, "Measure::Result")
            volume = App.Units.Quantity(saved.Volume.replace("³", "^3"))
            self.assertAlmostEqual(volume.getValueAs("mm^3"), 1000, places=6)
        self.assertNotIn("Invalid", saved.State)
        Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        Gui.updateGui()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIn(saved, group.Group)
        self.assertAlmostEqual(self.sample.Shape.Volume, 1000, places=8)
        return group, saved

    def _roundtrip_group(self, dedicated):
        group = self.doc.getObject("Measurements")
        expected_label = group.Label
        expected_provider = group.ViewObject.TypeId
        expected_members = [(obj.Name, obj.TypeId, obj.Label) for obj in group.Group]
        expected_icon = group.ViewObject.Icon.pixmap(32, 32).toImage()
        path = str(Path(self.directory.name) / "measurement-groups.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        self.doc = App.openDocument(path)
        Gui.updateGui()
        group = self.doc.getObject("Measurements")
        self.assertIsNotNone(group)
        self.assertEqual(group.Label, expected_label)
        self.assertEqual(group.ViewObject.TypeId, expected_provider)
        self.assertEqual([(obj.Name, obj.TypeId, obj.Label) for obj in group.Group], expected_members)
        self.assertEqual(group.ViewObject.Icon.pixmap(32, 32).toImage(), expected_icon)
        if dedicated:
            self._assert_dedicated_group(group)
        self.assertAlmostEqual(self.doc.getObject("Sample").Shape.Volume, 1000, places=8)
        for obj in group.Group:
            self.assertNotIn("Invalid", obj.State)
            if obj.TypeId == "Measure::MeasureLength":
                self.assertAlmostEqual(obj.Length.Value, 10, places=8)
            elif obj.TypeId == "Measure::Result":
                volume = App.Units.Quantity(obj.Volume.replace("³", "^3"))
                self.assertAlmostEqual(volume.getValueAs("mm^3"), 1000, places=6)

    def _assert_dedicated_group(self, group):
        self.assertTrue(group.ViewObject.isDerivedFrom("MeasureGui::ViewProviderMeasureGroup"),
                        f"Shared Measurements folder has provider {group.ViewObject.TypeId}")
        actual = group.ViewObject.Icon.pixmap(32, 32).toImage()
        expected = Gui.getIcon("Measurement-Group.svg").pixmap(32, 32).toImage()
        self.assertFalse(actual.isNull())
        self.assertFalse(expected.isNull())
        self.assertEqual(actual, expected)

    def test_measure_first_then_mass_uses_dedicated_group_control(self):
        group, length = self._save("Std_Measure")
        self._assert_dedicated_group(group)
        same_group, mass = self._save("Std_MassProperties")
        self.assertEqual(same_group, group)
        self.assertEqual(set(group.Group), {length, mass})
        self._assert_dedicated_group(group)
        self._roundtrip_group(dedicated=True)

    def test_mass_first_uses_same_dedicated_group(self):
        group, mass = self._save("Std_MassProperties")
        self.assertEqual(group.Group, [mass])
        self._assert_dedicated_group(group)
        self._roundtrip_group(dedicated=True)

    def test_mass_first_then_measure_reuses_dedicated_group(self):
        group, mass = self._save("Std_MassProperties")
        same_group, length = self._save("Std_Measure")
        self.assertEqual(same_group, group)
        self.assertEqual(set(group.Group), {mass, length})
        self._assert_dedicated_group(group)
        self._roundtrip_group(dedicated=True)

    def test_existing_user_group_provider_and_member_are_preserved_control(self):
        group = self.doc.addObject("App::DocumentObjectGroup", "Measurements")
        group.Label = "User-owned measurements folder"
        sentinel = self.doc.addObject("App::FeaturePython", "UserValue")
        group.addObject(sentinel)
        provider = group.ViewObject.TypeId
        icon = group.ViewObject.Icon.pixmap(32, 32).toImage()
        same_group, mass = self._save("Std_MassProperties")
        self.assertEqual(same_group, group)
        same_group, length = self._save("Std_Measure")
        self.assertEqual(same_group, group)
        self.assertEqual(set(group.Group), {sentinel, mass, length})
        self.assertEqual(group.Label, "User-owned measurements folder")
        self.assertEqual(group.ViewObject.TypeId, provider)
        self.assertEqual(group.ViewObject.Icon.pixmap(32, 32).toImage(), icon)
        self._roundtrip_group(dedicated=False)


if __name__ == "__main__":
    unittest.main()
