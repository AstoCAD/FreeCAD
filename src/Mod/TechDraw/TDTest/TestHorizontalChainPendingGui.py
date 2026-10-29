# SPDX-License-Identifier: LGPL-2.1-or-later
"""Horizontal chain alignment preserves unrelated edits when selection is unsuitable.

The existing warning and ordinary alignment behavior are checked through the
actual GUI command. Independent public model, style, and copied edge snapshots
verify pending transactions and Undo/Redo without depending on rendering seams.
"""

import copy
import json
import math
from collections import Counter
import unittest

import FreeCAD as App

if App.GuiUp:
    from TDTest import TestViewLockNoViewSelectionGui as view_lock_fixture
    Gui = view_lock_fixture.Gui
    QtCore = view_lock_fixture.QtCore
    QtWidgets = view_lock_fixture.QtWidgets


COMMAND = "TechDraw_ExtensionPosHorizChainDimension"
UNDO_NAME = "Position Horizontal Chain Dimension"
WARNING_TITLE = "TechDraw PosHorizChainDimension"
WARNING_TEXT = "No horizontal dimensions selected"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestHorizontalChainPendingGui(unittest.TestCase):
    def setUp(self):
        self.fixture = view_lock_fixture.TestViewLockNoViewSelectionGui(
            "test_control_empty_selection_preserves_pending_edit")
        # The portable owned-profile guard precedes all GUI/model mutations.
        self.profile = self.fixture._owned_profile()
        self.addCleanup(self._cleanup_fixture)
        self.fixture.setUp()

    def _cleanup_fixture(self):
        self.assertTrue(self.fixture.doCleanups(), "Owned drawing fixture cleanup failed")

    def _point_data(self, point):
        values = tuple(float(value) for value in (point.x, point.y, point.z))
        require(all(math.isfinite(value) for value in values), "Fixture point is not finite")
        return tuple(round(value, 9) for value in values)

    def _edge_data(self, edge):
        import Part
        require(edge.ShapeType == "Edge" and edge.isValid(), "Copied view edge is invalid")
        curve = edge.Curve
        box = edge.BoundBox
        result = {
            "curve": type(curve).__name__,
            "length": round(edge.Length, 9),
            "closed": bool(edge.isClosed()),
            "bounds": tuple(round(value, 9) for value in
                            (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)),
        }
        if isinstance(curve, Part.Circle):
            # A transformed full circle can choose a different seam vertex.
            result["center"] = self._point_data(curve.Center)
            result["radius"] = round(curve.Radius, 9)
        else:
            points = tuple(self._point_data(vertex.Point) for vertex in edge.Vertexes)
            result["points"] = min(points, tuple(reversed(points)))
        return result

    def _geometry(self, view):
        # Only independent public Part edge copies; no cosmetic wrappers/properties.
        return {
            kind: sorted((self._edge_data(edge) for edge in edges),
                         key=lambda value: json.dumps(value, sort_keys=True))
            for kind, edges in (
                ("visible", view.getVisibleEdges(True)), ("hidden", view.getHiddenEdges(True)))
        }

    def _flatten(self, data):
        return Counter(json.dumps(edge, sort_keys=True)
                       for kind in ("visible", "hidden") for edge in data[kind])

    def _selection(self):
        return [(item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
                for item in Gui.Selection.getSelectionEx()]

    def _snapshot(self, fx):
        model = self.fixture._model(fx)
        view = fx["view"]
        model["view_fields"] = {
            "x": view.X.Value, "y": view.Y.Value, "rotation": view.Rotation.Value,
            "scale": view.Scale, "scale_type": str(view.ScaleType),
            "direction": self._point_data(view.Direction), "x_direction": self._point_data(view.XDirection),
        }
        model["dimensions"] = [self._dimension_data(dimension) for dimension in fx["dimensions"]]
        return {"model": model, "geometry": self._geometry(view), "selection": self._selection(),
                "pending": bool(fx["doc"].HasPendingTransaction),
                "booked": fx["doc"].getBookedTransactionID(),
                "undo": list(fx["doc"].UndoNames), "redo": list(fx["doc"].RedoNames)}

    def _select(self, fx, subnames):
        Gui.Selection.clearSelection()
        if subnames:
            for subname in subnames:
                Gui.Selection.addSelection(fx["doc"].Name, fx["view"].Name, subname)
        else:
            Gui.Selection.addSelection(fx["doc"].Name, fx["view"].Name)
        actual = self._selection()
        require(actual == [(fx["doc"].Name, fx["view"].Name, tuple(subnames))],
                "Actual SelectionEx names/order differ from the ordinary TD selection")
        return actual

    def _dimension_data(self, dimension):
        vp = dimension.ViewObject
        return {
            "name": dimension.Name, "label": dimension.Label,
            "type": str(dimension.Type), "measure_type": str(dimension.MeasureType),
            "references2d": [(obj.Name, tuple(subs)) for obj, subs in dimension.References2D],
            "references3d": [(obj.Name if obj is not None else None, tuple(subs))
                             for obj, subs in dimension.References3D],
            "x": round(dimension.X.Value, 9), "y": round(dimension.Y.Value, 9),
            "raw_value": round(dimension.getRawValue(), 9),
            "points": [self._point_data(point) for point in dimension.getLinearPoints()],
            "valid": bool(dimension.isValid()),
            "format": {
                "nominal": dimension.FormatSpec,
                "over": dimension.FormatSpecOverTolerance,
                "under": dimension.FormatSpecUnderTolerance,
                "arbitrary": bool(dimension.Arbitrary),
                "arbitrary_tolerances": bool(dimension.ArbitraryTolerances),
                "show_units": bool(dimension.ShowUnits),
            },
            "style": {
                "font": vp.Font, "font_size": vp.Fontsize.Value,
                "arrow_size": vp.Arrowsize.Value, "arrow_style": str(vp.ArrowStyle),
                "line_width": vp.LineWidth.Value, "color": tuple(vp.Color),
                "standard": str(vp.StandardAndStyle), "extent": str(vp.RenderingExtent),
                "flip": bool(vp.FlipArrowheads), "gap_iso": vp.GapFactorISO,
                "gap_asme": vp.GapFactorASME, "spacing_iso": vp.LineSpacingFactorISO,
                "allow_snap": bool(vp.AllowSnap),
            },
        }

    def _fixture(self, suffix):
        import Part
        fx = self.fixture._fixture("Chain93" + suffix)
        view, document = fx["view"], fx["doc"]
        require(view.Scale == 1 and view.Rotation.Value == 0,
                "Requires the ordinary unit-scale unrotated projection")
        count = len(view.getVisibleEdges(True)) + len(view.getHiddenEdges(True))
        horizontal = []
        for index in range(count):
            edge = view.getEdgeByIndex(index)
            if not isinstance(edge.Curve, Part.Line) or len(edge.Vertexes) != 2:
                continue
            points = tuple(self._point_data(vertex.Point) for vertex in edge.Vertexes)
            if points[0][1:] == points[1][1:] and points[0][0] != points[1][0]:
                name = "Edge" + str(index)
                require(self._edge_data(view.getEdgeBySelection(name)) == self._edge_data(edge),
                        "Ordinary selected horizontal edge differs from its public index")
                horizontal.append((name, self._edge_data(edge)))
        require(len(horizontal) >= 2, "The ordinary box needs two horizontal projected edges")
        dimensions = []
        for index, (edge_name, copied_edge) in enumerate(horizontal[:2]):
            dimension = document.addObject("TechDraw::DrawViewDimension",
                                           "DimensionA" if index == 0 else "DimensionB")
            fx["page"].addView(dimension)
            dimension.Type = "DistanceX"
            dimension.References2D = [(view, edge_name)]
            dimension.X = 5 if index == 0 else 9
            dimension.Y = 12 if index == 0 else 24
            dimensions.append(dimension)
        document.recompute()
        self.fixture._wait(view.isProjectionReady, "Dimension producer projection did not settle")
        for dimension in dimensions:
            require(dimension.isValid() and "Up-to-date" in dimension.State,
                    "Ordinary DistanceX producer is not valid and up to date")
            require(dimension.Type == "DistanceX" and dimension.getRawValue() > 0,
                    "Producer must be a positive ordinary horizontal dimension")
            points = dimension.getLinearPoints()
            require(len(points) == 2 and points[0].x != points[1].x,
                    "Ordinary DistanceX points must span a nonzero horizontal distance")
        fx["dimensions"] = dimensions
        fx["producer_edges"] = horizontal[:2]
        self.fixture._pump()
        document.clearUndos()
        require(not document.HasPendingTransaction and document.UndoNames == [] and
                document.RedoNames == [], "Dimension setup must leave empty history")
        return fx

    def _select_dimensions(self, fx, reverse):
        dimensions = list(reversed(fx["dimensions"])) if reverse else fx["dimensions"]
        Gui.Selection.clearSelection()
        for dimension in dimensions:
            Gui.Selection.addSelection(fx["doc"].Name, dimension.Name)
        self.assertEqual(self._selection(),
                         [(fx["doc"].Name, dimension.Name, ()) for dimension in dimensions])
        return dimensions

    def _invoke(self, fx, command_name, expect_warning=False):
        require(App.ActiveDocument.Name == fx["doc"].Name, "Owned fixture is not active")
        command = Gui.Command.get(command_name)
        require(command is not None and command.isActive(), "Ordinary command is not enabled")
        warning = self._run_warning_command(command_name) if expect_warning else None
        if not expect_warning:
            Gui.runCommand(command_name)
        self.fixture._pump()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Command projection did not settle")
        require(QtWidgets.QApplication.activeModalWidget() is None,
                "The ordinary action must not leave a modal dialog")
        return warning

    def _run_warning_command(self, command_name):
        try:
            from PySide import QtTest
        except ImportError:
            from PySide6 import QtTest
        app = QtWidgets.QApplication.instance()
        seen, errors = [], []
        fixture = self.fixture

        class WarningObserver(QtCore.QObject):
            def eventFilter(self, watched, event):
                if isinstance(watched, QtWidgets.QMessageBox) and event.type() == QtCore.QEvent.Show:
                    record = {"title": watched.windowTitle(), "text": watched.text(),
                              "icon": str(watched.icon()),
                              "buttons": str(watched.standardButtons()), "clicked_ok": False}
                    seen.append(record)

                    def close_warning():
                        try:
                            require(len(seen) == 1, "The action showed multiple warnings")
                            require(record["title"] == WARNING_TITLE and
                                    record["text"] == WARNING_TEXT,
                                    "The action warning title/body differs")
                            require(watched.icon() == QtWidgets.QMessageBox.Warning,
                                    "Expected the existing warning icon")
                            require(watched.standardButtons() == QtWidgets.QMessageBox.Ok,
                                    "Expected exactly the existing OK button")
                            button = watched.button(QtWidgets.QMessageBox.Ok)
                            require(button is not None and button.isVisible() and button.isEnabled(),
                                    "The real warning OK button is not ready")
                            record["ok_text"] = button.text()
                            QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
                            require(watched.clickedButton() == button,
                                    "The real OK click did not close the warning")
                            record["clicked_ok"] = True
                        except BaseException as exc:
                            errors.append(repr(exc))
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
            errors.append("Timed out closing the expected chain warning")
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QMessageBox) and dialog.windowTitle() == WARNING_TITLE:
                dialog.reject()

        watchdog.timeout.connect(timeout)
        watchdog.start(5000)
        try:
            Gui.runCommand(command_name)
        finally:
            watchdog.stop()
            app.removeEventFilter(observer)
        fixture._pump()
        require(not errors, "Warning controller failed: " + repr(errors))
        require(len(seen) == 1 and seen[0]["clicked_ok"],
                "The actual warning must be captured and closed with its real OK button")
        return seen[0]

    def _valid_control(self, reverse):
        fx = self._fixture("Reverse" if reverse else "Forward")
        dimensions = self._select_dimensions(fx, reverse)
        before = self._snapshot(fx)
        expected_model = copy.deepcopy(before["model"])
        master_y = round(dimensions[0].Y.Value, 9)
        for entry in expected_model["dimensions"]:
            entry["x"] = round((entry["points"][0][0] + entry["points"][1][0]) / 2, 9)
            entry["y"] = master_y
        require(expected_model != before["model"], "Alignment control must make a real change")
        warning = self._invoke(fx, COMMAND)
        self.assertIsNone(warning)
        after = self._snapshot(fx)
        self.assertEqual(after["model"], expected_model)
        self.assertEqual(after["geometry"], before["geometry"])
        self.assertEqual(after["selection"], before["selection"])
        self.assertFalse(after["pending"])
        self.assertEqual(after["undo"], [UNDO_NAME])
        self.assertEqual(after["redo"], [])
        fx["doc"].undo()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Undo projection did not settle")
        undone = self._snapshot(fx)
        self.assertEqual(undone["model"], before["model"])
        self.assertEqual(undone["geometry"], before["geometry"])
        self.assertEqual(undone["selection"], before["selection"])
        self.assertFalse(undone["pending"])
        self.assertEqual(undone["undo"], [])
        self.assertEqual(undone["redo"], [UNDO_NAME])
        fx["doc"].redo()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Redo projection did not settle")
        redone = self._snapshot(fx)
        self.assertEqual(redone["model"], after["model"])
        self.assertEqual(redone["geometry"], after["geometry"])
        self.assertEqual(redone["selection"], after["selection"])
        self.assertFalse(redone["pending"])
        self.assertEqual(redone["undo"], [UNDO_NAME])
        self.assertEqual(redone["redo"], [])
        return {"kind": "valid_reverse" if reverse else "valid_forward", "passed": True,
                "producer_edges": fx["producer_edges"], "expected_model": expected_model,
                "before": before, "after": after, "undone": undone, "redone": redone}

    def _warning_control(self):
        fx = self._fixture("WarningControl")
        self._select(fx, [])
        self.assertEqual(self._selection()[0][2], ())
        before = self._snapshot(fx)
        warning = self._invoke(fx, COMMAND, True)
        after = self._snapshot(fx)
        for key in ("model", "geometry", "selection"):
            self.assertEqual(after[key], before[key], key)
        # The empty command's history is recorded, not assumed correct by this control.
        return {"kind": "warning_without_pending_control", "passed": True,
                "warning": warning, "before": before, "after": after}

    def _preserve_pending(self, control):
        command_name = "Std_ViewFitAll" if control else COMMAND
        fx = self._fixture("PendingControl" if control else "PendingTarget")
        self._select(fx, [])
        self.assertEqual(self._selection()[0][2], ())
        pristine = self._snapshot(fx)
        original_label = fx["container"].Label
        fx["doc"].openTransaction("Unrelated pending edit")
        fx["container"].Label = "Uncommitted container label"
        self.assertTrue(fx["doc"].HasPendingTransaction)
        self.assertEqual(fx["doc"].UndoNames, ["Unrelated pending edit"])
        self.assertEqual(fx["doc"].RedoNames, [])
        before = self._snapshot(fx)
        self._invoke(fx, command_name, not control)
        after = self._snapshot(fx)
        for key in before:
            with self.subTest(preserved=key):
                self.assertEqual(after[key], before[key])
        fx["doc"].abortTransaction()
        self.fixture._pump()
        aborted = self._snapshot(fx)
        with self.subTest(oracle="abort_restored_label"):
            self.assertEqual(fx["container"].Label, original_label)
        with self.subTest(oracle="abort_restored_model"):
            self.assertEqual(aborted["model"], pristine["model"])
        with self.subTest(oracle="abort_restored_geometry"):
            self.assertEqual(aborted["geometry"], pristine["geometry"])
        with self.subTest(oracle="abort_restored_selection"):
            self.assertEqual(aborted["selection"], pristine["selection"])
        with self.subTest(oracle="abort_history_match"):
            self.assertEqual((aborted["undo"], aborted["redo"]),
                             (pristine["undo"], pristine["redo"]))
        with self.subTest(oracle="abort_no_pending"):
            self.assertFalse(aborted["pending"])

    def test_control_alignment_forward_undo_redo(self):
        self._valid_control(False)

    def test_control_alignment_reverse_undo_redo(self):
        self._valid_control(True)

    def test_control_warning_without_pending_edit(self):
        self._warning_control()

    def test_control_fit_all_preserves_pending_edit(self):
        self._preserve_pending(True)

    def test_view_only_warning_preserves_pending_edit(self):
        self._preserve_pending(False)
