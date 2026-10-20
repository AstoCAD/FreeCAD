# SPDX-License-Identifier: LGPL-2.1-or-later
"""Integer conversion for constrained floats and quantities.

Finite integer inputs must match their accepted equivalent floats. Overflow
must precede state changes and document notifications. Existing unit, clamp,
subclass, boolean, and transaction behavior has independent controls.
"""

import ctypes
import math
import unittest
from uuid import uuid4

import FreeCAD as App


# As in the qualified plain-PropertyFloat fixture, PyDLL observes an error left
# pending by the real setter. The check stays inside the assignment's try block.
_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p


class IntWithoutFloatOverride(int):
    def __float__(self):
        raise AssertionError("Genuine integer input must use its integer value")


def _property_value(owner, name):
    value = getattr(owner, name)
    if hasattr(value, "Value") and hasattr(value, "Unit"):
        return value.Value, str(value.Unit)
    return value


class _PropertyObserver:
    def __init__(self, owner, name):
        self.document_name = owner.Document.Name
        self.object_name = owner.Name
        self.name = name
        self.before, self.after = [], []

    def _matches(self, owner, name):
        return (name == self.name and owner.Name == self.object_name
                and owner.Document.Name == self.document_name)

    def slotBeforeChangeObject(self, owner, name):
        if self._matches(owner, name):
            self.before.append(_property_value(owner, name))

    def slotChangedObject(self, owner, name):
        if self._matches(owner, name):
            self.after.append(_property_value(owner, name))


