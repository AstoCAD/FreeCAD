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

"""Regressions for assembly-wide and simulation-local contact."""

import unittest
import math

import AssemblyApp  # Registers Assembly::AssemblyObject.
import FreeCAD as App
import Materials
import Part

import Dynamics


class TestContact(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve_on_recompute = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("ContactTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve_on_recompute)

    @staticmethod
    def material(density="1000 kg/m^3"):
        material = Materials.Material()
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", density)
        return material

    def sphere(self, name, x):
        sphere = self.assembly.newObject("Part::Feature", name)
        sphere.Shape = Part.makeSphere(10)
        sphere.ShapeMaterial = self.material()
        sphere.Placement.Base = App.Vector(x, 0, 0)
        return sphere

    def linked_part_sphere(self, name, x):
        source = self.doc.addObject("App::Part", name + "Source")
        sphere = source.newObject("Part::Feature", name + "Shape")
        sphere.Shape = Part.makeSphere(10)
        sphere.ShapeMaterial = self.material()
        occurrence = self.assembly.newObject("App::Link", name)
        occurrence.setLink(source)
        occurrence.Placement.Base = App.Vector(x, 0, 0)
        return occurrence

    def centered_box(self, name, size, position=(0, 0, 0)):
        x, y, z = size
        box = self.assembly.newObject("Part::Feature", name)
        box.Shape = Part.makeBox(x, y, z, App.Vector(-x / 2, -y / 2, 0))
        box.ShapeMaterial = self.material()
        box.Placement.Base = App.Vector(*position)
        return box

    def study(self, end="0.4 s"):
        study = Dynamics.create_study(self.assembly)
        study.GravityEnabled = False
        study.EndTime = end
        study.OutputStep = "0.005 s"
        study.MaximumStep = "0.0005 s"
        return study

    @staticmethod
    def velocity(study, component, value):
        initial = Dynamics.create_initial_velocity(study, "Linear", component)
        initial.Direction = App.Vector(1, 0, 0)
        initial.LinearVelocity = value

    def test_assembly_contact_rebounds_in_every_simulation(self):
        first = self.sphere("First", -15)
        second = self.sphere("Second", 15)
        contact = Dynamics.create_contact(self.assembly, first, second)
        contact.Stiffness = "0.1 N/mm"

        study = self.study()
        self.velocity(study, first, "100 mm/s")
        self.velocity(study, second, "-100 mm/s")
        data = Dynamics.run(study)

        first_result = data["Bodies"][first.Name]
        second_result = data["Bodies"][second.Name]
        distances = [
            abs(b[0] - a[0])
            for a, b in zip(first_result["Placements"], second_result["Placements"])
        ]
        self.assertLess(min(distances), 20)
        self.assertLess(first_result["Velocity"][-1][0], 0)
        self.assertGreater(second_result["Velocity"][-1][0], 0)
        self.assertNotIn("Touched", contact.State)

        other_study = self.study("0.01 s")
        Dynamics.run(other_study)
        self.assertEqual(study.Status, "Complete")
        self.assertEqual(other_study.Status, "Complete")
        contact.Damping = "0.001 kg/s"
        self.assertEqual(study.Status, "NotRun")
        self.assertEqual(other_study.Status, "NotRun")

    def test_fast_sphere_does_not_tunnel_through_thin_wall(self):
        self.check_fast_sphere(1, 1e-8)

    def test_small_stiff_sphere_contact_with_tight_tolerance(self):
        self.check_fast_sphere(0.1, 1e-11)

    def check_fast_sphere(self, radius, tolerance):
        sphere = self.sphere("Projectile", -2)
        sphere.Shape = Part.makeSphere(radius)
        sphere.Placement.Base = App.Vector(-2, 0, 0)
        wall = self.centered_box("Wall", (0.1, 10, 10), (0, 0, -5))
        wall.setPropertyStatus("Placement", "ReadOnly")
        study = self.study("0.001 s")
        study.MinimumStep = "1e-12 s"
        study.Tolerance = tolerance
        study.OutputStep = "0.00001 s"
        contact = Dynamics.create_contact(study, sphere, wall)
        contact.Stiffness = "100 N/mm"
        self.velocity(study, sphere, "5000 mm/s")
        final_positions = []
        for step in ("0.0005 s", "0.00005 s"):
            study.MaximumStep = step
            body = Dynamics.run(study)["Bodies"][sphere.Name]
            self.assertLess(max(p[0] for p in body["Placements"]), -0.05)
            self.assertLess(body["Velocity"][-1][0], 0)
            # An undamped linear penalty against a fixed plane has an exact
            # half-oscillation impact: velocity reverses without energy loss.
            mass = 4 * math.pi * radius**3 * 1e-6 / 3
            contact_duration = math.pi * math.sqrt(mass / 100000)
            arrival = (2 - radius - 0.05) / 5000
            expected = -radius - 0.05 - 5000 * (0.001 - arrival - contact_duration)
            self.assertAlmostEqual(body["Velocity"][-1][0], -5000, delta=25)
            self.assertAlmostEqual(body["Placements"][-1][0], expected, delta=0.02)
            final_positions.append(body["Placements"][-1][0])
        self.assertAlmostEqual(*final_positions, delta=0.02)

    def test_rotating_bar_hits_obstacle_without_initial_linear_velocity(self):
        bar = self.centered_box("Bar", (10, 0.4, 0.4))
        bar.Shape = Part.makeBox(10, 0.4, 0.4, App.Vector(-5, -0.2, -0.2))
        bar.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), -60)
        obstacle = self.sphere("Obstacle", 3)
        obstacle.Shape = Part.makeSphere(0.25)
        obstacle.Placement.Base = App.Vector(3, 0, 0)
        obstacle.setPropertyStatus("Placement", "ReadOnly")
        study = self.study("0.08 s")
        study.MaximumStep = "0.02 s"
        study.OutputStep = "0.00001 s"
        contact = Dynamics.create_contact(study, bar, obstacle)
        contact.Stiffness = "1 N/mm"
        velocity = Dynamics.create_initial_velocity(study, "Angular", bar)
        velocity.Direction = App.Vector(0, 0, 1)
        velocity.AngularVelocity = "20 rad/s"
        data = Dynamics.run(study)
        self.assertLess(data["Bodies"][bar.Name]["AngularVelocity"][-1][2], 19)
        forces = next(iter(data["Loads"].values()))
        self.assertGreater(max(abs(f) for f in forces["ForceY"]), 1e-5)
        # Translating the entire mechanism must not change a rotational sweep
        # into a rotation about the assembly origin.
        shift = App.Vector(1000, 2000, 3000)
        bar.Placement.Base = shift
        obstacle.Placement.Base = App.Vector(3, 0, 0) + shift
        translated = Dynamics.run(study)
        self.assertAlmostEqual(
            translated["Bodies"][bar.Name]["AngularVelocity"][-1][2],
            data["Bodies"][bar.Name]["AngularVelocity"][-1][2], delta=0.02)

    def test_concave_stack_remains_at_gravity_equilibrium(self):
        ground = self.centered_box("Ground", (40, 40, 10), (0, 0, -10))
        ground.setPropertyStatus("Placement", "ReadOnly")
        ring = Part.makeBox(10, 10, 10, App.Vector(-5, -5, 0)).cut(
            Part.makeBox(4, 4, 12, App.Vector(-2, -2, -1)))
        lower = self.centered_box("Lower", (10, 10, 10))
        upper = self.centered_box("Upper", (10, 10, 10))
        lower.Shape = ring
        upper.Shape = ring
        # Each ring has mass 0.00084 kg. K=1 N/mm: lower contact
        # supports two weights and the upper contact supports one.
        compression = 0.00084 * 9.81
        lower.Placement.Base = App.Vector(0, 0, -2 * compression)
        upper.Placement.Base = App.Vector(0, 0, 10 - 3 * compression)
        study = self.study("0.01 s")
        study.GravityEnabled = True
        study.MaximumStep = "0.0001 s"
        for first, second in ((lower, ground), (upper, lower)):
            contact = Dynamics.create_contact(study, first, second)
            contact.Stiffness = "1 N/mm"
            contact.Damping = "0.1 kg/s"
        data = Dynamics.run(study)
        for body in (lower, upper):
            result = data["Bodies"][body.Name]
            for initial, final in zip(result["Placements"][0][:3], result["Placements"][-1][:3]):
                self.assertAlmostEqual(initial, final, delta=1e-4)
            self.assertLess(App.Vector(*result["Velocity"][-1]).Length, 0.01)
            self.assertLess(App.Vector(*result["AngularVelocity"][-1]).Length, 1e-4)

    def test_sphere_ramp_force_is_geometric_and_rotation_invariant(self):
        sphere = self.sphere("Sphere", 0)
        sphere.Shape = Part.makeSphere(1)
        ramp = self.centered_box("Ramp", (20, 20, 2))
        ramp.Shape = Part.makeBox(20, 20, 2, App.Vector(-10, -10, -2))
        ramp.setPropertyStatus("Placement", "ReadOnly")
        study = self.study("0.000001 s")
        study.OutputStep = study.EndTime
        contact = Dynamics.create_contact(study, sphere, ramp)
        contact.Stiffness = "1 N/mm"
        for rotation in (App.Rotation(App.Vector(0, 1, 0), 30), App.Rotation(32, -17, 23)):
            normal = rotation.multVec(App.Vector(0, 0, 1))
            ramp.Placement.Rotation = rotation
            sphere.Placement.Base = normal * 0.99
            data = Dynamics.run(study)
            force = next(iter(data["Loads"].values()))
            actual = App.Vector(*(force["Force" + axis][0] for axis in "XYZ"))
            self.assertLess((actual - normal * 0.01).Length, 1e-7)
            self.assertLess(App.Vector(*(force["Torque" + axis][0] for axis in "XYZ")).Length, 1e-8)

    def test_parallel_box_contact_has_no_artificial_moment(self):
        first = self.centered_box("First", (10, 10, 10))
        second = self.centered_box("Second", (10, 10, 10), (0, 0, 9.99))
        second.setPropertyStatus("Placement", "ReadOnly")
        study = self.study("0.000001 s")
        study.OutputStep = study.EndTime
        Dynamics.create_contact(study, first, second).Stiffness = "1 N/mm"
        force = next(iter(Dynamics.run(study)["Loads"].values()))
        self.assertAlmostEqual(force["ForceZ"][0], -0.01, delta=1e-6)
        self.assertAlmostEqual(force["ForceX"][0], 0, delta=1e-8)
        self.assertAlmostEqual(force["ForceY"][0], 0, delta=1e-8)
        self.assertAlmostEqual(force["TorqueX"][0], 0, delta=1e-6)
        self.assertAlmostEqual(force["TorqueY"][0], 0, delta=1e-6)

    def test_simulation_contact_is_local(self):
        first = self.sphere("First", -15)
        second = self.sphere("Second", 15)

        without_contact = self.study()
        self.velocity(without_contact, first, "100 mm/s")
        self.velocity(without_contact, second, "-100 mm/s")
        free = Dynamics.run(without_contact)
        self.assertGreater(free["Bodies"][first.Name]["Velocity"][-1][0], 99)
        self.assertLess(free["Bodies"][second.Name]["Velocity"][-1][0], -99)

        with_contact = self.study()
        self.velocity(with_contact, first, "100 mm/s")
        self.velocity(with_contact, second, "-100 mm/s")
        contact = Dynamics.create_contact(with_contact, first, second)
        contact.Stiffness = "0.1 N/mm"
        self.assertEqual(without_contact.Status, "Complete")
        free_again = Dynamics.run(without_contact)
        self.assertGreater(free_again["Bodies"][first.Name]["Velocity"][-1][0], 99)
        self.assertLess(free_again["Bodies"][second.Name]["Velocity"][-1][0], -99)
        bounced = Dynamics.run(with_contact)
        self.assertLess(bounced["Bodies"][first.Name]["Velocity"][-1][0], 0)
        self.assertGreater(bounced["Bodies"][second.Name]["Velocity"][-1][0], 0)

    def test_box_on_inclined_support_has_normal_force_and_no_moment(self):
        body = self.centered_box("Body", (10, 10, 10))
        support = self.centered_box("Support", (40, 40, 10), (0, 0, -10))
        support.setPropertyStatus("Placement", "ReadOnly")
        study = self.study("0.000001 s")
        study.OutputStep = study.EndTime
        contact = Dynamics.create_contact(study, body, support)
        contact.Stiffness = "1 N/mm"
        for rotation in (App.Rotation(), App.Rotation(32, -17, 23)):
            normal = rotation.multVec(App.Vector(0, 0, 1))
            support.Placement = App.Placement(normal * -10, rotation)
            body.Placement = App.Placement(normal * -0.01, rotation)
            force = next(iter(Dynamics.run(study)["Loads"].values()))
            actual = App.Vector(*(force["Force" + axis][0] for axis in "XYZ"))
            moment = App.Vector(*(force["Torque" + axis][0] for axis in "XYZ"))
            self.assertLess((actual - normal * 0.01).Length, 1e-6)
            self.assertLess(moment.Length, 1e-6)

    def test_stack_remains_at_gravity_equilibrium(self):
        ground = self.centered_box("Ground", (40, 40, 10), (0, 0, -10))
        ground.setPropertyStatus("Placement", "ReadOnly")
        # Each 10 mm cube weighs 0.00981 N. At 1 N/mm, the lower
        # contact compresses twice as much because it supports both cubes.
        lower = self.centered_box("Lower", (10, 10, 10), (0, 0, -0.01962))
        upper = self.centered_box("Upper", (10, 10, 10), (0, 0, 10 - 0.02943))
        study = self.study("0.05 s")
        study.GravityEnabled = True
        study.MaximumStep = "0.0001 s"
        for first, second in ((lower, ground), (upper, lower)):
            contact = Dynamics.create_contact(study, first, second)
            contact.Stiffness = "1 N/mm"
            contact.Damping = "1 kg/s"
        data = Dynamics.run(study)
        for component in (lower, upper):
            result = data["Bodies"][component.Name]
            for pose, velocity, omega in zip(
                result["Placements"], result["Velocity"], result["AngularVelocity"]
            ):
                self.assertLess((App.Vector(*pose[:3]) - component.Placement.Base).Length, 1e-4)
                self.assertLess(App.Vector(*velocity).Length, 0.01)
                self.assertLess(App.Vector(*omega).Length, 1e-4)

    def test_falling_box_settles_with_step_refinement(self):
        ground = self.centered_box("Ground", (40, 40, 10), (0, 0, -10))
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.centered_box("Body", (10, 10, 10), (0, 0, 0.2))
        study = self.study("0.15 s")
        study.GravityEnabled = True
        contact = Dynamics.create_contact(study, body, ground)
        contact.Stiffness = "0.1 N/mm"
        contact.Damping = "0.5 kg/s"
        final_heights = []
        for step in ("0.0002 s", "0.0001 s"):
            study.MaximumStep = step
            result = Dynamics.run(study)["Bodies"][body.Name]
            final_heights.append(result["Placements"][-1][2])
            # m*g/k: 0.001 kg * 9.81 m/s^2 / (0.1 N/mm).
            self.assertAlmostEqual(final_heights[-1], -0.0981, delta=0.002)
            self.assertLess(App.Vector(*result["Velocity"][-1]).Length, 0.1)
            self.assertLess(App.Vector(*result["AngularVelocity"][-1]).Length, 1e-4)
        self.assertAlmostEqual(final_heights[0], final_heights[1], delta=0.001)

    def test_links_to_app_parts_are_contact_components(self):
        first = self.linked_part_sphere("FirstOccurrence", -15)
        second = self.linked_part_sphere("SecondOccurrence", 15)
        Dynamics.create_contact(self.assembly, first, second).Stiffness = "0.1 N/mm"
        study = self.study()
        self.velocity(study, first, "100 mm/s")
        self.velocity(study, second, "-100 mm/s")

        data = Dynamics.run(study)
        self.assertLess(data["Bodies"][first.Name]["Velocity"][-1][0], 0)
        self.assertGreater(data["Bodies"][second.Name]["Velocity"][-1][0], 0)

    def test_general_mode_expands_all_sphere_pairs(self):
        first = self.sphere("First", -15)
        middle = self.sphere("Middle", 15)
        self.sphere("FarAway", 200)
        contact = Dynamics.create_contact(
            self.assembly, mode="General collision detection"
        )
        contact.Stiffness = "0.1 N/mm"
        self.assertIsNone(contact.ComponentI)
        self.assertIsNone(contact.ComponentJ)

        study = self.study()
        self.velocity(study, first, "100 mm/s")
        self.velocity(study, middle, "-100 mm/s")
        data = Dynamics.run(study)
        self.assertLess(data["Bodies"][first.Name]["Velocity"][-1][0], 0)
        self.assertGreater(data["Bodies"][middle.Name]["Velocity"][-1][0], 0)

    def test_arbitrary_solid_contact_rebounds_in_dynamics(self):
        # Exercise conversion between solver-local coordinates and transformed
        # document geometry, not just an Assembly at the document origin.
        self.assembly.Placement = App.Placement(
            App.Vector(80, -30, 20), App.Rotation(App.Vector(0, 0, 1), 37)
        )
        first = self.assembly.newObject("Part::Feature", "FirstBox")
        first.Shape = Part.makeBox(10, 12, 14)
        first.ShapeMaterial = self.material()
        first.Placement.Base = App.Vector(-15, 0, 0)
        second = self.assembly.newObject("Part::Feature", "SecondBox")
        second.Shape = Part.makeBox(10, 12, 14)
        second.ShapeMaterial = self.material()
        second.Placement.Base = App.Vector(5, 0, 0)
        contact = Dynamics.create_contact(self.assembly, first, second)
        contact.Stiffness = "0.1 N/mm"

        study = self.study("0.12 s")
        self.velocity(study, first, "100 mm/s")
        self.velocity(study, second, "-100 mm/s")
        data = Dynamics.run(study)

        self.assertEqual(study.Status, "Complete")
        self.assertLess(data["Bodies"][first.Name]["Velocity"][-1][0], 0)
        self.assertGreater(data["Bodies"][second.Name]["Velocity"][-1][0], 0)

    def test_contact_friction_transfers_tangential_momentum(self):
        first = self.sphere("First", -15)
        second = self.sphere("Second", 15)
        contact = Dynamics.create_contact(self.assembly, first, second)
        contact.Stiffness = "0.1 N/mm"

        def oblique_study():
            study = self.study()
            oblique = Dynamics.create_initial_velocity(study, "Linear", first)
            oblique.Direction = App.Vector(1, 1, 0)
            oblique.LinearVelocity = f"{100 * 2**0.5} mm/s"
            self.velocity(study, second, "-100 mm/s")
            return study

        frictionless = Dynamics.run(oblique_study())
        contact.FrictionEnabled = True
        contact.StaticFriction = 0.8
        contact.DynamicFriction = 0.6
        contact.FrictionTransitionVelocity = "1 mm/s"
        friction = Dynamics.run(oblique_study())

        first_baseline = frictionless["Bodies"][first.Name]["Velocity"][-1]
        second_baseline = frictionless["Bodies"][second.Name]["Velocity"][-1]
        first_velocity = friction["Bodies"][first.Name]["Velocity"][-1]
        second_velocity = friction["Bodies"][second.Name]["Velocity"][-1]
        self.assertLess(first_velocity[1], first_baseline[1] - 10)
        self.assertGreater(second_velocity[1], second_baseline[1] + 10)
        self.assertAlmostEqual(first_velocity[1] + second_velocity[1], 100, delta=0.1)

    def test_arbitrary_solid_contact_includes_friction(self):
        first = self.assembly.newObject("Part::Feature", "FirstBox")
        # Broad parallel faces keep the contact normal on X, so the Y result
        # isolates tangential friction instead of normal deflection.
        first.Shape = Part.makeBox(10, 100, 100)
        first.ShapeMaterial = self.material()
        first.Placement.Base = App.Vector(-15, 0, 0)
        second = self.assembly.newObject("Part::Feature", "SecondBox")
        second.Shape = Part.makeBox(10, 100, 100)
        second.ShapeMaterial = self.material()
        second.Placement.Base = App.Vector(5, 0, 0)
        contact = Dynamics.create_contact(self.assembly, first, second)
        contact.Stiffness = "1 N/mm"

        def oblique_study():
            study = self.study("0.12 s")
            oblique = Dynamics.create_initial_velocity(study, "Linear", first)
            oblique.Direction = App.Vector(1, 1, 0)
            oblique.LinearVelocity = f"{100 * 2**0.5} mm/s"
            self.velocity(study, second, "-100 mm/s")
            return study

        frictionless = Dynamics.run(oblique_study())
        contact.FrictionEnabled = True
        contact.StaticFriction = 0.8
        contact.DynamicFriction = 0.6
        friction = Dynamics.run(oblique_study())

        first_baseline = frictionless["Bodies"][first.Name]["Velocity"][-1]
        second_baseline = frictionless["Bodies"][second.Name]["Velocity"][-1]
        first_velocity = friction["Bodies"][first.Name]["Velocity"][-1]
        second_velocity = friction["Bodies"][second.Name]["Velocity"][-1]
        self.assertLess(first_velocity[1], first_baseline[1] - 5)
        self.assertGreater(second_velocity[1], second_baseline[1] + 5)

    def test_face_contact_manifold_damps_rocking(self):
        ground = self.centered_box("Ground", (40, 40, 10), (0, 0, -10))
        ground.setPropertyStatus("Placement", "ReadOnly")
        body = self.centered_box("Body", (20, 20, 10), (0, 0, -0.25))
        contact = Dynamics.create_contact(self.assembly, body, ground)
        contact.Stiffness = "0.02 N/mm"
        contact.Damping = "0.02 kg/s"

        study = self.study("0.01 s")
        study.MaximumStep = "0.0001 s"
        angular = Dynamics.create_initial_velocity(study, "Angular", body)
        angular.Direction = App.Vector(1, 0, 0)
        angular.AngularVelocity = "1 rad/s"
        data = Dynamics.run(study)

        result = data["Bodies"][body.Name]
        self.assertLess(abs(result["AngularVelocity"][-1][0]), 0.95)
        pose = result["Placements"][-1]
        rotation = App.Rotation(*pose[3:])
        center_lever = rotation.multVec(App.Vector(0, 0, 5))
        center_velocity = App.Vector(*result["Velocity"][-1]) + App.Vector(
            *result["AngularVelocity"][-1]
        ).cross(center_lever)
        self.assertAlmostEqual(center_velocity.x, 0, delta=1e-5)
        self.assertAlmostEqual(center_velocity.y, 0, delta=1e-5)

    def test_arbitrary_body_can_resolve_simultaneous_contacts(self):
        left = self.centered_box("LeftWall", (10, 40, 40), (-10, 0, -20))
        right = self.centered_box("RightWall", (10, 40, 40), (10, 0, -20))
        left.setPropertyStatus("Placement", "ReadOnly")
        right.setPropertyStatus("Placement", "ReadOnly")
        body = self.centered_box("Body", (10.5, 10, 10), (0, 0, -5))
        first = Dynamics.create_contact(self.assembly, body, left)
        second = Dynamics.create_contact(self.assembly, body, right)
        for contact in (first, second):
            contact.Stiffness = "0.02 N/mm"
            contact.Damping = "0.001 kg/s"

        study = self.study("0.01 s")
        study.MaximumStep = "0.0001 s"
        data = Dynamics.run(study)

        result = data["Bodies"][body.Name]
        self.assertAlmostEqual(result["Placements"][-1][0], 0, delta=0.01)
        self.assertAlmostEqual(result["Velocity"][-1][0], 0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
