# SPDX-License-Identifier: LGPL-2.1-or-later
"""Test constrained integer conversion, clamping, notifications and undo.

PropertyIntegerConstraint and PropertyPercent retain native C-long limits,
accepted types and saved bounds while rejecting overflow before mutation.
"""

import ctypes
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET
import zipfile

import FreeCAD as App

_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p
_LONG_BITS = ctypes.sizeof(ctypes.c_long) * 8
_LONG_MIN = -(1 << (_LONG_BITS - 1))
_LONG_MAX = (1 << (_LONG_BITS - 1)) - 1
_OVERFLOW_VALUES = (_LONG_MIN - 1, _LONG_MAX + 1, -(10**400), 10**400)


class _NativeDigitsInt(int):
    def __int__(self):
        raise AssertionError("A genuine int must retain native PyLong digits")

    def __index__(self):
        raise AssertionError("A genuine int must retain native PyLong digits")

    def __float__(self):
        raise AssertionError("Integer properties must not convert through double")


class _IndexOnly:
    def __init__(self, value):
        self.value = value

    def __index__(self):
        return self.value


class _PropertyObserver:
    def __init__(self, obj, name):
        self.document_name = obj.Document.Name
        self.object_name = obj.Name
        self.name = name
        self.before = []
        self.after = []

    def _matches(self, obj, name):
        return (
            name == self.name
            and obj.Name == self.object_name
            and obj.Document.Name == self.document_name
        )

    def slotBeforeChangeObject(self, obj, name):
        if self._matches(obj, name):
            self.before.append(getattr(obj, name))

    def slotChangedObject(self, obj, name):
        if self._matches(obj, name):
            self.after.append(getattr(obj, name))


