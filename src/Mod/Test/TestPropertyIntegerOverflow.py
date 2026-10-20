# SPDX-License-Identifier: LGPL-2.1-or-later
"""Scalar integer property conversion preserves values and notifications."""

import ctypes
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import FreeCAD as App

_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p
_long_bits = ctypes.sizeof(ctypes.c_long) * 8
_long_max = (1 << (_long_bits - 1)) - 1
_long_min = -(1 << (_long_bits - 1))


class IntWithNativeDigits(int):
    def __int__(self):
        raise AssertionError("A genuine int's native digits must not call __int__")

    def __index__(self):
        raise AssertionError("A genuine int's native digits must not call __index__")

    def __float__(self):
        raise AssertionError("An integer property must not call __float__")


class _ValueObserver:
    def __init__(self, obj):
        self.doc_name, self.object_name = obj.Document.Name, obj.Name
        self.before, self.after = [], []

    def _matches(self, obj, property_name):
        return (
            property_name == "Value"
            and obj.Name == self.object_name
            and obj.Document.Name == self.doc_name
        )

    def slotBeforeChangeObject(self, obj, property_name):
        if self._matches(obj, property_name):
            self.before.append(obj.Value)

    def slotChangedObject(self, obj, property_name):
        if self._matches(obj, property_name):
            self.after.append(obj.Value)


class TestPropertyIntegerOverflow(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        self.owned_names = []
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("IntegerOverflow_" + uuid4().hex[:10])
        self.owned_names.append(self.doc.Name)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyInteger", "Value", "Values")
        self.obj.Value = 37
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(self.obj.Value, 37)
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)

    def _cleanup(self):
        for name in reversed(self.owned_names):
            if name in App.listDocuments():
                doc = App.getDocument(name)
                if doc.HasPendingTransaction:
                    doc.abortTransaction()
                App.closeDocument(name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    @staticmethod
    def _assign(obj, value):
        # Same qualified PyDLL boundary used in the permanent floating-property
        # regression: materialize any native pending error inside this try.
        # Never clear, translate or suppress an error left by the product setter.
        try:
            setattr(obj, "Value", value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _snapshot(self):
        return (
            self.obj.Value,
            tuple(self.obj.State),
            self.doc.isTouched(),
            tuple(self.doc.UndoNames),
            self.doc.HasPendingTransaction,
        )

    def _reject_without_mutation(self, value):
        before = self._snapshot()
        error = self._assign(self.obj, value)
        with self.subTest(oracle="conversion_reports_OverflowError", long_bits=_long_bits):
            self.assertIsInstance(error, OverflowError, repr(error))
        with self.subTest(oracle="value_unchanged"):
            self.assertEqual(self.obj.Value, before[0])
        with self.subTest(oracle="object_state_unchanged"):
            self.assertEqual(tuple(self.obj.State), before[1])
        with self.subTest(oracle="document_touch_unchanged"):
            self.assertEqual(self.doc.isTouched(), before[2])
        with self.subTest(oracle="undo_names_unchanged"):
            self.assertEqual(tuple(self.doc.UndoNames), before[3])
        with self.subTest(oracle="transaction_state_unchanged"):
            self.assertEqual(self.doc.HasPendingTransaction, before[4])

    def test_positive_native_long_overflow_is_atomic(self):
        self._reject_without_mutation(_long_max + 1)

    def test_negative_native_long_overflow_is_atomic(self):
        self._reject_without_mutation(_long_min - 1)

    def test_enormous_integer_overflow_is_atomic(self):
        self._reject_without_mutation(10**400)

    def test_overflow_does_not_notify_document_observers(self):
        observer = _ValueObserver(self.obj)
        App.addDocumentObserver(observer)
        self.addCleanup(App.removeDocumentObserver, observer)
        self.assertIsNone(self._assign(self.obj, 51))
        self.assertEqual(observer.before, [37])
        self.assertEqual(observer.after, [51])
        self.doc.recompute()
        self.doc.clearUndos()
        observer.before.clear()
        observer.after.clear()
        error = self._assign(self.obj, 10**400)
        with self.subTest(oracle="observer_case_reports_OverflowError"):
            self.assertIsInstance(error, OverflowError, repr(error))
        with self.subTest(oracle="no_before_notification"):
            self.assertEqual(observer.before, [])
        with self.subTest(oracle="no_after_notification"):
            self.assertEqual(observer.after, [])
        with self.subTest(oracle="observer_case_value_preserved"):
            self.assertEqual(self.obj.Value, 51)
        with self.subTest(oracle="observer_case_document_untouched"):
            self.assertFalse(self.doc.isTouched())
        self.assertEqual(self.doc.UndoNames, [])
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_failed_conversion_leaves_transaction_empty(self):
        # First qualify ordinary type rejection in an empty real transaction.
        self.doc.openTransaction("Rejected integer type control")
        self.assertIsInstance(self._assign(self.obj, object()), TypeError)
        self.doc.commitTransaction()
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.obj.Value, 37)
        self.assertFalse(self.doc.isTouched())
        self.doc.openTransaction("Rejected integer conversion")
        self._reject_without_mutation(_long_max + 1)
        self.doc.commitTransaction()
        with self.subTest(oracle="failed_conversion_creates_no_undo"):
            self.assertEqual(self.doc.UndoNames, [])
        with self.subTest(oracle="failed_transaction_value_preserved"):
            self.assertEqual(self.obj.Value, 37)

    def test_native_long_limits_bools_and_int_subclass_control(self):
        for value, expected in (
            (_long_min, _long_min),
            (_long_max, _long_max),
            (-1, -1),
            (0, 0),
            (1, 1),
            (True, 1),
            (False, 0),
            (IntWithNativeDigits(23), 23),
        ):
            with self.subTest(
                type=type(value).__name__, expected=expected, native_long_bits=_long_bits
            ):
                self.assertIsNone(self._assign(self.obj, value))
                self.assertEqual(self.obj.Value, expected)
                self.doc.recompute()
                self.assertTrue(self.obj.isValid())

    def test_type_rejection_and_ordinary_undo_redo_control(self):
        for value in (37.0, "37", [], object()):
            with self.subTest(type=type(value).__name__):
                self.assertIsInstance(self._assign(self.obj, value), TypeError)
                self.assertEqual(self.obj.Value, 37)
                self.assertFalse(self.doc.isTouched())
        self.doc.openTransaction("Ordinary integer assignment")
        self.assertIsNone(self._assign(self.obj, 51))
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 51)
        self.assertEqual(self.doc.UndoNames, ["Ordinary integer assignment"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 37)
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(self.obj.Value, 51)

    def test_native_long_boundaries_save_reopen_control(self):
        self.obj.addProperty("App::PropertyInteger", "Minimum", "Values")
        self.obj.Minimum = _long_min
        self.obj.Value = _long_max
        self.doc.recompute()
        with tempfile.TemporaryDirectory(prefix="fc_integer_limits_") as temporary:
            path = Path(temporary) / "native_integer_limits.FCStd"
            self.doc.saveAs(str(path))
            self.assertTrue(path.is_file())
            App.closeDocument(self.doc.Name)
            restored = App.openDocument(str(path))
            self.owned_names.append(restored.Name)
            self.assertEqual(restored.Variables.Value, _long_max)
            self.assertEqual(restored.Variables.Minimum, _long_min)
            self.assertTrue(restored.Variables.isValid())
            App.closeDocument(restored.Name)
