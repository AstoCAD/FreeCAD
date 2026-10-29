# SPDX-License-Identifier: LGPL-2.1-or-later
"""Ordinary dimension-format commands preserve unrelated pending edits.

Only well-formed fixed-decimal formats and the standard command-generated
prefixes are exercised. Repetition keeps its real prompt before selection
validation; its OK and keyboard Escape paths are observed independently.
"""

import copy
import json
import unittest

import FreeCAD as App

if App.GuiUp:
    from TDTest import TestHorizontalChainPendingGui as horizontal_fixture
    Gui = horizontal_fixture.Gui
    QtCore = horizontal_fixture.QtCore
    QtWidgets = horizontal_fixture.QtWidgets


SPECS = (
    {"key": "diameter", "command": "TechDraw_ExtensionInsertDiameter",
     "initial": "%.2f", "expected": chr(0x2300) + "%.2f", "undo": "Insert Prefix"},
    {"key": "square", "command": "TechDraw_ExtensionInsertSquare",
     "initial": "%.2f", "expected": chr(0x25A1) + "%.2f", "undo": "Insert Prefix"},
    {"key": "repetition", "command": "TechDraw_ExtensionInsertRepetition",
     "initial": "%.2f", "expected": "4" + chr(0x00D7) + " %.2f", "undo": "Insert Prefix"},
    {"key": "remove", "command": "TechDraw_ExtensionRemovePrefixChar",
     "initial": "R %.2f", "expected": "%.2f", "undo": "Remove Prefix"},
    {"key": "increase", "command": "TechDraw_ExtensionIncreaseDecimal",
     "initial": "%.2f", "expected": "%.3f", "undo": "Increase/Decrease Decimal"},
    {"key": "decrease", "command": "TechDraw_ExtensionDecreaseDecimal",
     "initial": "%.2f", "expected": "%.1f", "undo": "Increase/Decrease Decimal"},
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestDimensionFormatPendingGui(unittest.TestCase):
    def setUp(self):
        # The existing guard only needs unittest.skipTest; no CAD mutation precedes it.
        self.profile = horizontal_fixture.view_lock_fixture.TestViewLockNoViewSelectionGui._owned_profile(self)

    def _with_case(self, callback):
        case = horizontal_fixture.TestHorizontalChainPendingGui(
            "test_control_fit_all_preserves_pending_edit")
        try:
            case.setUp()
            return callback(case)
        finally:
            self.assertTrue(case.doCleanups(), "Owned drawing fixture cleanup failed")

    def _fixture(self, case, spec, suffix):
        fx = case._fixture("Format98" + spec["key"] + suffix)
        for dimension in fx["dimensions"]:
            dimension.FormatSpec = spec["initial"]
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Format fixture projection did not settle")
        case.fixture._pump()
        fx["doc"].clearUndos()
        require(not fx["doc"].HasPendingTransaction and fx["doc"].UndoNames == []
                and fx["doc"].RedoNames == [], "Ordinary format setup must leave empty history")
        for dimension in fx["dimensions"]:
            require(dimension.FormatSpec == spec["initial"] and dimension.isValid(),
                    "Ordinary well-formed initial dimension format did not qualify")
        return fx

    def _repetition_prompt(self, case, cancel):
        try:
            from PySide import QtTest
        except ImportError:
            from PySide6 import QtTest
        app = QtWidgets.QApplication.instance()
        main_window = Gui.getMainWindow()
        require(QtWidgets.QApplication.activeModalWidget() is None, "Foreign modal dialog exists")
        seen, errors, owned = [], [], []

        def fail(error):
            errors.append(repr(error))
            if owned:
                try:
                    if QtWidgets.QApplication.activeModalWidget() == owned[0]:
                        owned[0].reject()  # Failure cleanup never counts as a passing Escape.
                except RuntimeError:
                    pass

        def handle(dialog, record):
            try:
                require(QtWidgets.QApplication.activeModalWidget() == dialog,
                        "Prefix Text must be the active owned modal dialog")
                edits = dialog.findChildren(QtWidgets.QLineEdit)
                boxes = dialog.findChildren(QtWidgets.QDialogButtonBox)
                require(len(edits) == 1 and len(boxes) == 1, "Prefix Text fields are not unique")
                edit, box = edits[0], boxes[0]
                require(box.standardButtons() == QtWidgets.QDialogButtonBox.Ok,
                        "Repetition must retain its sole existing OK button")
                button = box.button(QtWidgets.QDialogButtonBox.Ok)
                require(button is not None and button.isVisible() and button.isEnabled()
                        and edit.isVisible() and edit.isEnabled(), "Prefix Text fields are not ready")
                require(edit.text() == "", "New Prefix Text field must initially be empty")
                edit.setFocus()
                case.fixture._wait(lambda: QtWidgets.QApplication.focusWidget() == edit,
                                   "Actual Prefix Text editor did not acquire focus")
                QtTest.QTest.keyClicks(edit, "4")
                require(edit.text() == "4", "Real ordinary ASCII typing did not enter the repetition count")
                record["typed_text"] = edit.text()
                record["ok_text"] = button.text()
                if cancel:
                    QtTest.QTest.keyClick(edit, QtCore.Qt.Key_Escape)
                    require(record["result"] == QtWidgets.QDialog.Rejected and record["rejected"]
                            and not record["accepted"], "Real Escape did not reject Prefix Text")
                    record["closed_by_escape"] = True
                else:
                    QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
                    require(record["result"] == QtWidgets.QDialog.Accepted and record["accepted"]
                            and not record["rejected"], "Real OK click did not accept Prefix Text")
                    record["closed_by_ok"] = True
            except BaseException as error:
                fail(error)

        class PrefixObserver(QtCore.QObject):
            def eventFilter(self, watched, event):
                if (event.type() == QtCore.QEvent.Show and isinstance(watched, QtWidgets.QDialog)
                        and watched.metaObject().className() == "QDialog"
                        and watched.parentWidget() == main_window and watched.windowTitle() == "Prefix Text"):
                    if owned:
                        fail(AssertionError("Repetition showed more than one Prefix Text dialog"))
                    else:
                        owned.append(watched)
                        record = {"title": watched.windowTitle(), "class": watched.metaObject().className(),
                                  "result": None, "accepted": False, "rejected": False,
                                  "closed_by_ok": False, "closed_by_escape": False}
                        seen.append(record)
                        watched.finished.connect(lambda result: record.__setitem__("result", result))
                        watched.accepted.connect(lambda: record.__setitem__("accepted", True))
                        watched.rejected.connect(lambda: record.__setitem__("rejected", True))
                        QtCore.QTimer.singleShot(0, lambda: handle(watched, record))
                return False

        observer = PrefixObserver()
        app.installEventFilter(observer)
        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)

        def timeout():
            if not owned:
                candidates = [widget for widget in app.topLevelWidgets()
                              if isinstance(widget, QtWidgets.QDialog)
                              and widget.metaObject().className() == "QDialog"
                              and widget.parentWidget() == main_window and widget.windowTitle() == "Prefix Text"]
                if len(candidates) == 1:
                    owned.append(candidates[0])
            fail(AssertionError("Timed out handling the owned Prefix Text dialog"))

        watchdog.timeout.connect(timeout)
        watchdog.start(10000)
        try:
            Gui.runCommand(SPECS[2]["command"])
        finally:
            watchdog.stop()
            app.removeEventFilter(observer)
        require(not errors, "Prefix Text controller failed: " + repr(errors))
        require(len(seen) == 1 and seen[0]["closed_by_escape" if cancel else "closed_by_ok"],
                "Expected one real Prefix Text dialog and the requested public close route")
        return seen[0]

    def _invoke(self, case, fx, spec, cancel=False):
        require(App.ActiveDocument.Name == fx["doc"].Name, "Owned format fixture is not active")
        command = Gui.Command.get(spec["command"])
        require(command is not None and command.isActive(), "Ordinary format command is not enabled")
        prompt = None
        if spec["key"] == "repetition":
            prompt = self._repetition_prompt(case, cancel)
            case.fixture._pump()
            fx["doc"].recompute()
            case.fixture._wait(fx["view"].isProjectionReady, "Prefix command projection did not settle")
            require(QtWidgets.QApplication.activeModalWidget() is None, "Prefix Text left a modal dialog")
        else:
            require(not cancel, "Only Repetition has the admitted cancel prompt")
            case._invoke(fx, spec["command"])
        return prompt

    def _valid_one(self, case, spec, mixed):
        fx = self._fixture(case, spec, "MixedViewFirst" if mixed else "Valid")
        case._select_dimensions(fx, False)
        if mixed:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(fx["doc"].Name, fx["view"].Name)
            for dimension in fx["dimensions"]:
                Gui.Selection.addSelection(fx["doc"].Name, dimension.Name)
            self.assertEqual(case._selection(),
                             [(fx["doc"].Name, obj.Name, ())
                              for obj in [fx["view"], *fx["dimensions"]]])
        before = case._snapshot(fx)
        self.assertFalse(before["pending"])
        self.assertEqual(before["booked"], 0)
        self.assertEqual(before["redo"], [])
        expected_undo = [spec["undo"]] + before["undo"]
        expected = copy.deepcopy(before["model"])
        for dimension in expected["dimensions"]:
            dimension["format"]["nominal"] = spec["expected"]
        require(expected != before["model"], "Valid format control must make an actual change")
        prompt = self._invoke(case, fx, spec)
        after = case._snapshot(fx)
        self.assertEqual(after["model"], expected)
        self.assertEqual(after["geometry"], before["geometry"])
        self.assertEqual(after["selection"], before["selection"])
        self.assertFalse(after["pending"])
        self.assertEqual(after["booked"], 0)
        self.assertEqual((after["undo"], after["redo"]), (expected_undo, []))
        fx["doc"].undo()
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Undo projection did not settle")
        undone = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(undone[key], before[key], key)
        self.assertFalse(undone["pending"])
        self.assertEqual((undone["undo"], undone["redo"]), (before["undo"], [spec["undo"]]))
        fx["doc"].redo()
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Redo projection did not settle")
        redone = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(redone[key], after[key], key)
        self.assertFalse(redone["pending"])
        self.assertEqual((redone["undo"], redone["redo"]), (expected_undo, []))
        print("FORMAT98_CONTROL " + json.dumps({"command": spec["command"], "mixed_view_first": mixed,
              "before_model": before["model"], "after_model": after["model"],
              "geometry": before["geometry"],
              "selected_names": [(name, list(subs)) for _doc, name, subs in before["selection"]]},
              sort_keys=True), flush=True)
        if prompt is not None:
            print("FORMAT98_PROMPT " + json.dumps({"command": spec["command"],
                  "mixed_view_first": mixed, "prompt": prompt}, sort_keys=True), flush=True)

    def _valid(self, spec):
        for mixed in (False, True):
            with self.subTest(command=spec["command"], mixed_view_first=mixed):
                self._with_case(lambda case: self._valid_one(case, spec, mixed))

    def _without_pending(self, case, spec):
        fx = self._fixture(case, spec, "NoPending")
        case._select(fx, [])
        self.assertEqual(case._selection()[0][2], ())
        before = case._snapshot(fx)
        prompt = self._invoke(case, fx, spec)
        after = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(after[key], before[key], key)
        print("FORMAT98_VIEW_CONTROL " + json.dumps({"command": spec["command"], "prompt": prompt,
              "before_history": {key: before[key] for key in ("pending", "booked", "undo", "redo")},
              "after_history": {key: after[key] for key in ("pending", "booked", "undo", "redo")}},
              sort_keys=True), flush=True)

    def _pending_one(self, case, spec, cancel=False, selected_dimensions=False):
        fx = self._fixture(case, spec, "CancelDimensions" if selected_dimensions else "PendingView")
        if selected_dimensions:
            case._select_dimensions(fx, False)
        else:
            case._select(fx, [])
            self.assertEqual(case._selection()[0][2], ())
        pristine = case._snapshot(fx)
        original_label = fx["container"].Label
        fx["doc"].openTransaction("Unrelated pending edit")
        fx["container"].Label = "Uncommitted container label"
        self.assertTrue(fx["doc"].HasPendingTransaction)
        self.assertEqual((fx["doc"].UndoNames, fx["doc"].RedoNames), (["Unrelated pending edit"], []))
        before = case._snapshot(fx)
        prompt = self._invoke(case, fx, spec, cancel)
        after = case._snapshot(fx)
        for key in before:
            with self.subTest(command=spec["command"], preserved=key, cancel=cancel):
                self.assertEqual(after[key], before[key])
        fx["doc"].abortTransaction()
        case.fixture._pump()
        aborted = case._snapshot(fx)
        with self.subTest(oracle="abort_restored_label"):
            self.assertEqual(fx["container"].Label, original_label)
        for key in ("model", "geometry", "selection"):
            with self.subTest(oracle="abort_restored_" + key):
                self.assertEqual(aborted[key], pristine[key])
        with self.subTest(oracle="abort_history_match"):
            self.assertEqual((aborted["undo"], aborted["redo"]), (pristine["undo"], pristine["redo"]))
        with self.subTest(oracle="abort_no_pending"):
            self.assertFalse(aborted["pending"])
        if cancel:
            self.assertTrue(prompt["closed_by_escape"])
            print("FORMAT98_CANCEL " + json.dumps({"selected_dimensions": selected_dimensions,
                  "prompt": prompt, "before_model": before["model"], "after_model": after["model"]},
                  sort_keys=True), flush=True)

    def test_control_00_diameter_formats_undo_redo(self):
        self._valid(SPECS[0])

    def test_control_01_square_formats_undo_redo(self):
        self._valid(SPECS[1])

    def test_control_02_repetition_formats_undo_redo(self):
        self._valid(SPECS[2])

    def test_control_03_remove_prefix_formats_undo_redo(self):
        self._valid(SPECS[3])

    def test_control_04_increase_decimal_formats_undo_redo(self):
        self._valid(SPECS[4])

    def test_control_05_decrease_decimal_formats_undo_redo(self):
        self._valid(SPECS[5])

    def test_control_06_fit_all_preserves_pending_edit(self):
        self._with_case(lambda case: case._preserve_pending(True))

    def test_control_07_all_view_selections_without_pending_edit(self):
        for spec in SPECS:
            with self.subTest(command=spec["command"]):
                self._with_case(lambda case: self._without_pending(case, spec))

    def test_control_08_repetition_escape_preserves_dimension_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[2], True, True))

    def test_control_09_repetition_escape_preserves_view_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[2], True, False))

    def test_diameter_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[0]))

    def test_square_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[1]))

    def test_repetition_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[2]))

    def test_remove_prefix_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[3]))

    def test_increase_decimal_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[4]))

    def test_decrease_decimal_view_selection_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[5]))
