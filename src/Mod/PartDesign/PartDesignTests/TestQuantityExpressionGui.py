# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native quantity expression commits update dress-up task previews.

Regressions for https://github.com/FreeCAD/FreeCAD/issues/33098 and #32968,
including range, cancellation, keyboard, and notification compatibility.
"""

import json
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestQuantityExpressionCommitGui(unittest.TestCase):
    def setUp(self):
        old = Gui.activeWorkbench()
        self.old_workbench = old.name() if old else None
        self.doc = App.newDocument("QuantityExpressionCommitDiagnostic")
        self.doc.UndoMode = 1
        self.gui_doc = Gui.getDocument(self.doc.Name)
        self.variables = self.doc.addObject("App::VarSet", "Variables")
        self.variables.addProperty("App::PropertyLength", "Target")
        self.variables.Target = 1
        self.variables.addProperty("App::PropertyFloat", "Factor")
        self.variables.Factor = 10
        self.variables.addProperty("App::PropertyLength", "DressupSize")
        self.variables.DressupSize = 3
        self.holder = QtWidgets.QWidget(Gui.getMainWindow())
        self.layout = QtWidgets.QVBoxLayout(self.holder)
        self.spin = None
        self.dialog = None
        self.values = []

    def tearDown(self):
        try:
            if self.dialog is not None:
                try:
                    self.dialog.reject()
                except RuntimeError:
                    pass
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                if self.doc.HasPendingTransaction:
                    self.doc.abortTransaction()
                Gui.Selection.clearSelection()
                self.holder.close()
                self.holder.deleteLater()
                App.closeDocument(self.doc.Name)
        finally:
            if self.old_workbench:
                Gui.activateWorkbench(self.old_workbench)
            Gui.updateGui()

    def _native_quantity_editor(self):
        # Use an ordinary native task binding. setBoundToByName's qualified
        # ObjectIdentifier is a separate callback-identity boundary on old source.
        Gui.activateWorkbench("PartDesignWorkbench")
        body = self.doc.addObject("PartDesign::Body", "WidgetBody")
        self.gui_doc.activeView().setActiveObject("pdbody", body)
        box = body.newObject("PartDesign::AdditiveBox", "WidgetBox")
        box.Length = box.Width = box.Height = 100
        self.doc.recompute()
        feature = body.newObject("PartDesign::Chamfer", "WidgetChamfer")
        feature.Base = (box, ["Edge1"])
        feature.Size = 1
        self.doc.recompute()
        self.assertTrue(feature.isValid())
        self.assertTrue(self.gui_doc.setEdit(feature.Name))
        Gui.updateGui()
        editors = [widget for widget in Gui.getMainWindow().findChildren(
            QtWidgets.QAbstractSpinBox, "chamferSize") if not widget.isHidden()]
        self.assertEqual(len(editors), 1)
        self.spin = editors[0]
        self.assertTrue(self.spin.property("binding"))
        self.assertAlmostEqual(self.spin.property("rawValue"), 1)
        QtCore.QObject.connect(self.spin, QtCore.SIGNAL("valueChanged(double)"),
                               self.values.append)

    def _open_fx(self, editor, expression):
        icons = [widget for widget in editor.findChildren(QtWidgets.QLabel)
                 if widget.inherits("ExpressionLabel")]
        self.assertEqual(len(icons), 1)
        self.assertTrue(QtCore.QMetaObject.invokeMethod(
            icons[0], "clicked", QtCore.Qt.DirectConnection))
        Gui.updateGui()
        self.dialog = editor.findChild(QtWidgets.QDialog, "DlgExpressionInput")
        self.assertIsNotNone(self.dialog)
        self.dialog.findChild(QtWidgets.QCheckBox, "checkBoxVarSets").setChecked(False)
        self.dialog.findChild(QtWidgets.QPlainTextEdit, "expression").setPlainText(expression)
        Gui.updateGui()
        buttons = self.dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
        self.assertIsNotNone(buttons)
        return buttons.button(QtWidgets.QDialogButtonBox.Ok)

    def _accept_fx(self, editor, expression):
        ok = self._open_fx(editor, expression)
        self.assertTrue(ok.isEnabled(), "Valid expression must be accepted by ordinary Fx dialog")
        accepted = []
        self.dialog.accepted.connect(lambda: accepted.append(True))
        ok.click()
        self.assertEqual(accepted, [True])
        self.dialog = None
        Gui.updateGui()

    def _snapshot(self, editor):
        line = editor.findChild(QtWidgets.QLineEdit)
        return {"value": editor.property("rawValue"), "unit": editor.property("unit"),
                "text": line.text() if line else None, "signals": list(self.values)}

    def test_dimensionless_expression_keeps_required_length_unit(self):
        self._native_quantity_editor()
        for expression in ("Variables.Factor", "5 * 2"):
            with self.subTest(expression=expression):
                self._accept_fx(self.spin, expression)
                state = self._snapshot(self.spin)
                print("QUANTITY_FX_UNIT " + json.dumps(state, sort_keys=True))
                self.assertAlmostEqual(state["value"], 10)
                actual_unit = App.Units.Quantity("1 " + state["unit"]).Unit
                self.assertEqual(actual_unit, App.Units.Quantity("1 mm").Unit,
                                 "A bare expression must retain the required length unit")

    def test_quantity_expression_notifies_once_and_same_value_does_not(self):
        self._native_quantity_editor()
        self._accept_fx(self.spin, "10 mm")
        print("QUANTITY_FX_SIGNAL " + json.dumps(self._snapshot(self.spin), sort_keys=True))
        self.assertAlmostEqual(self.spin.property("rawValue"), 10)
        self.assertEqual(self.values, [10.0], "A new semantic value must notify its listeners")
        self.values.clear()
        self._accept_fx(self.spin, "5 * 2 mm")
        self.assertAlmostEqual(self.spin.property("rawValue"), 10)
        self.assertEqual(self.values, [], "An unchanged expression result must not notify again")

    def test_cancel_keeps_value_unit_expression_and_notifications_control(self):
        self._native_quantity_editor()
        before = self._snapshot(self.spin)
        before_expressions = list(self.variables.ExpressionEngine)
        ok = self._open_fx(self.spin, "9 mm")
        self.assertTrue(ok.isEnabled())
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertEqual(self._snapshot(self.spin), before)
        self.assertEqual(self.variables.ExpressionEngine, before_expressions)

    def test_incompatible_angle_is_rejected_by_dialog_control(self):
        self._native_quantity_editor()
        before = self._snapshot(self.spin)
        before_expressions = list(self.variables.ExpressionEngine)
        ok = self._open_fx(self.spin, "10 deg")
        self.assertFalse(ok.isEnabled(), "The length editor must reject an angle result")
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertEqual(self._snapshot(self.spin), before)
        self.assertEqual(self.variables.ExpressionEngine, before_expressions)

    def _dressup_preview(self, kind, parameter, editor_name):
        Gui.activateWorkbench("PartDesignWorkbench")
        body = self.doc.addObject("PartDesign::Body", "Body")
        self.gui_doc.activeView().setActiveObject("pdbody", body)
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 10
        self.doc.recompute()
        feature = body.newObject("PartDesign::" + kind, kind)
        feature.Base = (box, ["Edge1"])
        setattr(feature, parameter, 3)
        self.doc.recompute()
        self.assertTrue(feature.isValid())
        expected_volume = feature.Shape.Volume
        expected_area = feature.Shape.Area
        setattr(feature, parameter, 1)
        self.doc.recompute()
        self.assertTrue(feature.isValid())
        original_volume = feature.Shape.Volume
        self.assertGreater(abs(original_volume - expected_volume), 1)
        self.assertTrue(self.gui_doc.setEdit(feature.Name))
        Gui.updateGui()
        editors = [widget for widget in Gui.getMainWindow().findChildren(
            QtWidgets.QAbstractSpinBox, editor_name) if not widget.isHidden()]
        self.assertEqual(len(editors), 1)
        editor = editors[0]
        self._accept_fx(editor, "Variables.DressupSize")
        print("QUANTITY_FX_PREVIEW " + json.dumps({
            "kind": kind, "editor": self._snapshot(editor),
            "property": getattr(feature, parameter).Value,
            "volume": feature.Shape.Volume, "expected_volume": expected_volume,
            "expression": dict(feature.ExpressionEngine).get(parameter)}, sort_keys=True))
        with self.subTest(stage="before_task_accept", oracle="semantic_value"):
            self.assertAlmostEqual(getattr(feature, parameter).Value, 3)
        with self.subTest(stage="before_task_accept", oracle="preview_geometry"):
            self.assertAlmostEqual(feature.Shape.Volume, expected_volume, places=7)
            self.assertAlmostEqual(feature.Shape.Area, expected_area, places=7)
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        task.accept()
        Gui.updateGui()
        self.assertIsNone(self.gui_doc.getInEdit())
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))
        with self.subTest(stage="after_task_accept", oracle="geometry"):
            self.assertAlmostEqual(feature.Shape.Volume, expected_volume, places=7)
        self.assertIn("DressupSize", dict(feature.ExpressionEngine)[parameter])
        self.variables.DressupSize = 2
        self.doc.recompute()
        self.assertAlmostEqual(getattr(feature, parameter).Value, 2)
        self.assertTrue(feature.isValid())
        self.assertNotAlmostEqual(feature.Shape.Volume, expected_volume, places=5)
        self.assertNotAlmostEqual(feature.Shape.Volume, original_volume, places=5)

    def test_chamfer_expression_updates_actual_preview_and_acceptance(self):
        self._dressup_preview("Chamfer", "Size", "chamferSize")

    def test_fillet_expression_updates_actual_preview_and_acceptance(self):
        self._dressup_preview("Fillet", "Radius", "filletRadius")


class TestQuantityExpressionCompatibilityGui(unittest.TestCase):
    setUp = TestQuantityExpressionCommitGui.setUp
    tearDown = TestQuantityExpressionCommitGui.tearDown
    _native_quantity_editor = TestQuantityExpressionCommitGui._native_quantity_editor
    _open_fx = TestQuantityExpressionCommitGui._open_fx
    _accept_fx = TestQuantityExpressionCommitGui._accept_fx
    _snapshot = TestQuantityExpressionCommitGui._snapshot

    def _editor(self):
        self._native_quantity_editor()
        return self.doc.getObject("WidgetChamfer")

    def test_same_quantity_result_has_no_notification_control(self):
        feature = self._editor()
        self._accept_fx(self.spin, "1 mm")
        self.assertAlmostEqual(self.spin.property("rawValue"), 1)
        self.assertEqual(self.spin.property("unit"), "mm")
        self.assertEqual(self.values, [])
        self.assertAlmostEqual(feature.Size.Value, 1)
        self.assertTrue(feature.isValid())

    def test_equivalent_display_units_keep_same_quantity_control(self):
        feature = self._editor()
        for expression in ("0.1 cm", "0.001 m"):
            with self.subTest(expression=expression):
                self._accept_fx(self.spin, expression)
                self.assertAlmostEqual(self.spin.property("rawValue"), 1)
                self.assertEqual(self.spin.property("unit"), "mm")
                self.assertEqual(self.values, [])
                self.assertAlmostEqual(feature.Size.Value, 1)

    def test_maximum_clamping_does_not_notify_unchanged_value_control(self):
        self._editor()
        self.assertTrue(self.spin.setProperty("maximum", 3))
        self.assertTrue(self.spin.setProperty("rawValue", 3))
        self.assertAlmostEqual(self.spin.property("rawValue"), 3)
        self.values.clear()
        for expression in ("10 mm", "20 mm"):
            with self.subTest(expression=expression):
                self._accept_fx(self.spin, expression)
                self.assertAlmostEqual(self.spin.property("rawValue"), 3)
                self.assertEqual(self.spin.property("unit"), "mm")
                self.assertEqual(self.values, [],
                                 "A result clamped to the committed value must not notify again")

    def test_minimum_clamping_does_not_notify_unchanged_value_control(self):
        self._editor()
        self.assertTrue(self.spin.setProperty("minimum", 3))
        self.assertTrue(self.spin.setProperty("rawValue", 3))
        self.assertAlmostEqual(self.spin.property("rawValue"), 3)
        self.values.clear()
        for expression in ("1 mm", "2 mm"):
            with self.subTest(expression=expression):
                self._accept_fx(self.spin, expression)
                self.assertAlmostEqual(self.spin.property("rawValue"), 3)
                self.assertEqual(self.spin.property("unit"), "mm")
                self.assertEqual(self.values, [],
                                 "A result clamped to the committed value must not notify again")

    def test_cancel_then_ordinary_return_still_commits_control(self):
        feature = self._editor()
        self.assertTrue(self._open_fx(self.spin, "9 mm").isEnabled())
        self.dialog.reject()
        self.dialog = None
        Gui.updateGui()
        self.assertEqual(self.values, [])
        line = self.spin.findChild(QtWidgets.QLineEdit)
        self.assertIsNotNone(line)
        line.setFocus()
        line.selectAll()
        QtTest.QTest.keyClicks(line, "2 mm")
        QtTest.QTest.keyClick(self.spin, QtCore.Qt.Key_Return)
        Gui.updateGui()
        self.assertAlmostEqual(feature.Size.Value, 2)
        self.assertTrue(feature.isValid())
        self.assertIn(2.0, self.values)

    def test_keyboard_tracking_false_keeps_expression_notifications(self):
        feature = self._editor()
        self.spin.setKeyboardTracking(False)
        self.assertFalse(self.spin.keyboardTracking())
        self._accept_fx(self.spin, "3 mm")
        with self.subTest(oracle="notification"):
            self.assertEqual(self.values, [3.0])
        with self.subTest(oracle="model"):
            self.assertAlmostEqual(feature.Size.Value, 3)
        self.assertTrue(feature.isValid())

    def test_model_notification_can_edit_feature_label_synchronously(self):
        feature = self._editor()
        events = []

        class Observer:
            armed = True

            def slotChangedObject(self, obj, prop):
                if (self.armed and obj == feature and prop == "Size"
                        and abs(obj.Size.Value - 3) < 1e-12):
                    self.armed = False
                    events.append(obj.Size.Value)
                    obj.Label = "Observed expression result"

        observer = Observer()
        App.addDocumentObserver(observer)
        try:
            self._accept_fx(self.spin, "3 mm")
        finally:
            App.removeDocumentObserver(observer)
        self.assertEqual(events, [3.0], "The actual feature callback must be reached exactly once")
        self.assertEqual(feature.Label, "Observed expression result")
        self.assertAlmostEqual(feature.Size.Value, 3)
        self.assertTrue(feature.isValid())

    def test_programmatic_setvalue_and_same_value_notification_control(self):
        feature = self._editor()
        self.assertTrue(self.spin.setProperty("rawValue", 3))
        Gui.updateGui()
        self.assertEqual(self.values, [3.0])
        self.assertAlmostEqual(feature.Size.Value, 3)
        self.values.clear()
        self.assertTrue(self.spin.setProperty("rawValue", 3))
        self.assertEqual(self.values, [])
        self.assertAlmostEqual(feature.Size.Value, 3)
        self.assertTrue(feature.isValid())
