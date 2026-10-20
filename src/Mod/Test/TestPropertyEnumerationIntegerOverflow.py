# SPDX-License-Identifier: LGPL-2.1-or-later
"""Enumeration integer conversion errors precede property notifications."""

import ctypes
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import FreeCAD as App

_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p
_LONG_BITS = ctypes.sizeof(ctypes.c_long) * 8
_LONG_MIN = -(1 << (_LONG_BITS - 1))
_LONG_MAX = (1 << (_LONG_BITS - 1)) - 1
_OVERFLOW = (_LONG_MIN - 1, _LONG_MAX + 1, -(10**400), 10**400)


class _NativeDigitsInt(int):
    def __int__(self):
        raise AssertionError("Native integer digits must retain their existing conversion")

    def __index__(self):
        raise AssertionError("Native integer digits must retain their existing conversion")


class _IndexOnly:
    def __index__(self):
        return 1


class _Observer:
    def __init__(self, obj, name):
        self.document = obj.Document.Name
        self.object = obj.Name
        self.name = name
        self.before = []
        self.after = []

    def _matches(self, obj, name):
        return name == self.name and obj.Name == self.object and obj.Document.Name == self.document

    def slotBeforeChangeObject(self, obj, name):
        if self._matches(obj, name):
            self.before.append(getattr(obj, name))

    def slotChangedObject(self, obj, name):
        if self._matches(obj, name):
            self.after.append(getattr(obj, name))


