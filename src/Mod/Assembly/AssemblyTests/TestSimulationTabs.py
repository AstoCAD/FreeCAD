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

"""Tabbed Simulation task and prescribed-motion child-task regressions."""

import unittest
from unittest.mock import patch

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import CommandCreateLoad
    import CommandCreateContact
    import CommandCreateInitialVelocity
    import CommandCreateFriction
    import CommandCreateSimulation as SimulationCommand
    import Dynamics
    import JointObject
    import UtilsAssembly
    from PySide import QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestSimulationTabs(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("SimulationTabsTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.first = self.assembly.newObject("Part::Feature", "First")
        self.second = self.assembly.newObject("Part::Feature", "Second")
        self.first.Shape = Part.makeBox(10, 10, 10)
        self.second.Shape = Part.makeBox(10, 10, 10)
        joints = self.assembly.newObject("Assembly::JointGroup", "Joints")
        self.joint = joints.newObject("App::FeaturePython", "Slider")
        JointObject.Joint(self.joint, JointObject.JointTypes.index("Slider"))
        self.joint.Detach1 = self.joint.Detach2 = True
        self.joint.Reference1 = (self.first, [""])
        self.joint.Reference2 = (self.second, [""])
        self.doc.recompute()
        self.active = patch.object(
            SimulationCommand.UtilsAssembly, "activeAssembly", return_value=self.assembly
        )
        self.active.start()
        self.panel = SimulationCommand.TaskAssemblyCreateSimulation()
        Gui.Control.showDialog(self.panel)
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if Gui.Control.activeDialog():
            self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.active.stop()
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve)

    def clickTaskButton(self, button):
        boxes = Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
        candidates = [box for box in boxes if box.button(button)]
        self.assertTrue(candidates)
        candidates[-1].button(button).click()
        QtWidgets.QApplication.processEvents()

    def test_tabs_and_menu_only_commands(self):
        tabs = self.panel.form.tabWidget
        self.assertEqual(
            [tabs.tabText(i) for i in range(tabs.count())],
            ["Settings", "Motions", "Loads", "Initial", "Contacts", "Friction", "Events", "Results"],
        )
        self.assertTrue(all(not tabs.tabIcon(i).isNull() for i in range(tabs.count())))
        outer_margins = self.panel.form.layout().contentsMargins()
        self.assertEqual(
            tuple(
                getattr(outer_margins, edge)()
                for edge in ("left", "top", "right", "bottom")
            ),
            (0, 0, 0, 0),
        )
        for page in (
            self.panel.form.settingsTab,
            self.panel.form.motionsTab,
            self.panel.form.loadsTab,
            self.panel.form.initialTab,
            self.panel.form.contactsTab,
            self.panel.form.resultsTab,
        ):
            margins = page.layout().contentsMargins()
            self.assertEqual(
                tuple(getattr(margins, edge)() for edge in ("left", "top", "right", "bottom")),
                (6, 6, 6, 6),
            )
        self.assertTrue(Gui.Command.get("Assembly_CreateMotion").isActive())
        self.assertTrue(Gui.Command.get("Assembly_CreateLoad").isActive())
        self.assertTrue(Gui.Command.get("Assembly_CreateInitialVelocity").isActive())
        self.assertTrue(Gui.Command.get("Assembly_CreateContact").isActive())
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)
        for label in (
            self.panel.form.ResultCategoryLabel,
            self.panel.form.ResultEntityLabel,
            self.panel.form.ResultQuantityLabel,
        ):
            self.assertTrue(label.isHidden())
        simulation_group = next(
            obj
            for obj in self.assembly.OutList
            if obj.TypeId == "Assembly::SimulationGroup"
        )
        self.assertNotIn("Touched", simulation_group.State)

    def test_open_and_accept_do_not_touch_simulation(self):
        simulation = self.panel.simFeaturePy
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.assertNotIn("Touched", simulation.State)
        self.assertTrue(simulation.ViewObject.Proxy.doubleClicked(simulation.ViewObject))
        QtWidgets.QApplication.processEvents()
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertNotIn("Touched", simulation.State)

    def test_friction_tab_creates_simulation_local_object(self):
        self.panel.form.AddFrictionButton.click()
        QtWidgets.QApplication.processEvents()
        friction = next(
            obj for obj in self.panel.simFeaturePy.Group if hasattr(obj, "FrictionModel")
        )
        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = task.findChild(QtWidgets.QWidget, "TaskAssemblyCreateFriction")
        self.assertIsNotNone(form)
        self.assertEqual(form.JointComboBox.currentData(), self.joint)
        form.ModelComboBox.setCurrentIndex(1)
        form.StaticCoefficientSpinBox.setValue(0.35)
        form.DynamicCoefficientSpinBox.setValue(0.25)
        self.assertEqual(friction.FrictionModel, "Reaction based")
        self.assertAlmostEqual(friction.StaticCoefficient, 0.35)
        self.assertAlmostEqual(friction.DynamicCoefficient, 0.25)
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.panel.form.frictionList.count(), 1)

    def test_create_edit_and_remove_motion_through_task_panels(self):
        self.panel.form.AddMotionButton.click()
        QtWidgets.QApplication.processEvents()
        motions = [obj for obj in self.panel.simFeaturePy.Group if hasattr(obj, "MotionType")]
        self.assertEqual(len(motions), 1)
        motion = motions[0]
        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = task.findChild(QtWidgets.QWidget, "TaskAssemblyCreateMotion")
        self.assertIsNotNone(form)
        self.assertEqual(form.JointComboBox.currentData(), self.joint)
        self.assertEqual(form.MotionTypeComboBox.currentText(), "Linear")
        self.assertTrue(motion.hasExtension("App::SuppressibleExtensionPython"))
        self.assertTrue(
            motion.ViewObject.hasExtension("Gui::ViewProviderSuppressibleExtensionPython")
        )
        self.assertNotIn("Touched", motion.State)
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)
        form.FormulaLineEdit.setText("initialValue + 12*time")
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.panel.form.tabWidget.currentWidget().objectName(), "motionsTab")
        self.assertEqual(self.panel.form.motionList.count(), 1)
        self.assertEqual(motion.Formula, "initialValue + 12*time")
        self.assertNotIn("Touched", motion.State)
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)

        self.assertTrue(motion.ViewObject.Proxy.doubleClicked(motion.ViewObject))
        QtWidgets.QApplication.processEvents()
        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
        task.findChild(QtWidgets.QLineEdit, "FormulaLineEdit").setText("99*time")
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.panel.form.tabWidget.currentWidget().objectName(), "motionsTab")
        self.assertEqual(motion.Formula, "initialValue + 12*time")

        motion_name = motion.Name
        self.panel.form.motionList.setCurrentRow(0)
        self.panel.form.RemoveMotionButton.click()
        self.assertIsNone(self.doc.getObject(motion_name))
        self.assertEqual(self.panel.form.motionList.count(), 0)

    def test_loads_tab_tracks_add_and_remove(self):
        self.panel.form.AddLoadButton.click()
        QtWidgets.QApplication.processEvents()
        load = next(obj for obj in self.panel.simFeaturePy.Group if hasattr(obj, "LoadType"))
        self.assertNotIn("Touched", load.State)
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.panel.form.tabWidget.currentWidget().objectName(), "loadsTab")
        self.assertEqual(self.panel.form.loadList.count(), 1)
        self.assertEqual(self.panel.form.loadList.item(0).text(), "Force")
        load_name = load.Name
        self.panel.form.loadList.setCurrentRow(0)
        self.panel.form.RemoveLoadButton.click()
        self.assertIsNone(self.doc.getObject(load_name))
        self.assertEqual(self.panel.form.loadList.count(), 0)

    def test_global_inputs_are_marked_in_simulation_lists(self):
        global_load = Dynamics.create_load(self.assembly, "Force", self.first)
        CommandCreateLoad.ViewProviderLoad(global_load.ViewObject)
        self.panel.onInputsChanged()
        self.assertEqual(self.panel.form.loadList.count(), 1)
        self.assertEqual(self.panel.form.loadList.item(0).text(), "Force (global)")
        global_load.Suppressed = True
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.panel.form.loadList.item(0).text(), "Force (global) (suppressed)")
        global_load.Suppressed = False
        QtWidgets.QApplication.processEvents()
        self.assertEqual(self.panel.form.loadList.item(0).text(), "Force (global)")

    def test_suppressed_initial_velocities_do_not_reserve_types(self):
        for kind in ("Linear", "Angular"):
            initial = Dynamics.create_initial_velocity(self.panel.simFeaturePy, kind, self.second)
            initial.Suppressed = True
        self.assertEqual(CommandCreateInitialVelocity._available_types(self.panel.simFeaturePy, self.second), ["Linear", "Angular"])
        initial.Suppressed = False
        self.assertEqual(CommandCreateInitialVelocity._available_types(self.panel.simFeaturePy, self.second), ["Linear"])

    def test_suppressed_velocity_editor_retains_its_current_type(self):
        study = self.panel.simFeaturePy
        initial = Dynamics.create_initial_velocity(study, "Angular", self.second)
        CommandCreateInitialVelocity.ViewProviderInitialVelocity(initial.ViewObject)
        initial.Suppressed = True
        for kind in ("Linear", "Angular"):
            Dynamics.create_initial_velocity(study, kind, self.second)
        self.assertEqual(CommandCreateInitialVelocity._available_types(study, self.second), [])
        self.assertEqual(CommandCreateInitialVelocity._available_types(study, self.second, initial), ["Angular"])
        task = CommandCreateInitialVelocity.TaskAssemblyCreateInitialVelocity(initial, study)
        try:
            self.assertEqual(task.form.ComponentComboBox.currentData(), self.second)
            self.assertEqual(task.form.TypeComboBox.currentData(), "Angular")
            self.assertEqual(task.form.VelocityLabel.text(), "Angular velocity")
            self.assertTrue(initial.Suppressed)
            self.assertEqual(initial.InitialVelocityType, "Angular")
        finally:
            task.form.deleteLater()

    def test_simulation_drop_rejects_foreign_assemblies(self):
        study = self.panel.simFeaturePy
        foreign_assembly = self.doc.addObject("Assembly::AssemblyObject", "ForeignAssembly")
        foreign = Dynamics.create_study(foreign_assembly)
        SimulationCommand.ViewProviderSimulation(foreign.ViewObject)
        own_group = UtilsAssembly.getSimulationGroup(self.assembly)
        foreign_group = UtilsAssembly.getSimulationGroup(foreign_assembly)
        inputs = [
            Dynamics.create_load(study, "Force", self.first),
            SimulationCommand._createMotion(study, self.joint),
            Dynamics.create_initial_velocity(study, "Linear", self.second),
            Dynamics.create_contact(study, self.first, self.second),
            Dynamics.create_friction(study, self.joint),
        ]
        for obj in inputs:
            with self.subTest(input=obj.Name):
                self.assertTrue(study.ViewObject.Proxy.canDropObject(obj))
                self.assertFalse(foreign.ViewObject.Proxy.canDropObject(obj))
                self.assertTrue(own_group.ViewObject.canDropObject(obj))
                self.assertFalse(foreign_group.ViewObject.canDropObject(obj))
                with self.assertRaises(ValueError):
                    foreign.ViewObject.Proxy.dropObject(None, obj)
                with self.assertRaises((ValueError, RuntimeError)):
                    foreign_group.ViewObject.dropObject(obj)
                self.assertEqual(Dynamics.input_owner(obj), study)
        obj = inputs[0]
        study.ViewObject.Proxy.dragObject(None, obj)
        own_group.ViewObject.dropObject(obj)
        self.assertEqual(Dynamics.input_owner(obj), own_group)
        self.assertTrue(study.ViewObject.Proxy.canDropObject(obj))
        self.assertFalse(foreign.ViewObject.Proxy.canDropObject(obj))
        own_group.ViewObject.dragObject(obj)
        study.ViewObject.Proxy.dropObject(None, obj)
        self.assertEqual(Dynamics.input_owner(obj), study)

    def test_global_deletion_requires_confirmation(self):
        load = Dynamics.create_load(self.assembly, "Force", self.first)
        name = load.Name
        self.panel.onInputsChanged()
        self.panel.form.loadList.setCurrentRow(0)
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No) as question:
            self.panel.deleteSelectedLoads()
            self.assertIsNotNone(self.doc.getObject(name))
            self.assertIn("every simulation", question.call_args.args[2])
        with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
            self.panel.deleteSelectedLoads()
            self.assertIsNone(self.doc.getObject(name))

    def test_suppressed_event_status_updates_in_open_task(self):
        import SimulationEvents
        event = SimulationEvents.create(self.panel.simFeaturePy)
        event.Suppressed = True
        QtWidgets.QApplication.processEvents()
        self.assertIn("Suppressed", self.panel.eventList.item(0).text())
        self.assertNotIn("Not triggered", self.panel.eventList.item(0).text())
        event.Suppressed = False
        QtWidgets.QApplication.processEvents()
        self.assertIn("Not generated", self.panel.eventList.item(0).text())

    def test_friction_models_follow_joint_type(self):
        revolute = self.joint.InList[0].newObject("App::FeaturePython", "Revolute")
        JointObject.Joint(revolute, JointObject.JointTypes.index("Revolute"))
        revolute.Detach1 = revolute.Detach2 = True
        revolute.Reference1 = (self.first, [""])
        revolute.Reference2 = (self.second, [""])
        self.doc.recompute()
        friction = Dynamics.create_friction(self.panel.simFeaturePy, self.joint)
        CommandCreateFriction.ViewProviderFriction(friction.ViewObject)
        task = CommandCreateFriction.TaskAssemblyCreateFriction(friction, self.panel.simFeaturePy)
        try:
            models = task.form.ModelComboBox
            self.assertEqual(models.findData("Rolling resistance"), -1)
            self.assertEqual(models.findData("Thrust bearing"), -1)
            task.form.JointComboBox.setCurrentIndex(task.form.JointComboBox.findData(revolute))
            self.assertGreaterEqual(models.findData("Rolling resistance"), 0)
            models.setCurrentIndex(models.findData("Rolling resistance"))
            task.form.JointComboBox.setCurrentIndex(task.form.JointComboBox.findData(self.joint))
            self.assertEqual(models.findData("Rolling resistance"), -1)
            self.assertEqual(friction.FrictionModel, "Specified resistance")
        finally:
            task.form.deleteLater()

    def test_contacts_tab_creates_simulation_local_contact(self):
        self.panel.form.AddContactButton.click()
        QtWidgets.QApplication.processEvents()
        contact = next(
            obj for obj in self.panel.simFeaturePy.Group if hasattr(obj, "ContactType")
        )
        self.assertEqual(
            CommandCreateContact._contact_owner(contact), self.panel.simFeaturePy
        )
        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = task.findChild(QtWidgets.QWidget, "TaskAssemblyCreateContact")
        self.assertIsNotNone(form)
        self.assertEqual(form.ScopeValueLabel.text(), "This simulation")
        self.assertEqual(form.ModeComboBox.currentIndex(), 0)
        self.assertTrue(form.GeneralWarningLabel.isHidden())
        self.assertTrue(form.FirstComponentComboBox.isEnabled())
        self.assertTrue(form.FrictionGroupBox.isCheckable())
        self.assertFalse(form.FrictionGroupBox.isChecked())
        self.assertFalse(form.StaticFrictionSpinBox.isEnabled())
        form.FrictionGroupBox.setChecked(True)
        form.StaticFrictionSpinBox.setValue(0.7)
        form.DynamicFrictionSpinBox.setValue(0.4)
        QtWidgets.QApplication.processEvents()
        self.assertTrue(contact.FrictionEnabled)
        self.assertAlmostEqual(contact.StaticFriction, 0.7)
        self.assertAlmostEqual(contact.DynamicFriction, 0.4)
        self.assertTrue(form.TransitionVelocitySpinBox.isEnabled())

        form.ModeComboBox.setCurrentIndex(1)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(contact.Mode, "General collision detection")
        self.assertFalse(form.GeneralWarningLabel.isHidden())
        self.assertFalse(form.FirstComponentComboBox.isEnabled())
        self.assertIn("very small assemblies", form.GeneralWarningLabel.text())
        self.assertNotIn("Touched", contact.State)
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(
            self.panel.form.tabWidget.currentWidget().objectName(), "contactsTab"
        )
        self.assertEqual(self.panel.form.contactList.count(), 1)
        self.assertEqual(self.panel.form.contactList.item(0).text(), "Contact")

        contact_name = contact.Name
        self.panel.form.contactList.setCurrentRow(0)
        self.panel.form.RemoveContactButton.click()
        self.assertIsNone(self.doc.getObject(contact_name))
        self.assertEqual(self.panel.form.contactList.count(), 0)

    def test_toolbar_contact_outside_simulation_is_assembly_wide(self):
        simulation = self.panel.simFeaturePy
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        Gui.Selection.addSelection(self.first)
        Gui.Selection.addSelection(self.second)

        Gui.runCommand("Assembly_CreateContact")
        QtWidgets.QApplication.processEvents()
        sim_group = UtilsAssembly.getSimulationGroup(self.assembly)
        contact = next(obj for obj in sim_group.Group if hasattr(obj, "ContactType"))
        self.assertNotIn(contact, simulation.Group)
        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = task.findChild(QtWidgets.QWidget, "TaskAssemblyCreateContact")
        self.assertIsNotNone(form)
        self.assertEqual(
            form.ScopeValueLabel.text(), "Assembly (dragging and all simulations)"
        )

        name = contact.Name
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.assertIsNone(self.doc.getObject(name))

    def test_prescribed_motion_without_gravity_populates_results(self):
        joint_group = self.joint.InList[0]
        grounding = joint_group.newObject("App::FeaturePython", "Grounding")
        JointObject.GroundedJoint(grounding, self.first)
        motion = SimulationCommand._createMotion(self.panel.simFeaturePy, self.joint)
        motion.Formula = "initialValue + 5*time"

        self.assertFalse(self.panel.simFeaturePy.GravityEnabled)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.panel.runKinematics()
            warning.assert_not_called()

        self.assertEqual(self.panel.simFeaturePy.Status, "Complete")
        self.assertTrue(self.panel.simFeaturePy.ResultData)
        self.assertIsNotNone(self.panel.resultData)
        self.assertIn(self.second.Name, self.panel.resultData["Bodies"])
        self.assertEqual(self.panel.resultData["MassProperties"], {})
        self.assertEqual(self.panel.form.ResultCategoryComboBox.currentData(), "Bodies")
        self.assertEqual(self.panel.form.ResultCategoryComboBox.currentText(), "Component motion")
        self.assertFalse(self.panel.form.NoResultsLabel.isVisible())
        for label in (
            self.panel.form.ResultCategoryLabel,
            self.panel.form.ResultEntityLabel,
            self.panel.form.ResultQuantityLabel,
        ):
            self.assertFalse(label.isHidden())
        self.assertGreater(self.panel.form.ResultTable.rowCount(), 1)

    def test_invalidation_stops_playback_and_clears_results(self):
        self.test_prescribed_motion_without_gravity_populates_results()
        self.panel.animationTimerStartForward()
        self.assertTrue(self.panel.animationTimer.isActive())
        self.panel.onTimeEndChanged(None)
        self.assertFalse(self.panel.animationTimer.isActive())
        self.assertTrue(self.panel.form.groupBox_player.isHidden())
        self.assertTrue(self.panel.form.SaveAnimationButton.isHidden())
        self.assertIsNone(self.panel.resultData)
        self.panel.runKinematics()
        motion = next(obj for obj in self.panel.simFeaturePy.Group if hasattr(obj, "MotionType"))
        motion.Suppressed = True
        QtWidgets.QApplication.processEvents()
        self.assertIsNone(self.panel.resultData)
        self.assertEqual(self.panel.form.ResultTable.rowCount(), 0)
        self.assertTrue(self.panel.form.ExportResultButton.isHidden())
        self.assertTrue(self.panel.form.groupBox_player.isHidden())
        self.assertEqual(self.panel.frameTimes, {})

    def test_playback_includes_both_endpoints(self):
        panel = self.panel
        panel.currentFrm = panel.startFrm = 1
        panel.endFrm = 3
        panel.startTime = 0
        panel.deltaTime = 1
        for direction, expected in ((1, [1, 2, 3, 1, 2, 3]), (-1, [1, 3, 2, 1, 3, 2])):
            panel.direction = direction
            frames = []
            with patch.object(panel, "setFrameValue", side_effect=frames.append):
                for time in range(6):
                    with patch.object(SimulationCommand.time, "time", return_value=time):
                        panel.playAnimation()
            self.assertEqual(frames, expected)

    def test_saved_results_play_without_solver_cache(self):
        # Synthetic saved data needs no solver generation, just as after restore.
        study = self.panel.simFeaturePy
        times = [0.0, 0.003, 0.021]
        poses = [[0, 0, z, 0, 0, 0, 1] for z in (0, 7, 19)]
        data = {"SchemaVersion": 2, "Times": times, "Bodies": {
            self.second.Name: {"Placements": poses},
        }}
        Dynamics.save_results(study, data)
        self.panel.accept()
        QtWidgets.QApplication.processEvents()
        self.panel = SimulationCommand.TaskAssemblyCreateSimulation(study)
        Gui.Control.showDialog(self.panel)
        self.assertFalse(self.panel.form.groupBox_player.isHidden())
        self.assertEqual(self.panel.frameTimes, dict(enumerate(times, 1)))
        self.assertEqual(self.panel.form.frameSlider.maximum(), 3)
        self.panel.setFrameValue(3)
        self.assertAlmostEqual(self.second.Placement.Base.z, 19)
        self.assertEqual(self.panel.form.FrameTimeLabel.text(), "0.021 s")
        self.panel.setFrameValue(2)
        self.assertAlmostEqual(self.second.Placement.Base.z, 7)
        self.panel.setFrameValue(3)
        self.assertAlmostEqual(self.second.Placement.Base.z, 19)
