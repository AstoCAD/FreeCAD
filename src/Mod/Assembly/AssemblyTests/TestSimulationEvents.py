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

"""Analytic event integration and run-isolation regressions."""
import json
import unittest

import FreeCAD as App
import Dynamics
import SimulationEvents as Events


class TestSimulationEvents(unittest.TestCase):
    def setUp(self):
        from AssemblyTests.TestDynamics import TestDynamics
        self.fixture = TestDynamics()
        self.fixture.setUp()
        self.body = self.fixture.box()
        self.study = self.fixture.study(False)
        self.study.MaximumStep = "0.007 s"
        self.study.Tolerance = 1e-10

    def tearDown(self):
        self.fixture.tearDown()

    def event(self, target, kind="Deactivate", time=.035):
        event = Events.create(self.study)
        event.Time = time
        event.Targets = [target]
        event.Actions = json.dumps([dict(kind=kind, value=0, duration=.02)])
        return event

    def force(self, owner=None):
        load = Dynamics.create_load(owner or self.study, "Force", self.body)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        load.Force = "0.006 N"  # 6 g component: 1000 mm/s^2.
        return load

    def test_timed_force_off_exact_boundary_and_run_isolation(self):
        load = self.force(self.fixture.assembly)
        event = self.event(load)
        original = (load.Suppressed, load.Formula, load.Force.Value)
        for _ in range(2):
            data = Dynamics.run(self.study)
            self.assertEqual(len(data["EventLog"]), 1)
            self.assertAlmostEqual(data["EventLog"][0]["Time"], .035, places=9)
            self.assertTrue(any(abs(t-.035) < 1e-9 for t in data["Times"]))
            self.assertTrue(all(b > a for a,b in zip(data["Times"], data["Times"][1:])))
            for time, pose, velocity in zip(data["Times"], data["Bodies"][self.body.Name]["Placements"], data["Bodies"][self.body.Name]["Velocity"]):
                powered = min(time, .035)
                self.assertAlmostEqual(pose[2], 500*powered**2+1000*powered*max(0,time-.035), delta=2e-4)
                self.assertAlmostEqual(velocity[2], 1000*powered, delta=2e-3)
            self.assertEqual(original, (load.Suppressed, load.Formula, load.Force.Value))
        self.assertNotIn("Touched", event.State)

    def test_suppressed_load_activation_and_delayed_deactivation(self):
        load = self.force()
        load.Suppressed = True
        first = self.event(load, "Activate", .023)
        second = self.event(load)
        second.Trigger = "After event"
        second.PreviousEvent = first
        second.Delay = .031
        data = Dynamics.run(self.study)
        self.assertEqual([e["Event"] for e in data["EventLog"]], [first.Name, second.Name])
        self.assertAlmostEqual(data["EventLog"][1]["Time"], .054, places=9)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 31, delta=.002)
        self.assertTrue(load.Suppressed)

    def test_threshold_crossing_between_output_frames(self):
        load = self.force()
        event = self.event(load)
        event.Trigger = "Measurement"
        event.Component = self.body
        event.Quantity = "Position Z"
        event.Threshold = .6125  # z=500*t^2 -> t=.035 s.
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["EventLog"][0]["Time"], .035, delta=2e-6)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 35, delta=.003)

    def test_event_does_not_bypass_joint_stop(self):
        ground = self.fixture.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        joint = self.fixture.joint("Slider", ground, self.body)
        joint.EnableLengthMax = True
        joint.LengthMax = "3.5 mm"
        initial = Dynamics.create_initial_velocity(self.study, "Linear", self.body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.LinearVelocity = "100 mm/s"
        load = self.force()
        load.Force = "0 N"
        self.event(load, time=.035)
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Placements"][-1][2], 3.5, delta=.001)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 0, delta=.002)

    def test_initial_condition_and_zero_delay_cascade(self):
        load = self.force()
        first = self.event(load)
        first.Trigger = "Measurement"
        first.Component = self.body
        first.Quantity = "Position Z"
        first.Threshold = -1
        first.FireInitially = True
        second = self.event(load, "Activate")
        second.Trigger = "After event"
        second.PreviousEvent = first
        data = Dynamics.run(self.study)
        self.assertEqual([entry["Time"] for entry in data["EventLog"]], [0, 0])
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 100, delta=.002)

    def motion(self):
        from CommandCreateSimulation import Motion
        ground = self.fixture.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        joint = self.fixture.joint("Slider", ground, self.body)
        motion = self.fixture.doc.addObject("App::FeaturePython", "Motion")
        Motion(motion, "Linear", joint, "initialValue+100*time")
        self.study.addObject(motion)
        return motion

    def test_motion_release_keeps_velocity(self):
        motion = self.motion()
        self.event(motion)
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Placements"][-1][2], 10, delta=.001)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 100, delta=.002)
        self.assertFalse(motion.Suppressed)

    def test_motion_ramp_stops_without_position_jump(self):
        motion = self.motion()
        self.event(motion, "Ramp", .03)
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Placements"][-1][2], 4, delta=.002)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 0, delta=.002)
        self.assertEqual(motion.Formula, "initialValue+100*time")

    def test_ramp_load_impulse(self):
        load = self.force()
        self.event(load, "Ramp", .03)
        data = Dynamics.run(self.study)
        # 0.03 s at full force + 0.02 s symmetric quintic ramp = 0.04 s impulse.
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 40, delta=.01)

    def test_reactivate_suppressed_motor_preserves_position(self):
        motion = self.motion()
        motion.Suppressed = True
        self.event(motion, "Activate", .03)
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Placements"][-1][2], 7, delta=.002)
        self.assertTrue(motion.Suppressed)

    def test_start_saved_force_profile_and_preserve_definition(self):
        import MotionProfile
        load = self.force()
        spec = MotionProfile.defaults("N")
        spec.update(quantity="Magnitude", segments=[[.02, .006, "Smooth"]])
        MotionProfile.assign(load, spec)
        load.Suppressed = True
        self.event(load, "Start profile", .02)
        original = load.ProfileData, load.Formula
        data = Dynamics.run(self.study)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["Velocity"][-1][2], 70, delta=.02)
        self.assertEqual((load.ProfileData, load.Formula), original)
        self.assertTrue(load.Suppressed)

    def test_speed_crossing_caused_by_motor_activation(self):
        motion = self.motion()
        motion.Suppressed = True
        first = self.event(motion, "Activate", .03)
        load = self.force()
        load.Force = "0 N"
        second = self.event(load)
        second.Trigger = "Measurement"
        second.Component = self.body
        second.Quantity = "Speed"
        second.Threshold = 50
        data = Dynamics.run(self.study)
        self.assertEqual([e["Event"] for e in data["EventLog"]], [first.Name, second.Name])
        self.assertEqual([e["Time"] for e in data["EventLog"]], [.03, .03])

    def test_angular_motor_ramp(self):
        from CommandCreateSimulation import Motion
        ground = self.fixture.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        joint = self.fixture.joint("Revolute", ground, self.body)
        motion = self.fixture.doc.addObject("App::FeaturePython", "Motion")
        Motion(motion, "Angular", joint, "initialValue+time")
        self.study.addObject(motion)
        self.event(motion, "Ramp", .03)
        data = Dynamics.run(self.study)
        pose = data["Bodies"][self.body.Name]["Placements"][-1]
        rotation = App.Rotation(*pose[3:])
        self.assertAlmostEqual(rotation.Angle, .04, delta=.0002)
        self.assertAlmostEqual(data["Bodies"][self.body.Name]["AngularVelocity"][-1][2], 0, delta=.002)

    def test_repeated_threshold_crossing(self):
        motion = self.motion()
        motion.Formula = "initialValue+10*sin(50*pi*time)"
        load = self.force()
        load.Force = "0 N"
        event = self.event(load)
        event.Trigger = "Measurement"
        event.Component = self.body
        event.Quantity = "Position Z"
        event.Repeat = True
        event.Hysteresis = 1
        self.study.MaximumStep = "0.001 s"
        data = Dynamics.run(self.study)
        self.assertEqual(len(data["EventLog"]), 2)
        for entry, expected in zip(data["EventLog"], (.04, .08)):
            self.assertAlmostEqual(entry["Time"], expected, delta=1e-6)

    def test_validation_and_analysis_mode(self):
        load = self.force()
        a = self.event(load)
        b = self.event(load)
        a.Trigger = b.Trigger = "After event"
        a.PreviousEvent, b.PreviousEvent = b, a
        with self.assertRaisesRegex(ValueError, "cycle"):
            Events.describe(self.study)
        self.study.AnalysisType = "Kinematics"
        with self.assertRaisesRegex(ValueError, "events"):
            Dynamics.analysis_type(self.study)

    def test_task_fields_and_cancel(self):
        if not App.GuiUp:
            self.skipTest("GUI required")
        import CommandSimulationEvent
        load = self.force()
        event = self.event(load)
        suppressed = self.event(load)
        suppressed.Suppressed = True
        panel = CommandSimulationEvent.Task(self.study, event)
        self.assertEqual(panel.table.rowCount(), 1)
        self.assertEqual(panel.previous.findData(suppressed), -1)
        self.assertEqual(panel.reference.findData(panel.component.currentData()), -1)
        panel.trigger.setCurrentIndex(panel.trigger.findData("After event"))
        self.assertTrue(panel.hysteresis.isHidden())
        self.assertTrue(panel.advanced.layout().labelForField(panel.hysteresis).isHidden())
        self.assertTrue(panel.initial.isHidden())
        self.assertEqual(panel.repeat.text(), "Repeat for each occurrence")
        panel.trigger.setCurrentIndex(panel.trigger.findData("Measurement"))
        self.assertFalse(panel.hysteresis.isHidden())
        self.assertFalse(panel.initial.isHidden())
        self.assertFalse(panel.measurement.isHidden())
        self.assertTrue(panel.time.isHidden())
        self.assertEqual(event.Trigger, "Time", "The editor should defer changes until acceptance")
        panel.form.deleteLater()

    def test_task_filters_action_targets(self):
        if not App.GuiUp:
            self.skipTest("GUI required")
        import CommandSimulationEvent
        import MotionProfile
        load = self.force()
        spring = Dynamics.create_load(self.study, "SpringDamper", self.body)
        event = self.event(load)
        panel = CommandSimulationEvent.Task(self.study, event)
        try:
            action = panel.table.cellWidget(0, 0)
            target = panel.table.cellWidget(0, 1)
            self.assertGreaterEqual(target.findData(spring), 0)
            action.setCurrentIndex(action.findData("Ramp"))
            self.assertEqual(target.findData(spring), -1)
            self.assertGreaterEqual(target.findData(load), 0)
            action.setCurrentIndex(action.findData("Start profile"))
            self.assertEqual(target.count(), 0)
            spec = MotionProfile.defaults("N")
            spec["quantity"] = "Magnitude"
            MotionProfile.assign(load, spec)
            action.setCurrentIndex(action.findData("Activate"))
            action.setCurrentIndex(action.findData("Start profile"))
            self.assertEqual(target.currentData(), load)
            self.assertEqual(target.count(), 1)
        finally:
            panel.form.deleteLater()

    def test_unavailable_event_target_is_not_replaced(self):
        if not App.GuiUp:
            self.skipTest("GUI required")
        import CommandSimulationEvent
        import MotionProfile
        load, other = self.force(), self.force()
        spec = MotionProfile.defaults("N")
        spec["quantity"] = "Magnitude"
        MotionProfile.assign(other, spec)
        event = self.event(load, "Start profile")
        panel = CommandSimulationEvent.Task(self.study, event)
        try:
            target = panel.table.cellWidget(0, 1)
            self.assertEqual(target.count(), 1)
            self.assertEqual(target.currentIndex(), -1)
            self.assertFalse(panel.accept())
            self.assertEqual(event.Targets, [load])
        finally:
            panel.form.deleteLater()

    def test_rejected_event_edit_preserves_results_and_allows_recovery(self):
        if not App.GuiUp:
            self.skipTest("GUI required")
        from unittest.mock import patch
        import CommandSimulationEvent
        load = self.force()
        event = self.event(load)
        original = (list(event.Targets), event.Actions, event.Time)
        Dynamics.save_results(self.study, {"SchemaVersion": 2, "Times": [0], "Bodies": {}})
        snapshot = self.study.ResultData
        self.study.Document.openTransaction("Edit event")
        panel = CommandSimulationEvent.Task(self.study, event)
        try:
            panel.addAction(target=load)
            self.assertFalse(panel.accept())
            self.assertIn("only once", panel.message.text())
            self.assertEqual((list(event.Targets), event.Actions, event.Time), original)
            self.assertEqual(self.study.ResultData, snapshot)
            self.assertEqual(self.study.Status, "Complete")
            self.assertFalse(event.Proxy._validating_edit)
            panel.table.removeRow(1)
            with patch.object(panel, "finish"):
                self.assertTrue(panel.accept())
            self.assertEqual(self.study.ResultData, snapshot)
            self.assertEqual(self.study.Status, "Complete")
            self.study.Document.openTransaction("Change event time")
            panel.time.setValue(.05)
            with patch.object(panel, "finish"):
                self.assertTrue(panel.accept())
            self.assertEqual(event.Time, .05)
            self.assertEqual(self.study.Status, "NotRun")
            self.assertEqual(self.study.ResultData, "")
        finally:
            panel.form.deleteLater()
