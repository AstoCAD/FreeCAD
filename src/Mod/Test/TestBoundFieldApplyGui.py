# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: a field bound to a property writes its value with all digits.

Gui::QuantitySpinBox, Gui::InputField and Gui::DoubleSpinBox write their value to the bound
property (ExpressionBinding apply, which task panels call on OK) as a Python command. The number
was formatted with "%f", which keeps 6 decimals: 1e-07 mm became 0 mm and 1.23456789 became
1.234568.

To run tests:
    FreeCAD -t TestBoundFieldApplyGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestBoundFieldApplyGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BoundFieldApplyGui")
        self.obj = self.doc.addObject("App::FeaturePython", "Target")
        self.obj.addProperty("App::PropertyLength", "Length", "Test")
        self.obj.addProperty("App::PropertyFloat", "Number", "Test")
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.deleteLater()
        App.closeDocument(self.doc.Name)
        Gui.updateGui()

    def apply(self, class_name, prop, setup):
        widget = Gui.UiLoader().createWidget(class_name)
        self.assertIsNotNone(widget, class_name)
        self.widgets.append(widget)
        binding = Gui.ExpressionBinding(widget)
        binding.bind(self.obj, prop)
        setup(widget)  # after bind(), which may show the current value of the property
        binding.apply("App.getDocument('{}').{}.{}".format(self.doc.Name, self.obj.Name, prop))
        return getattr(self.obj, prop)

    def test_quantity_spin_box(self):
        for value in (1e-07, 1234.56789012):
            with self.subTest(value=value):

                def setup(widget):
                    widget.setProperty("unit", "mm")
                    widget.setProperty("rawValue", value)
                    self.assertEqual(widget.property("rawValue"), value)

                result = self.apply("Gui::QuantitySpinBox", "Length", setup)
                self.assertEqual(result.Value, value)

    def test_input_field(self):
        def setup(widget):
            widget.setProperty("unit", "mm")
            widget.setProperty("rawValue", 1e-07)
            self.assertEqual(widget.property("rawValue"), 1e-07)

        result = self.apply("Gui::InputField", "Length", setup)
        self.assertEqual(result.Value, 1e-07)

    def test_double_spin_box(self):
        def setup(widget):
            widget.setProperty("decimals", 10)
            widget.setProperty("value", 1.23456789)
            self.assertEqual(widget.property("value"), 1.23456789)

        self.assertEqual(self.apply("Gui::DoubleSpinBox", "Number", setup), 1.23456789)


if __name__ == "__main__":
    unittest.main()
