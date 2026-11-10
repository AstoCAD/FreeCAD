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
import PartDesign
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide import QtCore

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
    def _check_export_asmt_path(self, filename="ordinary.asmt", native_path=False):
        import CommandExportASMT

        self.assembly.newObject("Part::Box", "Component")
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / filename
            picker_path = str(path) if native_path else path.as_posix()
            recorded = []
            with (
                patch.object(
                    CommandExportASMT.UtilsAssembly, "activeAssembly", return_value=self.assembly
                ),
                patch.object(
                    CommandExportASMT.QFileDialog, "getSaveFileName", return_value=(picker_path, "")
                ),
                patch.object(CommandExportASMT.Gui, "doCommand", side_effect=recorded.append),
            ):
                CommandExportASMT.CommandExportASMT().Activated()
            self.assertEqual(len(recorded), 2)
            namespace = {"App": App, "UtilsAssembly": CommandExportASMT.UtilsAssembly}
            with patch.object(
                CommandExportASMT.UtilsAssembly, "activeAssembly", return_value=self.assembly
            ):
                try:
                    command = compile("\n".join(recorded), "<Export ASMT command>", "exec")
                except SyntaxError as error:
                    self.fail(f"Export command cannot represent the selected file path: {error}")
                exec(command, namespace)
            self.assertTrue(path.is_file(), f"Selected output file was not created: {picker_path!r}")
            self.assertTrue(path.read_text(encoding="utf-8").startswith("OndselSolver\nAssembly\n"))

    @unittest.skipIf(not App.GuiUp, "Export command tests require FreeCAD GUI mode")
    def test_export_asmt_forward_slash_path(self):
        self._check_export_asmt_path()

    @unittest.skipIf(not App.GuiUp, "Export command tests require FreeCAD GUI mode")
    def test_export_asmt_apostrophe_filename(self):
        self._check_export_asmt_path("component's export.asmt")

    @unittest.skipIf(not App.GuiUp, "Export command tests require FreeCAD GUI mode")
    @unittest.skipUnless(os.sep == "\\", "Requires Windows native path separators")
    def test_export_asmt_windows_native_backslash_path(self):
        self._check_export_asmt_path(native_path=True)

    @unittest.skipIf(not App.GuiUp, "Export command tests require FreeCAD GUI mode")
    @unittest.skipIf(os.name == "nt", "Double quotes are not valid Windows file-name characters")
    def test_export_asmt_posix_quoted_filename(self):
        self._check_export_asmt_path('component "quoted".asmt')

    @unittest.skipIf(not App.GuiUp, "Export command tests require FreeCAD GUI mode")
    def test_export_asmt_cancel_does_not_record_or_export(self):
        import CommandExportASMT

        with (
            patch.object(
                CommandExportASMT.UtilsAssembly, "activeAssembly", return_value=self.assembly
            ),
            patch.object(CommandExportASMT.QFileDialog, "getSaveFileName", return_value=("", "")),
            patch.object(CommandExportASMT.Gui, "doCommand") as execute,
        ):
            CommandExportASMT.CommandExportASMT().Activated()
        execute.assert_not_called()

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

    def test_simulation_accepts_study_without_group(self):
        # A study without a Group has no motions or contacts; it still runs.
        study = self.doc.addObject("App::FeaturePython", "Study")
        self.assertFalse(hasattr(study, "Group"))
        self.assertEqual(self.assembly.generateSimulation(study), 0)

    def _check_bare_root_datum_grounded(self, type_id):
        datum = self.assembly.newObject(type_id, "RootDatum")
        self.assertIn(datum, self.assembly.Group)
        self.assertFalse(datum.hasExtension("Part::AttachExtension"))
        self.assertTrue(self.assembly.isPartGrounded(datum))
        self.assertTrue(self.assembly.isPartConnected(datum))

    def test_bare_root_coordinate_system_is_grounded(self):
        self._check_bare_root_datum_grounded("App::LocalCoordinateSystem")

    def test_bare_root_point_is_grounded(self):
        self._check_bare_root_datum_grounded("App::Point")

    def test_bare_root_line_is_grounded(self):
        self._check_bare_root_datum_grounded("App::Line")

    def test_bare_root_plane_is_grounded(self):
        self._check_bare_root_datum_grounded("App::Plane")

    def test_part_coordinate_system_grounding_respects_attachment(self):
        support = self.assembly.newObject("Part::Box", "AttachmentSupport")
        self.doc.recompute()
        datum = self.assembly.newObject("Part::LocalCoordinateSystem", "RootLCS")
        self.assertTrue(datum.hasExtension("Part::AttachExtension"))
        self.assertEqual(datum.MapMode, "Deactivated")
        placement_status = datum.getPropertyStatus("Placement")
        self.assertTrue(self.assembly.isPartGrounded(datum))
        self.assertTrue(self.assembly.isPartConnected(datum))
        self.assertEqual(datum.getPropertyStatus("Placement"), placement_status)

        datum.AttachmentSupport = [(support, ["Face1"])]
        datum.MapMode = "FlatFace"
        datum.recompute()
        self.assertEqual(datum.MapMode, "FlatFace")
        placement_status = datum.getPropertyStatus("Placement")
        self.assertFalse(self.assembly.isPartGrounded(datum))
        self.assertFalse(self.assembly.isPartConnected(datum))
        self.assertEqual(datum.getPropertyStatus("Placement"), placement_status)

    def _make_grounding_body(self, name, linked=False):
        body = self.doc.addObject("PartDesign::Body", name + "Body")
        tip = body.newObject("PartDesign::Feature", name + "Tip")
        tip.Shape = Part.makeBox(3, 4, 5)
        body.Tip = tip
        self.doc.recompute()
        self.assertFalse(body.Shape.isNull())
        if linked:
            component = self.assembly.newObject("App::Link", name + "Link")
            component.setLink(body)
        else:
            self.assembly.addObject(body)
            component = body
        return component

    def _check_ordinary_component_grounding(self, linked=False):
        component = self._make_grounding_body("Grounded", linked)
        other = self._make_grounding_body("Free", linked)
        self.assertFalse(self.assembly.isPartGrounded(component))
        self.assertFalse(self.assembly.isPartGrounded(other))
        ground = self.jointgroup.newObject("App::FeaturePython", "Ground")
        JointObject.GroundedJoint(ground, component)
        self.assertTrue(self.assembly.isPartGrounded(component))
        self.assertTrue(self.assembly.isPartConnected(component))
        self.assertFalse(self.assembly.isPartGrounded(other))

    def test_body_grounding_control(self):
        self._check_ordinary_component_grounding()

    def test_linked_body_grounding_control(self):
        self._check_ordinary_component_grounding(linked=True)

    def test_undo_of_deleting_grounded_primitive_keeps_it_grounded(self):
        """Undo restores the attachment properties of a deleted Part primitive. That must
        not unlock its placement, or the next solve deletes the grounded joint."""
        self.doc.UndoMode = 1
        grounded = self.assembly.newObject("Part::Box", "GroundedBox")
        self.doc.recompute()
        ground = self.jointgroup.newObject("App::FeaturePython", "Ground")
        JointObject.GroundedJoint(ground, grounded)
        ground_name = ground.Name

        self.doc.openTransaction("Delete grounded part")
        self.doc.removeObject(grounded.Name)
        self.doc.commitTransaction()
        self.doc.undo()

        grounded = self.doc.getObject("GroundedBox")
        self.assertIn("ReadOnly", grounded.getPropertyStatus("Placement"))
        self.assertEqual(self.assembly.solve(), 0)
        self.assertIsNotNone(self.doc.getObject(ground_name))
        self.assertTrue(self.assembly.isPartGrounded(grounded))

    def test_body_contained_bare_coordinate_system_is_not_root_grounded(self):
        body = self._make_grounding_body("Component")
        datum = body.newObject("App::LocalCoordinateSystem", "BodyLCS")
        self.assertEqual(datum.getParentGeoFeatureGroup(), body)
        self.assertNotIn(datum, self.assembly.Group)
        self.assertFalse(datum.hasExtension("Part::AttachExtension"))
        self.assertFalse(self.assembly.isPartGrounded(body))
        self.assertFalse(self.assembly.isPartGrounded(datum))

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

    def _grounded_box_fixed_to_other(self):
        grounded = self.assembly.newObject("Part::Box", "Grounded")
        grounded.Placement = App.Placement(App.Vector(5, -3, 2), App.Rotation(30, 10, 0))
        other = self.assembly.newObject("Part::Box", "Other")
        other.Placement = grounded.Placement.multiply(
            App.Placement(App.Vector(0, 0, 10), App.Rotation())
        )
        self.doc.recompute()
        ground = self.jointgroup.newObject("App::FeaturePython", "Ground")
        JointObject.GroundedJoint(ground, grounded)
        fixed = self.jointgroup.newObject("App::FeaturePython", "Fixed")
        JointObject.Joint(fixed, JointObject.JointTypes.index("Fixed"))
        fixed.Proxy.setJointConnectors(
            fixed, [[grounded, ["Face6", "Vertex7"]], [other, ["Face5", "Vertex1"]]]
        )
        self.assertEqual(self.assembly.solve(), 0)
        return grounded, other

    def test_conflicting_joints_do_not_move_grounded_part(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32650 (redundant constraint cause):
        # removing the redundant equations must never drop the grounding.
        grounded, other = self._grounded_box_fixed_to_other()
        initial = App.Placement(grounded.Placement)

        # The fixed joint makes this distance impossible.
        distance = self.jointgroup.newObject("App::FeaturePython", "Distance")
        JointObject.Joint(distance, JointObject.JointTypes.index("Distance"))
        distance.Distance = 1000
        distance.Proxy.setJointConnectors(
            distance, [[grounded, ["Vertex1", "Vertex1"]], [other, ["Vertex1", "Vertex1"]]]
        )
        self.assembly.solve()

        self.assertTrue(
            grounded.Placement.isSame(initial, 1e-7),
            f"grounded part moved to {grounded.Placement}",
        )

    def test_conflicting_revolutes_do_not_move_grounded_parts(self):
        # A part tied to two grounded parts by revolutes that cannot both be met. The
        # solver iterations diverge before the redundant equations are looked for, and
        # the grounding equations were among those removed at that point.
        first = self.assembly.newObject("Part::Box", "FirstGrounded")
        first.Placement = App.Placement(App.Vector(5, -3, 2), App.Rotation(30, 10, 0))
        second = self.assembly.newObject("Part::Box", "SecondGrounded")
        second.Placement = App.Placement(App.Vector(100, 0, 0), App.Rotation(0, 0, 180))
        moving = self.assembly.newObject("Part::Box", "Moving")
        moving.Placement = App.Placement(App.Vector(30, 30, 30), App.Rotation(5, 6, 7))
        self.doc.recompute()
        for name, part in (("FirstGround", first), ("SecondGround", second)):
            ground = self.jointgroup.newObject("App::FeaturePython", name)
            JointObject.GroundedJoint(ground, part)
        initial = [App.Placement(first.Placement), App.Placement(second.Placement)]

        for name, part, moving_reference in (
            ("FirstRevolute", first, ["Face5", "Vertex1"]),
            ("SecondRevolute", second, ["Face6", "Vertex7"]),
        ):
            revolute = self.jointgroup.newObject("App::FeaturePython", name)
            JointObject.Joint(revolute, JointObject.JointTypes.index("Revolute"))
            revolute.Proxy.setJointConnectors(
                revolute, [[part, ["Face6", "Vertex7"]], [moving, moving_reference]]
            )
        self.assembly.solve()

        for part, placement in zip((first, second), initial):
            self.assertTrue(
                part.Placement.isSame(placement, 1e-7),
                f"{part.Name} moved to {part.Placement}",
            )

    def test_export_asmt_writes_grounding(self):
        # The ASMT format has no fixed-body flag: the grounding is written as a fixed joint.
        grounded, _other = self._grounded_box_fixed_to_other()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "grounded.asmt"
            self.assembly.exportAsASMT(str(path))
            text = path.read_text(encoding="utf-8")
        self.assertIn(f"marker-{self.doc.Name}#{grounded.Name}", text)
        self.assertIn("FixingMarker", text)

    def _fixed_joint_between_boxes(self):
        grounded = self.assembly.newObject("Part::Box", "Grounded")
        moving = self.assembly.newObject("Part::Box", "Moving")
        moving.Placement = App.Placement(App.Vector(40, 50, 60), App.Rotation(10, 20, 30))
        self.doc.recompute()
        ground = self.jointgroup.newObject("App::FeaturePython", "Ground")
        JointObject.GroundedJoint(ground, grounded)
        joint = self.jointgroup.newObject("App::FeaturePython", "Fixed")
        JointObject.Joint(joint, JointObject.JointTypes.index("Fixed"))
        refs = [[grounded, ["Face6", "Vertex7"]], [moving, ["Face6", "Vertex7"]]]
        return moving, joint, refs

    def test_joint_task_shows_offsets_reset_by_new_references(self):
        """Without Preserve position, picking the references resets the offsets; the task
        panel must then show the reset values, not the ones typed before."""
        _moving, joint, refs = self._fixed_joint_between_boxes()
        task = JointObject.TaskAssemblyCreateJoint.__new__(JointObject.TaskAssemblyCreateJoint)
        QtCore.QObject.__init__(task)
        task.joint = joint
        task.refs = [refs[0]]
        task.activeType = "Part"  # no isolation of the view
        task.blockOffsetRotation = False
        task.jForm = MagicMock()
        task.jForm.preservePosCheckbox.isChecked.return_value = False
        task.updateJoint()
        joint.Offset2 = App.Placement(App.Vector(0, 0, 10), App.Rotation(15, 0, 0))

        task.refs = refs
        task.updateJoint()

        self.assertTrue(joint.Offset2.isIdentity(), str(joint.Offset2))
        task.jForm.offsetSpinbox.setProperty.assert_called_with("rawValue", 0.0)
        task.jForm.rotationSpinbox.setProperty.assert_called_with("rawValue", 0.0)

    def test_without_preserve_position_new_references_reset_the_offsets(self):
        """Without Preserve position the picked elements are joined as they are, dropping the
        offsets computed by a previous pick with Preserve position."""
        moving, joint, refs = self._fixed_joint_between_boxes()
        before = App.Placement(moving.Placement)
        joint.Proxy.setJointConnectors(joint, refs, True)
        self.assertFalse(joint.Offset2.isIdentity())

        joint.Proxy.setJointConnectors(joint, refs[:1])
        joint.Proxy.setJointConnectors(joint, refs)

        self.assertTrue(joint.Offset1.isIdentity(), str(joint.Offset1))
        self.assertTrue(joint.Offset2.isIdentity(), str(joint.Offset2))
        self.assertFalse(moving.Placement.isSame(before, 1e-6))
        jcs1 = UtilsAssembly.getJcsGlobalPlc(joint.Placement1, joint.Reference1)
        jcs2 = UtilsAssembly.getJcsGlobalPlc(joint.Placement2, joint.Reference2)
        self.assertTrue(jcs1.isSame(jcs2, 1e-6), f"{jcs1} != {jcs2}")

    def test_clearing_second_reference_after_offsets_reset_restores_part(self):
        """Resetting the offsets of a previous pick must not move the part before the joint
        records where to put it back."""
        moving, joint, refs = self._fixed_joint_between_boxes()
        before = App.Placement(moving.Placement)
        joint.Proxy.setJointConnectors(joint, refs, True)
        joint.Proxy.setJointConnectors(joint, refs[:1])
        joint.Proxy.setJointConnectors(joint, refs)
        self.assertTrue(joint.Offset2.isIdentity(), str(joint.Offset2))
        self.assertFalse(moving.Placement.isSame(before, 1e-6))

        joint.Proxy.setJointConnectors(joint, refs[:1])

        self.assertTrue(moving.Placement.isSame(before, 1e-6), str(moving.Placement))

    def test_preserve_position_when_reference_is_picked_again(self):
        """Preserve position keeps the part where it is, also when the joint still has the
        offsets computed for a previous pick."""
        moving, joint, refs = self._fixed_joint_between_boxes()
        before = App.Placement(moving.Placement)
        joint.Proxy.setJointConnectors(joint, refs, True)
        offset = App.Placement(joint.Offset2)
        self.assertFalse(offset.isIdentity())
        self.assertTrue(moving.Placement.isSame(before, 1e-6), str(moving.Placement))

        joint.Proxy.setJointConnectors(joint, refs[:1], True)
        joint.Proxy.setJointConnectors(joint, refs, True)

        self.assertTrue(joint.Offset2.isSame(offset, 1e-6), str(joint.Offset2))
        self.assertTrue(moving.Placement.isSame(before, 1e-6), str(moving.Placement))

    def test_preserve_position_replaces_an_existing_first_offset(self):
        moving, joint, refs = self._fixed_joint_between_boxes()
        before = App.Placement(moving.Placement)
        joint.Proxy.setJointConnectors(joint, refs[:1])
        joint.Offset1 = App.Placement(App.Vector(0, 0, 5), App.Rotation())

        joint.Proxy.setJointConnectors(joint, refs, True)

        self.assertTrue(joint.Offset1.isIdentity(), str(joint.Offset1))
        self.assertTrue(moving.Placement.isSame(before, 1e-6), str(moving.Placement))

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

    def test_bom_keeps_custom_data_of_mirrored_row(self):
        """Custom column text typed on a mirrored row must survive a BOM refresh."""
        source = self.doc.addObject("Part::Box", "ComponentSource")
        source.Label = "Component"
        regular = self.assembly.newObject("App::Link", "Regular")
        regular.LinkedObject = source
        mirrored = self.assembly.newObject("App::Link", "Mirrored")
        mirrored.LinkedObject = source
        mirrored.Scale = -1
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Quantity", "Notes"]
        self.doc.recompute()

        suffix = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly").GetString(
            "BomMirroredSuffix", " (mirrored)"
        )
        rows = {bom.get("A2"): "2", bom.get("A3"): "3"}
        self.assertEqual(set(rows), {source.Label, source.Label + suffix})
        bom.set("C" + rows[source.Label], "regular note")
        bom.set("C" + rows[source.Label + suffix], "mirrored note")
        bom.touch()
        self.doc.recompute()

        notes = {bom.get("A2"): bom.get("C2"), bom.get("A3"): bom.get("C3")}
        self.assertEqual(
            notes,
            {source.Label: "regular note", source.Label + suffix: "mirrored note"},
        )
        self.assertNotIn("Invalid", bom.State)

    def test_bom_lists_only_components_of_parts(self):
        """Objects used by the expressions of an assembly or a part are not its components."""
        outside = self.doc.addObject("Part::Box", "Outside")
        part = self.assembly.newObject("App::Part", "Part")
        part.newObject("Part::Box", "PartBox")
        part.setExpression(".Placement.Base.x", "Outside.Length")
        self.assembly.setExpression(".Placement.Base.y", "Outside.Width")
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Index", "Name", "Quantity"]
        self.doc.recompute()

        rows = []
        for row in range(2, 10):
            if bom.getContents(f"A{row}"):
                rows.append((bom.get(f"A{row}"), bom.get(f"B{row}")))
        self.assertEqual(rows, [("1", part.Label), ("1.1", "PartBox")])
        self.assertNotIn("Invalid", bom.State)

    def test_bom_keeps_component_labels_as_text(self):
        """Labels that look like numbers, quantities or formulas must be listed verbatim,
        and the custom column text of their rows must survive a BOM refresh."""
        labels = ["007", "1/2", "10 mm", "=1+1", "'quoted"]
        for i, label in enumerate(labels):
            box = self.assembly.newObject("Part::Box", f"Component{i}")
            box.Label = label
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Notes"]
        self.doc.recompute()

        names = [bom.getContents(f"A{row}") for row in range(2, 2 + len(labels))]
        self.assertEqual(names, ["'" + label for label in labels])
        for row in range(2, 2 + len(labels)):
            bom.set(f"B{row}", f"note {row}")
        bom.touch()
        self.doc.recompute()

        names = [bom.getContents(f"A{row}") for row in range(2, 2 + len(labels))]
        self.assertEqual(names, ["'" + label for label in labels])
        notes = [bom.get(f"B{row}") for row in range(2, 2 + len(labels))]
        self.assertEqual(notes, [f"note {row}" for row in range(2, 2 + len(labels))])
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

    def test_bom_counts_link_array_elements(self):
        """Every element of a link array is one occurrence of the linked object."""
        source = self.doc.addObject("Part::Box", "ArraySource")
        source.Label = "Rod"
        group = self.assembly.newObject("App::Link", "LinkGroup")
        group.LinkedObject = source
        group.ElementCount = 3
        generated = self.assembly.newObject("Part::LinkArrayLinear", "Generated")
        generated.LinkedObject = source
        generated.Occurrences = 4
        single = self.assembly.newObject("App::Link", "Single")
        single.LinkedObject = source
        self.doc.recompute()
        bom = self.assembly.newObject("Assembly::BomObject", "BillOfMaterials")
        bom.columnsNames = ["Name", "Quantity"]
        self.doc.recompute()
        self.assertNotIn("Invalid", bom.State)
        self.assertEqual(generated.ElementCount, 4)
        self.assertEqual(bom.get("A2"), source.Label)
        self.assertEqual(int(float(bom.get("B2"))), 8)
        self.assertNotIn("A3", bom.getNonEmptyCells())

        group.ElementList[1].Suppressed = True
        bom.touch()
        self.doc.recompute()
        self.assertEqual(int(float(bom.get("B2"))), 7)

    def test_snapshot_restores_remaining_components_after_deletion(self):
        """Deleting a captured component must not shift the other captured states."""
        import CommandCreateSnapshot

        boxes = []
        for i in range(3):
            box = self.assembly.newObject("Part::Box", "Box")
            box.Placement = App.Placement(App.Vector(10 * (i + 1), 0, 0), App.Rotation())
            boxes.append(box)
        self.doc.recompute()
        group = UtilsAssembly.getSnapshotGroup(self.assembly)
        snapshot = group.newObject("App::FeaturePython", "Snapshot")
        CommandCreateSnapshot.Snapshot(snapshot)
        snapshot.SolveOnActivation = False
        self.assertEqual(len(snapshot.Components), 3)
        captured = {box.Name: App.Placement(box.Placement) for box in boxes}

        for box in boxes:
            box.Placement = App.Placement(App.Vector(0, 0, 100), App.Rotation())
        boxes[2].Visibility = False
        self.doc.removeObject(boxes[0].Name)
        self.assertEqual(len(snapshot.Components), 2)
        self.assertEqual(len(snapshot.Placements), 2)
        self.assertEqual(len(snapshot.Visibilities), 2)

        snapshot.Proxy.restoreState(snapshot)
        for box in boxes[1:]:
            with self.subTest(box=box.Name):
                self.assertTrue(box.Placement.isSame(captured[box.Name], 1e-6))
        self.assertTrue(boxes[2].Visibility)

    def test_snapshot_restores_parts_of_flexible_sub_assembly(self):
        """The parts of a flexible sub-assembly move independently, so a snapshot must
        capture them one by one, not the assembly link as a whole."""
        import CommandCreateSnapshot

        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Part::Box", "SubBox1")
        sub.newObject("Part::Box", "SubBox2")
        instance = self.assembly.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = sub
        instance.Rigid = False
        self.doc.recompute()
        parts = [obj for obj in instance.Group if obj.isDerivedFrom("App::Link")]
        self.assertEqual(len(parts), 2)

        group = UtilsAssembly.getSnapshotGroup(self.assembly)
        snapshot = group.newObject("App::FeaturePython", "Snapshot")
        CommandCreateSnapshot.Snapshot(snapshot)
        snapshot.SolveOnActivation = False
        captured = [App.Placement(part.Placement) for part in parts]

        for part in parts:
            part.Placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        snapshot.Proxy.restoreState(snapshot)
        for part, placement in zip(parts, captured):
            with self.subTest(part=part.Name):
                self.assertTrue(part.Placement.isSame(placement, 1e-6), part.Placement)

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

    def test_flexible_assembly_link_places_new_component(self):
        """A placed part moved into a sub-assembly that is used as a flexible sub-assembly
        starts at its position in the sub-assembly, not at the origin. (The link is created
        when the part joins the Group; later moves of the source are not followed, the
        parent assembly owns the placements of a flexible sub-assembly.)"""
        first = self.assembly.newObject("Part::Box", "First")
        first.Placement = App.Placement(App.Vector(30, 0, 0), App.Rotation(20, 0, 0))
        parent = self.doc.addObject("Assembly::AssemblyObject", "ParentAssembly")
        instance = parent.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = self.assembly
        self.doc.recompute()
        instance.Rigid = False
        self.doc.recompute()

        added = self.doc.addObject("Part::Box", "Added")
        added.Placement = App.Placement(App.Vector(0, 60, 0), App.Rotation(0, 0, 45))
        self.assembly.addObject(added)
        self.doc.recompute()

        local = {obj.LinkedObject: obj for obj in instance.Group if obj.TypeId == "App::Link"}
        self.assertTrue(local[first].Placement.isSame(first.Placement, 1e-9))
        self.assertTrue(
            local[added].Placement.isSame(added.Placement, 1e-9), str(local[added].Placement)
        )

    def test_assembly_link_rejects_cyclic_link(self):
        """An assembly link to an object that depends on it (its own parent assembly, or a
        link back to itself) used to crash on recompute or hang forever."""
        instance = self.assembly.newObject("Assembly::AssemblyLink", "Instance")
        with self.assertRaises(ValueError):
            instance.LinkedObject = self.assembly
        self.assertIsNone(instance.LinkedObject)

        first = self.doc.addObject("Assembly::AssemblyLink", "First")
        second = self.doc.addObject("Assembly::AssemblyLink", "Second")
        first.LinkedObject = second
        with self.assertRaises(ValueError):
            second.LinkedObject = first
        self.assertIsNone(second.LinkedObject)

        # linking another assembly still works
        other = self.doc.addObject("Assembly::AssemblyObject", "Other")
        instance.LinkedObject = other
        self.doc.recompute()
        self.assertEqual(instance.LinkedObject, other)

    def test_delete_linked_sub_assembly(self):
        """Deleting a sub-assembly used by a rigid assembly link crashed (access violation):
        the link synchronized while the document was breaking the links to the deleted
        sub-assembly and removed its own components from the document."""
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Part::Box", "SubBox")
        self.doc.recompute()
        instance = self.assembly.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = sub
        self.doc.recompute()
        self.assertEqual(len(instance.Group), 1)

        self.doc.removeObject("Sub")
        self.assertIsNone(instance.LinkedObject)
        self.assertIsNotNone(self.doc.getObject("SubBox"))
        self.doc.recompute()
        self.assembly.solve()

    def test_assembly_link_maps_generated_array_joint(self):
        self._check_generated_array_joint("Face1")

    def test_assembly_link_maps_generated_array_whole_element_joint(self):
        self._check_generated_array_joint("")

    def test_assembly_link_rigid_toggle_undo_redo(self):
        """Undoing or redoing a Rigid toggle must not create the joint copies a second time
        (they were duplicated and orphan objects were left in the document)."""
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        joints = sub.newObject("Assembly::JointGroup", "SubJoints")
        box1 = sub.newObject("Part::Box", "SubBox1")
        box2 = sub.newObject("Part::Box", "SubBox2")
        box2.Placement.Base = App.Vector(0, 0, 10)
        joint = joints.newObject("App::FeaturePython", "SubJoint")
        JointObject.Joint(joint, 0)
        joint.Reference1 = (box1, ["Face6", "Vertex6"])
        joint.Reference2 = (box2, ["Face5", "Vertex5"])
        instance = self.assembly.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = sub
        self.doc.recompute()
        self.doc.UndoMode = 1

        def state():
            return instance.Rigid, sorted(obj.Name for obj in self.doc.Objects)

        rigid = state()
        for value in (False, True):
            self.doc.openTransaction("Toggle Rigid")
            instance.Rigid = value
            self.doc.commitTransaction()
            self.doc.recompute()
            if not value:
                flexible = state()
        self.assertEqual(state(), rigid)

        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(state(), flexible)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(state(), rigid)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(state(), flexible)

    def test_flexible_assembly_link_synchronizes_joint_angle(self):
        """A flexible assembly link copies the joints of its sub-assembly. The Angle of an
        Angle joint was not kept in sync, so the parent assembly solved with a stale angle."""
        box1 = self.assembly.newObject("Part::Box", "Box1")
        box2 = self.assembly.newObject("Part::Box", "Box2")
        box2.Placement.Base = App.Vector(0, 0, 20)
        joint = self.jointgroup.newObject("App::FeaturePython", "Joint")
        JointObject.Joint(joint, JointObject.JointTypes.index("Angle"))
        joint.Reference1 = (box1, ["Face6", "Vertex6"])
        joint.Reference2 = (box2, ["Face6", "Vertex6"])
        joint.Angle = 30
        parent = self.doc.addObject("Assembly::AssemblyObject", "ParentAssembly")
        instance = parent.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = self.assembly
        instance.Rigid = False
        self.doc.recompute()
        local_group = next(obj for obj in instance.Group if obj.TypeId == "Assembly::JointGroup")
        local_joint = local_group.Group[0]
        self.assertAlmostEqual(local_joint.Angle.Value, 30)

        joint.Angle = 60
        instance.touch()
        self.doc.recompute()
        self.assertAlmostEqual(local_joint.Angle.Value, 60)

    def _make_nested_sub_assembly(self, rigid_hinge):
        """A "Door" assembly with a panel joined to a part of its "Hinge" sub-assembly,
        used as a flexible sub-assembly of a parent assembly."""
        hinge = self.doc.addObject("Assembly::AssemblyObject", "Hinge")
        hinge_joints = hinge.newObject("Assembly::JointGroup", "HingeJoints")
        leaf1 = hinge.newObject("Part::Box", "Leaf1")
        leaf2 = hinge.newObject("Part::Box", "Leaf2")
        leaf2.Placement.Base = App.Vector(0, 0, 10)
        joint = hinge_joints.newObject("App::FeaturePython", "HingeJoint")
        JointObject.Joint(joint, 0)
        joint.Reference1 = (leaf1, ["Face6", "Vertex6"])
        joint.Reference2 = (leaf2, ["Face5", "Vertex5"])
        ground = hinge_joints.newObject("App::FeaturePython", "HingeGround")
        JointObject.GroundedJoint(ground, leaf1)
        self.doc.recompute()
        hinge.solve()

        panel = self.assembly.newObject("Part::Box", "Panel")
        panel.Placement.Base = App.Vector(0, 0, 20)
        hinge_link = self.assembly.newObject("Assembly::AssemblyLink", "HingeLink")
        hinge_link.LinkedObject = hinge
        hinge_link.Rigid = rigid_hinge
        self.doc.recompute()
        door_joint = self.jointgroup.newObject("App::FeaturePython", "DoorJoint")
        JointObject.Joint(door_joint, 0)
        if rigid_hinge:
            door_joint.Reference1 = (hinge_link, ["Leaf2.Face6", "Leaf2.Vertex6"])
        else:
            local_leaf2 = next(
                obj
                for obj in hinge_link.Group
                if obj.TypeId == "App::Link" and obj.LinkedObject == leaf2
            )
            door_joint.Reference1 = (local_leaf2, ["Face6", "Vertex6"])
        door_joint.Reference2 = (panel, ["Face5", "Vertex5"])
        self.doc.recompute()

        parent = self.doc.addObject("Assembly::AssemblyObject", "ParentAssembly")
        instance = parent.newObject("Assembly::AssemblyLink", "Instance")
        instance.LinkedObject = self.assembly
        instance.Rigid = False
        self.doc.recompute()

        local_hinge = next(o for o in instance.Group if o.TypeId == "Assembly::AssemblyLink")
        local_panel = next(o for o in instance.Group if o.TypeId == "App::Link")
        local_group = next(o for o in instance.Group if o.TypeId == "Assembly::JointGroup")
        self.assertEqual(local_hinge.LinkedObject, hinge_link)
        self.assertEqual(local_panel.LinkedObject, panel)
        self.assertEqual(len(local_group.Group), 1)
        return parent, local_hinge, local_panel, local_group.Group[0]

    def test_flexible_assembly_link_maps_joint_to_nested_flexible_sub_assembly(self):
        """Issue #31362: the joints of a flexible sub-assembly that reference a part of one of
        its own flexible sub-assemblies were not mapped onto the corresponding part of the
        nested assembly link ("Could not map external component"), so the copies kept
        referencing the parts of the sub-assembly itself, and the parent assembly did not
        solve the joints of the nested sub-assembly."""
        parent, local_hinge, local_panel, local_joint = self._make_nested_sub_assembly(False)
        self.assertFalse(local_hinge.Rigid)
        local_leaves = {
            obj.LinkedObject.Name: obj for obj in local_hinge.Group if obj.TypeId == "App::Link"
        }
        local_leaf1, local_leaf2 = local_leaves["Leaf1"], local_leaves["Leaf2"]
        self.assertEqual(local_joint.Reference1, (local_leaf2, ["Face6", "Vertex6"]))
        self.assertEqual(local_joint.Reference2, (local_panel, ["Face5", "Vertex5"]))

        leaf1, leaf2 = self.doc.getObject("Leaf1"), self.doc.getObject("Leaf2")
        relative = leaf1.Placement.inverse().multiply(leaf2.Placement)
        parent_joints = parent.newObject("Assembly::JointGroup", "ParentJoints")
        ground = parent_joints.newObject("App::FeaturePython", "ParentGround")
        JointObject.GroundedJoint(ground, local_panel)
        self.doc.recompute()
        local_leaf1.Placement = App.Placement(App.Vector(100, 37, -5), App.Rotation(30, 10, 0))
        local_leaf2.Placement = App.Placement(App.Vector(-40, 12, 60), App.Rotation(0, 20, 45))
        parent.solve()
        # The joint of the nested hinge holds its leaves together in the parent assembly.
        solved = local_leaf1.Placement.inverse().multiply(local_leaf2.Placement)
        self.assertTrue(solved.isSame(relative, 1e-6), f"{solved} != {relative}")

    def test_flexible_assembly_link_maps_joint_to_nested_rigid_sub_assembly(self):
        """A joint on a rigid sub-assembly of a flexible sub-assembly references the whole
        nested assembly link."""
        _, local_hinge, local_panel, local_joint = self._make_nested_sub_assembly(True)
        self.assertTrue(local_hinge.Rigid)
        self.assertEqual(local_joint.Reference1, (local_hinge, ["Leaf2.Face6", "Leaf2.Vertex6"]))
        self.assertEqual(local_joint.Reference2, (local_panel, ["Face5", "Vertex5"]))

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

    def test_presolve_keeps_joint_suppressed(self):
        """Changing an offset of a suppressed joint must not unsuppress it."""
        box = self.assembly.newObject("Part::Box", "Box")
        box2 = self.assembly.newObject("Part::Box", "Box")
        box2.Placement = App.Placement(App.Vector(40, 50, 60), App.Rotation())
        self.doc.recompute()
        ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground, box2)
        joint = self.jointgroup.newObject("App::FeaturePython", "testJoint")
        JointObject.Joint(joint, JointObject.JointTypes.index("Fixed"))
        joint.Proxy.setJointConnectors(
            joint, [[box2, ["Face6", "Vertex7"]], [box, ["Face6", "Vertex7"]]]
        )
        self.assertTrue(box.Placement.isSame(box2.Placement, 1e-6))
        self.assertFalse(joint.Suppressed)

        joint.Suppressed = True
        joint.Offset1 = App.Placement(App.Vector(0, 0, 5), App.Rotation())
        self.assertTrue(joint.Suppressed)

        joint.Proxy.flipOnePart(joint)
        self.assertTrue(joint.Suppressed)

    def test_clearing_second_reference_restores_presolved_part(self):
        """Removing the second reference while a joint is edited puts back the part the
        reference selection moved, also for Angle and Perpendicular joints, whose
        references are first tilted out of parallel."""
        for joint_type in ("Fixed", "Angle", "Perpendicular"):
            with self.subTest(joint_type=joint_type):
                grounded = self.assembly.newObject("Part::Box", "Grounded")
                moving = self.assembly.newObject("Part::Box", "Moving")
                moving.Placement = App.Placement(App.Vector(40, 50, 60), App.Rotation())
                self.doc.recompute()
                ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
                JointObject.GroundedJoint(ground, grounded)
                joint = self.jointgroup.newObject("App::FeaturePython", joint_type)
                JointObject.Joint(joint, JointObject.JointTypes.index(joint_type))
                if joint_type == "Angle":
                    joint.Angle = 30
                before = App.Placement(moving.Placement)
                first = [grounded, ["Face6", "Vertex7"]]

                joint.Proxy.setJointConnectors(joint, [first, [moving, ["Face6", "Vertex7"]]])
                self.assertFalse(moving.Placement.isSame(before, 1e-6))
                joint.Proxy.setJointConnectors(joint, [first])

                self.assertTrue(moving.Placement.isSame(before, 1e-6), str(moving.Placement))
                for obj in (joint, ground, moving, grounded):
                    self.doc.removeObject(obj.Name)

    def test_grounded_rigid_group_preserves_member_placements_on_solve(self):
        representative = self.assembly.newObject("Part::Box", "ARepresentative")
        grounded = self.assembly.newObject("Part::Box", "ZGrounded")
        representative.Placement.Base = App.Vector(10, 3, 2)
        grounded.Placement.Base = App.Vector(32, 7, 5)
        self.doc.recompute()

        ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground, grounded)
        group = self.jointgroup.newObject("App::FeaturePython", "RigidGroupJoint")
        # The solver chooses the representative by internal name, independent of member order.
        JointObject.RigidGroupJoint(group, [grounded, representative])
        self.doc.recompute()

        self.assertLess(representative.Name, grounded.Name)
        self.assertEqual(ground.ObjectToGround, grounded)
        self.assertNotIn("ReadOnly", representative.getPropertyStatus("Placement"))
        self.assertFalse(group.Suppressed)
        before = [(part, App.Placement(part.Placement)) for part in (representative, grounded)]

        self.assertEqual(self.assembly.solve(), 0)
        for part, placement in before:
            with self.subTest(part=part.Name):
                self.assertTrue(part.Placement.isSame(placement, 1e-6))

    def _rigid_group_kinematic_fixture(self):
        import Dynamics
        from CommandCreateSimulation import Motion

        ground = self.assembly.newObject("Part::Box", "Ground")
        driven = self.assembly.newObject("Part::Box", "Driven")
        member = self.assembly.newObject("Part::Box", "Member")
        other = self.assembly.newObject("Part::Box", "Other")
        member.Placement.Base = App.Vector(20, 0, 0)
        other.Placement.Base = App.Vector(40, 0, 0)
        grounding = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(grounding, ground)
        revolute = self.jointgroup.newObject("App::FeaturePython", "Revolute")
        JointObject.Joint(revolute, JointObject.JointTypes.index("Revolute"))
        revolute.Detach1 = revolute.Detach2 = True
        revolute.Reference1 = (ground, [""])
        revolute.Reference2 = (driven, [""])
        self.doc.recompute()

        study = Dynamics.create_study(self.assembly)
        study.EndTime = "1 s"
        study.OutputStep = "0.5 s"
        motion = self.doc.addObject("App::FeaturePython", "Motion")
        Motion(motion, "Angular", revolute, "initialValue + time")
        study.addObject(motion)
        return driven, member, other, study

    def _kinematic_end_positions(self, study):
        self.assertEqual(self.assembly.generateSimulation(study), 0)
        bodies = self.assembly.getSimulationResults()["Bodies"]
        return {name: App.Vector(*body["Placements"][-1][:3]) for name, body in bodies.items()}

    def test_kinematic_simulation_uses_rigid_groups_changed_since_last_solve(self):
        driven, member, other, study = self._rigid_group_kinematic_fixture()
        rotated = App.Rotation(App.Vector(0, 0, 1), 57.29577951308232)

        # Created after the last solve: the member must turn with the driven part.
        group = self.jointgroup.newObject("App::FeaturePython", "RigidGroup")
        JointObject.RigidGroupJoint(group, [driven, member])
        positions = self._kinematic_end_positions(study)
        self.assertIn(member.Name, positions)
        self.assertLess((positions[member.Name] - rotated.multVec(App.Vector(20, 0, 0))).Length, 1e-6)

        # Edited after a solve: the group now holds the other part, not the member.
        self.assertEqual(self.assembly.solve(), 0)
        group.ObjectsToRigidGroup = [driven, other]
        positions = self._kinematic_end_positions(study)
        self.assertNotIn(member.Name, positions)
        self.assertLess((positions[other.Name] - rotated.multVec(App.Vector(40, 0, 0))).Length, 1e-6)

    def test_kinematic_simulation_after_deleting_rigid_group_member(self):
        driven, member, other, study = self._rigid_group_kinematic_fixture()
        self.doc.UndoMode = 0  # really free the deleted member
        group = self.jointgroup.newObject("App::FeaturePython", "RigidGroup")
        JointObject.RigidGroupJoint(group, [driven, member])
        self.assertEqual(self.assembly.solve(), 0)

        # The last solve's rigid clusters still point to the deleted member.
        self.doc.removeObject(member.Name)
        positions = self._kinematic_end_positions(study)
        self.assertEqual(set(positions), {"Ground", driven.Name})

    def test_simulation_playback_after_deleting_a_simulated_part(self):
        driven, member, other, study = self._rigid_group_kinematic_fixture()
        self.doc.UndoMode = 0  # really free the deleted part
        fixed = self.jointgroup.newObject("App::FeaturePython", "Fixed")
        JointObject.Joint(fixed, JointObject.JointTypes.index("Fixed"))
        fixed.Detach1 = fixed.Detach2 = True
        fixed.Reference1 = (driven, [""])
        fixed.Reference2 = (member, [""])
        fixed.Placement1 = App.Placement(App.Vector(20, 0, 0), App.Rotation())
        self.assertEqual(self.assembly.generateSimulation(study), 0)
        last = self.assembly.numberOfFrames() - 1

        # The playback must not write to the deleted part; the others still move.
        self.doc.removeObject(fixed.Name)
        self.doc.removeObject(member.Name)
        self.assembly.updateForFrame(last)
        self.assertAlmostEqual(driven.Placement.Rotation.Angle, 1.0, places=6)

    def test_rigid_clusters_after_deleting_a_member(self):
        ground = self.assembly.newObject("Part::Box", "Ground")
        member = self.assembly.newObject("Part::Box", "Member")
        other = self.assembly.newObject("Part::Box", "Other")
        free = self.assembly.newObject("Part::Box", "Free")
        self.doc.UndoMode = 0  # really free the deleted part
        grounding = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(grounding, ground)
        group = self.jointgroup.newObject("App::FeaturePython", "RigidGroup")
        JointObject.RigidGroupJoint(group, [ground, member, other])
        self.doc.recompute()
        self.assertEqual(self.assembly.solve(), 0)
        self.assertTrue(self.assembly.isPartGrounded(other))

        # No solve rebuilds the clusters here: they must not name the deleted member,
        # and the remaining members stay one cluster.
        self.doc.removeObject(member.Name)
        self.assertTrue(self.assembly.isPartGrounded(other))
        self.assertFalse(self.assembly.isPartGrounded(free))

    def test_slider_limits_preserve_precision_in_asmt(self):
        ground = self.assembly.newObject("Part::Box", "Ground")
        moving = self.assembly.newObject("Part::Box", "Moving")
        moving.Placement.Base = App.Vector(0, 0, 5)
        self.doc.recompute()

        grounding = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(grounding, ground)
        slider = self.jointgroup.newObject("App::FeaturePython", "Slider")
        JointObject.Joint(slider, JointObject.JointTypes.index("Slider"))
        slider.Detach1 = slider.Detach2 = True
        slider.Reference1 = (ground, [""])
        slider.Reference2 = (moving, [""])
        self.doc.recompute()

        minimum, maximum = 2.3e-7, 9.8765432
        slider.LengthMin, slider.LengthMax = minimum, maximum
        slider.EnableLengthMin = slider.EnableLengthMax = True
        self.assertEqual((slider.LengthMin.Value, slider.LengthMax.Value), (minimum, maximum))

        exported = self._exported_asmt_limits("TranslationLimit")
        for suffix, value in (("Min", minimum), ("Max", maximum)):
            with self.subTest(limit=suffix):
                self.assertEqual(float(exported[slider.FullName + "-LimitLen" + suffix]), value)

        self.assertEqual(self.assembly.solve(), 0)

    def test_revolute_limits_preserve_precision_in_asmt(self):
        ground = self.assembly.newObject("Part::Box", "Ground")
        moving = self.assembly.newObject("Part::Box", "Moving")
        moving.Placement.Base = App.Vector(0, 0, 20)
        self.doc.recompute()

        grounding = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(grounding, ground)
        revolute = self.jointgroup.newObject("App::FeaturePython", "Revolute")
        JointObject.Joint(revolute, JointObject.JointTypes.index("Revolute"))
        revolute.Detach1 = revolute.Detach2 = True
        revolute.Reference1 = (ground, [""])
        revolute.Reference2 = (moving, [""])
        # Coincident joint frames place the initial angle inside the limits.
        revolute.Placement1.Base = App.Vector(0, 0, 20)

        minimum, maximum = -2.3e-7, 45.1234567
        revolute.AngleMin, revolute.AngleMax = minimum, maximum
        revolute.EnableAngleMin = revolute.EnableAngleMax = True
        self.doc.recompute()
        self.assertEqual((revolute.AngleMin.Value, revolute.AngleMax.Value), (minimum, maximum))

        exported = self._exported_asmt_limits("RotationLimit")
        radians = "*pi/180.0"
        for suffix, value in (("Min", minimum), ("Max", maximum)):
            with self.subTest(limit=suffix):
                expression = exported[revolute.FullName + "-LimitRot" + suffix]
                self.assertTrue(expression.endswith(radians), expression)
                self.assertEqual(float(expression.removesuffix(radians)), value)

        self.assertEqual(self.assembly.solve(), 0)

    def _exported_asmt_limits(self, record_type):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "JointLimits.asmt"
            self.assembly.exportAsASMT(str(path))
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]

        starts = [index for index, line in enumerate(lines) if line == record_type]
        self.assertEqual(len(starts), 2)
        exported = {}
        for start, end in zip(starts, starts[1:] + [len(lines)]):
            record = lines[start + 1 : end]
            name = record[record.index("Name") + 1]
            exported[name] = record[record.index("Limit") + 1]
        return exported

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

    def _point(self, sub):
        shape = Part.getShape(self.assembly, sub, App.Matrix(), True)
        self.assertGreater(len(shape.Vertexes), 0, sub)
        return shape.Vertexes[0].Point

    def _component(self, full):
        comp, rel = UtilsAssembly.getComponentReference(self.assembly, self.assembly, full)
        self.assertIsNotNone(comp, full)
        return comp, rel

    def _assert_marker(self, full, vertex_rel=None):
        comp, rel = self._component(full)
        if vertex_rel is None:
            vertex_rel = rel
        ref = (comp, [rel, vertex_rel])
        marker = UtilsAssembly.getJcsGlobalPlc(UtilsAssembly.findPlacement(ref), ref)
        gap = (marker.Base - self._point(full)).Length
        self.assertLess(gap, 1e-6, "marker gap {:.4f} mm".format(gap))
        return comp, rel, ref

    def _fixed_to_target(self, target, comp, rel, vertex_rel=None):
        ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground, target)
        joint = self.jointgroup.newObject("App::FeaturePython", "FixedJoint")
        JointObject.Joint(joint, 0)
        target_comp, target_rel = self._component(target.Name + ".Vertex1")
        if vertex_rel is None:
            vertex_rel = rel
        joint.Proxy.setJointConnectors(
            joint,
            [(target_comp, [target_rel, target_rel]), (comp, [rel, vertex_rel])],
        )
        self.doc.recompute()
        self.assertEqual(self.assembly.solve(), 0)

    def _box(self, parent, name, length, width, height, placement):
        maker = parent.newObject if hasattr(parent, "newObject") else parent.addObject
        box = maker("Part::Box", name)
        box.Length = length
        box.Width = width
        box.Height = height
        box.Placement = placement
        return box

    def _linear_array(self, linked, occurrences, offset, spacing=False):
        array = self.assembly.newObject("Part::LinkArrayLinear", "Array")
        array.LinkedObject = linked
        array.Occurrences = occurrences
        array.Offset = offset
        array.ShowElement = True
        if spacing:
            array.Mode = "Spacing"
        return array

    def _move(self, obj, placement):
        if hasattr(self.doc, "commitCompatibilityMutation"):

            def mutate():
                obj.Placement = placement
                return True

            committed = self.doc.commitCompatibilityMutation(
                mutate, structural=True, recompute=True
            )
            self.assertTrue(committed["committed"], committed)
        else:
            obj.Placement = placement
        self.doc.recompute()
        self.assertEqual(self.assembly.solve(), 0)

    def _assert_stored(self, true, target, ref, limit, solved_limit=None):
        stored = UtilsAssembly.getJcsGlobalPlc(self.doc.getObject("FixedJoint").Placement2, ref)
        gap = (stored.Base - true).Length
        self.assertLess(gap, limit, "stored gap {:.4f} mm".format(gap))
        solved_limit = limit if solved_limit is None else solved_limit
        solved = (true - self._point(target.Name + ".Vertex1")).Length
        self.assertLess(solved, solved_limit, "solved gap {:.4f} mm".format(solved))

    def _circle(self, face_sub):
        edge = Part.getShape(self.assembly, face_sub, App.Matrix(), True).getElement("Edge1")
        self.assertEqual(edge.Curve.TypeId, "Part::GeomCircle", face_sub)
        return edge.Curve.Location

    def _axes(self, face_full):
        dot = face_full.rfind(".")
        shape = Part.getShape(self.assembly, face_full[: dot + 1], App.Matrix(), True)
        face = shape.getElement(face_full[dot + 1 :])
        edge = face.getElement("Edge2")
        self.assertEqual(edge.Curve.TypeId, "Part::GeomBSplineCurve", face_full)
        axes = [
            other.Surface
            for other in shape.Faces
            if other.Surface.TypeId == "Part::GeomCylinder"
            and any(
                item.Curve.TypeId == "Part::GeomBSplineCurve"
                and item.CenterOfGravity == edge.CenterOfGravity
                and item.Length == edge.Length
                for item in other.Edges
            )
        ]
        line1 = Part.Line(axes[0].Center, axes[0].Center + axes[0].Axis)
        line2 = Part.Line(axes[1].Center, axes[1].Center + axes[1].Axis)
        point = line1.intersect(line2, Part.Precision.confusion())[0]
        return App.Vector(point.X, point.Y, point.Z)

    def test_link_array_fixed_joint_uses_inner_source_placement_once(self):
        _msg("  Test 'Link array joint matches inner source placement'")
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Assembly::JointGroup", "SubJoints")
        source = self._box(
            sub,
            "Source",
            10,
            20,
            30,
            App.Placement(App.Vector(0, 40, 15), App.Rotation(App.Vector(0, 0, 1), 90)),
        )
        array = self._linear_array(sub, 2, 100)
        target = self._box(
            self.assembly,
            "Target",
            10,
            20,
            30,
            App.Placement(App.Vector(0, 200, 0), App.Rotation()),
        )
        plain = self.assembly.newObject("App::Link", "Plain")
        plain.LinkedObject = sub
        plain.Placement = App.Placement(App.Vector(0, -80, 0), App.Rotation())
        self.doc.recompute()

        element = array.ElementList[1]
        self.assertGreater(element.Placement.Base.x, 50)
        full = "{}.{}.Sub.Source.Vertex1".format(array.Name, element.Name)
        comp, rel, _ref = self._assert_marker(full)
        edge_comp, edge_rel = self._component(
            "{}.{}.Sub.Source.Edge1".format(array.Name, element.Name)
        )
        edge_ref = (edge_comp, [edge_rel, rel])
        edge_marker = UtilsAssembly.getJcsGlobalPlc(UtilsAssembly.findPlacement(edge_ref), edge_ref)
        edge_gap = (edge_marker.Base - self._point(full)).Length
        self.assertLess(edge_gap, 1e-6, "marker gap {:.4f} mm".format(edge_gap))
        plain_full = "Plain.Sub.Source.Vertex1"
        _plain_comp, _plain_rel, plain_ref = self._assert_marker(plain_full)
        self.assertEqual(UtilsAssembly.getObject(plain_ref).Name, source.Name)

        self._fixed_to_target(target, comp, rel)
        solved = (self._point(full) - self._point(target.Name + ".Vertex1")).Length
        self.assertLess(solved, 1e-5, "solved gap {:.4f} mm".format(solved))

    def test_link_array_fixed_joint_ignores_source_object_placement(self):
        _msg("  Test 'Link array joint ignores source object placement'")
        source = self._box(
            self.doc, "Source", 10, 20, 30, App.Placement(App.Vector(0, 80, 15), App.Rotation())
        )
        array = self._linear_array(source, 2, 100)
        target = self._box(
            self.assembly,
            "Target",
            10,
            20,
            30,
            App.Placement(App.Vector(0, 200, 0), App.Rotation()),
        )
        plain = self.assembly.newObject("App::Link", "Plain")
        plain.LinkedObject = source
        self.doc.recompute()

        element = array.ElementList[1]
        full = "{}.{}.{}.Vertex1".format(array.Name, element.Name, source.Name)
        comp, rel, _ref = self._assert_marker(full)
        self._assert_marker(plain.Name + ".Vertex1")

        self._fixed_to_target(target, comp, rel)
        solved = (self._point(full) - self._point(target.Name + ".Vertex1")).Length
        self.assertLess(solved, 1e-5, "solved gap {:.4f} mm".format(solved))

    def test_link_array_joint_follows_moved_inner_body(self):
        _msg("  Test 'Link array joint follows a moved inner body'")
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Assembly::JointGroup", "SubJoints")
        inner = self._box(
            sub, "InnerBox", 10, 10, 10, App.Placement(App.Vector(0, 30, 0), App.Rotation())
        )
        array = self._linear_array(sub, 3, 120, spacing=True)
        target = self._box(self.assembly, "Target", 20, 20, 20, App.Placement())
        self.doc.recompute()

        full = "{}.{}.Sub.InnerBox.Vertex1".format(array.Name, array.ElementList[1].Name)
        comp, rel, ref = self._assert_marker(full)
        self._fixed_to_target(target, comp, rel)
        self._assert_stored(self._point(full), target, ref, 1e-6)

        self._move(inner, App.Placement(App.Vector(0, 70, 0), App.Rotation()))
        self._assert_stored(self._point(full), target, ref, 1e-6)

    def test_link_array_joint_follows_moved_inner_cylinder_bottom(self):
        _msg("  Test 'Link array joint follows a moved cylinder bottom circle'")
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Assembly::JointGroup", "SubJoints")
        inner = sub.newObject("Part::Cylinder", "InnerCyl")
        inner.Radius = 5
        inner.Height = 10
        inner.Placement = App.Placement(App.Vector(0, 30, 0), App.Rotation())
        array = self._linear_array(sub, 3, 120, spacing=True)
        target = self._box(self.assembly, "Target", 20, 20, 20, App.Placement())
        self.doc.recompute()

        bottom_index = None
        bottom_face = None
        for index, face in enumerate(inner.Shape.Faces, 1):
            if face.Surface.TypeId != "Part::GeomPlane":
                continue
            if bottom_face is None or face.CenterOfGravity.z < bottom_face.CenterOfGravity.z:
                bottom_face = face
                bottom_index = index
        self.assertEqual(len(bottom_face.Edges), 1)
        self.assertEqual(bottom_face.getElement("Edge1").Curve.TypeId, "Part::GeomCircle")
        self.assertNotEqual(inner.Shape.getElement("Edge1").Curve.TypeId, "Part::GeomCircle")

        element = array.ElementList[1]
        face_full = "{}.{}.Sub.InnerCyl.Face{}".format(array.Name, element.Name, bottom_index)
        comp, face_rel = self._component(face_full)
        _edge_comp, edge_rel = self._component(
            "{}.{}.Sub.InnerCyl.Edge1".format(array.Name, element.Name)
        )
        self.assertTrue(face_rel.endswith("Face{}".format(bottom_index)), face_rel)
        self.assertTrue(edge_rel.endswith("Edge1"), edge_rel)
        ref = (comp, [face_rel, edge_rel])
        marker = UtilsAssembly.getJcsGlobalPlc(UtilsAssembly.findPlacement(ref), ref)
        gap = (marker.Base - self._circle(face_full)).Length
        self.assertLess(gap, 1e-6, "marker gap {:.4f} mm".format(gap))

        self._fixed_to_target(target, comp, face_rel, edge_rel)
        self._assert_stored(self._circle(face_full), target, ref, 1e-6)
        self._move(inner, App.Placement(App.Vector(0, 70, 0), App.Rotation()))
        self._assert_stored(self._circle(face_full), target, ref, 1e-6)

    def test_link_array_joint_follows_moved_cylinder_intersection(self):
        _msg("  Test 'Link array joint follows a moved cylinder intersection'")
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Assembly::JointGroup", "SubJoints")
        inner = sub.newObject("Part::Feature", "Fusion")
        inner.Shape = Part.makeCylinder(5, 40).fuse(
            Part.makeCylinder(8, 40, App.Vector(-20, 0, 20), App.Vector(1, 0, 0))
        )
        inner.Placement = App.Placement(App.Vector(0, 30, 0), App.Rotation())
        array = self._linear_array(sub, 2, 100)
        target = self._box(self.assembly, "Target", 20, 20, 20, App.Placement())
        self.doc.recompute()

        full = "{}.{}.Sub.Fusion.Face1".format(array.Name, array.ElementList[1].Name)
        comp, rel = self._component(full)
        _edge_comp, edge_rel = self._component(full.replace("Face1", "Edge2"))
        ref = (comp, [rel, edge_rel])
        marker = UtilsAssembly.getJcsGlobalPlc(UtilsAssembly.findPlacement(ref), ref)
        gap = (marker.Base - self._axes(full)).Length
        self.assertLess(gap, 1e-6, "marker gap {:.4f} mm".format(gap))
        self._fixed_to_target(target, comp, rel, edge_rel)
        self._assert_stored(self._axes(full), target, ref, 1e-6)
        self._move(inner, App.Placement(App.Vector(0, 70, 0), App.Rotation()))
        self._assert_stored(self._axes(full), target, ref, 1e-6)

    def _check_pattern_array_joint(self, kind):
        _msg("  Test 'Link array joint on a {} pattern'".format(kind.lower()))
        sub = self.doc.addObject("Assembly::AssemblyObject", "Sub")
        sub.newObject("Assembly::JointGroup", "SubJoints")
        rotation = App.Rotation(App.Vector(0, 0, 1), 90)
        inner = self._box(
            sub, "InnerBox", 10, 10, 10, App.Placement(App.Vector(0, 30, 15), rotation)
        )
        array = self.assembly.newObject("Part::LinkArray" + kind, "Array")
        array.LinkedObject = sub
        array.ShowElement = True
        if kind == "Circular":
            array.Axis = (None, ["Z_Axis"])
            array.BinormalAxis = (None, ["Y_Axis"])
        elif kind in ("Path", "Point"):
            pattern = self.doc.addObject("Part::Feature", "Pattern")
            pattern.Shape = Part.makePolygon([App.Vector(), App.Vector(120, 0, 0)])
            if kind == "Path":
                array.Path = (pattern, ["Edge1"])
                array.Count = 2
            else:
                array.PointObject = pattern
        target = self._box(self.assembly, "Target", 20, 20, 20, App.Placement())
        self.doc.recompute()

        self.assertGreaterEqual(len(array.ElementList), 2)
        element = array.ElementList[1]
        self.assertFalse(element.Placement.isIdentity())
        full = "{}.{}.Sub.InnerBox.Vertex1".format(array.Name, element.Name)
        comp, rel, ref = self._assert_marker(full)
        self._fixed_to_target(target, comp, rel)
        solved = (self._point(full) - self._point(target.Name + ".Vertex1")).Length
        self.assertLess(solved, 1e-5, "solved gap {:.4f} mm".format(solved))
        self._move(inner, App.Placement(App.Vector(0, 70, 15), rotation))
        self._assert_stored(self._point(full), target, ref, 1e-6, 1e-5)

    def test_link_array_joint_on_polar_pattern(self):
        self._check_pattern_array_joint("Polar")

    def test_link_array_joint_on_circular_pattern(self):
        self._check_pattern_array_joint("Circular")

    def test_link_array_joint_on_path_pattern(self):
        self._check_pattern_array_joint("Path")

    def test_link_array_joint_on_point_pattern(self):
        self._check_pattern_array_joint("Point")

    def test_rack_pinion_marker_on_rotated_rack(self):
        """The rack marker of a rack and pinion joint must have its Z axis along the
        pinion axis and its X axis along the sliding axis, also when the rack part is
        rotated, see github.com/freecad/freecad/issues/30887"""
        operation = "Rack and pinion marker on rotated rack"
        _msg("  Test '{}'".format(operation))

        ground = self.assembly.newObject("Part::Box", "Ground")
        ground.Length = 200
        ground.Width = 200
        ground.Height = 10

        # The pinion axis (global Z) is not the Z axis of the rack part.
        rack_rot = App.Rotation(App.Vector(0, 1, 0), 90)
        rack = self.assembly.newObject("Part::Box", "Rack")
        rack.Length = 10
        rack.Width = 100
        rack.Height = 10
        rack.Placement = App.Placement(App.Vector(60, 0, 10), rack_rot)

        pinion = self.assembly.newObject("Part::Cylinder", "Pinion")
        pinion.Radius = 10
        pinion.Height = 10
        pinion.Placement.Base = App.Vector(30, 50, 10)
        self.doc.recompute()

        ground_joint = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground_joint, ground)

        along_rack = App.Rotation(App.Vector(1, 0, 0), -90)
        along_rack_local = rack_rot.inverted() * along_rack

        slider = self.jointgroup.newObject("App::FeaturePython", "Slider")
        JointObject.Joint(slider, JointObject.JointTypes.index("Slider"))
        slider.Detach1 = True
        slider.Detach2 = True
        slider.Reference1 = (ground, ["Face1"])
        slider.Reference2 = (rack, ["Face1"])
        slider.Placement1 = App.Placement(App.Vector(), along_rack)
        slider.Placement2 = App.Placement(App.Vector(), along_rack_local)

        rackPinion = self.jointgroup.newObject("App::FeaturePython", "RackPinion")
        JointObject.Joint(rackPinion, JointObject.JointTypes.index("RackPinion"))
        rackPinion.Detach1 = True
        rackPinion.Reference1 = (rack, ["Face1"])
        rackPinion.Reference2 = (pinion, ["Face1"])
        rackPinion.Placement1 = App.Placement(App.Vector(), along_rack_local)
        rackPinion.Distance = 10

        self.doc.recompute()

        slide_axis = UtilsAssembly.getJcsGlobalPlc(
            rackPinion.Placement1, rackPinion.Reference1
        ).Rotation.multVec(App.Vector(0, 0, 1))
        pinion_axis = UtilsAssembly.getJcsGlobalPlc(
            rackPinion.Placement2, rackPinion.Reference2
        ).Rotation.multVec(App.Vector(0, 0, 1))

        with tempfile.TemporaryDirectory() as temp_dir:
            fileName = os.path.join(temp_dir, "rackPinionRotated.asmt")
            self.assembly.exportAsASMT(fileName)
            with open(fileName) as asmt:
                lines = [line.strip() for line in asmt]

        # Parts and markers are both written as Name, Position3D and RotationMatrix.
        entries = []
        for i in range(len(lines) - 7):
            if lines[i] == "Name" and lines[i + 2] == "Position3D":
                if lines[i + 4] == "RotationMatrix":
                    rows = [[float(v) for v in lines[i + 5 + r].split()] for r in range(3)]
                    entries.append((lines[i + 1], rows))

        def toMatrix(rows):
            return App.Matrix(*rows[0], 0, *rows[1], 0, *rows[2], 0, 0, 0, 0, 1)

        names = [entry[0] for entry in entries]
        rackIndex = names.index(rack.FullName)
        markerIndex = names.index(rackPinion.FullName, rackIndex + 1)
        rackMatrix = toMatrix(entries[rackIndex][1])
        markerMatrix = toMatrix(entries[markerIndex][1])
        globalMarker = rackMatrix.multiply(markerMatrix)

        markerX = globalMarker.multVec(App.Vector(1, 0, 0))
        markerZ = globalMarker.multVec(App.Vector(0, 0, 1))
        self.assertLess(
            markerZ.cross(pinion_axis).Length,
            1e-7,
            "'{}' failed - rack marker Z {} is not the pinion axis {}".format(
                operation, markerZ, pinion_axis
            ),
        )
        self.assertLess(
            markerX.cross(slide_axis).Length,
            1e-7,
            "'{}' failed - rack marker X {} is not the sliding axis {}".format(
                operation, markerX, slide_axis
            ),
        )

    def test_undo_solve_after_part_deleted(self):
        """undoSolve() must skip parts deleted since the solve instead of using
        dangling pointers (access violation)."""
        operation = "Undo solve after a part was deleted"
        _msg("  Test '{}'".format(operation))

        grounded = self.assembly.newObject("Part::Box", "Grounded")
        deleted = self.assembly.newObject("Part::Box", "Deleted")
        kept = self.assembly.newObject("Part::Box", "Kept")
        self.doc.recompute()

        ground = self.jointgroup.newObject("App::FeaturePython", "GroundedJoint")
        JointObject.GroundedJoint(ground, grounded)
        for part in (deleted, kept):
            joint = self.jointgroup.newObject("App::FeaturePython", "Fixed" + part.Name)
            JointObject.Joint(joint, JointObject.JointTypes.index("Fixed"))
            joint.Proxy.setJointConnectors(
                joint,
                [[grounded, ["Face6", "Vertex7"]], [part, ["Face6", "Vertex7"]]],
            )
        self.doc.recompute()

        self.assertEqual(self.assembly.solve(True), 0)
        solved = App.Placement(kept.Placement)

        kept.Placement = App.Placement(App.Vector(100, 200, 300), App.Rotation())
        self.doc.removeObject("Fixed" + deleted.Name)
        self.doc.removeObject(deleted.Name)

        self.assembly.undoSolve()

        self.assertTrue(
            kept.Placement.isSame(solved, 1e-7),
            "'{}' failed - {} not restored to {}".format(operation, kept.Placement, solved),
        )
