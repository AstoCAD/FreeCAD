# SPDX-License-Identifier: LGPL-2.1-or-later

"""Assembly isolation state and argument validation regressions."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import Part
    import AssemblyApp
    import AssemblyGui


class _LengthErrorList(list):
    def __len__(self):
        raise ValueError("isolation sequence length failed")


class _ItemErrorList(list):
    def __getitem__(self, index):
        if index == 1:
            raise LookupError("isolation sequence item failed")
        return super().__getitem__(index)


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestViewProviderAssembly(unittest.TestCase):
    def setUp(self):
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument("AssemblyIsolationTest")
        self.addCleanup(self._cleanup)
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.first = self.assembly.newObject("Part::Box", "First")
        self.second = self.assembly.newObject("Part::Box", "Second")
        self.second.Placement.Base = App.Vector(15, 0, 0)
        self.doc.recompute()
        self.provider = self.assembly.ViewObject
        self.first.Visibility = True
        self.second.Visibility = True
        self.first.ViewObject.Selectable = True
        self.second.ViewObject.Selectable = True

    def _cleanup(self):
        if self.doc.Name in App.listDocuments():
            self.assembly.ViewObject.clearIsolate()
            App.closeDocument(self.doc.Name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    def _state(self):
        return tuple(
            (bool(obj.Visibility), bool(obj.ViewObject.Selectable))
            for obj in (self.first, self.second)
        )

    def _check_rejected_sequence(self, sequence, error_type, message, preexisting=False):
        if preexisting:
            self.provider.isolateComponents([self.second], 2)
            self.assertEqual(self._state(), ((False, True), (True, True)))
        before = self._state()
        error = None
        try:
            self.provider.isolateComponents(sequence, 2)
        except Exception as caught:
            error = caught
        self.assertEqual(
            self._state(), before, "A sequence protocol error changed component isolation"
        )
        self.assertIsInstance(error, error_type)
        self.assertEqual(str(error), message)

    def test_length_error_preserves_visibility_and_original_exception(self):
        self._check_rejected_sequence(
            _LengthErrorList([self.first]), ValueError, "isolation sequence length failed"
        )

    def test_item_error_preserves_visibility_and_original_exception(self):
        self._check_rejected_sequence(
            _ItemErrorList([self.first, self.second]),
            LookupError,
            "isolation sequence item failed",
        )

    def test_item_error_preserves_existing_isolation(self):
        self._check_rejected_sequence(
            _ItemErrorList([self.first, self.second]),
            LookupError,
            "isolation sequence item failed",
            preexisting=True,
        )

    def _check_ordinary(self, values):
        self.provider.isolateComponents(values, 2)
        self.assertEqual(self._state(), ((True, True), (False, True)))
        self.provider.clearIsolate()
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_ordinary_list_control(self):
        self._check_ordinary([self.first])

    def test_ordinary_tuple_control(self):
        self._check_ordinary((self.first,))

    def test_ordinary_mixed_sequence_keeps_ignoring_non_objects(self):
        self._check_ordinary([None, self.first, object()])

    def test_empty_sequence_keeps_isolating_no_components(self):
        self.provider.isolateComponents([], 2)
        self.assertEqual(self._state(), ((False, True), (False, True)))
        self.provider.clearIsolate()
        self.assertEqual(self._state(), ((True, True), (True, True)))

    def test_non_sequence_rejection_control(self):
        before = self._state()
        with self.assertRaises(TypeError):
            self.provider.isolateComponents(object(), 2)
        self.assertEqual(self._state(), before)

    def test_invalid_mode_rejection_control(self):
        before = self._state()
        with self.assertRaises(ValueError):
            self.provider.isolateComponents([self.first], 3)
        self.assertEqual(self._state(), before)
