# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI tests for quick user-parameter input (`myVar = 23 mm`) in expression-capable fields.

A bound Gui::QuantitySpinBox (as in task panels, the property editor and the Sketcher datum
dialog) and its formula dialog create the parameter in the group 'UserParameters' of the owner
of the bound property; `myVar` typed for another object resolves to that parameter.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestUserParametersGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("UserParametersGui")
        self.doc.UndoMode = 1
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

    def test_dialog_assignment_creates_parameter_and_binds(self):
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = 23 mm")
        Gui.updateGui()
        self.acceptDialog()
        self.assertIn("myVar", self.holder.PropertiesList)
        self.assertEqual(self.holder.getGroupOfProperty("myVar"), "UserParameters")
        self.assertAlmostEqual(self.holder.myVar.Value, 23.0)
        self.assertEqual(self.expressions(self.holder)["Length"], "myVar")
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
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_dialog_assignment_whose_binding_fails_leaves_no_parameter(self):
        # myVar = Length * 2 is valid, binding Length to myVar is a cycle
        self.bind(self.holder, "Length")
        self.openDialog().setPlainText("myVar = Length * 2")
        Gui.updateGui()
        self.dialog.accept()  # even if the dialog would refuse it up front
        Gui.updateGui()
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_dialog_resolves_parameter_of_other_object_and_shows_short_name(self):
        self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.bind(self.other, "Target")
        self.openDialog().setPlainText("2 * myVar")
        Gui.updateGui()
        self.acceptDialog()
        self.assertEqual(self.expressions(self.other)["Target"], "2 * Holder.myVar")
        self.assertIn(self.holder, self.other.OutList)
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
        self.assertEqual(self.other.getGroupOfProperty("width"), "UserParameters")
        self.assertEqual(self.expressions(self.other).get("Target"), "width")

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
        self.assertEqual(self.expressions(self.other).get("Target"), "2 * Holder.myVar")

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
        self.assertEqual(self.other.getGroupOfProperty("w"), "UserParameters")
        self.assertEqual(self.expressions(self.other).get("Target"), "w")
        # no error after a successful commit (the nested validation parsed `w = 5 mm`)
        self.assertEqual(rejected, [])
        self.assertFalse(self.lineEdit().property("numericInputInvalid"))
        self.doc.undo()
        self.assertNotIn("w", self.other.PropertiesList)

    def assert_spinbox_failed_binding_leaves_no_parameter(self):
        # myVar = Length * 2 is valid, binding Length to myVar is a cycle
        self.bind(self.holder, "Length")
        self.spin.setFocus()
        self.lineEdit().setText("myVar = Length * 2")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertNotIn("myVar", self.holder.PropertiesList)
        self.assertNotIn("Length", self.expressions(self.holder))

    def test_spinbox_failed_binding_leaves_no_parameter(self):
        self.assert_spinbox_failed_binding_leaves_no_parameter()

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
