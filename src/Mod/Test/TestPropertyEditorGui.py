# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regressions for values written through the live property editor model."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class PropertyEditorGuiTestCase(unittest.TestCase):
    """Provide actual document selection and property-model lookup helpers."""

    def setUp(self):
        self.doc = App.newDocument("PropertyEditorGuiTest")
        Gui.Selection.clearSelection()

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def find_property_index(self, model, name, parent=QtCore.QModelIndex()):
        for row in range(model.rowCount(parent)):
            label = model.index(row, 0, parent)
            if model.data(label, QtCore.Qt.DisplayRole) == name:
                return model.index(row, 1, parent)
            result = self.find_property_index(model, name, label)
            if result.isValid():
                return result
        return QtCore.QModelIndex()

    def property_model(self, obj, name, expected_value=None):
        """Select an object and wait until its current property is in the model.

        The edit-role value can differ from the Python property value, for example
        for an enumeration. Callers can supply that expected model value.
        """
        if expected_value is None:
            expected_value = getattr(obj, name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)
        for _ in range(40):
            Gui.updateGui()
            trees = Gui.getMainWindow().findChildren(QtWidgets.QTreeView, "propertyEditorData")
            for tree in trees:
                model = tree.model()
                index = self.find_property_index(model, name)
                label = self.find_property_index(model, "Label")
                if (
                    index.isValid()
                    and label.isValid()
                    and model.data(label, QtCore.Qt.EditRole) == obj.Label
                    and model.data(index, QtCore.Qt.EditRole) == expected_value
                ):
                    return model, index
            QtTest.QTest.qWait(50)
        self.fail("The property editor did not show the selected object's " + name)


class TestPropertyEditorStrings(PropertyEditorGuiTestCase):
    def setUp(self):
        super().setUp()
        self.obj = self.doc.addObject("App::FeaturePython", "TextObject")
        self.obj.addProperty("App::PropertyString", "Text", "IssueAudit")
        self.obj.Text = "Initial text"
        self.doc.recompute()

    def check_text_round_trip(self, value):
        model, index = self.property_model(self.obj, "Text")
        self.assertTrue(model.setData(index, value, QtCore.Qt.EditRole))
        Gui.updateGui()
        self.assertEqual(self.obj.Text, value)

    def test_ascii_string(self):
        self.check_text_round_trip("ordinary changed text")

    def test_unicode_string(self):
        self.check_text_round_trip("Café αβγ 测量")

    def test_quotes_and_backslash(self):
        self.check_text_round_trip("'single' and \"double\" C:\\folder\\name")

    def test_literal_line_feed(self):
        # https://github.com/FreeCAD/FreeCAD/issues/14119
        self.check_text_round_trip("First line\nSecond line")

    def test_literal_carriage_return(self):
        self.check_text_round_trip("First line\rSecond line")

    def test_literal_carriage_return_line_feed(self):
        self.check_text_round_trip("First line\r\nSecond line")

    def test_rename_multiline_measurement_label(self):
        import Part

        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        measure = self.doc.addObject("Measure::MeasurePosition", "Position")
        measure.Element = (box, ["Vertex2"])
        self.doc.recompute()
        Gui.updateGui()
        self.assertIn("\n", measure.Label)
        expected = "Renamed position:" + measure.Label.split(":", 1)[1]
        model, index = self.property_model(measure, "Label")
        self.assertTrue(model.setData(index, expected, QtCore.Qt.EditRole))
        Gui.updateGui()
        self.assertEqual(measure.Label, expected)


class TestPropertyEditorEnums(PropertyEditorGuiTestCase):
    def setUp(self):
        super().setUp()
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyEnumeration", "Modes", "Enumeration")
        self.obj.Modes = ["Initial", "Control"]
        self.model, _ = self.property_model(self.obj, "Label")
        self.tree = next(
            tree for tree in Gui.getMainWindow().findChildren(
                QtWidgets.QTreeView, "propertyEditorData"
            ) if tree.model() == self.model
        )
        self.previously_hidden = None
        self.set_show_hidden(True)

    def tearDown(self):
        try:
            if self.previously_hidden is not None:
                self.set_show_hidden(self.previously_hidden)
        finally:
            super().tearDown()

    def set_show_hidden(self, enabled):
        errors = []

        def choose():
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                self.assertIsInstance(menu, QtWidgets.QMenu)
                text = QtCore.QCoreApplication.translate(
                    "Gui::PropertyEditor::PropertyEditor", "Show Hidden"
                )
                action = next(action for action in menu.actions() if action.text() == text)
                if self.previously_hidden is None:
                    self.previously_hidden = action.isChecked()
                if action.isChecked() != enabled:
                    menu.setActiveAction(action)
                    QtTest.QTest.keyClick(menu, QtCore.Qt.Key_Return)
                else:
                    menu.close()
            except BaseException as error:
                errors.append(repr(error))
                if menu:
                    menu.close()

        index = self.find_property_index(self.model, "Modes")
        self.assertTrue(index.isValid())
        self.tree.expandAll()
        QtCore.QTimer.singleShot(50, choose)
        from PySide import QtGui
        point = self.tree.visualRect(index).center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, point, self.tree.viewport().mapToGlobal(point)
        )
        QtWidgets.QApplication.sendEvent(self.tree.viewport(), event)
        Gui.updateGui()
        self.assertFalse(errors, errors)

    def test_enum_list_round_trips(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32820
        for values in (
            ["First", "Second"],
            ["создает", "полилинию", "нескольких", "測量"],
            ['single\' and "double"', "C:\\new\\tool", "First\nSecond", "CR\rLF\r\n"],
        ):
            with self.subTest(values=values):
                index = self.find_property_index(self.model, "Enum")
                self.assertTrue(index.isValid())
                self.assertTrue(self.model.setData(index, values, QtCore.Qt.EditRole))
                Gui.updateGui()
                self.assertEqual(self.obj.getEnumerationsOfProperty("Modes"), values)

    def test_enum_selection_round_trips_quotes_and_unicode(self):
        values = ["Initial", "測量", 'single\' and "double"', "C:\\new\\tool", "First\nSecond"]
        self.obj.Modes = values
        for value in values[1:]:
            with self.subTest(value=value):
                index = self.find_property_index(self.model, "Modes")
                self.assertTrue(index.isValid())
                self.assertTrue(self.model.setData(index, value, QtCore.Qt.EditRole))
                Gui.updateGui()
                self.assertEqual(self.obj.Modes, value)
