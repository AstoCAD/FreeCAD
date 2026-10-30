# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regressions for the actual Assembly joint command and task lifecycle."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import JointObject
    import CommandCreateJoint
    from PySide import QtCore, QtWidgets


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestCommandCreateJoint(unittest.TestCase):
    def setUp(self):
        self.previous = App.activeDocument().Name if App.activeDocument() else None
        self.previous_workbench = Gui.activeWorkbench().name()
        self.owned_names = []
        self.task = None
        self.owner_name = None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        self.owner = App.newDocument("JointTaskCloseOwner")
        self.owner_name = self.owner.Name
        self.owned_names.append(self.owner_name)
        self.assembly = self.owner.addObject("Assembly::AssemblyObject", "Assembly")
        self.assembly.newObject("Assembly::JointGroup", "Joints")
        self.assembly.newObject("Part::Box", "Box")
        self.owner.recompute()
        self.owner_gui = Gui.getDocument(self.owner_name)
        self.owner_gui.setEdit(self.assembly)
        Gui.updateGui()
        self.assertTrue(self.assembly.ViewObject.isInEditMode())
        CommandCreateJoint.activateJoint(0)
        self.task = JointObject.activeTask
        Gui.updateGui()
        self.assertIsNotNone(self.task)
        self.assertIs(JointObject.activeTask, self.task)
        self.assertTrue(Gui.Control.activeDialog(self.owner_gui))
        dialog = Gui.Control.activeTaskDialog(self.owner_gui)
        self.assertTrue(dialog.isAutoCloseOnDeletedDocument())
        self.assertTrue(dialog.isAutoCloseOnTransactionChange())
        self.assertEqual(dialog.getDocumentName(), self.owner_name)
        self.owner_transaction_id = self.owner.getBookedTransactionID()
        self.assertGreater(self.owner_transaction_id, 0)
        self.callback_events = []
        original_deleted_callback = self.task.autoClosedOnDeletedDocument

        def trace_deleted_callback():
            active = App.activeDocument()
            module_active = App.ActiveDocument
            context = (active.Name if active else None,
                       module_active.Name if module_active else None)
            self.callback_events.append(context)
            print("JOINT_TASK_ACTUAL_DELETE_CALLBACK", context, flush=True)
            return original_deleted_callback()

        self.task.autoClosedOnDeletedDocument = trace_deleted_callback
        self.undo_events = []
        original_transaction_callback = self.task.autoClosedOnTransactionChange

        def trace_transaction_callback():
            active = App.activeDocument()
            module_active = App.ActiveDocument
            context = (active.Name if active else None,
                       module_active.Name if module_active else None)
            self.undo_events.append(context)
            print("JOINT_TASK_ACTUAL_UNDO_CALLBACK", context, flush=True)
            return original_transaction_callback()

        self.task.autoClosedOnTransactionChange = trace_transaction_callback
        self.other = App.newDocument("JointTaskCloseOther")
        self.other_name = self.other.Name
        self.owned_names.append(self.other_name)
        self.value = self.other.addObject("App::FeaturePython", "UnrelatedValue")
        self.value.Label = "Original unrelated value"
        self.other.recompute()

    def _cleanup(self):
        if self.owner_name in App.listDocuments():
            App.setActiveDocument(self.owner_name)
            if self.task is not None and Gui.Control.activeDialog(self.owner_gui):
                self.task.reject()
                if Gui.Control.activeDialog(self.owner_gui):
                    Gui.Control.closeDialog(self.owner_gui)
            if self.owner_gui.getInEdit():
                self.owner_gui.resetEdit()
        for name in reversed(self.owned_names):
            if name in App.listDocuments():
                App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        Gui.activateWorkbench(self.previous_workbench)
        Gui.Selection.clearSelection()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        Gui.updateGui()

    def _close_owner(self):
        self.assertEqual(App.activeDocument().Name, self.other_name)
        self.assertIs(JointObject.activeTask, self.task)
        self.assertFalse(self.callback_events)
        self.assertTrue(Gui.Control.activeDialog(self.owner_gui),
                        "Owner task must still exist before document-close callback")
        owner_id = self.owner.getBookedTransactionID()
        other_id = self.other.getBookedTransactionID()
        print("JOINT_TASK_TRANSACTION_IDS", self.owner_transaction_id, owner_id, other_id,
              self.other.HasPendingTransaction, flush=True)
        if self.other.HasPendingTransaction:
            self.assertGreater(other_id, 0)
            self.assertNotEqual(other_id, self.owner_transaction_id)
            self.assertNotEqual(other_id, owner_id)
        print("JOINT_TASK_OWNER_CLOSE_ENTER", self.owner_name, self.other_name,
              self.other.HasPendingTransaction, self.value.Label, flush=True)
        App.closeDocument(self.owner_name)
        Gui.updateGui()
        self.assertEqual(self.callback_events, [(self.other_name, self.other_name)],
                         "Actual command deletion callback must execute in the other document")
        print("JOINT_TASK_OWNER_CLOSE_RETURN", self.other.HasPendingTransaction,
              self.value.Label, flush=True)

    def _undo_owner(self):
        self.assertEqual(App.activeDocument().Name, self.other_name)
        self.assertIs(JointObject.activeTask, self.task)
        self.assertTrue(Gui.Control.activeDialog(self.owner_gui))
        owner_id = self.owner.getBookedTransactionID()
        other_id = self.other.getBookedTransactionID()
        print("JOINT_TASK_UNDO_TRANSACTION_IDS", self.owner_transaction_id,
              owner_id, other_id, flush=True)
        if self.other.HasPendingTransaction:
            self.assertGreater(other_id, 0)
            self.assertNotEqual(other_id, self.owner_transaction_id)
            self.assertNotEqual(other_id, owner_id)
        print("JOINT_TASK_OWNER_UNDO_ENTER", self.value.Label,
              self.other.HasPendingTransaction, flush=True)
        self.owner.undo()
        Gui.updateGui()
        self.assertEqual(self.undo_events, [(self.other_name, self.other_name)],
                         "Actual command transaction callback must execute in the other document")
        self.assertFalse(self.callback_events)
        self.assertIsNone(JointObject.activeTask)
        self.assertFalse(Gui.Control.activeDialog(self.owner_gui))
        print("JOINT_TASK_OWNER_UNDO_RETURN", self.value.Label,
              self.other.HasPendingTransaction, flush=True)

    def test_background_owner_close_preserves_other_pending_transaction(self):
        self.other.openTransaction("Unrelated user change")
        self.value.Label = "Pending unrelated value"
        self.assertTrue(self.other.HasPendingTransaction)
        self._close_owner()
        self.assertEqual(self.value.Label, "Pending unrelated value")
        self.assertTrue(self.other.HasPendingTransaction)

    def test_background_owner_close_preserves_other_committed_value(self):
        self.other.openTransaction("Committed unrelated change")
        self.value.Label = "Committed unrelated value"
        self.other.commitTransaction()
        self.assertFalse(self.other.HasPendingTransaction)
        self._close_owner()
        self.assertEqual(self.value.Label, "Committed unrelated value")
        self.assertFalse(self.other.HasPendingTransaction)

    def test_closing_unrelated_document_keeps_owner_task(self):
        App.setActiveDocument(self.owner_name)
        App.closeDocument(self.other_name)
        Gui.updateGui()
        self.assertIs(JointObject.activeTask, self.task)
        self.assertTrue(Gui.Control.activeDialog(self.owner_gui))
        self.assertFalse(self.callback_events)

    def test_background_undo_preserves_other_pending_transaction(self):
        self.other.openTransaction("Unrelated user change")
        self.value.Label = "Pending unrelated value"
        self.assertTrue(self.other.HasPendingTransaction)
        self._undo_owner()
        self.assertEqual(self.value.Label, "Pending unrelated value")
        self.assertTrue(self.other.HasPendingTransaction)

    def test_background_undo_preserves_other_committed_value(self):
        self.other.openTransaction("Committed unrelated change")
        self.value.Label = "Committed unrelated value"
        self.other.commitTransaction()
        self.assertFalse(self.other.HasPendingTransaction)
        self._undo_owner()
        self.assertEqual(self.value.Label, "Committed unrelated value")
        self.assertFalse(self.other.HasPendingTransaction)

    def test_angle_limit_spinboxes_accept_a_full_turn(self):
        """Angle limits beyond 180 degrees can be entered (issue #30123)."""
        for spin in (self.task.jForm.limitRotMinSpinbox, self.task.jForm.limitRotMaxSpinbox):
            self.assertEqual(spin.property("minimum"), -360.0)
            self.assertEqual(spin.property("maximum"), 360.0)
            spin.setProperty("rawValue", 270.0)
            self.assertAlmostEqual(spin.property("rawValue"), 270.0)
            spin.setProperty("rawValue", -270.0)
            self.assertAlmostEqual(spin.property("rawValue"), -270.0)

    def test_reject_active_owner_aborts_joint_transaction(self):
        App.setActiveDocument(self.owner_name)
        Gui.updateGui()
        joint_name = self.task.joint.Name
        self.assertIsNotNone(self.owner.getObject(joint_name))
        self.assertTrue(self.owner.HasPendingTransaction)
        self.assertTrue(self.task.reject())
        Gui.updateGui()
        self.assertIsNone(self.owner.getObject(joint_name))
        self.assertFalse(self.owner.HasPendingTransaction)
        self.assertIsNone(JointObject.activeTask)
        self.assertFalse(Gui.Control.activeDialog(self.owner_gui))
        self.assertFalse(self.callback_events)
        self.assertFalse(self.undo_events)
