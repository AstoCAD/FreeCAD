# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2026 AstoCAD     <hello@astocad.com>                     *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

"""Gravity task-panel and shared vector-widget integration regressions."""

import os
import tempfile
import unittest
from unittest.mock import patch

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import Materials
    import AssemblyGui
    import CommandCreateSimulation as SimulationCommand
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestSimulationGravity(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("GravityUiTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.body = self.assembly.newObject("Part::Feature", "Body")
        self.body.Shape = Part.makeBox(10, 20, 30)
        self.body.ShapeMaterial = Materials.MaterialManager().getMaterial(
            "92589471-a6cb-4bbc-b748-d425a17dea7d"
        )
        self.body.Placement.Base = App.Vector(0, 0, 100)
        self.doc.recompute()
        self.active = patch.object(SimulationCommand.UtilsAssembly, "activeAssembly", return_value=self.assembly)
        self.active.start()
        self.panel = SimulationCommand.TaskAssemblyCreateSimulation()

    def tearDown(self):
        if self.panel:
            self.panel.reject()
        self.active.stop()
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve)

    def test_default_controls_and_vector_edit(self):
        panel = self.panel
        actual_icon = panel.form.windowIcon().pixmap(32, 32).toImage()
        expected_icon = Gui.getIcon("Assembly_CreateSimulation").pixmap(32, 32).toImage()
        actual_pixels = [
            actual_icon.pixel(x, y)
            for y in range(actual_icon.height())
            for x in range(actual_icon.width())
        ]
        expected_pixels = [
            expected_icon.pixel(x, y)
            for y in range(expected_icon.height())
            for x in range(expected_icon.width())
        ]
        self.assertEqual(actual_pixels, expected_pixels)
        gravity = panel.form.groupBox_gravity
        self.assertTrue(gravity.isCheckable())
        self.assertFalse(gravity.isChecked())
        self.assertAlmostEqual(panel.simFeaturePy.GravityMagnitude.Value, 9810)
        self.assertEqual(panel.simFeaturePy.GravityDirection, App.Vector(0, 0, -1))
        gravity.setChecked(True)
        vector = panel.form.GravityDirectionEdit
        vector.setProperty("vectorX", 1.0)
        vector.setProperty("vectorZ", 0.0)
        self.assertEqual(panel.simFeaturePy.GravityDirection, App.Vector(1, 0, 0))
        panel.form.GravityMagnitudeSpinBox.setProperty("rawValue", 1000.0)
        self.assertAlmostEqual(panel.simFeaturePy.GravityMagnitude.Value, 1000)

    def test_vector_expander_and_single_notifications(self):
        self.panel.form.groupBox_gravity.setChecked(True)
        vector = self.panel.form.GravityDirectionEdit
        events = []
        vector.vectorChanged.connect(lambda: events.append(True))
        vector.setProperty("vectorX", 0.25)
        self.assertEqual(len(events), 1)
        button = vector.findChild(QtWidgets.QToolButton, "tbExpand")
        spin = vector.findChild(QtWidgets.QDoubleSpinBox, "dsbX")
        self.assertTrue(spin.parentWidget().isHidden())
        button.setChecked(True)
        self.assertFalse(spin.parentWidget().isHidden())
        spin.setValue(-0.5)
        self.assertAlmostEqual(self.panel.simFeaturePy.GravityDirection.x, -0.5)
        button.setChecked(False)
        self.assertTrue(spin.parentWidget().isHidden())

    def test_generate_gravity_and_repeat_from_original_pose(self):
        panel = self.panel
        panel.form.groupBox_gravity.setChecked(True)
        panel.form.TimeEndSpinBox.setProperty("rawValue", 0.1)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            panel.runKinematics()
            warning.assert_not_called()
            self.assertAlmostEqual(self.body.Placement.Base.z, 50.95, delta=0.002)
            panel.runKinematics()
            warning.assert_not_called()
            self.assertAlmostEqual(self.body.Placement.Base.z, 50.95, delta=0.002)
        self.assertEqual(panel.simFeaturePy.Status, "Complete")
        self.assertFalse(panel.form.groupBox_player.isHidden())
        self.assertFalse(panel.form.NoResultsLabel.isVisible())
        self.assertEqual(panel.form.ResultCategoryComboBox.currentData(), "Bodies")
        self.assertEqual(panel.form.ResultQuantityComboBox.currentData()[0], "Placements")
        self.assertGreater(panel.form.ResultTable.rowCount(), 1)
        last_row = panel.form.ResultTable.rowCount() - 1
        self.assertAlmostEqual(float(panel.form.ResultTable.item(last_row, 3).text()), 50.95, delta=0.002)
        headers, rows = panel.resultTableData()
        self.assertEqual(len(headers), 5)
        self.assertEqual(len(rows), panel.form.ResultTable.rowCount())
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "body-position")
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(path, "CSV files (*.csv)"),
            ):
                panel.exportResult()
            with open(path + ".csv", encoding="utf-8") as exported:
                lines = exported.readlines()
            self.assertEqual(len(lines), panel.form.ResultTable.rowCount() + 1)
            self.assertIn("Time (s)", lines[0])

    def test_zero_vector_reports_error_without_preview(self):
        panel = self.panel
        panel.form.groupBox_gravity.setChecked(True)
        panel.form.GravityDirectionEdit.setProperty("vectorZ", 0.0)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            panel.runKinematics()
            warning.assert_called_once()
        self.assertEqual(panel.simFeaturePy.Status, "Failed")
        self.assertTrue(panel.form.groupBox_player.isHidden())
        self.assertAlmostEqual(self.body.Placement.Base.z, 100)

    def test_grounded_cube_vertical_slider_does_not_jump(self):
        import JointObject
        self.panel.reject()
        self.panel = None
        joints = self.assembly.newObject("Assembly::JointGroup", "Joints")
        ground = self.assembly.newObject("Part::Feature", "Ground")
        ground.Shape = Part.makeBox(10, 10, 10)
        self.body.Shape = Part.makeBox(10, 10, 10)
        grounding = joints.newObject("App::FeaturePython", "Grounding")
        JointObject.GroundedJoint(grounding, ground)
        slider = joints.newObject("App::FeaturePython", "Slider")
        JointObject.Joint(slider, JointObject.JointTypes.index("Slider"))
        slider.Detach1 = slider.Detach2 = True
        slider.Reference1 = (ground, [""])
        slider.Reference2 = (self.body, [""])
        rotation = App.Rotation(App.Vector(1, 0, 0), 90)
        ground.Placement = App.Placement(App.Vector(10, 20, 30), rotation)
        self.body.Placement = App.Placement(App.Vector(10, 20, 100), rotation)
        slider.Placement1 = App.Placement(App.Vector(), rotation.inverted())
        slider.Placement2 = App.Placement(App.Vector(), rotation.inverted())
        original = ground.Placement
        self.panel = SimulationCommand.TaskAssemblyCreateSimulation()
        self.panel.form.groupBox_gravity.setChecked(True)
        self.panel.form.TimeEndSpinBox.setProperty("rawValue", 0.1)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.panel.runKinematics()
            warning.assert_not_called()
        self.assertTrue(ground.Placement.isSame(original, 1e-9))
        self.assertTrue(self.body.Placement.Rotation.isSame(rotation, 1e-9))
        self.assertAlmostEqual(self.body.Placement.Base.z, 50.95, delta=0.002)
        self.panel.setFrameValue(1)
        self.assertTrue(ground.Placement.isSame(original, 1e-9))
        self.assertAlmostEqual(self.body.Placement.Base.z, 100, delta=1e-8)

    def test_disabled_gravity_uses_kinematic_path(self):
        self.assertEqual(self.panel.simFeaturePy.AnalysisType, "Automatic")
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.panel.runKinematics()
            warning.assert_not_called()
        self.assertEqual(self.panel.resultData["AnalysisType"], "Kinematics")
        self.assertFalse(self.panel.resultData["JointReactions"])

    def test_explicit_dynamics_without_physical_inputs_and_mode_invalidation(self):
        panel = self.panel
        combo = panel.form.AnalysisTypeComboBox
        combo.setCurrentIndex(combo.findData("Dynamics"))
        self.assertEqual(panel.simFeaturePy.AnalysisType, "Dynamics")
        self.assertFalse(panel.simFeaturePy.GravityEnabled)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            panel.runKinematics()
            warning.assert_not_called()
        self.assertEqual(panel.resultData["AnalysisType"], "Dynamics")
        self.assertEqual(panel.simFeaturePy.Status, "Complete")
        combo.setCurrentIndex(combo.findData("Kinematics"))
        self.assertEqual(panel.simFeaturePy.Status, "NotRun")
        self.assertFalse(panel.simFeaturePy.ResultData)
        self.assertIsNone(panel.resultData)
        self.assertTrue(panel.form.groupBox_player.isHidden())

    def test_load_without_gravity_uses_dynamics_and_populates_load_results(self):
        load = SimulationCommand.Dynamics.create_load(
            self.panel.simFeaturePy, "Force", self.body
        )
        load.Force = "0.006 N"
        self.panel.runKinematics()
        self.assertEqual(self.panel.simFeaturePy.Status, "Complete")
        categories = [
            self.panel.form.ResultCategoryComboBox.itemData(index)
            for index in range(self.panel.form.ResultCategoryComboBox.count())
        ]
        self.assertIn("Loads", categories)
        self.panel.form.ResultCategoryComboBox.setCurrentIndex(categories.index("Loads"))
        self.assertEqual(self.panel.form.ResultQuantityComboBox.currentData()[0], "Force")
        self.assertAlmostEqual(
            float(self.panel.form.ResultTable.item(0, 3).text()), 0.006, delta=1e-9
        )

    def test_legacy_migration_preserves_inputs(self):
        simulation = self.panel.simFeaturePy
        simulation.aTimeStart = "2 s"
        simulation.bTimeEnd = "5 s"
        simulation.removeProperty("GravityEnabled")
        simulation.removeProperty("GravityDirection")
        simulation.removeProperty("AnalysisType")
        simulation.Proxy.onDocumentRestored(simulation)
        self.assertEqual(simulation.AnalysisType, "Automatic")
        self.assertFalse(simulation.GravityEnabled)
        self.assertEqual(simulation.GravityDirection, App.Vector(0, 0, -1))
        self.assertAlmostEqual(simulation.aTimeStart.Value, 2)
        self.assertAlmostEqual(simulation.bTimeEnd.Value, 5)

    def test_gravity_properties_survive_reopen(self):
        self.panel.form.AnalysisTypeComboBox.setCurrentIndex(
            self.panel.form.AnalysisTypeComboBox.findData("Dynamics")
        )
        self.panel.form.groupBox_gravity.setChecked(True)
        self.panel.form.GravityDirectionEdit.setProperty("vectorX", 0.5)
        name = self.panel.simFeaturePy.Name
        self.panel.accept()
        self.panel = None
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Gravity.FCStd")
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            simulation = self.doc.getObject(name)
            self.assertEqual(simulation.AnalysisType, "Dynamics")
            self.assertTrue(simulation.GravityEnabled)
            self.assertEqual(simulation.GravityDirection, App.Vector(0.5, 0, -1))
            self.assertAlmostEqual(simulation.GravityMagnitude.Value, 9810)
