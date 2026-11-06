# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for immediate Store-in-VarSet values.

These inspect the new property before any document recompute or sketch closure,
then check that the expression remains live. The Fx dialog is the actual C++
dialog opened by a bound QuantitySpinBox, as in a Sketcher datum editor.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestExpressionVarSetGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("StoreVariableExpressionValue")
        self.doc.UndoMode = 1
        self.variables = self.doc.addObject("App::VarSet", "Variables")
        self.variables.addProperty("App::PropertyLength", "Length", "Variables")
        self.variables.Length = 20
        self.variables.addProperty("App::PropertyFloat", "Factor", "Variables")
        self.variables.Factor = 2
        self.variables.addProperty("App::PropertyInteger", "Count", "Variables")
        self.variables.Count = 4
        self.holder = QtWidgets.QWidget(Gui.getMainWindow())
        layout = QtWidgets.QVBoxLayout(self.holder)
        self.spin = Gui.UiLoader().createWidget("Gui::QuantitySpinBox")
        layout.addWidget(self.spin)
        self.dialog = None
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/ExpressionEditor")
        keys = set(self.preferences.GetStrings())
        self.old_preferences = {key: self.preferences.GetString(key) if key in keys else None
                                for key in ("LastDocument", "LastVarSet", "LastGroup")}
        self.preferences.SetString("LastDocument", self.doc.Name)
        self.preferences.SetString("LastVarSet", self.variables.Name)
        self.preferences.SetString("LastGroup", "Variables")

    def tearDown(self):
        if self.dialog is not None:
            try:
                self.dialog.reject()
            except RuntimeError:
                pass
        Gui.activeDocument().resetEdit()
        Gui.Selection.clearSelection()
        self.holder.close()
        self.holder.deleteLater()
        App.closeDocument(self.doc.Name)
        for key, value in self.old_preferences.items():
            if value is None:
                self.preferences.RemString(key)
            else:
                self.preferences.SetString(key, value)
        Gui.updateGui()

    def store(self, source, path, unit, expression, variable, editor=None, cancel=False):
        if editor is None:
            editor = self.spin
            editor.setProperty("unit", unit)
            editor.setProperty("binding", self.doc.Name + "#" + source.Name + "." + path)
            self.assertTrue(editor.property("binding"))
        icons = [widget for widget in editor.findChildren(QtWidgets.QLabel)
                 if widget.inherits("ExpressionLabel")]
        self.assertEqual(len(icons), 1)
        self.assertTrue(QtCore.QMetaObject.invokeMethod(
            icons[0], "clicked", QtCore.Qt.DirectConnection))
        Gui.updateGui()
        self.dialog = editor.findChild(QtWidgets.QDialog, "DlgExpressionInput")
        self.assertIsNotNone(self.dialog)
        self.dialog.findChild(QtWidgets.QPlainTextEdit, "expression").setPlainText(expression)
        enabled = self.dialog.findChild(QtWidgets.QCheckBox, "checkBoxVarSets")
        self.assertFalse(enabled.isHidden())
        enabled.setChecked(True)
        combo = self.dialog.findChild(QtWidgets.QComboBox, "comboBoxVarSet")
        candidates = [index for index in range(combo.count())
                      if combo.itemData(index, QtCore.Qt.UserRole + 1) == self.variables.Name]
        self.assertEqual(len(candidates), 1)
        combo.setCurrentIndex(candidates[0])
        self.dialog.findChild(QtWidgets.QComboBox, "comboBoxGroup").setCurrentText("Variables")
        self.dialog.findChild(QtWidgets.QLineEdit, "lineEditPropNew").setText(variable)
        Gui.updateGui()
        button = self.dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox").button(
            QtWidgets.QDialogButtonBox.Ok)
        self.assertTrue(button.isEnabled())
        if cancel:
            self.dialog.reject()
            self.dialog = None
            return None
        accepted = []
        self.dialog.accepted.connect(lambda: accepted.append(True))
        button.click()
        self.assertTrue(accepted, "Valid Store-in-VarSet expression must be accepted")
        self.dialog = None
        self.assertIn(variable, self.variables.PropertiesList)
        value = getattr(self.variables, variable)
        return value.Value if hasattr(value, "Value") else value

    def valueSource(self, name="Scale", property_type="App::PropertyFloat", value=3):
        source = self.doc.addObject("App::FeaturePython", "Source")
        source.addProperty(property_type, name)
        setattr(source, name, value)
        return source

    @staticmethod
    def propertyIndex(model, name, parent=QtCore.QModelIndex()):
        for row in range(model.rowCount(parent)):
            label = model.index(row, 0, parent)
            if model.data(label, QtCore.Qt.DisplayRole) == name:
                return model.index(row, 1, parent)
            index = TestExpressionVarSetGui.propertyIndex(model, name, label)
            if index.isValid():
                return index
        return QtCore.QModelIndex()

    def stringEditor(self, source):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source)
        for _ in range(40):
            Gui.updateGui()
            for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeView, "propertyEditorData"):
                model = tree.model()
                index = self.propertyIndex(model, "Text")
                label = self.propertyIndex(model, "Label")
                if (index.isValid() and label.isValid()
                        and model.data(label, QtCore.Qt.EditRole) == source.Label):
                    tree.expandAll()
                    tree.setCurrentIndex(index)
                    tree.edit(index)
                    Gui.updateGui()
                    editors = [widget for widget in tree.findChildren(QtWidgets.QLineEdit)
                               if widget.inherits("Gui::ExpLineEdit")]
                    self.assertEqual(len(editors), 1)
                    return editors[0]
            QtTest.QTest.qWait(50)
        self.fail("Selected object's real string property editor did not open")

    def sketch(self, radius=False):
        try:
            import Part
            import Sketcher
        except ImportError as error:
            self.skipTest(str(error))
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        if radius:
            sketch.addGeometry(Part.Circle(App.Vector(), App.Vector(0, 0, 1), 5), False)
            sketch.addConstraint(Sketcher.Constraint("Radius", 0, 5))
        else:
            sketch.addGeometry(Part.LineSegment(App.Vector(), App.Vector(20, 0, 0)), False)
            sketch.addConstraint(Sketcher.Constraint("Distance", 0, 20))
        self.doc.recompute()
        self.assertTrue(Gui.activeDocument().setEdit(sketch.Name))
        return sketch

    def storeFromSketchDatumEditor(self, sketch):
        errors = []
        handled = []
        timer = QtCore.QTimer(self.holder)

        def editDatum():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                return
            timer.stop()
            handled.append(True)
            try:
                editor = dialog.findChild(QtWidgets.QWidget, "labelEdit")
                self.assertIsNotNone(editor, "The ordinary Sketcher datum dialog must open")
                self.assertTrue(editor.property("binding"),
                                "Use the datum editor's existing C++ constraint binding")
                self.assertAlmostEqual(self.store(
                    sketch, "Constraints[0]", "mm", "<<Variables>>.Length / 2", "HalfLength",
                    editor=editor), 10)
                self.assertAlmostEqual(editor.property("rawValue"), 10)
                self.assertIsNotNone(Gui.activeDocument().getInEdit())
                buttons = dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
                self.assertIsNotNone(buttons)
                buttons.button(QtWidgets.QDialogButtonBox.Ok).click()
            except BaseException as error:
                errors.append(error)
                if self.dialog is not None:
                    try:
                        self.dialog.reject()
                    except RuntimeError:
                        pass
                    self.dialog = None
                dialog.reject()

        timer.timeout.connect(editDatum)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, sketch.Name, "Constraint1")
        timer.start(25)
        try:
            Gui.runCommand("Sketcher_ChangeDimensionConstraint", 0)
        finally:
            timer.stop()
            timer.deleteLater()
        if errors:
            raise errors[0]
        self.assertTrue(handled, "Edit Value must run the ordinary native datum editor")

    def checkLiveHalfLength(self, sketch):
        self.storeFromSketchDatumEditor(sketch)
        self.assertIsNotNone(Gui.activeDocument().getInEdit())
        self.assertIn("HalfLength", dict(self.variables.ExpressionEngine))
        self.assertTrue(any("HalfLength" in expression for _path, expression
                            in sketch.ExpressionEngine))
        self.assertAlmostEqual(sketch.Constraints[0].Value, 10)
        geometry = sketch.Geometry[0]
        if hasattr(geometry, "Radius"):
            self.assertAlmostEqual(geometry.Radius, 10)
        else:
            self.assertAlmostEqual((geometry.EndPoint - geometry.StartPoint).Length, 10)
        self.variables.Length = 24
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.HalfLength.Value, 12)

    def testSketchLengthExpressionImmediate(self):
        self.checkLiveHalfLength(self.sketch())

    def testSketchRadiusExpressionImmediate(self):
        self.checkLiveHalfLength(self.sketch(radius=True))

    def testFloatExpressionImmediate(self):
        source = self.doc.addObject("App::FeaturePython", "Source")
        source.addProperty("App::PropertyFloat", "Scale")
        source.Scale = 3
        self.doc.recompute()
        self.assertAlmostEqual(self.store(source, "Scale", "",
                                         "<<Variables>>.Factor * 1.5", "Scale"), 3)
        self.assertIn("Scale", dict(self.variables.ExpressionEngine))
        self.variables.Factor = 4
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.Scale, 6)

    def testIntegerExpressionImmediate(self):
        source = self.doc.addObject("App::FeaturePython", "Source")
        source.addProperty("App::PropertyInteger", "Amount")
        source.Amount = 6
        self.doc.recompute()
        self.assertEqual(self.store(source, "Amount", "",
                                    "<<Variables>>.Count + 2", "Amount"), 6)
        self.assertIn("Amount", dict(self.variables.ExpressionEngine))
        self.variables.Count = 8
        self.doc.recompute()
        self.assertEqual(self.variables.Amount, 10)

    def testLengthLiteralImmediateControl(self):
        try:
            import Part
        except ImportError as error:
            self.skipTest(str(error))
        source = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.assertAlmostEqual(self.store(source, "Length", "mm", "10 mm", "HalfLength"), 10)
        self.assertNotIn("HalfLength", dict(self.variables.ExpressionEngine))

    def testFloatLiteralImmediateControl(self):
        source = self.doc.addObject("App::FeaturePython", "Source")
        source.addProperty("App::PropertyFloat", "Scale")
        source.Scale = 3
        self.doc.recompute()
        self.assertAlmostEqual(self.store(source, "Scale", "", "3.5", "Scale"), 3.5)
        self.assertNotIn("Scale", dict(self.variables.ExpressionEngine))

    def testFloatLiteralKeepsAllDigits(self):
        # the value was recorded with "%f": 6 decimals only
        source = self.valueSource()
        self.doc.recompute()
        self.assertAlmostEqual(self.store(source, "Scale", "", "1.23456789", "Precise"), 1.23456789,
                               places=12)
        self.assertAlmostEqual(self.store(source, "Scale", "", "0.0000001", "Tiny"), 1e-7,
                               places=12)

    def testReferencedVariableChain(self):
        self.variables.addProperty("App::PropertyLength", "Middle", "Variables")
        self.variables.setExpression("Middle", "Length / 2")
        source = self.valueSource("Distance", "App::PropertyLength", 5)
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.Middle.Value, 10)
        original = dict(self.variables.ExpressionEngine)["Middle"]
        actual = self.store(source, "Distance", "mm", "<<Variables>>.Middle / 2", "Quarter")
        with self.subTest(stage="immediate"):
            self.assertAlmostEqual(actual, 5)
        self.assertEqual(dict(self.variables.ExpressionEngine)["Middle"], original)
        self.variables.Length = 24
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.Middle.Value, 12)
        self.assertAlmostEqual(self.variables.Quarter.Value, 6)
        self.assertAlmostEqual(source.Distance.Value, 6)

    def testRelativeSourceExpression(self):
        source = self.valueSource("Result", "App::PropertyLength", 10)
        self.doc.recompute()
        actual = self.store(source, "Result", "mm", "Variables.Length / 2", "HalfLength")
        with self.subTest(stage="immediate"):
            self.assertAlmostEqual(actual, 10)
        self.assertIn("HalfLength", dict(self.variables.ExpressionEngine))
        self.variables.Length = 24
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.HalfLength.Value, 12)
        self.assertAlmostEqual(source.Result.Value, 12)

    def testStringExpression(self):
        self.variables.addProperty("App::PropertyString", "Text", "Variables")
        self.variables.Text = "Hello \u6f22\u5b57 \u00fc"
        source = self.valueSource("Text", "App::PropertyString", "Initial")
        self.doc.recompute()
        editor = self.stringEditor(source)
        actual = self.store(source, "Text", "", "<<Variables>>.Text", "StoredText", editor=editor)
        with self.subTest(stage="immediate"):
            self.assertEqual(actual, "Hello \u6f22\u5b57 \u00fc")
        self.assertIn("StoredText", dict(self.variables.ExpressionEngine))
        self.variables.Text = "Updated text"
        self.doc.recompute()
        self.assertEqual(self.variables.StoredText, "Updated text")
        self.assertEqual(source.Text, "Updated text")

    def testStringLiteralWithQuotesAndBackslash(self):
        # the value is assigned by a recorded Python command: it must survive quoting
        source = self.valueSource("Text", "App::PropertyString", "Initial")
        self.doc.recompute()
        editor = self.stringEditor(source)
        expected = 'say "hi" \'x\' \\ \n end'
        actual = self.store(source, "Text", "", '<<say "hi" \'x\' \\\\ \\n end>>', "StoredText",
                            editor=editor)
        self.assertEqual(actual, expected)
        self.assertNotIn("StoredText", dict(self.variables.ExpressionEngine))
        self.doc.recompute()
        self.assertEqual(source.Text, expected)

    def testInchLiteralImmediate(self):
        # the inch unit is a double quote: 2" was recorded as V.Inches = "2 ""
        source = self.valueSource("Distance", "App::PropertyLength", 5)
        self.doc.recompute()
        self.assertAlmostEqual(self.store(source, "Distance", "mm", '2"', "Inches"), 50.8)
        self.assertNotIn("Inches", dict(self.variables.ExpressionEngine))

    def testCancelPreservesExistingBinding(self):
        source = self.valueSource()
        source.setExpression("Scale", "<<Variables>>.Factor * 1.5")
        self.doc.recompute()
        expressions = list(source.ExpressionEngine)
        properties = list(self.variables.PropertiesList)
        self.store(source, "Scale", "", "<<Variables>>.Factor * 2", "Cancelled", cancel=True)
        self.assertEqual(source.ExpressionEngine, expressions)
        self.assertEqual(self.variables.PropertiesList, properties)
        self.assertAlmostEqual(source.Scale, 3)

    def testStoreUndoRedoPreservesExpressions(self):
        source = self.valueSource()
        source.setExpression("Scale", "<<Variables>>.Factor * 1.5")
        self.doc.recompute()
        original = list(source.ExpressionEngine)
        self.doc.openTransaction("Store expression in variable set")
        self.store(source, "Scale", "", "<<Variables>>.Factor * 2", "StoredScale")
        self.doc.recompute()
        self.doc.commitTransaction()
        self.assertAlmostEqual(self.variables.StoredScale, 4)
        self.assertAlmostEqual(source.Scale, 4)
        self.doc.undo()
        self.doc.recompute()
        self.assertNotIn("StoredScale", self.variables.PropertiesList)
        self.assertEqual(source.ExpressionEngine, original)
        self.assertAlmostEqual(source.Scale, 3)
        self.doc.redo()
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.StoredScale, 4)
        self.assertAlmostEqual(source.Scale, 4)
        self.assertIn("StoredScale", dict(self.variables.ExpressionEngine))

    def testPreservesUnrelatedPendingExpression(self):
        self.variables.addProperty("App::PropertyFloat", "Existing", "Variables")
        self.variables.setExpression("Existing", "Factor * 7")
        source = self.valueSource()
        self.doc.recompute()
        old_expression = dict(self.variables.ExpressionEngine)["Existing"]
        self.assertAlmostEqual(self.variables.Existing, 14)
        self.variables.Factor = 4
        actual = self.store(source, "Scale", "", "<<Variables>>.Factor * 1.5", "StoredScale")
        with self.subTest(stage="immediate"):
            self.assertAlmostEqual(actual, 6)
        # Initializing the new property must not execute unrelated bindings.
        self.assertAlmostEqual(self.variables.Existing, 14)
        self.assertEqual(dict(self.variables.ExpressionEngine)["Existing"], old_expression)
        self.doc.recompute()
        self.assertAlmostEqual(self.variables.Existing, 28)
        self.assertAlmostEqual(self.variables.StoredScale, 6)
