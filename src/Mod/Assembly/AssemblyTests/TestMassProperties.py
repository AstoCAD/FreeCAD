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

"""Consolidated-component mass-property regressions used by dynamics."""

import unittest

import FreeCAD as App
import Part
import Materials
import AssemblyApp


class TestMassProperties(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("MassPropertiesTest")
        self.doc.UndoMode = 1
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve)

    def box(self, parent, name="Box", density="1000 kg/m^3", position=(0, 0, 0)):
        obj = (
            parent.newObject("Part::Feature", name)
            if parent != self.doc
            else parent.addObject("Part::Feature", name)
        )
        obj.Shape = Part.makeBox(10, 20, 30)
        obj.Placement.Base = App.Vector(*position)
        material = Materials.Material()
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", density)
        obj.ShapeMaterial = material
        return obj

    def link(self, source, scale=1):
        obj = self.assembly.newObject("App::Link", "Occurrence")
        obj.setLink(source)
        obj.Scale = scale
        return obj

    def part(self):
        container = self.doc.addObject("App::Part", "Component")
        self.box(container)
        self.box(container, "Heavy", "2000 kg/m^3", (20, 0, 0))
        return container

    def test_scaled_instances_have_actual_mass(self):
        source = self.box(self.doc)
        ordinary = self.link(source)
        scaled = self.link(source, 2)
        self.assertAlmostEqual(self.assembly.getMassProperties(ordinary)["Mass"], 0.006)
        self.assertAlmostEqual(self.assembly.getMassProperties(scaled)["Mass"], 0.048)

    def test_part_children_have_individual_materials(self):
        container = self.part()
        container.Placement = App.Placement(
            App.Vector(99, 23, 12), App.Rotation(App.Vector(0, 0, 1), 71)
        )
        self.assembly.addObject(container)
        mass = self.assembly.getMassProperties(container)
        self.assertTrue(mass["IsAggregate"])
        self.assertAlmostEqual(mass["Mass"], 0.018)
        self.assertAlmostEqual(mass["CenterOfMass"][0], 55 / 3)
        self.assertAlmostEqual(mass["Inertia"][0][0], 1.95)
        self.assertAlmostEqual(mass["Inertia"][1][1], 3.1)

    def test_part_modeling_history_counts_only_terminal_feature(self):
        container = self.doc.addObject("App::Part", "Component")
        box = container.newObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 10, 20, 30
        tool = container.newObject("Part::Cylinder", "Cylinder")
        tool.Radius, tool.Height = 3, 30
        cut = container.newObject("Part::Cut", "Cut")
        cut.Base, cut.Tool = box, tool
        material = Materials.Material()
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        cut.ShapeMaterial = material
        self.doc.recompute()

        mass = self.assembly.getMassProperties(container)
        self.assertAlmostEqual(mass["Volume"], cut.Shape.Volume)
        self.assertAlmostEqual(mass["Mass"], cut.Shape.Volume * 1e-6)

    def test_link_to_part_scales_aggregate(self):
        source = self.part()
        scaled = self.link(source, 2)
        scaled.Placement.Base = App.Vector(0, 0, 100)
        mass = self.assembly.getMassProperties(scaled)
        self.assertAlmostEqual(mass["Mass"], 0.144)
        self.assertAlmostEqual(mass["CenterOfMass"][0], 110 / 3)
        self.assertAlmostEqual(mass["Inertia"][1][1], 3.1 * 32)

    def test_nested_part_rotates_child_center(self):
        outer = self.doc.addObject("App::Part", "Outer")
        inner = outer.newObject("App::Part", "Inner")
        self.box(inner)
        inner.Placement = App.Placement(
            App.Vector(30, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90)
        )
        mass = self.assembly.getMassProperties(outer)
        for actual, expected in zip(mass["CenterOfMass"], (20, 5, 15)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(mass["Inertia"][0][0], 0.5)

    def test_invalid_child_density_blocks_aggregate(self):
        source = self.part()
        source.Group[-1].ShapeMaterial = Materials.Material()
        with self.assertRaises(ValueError):
            self.assembly.getMassProperties(source)

    def test_nonuniform_scaled_part(self):
        source = self.part()
        occurrence = self.link(source)
        occurrence.ScaleVector = App.Vector(2, 3, 4)
        mass = self.assembly.getMassProperties(occurrence)
        self.assertAlmostEqual(mass["Mass"], 0.018 * 24)
        for actual, expected in zip(mass["CenterOfMass"], (110 / 3, 30, 60)):
            self.assertAlmostEqual(actual, expected)

    def test_part_with_organizational_folder(self):
        container = self.doc.addObject("App::Part", "Component")
        folder = container.newObject("App::DocumentObjectGroup", "Folder")
        self.box(folder)
        container.newObject("App::DocumentObjectGroup", "EmptyFolder")
        self.assembly.addObject(container)
        self.assertEqual(self.assembly.getComponents(), [container])
        self.assertAlmostEqual(self.assembly.getMassProperties(container)["Mass"], 0.006)

    def test_linked_part_frames_match_shape_resolution(self):
        source = self.doc.addObject("App::Part", "Component")
        self.box(source)
        source.Placement = App.Placement(
            App.Vector(91, 23, 17), App.Rotation(App.Vector(0, 0, 1), 37)
        )
        first = self.link(source, 2)
        outer = self.link(first, 3)
        for link_transform in (False, True):
            first.LinkTransform = link_transform
            outer.LinkTransform = link_transform
            self.doc.recompute()
            for occurrence in (first, outer):
                with self.subTest(link_transform=link_transform, occurrence=occurrence.Name):
                    shape = Part.getShape(occurrence, transform=False)
                    mass = self.assembly.getMassProperties(occurrence)
                    self.assertAlmostEqual(mass["Mass"], shape.Volume * 1e-6)
                    self.assertEqual(len(shape.Solids), 1)
                    for actual, expected in zip(
                        mass["CenterOfMass"], shape.Solids[0].CenterOfMass
                    ):
                        self.assertAlmostEqual(actual, expected)

    def test_assembly_folder_does_not_duplicate_components(self):
        folder = self.assembly.newObject("App::DocumentObjectGroup", "Folder")
        component = self.box(folder)
        self.assertEqual(self.assembly.getComponents(), [component])
        self.assertAlmostEqual(self.assembly.getMassProperties(component)["Mass"], 0.006)

    def test_part_can_fall_as_one_dynamics_body(self):
        import Dynamics

        source = self.part()
        occurrence = self.link(source)
        self.assembly.newObject("Assembly::JointGroup", "Joints")
        study = Dynamics.create_study(self.assembly)
        study.GravityEnabled = True
        study.EndTime = "0.1 s"
        study.OutputStep = "0.01 s"
        self.doc.recompute()
        result = self.assembly.generateDynamics(study)
        self.assertAlmostEqual(result["MassProperties"][occurrence.Name]["Mass"], 0.018)
        self.assertEqual(occurrence.Placement.Base, App.Vector())

    def test_material_assignment_is_shared_by_links_and_undoable(self):
        source = self.box(self.doc)
        one, two = self.link(source), self.link(source)
        material = Materials.MaterialManager().getMaterial(
            "92589471-a6cb-4bbc-b748-d425a17dea7d"
        )
        self.doc.openTransaction("Assign Material")
        source.ShapeMaterial = material
        self.doc.commitTransaction()
        self.assertAlmostEqual(self.assembly.getMassProperties(one)["Mass"], 0.0474)
        self.assertAlmostEqual(self.assembly.getMassProperties(two)["Mass"], 0.0474)
        self.doc.undo()
        self.assertAlmostEqual(self.assembly.getMassProperties(one)["Mass"], 0.006)

    @unittest.skipUnless(App.GuiUp, "Requires GUI runtime")
    def test_simulation_toolbar_is_separate(self):
        import FreeCADGui as Gui

        fallback = next(
            name for name in Gui.listWorkbenches() if name != "AssemblyWorkbench"
        )
        try:
            Gui.activateWorkbench(fallback)
            Gui.activateWorkbench("AssemblyWorkbench")
            toolbars = Gui.activeWorkbench().getToolbarItems()
            self.assertNotIn("Assembly_CreateSimulation", toolbars["Assembly"])
            self.assertEqual(
                toolbars["Assembly Simulation"],
                [
                    "Assembly_CreateSimulation",
                    "Assembly_CreateMotion",
                    "Assembly_CreateLoad",
                    "Assembly_CreateInitialVelocity",
                    "Assembly_CreateContact",
                    "Assembly_CreateFriction",
                ],
            )
        finally:
            Gui.activateWorkbench(fallback)
