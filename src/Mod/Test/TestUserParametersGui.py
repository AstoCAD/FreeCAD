# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI tests for quick user-parameter input (`myVar = 23 mm`) in expression-capable fields.

A bound Gui::QuantitySpinBox (as in task panels, the property editor and the Sketcher datum
dialog) and its formula dialog create the parameter in the group 'UserParameters' of the variable
set 'UserParameters' of the document, which is created with the first parameter and is not shown
in the tree, and bind the property to it; `myVar` typed for any object resolves to that parameter.
"""

import os
import shutil
import tempfile
import unittest
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestUserParametersGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("UserParametersGui")
        self.doc.UndoMode = 1
        # Two objects with a property to type in. The parameters are not created on them but on
        # the variable set `UserParameters` of the document, see parameters().
        self.holder = self.doc.addObject("App::VarSet", "Holder")
        self.holder.addProperty("App::PropertyLength", "Length", "Base")
        self.holder.Length = 1
        self.other = self.doc.addObject("App::VarSet", "Other")
        self.other.addProperty("App::PropertyLength", "Target", "Base")
        self.widget = QtWidgets.QWidget(Gui.getMainWindow())
        layout = QtWidgets.QVBoxLayout(self.widget)
        self.spin = Gui.UiLoader().createWidget("Gui::QuantitySpinBox")
        layout.addWidget(self.spin)
        self.widget.show()
        self.dialog = None

    def tearDown(self):
        if self.dialog is not None:
            try:
                self.dialog.reject()
            except RuntimeError:
                pass
        self.widget.close()
        self.widget.deleteLater()
        App.closeDocument(self.doc.Name)
        Gui.updateGui()

    def bind(self, obj, prop, editor=None):
        editor = editor or self.spin
        editor.setProperty("unit", "mm")
        editor.setProperty("binding", self.doc.Name + "#" + obj.Name + "." + prop)
        self.assertTrue(editor.property("binding"))
        return editor

    def openDialog(self, editor=None):
        editor = editor or self.spin
        icons = [w for w in editor.findChildren(QtWidgets.QLabel) if w.inherits("ExpressionLabel")]
        self.assertEqual(len(icons), 1)
        self.assertTrue(QtCore.QMetaObject.invokeMethod(icons[0], "clicked",
                                                        QtCore.Qt.DirectConnection))
        Gui.updateGui()
        self.dialog = editor.findChild(QtWidgets.QDialog, "DlgExpressionInput")
        self.assertIsNotNone(self.dialog)
        return self.dialog.findChild(QtWidgets.QPlainTextEdit, "expression")

    def okButton(self):
        return self.dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox").button(
            QtWidgets.QDialogButtonBox.Ok)

    def acceptDialog(self):
        button = self.okButton()
        self.assertTrue(button.isEnabled())
        button.click()
        Gui.updateGui()
        self.dialog = None

    def expressions(self, obj):
        return dict(obj.ExpressionEngine)

    def lineEdit(self, editor=None):
        return (editor or self.spin).findChild(QtWidgets.QLineEdit)

    def parameters(self):
        """The object holding the user parameters of the document, None when it has none."""
        return self.doc.getObject("UserParameters")

    def commitText(self, text, editor=None):
        """Commit @p text in a field, as pasted and confirmed with Return."""
        editor = editor or self.spin
        editor.setFocus()
        self.lineEdit(editor).setText(text)
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        Gui.updateGui()

    def reopen(self, withViewProperties=True):
        """Save the document and open it again, optionally as saved without the GUI."""
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "UserParametersGui.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        if not withViewProperties:
            saved = path
            path = os.path.join(folder, "UserParametersApp.FCStd")
            with zipfile.ZipFile(saved) as source:
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
                    for item in source.infolist():
                        if item.filename != "GuiDocument.xml":
                            target.writestr(item, source.read(item.filename))
        self.doc = App.openDocument(path)
        Gui.updateGui()

    def test_dialog_assignment_creates_parameter_and_binds(self):
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = 23 mm")
        Gui.updateGui()
        self.acceptDialog()
        parameters = self.parameters()
        self.assertIsNotNone(parameters)
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertEqual(parameters.getGroupOfProperty("myVar"), "UserParameters")
        self.assertAlmostEqual(parameters.myVar.Value, 23.0)
        self.assertEqual(self.expressions(self.holder)["Length"], "UserParameters.myVar")
        self.doc.recompute()
        self.assertAlmostEqual(self.holder.Length.Value, 23.0)

    def test_dialog_assignment_is_one_undo_step(self):
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = 23 mm")
        Gui.updateGui()
        undo_count = len(self.doc.UndoNames)
        self.acceptDialog()
        self.assertEqual(len(self.doc.UndoNames), undo_count + 1, self.doc.UndoNames)
        self.doc.undo()
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertIsNone(self.parameters())
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_dialog_cancel_creates_nothing(self):
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = 23 mm")
        Gui.updateGui()
        self.assertTrue(self.okButton().isEnabled())
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertIsNone(self.parameters())
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_dialog_assignment_whose_binding_fails_leaves_no_parameter(self):
        # myVar = Length * 2 is valid, binding Length to myVar is a cycle
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = Length * 2")
        Gui.updateGui()
        self.dialog.accept()  # even if the dialog would refuse it up front
        Gui.updateGui()
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_dialog_resolves_parameter_of_other_object_and_shows_short_name(self):
        self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.bind(self.other, "Target")
        self.openDialog().setPlainText("2 * myVar")
        Gui.updateGui()
        self.acceptDialog()
        self.assertEqual(self.expressions(self.other)["Target"], "2 * UserParameters.myVar")
        self.assertIn(self.parameters(), self.other.OutList)
        # Reopening shows the name as typed.
        self.assertEqual(self.openDialog().toPlainText(), "2 * myVar")

    def test_dialog_refuses_taken_name(self):
        self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.bind(self.other, "Target")
        self.openDialog().setPlainText("myVar = 3 mm")
        Gui.updateGui()
        self.assertFalse(self.okButton().isEnabled())
        self.assertNotIn("myVar", self.other.PropertiesList)

    def test_dialog_prefills_assignment_after_typed_name(self):
        self.bind(self.other, "Target")
        edit = self.lineEdit()
        edit.setText("width")
        self.assertEqual(self.openDialog().toPlainText(), "width = ")

    def test_typing_name_then_equal_continues_in_dialog(self):
        self.bind(self.other, "Target")
        self.spin.setFocus()
        self.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin, "width")
        QtTest.QTest.keyClicks(self.spin, "=")
        Gui.updateGui()
        self.dialog = self.spin.findChild(QtWidgets.QDialog, "DlgExpressionInput")
        self.assertIsNotNone(self.dialog)
        text = self.dialog.findChild(QtWidgets.QPlainTextEdit, "expression")
        self.assertEqual(text.toPlainText(), "width = ")
        QtTest.QTest.keyClicks(text, "7 mm")
        Gui.updateGui()
        self.acceptDialog()
        self.assertEqual(self.parameters().getGroupOfProperty("width"), "UserParameters")
        self.assertEqual(self.expressions(self.other).get("Target"), "UserParameters.width")

    def test_dialog_keeps_cursor_after_prefilled_assignment(self):
        # The value is typed next: a selected `width = ` would be replaced by it.
        self.bind(self.other, "Target")
        self.lineEdit().setText("width")
        text = self.openDialog()
        self.assertEqual(text.toPlainText(), "width = ")
        cursor = text.textCursor()
        self.assertFalse(cursor.hasSelection())
        self.assertEqual(cursor.position(), len("width = "))

    def test_dialog_selects_input_that_is_not_an_assignment(self):
        self.bind(self.other, "Target")
        self.lineEdit().setText("5 mm")
        text = self.openDialog()
        self.assertEqual(text.toPlainText(), "5 mm")
        self.assertEqual(text.textCursor().selectedText(), "5 mm")

    def test_text_field_does_not_start_an_assignment(self):
        # The text of a string property is a value, not the name of a new parameter: its formula
        # dialog shows it unchanged (accepting `Steel = 5` would bind the text to a parameter).
        self.holder.addProperty("App::PropertyString", "Material", "Base")
        self.holder.Material = "Steel"
        edit = Gui.UiLoader().createWidget("Gui::ExpLineEdit")
        self.widget.layout().addWidget(edit)
        Gui.ExpressionBinding(edit).bind(self.holder, "Material")
        edit.setText("Steel")
        text = self.openDialog(edit)
        self.assertEqual(text.toPlainText(), "Steel")
        self.assertEqual(text.textCursor().selectedText(), "Steel")
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertNotIn("Steel", self.holder.PropertiesList)
        self.assertNotIn("Material", self.expressions(self.holder))

    def typeUncommittedValue(self):
        """Type `7 mm` in a field that commits when the editing ends (no keyboard tracking)."""
        self.spin.setProperty("unit", "mm")
        self.spin.setProperty("keyboardTracking", False)
        self.spin.setFocus()
        self.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin, "7 mm")
        self.assertEqual(self.lineEdit().text(), "7 mm")
        self.assertAlmostEqual(self.spin.property("rawValue"), 0.0)

    def popupTakesFocus(self, popup):
        """Tell the field that @p popup, which is shown, took the focus."""
        Gui.updateGui()
        self.assertEqual(QtWidgets.QApplication.activePopupWidget(), popup)
        # Qt sends this event to the widget that has the focus when a popup opens. It is sent
        # here as well, for the test not to depend on the test window being the active one.
        event = QtGui.QFocusEvent(QtCore.QEvent.FocusOut, QtCore.Qt.PopupFocusReason)
        QtWidgets.QApplication.sendEvent(self.spin, event)
        Gui.updateGui()

    def test_foreign_popup_commits_typed_value(self):
        # A menu of the main window runs a command: it must see the value that was typed.
        self.typeUncommittedValue()
        menu = QtWidgets.QMenu(Gui.getMainWindow())
        menu.addAction("Command")
        try:
            menu.popup(self.spin.mapToGlobal(QtCore.QPoint(0, self.spin.height())))
            self.popupTakesFocus(menu)
            self.assertAlmostEqual(self.spin.property("rawValue"), 7.0)
        finally:
            menu.hide()
            menu.deleteLater()

    def test_context_menu_of_field_keeps_input_in_edit(self):
        self.typeUncommittedValue()
        menu = QtWidgets.QMenu(self.lineEdit())  # as QLineEdit::createStandardContextMenu()
        menu.addAction("Paste")
        try:
            menu.popup(self.spin.mapToGlobal(QtCore.QPoint(0, self.spin.height())))
            self.popupTakesFocus(menu)
            self.assertAlmostEqual(self.spin.property("rawValue"), 0.0)
            self.assertEqual(self.lineEdit().text(), "7 mm")
        finally:
            menu.hide()
            menu.deleteLater()

    def test_completer_popup_of_field_keeps_input_in_edit(self):
        self.typeUncommittedValue()
        completer = QtWidgets.QCompleter(["7 mm"], self.spin)
        completer.setWidget(self.lineEdit())
        completer.setCompletionPrefix("7")
        try:
            completer.complete()
            self.popupTakesFocus(completer.popup())
            self.assertAlmostEqual(self.spin.property("rawValue"), 0.0)
            self.assertEqual(self.lineEdit().text(), "7 mm")
        finally:
            completer.popup().hide()

    def test_opening_dialog_does_not_bind_typed_input(self):
        # `=` after `2*myVar` opens the dialog, which takes the focus: the focus-out must not
        # bind the field (Cancel of the dialog would leave the binding).
        self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.bind(self.other, "Target")
        self.spin.setFocus()
        self.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin, "2*myVar")
        QtTest.QTest.keyClicks(self.spin, "=")
        Gui.updateGui()
        self.dialog = self.spin.findChild(QtWidgets.QDialog, "DlgExpressionInput")
        self.assertIsNotNone(self.dialog)
        self.dialog.activateWindow()
        Gui.updateGui()
        self.assertNotIn("Target", self.expressions(self.other))
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertNotIn("Target", self.expressions(self.other))

    def test_spinbox_binds_input_naming_a_parameter(self):
        self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.bind(self.other, "Target")
        self.spin.setFocus()
        self.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin, "2*myVar")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertEqual(self.expressions(self.other).get("Target"), "2 * UserParameters.myVar")

    def test_spinbox_assignment_from_pasted_text(self):
        self.bind(self.other, "Target")
        rejected = []
        QtCore.QObject.connect(
            self.spin,
            QtCore.SIGNAL("inputRejected(QString,int,int)"),
            lambda message, start, length: rejected.append(message),
        )
        self.spin.setFocus()
        self.lineEdit().setText("w = 5 mm")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertEqual(self.parameters().getGroupOfProperty("w"), "UserParameters")
        self.assertEqual(self.expressions(self.other).get("Target"), "UserParameters.w")
        # no error after a successful commit (the nested validation parsed `w = 5 mm`)
        self.assertEqual(rejected, [])
        self.assertFalse(self.lineEdit().property("numericInputInvalid"))
        self.doc.undo()
        self.assertNotIn("w", self.other.PropertiesList)
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertNotIn("Target", self.expressions(self.other))

    def test_first_assignment_creates_holder_hidden_in_tree(self):
        self.assertIsNone(self.parameters())
        self.bind(self.other, "Target")
        self.commitText("w = 5 mm")
        parameters = self.parameters()
        self.assertIsNotNone(parameters)
        self.assertEqual(parameters.TypeId, "App::VarSet")
        self.assertEqual(parameters.Label, "User Parameters")
        self.assertFalse(parameters.ViewObject.ShowInTree)
        self.assertEqual(self.doc.getUserParameters(), [(parameters, "w")])
        # The holder is created with its first parameter: undoing the input removes both.
        self.doc.undo()
        self.assertIsNone(self.parameters())
        self.assertEqual(self.doc.getUserParameters(), [])
        self.doc.redo()
        parameters = self.parameters()
        self.assertIsNotNone(parameters)
        self.assertFalse(parameters.ViewObject.ShowInTree)
        self.assertEqual(self.doc.getUserParameters(), [(parameters, "w")])

    def test_second_parameter_reuses_holder(self):
        self.bind(self.other, "Target")
        self.commitText("depth = 1 mm")
        parameters = self.parameters()
        self.assertIsNotNone(parameters)
        # The user shows the holder in the tree: creating a parameter does not hide it again.
        parameters.ViewObject.ShowInTree = True
        second = Gui.UiLoader().createWidget("Gui::QuantitySpinBox")
        self.widget.layout().addWidget(second)
        self.bind(self.holder, "Length", second)
        self.commitText("height = 2 mm", second)
        found = self.doc.getUserParameters()
        self.assertEqual(sorted(name for _, name in found), ["depth", "height"])
        self.assertEqual([obj for obj, _ in found], [parameters, parameters])
        self.assertEqual(
            [obj.Name for obj in self.doc.Objects if obj.Name.startswith("UserParameters")],
            ["UserParameters"],
        )
        self.assertEqual(self.expressions(self.holder).get("Length"), "UserParameters.height")
        self.assertTrue(parameters.ViewObject.ShowInTree)
        # Undoing the second parameter leaves the holder with the first one.
        self.doc.undo()
        self.assertEqual(self.doc.getUserParameters(), [(self.parameters(), "depth")])

    def test_holder_created_by_script_is_hidden_in_tree(self):
        self.doc.addUserParameter(self.other, "w", "5 mm")
        self.assertFalse(self.parameters().ViewObject.ShowInTree)

    def test_reopened_document_keeps_choice_to_show_holder(self):
        self.doc.addUserParameter(self.other, "w", "5 mm")
        self.reopen()
        self.assertFalse(self.parameters().ViewObject.ShowInTree)
        self.parameters().ViewObject.ShowInTree = True
        self.reopen()
        self.assertTrue(self.parameters().ViewObject.ShowInTree)

    def test_holder_of_document_saved_without_gui_is_hidden_in_tree(self):
        # No view properties are saved without the GUI: the holder is new to it.
        self.doc.addUserParameter(self.other, "w", "5 mm")
        self.parameters().ViewObject.ShowInTree = True
        self.reopen(withViewProperties=False)
        self.assertFalse(self.parameters().ViewObject.ShowInTree)

    def assert_spinbox_failed_binding_leaves_no_parameter(self):
        # myVar = Length * 2 is valid, binding Length to myVar is a cycle
        self.bind(self.holder, "Length")
        self.spin.setFocus()
        self.lineEdit().setText("myVar = Length * 2")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_spinbox_failed_binding_leaves_no_parameter(self):
        self.assert_spinbox_failed_binding_leaves_no_parameter()
        # The transaction of the input is aborted: the holder created for it is gone as well.
        self.assertIsNone(self.parameters())

    def test_spinbox_failed_binding_in_open_transaction_leaves_no_parameter(self):
        # as in a task dialog: its booked transaction is used and stays open, so nothing is
        # aborted and the parameter must be removed explicitly
        self.doc.openTransaction("Task")
        try:
            self.assert_spinbox_failed_binding_leaves_no_parameter()
        finally:
            self.doc.abortTransaction()

    def test_dialog_failed_binding_in_open_transaction_leaves_no_parameter(self):
        self.doc.openTransaction("Task")
        try:
            self.test_dialog_assignment_whose_binding_fails_leaves_no_parameter()
        finally:
            self.doc.abortTransaction()

    def test_spinbox_plain_values_are_unchanged(self):
        self.bind(self.other, "Target")
        self.spin.setFocus()
        self.lineEdit().selectAll()
        QtTest.QTest.keyClicks(self.spin, "2*3 mm")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertNotIn("Target", self.expressions(self.other))
        self.assertEqual(self.doc.getUserParameters(), [])
        self.assertIsNone(self.parameters())
