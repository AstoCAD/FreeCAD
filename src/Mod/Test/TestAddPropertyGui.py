# SPDX-License-Identifier: LGPL-2.1-or-later

"""Regression coverage for values committed by the Add Property dialog."""

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