class TestFloatConstraintQuantityIntegerConversion(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument("FloatSiblings_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyFloatConstraint", "ConstrainedValue", "Values")
        self.obj.addProperty("App::PropertyQuantity", "QuantityValue", "Values")
        self.obj.ConstrainedValue = 7.25  # Fresh dynamic constraint has no bounds.
        self.obj.QuantityValue = App.Units.Unit("mm")
        self.obj.QuantityValue = 7.25
        self.unit = str(self.obj.QuantityValue.Unit)
        self.assertEqual(self.obj.QuantityValue.Unit, App.Units.Unit("mm"))
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(self.obj.ConstrainedValue, 7.25)
        self.assertEqual(self.obj.QuantityValue.Value, 7.25)
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    @staticmethod
    def _assign(owner, name, value):
        try:
            setattr(owner, name, value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _expect_value(self, name, numeric):
        if name == "QuantityValue":
            self.assertEqual(_property_value(self.obj, name), (numeric, self.unit))
        else:
            self.assertEqual(_property_value(self.obj, name), numeric)

    def _finite_scalar(self, name):
        for value in (2 ** 80, -(2 ** 80)):
            with self.subTest(property=name, value=value):
                expected = float(value)
                self.assertTrue(math.isfinite(expected))
                self.assertIsNone(self._assign(self.obj, name, expected),
                                  "Equivalent finite float must already be accepted")
                self._expect_value(name, expected)
                self.assertIsNone(self._assign(self.obj, name, 7.25))
                error = self._assign(self.obj, name, value)
                with self.subTest(oracle="finite_integer_admission"):
                    self.assertIsNone(error, repr(error))
                with self.subTest(oracle="same_value_as_accepted_float"):
                    self._expect_value(name, expected)
                self.doc.recompute()
                self.assertTrue(self.obj.isValid())

    def _overflow_atomicity(self, name, invalid, ordinary):
        observer = _PropertyObserver(self.obj, name)
        App.addDocumentObserver(observer)
        self.addCleanup(App.removeDocumentObserver, observer)
        self.assertIsNone(self._assign(self.obj, name, ordinary))
        self.assertEqual(len(observer.before), 1, "Real before-change observer control")
        self.assertEqual(len(observer.after), 1, "Real after-change observer control")
        self.doc.recompute()
        self.doc.clearUndos()
        observer.before.clear()
        observer.after.clear()
        before = (_property_value(self.obj, name), tuple(self.obj.State),
                  self.doc.isTouched(), tuple(self.doc.UndoNames))
        error = self._assign(self.obj, name, invalid)
        with self.subTest(oracle="reported_conversion_error", property=name):
            self.assertIsInstance(error, OverflowError, repr(error))
        with self.subTest(oracle="value_and_unit_unchanged", property=name):
            self.assertEqual(_property_value(self.obj, name), before[0])
        with self.subTest(oracle="object_state_unchanged", property=name):
            self.assertEqual(tuple(self.obj.State), before[1])
        with self.subTest(oracle="document_state_unchanged", property=name):
            self.assertEqual(self.doc.isTouched(), before[2])
        with self.subTest(oracle="no_before_change_notification", property=name):
            self.assertEqual(observer.before, [])
        with self.subTest(oracle="no_after_change_notification", property=name):
            self.assertEqual(observer.after, [])
        self.assertEqual(tuple(self.doc.UndoNames), before[3])
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_float_constraint_finite_integer_matches_float(self):
        self._finite_scalar("ConstrainedValue")

    def test_quantity_finite_integer_matches_float_without_unit_change(self):
        self._finite_scalar("QuantityValue")


    def test_float_constraint_overflow_preserves_state_and_observers(self):
        self._overflow_atomicity("ConstrainedValue", 10 ** 400, 8.5)

    def test_quantity_overflow_preserves_unit_state_and_observers(self):
        self._overflow_atomicity("QuantityValue", 10 ** 400, 8.5)



    def test_float_constraint_existing_clamp_and_small_input_controls(self):
        self.obj.ConstrainedValue = (7.25, -100.0, 100.0, 0.25)
        for value, expected in ((123, 100.0), (-123, -100.0), (123.5, 100.0),
                                (-123.5, -100.0), (True, 1.0), (False, 0.0),
                                (IntWithoutFloatOverride(23), 23.0)):
            with self.subTest(value=repr(value)):
                self.assertIsNone(self._assign(self.obj, "ConstrainedValue", value))
                self.assertEqual(self.obj.ConstrainedValue, expected)

    def test_quantity_existing_unit_string_and_small_input_controls(self):
        for value, expected in (("2 cm", 20.0), (App.Units.Quantity("3 mm"), 3.0),
                                (True, 1.0), (False, 0.0),
                                (IntWithoutFloatOverride(23), 23.0)):
            with self.subTest(value=repr(value)):
                self.assertIsNone(self._assign(self.obj, "QuantityValue", value))
                self._expect_value("QuantityValue", expected)


    def test_constraint_large_integer_clamp_matches_accepted_float(self):
        self.obj.ConstrainedValue = (7.25, -100.0, 100.0, 0.25)
        for value in (2 ** 80, -(2 ** 80)):
            with self.subTest(value=value):
                self.assertIsNone(self._assign(self.obj, "ConstrainedValue", float(value)))
                expected = self.obj.ConstrainedValue
                self.assertEqual(expected, 100.0 if value > 0 else -100.0)
                self.obj.ConstrainedValue = 7.25
                error = self._assign(self.obj, "ConstrainedValue", value)
                with self.subTest(oracle="integer_clamps_like_equivalent_float"):
                    self.assertIsNone(error, repr(error))
                with self.subTest(oracle="existing_exact_clamp_result"):
                    self.assertEqual(self.obj.ConstrainedValue, expected)


    def test_inherited_quantity_integer_matches_accepted_float(self):
        for kind, name in (("App::PropertyQuantityConstraint", "ConstrainedQuantity"),
                           ("App::PropertyLength", "LengthValue"),
                           ("App::PropertyAngle", "AngleValue")):
            self.obj.addProperty(kind, name, "Inherited")
            for value in (2 ** 80, -(2 ** 80)):
                with self.subTest(kind=kind, value=value):
                    self.assertIsNone(self._assign(self.obj, name, float(value)))
                    expected = _property_value(self.obj, name)
                    self.assertIsNone(self._assign(self.obj, name, 7.25))
                    unit = str(getattr(self.obj, name).Unit)
                    error = self._assign(self.obj, name, value)
                    with self.subTest(oracle="inherited_integer_admission"):
                        self.assertIsNone(error, repr(error))
                    with self.subTest(oracle="same_clamped_value_and_unit_as_float"):
                        self.assertEqual(_property_value(self.obj, name), expected)
                    self.assertEqual(str(getattr(self.obj, name).Unit), unit)


    def test_inherited_quantity_overflow_precedes_existing_clamp_and_notifications(self):
        for kind, name in (("App::PropertyQuantityConstraint", "ConstrainedQuantity"),
                           ("App::PropertyLength", "LengthValue"),
                           ("App::PropertyAngle", "AngleValue")):
            with self.subTest(kind=kind):
                self.obj.addProperty(kind, name, "Inherited")
                self.assertIsNone(self._assign(self.obj, name, 7.25))
                self.doc.recompute()
                self.doc.clearUndos()
                self._overflow_atomicity(name, 10 ** 400, 8.5)


    def test_quantity_unit_mismatch_does_not_mutate_control(self):
        before = _property_value(self.obj, "QuantityValue")
        for value in ("2 s", App.Units.Quantity("3 deg")):
            with self.subTest(value=str(value)):
                error = self._assign(self.obj, "QuantityValue", value)
                self.assertIsInstance(error, Exception)
                self.assertEqual(_property_value(self.obj, "QuantityValue"), before)
                self.assertFalse(self.doc.isTouched())


    def test_negative_overflow_preserves_state_and_observers(self):
        kinds = (("App::PropertyQuantityConstraint", "ConstrainedQuantity"),
                 ("App::PropertyLength", "LengthValue"),
                 ("App::PropertyAngle", "AngleValue"))
        for kind, name in kinds:
            self.obj.addProperty(kind, name, "Inherited")
            self.assertIsNone(self._assign(self.obj, name, 7.25))
        for name in ("ConstrainedValue", "QuantityValue", "ConstrainedQuantity",
                     "LengthValue", "AngleValue"):
            with self.subTest(property=name):
                self.doc.recompute()
                self.doc.clearUndos()
                self._overflow_atomicity(name, -(10 ** 400), 8.5)

    def test_successful_constraint_and_quantity_undo_redo_control(self):
        for name in ("ConstrainedValue", "QuantityValue"):
            with self.subTest(property=name):
                self.assertIsNone(self._assign(self.obj, name, 7.25))
                self.doc.recompute()
                self.doc.clearUndos()
                self.doc.openTransaction("Assign numeric property")
                self.assertIsNone(self._assign(self.obj, name, 23))
                self.doc.commitTransaction()
                self._expect_value(name, 23.0)
                self.doc.undo()
                self.doc.recompute()
                self._expect_value(name, 7.25)
                self.doc.redo()
                self.doc.recompute()
                self._expect_value(name, 23.0)
                self.assertTrue(self.obj.isValid())
                self.assertFalse(self.doc.HasPendingTransaction)



if __name__ == "__main__":
    unittest.main()
