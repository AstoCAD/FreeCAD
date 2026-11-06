# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: the parameter editor keeps all digits of float values.

A float item showed its value with 6 significant digits, and the editor reads
the value back from that text: a new float item was stored rounded, and
"Change value" proposed (and on OK stored) the rounded number.

To run tests:
    FreeCAD -t TestParameterEditorFloatGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

GROUP = "ParameterEditorFloatTest"
VALUE = 1234.5678


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestParameterEditorFloatGui(unittest.TestCase):
    def setUp(self):
        self.results = {}
        self.errors = []
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences")
        self.assertNotIn(GROUP, self.preferences.GetGroups())
        self.editor = App.ParamGet("User parameter:BaseApp/Preferences/ParameterEditor")
        self.had_last = "LastParameterGroup" in self.editor.GetStrings()
        self.last = self.editor.GetString("LastParameterGroup")
        self.addCleanup(self._restore)
        App.ParamGet("User parameter:BaseApp/Preferences/" + GROUP).SetFloat("Value", VALUE)
        # the editor opens on the group selected last time
        self.editor.SetString("LastParameterGroup", "BaseApp.Preferences." + GROUP)

    def _restore(self):
        self.preferences.RemGroup(GROUP)
        if self.had_last:
            self.editor.SetString("LastParameterGroup", self.last)
        else:
            self.editor.RemString("LastParameterGroup")

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            values = [
                widget
                for widget in dialog.findChildren(QtWidgets.QTreeWidget)
                if widget.metaObject().className() == "Gui::Dialog::ParameterValue"
            ]
            if len(values) != 1:
                self.errors.append("value list not found")
                return
            items = [
                values[0].topLevelItem(index)
                for index in range(values[0].topLevelItemCount())
                if values[0].topLevelItem(index).text(0) == "Value"
            ]
            if len(items) != 1:
                self.errors.append("float item not found")
                return
            self.results["text"] = items[0].text(2)
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testFloatItemShowsAllDigits(self):
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.runCommand("Std_DlgParameter", 0)
        self.assertEqual(self.errors, [])
        self.assertEqual(float(self.results["text"]), VALUE, self.results["text"])
