# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rigid-group initialization completes before its member-change callback runs."""

import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import CommandCreateJoint  # noqa: F401
    import JointObject
    import UtilsAssembly
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRigidGroupInitializationGui(unittest.TestCase):
    command_name = "Assembly_CreateJointRigidGroup"

    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = self._selection()
        self.doc_name = None
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog(), "The fixture requires an idle task panel")
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("RigidGroupTransaction_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.joints = self.assembly.newObject("Assembly::JointGroup", "Joints")
        self.first = self.assembly.newObject("Part::Box", "First")
        self.first.Length, self.first.Width, self.first.Height = 3, 4, 5
        self.second = self.assembly.newObject("Part::Box", "Second")
        self.second.Length, self.second.Width, self.second.Height = 2, 3, 4
        self.second.Placement.Base = App.Vector(15, 0, 0)
        self.doc.recompute()
        self.owner_gui = Gui.getDocument(self.doc_name)
        self.owner_gui.setEdit(self.assembly)
        self.assertTrue(self._wait(lambda: UtilsAssembly.activeAssembly() == self.assembly))
        self.assertTrue(self.assembly.ViewObject.isInEditMode())
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 2)
        self.assertAlmostEqual(self.first.Shape.Volume, 60, places=8)
        self.assertAlmostEqual(self.second.Shape.Volume, 24, places=8)
        self.assertEqual(self.joints.Group, [])
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])
        self.assertEqual(self.doc.FileName, "")
        self._assert_active()

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            doc = App.getDocument(self.doc_name)
            if doc.HasPendingTransaction:
                doc.abortTransaction()
            owner_gui = Gui.getDocument(self.doc_name)
            if owner_gui.getInEdit():
                owner_gui.resetEdit()
            App.closeDocument(self.doc_name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, obj, names in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(obj):
                if names:
                    for name in names:
                        Gui.Selection.addSelection(document, obj, name)
                else:
                    Gui.Selection.addSelection(document, obj)

    @staticmethod
    def _pump(milliseconds=20):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _assert_active(self):
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertEqual(UtilsAssembly.activeAssembly(), self.assembly)
        self.assertFalse(Gui.Control.activeDialog())
        command = Gui.Command.get(self.command_name)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive(), "Two real components must enable the actual command")

    @staticmethod
    def _selection():
        return tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx("*", 0)
        )

    def _select(self, *components):
        Gui.Selection.clearSelection()
        for component in components:
            Gui.Selection.addSelection(self.doc.Name, self.assembly.Name, component.Name + ".")
        expected = (
            ((self.doc.Name, self.assembly.Name, tuple(obj.Name + "." for obj in components)),)
            if components
            else ()
        )
        self.assertEqual(self._selection(), expected)
        resolved = []
        for selected in Gui.Selection.getSelectionEx("*", 0):
            for sub in selected.SubElementNames:
                component, relative = UtilsAssembly.getComponentReference(
                    self.assembly, selected.Object, sub
                )
                self.assertEqual(relative, "")
                resolved.append(component)
        self.assertEqual(resolved, list(components))
        self._assert_active()

    @staticmethod
    def _placement(obj):
        return tuple(obj.Placement.Base), tuple(obj.Placement.Rotation.Q)

    def _geometry(self):
        return tuple(
            (
                obj.Name,
                obj.Label,
                obj.Length.Value,
                obj.Width.Value,
                obj.Height.Value,
                obj.Shape.Volume,
                self._placement(obj),
                obj.Visibility,
            )
            for obj in (self.first, self.second)
        )

    def _model(self):
        return {
            "objects": tuple(obj.Name for obj in self.doc.Objects),
            "assembly_group": tuple(obj.Name for obj in self.assembly.Group),
            "joint_group": tuple(obj.Name for obj in self.joints.Group),
            "assembly_placement": self._placement(self.assembly),
            "geometry": self._geometry(),
        }

    def _capture(self, action):
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports, "The real Report view must observe callback exceptions")
        previous = [widget.toPlainText() for widget in reports]
        value = action()
        self._pump()
        output = []
        for widget, before in zip(reports, previous):
            after = widget.toPlainText()
            output.append(after[len(before) :] if after.startswith(before) else after)
        text = "\n".join(output).lower()
        for marker in (
            "traceback",
            "access violation",
            "segmentation fault",
            "<exception>",
            "running the python command",
        ):
            with self.subTest(report_marker=marker):
                self.assertNotIn(marker, text)
        self._assert_active()
        return value

    def _assert_joint(self, joint, members):
        self.assertIsInstance(joint.Proxy, JointObject.RigidGroupJoint)
        self.assertEqual(joint.ObjectsToRigidGroup, members)
        self.assertEqual(len(joint.RigidPlacements), len(members))
        self.assertEqual(joint.getTypeIdOfProperty("ObjectsToRigidGroup"), "App::PropertyLinkList")
        self.assertEqual(joint.getTypeIdOfProperty("RigidPlacements"), "App::PropertyPlacementList")
        self.assertIn("Hidden", joint.getPropertyStatus("RigidPlacements"))
        self.assertIn("ReadOnly", joint.getPropertyStatus("RigidPlacements"))
        self.assertFalse(getattr(joint.Proxy, "_busy", False))
        self.assertTrue(joint.isValid())
        self.assertNotIn("Invalid", joint.State)
        anchor = members[0]
        for member, placement in zip(members, joint.RigidPlacements):
            self.assertTrue(placement.isSame(anchor.Placement.inverse() * member.Placement, 1e-9))
        self.assertEqual(self.joints.Group, [joint])

    def _construct(self, members):
        joint = self.joints.newObject("App::FeaturePython", "RigidGroupJoint")
        JointObject.RigidGroupJoint(joint, members)
        return joint

    def test_direct_constructor_has_no_error_and_later_member_change_updates_placements(self):
        before = self._geometry()
        joint = self._capture(lambda: self._construct([self.first, self.second]))
        self._assert_joint(joint, [self.first, self.second])
        self.assertEqual(self._geometry(), before)
        self._capture(lambda: setattr(joint, "ObjectsToRigidGroup", [self.second, self.first]))
        self._assert_joint(joint, [self.second, self.first])
        self.assertEqual(self._geometry(), before)

    def test_actual_command_initializes_members_and_one_undo_redo_without_error(self):
        self._select(self.first, self.second)
        before = self._model()
        self._capture(lambda: Gui.runCommand(self.command_name))
        self.assertEqual(len(self.joints.Group), 1)
        joint = self.joints.Group[0]
        name = joint.Name
        self._assert_joint(joint, [self.first, self.second])
        self.assertEqual(self._geometry(), before["geometry"])
        self.assertIsNotNone(joint.ViewObject.Proxy)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Create Rigid Group"])
        self._capture(self.doc.undo)
        self.doc.recompute()
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual(self._model(), before)
        self._capture(self.doc.redo)
        self.doc.recompute()
        restored = self.doc.getObject(name)
        self.assertIsNotNone(restored)
        self._assert_joint(restored, [self.first, self.second])
        self.assertEqual(self._geometry(), before["geometry"])

    def test_constructor_normalizes_duplicate_and_nonplacement_members_control(self):
        marker = self.doc.addObject("App::FeaturePython", "NonPlacementMember")
        self.assertNotIn("Placement", marker.PropertiesList)
        before = self._geometry()
        joint = self._capture(
            lambda: self._construct([self.first, marker, self.first, self.second])
        )
        self._assert_joint(joint, [self.first, self.second])
        self.assertEqual(self._geometry(), before)
        self.assertEqual(self.doc.getObject(marker.Name), marker)
        self.assertNotIn(joint, marker.InList)
