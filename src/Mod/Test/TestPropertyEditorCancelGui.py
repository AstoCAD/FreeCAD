# SPDX-License-Identifier: LGPL-2.1-or-later
"""Keyboard acceptance and cancellation in the live property editor."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest

from TestPropertyEditorGui import PropertyEditorGuiTestCase


class TestPropertyEditorCancelGui(PropertyEditorGuiTestCase):
    def _new_values(self):
        obj = self.doc.addObject("App::VarSet", "Variables")
        obj.addProperty("App::PropertyInteger", "Value", "Values")
        obj.addProperty("App::PropertyString", "Unrelated", "Values")
        obj.Value = 7
        obj.Unrelated = "Original unrelated value"
        self.doc.recompute()
        self.doc.clearUndos()
        return obj

    def _open_data_editor(self, obj):
        model, index = self.property_model(obj, "Value")
        tree = next(tree for tree in Gui.getMainWindow().findChildren(
            QtWidgets.QTreeView, "propertyEditorData"
        ) if tree.model() == model)
        return tree, index, self._open_editor(tree, index)

    def _open_editor(self, tree, index):
        tree.expandAll()
        tree.scrollTo(index)
        Gui.updateGui()
        QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.LeftButton,
                               QtCore.Qt.NoModifier, tree.visualRect(index).center())
        Gui.updateGui()
        editor = QtWidgets.QApplication.focusWidget()
        self.assertIsNotNone(editor)
        self.assertTrue(tree.isAncestorOf(editor))
        # Keep the custom editor's wrapper alive while using its child QLineEdit.
        self._editor_widget = editor
        line = editor if isinstance(editor, QtWidgets.QLineEdit) else editor.findChild(
            QtWidgets.QLineEdit
        )
        self.assertIsNotNone(line)
        return line

    def _type_value(self, line, value=42):
        line.selectAll()
        QtTest.QTest.keyClicks(line, str(value))
        Gui.updateGui()

    def _press(self, line, key):
        QtTest.QTest.keyClick(line, key)
        Gui.updateGui()

    def _check_key(self, kind, key):
        # https://github.com/FreeCAD/FreeCAD/issues/30992
        obj = self.doc.addObject("App::VarSet", "Variables")
        obj.addProperty("App::Property" + kind, "Value", "Values")
        initial = "original" if kind == "String" else 7
        changed = "changed" if kind == "String" else 42
        obj.Value = initial
        self.doc.recompute()
        _, _, line = self._open_data_editor(obj)
        self._type_value(line, changed)
        self._press(line, key)
        self.assertEqual(obj.Value, initial if key == QtCore.Qt.Key_Escape else changed)

    def test_float_escape(self):
        self._check_key("Float", QtCore.Qt.Key_Escape)

    def test_float_return(self):
        self._check_key("Float", QtCore.Qt.Key_Return)

    def test_integer_escape(self):
        self._check_key("Integer", QtCore.Qt.Key_Escape)

    def test_integer_return(self):
        self._check_key("Integer", QtCore.Qt.Key_Return)

    def test_string_escape(self):
        self._check_key("String", QtCore.Qt.Key_Escape)

    def test_string_return(self):
        self._check_key("String", QtCore.Qt.Key_Return)

    def test_owned_escape_preserves_prior_committed_undo_history(self):
        obj = self._new_values()
        self.doc.openTransaction("Prior committed user change")
        obj.Unrelated = "Prior committed unrelated value"
        self.doc.commitTransaction()
        previous_names = list(self.doc.UndoNames)
        self.assertEqual(previous_names, ["Prior committed user change"])
        _, _, line = self._open_data_editor(obj)
        self._type_value(line)
        self.assertEqual(obj.Value, 42)
        self.assertTrue(self.doc.HasPendingTransaction)
        self._press(line, QtCore.Qt.Key_Escape)
        self.assertEqual(obj.Value, 7)
        self.assertEqual(obj.Unrelated, "Prior committed unrelated value")
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, previous_names)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(obj.Value, 7)
        self.assertEqual(obj.Unrelated, "Original unrelated value")

    def _check_external_pending(self, key):
        obj = self._new_values()
        self.doc.openTransaction("External pending user change")
        obj.Unrelated = "External pending unrelated value"
        external_id = self.doc.getBookedTransactionID()
        self.assertGreater(external_id, 0)
        self.assertTrue(self.doc.HasPendingTransaction)
        previous_names = list(self.doc.UndoNames)
        _, _, line = self._open_data_editor(obj)
        self.assertEqual(self.doc.getBookedTransactionID(), external_id)
        self._type_value(line)
        self.assertEqual(obj.Value, 42)
        self._press(line, key)
        self.assertEqual(obj.Unrelated, "External pending unrelated value")
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), external_id)
        self.assertEqual(self.doc.UndoNames, previous_names)

    def test_external_pending_escape_preserves_unrelated_work(self):
        self._check_external_pending(QtCore.Qt.Key_Escape)

    def test_external_pending_return_preserves_unrelated_work(self):
        self._check_external_pending(QtCore.Qt.Key_Return)

    def test_auto_update_disabled_escape_preserves_external_pending_work(self):
        # The View editor has automatic transactions disabled by default.
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/PropertyView")
        if preferences.GetBool("AutoTransactionView", False):
            self.skipTest("View editor automatic transactions are enabled")
        import Part

        obj = self._new_values()
        box = self.doc.addObject("Part::Box", "Box")
        box.ViewObject.Transparency = 7
        self.doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(box)
        tree = Gui.getMainWindow().findChild(QtWidgets.QTreeView, "propertyEditorView")
        self.assertIsNotNone(tree)
        for tabs in Gui.getMainWindow().findChildren(QtWidgets.QTabWidget):
            tab_index = tabs.indexOf(tree)
            if tab_index >= 0:
                previous_tab = tabs.currentIndex()
                self.addCleanup(tabs.setCurrentIndex, previous_tab)
                tabs.setCurrentIndex(tab_index)
                break
        else:
            self.fail("The View property editor is not in a tab widget")
        for _ in range(40):
            Gui.updateGui()
            index = self.find_property_index(tree.model(), "Transparency")
            if index.isValid() and tree.model().data(index, QtCore.Qt.EditRole) == 7:
                break
            QtTest.QTest.qWait(50)
        else:
            self.fail("The View property editor did not show Box.Transparency")
        self.doc.openTransaction("External pending user change")
        obj.Unrelated = "External pending unrelated value"
        external_id = self.doc.getBookedTransactionID()
        self.assertGreater(external_id, 0)
        self.assertTrue(self.doc.HasPendingTransaction)
        previous_names = list(self.doc.UndoNames)
        line = self._open_editor(tree, index)
        self._type_value(line)
        self.assertEqual(box.ViewObject.Transparency, 42)
        self._press(line, QtCore.Qt.Key_Escape)
        self.assertEqual(obj.Unrelated, "External pending unrelated value")
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), external_id)
        self.assertEqual(self.doc.UndoNames, previous_names)

    def test_ordinary_tab_closure_commits_owned_edit(self):
        obj = self._new_values()
        previous_names = list(self.doc.UndoNames)
        _, _, line = self._open_data_editor(obj)
        self._type_value(line)
        self.assertTrue(self.doc.HasPendingTransaction)
        self._press(line, QtCore.Qt.Key_Tab)
        self.assertEqual(obj.Value, 42)
        self.assertEqual(obj.Unrelated, "Original unrelated value")
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoCount, len(previous_names) + 1)

    def test_programmatic_reset_commits_owned_edit(self):
        obj = self._new_values()
        previous_names = list(self.doc.UndoNames)
        tree, _, line = self._open_data_editor(obj)
        self._type_value(line)
        self.assertTrue(self.doc.HasPendingTransaction)
        # The public virtual reset() closes the persistent editor and commits.
        tree.reset()
        Gui.updateGui()
        self.assertEqual(obj.Value, 42)
        self.assertEqual(obj.Unrelated, "Original unrelated value")
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoCount, len(previous_names) + 1)
