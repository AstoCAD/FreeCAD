# SPDX-License-Identifier: LGPL-2.1-or-later
"""Chain/cascade warnings preserve pending edits without changing valid layouts.

Distance-type controls use genuine parallel horizontal projected-edge references.
They exercise the oblique commands' ordinary Distance path, not diagonal layouts.
Cascade spacing is observed geometrically; no global attribute is read or set.
"""

import copy
import json
import math
import unittest

import FreeCAD as App

if App.GuiUp:
    from TDTest import TestHorizontalChainPendingGui as horizontal_fixture
    Gui = horizontal_fixture.Gui
    QtCore = horizontal_fixture.QtCore
    QtWidgets = horizontal_fixture.QtWidgets


SPECS = (
    {"key": "vertical_chain", "command": "TechDraw_ExtensionPosVertChainDimension",
     "type": "DistanceY", "title": "TechDraw PosVertChainDimension",
     "warning": "No vertical dimensions selected", "undo": "Position Vert Chain Dimension"},
    {"key": "oblique_chain", "command": "TechDraw_ExtensionPosObliqueChainDimension",
     "type": "Distance", "title": "TechDraw PosObliqueChainDimension",
     "warning": "No oblique dimensions selected", "undo": "Position Oblique Chain Dimension"},
    {"key": "cascade_horizontal", "command": "TechDraw_ExtensionCascadeHorizDimension",
     "type": "DistanceX", "title": "TechDraw CascadeHorizDimension",
     "warning": "No horizontal dimensions selected", "undo": "Cascade Horizontal Dimension"},
    {"key": "cascade_vertical", "command": "TechDraw_ExtensionCascadeVertDimension",
     "type": "DistanceY", "title": "TechDraw CascadeVertDimension",
     "warning": "No vertical dimensions selected", "undo": "Cascade Vertical Dimension"},
    {"key": "cascade_oblique", "command": "TechDraw_ExtensionCascadeObliqueDimension",
     "type": "Distance", "title": "TechDraw CascadeObliqueDimension",
     "warning": "No oblique dimensions selected", "undo": "Cascade Oblique Dimension"},
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestChainWarningsPendingGui(unittest.TestCase):
    def setUp(self):
        # This existing guard only needs unittest.skipTest; no CAD mutation precedes it.
        self.profile = horizontal_fixture.view_lock_fixture.TestViewLockNoViewSelectionGui._owned_profile(self)

    def _with_case(self, callback):
        case = horizontal_fixture.TestHorizontalChainPendingGui(
            "test_control_fit_all_preserves_pending_edit")
        try:
            case.setUp()
            return callback(case)
        finally:
            # A fresh contained case owns exactly one document per iteration.
            self.assertTrue(case.doCleanups(), "Owned drawing fixture cleanup failed")

    def _fixture(self, case, spec, suffix):
        import Part
        fx = case.fixture._fixture("Chain97" + spec["key"] + suffix)
        view, document = fx["view"], fx["doc"]
        require(view.Scale == 1 and view.Rotation.Value == 0,
                "Requires the ordinary unit-scale unrotated projection")
        candidates = []
        count = len(view.getVisibleEdges(True)) + len(view.getHiddenEdges(True))
        for index in range(count):
            edge = view.getEdgeByIndex(index)
            if not isinstance(edge.Curve, Part.Line) or len(edge.Vertexes) != 2:
                continue
            first, second = [case._point_data(vertex.Point) for vertex in edge.Vertexes]
            horizontal = first[1:] == second[1:] and first[0] != second[0]
            vertical = first[0] == second[0] and first[2] == second[2] and first[1] != second[1]
            if vertical if spec["type"] == "DistanceY" else horizontal:
                name = "Edge" + str(index)
                require(case._edge_data(view.getEdgeBySelection(name)) == case._edge_data(edge),
                        "Selected projected edge differs from its public index")
                candidates.append(name)
        require(len(candidates) >= 2, "Ordinary projection needs two parallel dimension references")
        dimensions = []
        for index in range(3):
            dimension = document.addObject("TechDraw::DrawViewDimension", "Dimension" + str(index))
            fx["page"].addView(dimension)
            dimension.Type = spec["type"]
            # A third ordinary annotation reuses the first real edge for spacing checks.
            dimension.References2D = [(view, candidates[index % 2])]
            dimension.X = 5 + 4 * index
            dimension.Y = 12 + 12 * index
            dimensions.append(dimension)
        document.recompute()
        case.fixture._wait(view.isProjectionReady, "Dimension projection did not settle")
        for dimension in dimensions:
            require(dimension.isValid() and "Up-to-date" in dimension.State,
                    "Ordinary dimension producer is not valid and up to date")
            require(dimension.Type == spec["type"] and dimension.getRawValue() > 0,
                    "Producer must have its genuine positive dimension type")
            points = dimension.getLinearPoints()
            require(len(points) == 2, "Ordinary dimension must expose two reference points")
            if spec["type"] == "DistanceY":
                require(points[0].x == points[1].x and points[0].y != points[1].y,
                        "DistanceY producer must use a vertical projected edge")
            else:
                require(points[0].y == points[1].y and points[0].x != points[1].x,
                        "Distance/DistanceX producer must use a horizontal projected edge")
        fx["dimensions"] = dimensions
        case.fixture._pump()
        document.clearUndos()
        require(not document.HasPendingTransaction and document.UndoNames == []
                and document.RedoNames == [], "Fixture setup must leave empty history")
        return fx

    def _warning_command(self, case, spec):
        try:
            from PySide import QtTest
        except ImportError:
            from PySide6 import QtTest
        app = QtWidgets.QApplication.instance()
        seen, errors = [], []

        class WarningObserver(QtCore.QObject):
            def eventFilter(self, watched, event):
                if isinstance(watched, QtWidgets.QMessageBox) and event.type() == QtCore.QEvent.Show:
                    record = {"title": watched.windowTitle(), "text": watched.text(), "clicked_ok": False}
                    seen.append(record)

                    def close_warning():
                        try:
                            require(len(seen) == 1, "The action showed multiple warnings")
                            require(record["title"] == spec["title"] and record["text"] == spec["warning"],
                                    "The existing warning title/body differs")
                            require(watched.icon() == QtWidgets.QMessageBox.Warning,
                                    "Expected the existing warning icon")
                            require(watched.standardButtons() == QtWidgets.QMessageBox.Ok,
                                    "Expected exactly the existing OK button")
                            button = watched.button(QtWidgets.QMessageBox.Ok)
                            require(button is not None and button.isVisible() and button.isEnabled(),
                                    "The real warning OK button is not ready")
                            QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
                            require(watched.clickedButton() == button, "Real warning OK click did not close it")
                            record["clicked_ok"] = True
                        except BaseException as error:
                            errors.append(repr(error))
                            try:
                                watched.reject()
                            except RuntimeError:
                                pass
                    QtCore.QTimer.singleShot(0, close_warning)
                return False

        observer = WarningObserver()
        app.installEventFilter(observer)
        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)

        def timeout():
            errors.append("Timed out closing the expected chain/cascade warning")
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QMessageBox) and dialog.windowTitle() == spec["title"]:
                dialog.reject()

        watchdog.timeout.connect(timeout)
        watchdog.start(5000)
        try:
            Gui.runCommand(spec["command"])
        finally:
            watchdog.stop()
            app.removeEventFilter(observer)
        case.fixture._pump()
        require(not errors, "Warning controller failed: " + repr(errors))
        require(len(seen) == 1 and seen[0]["clicked_ok"], "Expected one warning closed by its real OK button")
        return seen[0]

    def _invoke_warning(self, case, fx, spec):
        require(App.ActiveDocument.Name == fx["doc"].Name, "Owned fixture is not active")
        command = Gui.Command.get(spec["command"])
        require(command is not None and command.isActive(), "Ordinary chain/cascade command is not enabled")
        warning = self._warning_command(case, spec)
        case.fixture._pump()
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Warning projection did not settle")
        require(QtWidgets.QApplication.activeModalWidget() is None, "Warning left a modal dialog")
        return warning

    @staticmethod
    def _without_positions(model):
        result = copy.deepcopy(model)
        for dimension in result["dimensions"]:
            dimension.pop("x")
            dimension.pop("y")
        return result

    def _close_position(self, actual, expected):
        # Only calculated annotation coordinates use tolerance; all other snapshots are exact.
        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-8, abs_tol=1e-6),
                        "Annotation position differs: " + repr((actual, expected)))

    def _assert_layout(self, fx, spec, order, before, after):
        original = {row["name"]: row for row in before["model"]["dimensions"]}
        result = {row["name"]: row for row in after["model"]["dimensions"]}
        rows = [result[dimension.Name] for dimension in order]
        master = original[order[0].Name]
        if spec["type"] == "DistanceY":
            font = order[0].ViewObject.Fontsize.Value
            preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
            self.assertEqual(preferences.GetFloat("FontSize", font), font)
            for dimension, row in zip(order, rows):
                self.assertEqual(dimension.ViewObject.Fontsize.Value, font)
                first, second = original[dimension.Name]["points"]
                self._close_position(row["y"] + (first[1] + second[1]) / 2, font / 2)
            axis = "x"
        else:
            axis = "y"
            for dimension, row in zip(order, rows):
                previous = original[dimension.Name]
                if spec["type"] == "DistanceX":
                    self._close_position(row["x"], (previous["points"][0][0] + previous["points"][1][0]) / 2)
                else:
                    self._close_position(row["x"], previous["x"])
        self._close_position(rows[0][axis], master[axis])
        if spec["key"].startswith("cascade_"):
            spacings = [rows[index + 1][axis] - rows[index][axis] for index in range(2)]
            self.assertTrue(all(value > 0 for value in spacings), "Cascade must space positive-side annotations outward")
            self._close_position(spacings[0], spacings[1])
        else:
            for row in rows:
                self._close_position(row[axis], master[axis])

    def _valid_one(self, case, spec, reverse):
        fx = self._fixture(case, spec, "Reverse" if reverse else "Forward")
        order = case._select_dimensions(fx, reverse)
        before = case._snapshot(fx)
        case._invoke(fx, spec["command"])
        after = case._snapshot(fx)
        self.assertNotEqual(after["model"], before["model"], "Valid command must make an actual position change")
        self.assertEqual(self._without_positions(after["model"]), self._without_positions(before["model"]))
        self._assert_layout(fx, spec, order, before, after)
        self.assertEqual(after["geometry"], before["geometry"])
        self.assertEqual(after["selection"], before["selection"])
        self.assertFalse(after["pending"])
        self.assertEqual(after["booked"], 0)
        self.assertEqual((after["undo"], after["redo"]), ([spec["undo"]], []))
        fx["doc"].undo()
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Undo projection did not settle")
        undone = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(undone[key], before[key], key)
        self.assertFalse(undone["pending"])
        self.assertEqual((undone["undo"], undone["redo"]), ([], [spec["undo"]]))
        fx["doc"].redo()
        fx["doc"].recompute()
        case.fixture._wait(fx["view"].isProjectionReady, "Redo projection did not settle")
        redone = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(redone[key], after[key], key)
        self.assertFalse(redone["pending"])
        self.assertEqual((redone["undo"], redone["redo"]), ([spec["undo"]], []))
        # No UID, document name, or transient transaction ID in differential records.
        record = {"command": spec["command"], "reverse": reverse,
                  "before_model": before["model"], "after_model": after["model"],
                  "geometry": before["geometry"], "selected_names": [dimension.Name for dimension in order]}
        print("CHAIN97_CONTROL " + json.dumps(record, sort_keys=True), flush=True)

    def _valid(self, spec):
        for reverse in (False, True):
            with self.subTest(command=spec["command"], reverse=reverse):
                self._with_case(lambda case: self._valid_one(case, spec, reverse))

    def _warning_without_pending(self, case, spec):
        fx = self._fixture(case, spec, "WarningControl")
        case._select(fx, [])
        before = case._snapshot(fx)
        warning = self._invoke_warning(case, fx, spec)
        after = case._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(after[key], before[key], key)
        print("CHAIN97_WARNING_CONTROL " + json.dumps({"command": spec["command"],
              "warning": warning, "before_history": {key: before[key] for key in ("pending", "booked", "undo", "redo")},
              "after_history": {key: after[key] for key in ("pending", "booked", "undo", "redo")}}, sort_keys=True), flush=True)

    def _pending_one(self, case, spec):
        fx = self._fixture(case, spec, "PendingTarget")
        case._select(fx, [])
        self.assertEqual(case._selection()[0][2], ())
        pristine = case._snapshot(fx)
        original_label = fx["container"].Label
        fx["doc"].openTransaction("Unrelated pending edit")
        fx["container"].Label = "Uncommitted container label"
        self.assertTrue(fx["doc"].HasPendingTransaction)
        self.assertEqual((fx["doc"].UndoNames, fx["doc"].RedoNames), (["Unrelated pending edit"], []))
        before = case._snapshot(fx)
        self._invoke_warning(case, fx, spec)
        after = case._snapshot(fx)
        for key in before:
            with self.subTest(command=spec["command"], preserved=key):
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

    def test_control_00_vertical_chain_both_orders(self):
        self._valid(SPECS[0])

    def test_control_01_oblique_chain_both_orders(self):
        self._valid(SPECS[1])

    def test_control_02_cascade_horizontal_both_orders(self):
        self._valid(SPECS[2])

    def test_control_03_cascade_vertical_both_orders(self):
        self._valid(SPECS[3])

    def test_control_04_cascade_oblique_both_orders(self):
        self._valid(SPECS[4])

    def test_control_05_warning_without_pending_all_commands(self):
        for spec in SPECS:
            with self.subTest(command=spec["command"]):
                self._with_case(lambda case: self._warning_without_pending(case, spec))

    def test_control_06_fit_all_preserves_pending_edit(self):
        self._with_case(lambda case: case._preserve_pending(True))

    def test_vertical_chain_warning_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[0]))

    def test_oblique_chain_warning_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[1]))

    def test_cascade_horizontal_warning_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[2]))

    def test_cascade_vertical_warning_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[3]))

    def test_cascade_oblique_warning_preserves_pending_edit(self):
        self._with_case(lambda case: self._pending_one(case, SPECS[4]))
