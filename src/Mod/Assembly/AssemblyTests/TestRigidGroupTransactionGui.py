# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rigid-group selection validation preserves document transactions and geometry."""

import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import CommandCreateJoint  # noqa: F401
    import UtilsAssembly
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestRigidGroupTransactionGui(unittest.TestCase):
    command_name = "Assembly_CreateJointRigidGroup"
    count_warning = "Select at least 2 components to create a rigid group"

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

    def _snapshot(self):
        return {
            "model": self._model(),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "selection": self._selection(),
        }

    def _run(self, expected_warning=None, command_name=None):
        self._assert_active()
        command_name = command_name or self.command_name
        command = Gui.Command.get(command_name)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports, "The real Report view must observe the command warning/errors")
        previous = [widget.toPlainText() for widget in reports]
        Gui.runCommand(command_name)
        self._pump()
        output = []
        for widget, before in zip(reports, previous):
            after = widget.toPlainText()
            output.append(after[len(before) :] if after.startswith(before) else after)
        text = "\n".join(output)
        if expected_warning is None:
            self.assertNotIn(self.count_warning, text)
        else:
            self.assertIn(expected_warning, text, "The real count-validation branch must execute")
        for marker in (
            "traceback",
            "access violation",
            "segmentation fault",
            "<exception>",
            "running the python command",
        ):
            self.assertNotIn(marker, text.lower())
        self._assert_active()

    def _assert_snapshot(self, before):
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])

    def _pending_edit(self):
        original = self.first.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.first.Label = "Pending first component label"
        self.assertTrue(self.doc.HasPendingTransaction)
        return original

    def _assert_abort_restores(self, original):
        self.doc.abortTransaction()
        with self.subTest(oracle="original_transaction_still_abortable"):
            self.assertEqual(self.first.Label, original)
        with self.subTest(oracle="unrelated_edit_not_committed_to_undo_history"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_rejected_single_component_preserves_fresh_state_and_next_direct_edit(self):
        self._select(self.first)
        before = self._snapshot()
        self._run(self.count_warning)
        self._assert_snapshot(before)
        self.first.Label = "Next direct label"
        self.assertEqual(self.first.Label, "Next direct label")
        self.assertEqual(self.doc.UndoNames, [])
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), before["booked"])

    def test_rejected_single_component_preserves_pending_edit(self):
        original = self._pending_edit()
        self._select(self.first)
        before = self._snapshot()
        self._run(self.count_warning)
        self._assert_snapshot(before)
        self._assert_abort_restores(original)

    def test_rejected_single_component_preserves_redo_history(self):
        original = self.first.Label
        self.doc.openTransaction("Existing redo edit")
        self.first.Label = "Undone component label"
        self.doc.commitTransaction()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.first.Label, original)
        self.assertEqual(self.doc.RedoNames, ["Existing redo edit"])
        self._select(self.first)
        before = self._snapshot()
        self._run(self.count_warning)
        self._assert_snapshot(before)
        self.doc.redo()
        self.assertEqual(self.first.Label, "Undone component label")
        self.assertEqual(self.joints.Group, [])

    def test_empty_selection_preserves_pending_edit_control(self):
        original = self._pending_edit()
        self._select()
        before = self._snapshot()
        self._run()
        self._assert_snapshot(before)
        self._assert_abort_restores(original)

    def test_fit_all_preserves_pending_edit_control(self):
        original = self._pending_edit()
        self._select(self.first)
        before = self._snapshot()
        self._run(command_name="Std_ViewFitAll")
        self._assert_snapshot(before)
        self._assert_abort_restores(original)

    def test_valid_two_component_creation_undo_redo_control(self):
        self._select(self.first, self.second)
        before = self._model()
        self._run()
        self.assertEqual(len(self.joints.Group), 1)
        joint = self.joints.Group[0]
        name = joint.Name
        self.assertEqual(joint.ObjectsToRigidGroup, [self.first, self.second])
        self.assertEqual(len(joint.RigidPlacements), 2)
        for member, placement in zip(joint.ObjectsToRigidGroup, joint.RigidPlacements):
            self.assertTrue(
                placement.isSame(self.first.Placement.inverse() * member.Placement, 1e-9)
            )
        self.assertTrue(joint.isValid())
        self.assertEqual(self._geometry(), before["geometry"])
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Create Rigid Group"])
        self.doc.undo()
        self.doc.recompute()
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual(self._model(), before)
        self.doc.redo()
        self.doc.recompute()
        restored = self.doc.getObject(name)
        self.assertIsNotNone(restored)
        self.assertEqual(self.joints.Group, [restored])
        self.assertEqual(restored.ObjectsToRigidGroup, [self.first, self.second])
        self.assertTrue(restored.isValid())
        self.assertEqual(self._geometry(), before["geometry"])
