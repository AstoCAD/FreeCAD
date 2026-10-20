# SPDX-License-Identifier: LGPL-2.1-or-later
"""Scalar PropertyMatrix tuple integer conversion must fail before mutation.

Preserve native C-long admission, float/native Matrix paths and tuple order.
Vector and generic list fallback behavior are outside this regression module.
"""

import ctypes
import unittest
from uuid import uuid4

import FreeCAD as App

_checked_error_boundary = ctypes.pythonapi.PyErr_Occurred
_checked_error_boundary.argtypes = ()
_checked_error_boundary.restype = ctypes.c_void_p
_LONG_BITS = ctypes.sizeof(ctypes.c_long) * 8
_LONG_MIN = -(1 << (_LONG_BITS - 1))
_LONG_MAX = (1 << (_LONG_BITS - 1)) - 1


class _IntWithoutFloatOverride(int):
    def __float__(self):
        raise AssertionError("Genuine integer tuple components must retain PyLong semantics")


class _FloatWithoutOverride(float):
    def __float__(self):
        raise AssertionError("Genuine float tuple components must retain PyFloat semantics")


class _FloatOnly:
    def __float__(self):
        return 12.5


class _IndexOnly:
    def __index__(self):
        return 12


def _snapshot_property(owner, name):
    value = getattr(owner, name)
    return tuple(
        getattr(value, "A%d%d" % (row + 1, col + 1)) for row in range(4) for col in range(4)
    )


class _GeoPropertyObserver:
    def __init__(self, owner, name):
        self.document_name, self.object_name = owner.Document.Name, owner.Name
        self.name = name
        self.before, self.after = [], []

    def _matches(self, owner, name):
        return (
            name == self.name
            and owner.Name == self.object_name
            and owner.Document.Name == self.document_name
        )

    def slotBeforeChangeObject(self, owner, name):
        if self._matches(owner, name):
            self.before.append(_snapshot_property(owner, name))

    def slotChangedObject(self, owner, name):
        if self._matches(owner, name):
            self.after.append(_snapshot_property(owner, name))


