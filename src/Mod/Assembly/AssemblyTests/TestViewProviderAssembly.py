# SPDX-License-Identifier: LGPL-2.1-or-later

"""Assembly isolation state and argument validation regressions."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import Part
    import AssemblyApp
    import AssemblyGui


class _LengthErrorList(list):
    def __len__(self):
        raise ValueError("isolation sequence length failed")


class _ItemErrorList(list):
    def __getitem__(self, index):
        if index == 1:
            raise LookupError("isolation sequence item failed")
        return super().__getitem__(index)


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestViewProviderAssembly(unittest.TestCase):
    def setUp(self):
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument("AssemblyIsolationTest")
        self.addCleanup(self._cleanup)
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.first = self.assembly.newObject("Part::Box", "First")
        self.second = self.assembly.newObject("Part::Box", "Second")
        self.second.Placement.Base = App.Vector(15, 0, 0)
        self.doc.recompute()
        self.provider = self.assembly.ViewObject
        self.first.Visibility = True
        self.second.Visibility = True
        self.first.ViewObject.Selectable = True
        self.second.ViewObject.Selectable = True

    def _cleanup(self):
        if self.doc.Name in App.listDocuments():
            self.assembly.ViewObject.clearIsolate()
            App.closeDocument(self.doc.Name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    def _state(self):
        return tuple(
            (bool(obj.Visibility), bool(obj.ViewObject.Selectable))
            for obj in (self.first, self.second)
        )

    def _check_rejected_sequence(self, sequence, error_type, message, preexisting=False):
        if preexisting:
            self.provider.isolateComponents([self.second], 2)
            self.assertEqual(self._state(), ((False, True), (True, True)))
        before = self._state()
        error = None
        try:
            self.provider.isolateComponents(sequence, 2)
        except Exception as caught:
            error = caught
        self.assertEqual(
            self._state(), before, "A sequence protocol error changed component isolation"
        )
        self.assertIsInstance(error, error_type)
        self.assertEqual(str(error), message)

    def test_length_error_preserves_visibility_and_original_exception(self):
        self._check_rejected_sequence(
            _LengthErrorList([self.first]), ValueError, "isolation sequence length failed"
        )

    def test_item_error_preserves_visibility_and_original_exception(self):
        self._check_rejected_sequence(
            _ItemErrorList([self.first, self.second]),
            LookupError,
            "isolation sequence item failed",
        )

    def test_item_error_preserves_existing_isolation(self):
        self._check_rejected_sequence(
            _ItemErrorList([self.first, self.second]),
            LookupError,
            "isolation sequence item failed",
            preexisting=True,
        )

    def _check_ordinary(self, values):
        self.provider.isolateComponents(values, 2)
        self.assertEqual(self._state(), ((True, True), (False, True)))
        self.provider.clearIsolate()
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_ordinary_list_control(self):
        self._check_ordinary([self.first])

    def test_ordinary_tuple_control(self):
        self._check_ordinary((self.first,))

    def test_ordinary_mixed_sequence_keeps_ignoring_non_objects(self):
        self._check_ordinary([None, self.first, object()])

    def test_empty_sequence_keeps_isolating_no_components(self):
        self.provider.isolateComponents([], 2)
        self.assertEqual(self._state(), ((False, True), (False, True)))
        self.provider.clearIsolate()
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_non_sequence_rejection_control(self):
        before = self._state()
        with self.assertRaises(TypeError):
            self.provider.isolateComponents(object(), 2)
        self.assertEqual(self._state(), before)

    def test_invalid_mode_rejection_control(self):
        before = self._state()
        with self.assertRaises(ValueError):
            self.provider.isolateComponents([self.first], 3)
        self.assertEqual(self._state(), before)

    def _change_selection(self):
        import FreeCADGui as Gui

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name, "First.Face1")
        Gui.Selection.clearSelection()

    def test_selection_clears_temporary_isolation_control(self):
        self.provider.isolateComponents([self.first], 2)
        self.assertFalse(self.provider.hasPersistentIsolation())
        self._change_selection()
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_persistent_isolation_survives_selection_and_transactions(self):
        # https://github.com/FreeCAD/FreeCAD/issues/12142
        self.provider.isolateComponents([self.first], 2, True)
        self.assertTrue(self.provider.hasPersistentIsolation())
        self._change_selection()
        self.doc.openTransaction("Edit")
        self.first.Placement.Base = App.Vector(1, 0, 0)
        self.doc.commitTransaction()
        self.assertEqual(self._state(), ((True, True), (False, True)))

        self.provider.clearIsolate()
        self.assertFalse(self.provider.hasPersistentIsolation())
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_isolate_selection_command_toggles(self):
        import FreeCADGui as Gui

        Gui.ActiveDocument.setEdit(self.assembly)
        self.addCleanup(Gui.ActiveDocument.resetEdit)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name, "First.Face1")
        Gui.runCommand("Assembly_IsolateSelection")
        self.assertTrue(self.provider.hasPersistentIsolation())
        # the other component is transparent and cannot be selected
        self.assertFalse(self.second.ViewObject.Selectable)
        self.assertTrue(self.first.ViewObject.Selectable)

        Gui.runCommand("Assembly_IsolateSelection")
        self.assertFalse(self.provider.hasPersistentIsolation())
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_isolation_task_box_ends_isolation(self):
        # A running isolation shows an "Isolation" box in the task panel whose
        # button ends it, so the isolation can be dismissed without the menus.
        import FreeCADGui as Gui
        from PySide import QtWidgets

        def shown(widget):
            # The task box is hidden while its watcher does not apply.
            while widget is not None and not isinstance(widget, QtWidgets.QStackedWidget):
                if widget.isHidden():
                    return False
                widget = widget.parentWidget()
            return True

        def endButtons():
            return [
                button
                for button in Gui.getMainWindow().findChildren(QtWidgets.QToolButton)
                if button.defaultAction()
                and button.defaultAction().objectName() == "Assembly_EndIsolation"
                and shown(button)
            ]

        previousWorkbench = Gui.activeWorkbench().name()
        Gui.activateWorkbench("AssemblyWorkbench")
        self.addCleanup(Gui.activateWorkbench, previousWorkbench)
        Gui.ActiveDocument.setEdit(self.assembly)
        self.addCleanup(Gui.ActiveDocument.resetEdit)
        self.assertEqual(endButtons(), [])

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name, "First.Face1")
        Gui.runCommand("Assembly_IsolateSelection")
        self.assertTrue(self.provider.hasPersistentIsolation())
        buttons = endButtons()
        self.assertEqual(len(buttons), 1)

        # Let the main window's action update enable the command, as it does for a user.
        from PySide import QtCore

        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(400, loop.quit)
        loop.exec_()
        self.assertTrue(buttons[0].defaultAction().isEnabled())
        buttons[0].click()
        self.assertFalse(self.provider.hasPersistentIsolation())
        self.assertEqual(self._state(), ((True, True), (True, True)))
        self.assertEqual(endButtons(), [])

        # A temporary (joint) isolation does not show the box.
        self.provider.isolateComponents([self.first], 2)
        Gui.Selection.clearSelection()
        self.assertEqual(endButtons(), [])

    def test_leaving_edit_ends_persistent_isolation(self):
        # Outside the assembly edit the command is inactive, so an isolation kept
        # there would leave the other components unselectable with no way back.
        import FreeCADGui as Gui

        guiDoc = Gui.getDocument(self.doc.Name)
        guiDoc.setEdit(self.assembly)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.assembly.Name, "First.Face1")
        Gui.runCommand("Assembly_IsolateSelection")
        self.assertTrue(self.provider.hasPersistentIsolation())
        self.assertFalse(self.second.ViewObject.Selectable)

        guiDoc.resetEdit()
        self.assertFalse(self.provider.isInEditMode())
        self.assertFalse(self.provider.hasPersistentIsolation())
        self.assertEqual(self._state(), ((True, True), (True, True)))
