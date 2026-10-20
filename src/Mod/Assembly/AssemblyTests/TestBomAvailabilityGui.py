# SPDX-License-Identifier: LGPL-2.1-or-later
"""Registered BOM command/action availability and genuine task regressions.

Run only in a fresh isolated GUI process. Existing documents are never closed.
"""

import unittest

import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
    import AssemblyGui  # noqa: F401
    import Part  # noqa: F401
    import CommandCreateBom
    from PySide import QtCore, QtWidgets


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestBomDocumentAvailability(unittest.TestCase):
    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "This probe requires an isolated blank desktop")
        self.previous_workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        self.owned = []
        self.retained = []
        pref = CommandCreateBom.Preferences.preferences()
        self.preferences = {key: pref.GetBool(key) if key in pref.GetBools() else None
                            for key in ("BOMOnlyParts", "BOMDetailParts", "BOMDetailSubAssemblies")}
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        Gui.Command.update()
        Gui.updateGui()
        self.command = Gui.Command.get("Assembly_CreateBom")
        self.assertIsNotNone(self.command)
        self.actions = list(self.command.getAction())
        self.assertTrue(self.actions, "Actual Assembly toolbar/menu action was not created")
        self.retained.extend(self.actions)

    def _cleanup(self):
        if Gui.Control.activeDialog():
            dialog = Gui.Control.activeTaskDialog()
            self.retained.append(dialog)
            dialog.reject()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        for name in reversed(self.owned):
            if name in App.listDocuments():
                gui_doc = Gui.getDocument(name)
                if gui_doc.getInEdit():
                    gui_doc.resetEdit()
                App.closeDocument(name)
        pref = CommandCreateBom.Preferences.preferences()
        for key, value in self.preferences.items():
            if value is None:
                pref.RemBool(key)
            else:
                pref.SetBool(key, value)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()

    def _refresh(self, enabled):
        # Command.update schedules MainWindow's ordinary 150 ms activity timer.
        # Pump normal Qt events until its QAction result reaches the explicit
        # expected state, or leave the unchanged caller assertion to report it.
        elapsed = QtCore.QElapsedTimer()
        elapsed.start()
        Gui.Command.update()
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()
        while (any(action.isEnabled() != enabled for action in self.actions)
               and elapsed.elapsed() < 3000):
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()

    def _new_document(self, assembly=False):
        doc = App.newDocument("BomAvailability33117")
        self.owned.append(doc.Name)
        if assembly:
            owner = doc.addObject("Assembly::AssemblyObject", "Assembly")
            owner.newObject("Assembly::JointGroup", "Joints")
            sample = owner.newObject("Part::Box", "Sample")
        else:
            owner = None
            sample = doc.addObject("Part::Box", "Sample")
        doc.recompute()
        if assembly:
            Gui.getDocument(doc.Name).setEdit(owner)
            Gui.updateGui()
            self.assertTrue(owner.ViewObject.isInEditMode())
        self._refresh(enabled=True)
        return doc, owner, sample

    def _assert_real_task_opens(self, assembly=False):
        doc, owner, sample = self._new_document(assembly)
        self.assertTrue(self.command.isActive())
        self.assertTrue(all(action.isEnabled() for action in self.actions))
        before = (sample.Shape.Volume, App.Placement(sample.Placement))
        Gui.runCommand("Assembly_CreateBom")
        Gui.updateGui()
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        self.retained.append(dialog)
        contents = dialog.getDialogContent()
        self.assertTrue(contents)
        self.retained.extend(contents)
        for content in contents:
            parent = content
            while parent is not None:
                self.retained.append(parent)
                parent = parent.parentWidget()
        boms = [obj for obj in doc.Objects if obj.TypeId == "Assembly::BomObject"]
        self.assertEqual(len(boms), 1)
        self.assertEqual(boms[0].Document, doc)
        self.assertNotIn("Invalid", boms[0].State)
        self.assertEqual((sample.Shape.Volume, sample.Placement), before)
        self._refresh(enabled=True)
        self.assertTrue(self.command.isActive(), "Existing ForEdit task gating must remain unchanged")
        self.assertTrue(all(action.isEnabled() for action in self.actions))
        if owner is None:
            self.assertFalse(any(obj.TypeId == "Assembly::BomGroup" for obj in doc.Objects))
        else:
            groups = [obj for obj in doc.Objects if obj.TypeId == "Assembly::BomGroup"]
            self.assertEqual(len(groups), 1)
            self.assertIn(groups[0], owner.Group)
            self.assertIn(boms[0], groups[0].Group)

    def test_no_document_registered_command_is_inactive(self):
        self.assertIsNone(App.activeDocument())
        self.assertFalse(self.command.isActive())

    def test_no_document_real_toolbar_action_is_disabled(self):
        self.assertIsNone(App.activeDocument())
        self._refresh(enabled=False)
        self.assertTrue(all(not action.isEnabled() for action in self.actions))

    def test_plain_document_real_bom_task_control(self):
        self._assert_real_task_opens()

    def test_active_assembly_real_bom_task_control(self):
        self._assert_real_task_opens(assembly=True)

    def test_closing_last_owned_document_disables_command_and_action(self):
        doc, _, _ = self._new_document()
        self.assertTrue(self.command.isActive())
        self.assertTrue(all(action.isEnabled() for action in self.actions))
        App.closeDocument(doc.Name)
        self._refresh(enabled=False)
        self.assertEqual(App.listDocuments(), {})
        with self.subTest(oracle="registered_command"):
            self.assertFalse(self.command.isActive())
        with self.subTest(oracle="real_action"):
            self.assertTrue(all(not action.isEnabled() for action in self.actions))


if __name__ == "__main__":
    unittest.main()
