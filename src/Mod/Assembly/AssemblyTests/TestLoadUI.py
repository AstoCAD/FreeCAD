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

"""Assembly load command, attachment task box, and transaction regressions."""

import unittest
from unittest.mock import patch

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import CommandCreateLoad as LoadCommand
    import CommandCreateSimulation as SimulationCommand
    from PySide import QtWidgets
    from PySide6 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestLoadUI(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("LoadUiTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.component = self.assembly.newObject("App::Part", "Component")
        solid = self.component.newObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(10, 10, 10)
        self.component.Placement.Base = App.Vector(10, 20, 30)
        self.doc.recompute()
        self.active = patch.object(
            SimulationCommand.UtilsAssembly, "activeAssembly", return_value=self.assembly
        )
        self.active.start()
        self.simulation_panel = SimulationCommand.TaskAssemblyCreateSimulation()
        Gui.Control.showDialog(self.simulation_panel)
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if Gui.Control.activeDialog():
            self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
            QtWidgets.QApplication.processEvents()
        self.active.stop()
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve)

    def addLoad(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.component)
        LoadCommand.CommandCreateLoad().Activated()
        QtWidgets.QApplication.processEvents()
        loads = [obj for obj in self.simulation.Group if hasattr(obj, "LoadType")]
        self.assertEqual(len(loads), 1)
        return loads[0]

    def clickTaskButton(self, button):
        boxes = Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
        candidates = [box for box in boxes if box.button(button)]
        self.assertTrue(candidates, "Task dialog standard buttons were not found")
        candidates[-1].button(button).click()
        QtWidgets.QApplication.processEvents()

    @property
    def simulation(self):
        return self.simulation_panel.simFeaturePy

    def test_command_is_available_inside_and_outside_simulation_task(self):
        command = LoadCommand.CommandCreateLoad()
        self.assertTrue(command.IsActive())
        self.simulation_panel.accept()
        self.simulation_panel = None
        QtWidgets.QApplication.processEvents()
        self.assertTrue(command.IsActive())

    def test_constant_profile_has_one_authoritative_editor(self):
        import json
        import MotionProfile
        import ProfileEditor
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        field = form.findChild(ProfileEditor.ProfileField)
        for kind, unit in (("Force", "N"), ("Torque", "N mm")):
            form.findChild(QtWidgets.QComboBox, "TypeComboBox").setCurrentIndex(0 if kind == "Force" else 1)
            spec = MotionProfile.defaults(unit, "Constant")
            spec.update(quantity="Magnitude", initial=10)
            field.apply(spec)
            self.assertTrue(form.findChild(QtWidgets.QWidget, "MagnitudeSpinBox").isHidden())
            self.assertFalse(field.constant.isHidden())
            self.assertEqual(field.constant.value(), 10)
            field.constant.setValue(20)
            self.assertEqual(json.loads(load.ProfileData)["initial"], 20)
            self.assertAlmostEqual(MotionProfile.Profile(json.loads(load.ProfileData)).sample(0.5), 20)

    def test_constant_wrench_visual_sign(self):
        import MotionProfile

        load = self.addLoad()
        vp = load.ViewObject.Proxy

        def visual():
            if load.LoadType == "Torque":
                return tuple(vp.torqueArcCoordinates.point[0].getValue())
            return tuple(vp.transform.rotation.getValue().getValue())

        for kind, unit in (("Force", "N"), ("Torque", "N mm")):
            load.LoadType = kind
            load.Formula = ""
            setattr(load, kind, 10)
            positive = visual()
            setattr(load, kind, -10)
            negative = visual()
            self.assertNotEqual(positive, negative)
            for magnitude, expected in ((-10, negative), (10, positive), (-10, negative)):
                spec = MotionProfile.defaults(unit, "Constant")
                spec.update(quantity="Magnitude", initial=magnitude)
                MotionProfile.assign(load, spec)
                self.assertEqual(visual(), expected)
                self.assertAlmostEqual(
                    LoadCommand.Dynamics.constant_load_magnitude(load), magnitude
                )
            load.Formula = "-10"
            self.assertEqual(visual(), negative)
            load.Formula = "sin(time)"
            self.assertEqual(visual(), positive)
            load.ProfileData = "invalid JSON"
            self.assertEqual(visual(), positive)
            load.ProfileData = "null"
            self.assertEqual(visual(), positive)
            load.ProfileData = ""

    def test_noop_global_load_and_event_preserve_results(self):
        import json
        import SimulationEvents
        import CommandSimulationEvent
        Dynamics = LoadCommand.Dynamics
        load = Dynamics.create_load(self.assembly, "Force", self.component)
        LoadCommand.ViewProviderLoad(load.ViewObject)
        study = self.simulation
        other = Dynamics.create_study(self.assembly)
        data = {"SchemaVersion": 2, "Times": [0], "Bodies": {}}
        for button in (QtWidgets.QDialogButtonBox.Cancel, QtWidgets.QDialogButtonBox.Ok):
            for item in (study, other):
                Dynamics.save_results(item, data)
            snapshots = [item.ResultData for item in (study, other)]
            QtWidgets.QApplication.processEvents()
            LoadCommand.editLoad(load)
            QtWidgets.QApplication.processEvents()
            self.assertEqual([item.Status for item in (study, other)], ["Complete", "Complete"])
            self.clickTaskButton(button)
            self.simulation_panel = SimulationCommand.activeSimulationTask()
            self.assertEqual([item.ResultData for item in (study, other)], snapshots)
        event = SimulationEvents.create(study)
        event.Time = .0123456789
        event.Targets = [load]
        event.Actions = json.dumps([dict(kind="Deactivate", value=0, duration=.123456789)])
        original = (event.Time, event.Actions, event.Component)
        Dynamics.save_results(study, data)
        snapshot = study.ResultData
        CommandSimulationEvent.edit(study, event)
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(study.ResultData, snapshot)
        self.assertEqual((event.Time, event.Actions, event.Component), original)
        # A real edit must still invalidate both studies using a global input.
        load.Force = "20 N"
        self.assertEqual([item.Status for item in (study, other)], ["NotRun", "NotRun"])

    def test_load_type_roundtrip_preserves_zero_values_and_attachment(self):
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        selector = form.findChild(QtWidgets.QComboBox, "TypeComboBox")
        for index in (2, 3, 4):
            selector.setCurrentIndex(index)
            QtWidgets.QApplication.processEvents()
        load.Stiffness = "0 N/mm"
        load.RestLength = 0
        load.TorsionalStiffness = "0 N*mm/rad"
        load.BushingLinearStiffnessX = "0 N/mm"
        load.BushingAngularStiffnessY = "0 N*mm/rad"
        expected = App.Placement(App.Vector(4, 5, 6), App.Rotation(20, 30, 40))
        load.AttachmentJ = expected
        for index in (0, 2, 3, 4):
            selector.setCurrentIndex(index)
            QtWidgets.QApplication.processEvents()
            self.assertTrue(load.AttachmentJ.isSame(expected, 1e-9))
        self.assertEqual(load.Stiffness.Value, 0)
        self.assertEqual(load.RestLength.Value, 0)
        self.assertEqual(load.TorsionalStiffness.Value, 0)
        self.assertEqual(load.BushingLinearStiffnessX.Value, 0)
        self.assertEqual(load.BushingAngularStiffnessY.Value, 0)
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()
        self.assertTrue(load.AttachmentJ.isSame(expected, 1e-9))
        LoadCommand.editLoad(load)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(load.AttachmentJ.isSame(expected, 1e-9))
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        selector = form.findChild(QtWidgets.QComboBox, "TypeComboBox")
        for index in (0, 2, 3, 4):
            selector.setCurrentIndex(index)
            QtWidgets.QApplication.processEvents()
        self.assertEqual(load.Stiffness.Value, 0)
        self.assertEqual(load.RestLength.Value, 0)
        self.assertEqual(load.TorsionalStiffness.Value, 0)
        self.assertEqual(load.BushingLinearStiffnessX.Value, 0)
        self.assertEqual(load.BushingAngularStiffnessY.Value, 0)
        self.assertTrue(load.AttachmentJ.isSame(expected, 1e-9))
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_second_component_selectors_stay_synchronized(self):
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        selector = form.findChild(QtWidgets.QComboBox, "TypeComboBox")
        first = form.findChild(QtWidgets.QComboBox, "ReactionComponentComboBox")
        second = form.findChild(QtWidgets.QComboBox, "BushingReactionComponentComboBox")
        selector.setCurrentIndex(2)
        first.setCurrentIndex(1)
        selector.setCurrentIndex(4)
        self.assertEqual(second.currentIndex(), 1)
        self.assertEqual(load.BodyJ, self.component)
        second.setCurrentIndex(0)
        selector.setCurrentIndex(2)
        self.assertEqual(first.currentIndex(), 0)
        self.assertIsNone(load.BodyJ)

    def test_matrix_validation_keeps_invalid_text_and_blocks_accept(self):
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form.findChild(QtWidgets.QComboBox, "TypeComboBox").setCurrentIndex(4)
        form.findChild(QtWidgets.QCheckBox, "CoupledBushingCheckBox").setChecked(True)
        table = form.findChild(QtWidgets.QTableWidget, "BushingStiffnessMatrixTable")
        table.item(0, 0).setText("invalid")
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.assertEqual(table.item(0, 0).text(), "invalid")
        self.assertIsNone(SimulationCommand.activeSimulationTask())
        table.item(0, 0).setText("1")
        table.item(1, 1).setText("1")
        table.item(0, 1).setText("2")
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.assertIsNone(SimulationCommand.activeSimulationTask())
        table.item(0, 1).setText("0.5")
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()
        self.assertIsNotNone(self.simulation_panel)

    def test_matrix_validation_accepts_semidefinite_and_rejects_invalid(self):
        matrix = [0.0] * 36
        LoadCommand.validateBushingMatrix(matrix)
        matrix[0] = matrix[7] = matrix[1] = matrix[6] = 1
        LoadCommand.validateBushingMatrix(matrix)
        for value in (2, -2, float("inf"), float("nan")):
            with self.subTest(value=value):
                invalid = list(matrix)
                invalid[1] = invalid[6] = value
                with self.assertRaises(ValueError):
                    LoadCommand.validateBushingMatrix(invalid)
    def test_cancel_removes_load_and_reopens_simulation(self):
        load = self.addLoad()
        load_name = load.Name
        self.assertEqual(load.Name, "Force")
        self.assertEqual(load.Label, "Force")
        self.assertIn(load, self.simulation.Group)
        self.assertEqual(load.BodyI, self.component)
        self.assertTrue(load.hasExtension("Part::AttachExtensionPython"))
        self.assertTrue(load.hasExtension("App::SuppressibleExtensionPython"))
        self.assertTrue(
            load.ViewObject.hasExtension("Gui::ViewProviderSuppressibleExtensionPython")
        )
        self.assertNotIn("Enabled", load.PropertiesList)
        self.assertNotIn("Touched", load.State)
        self.assertNotIn("Touched", self.simulation.State)
        self.assertFalse(load.isDerivedFrom("Part::Feature"))

        content = Gui.Control.activeTaskDialog().getDialogContent()
        self.assertEqual(len(content), 2)
        self.assertIsNotNone(
            content[0].findChild(QtWidgets.QWidget, "TaskAssemblyCreateLoad")
        )
        self.assertEqual(content[1].metaObject().className(), "PartGui::TaskAttacher")
        component_label = content[0].findChild(QtWidgets.QLabel, "ComponentLabel")
        self.assertEqual(component_label.text(), "Component")
        self.assertIsNone(content[0].findChild(QtWidgets.QCheckBox, "EnabledCheckBox"))
        type_combo = content[0].findChild(QtWidgets.QComboBox, "TypeComboBox")
        type_combo.setCurrentIndex(1)
        self.assertEqual(load.LoadType, "Torque")
        self.assertEqual(load.Label, "Torque")
        self.assertEqual(load.ViewObject.Proxy.loadSwitch.whichChild.getValue(), 1)
        self.assertEqual(
            load.ViewObject.Proxy.torqueAxisStyle.linePattern.getValue(), 0x0F0F
        )
        positive_head = load.ViewObject.Proxy.torqueHeadTransform.translation.getValue()
        self.assertLess(positive_head[1], 0)
        load.Torque = "-10 N*mm"
        negative_head = load.ViewObject.Proxy.torqueHeadTransform.translation.getValue()
        self.assertGreater(negative_head[1], 0)
        formula = content[0].findChild(QtWidgets.QLineEdit, "FormulaLineEdit")
        formula.setText("2*sin(time)")
        self.assertEqual(load.Formula, "2*sin(time)")
        self.assertFalse(
            content[0].findChild(QtWidgets.QWidget, "MagnitudeSpinBox").isEnabled()
        )

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(self.doc.getObject(load_name))
        self.assertIsNotNone(SimulationCommand.activeSimulationTask())
        self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_repeated_load_tasks_keep_correct_widget_types(self):
        for _ in range(12):
            self.addLoad()
            content = Gui.Control.activeTaskDialog().getDialogContent()[0]
            combo = content.findChild(QtWidgets.QComboBox, "ComponentComboBox")
            self.assertIsNotNone(combo)
            self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
            self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_follower_and_coupled_matrix_editors(self):
        load = self.addLoad()
        content = Gui.Control.activeTaskDialog().getDialogContent()[0]
        checkbox = content.findChild(QtWidgets.QCheckBox, "FollowerCheckBox")
        checkbox.setChecked(True)
        self.assertTrue(load.Follower)
        combo = content.findChild(QtWidgets.QComboBox, "TypeComboBox")
        combo.setCurrentIndex(4)
        coupled = content.findChild(QtWidgets.QCheckBox, "CoupledBushingCheckBox")
        coupled.setChecked(True)
        table = content.findChild(QtWidgets.QTableWidget, "BushingStiffnessMatrixTable")
        table.item(0, 5).setText("0.5")
        self.assertEqual(load.BushingStiffnessMatrix[5], 0.5)
        self.assertEqual(load.BushingStiffnessMatrix[30], 0.5)
        self.assertEqual(table.item(5, 0).text(), "0.5")
        name = load.Name
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.assertIsNone(self.doc.getObject(name))
        self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_double_click_edits_existing_load_and_cancel_restores_it(self):
        load = self.addLoad()
        load.Force = "12 N"
        original_force = load.Force.Value
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        QtWidgets.QApplication.processEvents()
        self.simulation_panel = SimulationCommand.activeSimulationTask()

        self.assertTrue(load.ViewObject.Proxy.doubleClicked(load.ViewObject))
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(SimulationCommand.activeSimulationTask())
        content = Gui.Control.activeTaskDialog().getDialogContent()
        self.assertEqual(len(content), 2)
        load.Force = "27 N"

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        QtWidgets.QApplication.processEvents()
        self.assertAlmostEqual(load.Force.Value, original_force)
        self.assertIsNotNone(SimulationCommand.activeSimulationTask())
        self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_accept_keeps_attached_load_and_reopens_simulation(self):
        load = self.addLoad()
        load.AttachmentSupport = (self.component, [""])
        load.MapMode = "ObjectXY"
        load.AttachmentOffset = App.Placement(
            App.Vector(5, 6, 7), App.Rotation(App.Vector(1, 0, 0), 90)
        )
        load.ViewObject.ArrowSize = 42
        self.doc.recompute()
        expected_attachment = (
            SimulationCommand.UtilsAssembly.getGlobalPlacement((self.component, [""])).inverse()
            * load.Placement
        )
        expected_direction = load.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        arrow_position = load.ViewObject.Proxy.transform.translation.getValue()
        for actual, expected in zip(arrow_position, load.Placement.Base):
            self.assertAlmostEqual(actual, expected, delta=1e-6)

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        QtWidgets.QApplication.processEvents()
        saved = self.doc.getObject(load.Name)
        self.assertIsNotNone(saved)
        self.assertIn(saved, self.simulation.Group)
        self.assertTrue(saved.AttachmentI.isSame(expected_attachment, 1e-9))
        for actual, expected in zip(saved.Direction, expected_direction):
            self.assertAlmostEqual(actual, expected, delta=1e-9)
        self.assertEqual(saved.ViewObject.DisplayMode, "Load")
        self.assertAlmostEqual(saved.ViewObject.ArrowSize.Value, 42)
        self.assertIsNotNone(SimulationCommand.activeSimulationTask())
        self.simulation_panel = SimulationCommand.activeSimulationTask()

    def test_linear_spring_damper_editor_and_visual(self):
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        type_combo = form.findChild(QtWidgets.QComboBox, "TypeComboBox")
        type_combo.setCurrentIndex(2)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(load.LoadType, "SpringDamper")
        self.assertEqual(load.Label, "Spring-Damper")
        stack = form.findChild(QtWidgets.QStackedWidget, "LoadTypeStack")
        self.assertEqual(stack.currentWidget().objectName(), "SpringPage")
        margins = form.findChild(QtWidgets.QWidget, "SpringPage").layout().contentsMargins()
        self.assertEqual(
            tuple(getattr(margins, edge)() for edge in ("left", "top", "right", "bottom")),
            (0, 0, 0, 0),
        )
        self.assertIsNone(load.BodyJ)
        self.assertAlmostEqual(
            load.RestLength.Value, LoadCommand.Dynamics.spring_length(load)
        )
        self.assertEqual(load.ViewObject.Proxy.loadSwitch.whichChild.getValue(), 2)
        self.assertGreater(load.ViewObject.Proxy.springCoordinates.point.getNum(), 2)

        stiffness = form.findChild(QtWidgets.QAbstractSpinBox, "StiffnessSpinBox")
        damping = form.findChild(QtWidgets.QAbstractSpinBox, "DampingSpinBox")
        endpoint = form.findChild(QtWidgets.QWidget, "EndpointJX")
        stiffness.setFocus()
        QtWidgets.QApplication.processEvents()
        stiffness.lineEdit().selectAll()
        QtTest.QTest.keyClicks(stiffness.lineEdit(), "2 N/mm")
        damping.setFocus()
        QtWidgets.QApplication.processEvents()
        damping.lineEdit().selectAll()
        QtTest.QTest.keyClicks(damping.lineEdit(), "0.3 kg/s")
        type_combo.setFocus()
        QtWidgets.QApplication.processEvents()
        endpoint.setProperty("value", App.Units.Quantity("15 mm"))
        QtWidgets.QApplication.processEvents()
        self.assertAlmostEqual(load.Stiffness.Value, 2000)
        self.assertAlmostEqual(load.Damping.Value, 0.3)
        self.assertAlmostEqual(load.AttachmentJ.Base.x, 15)

        form.findChild(QtWidgets.QToolButton, "UseCurrentLengthButton").click()
        self.assertAlmostEqual(
            load.RestLength.Value,
            (load.AttachmentJ.Base - App.Vector(10, 20, 30)).Length,
        )
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.simulation_panel.form.loadList.item(0).text(), "Spring-Damper")

    def test_torsional_spring_damper_editor_and_visual(self):
        load = self.addLoad()
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form.findChild(QtWidgets.QComboBox, "TypeComboBox").setCurrentIndex(3)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(load.LoadType, "TorsionalSpringDamper")
        self.assertEqual(load.Label, "Torsional Spring-Damper")
        self.assertEqual(
            form.findChild(QtWidgets.QStackedWidget, "LoadTypeStack")
            .currentWidget()
            .objectName(),
            "SpringPage",
        )
        self.assertEqual(
            form.findChild(QtWidgets.QLabel, "StiffnessLabel").text(),
            "Angular stiffness (per radian)",
        )
        self.assertEqual(
            form.findChild(QtWidgets.QLabel, "DampingLabel").text(),
            "Angular damping (per radian)",
        )
        self.assertEqual(form.findChild(QtWidgets.QLabel, "RestLengthLabel").text(), "Free angle")
        self.assertFalse(form.findChild(QtWidgets.QLabel, "EndpointJLabel").isVisible())
        self.assertFalse(form.findChild(QtWidgets.QWidget, "EndpointJX").isVisible())
        self.assertEqual(load.ViewObject.Proxy.loadSwitch.whichChild.getValue(), 1)
        self.assertAlmostEqual(load.TorsionalStiffness.getValueAs("N*mm/rad"), 100)

        stiffness = form.findChild(QtWidgets.QAbstractSpinBox, "StiffnessSpinBox")
        damping = form.findChild(QtWidgets.QAbstractSpinBox, "DampingSpinBox")
        stiffness.setFocus()
        QtWidgets.QApplication.processEvents()
        stiffness.lineEdit().selectAll()
        QtTest.QTest.keyClicks(stiffness.lineEdit(), "2 N*mm")
        damping.setFocus()
        QtWidgets.QApplication.processEvents()
        damping.lineEdit().selectAll()
        QtTest.QTest.keyClicks(damping.lineEdit(), "0.3 N*mm*s")
        form.findChild(QtWidgets.QComboBox, "TypeComboBox").setFocus()
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.processEvents()
        load.AttachmentJ = App.Placement(
            App.Vector(10, 20, 30), App.Rotation(App.Vector(0, 0, 1), 30)
        )
        form.findChild(QtWidgets.QToolButton, "UseCurrentLengthButton").click()
        QtWidgets.QApplication.processEvents()
        self.assertAlmostEqual(load.TorsionalStiffness.getValueAs("N*mm/rad"), 2)
        self.assertAlmostEqual(load.TorsionalDamping.getValueAs("N*mm*s/rad"), 0.3)
        self.assertAlmostEqual(load.FreeAngle.getValueAs("deg"), 30)

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.simulation_panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(
            self.simulation_panel.form.loadList.item(0).text(),
            "Torsional Spring-Damper",
        )

    def test_bushing_editor_defaults_and_visual(self):
        load = self.addLoad()
        load.Placement = App.Placement(
            App.Vector(10, 20, 30), App.Rotation(App.Vector(1, 2, 3), 37)
        )
        form = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form.findChild(QtWidgets.QComboBox, "TypeComboBox").setCurrentIndex(4)
        QtWidgets.QApplication.processEvents()

        self.assertEqual(load.LoadType, "Bushing")
        self.assertEqual(load.Label, "Bushing")
        self.assertEqual(
            form.findChild(QtWidgets.QStackedWidget, "LoadTypeStack")
            .currentWidget()
            .objectName(),
            "BushingPage",
        )
        margins = form.findChild(QtWidgets.QWidget, "BushingPage").layout().contentsMargins()
        self.assertEqual(
            tuple(getattr(margins, edge)() for edge in ("left", "top", "right", "bottom")),
            (0, 0, 0, 0),
        )
        self.assertEqual(load.ViewObject.Proxy.loadSwitch.whichChild.getValue(), 3)
        self.assertTrue(
            LoadCommand.Dynamics.attachment_placement(load, "I").isSame(
                LoadCommand.Dynamics.attachment_placement(load, "J"), 1e-9
            )
        )
        for axis in "XYZ":
            self.assertAlmostEqual(
                getattr(load, "BushingLinearStiffness" + axis).getValueAs("N/mm"), 1
            )
            self.assertAlmostEqual(
                getattr(load, "BushingAngularStiffness" + axis).getValueAs("N*mm/rad"),
                100,
            )

        stiffness = form.findChild(
            QtWidgets.QAbstractSpinBox, "BushingLinearStiffnessX"
        )
        stiffness.setFocus()
        stiffness.lineEdit().selectAll()
        QtTest.QTest.keyClicks(stiffness.lineEdit(), "2 N/mm")
        form.findChild(QtWidgets.QComboBox, "TypeComboBox").setFocus()
        QtWidgets.QApplication.processEvents()
        self.assertAlmostEqual(load.BushingLinearStiffnessX.getValueAs("N/mm"), 2)

        load.AttachmentJ.Base = App.Vector(1, 2, 3)
        form.findChild(QtWidgets.QPushButton, "UseCurrentPoseButton").click()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(
            LoadCommand.Dynamics.attachment_placement(load, "I").isSame(
                LoadCommand.Dynamics.attachment_placement(load, "J"), 1e-9
            )
        )
