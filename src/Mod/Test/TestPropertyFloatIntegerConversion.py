# SPDX-License-Identifier: LGPL-2.1-or-later
"""Integer conversion for floating properties preserves values and notifications."""

import ctypes
import math
import unittest
from uuid import uuid4

import FreeCAD as App


# PyDLL checks a pending Python exception after the real C API call. Keep this
# check inside _assign's try: the old native setter can return success while
# leaving OverflowError pending, which otherwise surfaces in unrelated code.
_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p


class IntWithoutFloatOverride(int):
    def __float__(self):
        raise AssertionError("A genuine int's numeric value must not call __float__")


class ValueChangeObserver:
    def __init__(self, owner):
        self.document_name, self.object_name = owner.Document.Name, owner.Name
        self.before, self.after = [], []

    def _matches(self, obj, prop):
        return (prop == "Value" and obj.Name == self.object_name
                and obj.Document.Name == self.document_name)

    def slotBeforeChangeObject(self, obj, prop):
        if self._matches(obj, prop):
            self.before.append(obj.Value)

    def slotChangedObject(self, obj, prop):
        if self._matches(obj, prop):
            self.after.append(obj.Value)


class TestPropertyFloatIntegerBoundary(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("FloatIntegerBoundary_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyFloat", "Value", "Values")
        self.obj.Value = 7.25
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(self.obj.Value, 7.25)
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)

    @staticmethod
    def _assign(owner, value):
        try:
            setattr(owner, "Value", value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _finite_integer(self, value):
        expected = float(value)
        self.assertTrue(math.isfinite(expected))
        error = self._assign(self.obj, value)
        with self.subTest(oracle="finite_integer_admission"):
            self.assertIsNone(error, repr(error))
        with self.subTest(oracle="same_numeric_value_as_float"):
            self.assertEqual(self.obj.Value, expected)
        self.doc.recompute()
        self.assertTrue(self.obj.isValid())

    def test_large_positive_integer_for_float_property(self):
        self._finite_integer(2 ** 80)

    def test_large_negative_integer_for_float_property(self):
        self._finite_integer(-(2 ** 80))

    def test_unrepresentable_integer_rejected_without_mutation(self):
        before = (self.obj.Value, tuple(self.obj.State),
                  self.doc.isTouched(), tuple(self.doc.UndoNames))
        error = self._assign(self.obj, 10 ** 400)
        with self.subTest(oracle="reported_conversion_exception"):
            self.assertIsInstance(error, OverflowError, repr(error))
        with self.subTest(oracle="value_unchanged"):
            self.assertEqual(self.obj.Value, before[0])
        with self.subTest(oracle="object_state_unchanged"):
            self.assertEqual(tuple(self.obj.State), before[1])
        with self.subTest(oracle="document_state_unchanged"):
            self.assertEqual(self.doc.isTouched(), before[2])
        self.assertEqual(tuple(self.doc.UndoNames), before[3])
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_equivalent_large_float_inputs_control(self):
        for value in (float(2 ** 80), -float(2 ** 80), 1.7976931348623157e308):
            with self.subTest(value=value):
                self.assertTrue(math.isfinite(value))
                self.assertIsNone(self._assign(self.obj, value))
                self.assertEqual(self.obj.Value, value)
                self.doc.recompute()
                self.assertTrue(self.obj.isValid())

    def test_small_integers_bools_and_int_subclass_control(self):
        for value, expected in ((-1, -1.0), (0, 0.0), (1, 1.0),
                                (True, 1.0), (False, 0.0),
                                (IntWithoutFloatOverride(23), 23.0)):
            with self.subTest(type=type(value).__name__, expected=expected):
                self.assertIsNone(self._assign(self.obj, value))
                self.assertEqual(self.obj.Value, expected)

    def test_type_rejection_and_ordinary_undo_redo_control(self):
        for value in ("12.5", [], object()):
            with self.subTest(type=type(value).__name__):
                self.assertIsInstance(self._assign(self.obj, value), TypeError)
                self.assertEqual(self.obj.Value, 7.25)
                self.assertFalse(self.doc.isTouched())
        self.doc.openTransaction("Ordinary float assignment")
        self.assertIsNone(self._assign(self.obj, 12.5))
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 12.5)
        self.assertEqual(self.doc.UndoNames, ["Ordinary float assignment"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 7.25)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 12.5)

    def test_nonfinite_float_and_signed_zero_controls(self):
        for value in (float("inf"), float("-inf"), float("nan"), -0.0):
            with self.subTest(value=repr(value)):
                self.assertIsNone(self._assign(self.obj, value))
                if math.isnan(value):
                    self.assertTrue(math.isnan(self.obj.Value))
                else:
                    self.assertEqual(self.obj.Value, value)
                    self.assertEqual(math.copysign(1, self.obj.Value), math.copysign(1, value))

    def test_failed_integer_conversion_does_not_notify_observers(self):
        observer = ValueChangeObserver(self.obj)
        App.addDocumentObserver(observer)
        self.addCleanup(App.removeDocumentObserver, observer)
        self.assertIsNone(self._assign(self.obj, 12.5))
        self.assertEqual(observer.before, [7.25])
        self.assertEqual(observer.after, [12.5])
        self.doc.recompute()
        self.doc.clearUndos()
        observer.before.clear()
        observer.after.clear()
        error = self._assign(self.obj, 10 ** 400)
        with self.subTest(oracle="reported_conversion_exception"):
            self.assertIsInstance(error, OverflowError, repr(error))
        with self.subTest(oracle="no_before_change_notification"):
            self.assertEqual(observer.before, [])
        with self.subTest(oracle="no_after_change_notification"):
            self.assertEqual(observer.after, [])
        with self.subTest(oracle="value_unchanged"):
            self.assertEqual(self.obj.Value, 12.5)
        with self.subTest(oracle="document_untouched"):
            self.assertFalse(self.doc.isTouched())
        self.assertEqual(self.doc.UndoNames, [])
        self.assertFalse(self.doc.HasPendingTransaction)
