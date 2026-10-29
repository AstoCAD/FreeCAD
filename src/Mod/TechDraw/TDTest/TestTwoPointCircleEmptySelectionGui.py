# SPDX-License-Identifier: LGPL-2.1-or-later
"""Two-point cosmetic circles preserve pending edits for a whole-view selection.

Only independent public copied edge geometry is observed. Circle identity uses
center and radius without depending on the seam vertex of a transformed circle.
"""

import json
import math
from collections import Counter
import unittest

import FreeCAD as App

if App.GuiUp:
    from TDTest import TestViewLockNoViewSelectionGui as view_lock_fixture
    Gui = view_lock_fixture.Gui
    QtWidgets = view_lock_fixture.QtWidgets


COMMAND = "TechDraw_ExtensionDrawCosmCircle"
VERTEX_NAMES = ("Vertex0", "Vertex1")
UNDO_NAME = "Cosmetic Circle"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestTwoPointCircleEmptySelectionGui(unittest.TestCase):
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

    def _admit_pair(self, fx):
        view = fx["view"]
        require(view.Scale == 1 and view.Rotation.Value == 0,
                "Coordinate admission requires the ordinary unit-scale unrotated fixture")
        points = []
        for index, name in enumerate(VERTEX_NAMES):
            vertex = view.getVertexByIndex(index)
            selected_vertex = view.getVertexBySelection(name)
            require(vertex.ShapeType == "Vertex" and vertex.isValid(),
                    "Control needs an ordinary projected vertex")
            point = self._point_data(vertex.Point)
            require(self._point_data(selected_vertex.Point) == point,
                    "Canonical selected vertex differs from its public geometry index")
            points.append(point)
        require(points[0] != points[1], "Control vertices must be distinct")
        return {"names": VERTEX_NAMES, "indices": (0, 1), "points": points}

    def _invoke(self, fx, command_name):
        require(App.ActiveDocument.Name == fx["doc"].Name, "Owned fixture is not active")
        command = Gui.Command.get(command_name)
        require(command is not None and command.isActive(),
                "The ordinary GUI action must be enabled")
        Gui.runCommand(command_name)
        self.fixture._pump()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Command projection did not settle")
        require(QtWidgets.QApplication.activeModalWidget() is None,
                "These ordinary selection paths must not show a modal dialog")

    def _valid_control(self, reverse):
        import Part
        fx = self.fixture._fixture("CircleVertex1First" if reverse else "CircleVertex0First")
        pair = self._admit_pair(fx)
        subnames = list(reversed(VERTEX_NAMES)) if reverse else list(VERTEX_NAMES)
        self._select(fx, subnames)
        before = self._snapshot(fx)
        base_count = sum(len(before["geometry"][kind]) for kind in ("visible", "hidden"))
        self._invoke(fx, COMMAND)
        after = self._snapshot(fx)
        self.assertEqual(sum(len(after["geometry"][kind]) for kind in ("visible", "hidden")),
                         base_count + 1)
        added_edge = fx["view"].getEdgeByIndex(base_count)
        self.assertIsInstance(added_edge.Curve, Part.Circle)
        added = self._edge_data(added_edge)
        self.assertTrue(added["closed"])
        self.assertGreater(added["radius"], 0)
        self.assertGreater(added["length"], 0)
        self.assertEqual(self._flatten(after["geometry"]),
                         self._flatten(before["geometry"]) +
                         Counter([json.dumps(added, sort_keys=True)]))
        for key in before["model"]:
            if key not in ("visible_lengths", "hidden_lengths"):
                self.assertEqual(after["model"][key], before["model"][key], key)
        self.assertEqual(after["selection"], [])
        self.assertFalse(after["pending"])
        self.assertEqual(after["undo"], [UNDO_NAME])
        self.assertEqual(after["redo"], [])
        fx["doc"].undo()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Undo projection did not settle")
        undone = self._snapshot(fx)
        self.assertEqual(undone["model"], before["model"])
        self.assertEqual(undone["geometry"], before["geometry"])
        self.assertFalse(undone["pending"])
        self.assertEqual(undone["undo"], [])
        self.assertEqual(undone["redo"], [UNDO_NAME])
        fx["doc"].redo()
        fx["doc"].recompute()
        self.fixture._wait(fx["view"].isProjectionReady, "Redo projection did not settle")
        redone = self._snapshot(fx)
        self.assertEqual(redone["model"], after["model"])
        self.assertEqual(redone["geometry"], after["geometry"])
        self.assertFalse(redone["pending"])
        self.assertEqual(redone["undo"], [UNDO_NAME])
        self.assertEqual(redone["redo"], [])
        return {"kind": "valid_vertex1_first" if reverse else "valid_vertex0_first",
                "passed": True, "pair": pair, "before": before, "added": added,
                "after": after, "undone": undone, "redone": redone}

    def _preserve_pending(self, control):
        command_name = "Std_ViewFitAll" if control else COMMAND
        fx = self.fixture._fixture("CirclePendingControl" if control else "CircleEmptyTarget")
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
        self._invoke(fx, command_name)
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

    def test_control_vertex0_first_circle_undo_redo(self):
        self._valid_control(False)

    def test_control_vertex1_first_circle_undo_redo(self):
        self._valid_control(True)

    def test_control_fit_all_preserves_pending_edit(self):
        self._preserve_pending(True)

    def test_view_only_preserves_pending_edit(self):
        self._preserve_pending(False)