class TestEnumerationIntegerBoundary(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous = previous.Name if previous else None
        self.names = []
        self.observers = []
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("EnumerationBoundary_" + uuid4().hex[:10])
        self.names.append(self.doc.Name)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyEnumeration", "Mode")
        self.obj.addProperty("App::PropertyEnumeration", "EmptyMode")
        self.choices = ["Zero", "First", "二Ω", "One"]
        self.obj.Mode = self.choices
        self.obj.Mode = "One"
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(self.obj.Mode, "One")
        self.assertEqual(self.obj.getEnumerationsOfProperty("Mode"), self.choices)
        self.assertIsNone(self.obj.EmptyMode)
        self.assertEqual(self.obj.getEnumerationsOfProperty("EmptyMode"), [])
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)

    def _cleanup(self):
        for observer in list(self.observers):
            App.removeDocumentObserver(observer)
        self.observers.clear()
        for name in reversed(self.names):
            if name in App.listDocuments():
                doc = App.getDocument(name)
                if doc.HasPendingTransaction:
                    doc.abortTransaction()
                App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    @staticmethod
    def _assign(obj, name, value):
        try:
            setattr(obj, name, value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _observer(self, name):
        observer = _Observer(self.obj, name)
        App.addDocumentObserver(observer)
        self.observers.append(observer)
        if name == "Mode":
            self.assertIsNone(self._assign(self.obj, name, "One"))
            self.assertEqual(observer.before, ["One"])
            self.assertEqual(observer.after, ["One"])
        observer.before.clear()
        observer.after.clear()
        self.doc.recompute()
        self.doc.clearUndos()
        return observer

    def _reset(self, observer):
        if observer.name == "Mode":
            self.assertIsNone(self._assign(self.obj, "Mode", "One"))
        self.doc.recompute()
        self.doc.clearUndos()
        observer.before.clear()
        observer.after.clear()
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)

    def _overflow_rejection(self, name):
        observer = self._observer(name)
        for value in _OVERFLOW:
            self._reset(observer)
            before = (
                getattr(self.obj, name),
                tuple(self.obj.getEnumerationsOfProperty(name)),
                tuple(self.obj.State),
                self.doc.isTouched(),
                tuple(self.doc.UndoNames),
                tuple(self.doc.RedoNames),
            )
            self.doc.openTransaction("Rejected enumeration conversion")
            error = self._assign(self.obj, name, value)
            self.doc.commitTransaction()
            with self.subTest(property=name, value=str(value), native_long_bits=_LONG_BITS):
                with self.subTest(oracle="exception"):
                    self.assertIsInstance(error, OverflowError, repr(error))
                with self.subTest(oracle="value_and_choices"):
                    self.assertEqual(getattr(self.obj, name), before[0])
                    self.assertEqual(tuple(self.obj.getEnumerationsOfProperty(name)), before[1])
                with self.subTest(oracle="state_and_touch"):
                    self.assertEqual(tuple(self.obj.State), before[2])
                    self.assertEqual(self.doc.isTouched(), before[3])
                with self.subTest(oracle="no_before_callback"):
                    self.assertEqual(observer.before, [])
                with self.subTest(oracle="no_after_callback"):
                    self.assertEqual(observer.after, [])
                with self.subTest(oracle="no_undo_or_redo"):
                    self.assertEqual(tuple(self.doc.UndoNames), before[4])
                    self.assertEqual(tuple(self.doc.RedoNames), before[5])
                with self.subTest(oracle="no_pending_transaction"):
                    self.assertFalse(self.doc.HasPendingTransaction)

    def test_populated_enumeration_overflow_rejected_before_notification(self):
        self._overflow_rejection("Mode")

    def test_empty_enumeration_reports_failed_integer_conversion(self):
        self._overflow_rejection("EmptyMode")

    def test_successful_scalar_indices_bool_and_int_subclass_undo_control(self):
        observer = self._observer("Mode")
        for value, expected in (
            (0, "Zero"),
            (2, "二Ω"),
            (True, "First"),
            (False, "Zero"),
            (_NativeDigitsInt(2), "二Ω"),
        ):
            with self.subTest(value=repr(value)):
                self._reset(observer)
                self.doc.openTransaction("Accepted enumeration conversion")
                self.assertIsNone(self._assign(self.obj, "Mode", value))
                self.doc.commitTransaction()
                self.assertEqual(self.obj.Mode, expected)
                self.assertEqual(observer.before, ["One"])
                self.assertEqual(observer.after, [expected])
                self.assertEqual(self.doc.UndoNames, ["Accepted enumeration conversion"])
                self.doc.undo()
                self.assertEqual(self.obj.Mode, "One")
                self.doc.redo()
                self.assertEqual(self.obj.Mode, expected)

    def test_native_out_of_range_indices_keep_existing_valueerror_and_before_hook(self):
        # This is the existing native-index rejection path, separate from a
        # failed PyLong conversion. Preserve its current before-only callback.
        observer = self._observer("Mode")
        for value in (-1, 4, _LONG_MIN, _LONG_MAX):
            with self.subTest(value=str(value), native_long_bits=_LONG_BITS):
                self._reset(observer)
                error = self._assign(self.obj, "Mode", value)
                self.assertIsInstance(error, ValueError, repr(error))
                self.assertEqual(self.obj.Mode, "One")
                self.assertEqual(self.obj.getEnumerationsOfProperty("Mode"), self.choices)
                self.assertEqual(observer.before, ["One"])
                self.assertEqual(observer.after, [])

    def test_empty_native_indices_and_existing_type_admission_controls(self):
        empty = self._observer("EmptyMode")
        for value in (_LONG_MIN, _LONG_MAX, -1, True, False, _NativeDigitsInt(2)):
            with self.subTest(empty_value=str(value)):
                self._reset(empty)
                self.assertIsNone(self._assign(self.obj, "EmptyMode", value))
                self.assertIsNone(self.obj.EmptyMode)
                self.assertEqual(empty.before, [])
                self.assertEqual(empty.after, [])
        observer = self._observer("Mode")
        for value in (1.0, _IndexOnly(), object()):
            with self.subTest(rejected_type=type(value).__name__):
                self._reset(observer)
                self.assertIsInstance(self._assign(self.obj, "Mode", value), TypeError)
                self.assertEqual(self.obj.Mode, "One")
                self.assertEqual(observer.before, [])
                self.assertEqual(observer.after, [])
        self.assertIsNone(self._assign(self.obj, "Mode", (["A", "B"], 1)))
        self.assertEqual(self.obj.Mode, "B")
        self.assertEqual(self.obj.getEnumerationsOfProperty("Mode"), ["A", "B"])

    def test_normal_string_selection_and_save_reopen_control(self):
        self.assertIsNone(self._assign(self.obj, "Mode", "二Ω"))
        self.doc.recompute()
        with tempfile.TemporaryDirectory(prefix="fc_enum_boundary_") as temporary:
            path = Path(temporary) / "enumeration.FCStd"
            self.doc.saveAs(str(path))
            self.assertTrue(path.is_file())
            App.closeDocument(self.doc.Name)
            restored = App.openDocument(str(path))
            self.names.append(restored.Name)
            try:
                owner = restored.getObject("Variables")
                self.assertEqual(owner.Mode, "二Ω")
                self.assertEqual(owner.getEnumerationsOfProperty("Mode"), self.choices)
                self.assertIsNone(self._assign(owner, "Mode", 0))
                self.assertEqual(owner.Mode, "Zero")
            finally:
                App.closeDocument(restored.Name)
