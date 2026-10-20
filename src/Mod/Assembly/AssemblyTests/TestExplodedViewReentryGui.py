# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exploded-view task re-entry preserves drafts and ordinary task switching."""

import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import CommandCreateView as Views
    import UtilsAssembly
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestExplodedViewReentryGui(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        ]
        pref = Views.Preferences.preferences()
        self.preferences = {
            key: pref.GetBool(key) if key in pref.GetBools() else None
            for key in (
                "PartsAsSingleSolid",
                "BOMOnlyParts",
                "BOMDetailParts",
                "BOMDetailSubAssemblies",
            )
        }
        self.doc_name = None
        self.retained = []
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog())
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("ExplodedReentry_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.assembly.newObject("Assembly::JointGroup", "Joints")
        self.first = self.assembly.newObject("Part::Box", "First")
        self.second = self.assembly.newObject("Part::Box", "Second")
        self.second.Placement.Base = App.Vector(15, 0, 0)
        self.doc.recompute()
        Gui.getDocument(self.doc_name).setEdit(self.assembly)
        self._pump()
        self.assertEqual(UtilsAssembly.activeAssembly(), self.assembly)
        self.assertFalse(Gui.Control.activeDialog())
        self.assertEqual(self.doc.FileName, "")
        self.original = App.Placement(self.second.Placement)
        self.doc.clearUndos()

    @staticmethod
    def _pump():
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _retain(self, widget):
        while widget is not None:
            self.retained.append(widget)
            widget = widget.parent()

    def _cleanup(self):
        try:
            if self.doc_name in App.listDocuments():
                App.setActiveDocument(self.doc_name)
                task = Gui.Control.activeTaskDialog()
                if task:
                    self.retained.append(task)
                    task.reject()
                    self._pump()
                if self.doc.HasPendingTransaction:
                    self.doc.abortTransaction()
                owner = Gui.getDocument(self.doc_name)
                if owner.getInEdit():
                    owner.resetEdit()
                Gui.Selection.clearSelection()
                App.closeDocument(self.doc_name)
        finally:
            pref = Views.Preferences.preferences()
            for key, value in self.preferences.items():
                if value is None:
                    pref.RemBool(key)
                else:
                    pref.SetBool(key, value)
            if self.previous_document in App.listDocuments():
                App.setActiveDocument(self.previous_document)
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            for document, name, subnames in self.previous_selection:
                if document in App.listDocuments() and App.getDocument(document).getObject(name):
                    if subnames:
                        for subname in subnames:
                            Gui.Selection.addSelection(document, name, subname)
                    else:
                        Gui.Selection.addSelection(document, name)

    def _assert_original(self):
        self.assertLess((self.second.Placement.Base - self.original.Base).Length, 1e-8)
        self.assertTrue(self.second.Placement.Rotation.isSame(self.original.Rotation, 1e-8))
        self.assertAlmostEqual(self.first.Shape.Volume, 1000)
        self.assertAlmostEqual(self.second.Shape.Volume, 1000)

    def _current_panel(self, view):
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        self.retained.append(dialog)
        callback = view.Proxy.stepsChangedCallback
        self.assertIsNotNone(callback)
        panel = callback.__self__
        self.assertIsInstance(panel, Views.TaskAssemblyCreateView)
        self.assertEqual(panel.viewObj, view)
        self.assertIsNotNone(panel.form)
        self.retained.append(panel)
        contents = dialog.getDialogContent()
        self.assertTrue(contents)
        self.assertTrue(
            any(widget == panel.form or widget.isAncestorOf(panel.form) for widget in contents)
        )
        for widget in contents:
            self._retain(widget)
        self._retain(panel.form)
        return panel

    def _create_and_record(self, distance=7):
        self.assertTrue(Gui.Command.get("Assembly_CreateView").isActive())
        Gui.runCommand("Assembly_CreateView")
        self._pump()
        task = Gui.doCommandEval("panel")
        self.assertIsInstance(task, Views.TaskAssemblyCreateView)
        self.retained.append(task)
        self.assertIs(self._current_panel(task.viewObj), task)
        Gui.Selection.addSelection(self.doc_name, self.assembly.Name, self.second.Name + ".")
        self._pump()
        self.assertEqual(task.selectedObjs, [self.second])
        moved = App.Placement(self.assembly.ViewObject.DraggerPlacement)
        moved.Base += App.Vector(distance, 0, 0)
        self.assembly.ViewObject.DraggerPlacement = moved
        task.draggerMoved(None)
        self._pump()
        self.assertEqual(len(task.viewObj.Group), 1)
        self.assertAlmostEqual(self.second.Placement.Base.x, 15 + distance)
        self.assertTrue(self.doc.HasPendingTransaction)
        return task

    @staticmethod
    def _placement(value):
        return (tuple(value.Base), value.Rotation.Q)

    def _draft(self, view):
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "parts": tuple(
                (obj.Name, self._placement(obj.Placement), obj.Shape.Volume)
                for obj in (self.first, self.second)
            ),
            "moves": tuple(
                (
                    move.Name,
                    move.MoveType,
                    self._placement(move.MovementTransform),
                    move.References[0].Name,
                    tuple(move.References[1]),
                )
                for move in view.Group
            ),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "selection": tuple(
                (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
                for item in Gui.Selection.getSelectionEx()
            ),
        }

    def _double_click(self, view):
        try:
            result = view.ViewObject.Proxy.doubleClicked(view.ViewObject)
        except Exception as error:
            self.fail("Exploded-view double-click raised " + repr(error))
        self.assertTrue(result)
        self._pump()

    def _reject_current(self):
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        self.retained.append(dialog)
        dialog.reject()
        self._pump()
        self.assertIsNone(Gui.Control.activeTaskDialog())

    def _save_view(self, distance=7):
        panel = self._create_and_record(distance)
        view = panel.viewObj
        self.assertTrue(panel.accept())
        self._pump()
        self.assertIsNone(Gui.Control.activeTaskDialog())
        self.assertIsNone(view.Proxy.stepsChangedCallback)
        self._assert_original()
        self.assertFalse(self.doc.HasPendingTransaction)
        return view

    def test_create_record_accept_and_reopen_cancel_control(self):
        view = self._save_view()
        self._double_click(view)
        self._current_panel(view)
        self.assertAlmostEqual(self.second.Placement.Base.x, 22)
        self._reject_current()
        self._assert_original()
        self.assertEqual(self.doc.getObject(view.Name), view)

    def test_reenter_new_current_view_preserves_draft_and_pending_transaction(self):
        panel = self._create_and_record()
        view = panel.viewObj
        view_name = view.Name
        before = self._draft(view)
        for _ in range(3):
            self._double_click(view)
            self.assertEqual(self.doc.getObject(view_name), view)
            self.assertIs(self._current_panel(view), panel)
            self.assertEqual(self._draft(view), before)
        self._reject_current()
        self._assert_original()
        self.assertIsNone(self.doc.getObject(view_name))
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_reenter_saved_current_view_preserves_preview_and_cancel_restores_model(self):
        view = self._save_view()
        self._double_click(view)
        panel = self._current_panel(view)
        self.assertAlmostEqual(self.second.Placement.Base.x, 22)
        self.assertTrue(self.doc.HasPendingTransaction)
        before = self._draft(view)
        for _ in range(3):
            self._double_click(view)
            self.assertIs(self._current_panel(view), panel)
            self.assertEqual(self._draft(view), before)
        self._reject_current()
        self._assert_original()
        self.assertEqual(self.doc.getObject(view.Name), view)
        self.assertEqual(len(view.Group), 1)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_other_saved_view_still_switches_and_only_its_preview_is_applied(self):
        first_view = self._save_view(7)
        second_view = self._save_view(11)
        self.assertNotEqual(first_view, second_view)
        undo = tuple(self.doc.UndoNames)
        self._double_click(first_view)
        first_panel = self._current_panel(first_view)
        self.assertAlmostEqual(self.second.Placement.Base.x, 22)
        self._double_click(second_view)
        second_panel = self._current_panel(second_view)
        self.assertIsNot(first_panel, second_panel)
        self.assertIsNone(first_view.Proxy.stepsChangedCallback)
        self.assertAlmostEqual(self.second.Placement.Base.x, 26)
        self.assertEqual(len(first_view.Group), 1)
        self.assertEqual(len(second_view.Group), 1)
        self._reject_current()
        self._assert_original()
        self.assertIsNone(second_view.Proxy.stepsChangedCallback)
        self.assertEqual(tuple(self.doc.UndoNames), undo)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_bill_of_materials_task_still_switches_to_saved_exploded_view(self):
        view = self._save_view()
        objects = tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects)
        undo = tuple(self.doc.UndoNames)
        command = Gui.Command.get("Assembly_CreateBom")
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        Gui.runCommand("Assembly_CreateBom")
        self._pump()
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        self.retained.append(dialog)
        contents = dialog.getDialogContent()
        self.assertTrue(contents)
        self.assertTrue(
            any(widget.findChild(QtWidgets.QListWidget, "columnList") for widget in contents)
        )
        for widget in contents:
            self._retain(widget)
        boms = [obj for obj in self.doc.Objects if obj.TypeId == "Assembly::BomObject"]
        self.assertEqual(len(boms), 1)
        bom_name = boms[0].Name
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertIsNone(view.Proxy.stepsChangedCallback)
        self._double_click(view)
        self._current_panel(view)
        self.assertIsNone(self.doc.getObject(bom_name))
        self.assertEqual(tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects), objects)
        self.assertAlmostEqual(self.second.Placement.Base.x, 22)
        self._reject_current()
        self._assert_original()
        self.assertEqual(tuple(self.doc.UndoNames), undo)
        self.assertFalse(self.doc.HasPendingTransaction)
