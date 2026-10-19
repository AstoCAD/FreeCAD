# SPDX-License-Identifier: LGPL-2.1-or-later
# /****************************************************************************
#                                                                           *
#    Copyright (c) 2023 Ondsel <development@ondsel.com>                     *
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
# ***************************************************************************/

import FreeCAD as App
import Part
import os
import tempfile
import unittest

import UtilsAssembly
import JointObject


def _msg(text, end="\n"):
    """Write messages to the console including the line ending."""
    App.Console.PrintMessage(text + end)


class AssemblyTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """setUpClass()...
        This method is called upon instantiation of this test class.  Add code and objects here
        that are needed for the duration of the test() methods in this class.  In other words,
        set up the 'global' test environment here; use the `setUp()` method to set up a 'local'
        test environment.
        This method does not have access to the class `self` reference, but it
        is able to call static methods within this same class.
        """
        pass

    @classmethod
    def tearDownClass(cls):
        """tearDownClass()...
        This method is called prior to destruction of this test class.  Add code and objects here
        that cleanup the test environment after the test() methods in this class have been executed.
        This method does not have access to the class `self` reference.  This method
        is able to call static methods within this same class.
        """
        pass

    # Setup and tear down methods called before and after each unit test
    def setUp(self):
        """setUp()...
        This method is called prior to each `test()` method.  Add code and objects here
        that are needed for multiple `test()` methods.
        """
        doc_name = self.__class__.__name__
        if App.ActiveDocument:
            if App.ActiveDocument.Name != doc_name:
                App.newDocument(doc_name)
        else:
            App.newDocument(doc_name)
        App.setActiveDocument(doc_name)
        self.doc = App.ActiveDocument

        self.assembly = App.ActiveDocument.addObject("Assembly::AssemblyObject", "Assembly")
        if self.assembly:
            self.jointgroup = self.assembly.newObject("Assembly::JointGroup", "Joints")

        _msg("  Temporary document '{}'".format(self.doc.Name))

    def tearDown(self):
        """tearDown()...
        This method is called after each test() method. Add cleanup instructions here.
        Such cleanup instructions will likely undo those in the setUp() method.
        """
        App.closeDocument(self.doc.Name)


