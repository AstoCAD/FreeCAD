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

"""Cross-feature regressions from the MbD integration review."""
import math
import unittest
from contextlib import contextmanager

import FreeCAD as App
import Dynamics


class TestSimulationRegression(unittest.TestCase):
    @contextmanager
    def mechanism(self):
        from AssemblyTests.TestDynamics import TestDynamics
        fixture = TestDynamics()
        fixture.setUp()
        try:
            yield fixture
        finally:
            fixture.tearDown()

    def test_measurement_survives_regeneration(self):
        import PointMeasurement
        with self.mechanism() as f:
            body = f.box()
            study = f.study()
            Dynamics.run(study)
            measurement = PointMeasurement.create(study)
            measurement.Point = (body, ["Vertex2"])
            before = PointMeasurement.measure(measurement)
            Dynamics.run(study)
            after = PointMeasurement.measure(measurement)
            self.assertEqual(study.Status, "Complete")
            for a, b in zip(before["Position"], after["Position"]):
                self.assertLess((a-b).Length, 1e-7)

    # End-to-end scenarios checked against closed-form results.

    @staticmethod
    def connect(f, kind, first, second, frame):
        """Joint whose connector is *frame*, given in assembly coordinates."""
        joint = f.joint(kind, first, second)
        joint.Placement1 = first.Placement.inverse() * frame
        joint.Placement2 = second.Placement.inverse() * frame
        return joint

    @staticmethod
    def upward_crossings(times, values):
        return [t0 + (t1-t0) * -v0/(v1-v0)
                for t0, t1, v0, v1 in zip(times, times[1:], values, values[1:]) if v0 < 0 <= v1]

    @staticmethod
    def add_motion(f, study, joint, kind, formula):
        from CommandCreateSimulation import Motion
        motion = f.doc.addObject("App::FeaturePython", "Motion")
        Motion(motion, kind, joint, formula)
        study.addObject(motion)
        return motion

    def test_compound_pendulum_period_energy_and_playback(self):
        import Part
        for variant in ("Part", "placed assembly", "scaled link"):
            with self.subTest(variant=variant), self.mechanism() as f:
                ground = f.box("Ground", density=None)
                ground.setPropertyStatus("Placement", "ReadOnly")
                rod = f.box("Rod")
                rod.Shape = Part.makeBox(2, 2, 100, App.Vector(-1, -1, -100))  # Pivot at its top.
                length, width = 100, 2
                if variant == "scaled link":
                    source = rod
                    f.assembly.removeObject(source)
                    rod = f.assembly.newObject("App::Link", "RodLink")
                    rod.setLink(source)
                    rod.Scale = 2
                    length, width = 200, 4
                if variant == "placed assembly":
                    # Results and gravity are in assembly coordinates.
                    f.assembly.Placement = App.Placement(App.Vector(30, 40, 50), App.Rotation(App.Vector(1, 2, 3), 70))
                amplitude = 5
                rod.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), amplitude))
                f.doc.recompute()
                self.connect(f, "Revolute", ground, rod, App.Placement(App.Vector(), App.Rotation(App.Vector(0, 1, 0), 90)))
                study = f.study()
                study.EndTime = "1.2 s"
                study.OutputStep = "0.002 s"
                data = Dynamics.run(study)
                # I_pivot = m (L^2 + w^2)/12 + m (L/2)^2; finite-amplitude factor 1 + theta^2/16.
                inertia = (length**2 + width**2)/12 + (length/2)**2
                period = 2*math.pi*math.sqrt(inertia/(9810*length/2)) * (1 + math.radians(amplitude)**2/16)
                body = data["Bodies"][rod.Name]
                crossings = self.upward_crossings(data["Times"], [w[0] for w in body["AngularVelocity"]])
                self.assertGreaterEqual(len(crossings), 2)
                self.assertAlmostEqual((crossings[1]-crossings[0])/period, 1, delta=1e-4)
                angles = [math.degrees(2*math.atan2(p[3], p[6])) for p in body["Placements"]]
                self.assertAlmostEqual(max(angles), amplitude, delta=1e-3)
                self.assertAlmostEqual(min(angles), -amplitude, delta=1e-3)
                energy = data["Energy"]["System"]["MechanicalEnergy"]
                self.assertLess(max(energy)-min(energy), 1e-5*max(data["Energy"]["System"]["KineticEnergy"]))
                # Playback through the occurrence's parent frame reproduces the saved pose.
                start = Dynamics.component_placement(rod)
                self.assertTrue(App.Placement(App.Vector(*body["Placements"][0][:3]), App.Rotation(*body["Placements"][0][3:])).isSame(start, 1e-9))
                pose = App.Placement(App.Vector(*body["Placements"][-1][:3]), App.Rotation(*body["Placements"][-1][3:]))
                parent = start * rod.Placement.inverse()
                rod.Placement = parent.inverse() * pose
                self.assertTrue(Dynamics.component_placement(rod).isSame(pose, 1e-9))

    def test_spring_damper_frequency_and_decay(self):
        with self.mechanism() as f:
            ground = f.box("Ground", density=None)
            ground.setPropertyStatus("Placement", "ReadOnly")
            body = f.box()  # 0.006 kg
            self.connect(f, "Slider", ground, body, App.Placement(App.Vector(5, 10, 15), App.Rotation(App.Vector(0, 1, 0), 90)))
            study = f.study(False)
            study.EndTime = "0.05 s"
            study.OutputStep = study.MaximumStep = "0.0001 s"
            spring = Dynamics.create_load(study, "SpringDamper", body)
            spring.AttachmentI = App.Placement(App.Vector(5, 10, 15), App.Rotation())
            spring.AttachmentJ = App.Placement(App.Vector(-15, 10, 15), App.Rotation())  # Ground, 20 mm away.
            spring.RestLength = "18 mm"
            spring.Stiffness = "1 N/mm"
            spring.Damping = "0.5 kg/s"
            data = Dynamics.run(study)
            k, c, m = 1000, 0.5, 0.006  # N/m, kg/s, kg
            zeta = c/(2*math.sqrt(k*m))
            damped = math.sqrt(k/m) * math.sqrt(1-zeta*zeta)
            self.assertAlmostEqual(data["Loads"][spring.Name]["ForceX"][0], -2, delta=1e-9)  # 2 mm stretch.
            x = [p[0] for p in data["Bodies"][body.Name]["Placements"]]
            crossings = self.upward_crossings(data["Times"], [v[0] for v in data["Bodies"][body.Name]["Velocity"]])
            self.assertGreaterEqual(len(crossings), 3)
            measured = (crossings[-1]-crossings[0])/(len(crossings)-1)
            self.assertAlmostEqual(measured*damped/(2*math.pi), 1, delta=1e-4)
            # First overshoot below the equilibrium x = -2 mm.
            overshoot = 2*math.exp(-zeta*math.pi/math.sqrt(1-zeta*zeta))
            self.assertAlmostEqual(min(x), -2-overshoot, delta=1e-3)

    def slider_crank(self, f, r, l):
        """Crank of length r at 90 deg, rod of length l, slider on the X axis.

        Return the crank's revolute joint and the slider's joint.
        """
        import Part
        ground = f.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        s0 = math.sqrt(l*l - r*r)
        crank, rod, slider = f.box("Crank"), f.box("Rod"), f.box("Slider")
        crank.Shape = Part.makeBox(r+4, 4, 4, App.Vector(-2, -2, -2))
        rod.Shape = Part.makeBox(l+4, 4, 4, App.Vector(-2, -2, -2))
        slider.Shape = Part.makeBox(10, 10, 10, App.Vector(-5, -5, -5))
        crank.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 90)
        rod.Placement = App.Placement(App.Vector(0, r, 0), App.Rotation(App.Vector(0, 0, 1), math.degrees(math.atan2(-r, s0))))
        slider.Placement.Base = App.Vector(s0, 0, 0)
        drive = self.connect(f, "Revolute", ground, crank, App.Placement())
        self.connect(f, "Revolute", crank, rod, App.Placement(App.Vector(0, r, 0), App.Rotation()))
        self.connect(f, "Revolute", rod, slider, App.Placement(App.Vector(s0, 0, 0), App.Rotation()))
        slide = self.connect(f, "Slider", ground, slider, App.Placement(App.Vector(s0, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90)))
        return drive, slide

    def test_slider_crank_dynamics_matches_kinematics(self):
        with self.mechanism() as f:
            r, l = 20, 60
            drive, _slide = self.slider_crank(f, r, l)
            study = f.study(False)
            study.EndTime = "0.5 s"
            study.OutputStep = "0.005 s"
            self.add_motion(f, study, drive, "Angular", "initialValue+2*pi*time")
            results = {}
            for mode in ("Kinematics", "Dynamics"):
                study.AnalysisType = mode
                data = results[mode] = Dynamics.run(study)
                self.assertEqual(data["AnalysisType"], mode)
                crank_poses = data["Bodies"]["Crank"]["Placements"]
                for i in range(len(data["Times"])):
                    theta = 2*math.atan2(crank_poses[i][5], crank_poses[i][6])
                    root = math.sqrt(l*l - (r*math.sin(theta))**2)
                    omega = data["Bodies"]["Crank"]["AngularVelocity"][i][2]
                    self.assertAlmostEqual(omega, 2*math.pi, delta=1e-6)
                    self.assertAlmostEqual(data["Bodies"]["Slider"]["Placements"][i][0], r*math.cos(theta) + root, delta=1e-6)
                    velocity = (-r*math.sin(theta) - r*r*math.sin(theta)*math.cos(theta)/root) * omega
                    self.assertAlmostEqual(data["Bodies"]["Slider"]["Velocity"][i][0], velocity, delta=1e-4)
            system = results["Dynamics"]["Energy"]["System"]
            self.assertAlmostEqual(system["EnergyBalanceResidual"][-1], 0, delta=1e-7)
            for kinematic, dynamic in zip(results["Kinematics"]["Bodies"]["Slider"]["Placements"],
                                          results["Dynamics"]["Bodies"]["Slider"]["Placements"]):
                self.assertAlmostEqual(kinematic[0], dynamic[0], delta=1e-6)

    def test_kinematics_stopped_by_the_solver_is_not_complete(self):
        # Driving the slider 50 mm has no kinematic solution past a dead
        # centre (slider 23 mm out or 17 mm in): the solver stops there.
        with self.mechanism() as f:
            _drive, slide = self.slider_crank(f, 20, 60)
            study = f.study(False)
            study.EndTime = "0.5 s"
            study.AnalysisType = "Kinematics"
            self.add_motion(f, study, slide, "Linear", "initialValue+100*time")
            with self.assertRaisesRegex(RuntimeError, "stopped at t = "):
                Dynamics.run(study)
            self.assertEqual(study.Status, "Failed")
            self.assertFalse(study.ResultData)

    def test_gear_train_motor_torque_balances_output_load(self):
        with self.mechanism() as f:
            ground = f.box("Ground", density=None)
            ground.setPropertyStatus("Placement", "ReadOnly")
            first, second = f.box("First"), f.box("Second")
            drive = f.joint("Revolute", ground, first)
            f.joint("Revolute", ground, second)
            gears = f.joint("Gears", first, second)
            gears.Distance = "10 mm"
            gears.Distance2 = "20 mm"
            study = f.study(False)
            study.AnalysisType = "Dynamics"
            self.add_motion(f, study, drive, "Angular", "initialValue+10*time")
            load = Dynamics.create_load(study, "Torque", second)
            load.Torque = "2 N*mm"
            data = Dynamics.run(study)
            omega_first = data["Bodies"]["First"]["AngularVelocity"][-1][2]
            omega_second = data["Bodies"]["Second"]["AngularVelocity"][-1][2]
            self.assertAlmostEqual(omega_first, 10, delta=1e-6)
            self.assertAlmostEqual(omega_second, -5, delta=1e-6)
            # Constant speed: the motor supplies the power the load absorbs, 2 N mm * 5 rad/s.
            motor = data["JointReactions"][drive.FullName + "-AngularMotion"]
            self.assertAlmostEqual(abs(motor["TorqueZ"][-1]), 1, delta=1e-6)
            self.assertAlmostEqual(motor["Power"][-1], 10, delta=1e-5)
            self.assertAlmostEqual(data["Loads"][load.Name]["Power"][-1], -10, delta=1e-5)

    def test_rerun_after_input_edit_and_after_reopen(self):
        import os
        import tempfile
        with self.mechanism() as f:
            body = f.box()
            study = f.study(False)
            load = Dynamics.create_load(study, "Force", body)
            load.AttachmentI.Base = App.Vector(5, 10, 15)
            load.Force = "0.006 N"
            self.assertAlmostEqual(Dynamics.run(study)["Bodies"][body.Name]["Velocity"][-1][2], 100, delta=1e-6)
            load.Force = "0.012 N"
            self.assertEqual(study.Status, "NotRun")
            edited = Dynamics.run(study)
            self.assertAlmostEqual(edited["Bodies"][body.Name]["Velocity"][-1][2], 200, delta=1e-6)
            names = study.Name, body.Name
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "Rerun.FCStd")
                f.doc.saveAs(path)
                App.closeDocument(f.doc.Name)
                f.doc = App.openDocument(path)
                study = f.doc.getObject(names[0])
                self.assertEqual(study.Status, "Complete")
                rerun = Dynamics.run(study)
                self.assertEqual(rerun["Times"], edited["Times"])
                self.assertEqual(rerun["Bodies"][names[1]]["Placements"], edited["Bodies"][names[1]]["Placements"])

    def test_event_activated_repeat_profile_and_shared_definition(self):
        import json
        import MotionProfile
        import SimulationEvents
        for suppressed in (False, True):
            with self.subTest(suppressed=suppressed), self.mechanism() as f:
                body = f.box()
                study = f.study(False)
                study.MaximumStep = "0.001 s"
                load = Dynamics.create_load(f.assembly, "Force", body)
                load.AttachmentI.Base = App.Vector(5, 10, 15)
                spec = MotionProfile.defaults("N", "Expression")
                spec.update(quantity="Magnitude", end=.02, outside="Repeat",
                            expression="0.006*(1-cos(2*pi*time/0.02))")
                MotionProfile.assign(load, spec)
                load.Suppressed = suppressed
                original = load.Formula, load.ProfileData
                event = SimulationEvents.create(study)
                event.Time = 0
                event.Targets = [load]
                event.Actions = json.dumps([dict(kind="Activate")])
                for duration in (.1, .06):
                    study.EndTime = duration
                    data = Dynamics.run(study)
                    self.assertAlmostEqual(data["Bodies"][body.Name]["Velocity"][-1][2],
                                           1000*duration, delta=.02)
                    self.assertEqual((load.Formula, load.ProfileData), original)
                    self.assertEqual(load.Suppressed, suppressed)

    def test_delayed_event_keeps_pending_occurrences(self):
        from AssemblyTests.TestSimulationEvents import TestSimulationEvents
        for repeat in (False, True):
            f = TestSimulationEvents()
            f.setUp()
            try:
                motion = f.motion()
                motion.Formula = "initialValue+10*sin(50*pi*time)"
                load = f.force()
                load.Force = "0 N"
                event = f.event(load)
                event.Trigger = "Measurement"
                event.Component = f.body
                event.Quantity = "Position Z"
                event.Repeat = True
                event.Hysteresis = 1
                delayed = f.event(load, "Activate")
                delayed.Trigger = "After event"
                delayed.PreviousEvent = event
                delayed.Delay = .05
                delayed.Repeat = repeat
                f.study.EndTime = .14
                f.study.MaximumStep = .001
                data = Dynamics.run(f.study)
                times = [e["Time"] for e in data["EventLog"] if e["Event"] == delayed.Name]
                expected = [.09, .13] if repeat else [.09]
                self.assertEqual(len(times), len(expected))
                for actual, target in zip(times, expected):
                    self.assertAlmostEqual(actual, target, delta=2e-7)
            finally:
                f.tearDown()

    def test_noncoaxial_torsion_virtual_work_and_energy(self):
        for damping in (0, .2):
            with self.subTest(damping=damping), self.mechanism() as f:
                body = f.box()
                rotation = App.Rotation(App.Vector(1, 2, 3), 60)
                body.Placement.Rotation = rotation
                study = f.study(False)
                study.EndTime = study.OutputStep = .00001
                load = Dynamics.create_load(study, "TorsionalSpringDamper", body)
                load.AttachmentI = App.Placement(App.Vector(5, 10, 15), App.Rotation())
                load.AttachmentJ = App.Placement(body.Placement.multVec(App.Vector(5, 10, 15)), App.Rotation())
                load.TorsionalStiffness = "1 N*mm/rad"
                load.TorsionalDamping = f"{damping} N*mm*s/rad"
                load.FreeAngle = "0 deg"
                initial = Dynamics.create_initial_velocity(study, "Angular", body)
                initial.Direction = App.Vector(1, 0, 0)
                initial.AngularVelocity = "1 rad/s"
                data = Dynamics.run(study)
                def angle(rot):
                    x, y, z, w = rot.inverted().Q
                    return math.atan2(2*z*w, w*w-z*z)
                eps = 1e-6
                plus = App.Rotation(App.Vector(1, 0, 0), math.degrees(eps))*rotation
                minus = App.Rotation(App.Vector(1, 0, 0), -math.degrees(eps))*rotation
                rate = (.5*angle(plus)**2-.5*angle(minus)**2)/(2*eps)
                speed = (angle(plus)-angle(minus))/(2*eps)
                result = data["Loads"][load.Name]
                self.assertAlmostEqual(result["Power"][0] + rate + damping*speed**2, 0, delta=1e-7)
                self.assertAlmostEqual(result["DissipatedPower"][0], damping*speed**2, delta=1e-7)
                energy = data["Energy"]["System"]["MechanicalEnergy"]
                if not damping:
                    self.assertAlmostEqual(energy[-1], energy[0], delta=1e-8)
                else:
                    self.assertLess(energy[-1], energy[0])

    def test_hard_slider_releases_under_separating_force(self):
        for sign, side in ((1, "Max"), (-1, "Min")):
            with self.subTest(side=side), self.mechanism() as f:
                body = f.box()
                ground = f.box("Ground", density=None)
                ground.setPropertyStatus("Placement", "ReadOnly")
                joint = f.joint("Slider", ground, body)
                setattr(joint, "EnableLength"+side, True)
                setattr(joint, "Length"+side, f"{sign*3.5} mm")
                study = f.study(False)
                study.MaximumStep = .0005
                initial = Dynamics.create_initial_velocity(study, "Linear", body)
                initial.Direction = App.Vector(0, 0, sign)
                initial.LinearVelocity = "100 mm/s"
                load = Dynamics.create_load(study, "Force", body)
                load.AttachmentI.Base = App.Vector(5, 10, 15)
                load.Direction = App.Vector(0, 0, -sign)
                load.Force = ".006 N"
                data = Dynamics.run(study)
                self.assertAlmostEqual(data["Bodies"][body.Name]["Placements"][-1][2], sign*2, delta=.003)
                self.assertAlmostEqual(data["Bodies"][body.Name]["Velocity"][-1][2], -sign*math.sqrt(3000), delta=.04)

    def test_contact_copy_and_deleted_endpoint_undo(self):
        with self.mechanism() as f:
            a, b, c = f.box("A"), f.box("B"), f.box("C")
            contact = Dynamics.create_contact(f.assembly, mode="General collision detection")
            Dynamics.set_contact_exclusions(contact, [(a, b), (b, c)])
            copied = f.doc.copyObject(f.assembly, True)
            other = next(o for o in f.doc.Objects if hasattr(o, "ContactType") and o != contact)
            self.assertEqual(len(Dynamics.contact_exclusions(other)), 2)
            self.assertEqual(len(Dynamics.contact_pairs(other)), 1)
            for pair in Dynamics.contact_exclusions(other):
                self.assertTrue(all(o in copied.getComponents() for o in pair))
            f.doc.openTransaction("Delete contact endpoint")
            name = b.Name
            f.doc.removeObject(name)
            f.doc.commitTransaction()
            self.assertEqual(Dynamics.contact_exclusions(contact), [])
            f.doc.undo()
            self.assertEqual(len(Dynamics.contact_exclusions(contact)), 2)

    def test_hard_revolute_releases_under_separating_torque(self):
        for sign, side in ((1, "Max"), (-1, "Min")):
            with self.subTest(side=side), self.mechanism() as f:
                body = f.box()
                ground = f.box("Ground", density=None)
                ground.setPropertyStatus("Placement", "ReadOnly")
                joint = f.joint("Revolute", ground, body)
                setattr(joint, "EnableAngle"+side, True)
                setattr(joint, "Angle"+side, f"{sign*.35} rad")
                study = f.study(False)
                study.MaximumStep = .0005
                initial = Dynamics.create_initial_velocity(study, "Angular", body)
                initial.Direction = App.Vector(0, 0, sign)
                initial.AngularVelocity = "10 rad/s"
                load = Dynamics.create_load(study, "Torque", body)
                load.Direction = App.Vector(0, 0, -sign)
                load.Torque = ".025 N*mm"  # Izz=.25 kg mm^2 -> 100 rad/s^2.
                data = Dynamics.run(study)
                pose = data["Bodies"][body.Name]["Placements"][-1]
                angle = 2*math.atan2(pose[5], pose[6])
                self.assertAlmostEqual(angle, sign*.2, delta=.0003)
                self.assertAlmostEqual(data["Bodies"][body.Name]["AngularVelocity"][-1][2],
                                       -sign*math.sqrt(30), delta=.004)

    def test_hard_stop_releases_when_compressive_load_reverses(self):
        with self.mechanism() as f:
            body = f.box()
            ground = f.box("Ground", density=None)
            ground.setPropertyStatus("Placement", "ReadOnly")
            joint = f.joint("Slider", ground, body)
            joint.EnableLengthMax = True
            joint.LengthMax = "3.5 mm"
            study = f.study(False)
            initial = Dynamics.create_initial_velocity(study, "Linear", body)
            initial.Direction = App.Vector(0, 0, 1)
            initial.LinearVelocity = "100 mm/s"
            load = Dynamics.create_load(study, "Force", body)
            load.AttachmentI.Base = App.Vector(5, 10, 15)
            load.Formula = "0.006*(1-20*time)"
            data = Dynamics.run(study)
            self.assertAlmostEqual(data["Bodies"][body.Name]["Placements"][-1][2],
                                   3.5-20000*.05**3/6, delta=.003)
            self.assertAlmostEqual(data["Bodies"][body.Name]["Velocity"][-1][2], -25, delta=.03)

    def test_simulation_knows_its_assembly_when_created_and_restored(self):
        import os
        import tempfile
        import CommandCreateSimulation
        import UtilsAssembly
        with self.mechanism() as f:
            group = UtilsAssembly.getSimulationGroup(f.assembly)
            simulation = group.newObject("App::FeaturePython", "Simulation")
            CommandCreateSimulation.Simulation(simulation)
            self.assertEqual(simulation.Assembly, f.assembly)
            # A Simulation saved before the dynamics schema has no backlink.
            for name in ("Assembly", "AnalysisType", "SchemaVersion", "GravityEnabled",
                         "GravityMagnitude", "GravityDirection", "MinimumStep",
                         "MaximumStep", "Status", "LastError", "ResultData"):
                simulation.removeProperty(name)
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "LegacySimulation.FCStd")
                names = simulation.Name, f.assembly.Name
                f.doc.saveAs(path)
                App.closeDocument(f.doc.Name)
                f.doc = App.openDocument(path)
                simulation, assembly = (f.doc.getObject(name) for name in names)
                self.assertEqual(simulation.Assembly, assembly)
                self.assertEqual(simulation.Proxy.getAssembly(simulation), assembly)
                self.assertEqual(Dynamics.inputs_for_study(simulation), [])

    def test_simulation_inputs_callback_waits_for_undo_to_finish(self):
        # The simulation panel refreshes its input lists from this callback and
        # closes after undo/redo. Undoing "Create Simulation" clears the study's
        # Assembly link before its Group: a refresh during that replay read a
        # half-removed study.
        import CommandCreateSimulation
        import UtilsAssembly
        with self.mechanism() as f:
            body = f.box()
            f.doc.UndoMode = 1
            f.doc.openTransaction("Create Simulation")
            group = UtilsAssembly.getSimulationGroup(f.assembly)
            simulation = group.newObject("App::FeaturePython", "Simulation")
            CommandCreateSimulation.Simulation(simulation)
            name = simulation.Name
            refreshes, errors = [], []

            def refresh():
                try:
                    refreshes.append(Dynamics.inputs_for_study(simulation))
                except Exception as error:  # onChanged would only print it
                    errors.append(error)

            simulation.Proxy.setMotionsChangedCallback(refresh)
            load = Dynamics.create_load(simulation, "Force", body)
            self.assertEqual(refreshes[-1], [load])
            f.doc.undo()
            self.assertIsNone(f.doc.getObject(name))
            self.assertEqual(errors, [])

    def test_simulation_panel_is_not_reopened_on_a_removed_study(self):
        # A child task reopens the simulation panel when it closes; undo may
        # have removed the study meanwhile, which keeps its Document.
        import CommandCreateSimulation
        import UtilsAssembly
        with self.mechanism() as f:
            f.doc.UndoMode = 1
            f.doc.openTransaction("Create Simulation")
            group = UtilsAssembly.getSimulationGroup(f.assembly)
            simulation = group.newObject("App::FeaturePython", "Simulation")
            CommandCreateSimulation.Simulation(simulation)
            f.doc.commitTransaction()
            f.doc.undo()
            self.assertIsNotNone(simulation.Document)
            # Returns before touching the task view (none exists headless).
            CommandCreateSimulation.TaskAssemblyCreateSimulation.reopen(simulation)

    def test_global_input_membership_invalidates_studies_and_undo_restores(self):
        # The tree moves inputs between a study and the Simulations group with
        # plain removeObject/addObject; the App group alone invalidates studies.
        import UtilsAssembly
        with self.mechanism() as f:
            body = f.box()
            study, other = f.study(False), f.study(False)
            group = UtilsAssembly.getSimulationGroup(f.assembly)
            load = Dynamics.create_load(study, "Force", body)
            data = {"SchemaVersion": 2, "Times": [0], "Bodies": {}}
            f.doc.UndoMode = 1
            for source, target in ((study, group), (group, study)):
                with self.subTest(target=target.Name):
                    for item in (study, other):
                        Dynamics.save_results(item, data)
                    f.doc.openTransaction("Move input")
                    source.removeObject(load)
                    target.addObject(load)
                    f.doc.commitTransaction()
                    self.assertEqual([item.Status for item in (study, other)], ["NotRun"] * 2)
                    f.doc.undo()
                    self.assertEqual([item.Status for item in (study, other)], ["Complete"] * 2)
                    self.assertEqual(Dynamics.input_owner(load), source)
                    f.doc.redo()
                    self.assertEqual(Dynamics.input_owner(load), target)
                    self.assertEqual([item.Status for item in (study, other)], ["NotRun"] * 2)
