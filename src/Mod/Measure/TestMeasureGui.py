# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for the core Measure tools."""

import unittest
from contextlib import contextmanager

import FreeCAD as App
import FreeCADGui as Gui
import MatGui
import Materials
import Part
from PySide import QtCore, QtWidgets
from pivy import coin


class TestMeasurementReferenceApi(unittest.TestCase):
    def setUp(self):
        import Measure

        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasurementReferenceApiTest")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length = 2
        self.box.Width = 3
        self.box.Height = 4
        self.doc.recompute()
        self.measurement = Measure.Measurement()

    def tearDown(self):
        self.measurement.clear()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    @contextmanager
    def _without_active_document(self):
        previous = App.activeDocument()
        previous_name = previous.Name if previous else None
        try:
            App.setActiveDocument("")
            # ActiveDocument is a module attribute updated by signals; the
            # activeDocument() function reads the actual core document pointer.
            self.assertIsNone(App.activeDocument())
            yield
        finally:
            if previous_name in App.listDocuments():
                App.setActiveDocument(previous_name)

    def test_add_reference_without_active_document_raises_clear_error(self):
        with self._without_active_document():
            with self.assertRaisesRegex(RuntimeError, "^No active document$"):
                self.measurement.addReference3D(self.box.Name, "Edge1")
            self.assertFalse(self.measurement.has3DReferences())

    def test_add_reference_checks_argument_types_before_document_lookup(self):
        with self._without_active_document():
            for args in ((None, "Edge1"), (42, "Edge1"), ("Box", None), ("Box", 42)):
                with self.subTest(args=args):
                    with self.assertRaises(TypeError):
                        self.measurement.addReference3D(*args)
                    self.assertFalse(self.measurement.has3DReferences())

    def test_add_reference_to_real_edge(self):
        self.assertIsNone(self.measurement.addReference3D(self.box.Name, "Edge1"))
        self.assertTrue(self.measurement.has3DReferences())
        self.assertAlmostEqual(self.measurement.length(), self.box.Shape.Edges[0].Length)

    def test_missing_object_error_keeps_measurement_empty(self):
        with self.assertRaisesRegex(ValueError, "does not exist in the document"):
            self.measurement.addReference3D("Missing", "Edge1")
        self.assertFalse(self.measurement.has3DReferences())


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


class TestMassPropertiesDensity(unittest.TestCase):
    @contextmanager
    def _mass_properties(self, density, size=10):
        previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        doc = App.newDocument("MassPropertiesDensityTest")
        try:
            material = Materials.Material()
            material.Name = "Density test material"
            material.addPhysicalModel(Materials.UUIDs().Density)
            material.setPhysicalValue("Density", f"{density} kg/m^3")
            obj = doc.addObject("Part::Feature", "DensitySample")
            obj.Shape = Part.makeBox(size, size, size)
            obj.ShapeMaterial = material
            doc.recompute()
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(obj)
            Gui.runCommand("Std_MassProperties")
            Gui.updateGui()
            task = Gui.Control.activeTaskDialog()
            self.assertIsNotNone(task)

            def widget(kind, name):
                for content in task.getDialogContent():
                    result = content.findChild(kind, name)
                    if result:
                        return result
                self.fail("Missing mass-properties widget: " + name)

            def save_result():
                panel = task.getDialogContent()[0]
                while panel.parentWidget() is not None and not isinstance(
                    panel.parentWidget(), QtWidgets.QStackedWidget
                ):
                    panel = panel.parentWidget()
                self.assertIsInstance(panel.parentWidget(), QtWidgets.QStackedWidget)
                buttons = panel.findChild(QtWidgets.QDialogButtonBox)
                self.assertIsNotNone(buttons)
                save_button = buttons.button(QtWidgets.QDialogButtonBox.Apply)
                self.assertIsNotNone(save_button)
                save_button.click()
                Gui.updateGui()
                saved = doc.getObject("MassProperties")
                self.assertIsNotNone(saved)
                return saved

            yield widget, save_result
        finally:
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            App.closeDocument(doc.Name)
            if previous_document in App.listDocuments():
                App.setActiveDocument(previous_document)

    def _check_density(self, density, save=False):
        with self._mass_properties(density) as (widget, save_result):
            # This dropdown changes only this task's schema, leaving user
            # preferences intact. MKS makes the expected density directly visible.
            widget(QtWidgets.QComboBox, "unitsComboBox").setCurrentIndex(1)
            Gui.updateGui()
            density_text = widget(QtWidgets.QLineEdit, "densityEdit").text()
            if save:
                # saved results are quantity properties
                displayed = float(save_result().Density.getValueAs("kg/m^3"))
            else:
                displayed = float(
                    App.Units.Quantity(density_text.replace("³", "^3")).getValueAs("kg/m^3")
                )
            decimals = App.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt(
                "Decimals", 2
            )
            self.assertAlmostEqual(displayed, density, delta=0.51 * 10 ** (-max(decimals, 0)))

    def test_small_mass_is_preserved_in_panel_and_saved_result(self):
        decimals = App.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt("Decimals", 2)
        tolerance = 0.51 * 10 ** (-max(decimals, 0))

        def assert_mass(text):
            self.assertTrue(text.endswith(" µg"), text)
            value = float(App.Units.Quantity(text).getValueAs("µg"))
            self.assertAlmostEqual(value, 62.8, delta=tolerance)

        with self._mass_properties(density=7850.0, size=0.2) as (widget, save_result):
            units = widget(QtWidgets.QComboBox, "unitsComboBox")
            mass = widget(QtWidgets.QLineEdit, "massEdit")
            for index, schema in ((0, "Standard"), (1, "MKS")):
                with self.subTest(result=schema):
                    units.setCurrentIndex(index)
                    Gui.updateGui()
                    assert_mass(mass.text())
            with self.subTest(result="saved"):
                # saved results are quantity properties
                value = float(save_result().Mass.getValueAs("µg"))
                self.assertAlmostEqual(value, 62.8, delta=tolerance)

    def test_metal_density_display_control(self):
        self._check_density(8500.0)

    def test_foam_density_display_is_not_zero(self):
        self._check_density(50.0)

    def test_gas_density_display_is_not_zero(self):
        self._check_density(1.2)

    def test_saved_metal_density_control(self):
        self._check_density(8500.0, save=True)

    def test_saved_foam_density_is_not_zero(self):
        self._check_density(50.0, save=True)

    def test_saved_gas_density_is_not_zero(self):
        self._check_density(1.2, save=True)


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
