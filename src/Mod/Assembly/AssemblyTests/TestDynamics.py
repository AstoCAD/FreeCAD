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

"""Headless regressions for the Materials-to-Assembly dynamics boundary."""

import math
import os
import tempfile
import unittest

import FreeCAD as App
import Part
import Materials
import AssemblyApp  # Registers Assembly::AssemblyObject.
import Dynamics


class TestDynamics(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve_on_recompute = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("DynamicsTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.joints = self.assembly.newObject("Assembly::JointGroup", "Joints")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve_on_recompute)

    def box(self, name="Box", density="1000 kg/m^3", position=(0, 0, 0)):
        box = self.assembly.newObject("Part::Feature", name)
        box.Shape = Part.makeBox(10, 20, 30)
        box.Placement.Base = App.Vector(*position)
        material = Materials.Material()
        if density is not None:
            material.addPhysicalModel(Materials.UUIDs().Density)
            material.setPhysicalValue("Density", density)
        box.ShapeMaterial = material
        return box

    def study(self, gravity=True):
        study = Dynamics.create_study(self.assembly)
        study.EndTime = "0.1 s"
        study.OutputStep = "0.01 s"
        study.GravityEnabled = gravity
        self.doc.recompute()
        return study

    def assertVectorClose(self, actual, expected, delta=1e-5):
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=delta)

    def joint(self, kind, first, second, attachment=(5, 10, 15)):
        import JointObject
        joint = self.joints.newObject("App::FeaturePython", "Joint")
        JointObject.Joint(joint, JointObject.JointTypes.index(kind))
        joint.Detach1 = True
        joint.Detach2 = True
        joint.Reference1 = (first, [""])
        joint.Reference2 = (second, [""])
        joint.Placement1.Base = App.Vector(*attachment)
        joint.Placement2.Base = App.Vector(*attachment)
        return joint

    def rigid_group(self, bodies):
        # The backend consumes the same document properties as JointObject.RigidGroup.
        group = self.joints.newObject("App::FeaturePython", "RigidGroup")
        group.addProperty("App::PropertyBool", "Suppressed")
        group.addProperty("App::PropertyLinkList", "ObjectsToRigidGroup")
        group.ObjectsToRigidGroup = bodies
        return group

    def test_global_and_local_inputs_share_the_simulation_group(self):
        body = self.box()
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        joint = self.joint("Slider", ground, body)
        study = self.study(gravity=False)
        global_load = Dynamics.create_load(self.assembly, "Force", body)
        global_initial = Dynamics.create_initial_velocity(self.assembly, "Linear", body)
        global_contact = Dynamics.create_contact(self.assembly, ground, body)
        global_friction = Dynamics.create_friction(self.assembly, joint)
        local_load = Dynamics.create_load(study, "Force", body)

        simulation_group = next(
            obj for obj in self.assembly.Group
            if obj.TypeId == "Assembly::SimulationGroup"
        )
        for obj in (global_load, global_initial, global_contact, global_friction):
            self.assertIn(obj, simulation_group.Group)
            self.assertTrue(Dynamics.is_global_input(obj))
        self.assertIn(study, simulation_group.Group)
        self.assertIn(local_load, study.Group)
        self.assertEqual(
            Dynamics.inputs_for_study(study),
            [global_load, global_initial, global_contact, global_friction, local_load],
        )

        study.Status = "Complete"
        study.ResultData = "{}"
        global_load.Force = "1 N"
        self.assertEqual(study.Status, "NotRun")
        self.assertEqual(study.ResultData, "")

    def test_box_mass_and_local_inertia(self):
        box = self.box(position=(43, -21, 109))
        box.Placement.Rotation = App.Rotation(App.Vector(1, 2, 3), 47)
        mass = self.assembly.getMassProperties(box)
        self.assertAlmostEqual(mass["Mass"], 0.006)
        self.assertAlmostEqual(mass["Volume"], 6000)
        self.assertVectorClose(mass["CenterOfMass"], (5, 10, 15))
        for actual, expected in zip(mass["Inertia"], ((0.65, 0, 0), (0, 0.5, 0), (0, 0, 0.25))):
            self.assertVectorClose(actual, expected)

    def test_study_inputs_and_membership_invalidate_results(self):
        body = self.box()
        study = self.study(False)
        Dynamics.run(study)
        study.EndTime = "0.2 s"
        self.assertEqual(study.Status, "NotRun")
        with self.assertRaises(ValueError):
            Dynamics.results(study)
        for owner in (study, self.assembly):
            Dynamics.run(study)
            initial = Dynamics.create_initial_velocity(owner, "Linear", body)
            self.assertEqual(study.Status, "NotRun")
            Dynamics.run(study)
            self.doc.removeObject(initial.Name)
            self.assertEqual(study.Status, "NotRun")
        Dynamics.run(study)
        other = Dynamics.create_study(self.assembly)
        self.assertEqual(study.Status, "Complete", "Adding a study is not a global input edit")
        initial = Dynamics.create_initial_velocity(other, "Linear", body)
        self.assertEqual(study.Status, "Complete")
        other.removeObject(initial)
        study.addObject(initial)
        self.assertEqual(study.Status, "NotRun")

    def test_ground_load_frames_follow_transformed_assembly(self):
        container = self.doc.addObject("App::Part", "Container")
        container.addObject(self.assembly)
        container.Placement = App.Placement(App.Vector(-20, 5, 4), App.Rotation(13, 22, 31))
        self.assembly.Placement = App.Placement(
            App.Vector(100, 200, 0), App.Rotation(App.Vector(0, 0, 1), 30)
        )
        body = self.box(position=(10, 20, 30))
        study = self.study(False)
        for kind in ("Bushing", "TorsionalSpringDamper"):
            load = Dynamics.create_load(study, kind, body)
            expected = body.Placement * load.AttachmentI
            self.assertTrue(load.AttachmentJ.isSame(expected, 1e-9))
            self.assertAlmostEqual(Dynamics.spring_length(load), 0, delta=1e-9)
            self.assertAlmostEqual(Dynamics.torsional_angle(load), 0, delta=1e-9)

    def test_angular_stop_energy_and_damping_use_radians(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        body.Shape = Part.makeBox(10, 10, 10, App.Vector(-5, -5, -5))
        joint = self.joint("Revolute", ground, body, attachment=(0, 0, 0))
        joint.EnableAngleMax = True
        joint.AngleMax = 0
        joint.AngleMaxLimitBehavior = "Compliant"
        joint.AngleMaxLimitStiffness = "100 N*mm/rad"
        joint.AngleMaxLimitDamping = "2 N*mm*s/rad"
        body.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), 10)
        study = self.study(False)
        study.EndTime = study.OutputStep = "0.00001 s"
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"
        limit = Dynamics.run(study)["Limits"][joint.FullName + "-LimitRotMax"]
        self.assertAlmostEqual(limit["StoredEnergy"][0], 0.5 * 100 * math.radians(10)**2, delta=1e-8)
        self.assertAlmostEqual(limit["DissipatedPower"][0], 2, delta=1e-6)

    def test_torsional_free_pose_above_half_turn(self):
        body = self.box()
        study = self.study(False)
        load = Dynamics.create_load(study, "TorsionalSpringDamper", body)
        load.AttachmentJ.Rotation = App.Rotation(App.Vector(0, 0, 1), 270)
        load.FreeAngle = "270 deg"
        load.TorsionalStiffness = "1 N*mm/rad"
        self.assertAlmostEqual(Dynamics.torsional_angle(load), 1.5 * math.pi, delta=1e-12)
        data = Dynamics.run(study)["Loads"][load.Name]
        self.assertTrue(all(abs(t) < 1e-8 for t in data["TorqueZ"]))

    def test_multiaxis_bushing_force_is_conjugate_to_elastic_energy(self):
        body = self.box()
        rotation = App.Rotation(App.Vector(1, 2, 3), 60)
        body.Placement.Rotation = rotation
        study = self.study(False)
        study.EndTime = study.OutputStep = "0.00001 s"
        load = Dynamics.create_load(study, "Bushing", body)
        load.AttachmentI = App.Placement(App.Vector(5, 10, 15), App.Rotation())
        offset = App.Vector(0.2, 0.3, 0.4)
        load.AttachmentJ = App.Placement(
            body.Placement.multVec(App.Vector(5, 10, 15)) + offset, App.Rotation()
        )
        for axis, stiffness in zip("XYZ", (1, 3, 5)):
            setattr(load, "BushingLinearStiffness" + axis, f"{stiffness} N/mm")
            setattr(load, "BushingAngularStiffness" + axis, f"{stiffness} N*mm/rad")
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.AngularVelocity = "1 rad/s"
        initial.Direction = App.Vector(1, 0, 0)
        data = Dynamics.run(study)

        def energy(pose):
            x, y, z, w = pose.inverted().Q
            if w < 0:
                x, y, z, w = -x, -y, -z, -w
            norm = math.sqrt(x*x + y*y + z*z)
            vector = App.Vector(x, y, z) * (2 * math.atan2(norm, w) / norm)
            displacement = pose.inverted().multVec(offset)
            return 0.5 * sum(
                k * (v*v + d*d) for k, v, d in zip((1, 3, 5), vector, displacement)
            )

        epsilon = 1e-6
        plus = App.Rotation(App.Vector(1, 0, 0), math.degrees(epsilon)) * rotation
        minus = App.Rotation(App.Vector(1, 0, 0), -math.degrees(epsilon)) * rotation
        rate = (energy(plus) - energy(minus)) / (2 * epsilon)
        self.assertAlmostEqual(data["Loads"][load.Name]["Power"][0] + rate, 0, delta=1e-7)
        mechanical = data["Energy"]["System"]["MechanicalEnergy"]
        self.assertAlmostEqual(mechanical[-1], mechanical[0], delta=1e-8)

    def test_coupled_bushing_translation_generates_torque(self):
        body = self.box()
        study = self.study(False)
        study.EndTime = study.OutputStep = "0.000001 s"
        load = Dynamics.create_load(study, "Bushing", body)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        Dynamics.align_bushing_reference(load)
        load.AttachmentJ.Base += App.Vector(1, 0, 0)
        load.CoupledBushing = True
        k = [0.0] * 36
        k[0], k[35], k[5], k[30] = 2, 3, 0.5, 0.5
        load.BushingStiffnessMatrix = k
        result = Dynamics.run(study)["Loads"][load.Name]
        self.assertAlmostEqual(result["ForceX"][0], 2, delta=1e-7)
        self.assertAlmostEqual(result["TorqueZ"][0], 0.5, delta=1e-7)
        self.assertAlmostEqual(result["StoredEnergy"][0], 1, delta=1e-7)
        # This symmetric matrix has positive diagonals but a negative eigenvalue.
        k[5] = k[30] = 3
        load.BushingStiffnessMatrix = k
        with self.assertRaisesRegex((ValueError, RuntimeError), "positive semidefinite"):
            Dynamics.run(study)

    def test_coupled_bushing_finite_rotation_energy_and_damping(self):
        body = self.box()
        rotation = App.Rotation(App.Vector(1, 2, 3), 60)
        body.Placement.Rotation = rotation
        study = self.study(False)
        study.EndTime = study.OutputStep = "0.000001 s"
        load = Dynamics.create_load(study, "Bushing", body)
        load.AttachmentI = App.Placement(App.Vector(5, 10, 15), App.Rotation())
        offset = App.Vector(0.2, 0.3, 0.4)
        load.AttachmentJ = App.Placement(
            body.Placement.multVec(App.Vector(5, 10, 15)) + offset, App.Rotation())
        load.CoupledBushing = True
        weights = (1, 2, 3, 4, 5, 6)
        matrix = [0.001 * a * b for a in weights for b in weights]
        load.BushingStiffnessMatrix = matrix
        load.BushingDampingMatrix = matrix
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(1, 0, 0)
        initial.AngularVelocity = "1 rad/s"

        def strain(pose):
            inverse = pose.inverted()
            x, y, z, w = inverse.Q
            if w < 0:
                x, y, z, w = -x, -y, -z, -w
            norm = math.sqrt(x*x + y*y + z*z)
            phi = App.Vector(x, y, z) * (2 * math.atan2(norm, w) / norm)
            return list(inverse.multVec(offset)) + list(phi)

        epsilon = 1e-6
        plus = strain(App.Rotation(App.Vector(1, 0, 0), math.degrees(epsilon)) * rotation)
        minus = strain(App.Rotation(App.Vector(1, 0, 0), -math.degrees(epsilon)) * rotation)
        q = strain(rotation)
        rate = [(a - b) / (2 * epsilon) for a, b in zip(plus, minus)]
        elastic = 0.0005 * sum(a*b for a, b in zip(weights, q))**2
        dissipation = 0.001 * sum(a*b for a, b in zip(weights, rate))**2
        energy_rate = 0.001 * sum(a*b for a, b in zip(weights, q)) * sum(a*b for a, b in zip(weights, rate))
        result = Dynamics.run(study)["Loads"][load.Name]
        self.assertAlmostEqual(result["StoredEnergy"][0], elastic, delta=1e-8)
        self.assertAlmostEqual(result["DissipatedPower"][0], dissipation, delta=1e-8)
        self.assertAlmostEqual(result["Power"][0] + energy_rate + dissipation, 0, delta=1e-8)

    def test_follower_load_tracks_component_rotation(self):
        body = self.box()
        study = self.study(False)
        study.EndTime = "0.1 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "Force", body)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        load.Direction = App.Vector(1, 0, 0)
        load.Force = "0.001 N"
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "10 rad/s"
        for follower in (False, True):
            load.Follower = follower
            for formula in ("", "0.001"):
                load.Formula = formula
                data = Dynamics.run(study)
                force = data["Loads"][load.Name]
                for index, pose in enumerate(data["Bodies"][body.Name]["Placements"]):
                    expected = App.Vector(0.001, 0, 0)
                    if follower:
                        expected = App.Rotation(*pose[3:]).multVec(expected)
                    actual = [force["Force" + axis][index] for axis in "XYZ"]
                    self.assertVectorClose(actual, expected, delta=1e-8)

    def test_follower_torque_tracks_component_rotation(self):
        body = self.box()
        study = self.study(False)
        study.EndTime = "0.01 s"
        study.MaximumStep = "0.0001 s"
        study.OutputStep = "0.001 s"
        load = Dynamics.create_load(study, "Torque", body)
        load.Direction = App.Vector(1, 0, 0)
        load.Torque = "0.001 N*mm"
        load.Follower = True
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "10 rad/s"
        for formula in ("", "0.001"):
            load.Formula = formula
            data = Dynamics.run(study)
            torque = data["Loads"][load.Name]
            for index, pose in enumerate(data["Bodies"][body.Name]["Placements"]):
                expected = App.Rotation(*pose[3:]).multVec(App.Vector(0.001, 0, 0))
                self.assertVectorClose([torque["Torque" + a][index] for a in "XYZ"], expected, delta=1e-8)

    def test_bearing_friction_distinguishes_radial_and_axial_load(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Revolute", ground, body)
        study = self.study()
        study.EndTime = "0.0001 s"
        study.OutputStep = study.EndTime
        study.GravityMagnitude = "10 m/s^2"
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "100 rad/s"
        friction = Dynamics.create_friction(study, joint)
        friction.StaticCoefficient = friction.DynamicCoefficient = 0.2
        friction.EffectiveRadius = "5 mm"
        for model, direction, expected in (
            ("Rolling resistance", App.Vector(-1, 0, 0), 0.06),
            ("Rolling resistance", App.Vector(0, 0, -1), 0),
            ("Thrust bearing", App.Vector(-1, 0, 0), 0),
            ("Thrust bearing", App.Vector(0, 0, -1), 0.06),
            ("Thrust bearing", App.Vector(0, 0, 1), 0.06),
        ):
            with self.subTest(model=model, direction=direction):
                friction.FrictionModel = model
                study.GravityDirection = direction
                result = Dynamics.run(study)["Loads"][friction.Name]
                self.assertAlmostEqual(result["TorqueZ"][0], expected, delta=1e-6)

    def test_link_mass_and_uniform_scale(self):
        box = self.box()
        link = self.assembly.newObject("App::Link", "Occurrence")
        link.setLink(box)
        link.Placement = App.Placement(App.Vector(100, 50, 10), App.Rotation(App.Vector(0, 0, 1), 90))
        mass = self.assembly.getMassProperties(link)
        self.assertAlmostEqual(mass["Mass"], 0.006)
        self.assertVectorClose(mass["CenterOfMass"], (5, 10, 15))
        link.Scale = 2
        mass = self.assembly.getMassProperties(link)
        self.assertAlmostEqual(mass["Mass"], 0.048)
        self.assertVectorClose(mass["CenterOfMass"], (10, 20, 30))
        self.assertAlmostEqual(mass["Inertia"][0][0], 0.65 * 32)

    def test_missing_or_invalid_density_is_not_guessed(self):
        for density in (None, "0 kg/m^3", "-1 kg/m^3"):
            box = self.box(density=density)
            with self.assertRaises(ValueError):
                self.assembly.getMassProperties(box)

    def test_open_shape_rejected(self):
        box = self.box()
        box.Shape = Part.makePlane(10, 20)
        with self.assertRaisesRegex(ValueError, "solid"):
            self.assembly.getMassProperties(box)

    def test_free_fall_does_not_move_document(self):
        box = self.box(position=(7, 9, 100))
        study = self.study()
        original = box.Placement
        data = Dynamics.run(study)
        self.assertEqual(study.Status, "Complete")
        self.assertTrue(box.Placement.isSame(original, 1e-12))
        self.assertAlmostEqual(data["Times"][-1], 0.1)
        self.assertTrue(all(b > a for a, b in zip(data["Times"], data["Times"][1:])))
        self.assertEqual(data["SolverFrames"][0], 1)
        body = data["Bodies"][box.Name]
        self.assertVectorClose(body["Placements"][-1][:3], (7, 9, 50.95), delta=0.002)
        self.assertVectorClose(body["Velocity"][-1], (0, 0, -981), delta=0.002)
        self.assertVectorClose(body["Acceleration"][-1], (0, 0, -9810), delta=0.002)
        self.assertEqual(Dynamics.results(study)["Times"], data["Times"])

    def test_free_fall_conserves_mechanical_energy(self):
        box = self.box(position=(0, 0, 100))
        data = Dynamics.run(self.study())

        body = data["Bodies"][box.Name]
        potential_loss = (
            body["GravitationalPotentialEnergy"][0]
            - body["GravitationalPotentialEnergy"][-1]
        )
        kinetic_gain = (
            body["TranslationalKineticEnergy"][-1]
            - body["TranslationalKineticEnergy"][0]
        )
        self.assertAlmostEqual(kinetic_gain, potential_loss, delta=2e-5)
        energy = data["Energy"]["System"]
        self.assertAlmostEqual(
            energy["MechanicalEnergy"][-1],
            energy["MechanicalEnergy"][0],
            delta=2e-5,
        )
        self.assertAlmostEqual(energy["EnergyBalanceResidual"][-1], 0, delta=2e-5)

    def test_initial_linear_velocity_of_center_of_mass(self):
        box = self.box()
        study = self.study(gravity=False)
        initial = Dynamics.create_initial_velocity(study, "Linear", box)
        initial.Direction = App.Vector(1, 0, 0)
        initial.LinearVelocity = "100 mm/s"
        data = Dynamics.run(study)
        body = data["Bodies"][box.Name]
        self.assertVectorClose(body["Velocity"][0], (100, 0, 0))
        self.assertAlmostEqual(body["Placements"][-1][0], 10, delta=0.002)
        self.assertNotIn("Touched", initial.State)
        self.assertNotIn("Touched", study.State)

    def test_initial_angular_velocity_rotates_about_center_of_mass(self):
        box = self.box()
        study = self.study(gravity=False)
        initial = Dynamics.create_initial_velocity(study, "Angular", box)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"
        center = box.Placement.multVec(App.Vector(5, 10, 15))
        data = Dynamics.run(study)
        body = data["Bodies"][box.Name]
        self.assertVectorClose(body["AngularVelocity"][0], (0, 0, 1))
        pose = body["Placements"][-1]
        final_center = App.Placement(
            App.Vector(*pose[:3]), App.Rotation(*pose[3:])
        ).multVec(App.Vector(5, 10, 15))
        self.assertVectorClose(tuple(final_center), tuple(center), delta=0.002)

    def test_force_units_and_reaction(self):
        box = self.box()
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Force", box)
        load.Force = "0.006 N"
        load.Direction = App.Vector(1, 0, 0)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        data = Dynamics.run(study)
        body = data["Bodies"][box.Name]
        self.assertVectorClose(body["Acceleration"][-1], (1000, 0, 0), delta=0.01)
        self.assertAlmostEqual(body["Placements"][-1][0], 5, delta=0.002)
        self.assertAlmostEqual(data["Loads"][load.Name]["ForceX"][-1], 0.006, delta=1e-8)

    def test_constant_force_work_matches_kinetic_energy(self):
        box = self.box()
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Force", box)
        load.Force = "0.006 N"
        load.Direction = App.Vector(1, 0, 0)
        load.AttachmentI.Base = App.Vector(5, 10, 15)

        data = Dynamics.run(study)

        body = data["Bodies"][box.Name]
        kinetic_gain = body["MechanicalEnergy"][-1] - body["MechanicalEnergy"][0]
        load_result = data["Loads"][load.Name]
        self.assertAlmostEqual(load_result["Power"][0], 0, delta=1e-10)
        self.assertAlmostEqual(load_result["Work"][-1], 0.03, delta=2e-5)
        self.assertAlmostEqual(kinetic_gain, load_result["Work"][-1], delta=2e-5)
        self.assertAlmostEqual(
            data["Energy"]["System"]["EnergyBalanceResidual"][-1],
            0,
            delta=2e-5,
        )

    def test_time_dependent_force_formula(self):
        box = self.box()
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Force", box)
        load.Direction = App.Vector(1, 0, 0)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        load.Formula = "0.06*time"
        data = Dynamics.run(study)
        self.assertAlmostEqual(data["Loads"][load.Name]["ForceX"][0], 0, delta=1e-12)
        self.assertAlmostEqual(data["Loads"][load.Name]["ForceX"][-1], 0.006, delta=1e-8)
        self.assertAlmostEqual(
            data["Bodies"][box.Name]["Acceleration"][-1][0], 1000, delta=0.02
        )

    def test_torque_uses_physical_inertia(self):
        box = self.box()
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", box)
        load.Torque = "0.00025 N*mm"  # Izz = 0.25 kg mm^2; alpha = 1 rad/s^2.
        data = Dynamics.run(study)
        self.assertAlmostEqual(data["Bodies"][box.Name]["AngularAcceleration"][-1][2], 1, delta=1e-5)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][-1], 0.00025, delta=1e-9)

    def test_torsional_spring_damper_restores_relative_twist(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "TorsionalSpringDamper", box)
        load.TorsionalStiffness = "0.001 N*mm/rad"
        load.TorsionalDamping = "0 N*mm*s/rad"
        load.FreeAngle = math.degrees(0.1)
        load.AttachmentJ.Rotation = App.Rotation(
            App.Vector(0, 0, 1), math.degrees(0.2)
        )

        data = Dynamics.run(study)

        # k*(0.2 rad twist - 0.1 rad free angle) applies +0.0001 N mm.
        # Izz is 0.25 kg mm^2, so the initial acceleration is +0.4 rad/s^2.
        result = data["Bodies"][box.Name]
        self.assertAlmostEqual(result["AngularAcceleration"][0][2], 0.4, delta=1e-5)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][0], 0.0001, delta=1e-9)
        self.assertGreater(result["AngularVelocity"][-1][2], 0)

    def test_torsional_damping_opposes_relative_angular_velocity(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        initial = Dynamics.create_initial_velocity(study, "Angular", box)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"
        load = Dynamics.create_load(study, "TorsionalSpringDamper", box)
        load.TorsionalStiffness = "0 N*mm/rad"
        load.TorsionalDamping = "0.00025 N*mm*s/rad"
        load.FreeAngle = "0 deg"

        data = Dynamics.run(study)

        result = data["Bodies"][box.Name]
        self.assertAlmostEqual(result["AngularAcceleration"][0][2], -1, delta=1e-5)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][0], -0.00025, delta=1e-9)
        self.assertLess(result["AngularVelocity"][-1][2], 1)

    def test_torsional_damping_energy_loss_matches_dissipation(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.01 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        initial = Dynamics.create_initial_velocity(study, "Angular", box)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"
        load = Dynamics.create_load(study, "TorsionalSpringDamper", box)
        load.TorsionalStiffness = "0 N*mm/rad"
        load.TorsionalDamping = "0.00025 N*mm*s/rad"

        data = Dynamics.run(study)

        system = data["Energy"]["System"]
        loss = system["MechanicalEnergy"][0] - system["MechanicalEnergy"][-1]
        self.assertGreater(loss, 0)
        self.assertAlmostEqual(loss, system["DissipatedEnergy"][-1], delta=2e-7)
        self.assertAlmostEqual(system["EnergyBalanceResidual"][-1], 0, delta=2e-7)
        load_result = data["Loads"][load.Name]
        self.assertAlmostEqual(
            load_result["DissipatedPower"][0], 0.00025, delta=1e-9
        )

    def test_bushing_translational_stiffness_uses_attachment_axes(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "Bushing", box)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        Dynamics.align_bushing_reference(load)
        load.BushingLinearStiffnessX = "0.006 N/mm"
        attachment = load.AttachmentJ
        attachment.Base.x += 1
        load.AttachmentJ = attachment

        data = Dynamics.run(study)

        # F = k*x = 0.006 N and m = 0.006 kg, therefore a = 1000 mm/s^2.
        result = data["Bodies"][box.Name]
        self.assertAlmostEqual(result["Acceleration"][0][0], 1000, delta=0.02)
        self.assertAlmostEqual(data["Loads"][load.Name]["ForceX"][0], 0.006, delta=1e-8)
        self.assertVectorClose(result["Acceleration"][0][1:], (0, 0), delta=1e-8)

    def test_undamped_bushing_exchanges_elastic_and_kinetic_energy(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.02 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "Bushing", box)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        Dynamics.align_bushing_reference(load)
        load.BushingLinearStiffnessX = "0.006 N/mm"
        attachment = load.AttachmentJ
        attachment.Base.x += 1
        load.AttachmentJ = attachment

        data = Dynamics.run(study)

        load_result = data["Loads"][load.Name]
        system = data["Energy"]["System"]
        self.assertAlmostEqual(load_result["StoredEnergy"][0], 0.003, delta=1e-9)
        self.assertGreater(system["KineticEnergy"][-1], system["KineticEnergy"][0])
        self.assertLess(load_result["StoredEnergy"][-1], load_result["StoredEnergy"][0])
        self.assertAlmostEqual(
            system["MechanicalEnergy"][-1],
            system["MechanicalEnergy"][0],
            delta=2e-6,
        )

    def test_bushing_rotational_stiffness_uses_rotation_vector(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "Bushing", box)
        load.BushingAngularStiffnessZ = "0.001 N*mm/rad"
        attachment = load.AttachmentJ
        attachment.Rotation = App.Rotation(App.Vector(0, 0, 1), math.degrees(0.1))
        load.AttachmentJ = attachment

        data = Dynamics.run(study)

        # T = k*theta = 0.0001 N mm and Izz = 0.25 kg mm^2.
        result = data["Bodies"][box.Name]
        self.assertAlmostEqual(result["AngularAcceleration"][0][2], 0.4, delta=1e-5)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][0], 0.0001, delta=1e-9)

    def test_bushing_angular_damping_opposes_relative_velocity(self):
        box = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        initial = Dynamics.create_initial_velocity(study, "Angular", box)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"
        load = Dynamics.create_load(study, "Bushing", box)
        load.BushingAngularDampingZ = "0.00025 N*mm*s/rad"

        data = Dynamics.run(study)

        result = data["Bodies"][box.Name]
        self.assertAlmostEqual(result["AngularAcceleration"][0][2], -1, delta=1e-5)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][0], -0.00025, delta=1e-9)
        self.assertLess(result["AngularVelocity"][-1][2], 1)

    def test_revolute_joint_friction_opposes_angular_velocity(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box("Rotor")
        joint = self.joint("Revolute", ground, body)
        study = self.study(gravity=False)
        friction = Dynamics.create_friction(study, joint)
        friction.StaticTorque = "0.00025 N*mm"
        friction.DynamicTorque = "0.00025 N*mm"
        friction.AngularTransitionVelocity = "0.001 rad/s"
        friction.AngularViscousDamping = "0 N*mm*s/rad"
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "1 rad/s"

        data = Dynamics.run(study)

        # Izz = 0.25 kg mm^2; a 0.00025 N mm resisting torque gives -1 rad/s^2.
        result = data["Bodies"][body.Name]
        self.assertAlmostEqual(result["AngularAcceleration"][0][2], -1, delta=1e-5)
        self.assertLess(result["AngularVelocity"][-1][2], 1)

    def test_slider_joint_friction_opposes_linear_velocity(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box("Slider")
        joint = self.joint("Slider", ground, body)
        study = self.study(gravity=False)
        friction = Dynamics.create_friction(study, joint)
        friction.StaticForce = "0.006 N"
        friction.DynamicForce = "0.006 N"
        friction.LinearTransitionVelocity = "1 mm/s"
        friction.LinearViscousDamping = "0 kg/s"
        initial = Dynamics.create_initial_velocity(study, "Linear", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.LinearVelocity = "100 mm/s"

        data = Dynamics.run(study)

        # m = 0.006 kg; a 0.006 N resisting force gives -1000 mm/s^2.
        result = data["Bodies"][body.Name]
        self.assertAlmostEqual(result["Acceleration"][0][2], -1000, delta=0.02)
        self.assertLess(result["Velocity"][-1][2], 100)

    def test_reaction_based_joint_friction_uses_transverse_load(self):
        for kind in ("Slider", "Revolute"):
            with self.subTest(kind=kind):
                ground = self.box(f"{kind}Ground", density=None)
                ground.setPropertyStatus("Placement", "ReadOnly")
                body = self.box(f"{kind}Body")
                joint = self.joint(kind, ground, body)
                study = self.study()
                friction_object = Dynamics.create_friction(study, joint)
                friction_object.FrictionModel = "Reaction based"
                friction_object.StaticCoefficient = 0.2
                friction_object.DynamicCoefficient = 0.2
                friction_object.EffectiveRadius = "5 mm"
                study.GravityMagnitude = "10 m/s^2"
                study.GravityDirection = App.Vector(-1, 0, 0)
                initial_kind = "Linear" if kind == "Slider" else "Angular"
                initial = Dynamics.create_initial_velocity(study, initial_kind, body)
                initial.Direction = App.Vector(0, 0, 1)
                if kind == "Slider":
                    initial.LinearVelocity = "1000 mm/s"
                else:
                    initial.AngularVelocity = "100 rad/s"

                data = Dynamics.run(study)
                result = data["Bodies"][body.Name]
                friction = data["Loads"][friction_object.Name]
                # m=0.006 kg gives a 0.06 N transverse reaction. Slider
                # resistance is mu*N=0.012 N; the bearing torque additionally
                # multiplies by the 5 mm effective radius, giving 0.06 N mm.
                if kind == "Slider":
                    self.assertAlmostEqual(result["Acceleration"][0][2], -2000, delta=0.1)
                    self.assertAlmostEqual(friction["ForceZ"][0], 0.012, delta=1e-6)
                else:
                    self.assertAlmostEqual(
                        result["AngularAcceleration"][0][2], -240, delta=0.02
                    )
                    self.assertAlmostEqual(friction["TorqueZ"][0], 0.06, delta=1e-6)

    def test_time_dependent_torque_formula_and_invalid_expression(self):
        box = self.box()
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", box)
        load.Formula = "0.0025*time"
        data = Dynamics.run(study)
        self.assertAlmostEqual(data["Loads"][load.Name]["TorqueZ"][-1], 0.00025, delta=1e-9)
        self.assertAlmostEqual(
            data["Bodies"][box.Name]["AngularAcceleration"][-1][2], 1, delta=1e-4
        )
        load.Formula = "not a valid expression"
        with self.assertRaises(RuntimeError):
            Dynamics.run(study)
        self.assertEqual(study.Status, "Failed")

    def test_rotated_inertia_and_constant_center_of_mass(self):
        box = self.box()
        box.Placement.Rotation = App.Rotation(App.Vector(0, 1, 0), 90)
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", box)
        load.Direction = App.Vector(1, 0, 0)
        load.Torque = "0.00025 N*mm"  # Local Z principal axis is world X.
        initial_com = box.Placement.multVec(App.Vector(5, 10, 15))
        data = Dynamics.run(study)
        body = data["Bodies"][box.Name]
        self.assertVectorClose(body["AngularAcceleration"][-1], (1, 0, 0))
        pose = body["Placements"][-1]
        final_com = App.Placement(App.Vector(*pose[:3]), App.Rotation(*pose[3:])).multVec(App.Vector(5, 10, 15))
        self.assertVectorClose(tuple(final_com), tuple(initial_com))

    def test_rigid_group_aggregates_different_materials(self):
        first = self.box(position=(0, 0, 0))
        second = self.box("Second", density="2000 kg/m^3", position=(30, 0, 0))
        self.rigid_group([first, second])
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Force", first)
        load.Force = "0.018 N"
        load.Direction = App.Vector(1, 0, 0)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        data = Dynamics.run(study)
        for box in (first, second):
            self.assertVectorClose(data["Bodies"][box.Name]["Acceleration"][-1], (1000, 0, 0), delta=0.01)
        self.assertAlmostEqual(data["Bodies"][second.Name]["Placements"][-1][0], 35, delta=0.002)

    def test_rigid_group_initial_velocity_at_selected_component_com(self):
        first = self.box("First", position=(7, 11, 13))
        second = self.box("Second", density="2000 kg/m^3", position=(107, 11, 13))
        first.Placement.Rotation = App.Rotation(25, 40, 10)
        second.Placement.Rotation = App.Rotation(-35, 0, 13)
        self.rigid_group([first, second])
        study = self.study(False)
        study.EndTime = study.OutputStep = "0.001 s"
        linear = Dynamics.create_initial_velocity(study, "Linear", first)
        angular = Dynamics.create_initial_velocity(study, "Angular", first)
        omega = App.Vector(1, 2, -1)
        angular.Direction = omega
        angular.AngularVelocity = f"{omega.Length} rad/s"
        for selected, requested in ((first, (0, 0, 0)), (first, (3, 4, 5)),
                                    (second, (3, 4, 5)), (None, (0, 0, 0))):
            with self.subTest(component=selected.Name if selected else "Angular only", velocity=requested):
                linear.Suppressed = selected is None
                linear.Component = selected or first
                velocity = App.Vector(*requested)
                linear.Direction = velocity if velocity.Length else App.Vector(1, 0, 0)
                linear.LinearVelocity = f"{velocity.Length} mm/s"
                data = Dynamics.run(study)
                centres, velocities = {}, {}
                for component in (first, second):
                    body = data["Bodies"][component.Name]
                    pose = body["Placements"][0]
                    rotation = App.Rotation(*pose[3:])
                    offset = rotation.multVec(App.Vector(*data["MassProperties"][component.Name]["CenterOfMass"]))
                    centres[component] = App.Vector(*pose[:3]) + offset
                    velocities[component] = App.Vector(*body["Velocity"][0]) + App.Vector(*body["AngularVelocity"][0]).cross(offset)
                    self.assertVectorClose(body["AngularVelocity"][0], omega)
                self.assertVectorClose(velocities[selected or first], requested)
                self.assertVectorClose(velocities[second] - velocities[first], omega.cross(centres[second] - centres[first]))

    def test_grounded_rigid_group_stays_fixed_without_materials(self):
        first = self.box(density=None)
        second = self.box("Second", density=None, position=(30, 0, 0))
        self.rigid_group([first, second])
        first.setPropertyStatus("Placement", "ReadOnly")
        moving = self.box("Moving", position=(0, 0, 100))
        study = self.study()
        data = Dynamics.run(study)
        for box in (first, second):
            self.assertVectorClose(data["Bodies"][box.Name]["Placements"][-1][:3], tuple(box.Placement.Base))
        self.assertAlmostEqual(data["Bodies"][moving.Name]["Placements"][-1][2], 50.95, delta=0.002)

    def test_existing_slider_joint_and_reaction(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Force", body)
        load.Force = "0.006 N"
        load.Direction = App.Vector(1, 0, 0)  # Slider Z allows no motion along X.
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        data = Dynamics.run(study)
        self.assertVectorClose(data["Bodies"][body.Name]["Placements"][-1][:3], (0, 0, 0))
        reaction = data["JointReactions"][joint.FullName]
        self.assertAlmostEqual(abs(reaction["ForceX"][-1]), 0.006, delta=1e-8)

    def test_coaxial_gears_transmit_torque_with_radius_ratio(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        first = self.box("First")
        second = self.box("Second")
        self.joint("Revolute", ground, first)
        self.joint("Revolute", ground, second)
        gears = self.joint("Gears", first, second)
        gears.Distance = "10 mm"
        gears.Distance2 = "20 mm"

        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", first)
        load.Torque = "0.00025 N*mm"
        data = Dynamics.run(study)

        omega_first = data["Bodies"][first.Name]["AngularVelocity"][-1][2]
        omega_second = data["Bodies"][second.Name]["AngularVelocity"][-1][2]
        self.assertGreater(abs(omega_first), 1e-6)
        self.assertAlmostEqual(omega_second, -0.5 * omega_first, delta=1e-5)

    def test_rack_pinion_transmits_rotation_to_translation(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        rack = self.box("Rack")
        pinion = self.box("Pinion")
        slider = self.joint("Slider", ground, rack)
        rack_axis = App.Rotation(App.Vector(0, 1, 0), 90)
        slider.Placement1.Rotation = rack_axis
        slider.Placement2.Rotation = rack_axis
        self.joint("Revolute", ground, pinion)
        relation = self.joint("RackPinion", rack, pinion)
        relation.Placement1.Rotation = rack_axis
        relation.Distance = "10 mm"

        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", pinion)
        load.Torque = "0.00025 N*mm"
        data = Dynamics.run(study)

        rack_velocity = data["Bodies"][rack.Name]["Velocity"][-1][0]
        pinion_omega = data["Bodies"][pinion.Name]["AngularVelocity"][-1][2]
        self.assertGreater(abs(pinion_omega), 1e-6)
        self.assertAlmostEqual(rack_velocity, 10 * pinion_omega, delta=1e-4)

    def test_screw_transmits_rotation_to_translation_by_pitch(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        slider = self.box("Slider")
        spindle = self.box("Spindle")
        self.joint("Slider", ground, slider)
        self.joint("Revolute", ground, spindle)
        relation = self.joint("Screw", slider, spindle)
        relation.Distance = "20 mm"

        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "Torque", spindle)
        load.Torque = "0.00025 N*mm"
        data = Dynamics.run(study)

        slider_velocity = data["Bodies"][slider.Name]["Velocity"][-1][2]
        spindle_omega = data["Bodies"][spindle.Name]["AngularVelocity"][-1][2]
        self.assertGreater(abs(spindle_omega), 1e-6)
        self.assertAlmostEqual(
            slider_velocity,
            -20 * spindle_omega / (2 * math.pi),
            delta=1e-4,
        )

    def test_rotated_translated_ground_and_vertical_slider_playback(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body, attachment=(0, 0, 0))
        study = self.study()
        # Define a Z slider on rotated parts. Reset after constructing the joint
        # to avoid the joint editor's initial connector-alignment operations.
        rotation = App.Rotation(App.Vector(1, 0, 0), 90)
        ground.Placement = App.Placement(App.Vector(10, 20, 30), rotation)
        body.Placement = App.Placement(App.Vector(10, 20, 60), rotation)
        joint.Placement1 = App.Placement(App.Vector(), rotation.inverted())
        joint.Placement2 = App.Placement(App.Vector(), rotation.inverted())
        original_ground = ground.Placement
        original_body = body.Placement
        data = Dynamics.run(study)
        self.assertTrue(ground.Placement.isSame(original_ground, 1e-10))
        self.assertTrue(body.Placement.isSame(original_body, 1e-10))
        for time, frame in zip(data["Times"], data["SolverFrames"]):
            self.assembly.updateForFrame(frame)
            self.assertTrue(ground.Placement.isSame(original_ground, 1e-9))
            self.assertTrue(body.Placement.Rotation.isSame(rotation, 1e-9))
            self.assertVectorClose(tuple(body.Placement.Base), (10, 20, 60 - 4905*time*time), delta=0.002)
            axis = (ground.Placement * joint.Placement1).Rotation.multVec(App.Vector(0, 0, 1))
            self.assertVectorClose(tuple(axis), (0, 0, 1))

    def test_spring_restoring_acceleration(self):
        body = self.box()
        study = self.study(gravity=False)
        study.EndTime = "0.001 s"
        study.OutputStep = "0.0001 s"
        study.MaximumStep = "0.0001 s"
        load = Dynamics.create_load(study, "SpringDamper", body)
        load.AttachmentI.Base = App.Vector(5, 10, 15)
        load.AttachmentJ.Base = App.Vector(5, 10, -5)
        load.RestLength = "10 mm"
        load.Stiffness = "0.0006 N/mm"
        load.Damping = "0 kg/s"
        data = Dynamics.run(study)
        # 10 mm extension => -0.006 N on a 0.006 kg body.
        self.assertVectorClose(data["Bodies"][body.Name]["Acceleration"][0], (0, 0, -1000), delta=0.01)

    def test_slider_limit_stops_dynamic_motion(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        joint.EnableLengthMin = True
        joint.LengthMin = "-20 mm"
        study = self.study()
        data = Dynamics.run(study)
        result = data["Bodies"][body.Name]
        self.assertGreaterEqual(min(pose[2] for pose in result["Placements"]), -20.001)
        self.assertAlmostEqual(result["Placements"][-1][2], -20, delta=0.001)
        self.assertAlmostEqual(result["Velocity"][-1][2], 0, delta=0.001)

    def test_compliant_slider_limit_rebounds_and_releases(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        joint.EnableLengthMin = True
        joint.LengthMin = "-10 mm"
        joint.LengthMinLimitBehavior = "Compliant"
        joint.LengthMinLimitStiffness = "0.001 N/mm"
        joint.LengthMinLimitDamping = "0 kg/s"
        study = self.study()
        study.EndTime = "0.4 s"
        study.OutputStep = "0.005 s"
        study.MaximumStep = "0.001 s"
        data = Dynamics.run(study)
        result = data["Bodies"][body.Name]
        positions = [pose[2] for pose in result["Placements"]]
        self.assertLess(min(positions), -20)
        self.assertGreater(result["Velocity"][-1][2], 0)
        self.assertGreater(positions[-1], min(positions) + 5)
        limit = data["Limits"][joint.FullName + "-LimitLenMin"]
        self.assertGreater(max(limit["StoredEnergy"]), 0)
        self.assertTrue(all(value >= 0 for value in limit["DissipatedPower"]))
        self.assertAlmostEqual(
            data["Energy"]["System"]["EnergyBalanceResidual"][-1],
            0,
            delta=2e-3,
        )

    def test_slider_limit_sides_have_independent_compliance(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        joint.EnableLengthMin = True
        joint.LengthMin = "-100 mm"
        joint.LengthMinLimitBehavior = "Rigid"
        joint.EnableLengthMax = True
        joint.LengthMax = "10 mm"
        joint.LengthMaxLimitBehavior = "Compliant"
        joint.LengthMaxLimitStiffness = "0.001 N/mm"
        joint.LengthMaxLimitDamping = "0 kg/s"

        study = self.study(gravity=False)
        study.EndTime = "0.31 s"
        study.OutputStep = "0.005 s"
        study.MaximumStep = "0.001 s"
        initial = Dynamics.create_initial_velocity(study, "Linear", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.LinearVelocity = "200 mm/s"

        result = Dynamics.run(study)["Bodies"][body.Name]
        positions = [pose[2] for pose in result["Placements"]]
        self.assertGreater(max(positions), 20)
        self.assertLess(result["Velocity"][-1][2], 0)

    def test_revolute_limit_stops_initial_angular_velocity(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Revolute", ground, body)
        joint.EnableAngleMin = True
        joint.AngleMin = "-30 deg"
        joint.EnableAngleMax = True
        joint.AngleMax = "30 deg"
        study = self.study(gravity=False)
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "10 rad/s"
        data = Dynamics.run(study)
        result = data["Bodies"][body.Name]
        final_rotation = App.Rotation(*result["Placements"][-1][3:])
        self.assertAlmostEqual(final_rotation.Angle, math.radians(30), delta=math.radians(0.01))
        self.assertAlmostEqual(result["AngularVelocity"][-1][2], 0, delta=0.001)

    def test_revolute_limit_sides_have_independent_compliance(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Revolute", ground, body)
        joint.EnableAngleMin = True
        joint.AngleMin = "-120 deg"
        joint.AngleMinLimitBehavior = "Rigid"
        joint.EnableAngleMax = True
        joint.AngleMax = "30 deg"
        joint.AngleMaxLimitBehavior = "Compliant"
        joint.AngleMaxLimitStiffness = "100 N*mm/rad"
        joint.AngleMaxLimitDamping = "0 N*mm*s/rad"

        study = self.study(gravity=False)
        study.EndTime = "0.22 s"
        study.OutputStep = "0.005 s"
        study.MaximumStep = "0.001 s"
        initial = Dynamics.create_initial_velocity(study, "Angular", body)
        initial.Direction = App.Vector(0, 0, 1)
        initial.AngularVelocity = "10 rad/s"

        result = Dynamics.run(study)["Bodies"][body.Name]
        angles = [App.Rotation(*pose[3:]).Angle for pose in result["Placements"]]
        self.assertGreater(max(angles), math.radians(40))
        self.assertLess(result["AngularVelocity"][-1][2], 0)

    def test_prescribed_motion_conflicts_with_limit_on_same_axis(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        joint.EnableLengthMax = True
        joint.LengthMax = "20 mm"
        study = self.study(gravity=False)
        motion = self.doc.addObject("App::FeaturePython", "Motion")
        motion.addProperty("App::PropertyEnumeration", "MotionType")
        motion.MotionType = ["Angular", "Linear"]
        motion.MotionType = "Linear"
        motion.addProperty("App::PropertyXLinkSubHidden", "Joint")
        motion.Joint = joint
        motion.addProperty("App::PropertyString", "Formula")
        motion.Formula = "100*time"
        study.addObject(motion)
        with self.assertRaisesRegex(RuntimeError, "cannot drive an axis with enabled limits"):
            Dynamics.run(study)

    def test_incomplete_joint_rejected_without_deleting_it(self):
        ground = self.box("Ground")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        study = self.study()
        joint.Reference2 = None
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            Dynamics.run(study)
        self.assertIsNotNone(self.doc.getObject(joint.Name))

    def test_invalid_rigid_group_not_silently_repaired(self):
        first = self.box()
        second = self.box("Second")
        study = self.study()
        outsider = self.doc.addObject("Part::Feature", "Outside")
        group = self.rigid_group([first, second, outsider])
        original = list(group.ObjectsToRigidGroup)
        with self.assertRaisesRegex(RuntimeError, "Rigid group"):
            Dynamics.run(study)
        self.assertEqual(group.ObjectsToRigidGroup, original)

    def test_motion_only_dynamics_reports_analytical_motor_torque(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Revolute", ground, body)
        study = self.study(False)
        motion = self.doc.addObject("App::FeaturePython", "Motion")
        motion.addProperty("App::PropertyEnumeration", "MotionType")
        motion.MotionType = ["Angular", "Linear"]
        motion.addProperty("App::PropertyXLinkSubHidden", "Joint")
        motion.Joint = joint
        motion.addProperty("App::PropertyString", "Formula")
        motion.Formula = "time*time"
        study.addObject(motion)
        study.AnalysisType = "Dynamics"
        original = body.Placement
        data = Dynamics.run(study)
        self.assertEqual(data["AnalysisType"], "Dynamics")
        reaction = data["JointReactions"][joint.FullName + "-AngularMotion"]
        # 10 x 20 x 30 mm box: mass 0.006 kg, Izz = 0.25 kg mm^2.
        # theta = t^2 radians, so torque = Izz * 2 / 1000 N mm.
        for torque in reaction["TorqueZ"]:
            self.assertAlmostEqual(abs(torque), 0.0005, delta=1e-8)
        self.assertAlmostEqual(reaction["Work"][-1], 0.5 * 0.25 * 0.2**2 / 1000, delta=1e-9)
        self.assertTrue(body.Placement.isSame(original, 1e-10))
        for mode in ("Kinematics", "Automatic"):
            study.AnalysisType = mode
            self.assertEqual(study.Status, "NotRun")
            data = Dynamics.run(study)
            self.assertEqual(data["AnalysisType"], "Kinematics")
            self.assertFalse(data["JointReactions"])
            self.assertAlmostEqual(data["Times"][-1], 0.1, delta=1e-9)

    def test_kinematics_rejects_physical_inputs_and_clears_results(self):
        body = self.box()
        study = self.study(False)
        Dynamics.run(study)
        study.AnalysisType = "Kinematics"
        load = Dynamics.create_load(study, "Force", body)
        with self.assertRaisesRegex(ValueError, "prescribed motion only"):
            Dynamics.run(study)
        self.assertEqual(study.Status, "Failed")
        self.assertFalse(study.ResultData)
        study.AnalysisType = "Automatic"
        self.assertEqual(Dynamics.analysis_type(study), "Dynamics")
        load.Suppressed = True
        self.assertEqual(Dynamics.analysis_type(study), "Kinematics")

    def test_prescribed_slider_motion_reuses_existing_properties(self):
        ground = self.box("Ground", density=None)
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.box()
        joint = self.joint("Slider", ground, body)
        study = self.study()
        # Same data schema as CommandCreateSimulation.Motion, without importing UI.
        motion = self.doc.addObject("App::FeaturePython", "Motion")
        motion.addProperty("App::PropertyEnumeration", "MotionType")
        motion.MotionType = ["Angular", "Linear"]
        motion.MotionType = "Linear"
        motion.addProperty("App::PropertyXLinkSubHidden", "Joint")
        motion.Joint = joint
        motion.addProperty("App::PropertyString", "Formula")
        motion.Formula = "100*time*time"
        study.addObject(motion)
        data = Dynamics.run(study)
        self.assertAlmostEqual(abs(data["Bodies"][body.Name]["Placements"][-1][2]), 1, delta=1e-5)
        self.assertEqual(len(data["JointReactions"]), 2)
        motion_result = data["JointReactions"][joint.FullName + "-LinearMotion"]
        system = data["Energy"]["System"]
        energy_change = system["MechanicalEnergy"][-1] - system["MechanicalEnergy"][0]
        self.assertAlmostEqual(motion_result["Work"][-1], energy_change, delta=2e-5)
        self.assertAlmostEqual(system["ExternalWork"][-1], energy_change, delta=2e-5)
        self.assertAlmostEqual(system["EnergyBalanceResidual"][-1], 0, delta=2e-5)

    def test_partdesign_tip_not_feature_history(self):
        import _PartDesign
        body = self.assembly.newObject("PartDesign::Body", "Body")
        original = body.newObject("PartDesign::Feature", "FirstShape")
        original.Shape = Part.makeBox(100, 100, 100)
        tip = body.newObject("PartDesign::Feature", "TipShape")
        tip.Shape = Part.makeBox(10, 20, 30)
        body.Tip = tip
        material = Materials.Material()
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        body.ShapeMaterial = material
        self.doc.recompute()
        self.assertAlmostEqual(self.assembly.getMassProperties(body)["Mass"], 0.006)

    def test_failed_run_clears_snapshot(self):
        self.box()
        study = self.study()
        Dynamics.run(study)
        previous_frames = self.assembly.numberOfFrames()
        study.EndTime = "-1 s"
        with self.assertRaises(RuntimeError):
            Dynamics.run(study)
        self.assertEqual(study.Status, "Failed")
        self.assertTrue(study.LastError)
        self.assertEqual(study.ResultData, "")
        self.assertEqual(self.assembly.numberOfFrames(), previous_frames)
        with self.assertRaises(ValueError):
            Dynamics.results(study)

    def test_out_of_scope_load_rejected(self):
        self.box()
        study = self.study()
        outsider = self.doc.addObject("Part::Feature", "Outside")
        Dynamics.create_load(study, "Force", outsider)
        with self.assertRaisesRegex(RuntimeError, "outside"):
            Dynamics.run(study)

    def test_python_argument_types(self):
        with self.assertRaises(TypeError):
            self.assembly.getMassProperties(42)
        with self.assertRaises(TypeError):
            self.assembly.generateDynamics("bad")

    def test_study_load_material_and_results_survive_reopen(self):
        box = self.box()
        # ShapeMaterial persists a library UUID, not ad-hoc unsaved edits.
        box.ShapeMaterial = Materials.MaterialManager().getMaterial("92589471-a6cb-4bbc-b748-d425a17dea7d")
        expected_mass = self.assembly.getMassProperties(box)["Mass"]
        study = self.study(gravity=False)
        load = Dynamics.create_load(study, "SpringDamper", box)
        load.Stiffness = "2 N/mm"
        load.Damping = "0.3 kg/s"
        load.RestLength = "17 mm"
        load.Suppressed = True
        expected = Dynamics.run(study)
        expected_snapshot = Dynamics.results(study)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "Dynamics.FCStd")
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            restored = self.doc.getObject("DynamicsStudy")
            self.assertIsInstance(restored.Proxy, Dynamics.Study)
            self.assertEqual(restored.Status, "Complete")
            self.assertNotIn("Touched", restored.State)
            self.assertEqual(Dynamics.results(restored)["Times"], expected["Times"])
            self.assertEqual(Dynamics.results(restored), expected_snapshot)
            restored_load = self.doc.getObject("SpringDamper")
            self.assertTrue(restored_load.Suppressed)
            self.assertNotIn("Touched", restored_load.State)
            self.assertEqual(restored_load.Stiffness.Unit, App.Units.Unit("N/mm"))
            self.assertAlmostEqual(restored_load.Stiffness.Value, 2000)
            self.assertAlmostEqual(restored_load.Damping.Value, 0.3)
            self.assertEqual(restored_load.BodyI, self.doc.getObject("Box"))
            self.assertAlmostEqual(self.doc.Assembly.getMassProperties(self.doc.Box)["Mass"], expected_mass)
