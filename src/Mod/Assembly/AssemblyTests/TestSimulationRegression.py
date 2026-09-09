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
