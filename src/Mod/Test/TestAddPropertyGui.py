# SPDX-License-Identifier: LGPL-2.1-or-later

"""Regression coverage for values committed by the Add Property dialog."""

import ast
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets


class TestAddPropertyGui(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/PropertyView")
        strings = self.preferences.GetStrings()
        self.previous_preferences = {
            key: self.preferences.GetString(key) if key in strings else None
            for key in ("NewPropertyType", "NewPropertyGroup")
        }
        self.doc = App.newDocument("TestAddPropertyGui")
        self.varset = self.doc.addObject("App::VarSet", "VarSet")
        self.varset.ViewObject.doubleClicked()
        Gui.updateGui()
        self.dialog = QtWidgets.QApplication.activeModalWidget()
        self.assertIsNotNone(self.dialog, "The VarSet property dialog did not open")

    def tearDown(self):
        try:
            if self.dialog is not None:
                self.dialog.reject()
                self.dialog = None
                Gui.updateGui()
        finally:
            App.closeDocument(self.doc.Name)
            for key, value in self.previous_preferences.items():
                if value is None:
                    self.preferences.RemString(key)
                else:
                    self.preferences.SetString(key, value)

    def widget(self, widget_type, name):
        widget = self.dialog.findChild(widget_type, name)
        self.assertIsNotNone(widget, name)
        return widget

    def prepareProperty(self, property_type, name):
        self.widget(QtWidgets.QComboBox, "comboBoxType").setCurrentText(property_type)
        self.widget(QtWidgets.QLineEdit, "lineEditName").setText(name)
        Gui.updateGui()

    def typeString(self, value):
        editor = self.widget(QtWidgets.QLineEdit, "editor")
        editor.setFocus()
        editor.selectAll()
        editor.insert(value)
        Gui.updateGui()
        self.assertEqual(editor.text(), value)

    def addProperty(self):
        box = self.widget(QtWidgets.QDialogButtonBox, "buttonBox")
        button = box.button(QtWidgets.QDialogButtonBox.Ok)
        self.assertTrue(button.isEnabled())
        # Exercise Add without relying on an editor focus-out to flush its value.
        button.click()
        Gui.updateGui()
        self.doc.recompute()
        self.assertEqual(self.widget(QtWidgets.QLineEdit, "lineEditName").text(), "")

    def testAddStoresAsciiString(self):
        self.prepareProperty("App::PropertyString", "Words")
        self.typeString("A typed property value")
        self.addProperty()
        self.assertEqual(self.varset.Words, "A typed property value")

    def testAddStoresUnicodeString(self):
        self.prepareProperty("App::PropertyString", "Words")
        expected = "Hello \u6f22\u5b57 \u00fc"
        self.typeString(expected)
        self.addProperty()
        self.assertEqual(self.varset.Words, expected)

    def testRenameKeepsTypedString(self):
        self.prepareProperty("App::PropertyString", "Words")
        self.typeString("Keep this while renaming")
        self.widget(QtWidgets.QLineEdit, "lineEditName").setText("RenamedWords")
        Gui.updateGui()
        self.addProperty()
        self.assertNotIn("Words", self.varset.PropertiesList)
        self.assertEqual(self.varset.RenamedWords, "Keep this while renaming")

    def testCancelDiscardsPendingString(self):
        self.prepareProperty("App::PropertyString", "PendingWords")
        self.typeString("Discard this value")
        self.assertIn("PendingWords", self.varset.PropertiesList)
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertNotIn("PendingWords", self.varset.PropertiesList)

    def testNumericEditorStillAddsValue(self):
        self.prepareProperty("App::PropertyInteger", "Count")
        self.widget(QtWidgets.QSpinBox, "editor").setValue(37)
        self.addProperty()
        self.assertEqual(self.varset.Count, 37)

    def testRecordedCommandHasFinalGroupAndToolTip(self):
        # The macro command was built when the name was typed, so a group or a tooltip
        # entered afterwards was missing from it, and a quote in the tooltip broke it
        console = Gui.getMainWindow().findChild(QtWidgets.QPlainTextEdit, "Python console")
        if console is None:
            self.skipTest("The Python console is hidden")
        macro = App.ParamGet("User parameter:BaseApp/Preferences/Macro")
        previous = None
        if "ScriptToPyConsole" in macro.GetBools():
            previous = macro.GetBool("ScriptToPyConsole")
        macro.SetBool("ScriptToPyConsole", True)
        try:
            self.prepareProperty("App::PropertyString", "Remark")
            self.widget(QtWidgets.QComboBox, "comboBoxGroup").setCurrentText("AuditNotes")
            self.widget(QtWidgets.QLineEdit, "lineEditToolTip").setText("Bob's \"remark\"")
            Gui.updateGui()
            self.typeString("Recorded")
            self.addProperty()
        finally:
            if previous is None:
                macro.RemBool("ScriptToPyConsole")
            else:
                macro.SetBool("ScriptToPyConsole", previous)
        self.assertEqual(self.varset.getGroupOfProperty("Remark"), "AuditNotes")
        self.assertEqual(self.varset.getDocumentationOfProperty("Remark"), "Bob's \"remark\"")

        lines = [
            line.split(">>> ", 1)[-1]
            for line in console.toPlainText().splitlines()
            if ".addProperty('App::PropertyString', 'Remark'" in line
        ]
        self.assertTrue(lines, "The added property was not recorded")
        call = ast.parse(lines[-1]).body[0].value
        args = [ast.literal_eval(arg) for arg in call.args]
        self.assertEqual(args, ["App::PropertyString", "Remark", "AuditNotes", "Bob's \"remark\""])

    def testRecordedCommandForTypeWithoutEditor(self):
        # A type without a property editor item has no propertyItem in the dialog:
        # its addProperty line must still be recorded
        console = Gui.getMainWindow().findChild(QtWidgets.QPlainTextEdit, "Python console")
        if console is None:
            self.skipTest("The Python console is hidden")
        macro = App.ParamGet("User parameter:BaseApp/Preferences/Macro")
        previous = None
        if "ScriptToPyConsole" in macro.GetBools():
            previous = macro.GetBool("ScriptToPyConsole")
        macro.SetBool("ScriptToPyConsole", True)
        try:
            self.prepareProperty("App::PropertyIntPairList", "Pairs")
            self.assertIn("Pairs", self.varset.PropertiesList)
            self.addProperty()
        finally:
            if previous is None:
                macro.RemBool("ScriptToPyConsole")
            else:
                macro.SetBool("ScriptToPyConsole", previous)
        lines = [
            line.split(">>> ", 1)[-1]
            for line in console.toPlainText().splitlines()
            if ".addProperty('App::PropertyIntPairList', 'Pairs'" in line
        ]
        self.assertTrue(lines, "The added property was not recorded")
        call = ast.parse(lines[-1]).body[0].value
        args = [ast.literal_eval(arg) for arg in call.args]
        self.assertEqual(args[:2], ["App::PropertyIntPairList", "Pairs"])
        self.assertEqual(args[2], self.varset.getGroupOfProperty("Pairs"))

    def testStringExpressionSurvivesAdd(self):
        self.prepareProperty("App::PropertyString", "ExpressionWords")
        expression = "<<Bound text>>"
        self.varset.setExpression("ExpressionWords", expression)
        self.doc.recompute()
        Gui.updateGui()
        self.assertEqual(self.varset.ExpressionWords, "Bound text")
        self.addProperty()
        self.assertEqual(self.varset.ExpressionWords, "Bound text")
        self.assertEqual(dict(self.varset.ExpressionEngine)["ExpressionWords"], expression)