class TestPropertyMatrixIntegerOverflow(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument("MatrixIntegerBoundary_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::VarSet", "Variables")
        self.obj.addProperty("App::PropertyMatrix", "MatrixValue", "Values")
        matrix = App.Matrix()
        matrix.A14, matrix.A21 = 2.5, -4.75
        self.obj.MatrixValue = matrix
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)
        self.initial = {"MatrixValue": _snapshot_property(self.obj, "MatrixValue")}

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    @staticmethod
    def _assign(owner, name, value):
        # PyDLL checks a pending native exception immediately after setattr.
        # Keep the boundary in the try so old success-with-exception setters
        # do not leak an error into unrelated test code.
        try:
            setattr(owner, name, value)
            _checked_error_boundary()
        except BaseException as error:
            return error
        return None

    def _reset(self, name, observer=None):
        self.assertIsNone(self._assign(self.obj, name, self._native_initial(name)))
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertEqual(_snapshot_property(self.obj, name), self.initial[name])
        self.assertFalse(self.doc.isTouched())
        self.assertFalse(self.doc.HasPendingTransaction)
        if observer is not None:
            observer.before.clear()
            observer.after.clear()

    def _observer(self, name):
        observer = _GeoPropertyObserver(self.obj, name)
        App.addDocumentObserver(observer)
        self.addCleanup(App.removeDocumentObserver, observer)
        self.assertIsNone(self._assign(self.obj, name, self._native_initial(name)))
        self.assertEqual(len(observer.before), 1, "Real before-change observer control")
        self.assertEqual(len(observer.after), 1, "Real after-change observer control")
        return observer

    def _rejection(self, name, value, observer, error_type=OverflowError):
        self._reset(name, observer)
        before = (
            _snapshot_property(self.obj, name),
            tuple(self.obj.State),
            self.doc.isTouched(),
            tuple(self.doc.UndoNames),
            tuple(self.doc.RedoNames),
        )
        self.doc.openTransaction("Rejected geometric tuple assignment")
        error = self._assign(self.obj, name, value)
        self.doc.commitTransaction()
        with self.subTest(oracle="conversion_exception"):
            self.assertIsInstance(error, error_type, repr(error))
        with self.subTest(oracle="value_unchanged"):
            self.assertEqual(_snapshot_property(self.obj, name), before[0])
        with self.subTest(oracle="object_state_unchanged"):
            self.assertEqual(tuple(self.obj.State), before[1])
        with self.subTest(oracle="document_untouched"):
            self.assertEqual(self.doc.isTouched(), before[2])
        with self.subTest(oracle="no_before_change_callback"):
            self.assertEqual(observer.before, [])
        with self.subTest(oracle="no_after_change_callback"):
            self.assertEqual(observer.after, [])
        with self.subTest(oracle="undo_redo_unchanged"):
            self.assertEqual(tuple(self.doc.UndoNames), before[3])
            self.assertEqual(tuple(self.doc.RedoNames), before[4])
        self.assertFalse(self.doc.HasPendingTransaction)

    def _accepted_undo(self, name, value, expected):
        self._reset(name)
        observer = self._observer(name)
        self._reset(name, observer)
        self.doc.openTransaction("Ordinary geometric assignment")
        self.assertIsNone(self._assign(self.obj, name, value))
        self.doc.commitTransaction()
        self.assertEqual(_snapshot_property(self.obj, name), expected)
        self.assertEqual(observer.before, [self.initial[name]])
        self.assertEqual(observer.after, [expected])
        self.assertEqual(self.doc.UndoNames, ["Ordinary geometric assignment"])
        self.doc.recompute()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(_snapshot_property(self.obj, name), self.initial[name])
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(_snapshot_property(self.obj, name), expected)

    def _native_initial(self, name):
        matrix = App.Matrix()
        for row in range(4):
            for col in range(4):
                setattr(matrix, "A%d%d" % (row + 1, col + 1), self.initial[name][row * 4 + col])
        return matrix

    def test_matrix_overflow_rejected_in_each_cell_without_mutation(self):
        observer = self._observer("MatrixValue")
        for index in range(16):
            for invalid in (_LONG_MIN - 1, _LONG_MAX + 1, 10**400, -(10**400)):
                with self.subTest(
                    tuple_index=index,
                    magnitude="huge" if abs(invalid) > 10**100 else str(invalid),
                    c_long_bits=_LONG_BITS,
                ):
                    value = list(range(16))
                    value[index] = invalid
                    self._rejection("MatrixValue", tuple(value), observer)

    def test_matrix_tuple_order_types_and_native_matrix_undo_controls(self):
        value = tuple(
            [True, _IntWithoutFloatOverride(-1), _FloatWithoutOverride(2.5)]
            + [i + 0.25 for i in range(3, 16)]
        )
        # Existing tuple conversion is column-major: cMatrix[x][y] = value[x + 4*y].
        ordinary = [1.0, -1.0, 2.5] + [i + 0.25 for i in range(3, 16)]
        expected = tuple(ordinary[row + col * 4] for row in range(4) for col in range(4))
        self._accepted_undo("MatrixValue", value, expected)
        matrix = App.Matrix()
        matrix.A11, matrix.A23, matrix.A34 = 2.5, -7.25, 12.0
        native_expected = tuple(
            getattr(matrix, "A%d%d" % (row + 1, col + 1)) for row in range(4) for col in range(4)
        )
        self._accepted_undo("MatrixValue", matrix, native_expected)

    def test_matrix_malformed_and_non_native_numeric_type_controls(self):
        observer = self._observer("MatrixValue")
        values = [list(range(16)), tuple(range(15)), tuple(range(17))]
        for item in (None, "1", _FloatOnly(), _IndexOnly()):
            value = list(range(16))
            value[9] = item
            values.append(tuple(value))
        for index, value in enumerate(values):
            with self.subTest(case=index, value_type=type(value).__name__):
                self._rejection("MatrixValue", value, observer, TypeError)

    def test_existing_c_long_bounds_and_minus_one_sentinel_controls(self):
        for numeric in (_LONG_MIN, -1, 0, _LONG_MAX):
            with self.subTest(value=numeric, c_long_bits=_LONG_BITS):
                self.assertIsNone(self._assign(self.obj, "MatrixValue", (numeric,) * 16))
                self.assertEqual(
                    _snapshot_property(self.obj, "MatrixValue"), (float(numeric),) * 16
                )