class TestCore(AssemblyTestBase):
    def test_simulation_rejects_non_document_object_arguments(self):
        for value in (None, True, 1, 1.25, "invalid", [], {}, object()):
            with self.subTest(argument_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    self.assembly.generateSimulation(value)

    def _check_origin_only_simulation(self, study_type):
        study = self.doc.addObject(study_type, "Study")
        self.assertEqual(study.Group, [])
        self.assertIsNotNone(self.assembly.Origin)
        self.assertEqual(self.assembly.getComponents(), [])
        # The origin is grounded even without components, so this is a valid
        # empty simulation and must retain the successful return value.
        self.assertEqual(self.assembly.generateSimulation(study), 0)

    def test_simulation_accepts_document_object_group(self):
        self._check_origin_only_simulation("App::DocumentObjectGroup")

    def test_simulation_accepts_python_document_object_group(self):
        self._check_origin_only_simulation("App::DocumentObjectGroupPython")

    def _check_generated_property_strings(self, value, enumeration=False):
        source = self.doc.addObject("App::FeaturePython", "RecordedObject")
        source.addProperty("App::PropertyString", "Text")
        source.addProperty("App::PropertyEnumeration", "Choice")
        source.Choice = ["Initial", value] if enumeration else ["Initial", "Other"]
        source.Choice = value if enumeration else "Other"
        source.Text = value
        source.Label = value
        command = UtilsAssembly.generatePropertySettings(source)

        replay_doc = App.newDocument("AssemblyPropertySettingsReplay")
        try:
            replayed = replay_doc.addObject("App::FeaturePython", source.Name)
            replayed.addProperty("App::PropertyString", "Text")
            replayed.addProperty("App::PropertyEnumeration", "Choice")
            replayed.Choice = source.getEnumerationsOfProperty("Choice")
            replayed.Choice = "Initial"
            exec(compile(command, "<Assembly property settings>", "exec"), {"App": App})
            self.assertEqual(replayed.Text, value)
            self.assertEqual(replayed.Label, value)
            self.assertEqual(replayed.Choice, value if enumeration else "Other")
        finally:
            App.closeDocument(replay_doc.Name)
            App.setActiveDocument(self.doc.Name)

    def test_generated_settings_preserve_ascii_strings(self):
        self._check_generated_property_strings("Ordinary label")

    def test_generated_settings_preserve_unicode_strings(self):
        self._check_generated_property_strings("Café α 测量")

    def test_generated_settings_preserve_quoted_strings(self):
        self._check_generated_property_strings('Part "quoted"')

    def test_generated_settings_preserve_literal_backslash(self):
        self._check_generated_property_strings("C:\\new\\tool")

    def test_generated_settings_preserve_multiline_strings(self):
        self._check_generated_property_strings("First line\nSecond line")

    def test_generated_settings_preserve_quoted_enumeration(self):
        self._check_generated_property_strings('Option "quoted"', enumeration=True)

    def _check_grounded_part_with_assembly_type(self, tag):
        self.assembly.Type = tag
        free = self.assembly.newObject("Part::Box", "Free")
        free.Placement = App.Placement(App.Vector(40, 50, 60), App.Rotation())
        grounded = self.assembly.newObject("Part::Box", "Grounded")
        grounded.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation())
        self.doc.recompute()
        ground = self.jointgroup.newObject("App::FeaturePython", "Ground")
        JointObject.GroundedJoint(ground, grounded)
        self.doc.recompute()
        initial_ground = App.Placement(grounded.Placement)
        self.assertTrue(self.assembly.isPartConnected(grounded))
        self.assertFalse(self.assembly.isPartConnected(free))

        joint = self.jointgroup.newObject("App::FeaturePython", "Fixed")
        JointObject.Joint(joint, JointObject.JointTypes.index("Fixed"))
        self.assertEqual(joint.Proxy.getAssembly(joint), self.assembly)
        joint.Proxy.setJointConnectors(
            joint,
            [[free, ["Face6", "Vertex7"]], [grounded, ["Face6", "Vertex7"]]],
        )

        self.assertTrue(grounded.Placement.isSame(initial_ground, 1e-6))

    def test_empty_assembly_type_preserves_grounded_second_reference(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32650 (Type metadata cause).
        self._check_grounded_part_with_assembly_type("")

    def test_canonical_assembly_type_preserves_grounded_second_reference(self):
        self._check_grounded_part_with_assembly_type("Assembly")

    def test_custom_assembly_type_preserves_grounded_second_reference(self):
        self._check_grounded_part_with_assembly_type("Custom assembly metadata")

    def test_plain_part_matching_still_moves_second_component(self):
        part = self.doc.addObject("App::Part", "OrdinaryPart")
        first = part.newObject("Part::Box", "First")
        second = part.newObject("Part::Box", "Second")
        second.Placement = App.Placement(App.Vector(100, 0, 0), App.Rotation())
        self.doc.recompute()
        joint = part.newObject("App::FeaturePython", "Match")
        JointObject.Joint(joint, JointObject.JointTypes.index("Fixed"))
        self.assertIsNone(joint.Proxy.getAssembly(joint))
        joint.Proxy.setJointConnectors(
            joint,
            [[first, ["Face6", "Vertex7"]], [second, ["Face6", "Vertex7"]]],
        )

        self.assertTrue(second.Placement.isSame(first.Placement, 1e-6))

    def test_bom_accepts_plain_part_features(self):
        """Mirror detection must not treat every component as a LinkElement."""
        box = self.assembly.newObject("Part::Box", "Component")
        box.Label = "Plain component"
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Quantity"]

        self.doc.recompute()

        self.assertEqual(bom.get("A2"), box.Label)
        self.assertEqual(int(float(bom.get("B2"))), 1)
        self.assertNotIn("Invalid", bom.State)

    def test_bom_separates_mirrored_link_from_regular_link(self):
        source = self.doc.addObject("Part::Box", "ComponentSource")
        source.Label = "Component"
        regular = self.assembly.newObject("App::Link", "Regular")
        regular.LinkedObject = source
        mirrored = self.assembly.newObject("App::Link", "Mirrored")
        mirrored.LinkedObject = source
        mirrored.Scale = -1
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Quantity"]

        self.doc.recompute()

        suffix = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly").GetString(
            "BomMirroredSuffix", " (mirrored)"
        )
        self.assertEqual({bom.get("A2"), bom.get("A3")}, {source.Label, source.Label + suffix})
        self.assertEqual(int(float(bom.get("B2"))), 1)
        self.assertEqual(int(float(bom.get("B3"))), 1)
        self.assertNotIn("Invalid", bom.State)

    def _check_bom_scale_vector_grouping(self, scale, mirrored, previous_scalar=None):
        source = self.doc.addObject("Part::Box", "VectorScaleComponent")
        source.Label = "Vector scale component"
        normal = self.assembly.newObject("App::Link", "NormalOccurrence")
        normal.setLink(source)
        transformed = self.assembly.newObject("App::Link", "TransformedOccurrence")
        transformed.setLink(source)
        if previous_scalar is not None:
            transformed.Scale = previous_scalar
        transformed.ScaleVector = App.Vector(*scale)
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Quantity"]
        self.doc.recompute()
        self.assertNotIn("Invalid", bom.State)
        self.assertEqual(tuple(transformed.ScaleVector), scale)
        if previous_scalar is not None and len(set(scale)) > 1:
            self.assertEqual(transformed.Scale, previous_scalar)

        rows = sorted(
            (bom.get(cell), int(float(bom.get("B" + cell[1:]))))
            for cell in bom.getNonEmptyCells()
            if cell.startswith("A") and int(cell[1:]) > 1
        )
        suffix = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly").GetString(
            "BomMirroredSuffix", " (mirrored)"
        )
        expected = sorted([(source.Label, 1), (source.Label + suffix, 1)]) if mirrored else [
            (source.Label, 2)
        ]
        self.assertEqual(rows, expected)

    def test_bom_groups_unscaled_occurrences(self):
        self._check_bom_scale_vector_grouping((1.0, 1.0, 1.0), mirrored=False)

    def test_bom_separates_uniform_negative_scale(self):
        self._check_bom_scale_vector_grouping((-1.0, -1.0, -1.0), mirrored=True)

    def test_bom_separates_single_axis_reflection(self):
        self._check_bom_scale_vector_grouping((-1.0, 1.0, 1.0), mirrored=True)

    def test_bom_groups_paired_reflections_despite_stale_negative_scalar(self):
        self._check_bom_scale_vector_grouping(
            (-1.0, -1.0, 1.0), mirrored=False, previous_scalar=-1.0
        )

    def _check_bom_hierarchical_quantities(
        self, nested, same_source, root_count=1, quantity=True, detail_parts=True
    ):
        source = self.doc.addObject("Part::Box", "ComponentSource")
        source.Label = "Shared component"
        root_source = source
        if not same_source:
            root_source = self.doc.addObject("Part::Box", "OtherSource")
            root_source.Label = "Other component"
        if nested:
            container = self.assembly.newObject("App::Part", "SubPart")
            container.Label = "Subpart"
            child = container.newObject("App::Link", "NestedOccurrence")
            child.setLink(source)
        for _ in range(root_count):
            link = self.assembly.newObject("App::Link", "RootOccurrence")
            link.setLink(root_source)
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Index", "Name", "Quantity"] if quantity else ["Index", "Name"]
        bom.detailParts = detail_parts
        bom.onlyParts = False
        self.doc.recompute()
        self.assertNotIn("Invalid", bom.State)

        cells = sorted(
            (
                cell for cell in bom.getNonEmptyCells()
                if cell.startswith("A") and int(cell[1:]) > 1
            ),
            key=lambda cell: int(cell[1:]),
        )
        rows = [
            (
                bom.get(cell).lstrip("'"),
                bom.get("B" + cell[1:]),
                int(float(bom.get("C" + cell[1:]))) if quantity else None,
            )
            for cell in cells
        ]
        expected = []
        if nested:
            expected.append(("1", container.Label, 1 if quantity else None))
            if detail_parts:
                expected.append(("1.1", source.Label, 1 if quantity else None))
        root_index = 2 if nested else 1
        if quantity:
            expected.append((str(root_index), root_source.Label, root_count))
        else:
            expected.extend(
                (str(root_index + index), root_source.Label, None)
                for index in range(root_count)
            )
        self.assertEqual(rows, expected)

    def test_bom_groups_same_level_duplicate_links(self):
        self._check_bom_hierarchical_quantities(nested=False, same_source=True, root_count=2)

    def test_bom_keeps_distinct_nested_and_root_sources(self):
        self._check_bom_hierarchical_quantities(nested=True, same_source=False)

    def test_bom_keeps_same_source_at_nested_and_root_levels_separate(self):
        self._check_bom_hierarchical_quantities(nested=True, same_source=True)

    def test_bom_groups_root_duplicates_without_merging_nested_occurrence(self):
        self._check_bom_hierarchical_quantities(nested=True, same_source=True, root_count=2)

    def test_bom_without_quantity_keeps_every_occurrence(self):
        self._check_bom_hierarchical_quantities(
            nested=True, same_source=True, root_count=2, quantity=False
        )

    def test_bom_without_part_details_keeps_root_quantity(self):
        self._check_bom_hierarchical_quantities(
            nested=True, same_source=True, root_count=2, detail_parts=False
        )

    def test_component_count_for_link_array(self):
        source = self.doc.addObject("Part::Box", "ArraySource")
        array = self.assembly.newObject("App::Link", "Array")
        array.LinkedObject = source
        array.ElementCount = 3
        array.ShowElement = False
        self.doc.recompute()
        self.assertEqual(len(array.ElementList), 0)
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 3)

        array.ShowElement = True
        self.doc.recompute()
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 3)
        array.ElementList[1].Suppressed = True
        self.doc.recompute()
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 2)
        array.ElementList[1].Suppressed = False
        self.doc.recompute()
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 3)

    def test_generated_array_is_one_component(self):
        source = self.doc.addObject("Part::Box", "ArraySource")
        array = self.assembly.newObject("Part::LinkArrayLinear", "Array")
        array.LinkedObject = source
        array.Occurrences = 3
        self.doc.recompute()
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 1)
        self.assertEqual(UtilsAssembly.getSubMovingParts(array, False), [array])
        self.assertEqual(UtilsAssembly.getObject((array, ["1.Face1"])), array)

    def test_suppressed_link_elements_are_not_movable(self):
        source = self.doc.addObject("Part::Box", "ArraySource")
        array = self.assembly.newObject("App::Link", "Array")
        array.LinkedObject = source
        array.ElementCount = 3
        self.doc.recompute()
        element = array.ElementList[1]
        element.Suppressed = True
        self.doc.recompute()
        self.assertNotIn(element, UtilsAssembly.getMovablePartsWithin(array))
        element.Suppressed = False
        self.doc.recompute()
        self.assertIn(element, UtilsAssembly.getMovablePartsWithin(array))

    def test_assembly_link_synchronizes_element_suppression(self):
        source = self.doc.addObject("Part::Box", "ArraySource")
        array = self.assembly.newObject("App::Link", "Array")
        array.LinkedObject = source
        array.ElementCount = 3
        array.ElementList[1].Suppressed = True
        parent = self.doc.addObject("Assembly::AssemblyObject", "ParentAssembly")
        instance = parent.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = self.assembly
        self.doc.recompute()
        local_array = next(obj for obj in instance.Group if obj.TypeId == "App::Link")
        self.assertTrue(local_array.ElementList[1].Suppressed)
        array.ElementList[1].Suppressed = False
        instance.touch()
        self.doc.recompute()
        self.assertFalse(local_array.ElementList[1].Suppressed)

    def test_assembly_link_maps_generated_array_joint(self):
        self._check_generated_array_joint("Face1")

    def test_assembly_link_maps_generated_array_whole_element_joint(self):
        self._check_generated_array_joint("")

    def _check_generated_array_joint(self, sub):
        source = self.doc.addObject("Part::Box", "ArraySource")
        array = self.assembly.newObject("Part::LinkArrayLinear", "Array")
        array.LinkedObject = source
        array.Occurrences = 3
        array.ShowElement = True
        self.doc.recompute()
        joint = self.jointgroup.newObject("App::FeaturePython", "Joint")
        JointObject.Joint(joint, 0)
        joint.Reference1 = (array.ElementList[1], [sub])
        joint.Reference2 = (array.ElementList[2], ["Face1"])
        parent = self.doc.addObject("Assembly::AssemblyObject", "ParentAssembly")
        instance = parent.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = self.assembly
        instance.Rigid = False
        self.doc.recompute()
        local_array = next(obj for obj in instance.Group if obj.TypeId == "App::Link")
        local_group = next(obj for obj in instance.Group if obj.TypeId == "Assembly::JointGroup")
        local_joint = local_group.Group[0]
        self.assertEqual(local_joint.Reference1, (local_array, ["1." + sub]))
        self.assertIsNotNone(local_array.getSubObject("1." + sub))

    def test_create_assembly(self):
        """Create an assembly."""
        operation = "Create Assembly Object"
        _msg("  Test '{}'".format(operation))
        self.assertTrue(self.assembly, "'{}' failed".format(operation))

    def test_create_jointGroup(self):
        """Create a joint group in an assembly."""
        operation = "Create JointGroup Object"
        _msg("  Test '{}'".format(operation))
        self.assertTrue(self.jointgroup, "'{}' failed".format(operation))

    def test_create_joint(self):
        """Create a joint in an assembly."""
        operation = "Create Joint Object"
        _msg("  Test '{}'".format(operation))

        joint = self.jointgroup.newObject("App::FeaturePython", "testJoint")
        self.assertTrue(joint, "'{}' failed (FeaturePython creation failed)".format(operation))
        JointObject.Joint(joint, 0)

        self.assertTrue(hasattr(joint, "JointType"), "'{}' failed".format(operation))

    def test_joints_in_nested_group_are_detected(self):
        """Joints remain active when organized in a folder under JointGroup."""
        box1 = self.assembly.newObject("Part::Box", "Box1")
        box2 = self.assembly.newObject("Part::Box", "Box2")
        folder = self.jointgroup.newObject("App::DocumentObjectGroup", "JointFolder")
        joint = folder.newObject("App::FeaturePython", "NestedJoint")
        JointObject.Joint(joint, 0)
        self.doc.recompute()
        joint.Proxy.setJointConnectors(
            joint,
            [[box1, ["Face1", "Face1"]], [box2, ["Face1", "Face1"]]],
        )

        self.assertIn(joint, self.assembly.Joints)

    def test_create_grounded_joint(self):
        """Create a grounded joint in an assembly."""
        operation = "Create Grounded Joint Object"
        _msg("  Test '{}'".format(operation))

        groundedjoint = self.jointgroup.newObject("App::FeaturePython", "testJoint")
        self.assertTrue(
            groundedjoint, "'{}' failed (FeaturePython creation failed)".format(operation)
        )

        box = self.assembly.newObject("Part::Box", "Box")

        JointObject.GroundedJoint(groundedjoint, box)

        self.assertTrue(
            hasattr(groundedjoint, "ObjectToGround"),
            "'{}' failed: No attribute 'ObjectToGround'".format(operation),
        )
        self.assertTrue(
            groundedjoint.ObjectToGround == box,
            "'{}' failed: ObjectToGround not set correctly.".format(operation),
        )

    def test_toggle_grounded_joint(self):
        """test grounding and ungrounding a part, added because of github.com/freecad/freecad/issues/28440"""
        operation = "Toggle Grounded Joint"
        _msg("  Test '{}'".format(operation))

        box = self.assembly.newObject("Part::Box", "Box")

        # ground the part
        groundedjoint = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(groundedjoint, box)
        self.doc.recompute()

        # verify grounded
        self.assertTrue(
            hasattr(groundedjoint, "ObjectToGround"),
            "'{}' failed: No attribute 'ObjectToGround'".format(operation),
        )
        self.assertEqual(
            groundedjoint.ObjectToGround,
            box,
            "'{}' failed: ObjectToGround not set correctly".format(operation),
        )

        # unground the part
        self.doc.removeObject(groundedjoint.Name)
        self.doc.recompute()

        # verify no grounded joints remain in this part
        for joint in self.jointgroup.Group:
            if hasattr(joint, "ObjectToGround"):
                self.assertNotEqual(
                    joint.ObjectToGround,
                    box,
                    "'{}' failed: part still grounded after toggle".format(operation),
                )

    def test_find_placement(self):
        """Test find placement of joint."""
        operation = "Find placement"
        _msg("  Test '{}'".format(operation))

        joint = self.jointgroup.newObject("App::FeaturePython", "testJoint")
        JointObject.Joint(joint, 0)

        L = 2
        W = 3
        H = 7
        box = self.assembly.newObject("Part::Box", "Box")
        box.Length = L
        box.Width = W
        box.Height = H
        box.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation(15, 25, 35))

        # Step 0 : box with placement. No element selected
        ref = [self.assembly, [box.Name + ".", box.Name + "."]]
        plc = joint.Proxy.findPlacement(joint, ref)
        targetPlc = App.Placement(App.Vector(), App.Rotation())
        self.assertTrue(plc.isSame(targetPlc, 1e-6), "'{}' failed - Step 0".format(operation))

        # Step 1 : box with placement. Face + Vertex
        ref = [self.assembly, [box.Name + ".Face6", box.Name + ".Vertex7"]]
        plc = joint.Proxy.findPlacement(joint, ref)
        targetPlc = App.Placement(App.Vector(L, W, H), App.Rotation())
        self.assertTrue(plc.isSame(targetPlc, 1e-6), "'{}' failed - Step 1".format(operation))

        # Step 2 : box with placement. Edge + Vertex
        ref = [self.assembly, [box.Name + ".Edge8", box.Name + ".Vertex8"]]
        plc = joint.Proxy.findPlacement(joint, ref)
        targetPlc = App.Placement(App.Vector(L, W, 0), App.Rotation(0, -90, 270))
        self.assertTrue(plc.isSame(targetPlc, 1e-6), "'{}' failed - Step 2".format(operation))

        # Step 3 : box with placement. Vertex
        ref = [self.assembly, [box.Name + ".Vertex3", box.Name + ".Vertex3"]]
        plc = joint.Proxy.findPlacement(joint, ref)
        targetPlc = App.Placement(App.Vector(0, W, H), App.Rotation())
        _msg("  plc '{}'".format(plc))
        _msg("  targetPlc '{}'".format(targetPlc))
        self.assertTrue(plc.isSame(targetPlc, 1e-6), "'{}' failed - Step 3".format(operation))

        # Step 4 : box with placement. Face
        ref = [self.assembly, [box.Name + ".Face2", box.Name + ".Face2"]]
        plc = joint.Proxy.findPlacement(joint, ref)
        targetPlc = App.Placement(App.Vector(L, W / 2, H / 2), App.Rotation(0, -90, 180))
        _msg("  plc '{}'".format(plc))
        _msg("  targetPlc '{}'".format(targetPlc))
        self.assertTrue(plc.isSame(targetPlc, 1e-6), "'{}' failed - Step 4".format(operation))

    def test_solve_assembly(self):
        """Test solving an assembly."""
        operation = "Solve assembly"
        _msg("  Test '{}'".format(operation))

        box = self.assembly.newObject("Part::Box", "Box")
        box.Length = 10
        box.Width = 10
        box.Height = 10
        box.Placement = App.Placement(App.Vector(10, 20, 30), App.Rotation(15, 25, 35))

        box2 = self.assembly.newObject("Part::Box", "Box")
        box2.Length = 10
        box2.Width = 10
        box2.Height = 10
        box2.Placement = App.Placement(App.Vector(40, 50, 60), App.Rotation(45, 55, 65))

        ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground, box2)

        joint = self.jointgroup.newObject("App::FeaturePython", "testJoint")
        JointObject.Joint(joint, 0)

        refs = [
            [box2, ["Face6", "Vertex7"]],
            [box, ["Face6", "Vertex7"]],
        ]

        joint.Proxy.setJointConnectors(joint, refs)

        self.assertTrue(box.Placement.isSame(box2.Placement, 1e-6), "'{}'".format(operation))

    def test_rack_pinion_with_slider_offset(self):
        """Rack and pinion joint whose rack slider has a yaw offset, see
        github.com/freecad/freecad/issues/17563"""
        operation = "Rack and pinion with slider offset"
        _msg("  Test '{}'".format(operation))

        ground = self.assembly.newObject("Part::Box", "Ground")
        ground.Length = 200
        ground.Width = 200
        ground.Height = 10

        rack = self.assembly.newObject("Part::Box", "Rack")
        rack.Length = 10
        rack.Width = 100
        rack.Height = 10
        rack.Placement.Base = App.Vector(50, 0, 10)

        pinion = self.assembly.newObject("Part::Cylinder", "Pinion")
        pinion.Radius = 10
        pinion.Height = 10
        pinion.Placement.Base = App.Vector(30, 50, 10)
        self.doc.recompute()

        # Attach to real faces, but specify the JCS explicitly so the test does
        # not depend on OpenCASCADE's orientation of those faces.
        along_rack = App.Rotation(App.Vector(1, 0, 0), -90)
        yaw_offset = App.Rotation(App.Vector(0, 0, 1), -90)

        slider = self.jointgroup.newObject("App::FeaturePython", "Slider")
        JointObject.Joint(slider, JointObject.JointTypes.index("Slider"))
        slider.Detach1 = True
        slider.Detach2 = True
        slider.Reference1 = (ground, ["Face1"])
        slider.Reference2 = (rack, ["Face1"])
        slider.Placement1 = App.Placement(App.Vector(), along_rack)
        slider.Placement2 = App.Placement(App.Vector(), along_rack * yaw_offset)

        rackPinion = self.jointgroup.newObject("App::FeaturePython", "RackPinion")
        JointObject.Joint(rackPinion, JointObject.JointTypes.index("RackPinion"))
        rackPinion.Detach1 = True
        rackPinion.Reference1 = (rack, ["Face1"])
        rackPinion.Reference2 = (pinion, ["Face1"])
        rackPinion.Placement1 = App.Placement(App.Vector(), along_rack)
        rackPinion.Distance = 10

        self.doc.recompute()

        slider_axis = UtilsAssembly.getJcsGlobalPlc(
            slider.Placement2, slider.Reference2
        ).Rotation.multVec(App.Vector(0, 0, 1))
        rack_axis = UtilsAssembly.getJcsGlobalPlc(
            rackPinion.Placement1, rackPinion.Reference1
        ).Rotation.multVec(App.Vector(0, 0, 1))
        self.assertLess(slider_axis.cross(rack_axis).Length, 1e-7)

        # The rack and pinion joint must reach the solver: it is silently dropped when
        # the rack cannot be identified from its slider. Look for its pitchRadius field
        # rather than its type name, which the solver derives from the compiler-specific
        # typeid name and is only readable with MSVC.
        with tempfile.TemporaryDirectory() as temp_dir:
            fileName = os.path.join(temp_dir, "rackPinion.asmt")
            self.assembly.exportAsASMT(fileName)
            with open(fileName) as asmt:
                content = asmt.read()
        self.assertIn(
            "pitchRadius",
            content,
            "'{}' failed - joint not exported; slider state: {}, rack-pinion state: {}; "
            "exported assembly: {}".format(
                operation, slider.State, rackPinion.State, content[-2500:]
            ),
        )