class TestIntegerConstraintOverflowApp(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        self.owned_names = []
        self.live_observers = []
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("ConstrainedInteger_" + uuid4().hex[:10])
        self.owned_names.append(self.doc.Name)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyIntegerConstraint", "UnconstrainedValue", "Values")
        self.obj.addProperty("App::PropertyIntegerConstraint", "ConstrainedValue", "Values")
        self.obj.addProperty("App::PropertyPercent", "PercentValue", "Values")
        self.obj.UnconstrainedValue = 37
        self.obj.ConstrainedValue = (37, -5, 50, 3)
        self.obj.PercentValue = 37
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.obj.UnconstrainedValue, 37)
        self.assertEqual(self.obj.ConstrainedValue, 37)
        self.assertEqual(self.obj.PercentValue, 37)

    def _cleanup(self):
        for observer in list(self.live_observers):
            self._remove_observer(observer)
        for name in reversed(self.owned_names):
            if name in App.listDocuments():
                doc = App.getDocument(name)
                if doc.HasPendingTransaction:
                    doc.abortTransaction()
                App.closeDocument(name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    @staticmethod
    def _assign(obj, name, value):
        # Check a pending native error inside the same protected boundary. This
        # never clears or substitutes an exception left by the property setter.
        try:
            setattr(obj, name, value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _reset(self, name, observer=None):
        self.assertIsNone(self._assign(self.obj, name, 37))
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(getattr(self.obj, name), 37)
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)
        if observer is not None:
            observer.before.clear()
            observer.after.clear()

    def _observer(self, name):
        observer = _PropertyObserver(self.obj, name)
        App.addDocumentObserver(observer)
        self.live_observers.append(observer)
        self.assertIsNone(self._assign(self.obj, name, 37))
        self.assertEqual(observer.before, [37], "Qualify the actual before-change hook")
        self.assertEqual(observer.after, [37], "Qualify the actual after-change hook")
        self._reset(name, observer)
        return observer

    def _remove_observer(self, observer):
        if observer in self.live_observers:
            App.removeDocumentObserver(observer)
            self.live_observers.remove(observer)

    def _reject_without_mutation(self, name, value, observer, error_type=OverflowError):
        self._reset(name, observer)
        before = (
            getattr(self.obj, name),
            tuple(self.obj.State),
            self.doc.isTouched(),
            tuple(self.doc.UndoNames),
            tuple(self.doc.RedoNames),
        )
        self.doc.openTransaction("Rejected constrained integer assignment")
        error = self._assign(self.obj, name, value)
        self.doc.commitTransaction()
        with self.subTest(oracle="conversion_exception"):
            self.assertIsInstance(error, error_type, repr(error))
        with self.subTest(oracle="value_unchanged"):
            self.assertEqual(getattr(self.obj, name), before[0])
        with self.subTest(oracle="object_state_unchanged"):
            self.assertEqual(tuple(self.obj.State), before[1])
        with self.subTest(oracle="document_untouched"):
            self.assertEqual(self.doc.isTouched(), before[2])
        with self.subTest(oracle="no_before_callback"):
            self.assertEqual(observer.before, [])
        with self.subTest(oracle="no_after_callback"):
            self.assertEqual(observer.after, [])
        with self.subTest(oracle="undo_redo_unchanged"):
            self.assertEqual(tuple(self.doc.UndoNames), before[3])
            self.assertEqual(tuple(self.doc.RedoNames), before[4])
        with self.subTest(oracle="no_pending_transaction"):
            self.assertFalse(self.doc.HasPendingTransaction)

    def _accepted_undo(self, name, value, expected):
        self._reset(name)
        observer = self._observer(name)
        try:
            self.doc.openTransaction("Accepted constrained integer assignment")
            self.assertIsNone(self._assign(self.obj, name, value))
            self.doc.commitTransaction()
            self.assertEqual(getattr(self.obj, name), expected)
            self.assertEqual(observer.before, [37])
            self.assertEqual(observer.after, [expected])
            self.assertEqual(self.doc.UndoNames, ["Accepted constrained integer assignment"])
            self.doc.recompute()
            self.assertTrue(self.obj.isValid())
            self.doc.undo()
            self.doc.recompute()
            self.assertEqual(getattr(self.obj, name), 37)
            self.doc.redo()
            self.doc.recompute()
            self.assertEqual(getattr(self.obj, name), expected)
        finally:
            self._remove_observer(observer)

    def _scalar_overflow(self, name):
        observer = self._observer(name)
        try:
            for value in _OVERFLOW_VALUES:
                with self.subTest(property=name, value=str(value), native_long_bits=_LONG_BITS):
                    self._reject_without_mutation(name, value, observer)
        finally:
            self._remove_observer(observer)

    def test_unconstrained_native_long_overflow_rejected_before_mutation(self):
        self._scalar_overflow("UnconstrainedValue")

    def test_configured_native_long_overflow_rejected_before_clamping(self):
        self._scalar_overflow("ConstrainedValue")

    def test_percent_native_long_overflow_rejected_before_clamping(self):
        self._scalar_overflow("PercentValue")

    def test_existing_tuple_dict_and_type_rejection_controls(self):
        # Both non-scalar APIs already use checked native-long argument parsing.
        # Their overflow rejection establishes that invalid conversion is not a
        # request to clamp a synthetic -1. All four fields must reject first.
        for name in ("UnconstrainedValue", "ConstrainedValue", "PercentValue"):
            observer = self._observer(name)
            try:
                for value in (37.0, "37", [], object(), _IndexOnly(37)):
                    with self.subTest(property=name, rejected_type=type(value).__name__):
                        self._reject_without_mutation(name, value, observer, TypeError)
                for index, key in enumerate(("value", "min", "max", "step")):
                    for bad in (_LONG_MIN - 1, _LONG_MAX + 1):
                        values = [37, -5, 50, 3]
                        values[index] = bad
                        forms = (
                            tuple(values),
                            dict(zip(("value", "min", "max", "step"), values)),
                        )
                        for form in forms:
                            with self.subTest(
                                property=name, field=key, form=type(form).__name__, value=str(bad)
                            ):
                                self._reject_without_mutation(name, form, observer)
            finally:
                self._remove_observer(observer)

    def test_unconstrained_native_bounds_minus_one_and_subtypes_undo_control(self):
        # No constraints struct means no default int32 clamp, including LP64.
        for value, expected in (
            (_LONG_MIN, _LONG_MIN),
            (_LONG_MAX, _LONG_MAX),
            (-1, -1),
            (0, 0),
            (True, 1),
            (False, 0),
            (_NativeDigitsInt(23), 23),
        ):
            with self.subTest(value=str(value), native_long_bits=_LONG_BITS):
                self._accepted_undo("UnconstrainedValue", value, expected)

    def test_configured_native_bounds_clamp_and_subtypes_undo_control(self):
        for value, expected in (
            (_LONG_MIN, -5),
            (_LONG_MAX, 50),
            (-100, -5),
            (49, 49),
            (-1, -1),
            (True, 1),
            (False, 0),
            (_NativeDigitsInt(22), 22),
        ):
            with self.subTest(value=str(value), expected=expected):
                self._accepted_undo("ConstrainedValue", value, expected)

    def test_percent_existing_zero_to_hundred_clamp_and_undo_control(self):
        for value, expected in (
            (_LONG_MIN, 0),
            (_LONG_MAX, 100),
            (-1, 0),
            (101, 100),
            (0, 0),
            (100, 100),
            (True, 1),
            (False, 0),
            (_NativeDigitsInt(77), 77),
        ):
            with self.subTest(value=str(value), expected=expected):
                self._accepted_undo("PercentValue", value, expected)

    def test_tuple_dict_configuration_and_saved_bounds_control(self):
        self.assertIsNone(self._assign(self.obj, "ConstrainedValue", (-100, -7, 71, 4)))
        self.assertEqual(self.obj.ConstrainedValue, -7)
        self.assertIsNone(self._assign(self.obj, "ConstrainedValue", 100))
        self.assertEqual(self.obj.ConstrainedValue, 71)
        # Existing checked argument parsing admits the index protocol here,
        # unlike the deliberately stricter scalar PyLong_Check branch.
        self.assertIsNone(
            self._assign(
                self.obj,
                "ConstrainedValue",
                (_IndexOnly(40), _IndexOnly(-8), _IndexOnly(72), _IndexOnly(2)),
            )
        )
        self.assertEqual(self.obj.ConstrainedValue, 40)
        self.assertIsNone(
            self._assign(
                self.obj,
                "ConstrainedValue",
                {"value": _IndexOnly(41), "min": -9, "max": 73, "step": 0},
            )
        )
        self.assertEqual(self.obj.ConstrainedValue, 41)
        self.obj.UnconstrainedValue = _LONG_MAX
        self.doc.recompute()
        with tempfile.TemporaryDirectory(prefix="fc_constrained_integer_") as temporary:
            path = Path(temporary) / "constrained_integer.FCStd"
            self.doc.saveAs(str(path))
            self.assertTrue(path.is_file())
            with zipfile.ZipFile(path) as archive:
                document = ET.fromstring(archive.read("Document.xml"))
            properties = [
                p for p in document.iter("Property") if p.attrib.get("name") == "ConstrainedValue"
            ]
            self.assertEqual(len(properties), 1)
            integer = properties[0].find("Integer")
            self.assertIsNotNone(integer)
            self.assertEqual(integer.attrib, {"value": "41", "min": "-9", "max": "73", "step": "1"})
            App.closeDocument(self.doc.Name)
            restored = App.openDocument(str(path))
            self.owned_names.append(restored.Name)
            owner = restored.getObject("Variables")
            self.assertEqual(owner.UnconstrainedValue, _LONG_MAX)
            self.assertEqual(owner.ConstrainedValue, 41)
            self.assertEqual(owner.PercentValue, 37)
            for value, expected in ((_LONG_MIN, -9), (_LONG_MAX, 73), (-1, -1)):
                self.assertIsNone(self._assign(owner, "ConstrainedValue", value))
                self.assertEqual(owner.ConstrainedValue, expected)
            for value, expected in ((_LONG_MIN, 0), (_LONG_MAX, 100), (77, 77)):
                self.assertIsNone(self._assign(owner, "PercentValue", value))
                self.assertEqual(owner.PercentValue, expected)
            restored.recompute()
            self.assertTrue(owner.isValid())
