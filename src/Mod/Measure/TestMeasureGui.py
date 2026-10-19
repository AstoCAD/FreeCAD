# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for the core Measure tools."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import MatGui
import Materials
import Part
from PySide import QtCore, QtWidgets
from pivy import coin


class _ResultTextMeasure:
    @staticmethod
    def getInputProps():
        return ("ResultText",)

    def getSubject(self, obj):
        return []

    def getResultString(self, obj):
        return obj.ResultText


class TestMeasureAnnotationLines(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("MeasureAnnotationLinesTest")
        self.measure = self.doc.addObject("Measure::MeasurePython", "CustomMeasurement")
        self.measure.addProperty("App::PropertyString", "ResultText")
        self.measure.Proxy = _ResultTextMeasure()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _set_text_and_check_lines(self, text):
        self.measure.ResultText = text
        self.doc.recompute()
        Gui.updateGui()
        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoFrameLabel"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(self.measure.ViewObject.RootNode)
        paths = search.getPaths()
        self.assertEqual(paths.getLength(), 1)
        node = coin.SoFullPath.fromSoPath(paths[0]).getTail()
        self.assertEqual(list(node.getField("string").getValues()), text.split("\n"))

    def test_single_line_result_updates(self):
        self._set_text_and_check_lines("Ordinary result")
        self._set_text_and_check_lines("Updated result")

    def test_growing_result_adds_annotation_lines(self):
        self._set_text_and_check_lines("First")
        self._set_text_and_check_lines("First\nSecond\nThird")

    def test_shrinking_result_removes_old_annotation_lines(self):
        self._set_text_and_check_lines("First\nSecond\nThird")
        self._set_text_and_check_lines("Updated")

    def test_empty_result_removes_old_annotation_lines(self):
        self._set_text_and_check_lines("First\nSecond\nThird")
        self._set_text_and_check_lines("")


class TestMeasureDistanceDisplayUnit(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("MeasureDistanceDisplayUnitTest")
        self.measure = self.doc.addObject("Measure::MeasureDistanceDetached", "Distance")
        self.measure.Position1 = App.Vector(0, 0, 0)
        self.measure.Position2 = App.Vector(30, 40, 120)
        self.measure.ViewObject.ShowDelta = True
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def annotation_nodes(self):
        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoFrameLabel"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        # The delta dimensions are nodekits; their internal labels are excluded
        # from Coin searches unless nodekit child searching is enabled.
        searching_children = coin.SoBaseKit.isSearchingChildren()
        try:
            coin.SoBaseKit.setSearchingChildren(True)
            search.apply(self.measure.ViewObject.RootNode)
        finally:
            coin.SoBaseKit.setSearchingChildren(searching_children)
        paths = search.getPaths()
        nodes = [
            coin.SoFullPath.fromSoPath(paths[index]).getTail()
            for index in range(paths.getLength())
        ]
        self.assertEqual(len(nodes), 4)
        return nodes

    def annotation_texts(self):
        texts = []
        for node in self.annotation_nodes():
            texts.extend(node.getField("string").getValues())
        self.assertEqual(len(texts), 4)
        return texts

    def test_distance_and_delta_annotations_follow_display_unit(self):
        for unit in ("mm", "cm", "in"):
            with self.subTest(unit=unit):
                self.measure.DisplayUnit = unit
                Gui.updateGui()
                texts = self.annotation_texts()
                self.assertTrue(all(text.endswith(" " + unit) for text in texts), texts)
                values = sorted(App.Units.Quantity(text.split(": ")[-1]).Value for text in texts)
                decimals = App.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt(
                    "Decimals", 2
                )
                tolerance = 0.51 * 10 ** (-decimals) * App.Units.Quantity("1 " + unit).Value
                for actual, expected in zip(values, (30, 40, 120, 130)):
                    self.assertAlmostEqual(actual, expected, delta=tolerance)

    def test_empty_display_unit_uses_global_unit_schema(self):
        self.measure.DisplayUnit = "cm"
        self.measure.DisplayUnit = ""
        Gui.updateGui()
        self.assertEqual(
            set(self.annotation_texts()),
            {
                self.measure.Distance.UserString,
                "Δx: " + self.measure.DistanceX.UserString,
                "Δy: " + self.measure.DistanceY.UserString,
                "Δz: " + self.measure.DistanceZ.UserString,
            },
        )

    def test_delta_annotation_background_preserves_blue_channel(self):
        expected = (0.1, 0.2, 0.8)
        self.measure.ViewObject.TextBackgroundColor = expected
        Gui.updateGui()
        for node in self.annotation_nodes():
            actual = node.getField("backgroundColor").getValue().getValue()
            for channel, value in zip(actual, expected):
                self.assertAlmostEqual(channel, value, places=6)


class TestMassPropertiesMaterial(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("MassPropertiesMaterialTest")
        self.doc.UndoMode = 1

    def tearDown(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def material(self, name, density):
        value = Materials.Material()
        value.Name = name
        value.addPhysicalModel(Materials.UUIDs().Density)
        value.setPhysicalValue("Density", density)
        return value

    def feature(self, name, material_name, density):
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = Part.makeBox(10, 10, 10)
        obj.ShapeMaterial = self.material(material_name, density)
        return obj

    def material_button(self):
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        for widget in task.getDialogContent():
            button = widget.findChild(QtWidgets.QPushButton, "materialButton")
            if button:
                return button
        self.fail("Material button not found")

    def test_material_selector_is_registered_widget(self):
        selector = Gui.UiLoader().createWidget("MatGui::MaterialSelector")
        self.assertIsNotNone(selector)
        self.assertEqual(selector.metaObject().className(), "MatGui::MaterialSelector")
        selector.deleteLater()

    def choose(self, uuid):
        errors = []

        def select_material():
            dialog = QtWidgets.QApplication.activeModalWidget()
            try:
                widget = dialog.findChild(QtWidgets.QWidget, "materialTreeWidget")
                self.assertIsNotNone(widget)
                picker = MatGui.MaterialTreeWidget(widget)
                picker.UUID = uuid
                buttons = dialog.findChild(QtWidgets.QDialogButtonBox)
                buttons.button(QtWidgets.QDialogButtonBox.Ok).click()
            except Exception as error:
                errors.append(error)
                if dialog:
                    dialog.reject()

        QtCore.QTimer.singleShot(100, select_material)
        self.material_button().click()
        self.assertEqual(errors, [])

    def test_mixed_materials_assignment_and_undo(self):
        first = self.feature("First", "Brass", "8500 kg/m^3")
        second = self.feature("Second", "Iron", "7874 kg/m^3")
        third = self.feature("Third", "Aluminium", "2700 kg/m^3")
        Gui.Selection.addSelection(first)
        Gui.Selection.addSelection(second)
        Gui.Selection.addSelection(third)
        Gui.runCommand("Std_MassProperties")
        Gui.updateGui()
        self.assertEqual(self.material_button().text(), "Brass, Iron, …")

        steel_uuid = "92589471-a6cb-4bbc-b748-d425a17dea7d"
        self.choose(steel_uuid)
        for obj in (first, second, third):
            self.assertEqual(obj.ShapeMaterial.UUID, steel_uuid)
        self.assertEqual(self.material_button().text(), "CalculiX-Steel")

        self.doc.undo()
        self.assertEqual(first.ShapeMaterial.Name, "Brass")
        self.assertEqual(second.ShapeMaterial.Name, "Iron")
        self.assertEqual(third.ShapeMaterial.Name, "Aluminium")

    def test_link_selection_edits_source_material(self):
        source = self.feature("Source", "Brass", "8500 kg/m^3")
        link = self.doc.addObject("App::Link", "Occurrence")
        link.setLink(source)
        Gui.Selection.addSelection(link)
        Gui.runCommand("Std_MassProperties")
        Gui.updateGui()
        self.assertEqual(self.material_button().text(), "Brass")

        iron_uuid = "1826c364-d26a-43fb-8f61-288281236836"
        self.choose(iron_uuid)
        self.assertEqual(source.ShapeMaterial.UUID, iron_uuid)
        self.assertEqual(self.material_button().text(), "Iron-Generic")
