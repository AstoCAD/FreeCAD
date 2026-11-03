# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sketcher endpoint releases preserve the preview for short and long drags."""

import importlib
import math
import os
from pathlib import Path
import stat
import unittest
from uuid import uuid4


def _plain_path(path):
    for component in (path, *path.parents):
        try:
            if component.is_symlink():
                return False
            junction = getattr(component, "is_junction", None)
            if junction is not None and junction():
                return False
            attributes = getattr(component.lstat(), "st_file_attributes", 0)
            if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                return False
        except FileNotFoundError:
            continue
        except OSError:
            return False
    return True


def _owned_profile():
    selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
    if not selected:
        raise unittest.SkipTest("Requires an explicitly selected disposable GUI profile")
    configured = os.environ.get("FREECAD_USER_HOME")
    if not configured:
        raise RuntimeError("FREECAD_USER_HOME must select the disposable profile")
    raw = Path(selected)
    home = Path(configured)
    for path in (raw, home):
        if not path.is_absolute() or not _plain_path(path):
            raise RuntimeError("Disposable profile paths must be absolute and free of links")
    profile = raw.resolve(strict=True)
    if not profile.is_dir() or home.resolve(strict=True) != profile:
        raise RuntimeError("FREECAD_USER_HOME must select the existing disposable profile")
    return profile


class TestDragReleaseGui(unittest.TestCase):
    def setUp(self):
        profile = _owned_profile()
        self.app = importlib.import_module("FreeCAD")
        if not self.app.GuiUp:
            self.skipTest("Requires the native GUI")
        paths = {
            "UserParameter": Path(self.app.ConfigGet("UserParameter")),
            "UserAppData": Path(self.app.getUserAppDataDir()),
        }
        system = self.app.ConfigGet("SystemParameter")
        if system:
            paths["SystemParameter"] = Path(system)
        for key, path in paths.items():
            self.assertTrue(path.is_absolute() and _plain_path(path), key)
            self.assertTrue(path.resolve().is_relative_to(profile), key)
        self.assertEqual(paths["UserParameter"].resolve(), profile / "user.cfg")
        if "SystemParameter" in paths:
            self.assertEqual(paths["SystemParameter"].resolve(), profile / "system.cfg")
        self.assertEqual(self.app.listDocuments(), {})

        self.gui = importlib.import_module("FreeCADGui")
        self.part = importlib.import_module("Part")
        importlib.import_module("Sketcher")
        self.core = importlib.import_module("PySide.QtCore")
        self.widgets = importlib.import_module("PySide.QtWidgets")
        self.coin = importlib.import_module("pivy.coin")
        self.assertIsNotNone(self.gui.getMainWindow())
        self.assertFalse(self.gui.Control.activeDialog())
        self.assertIsNone(self.widgets.QApplication.activeModalWidget())
        self.assertIsNone(self.widgets.QApplication.activePopupWidget())

        previous = self.gui.activeWorkbench()
        if previous:
            self.addCleanup(self.gui.activateWorkbench, previous.name())
        self.gui.activateWorkbench("SketcherWorkbench")
        helpers = importlib.import_module("SketcherTests.GuiTestCase")
        self.gui_helpers = helpers.SketcherGuiTestCase()
        snap = self.app.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/Snap")
        self.addCleanup(self._restore_snap, snap, "Snap" in snap.GetBools(),
                        snap.GetBool("Snap", True))
        snap.SetBool("Snap", False)

        self.doc = self.app.newDocument("SketchDragRelease_" + uuid4().hex[:12])
        self.doc_name = self.doc.Name
        self.doc_uid = str(self.doc.Uid)
        self.addCleanup(self._close_owned_document)
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.original_start = self.app.Vector(-10, 8, 0)
        self.original_end = self.app.Vector(10, 8, 0)
        self.sketch.addGeometry(self.part.LineSegment(
            self.original_start, self.original_end), False)
        self.sketch.ViewObject.Autoconstraints = False
        self.sketch.ViewObject.ShowGrid = False
        self.doc.recompute()
        self.gui_doc = self.gui.getDocument(self.doc_name)
        self.assertTrue(self.gui_doc.setEdit(self.sketch.Name))
        self.view = self.gui_doc.activeView()
        self.view.setNavigationType("Gui::CADNavigationStyle")
        self.view.setCamera(
            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
            "orientation 0 0 1 0 focalDistance 100 height 80 }"
        )
        self._pump(200)
        self.viewer = self.view.getViewer()
        self.viewport = self.view.graphicsView().viewport()
        self.assertGreater(self.viewport.width(), 200)
        self.assertGreater(self.viewport.height(), 200)
        self.assertTrue(self.viewport.isVisible())
        self.viewport.setFocus(self.core.Qt.OtherFocusReason)
        self.gui.Selection.clearSelection()
        self.gui.Selection.clearPreselection()
        self.mouse_down = False
        self.addCleanup(self._release_mouse)
        self._pump(30)
        self.assertEqual(self.gui_doc.getInEdit().Object, self.sketch)
        self.assertTrue(self.gui.Control.activeDialog(self.gui_doc))
        self.assertFalse(self.sketch.ViewObject.Autoconstraints)
        self.assertFalse(snap.GetBool("Snap", True))
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.undo_before = self.doc.UndoCount
        self.pick_radius = self.viewer.getPickRadius()
        self.scale = self.viewport.devicePixelRatioF()
        self.assertGreater(self.pick_radius, 3)
        self.assertGreater(self.scale, 0)
        self.start = self._qpoint(self.original_end)
        self.last_point = self.start
        self._assert_endpoint_pick(self.start)
        self._assert_drawn(self.original_start)
        self._assert_drawn(self.original_end)

    @staticmethod
    def _restore_snap(preferences, present, value):
        if present:
            preferences.SetBool("Snap", value)
        else:
            preferences.RemBool("Snap")

    def _close_owned_document(self):
        owned = self.app.listDocuments().get(self.doc_name)
        if owned is None:
            return
        self.assertEqual(str(owned.Uid), self.doc_uid)
        try:
            gui_doc = self.gui.getDocument(self.doc_name)
            if gui_doc.getInEdit():
                gui_doc.resetEdit()
                self._pump(30)
            if self.gui.Control.activeDialog(gui_doc):
                self.gui.Control.closeDialog(gui_doc)
            if owned.HasPendingTransaction:
                owned.abortTransaction()
            self.gui.Selection.clearSelection()
            self.gui.Selection.clearPreselection()
        finally:
            self.app.closeDocument(self.doc_name)
        self.assertEqual(self.app.listDocuments(), {})

    def _pump(self, milliseconds=30):
        loop = self.core.QEventLoop()
        self.core.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        self.gui.updateGui()

    def _qpoint(self, vector):
        return self.gui_helpers.viewport_to_qpoint(
            self.view, self.viewport, self.view.getPointOnScreen(vector))

    def _device(self, point):
        # Convert the public Qt event position to the Coin viewport convention.
        return (
            math.floor(point.x() * self.scale + 0.5),
            math.floor((self.viewport.height() - point.y() - 1) * self.scale + 0.5),
        )

    def _world(self, point):
        vector = self.view.getPoint(*self._device(point))
        self.assertAlmostEqual(vector.z, 0, places=5)
        return vector

    def _preselection_at(self, point):
        self._move(point, self.core.Qt.NoButton)
        self._pump(30)
        preselection = self.gui.Selection.getPreselection()
        return preselection

    def _assert_endpoint_pick(self, point):
        # Sketcher's edit root performs its own preselection. A document-scene
        # getObjectInfo result does not identify those edit-mode points.
        preselection = self._preselection_at(point)
        self.assertEqual(preselection.DocumentName, self.doc_name)
        self.assertEqual(preselection.ObjectName, self.sketch.Name)
        self.assertIn("Vertex2", preselection.SubElementNames)

    def _drawn_points(self):
        search = self.coin.SoSearchAction()
        search.setName("PointsCoordinate0")
        search.setSearchingAll(True)
        search.apply(self.view.getSceneGraph())
        path = search.getPath()
        self.assertIsNotNone(path, "No Sketcher edit-mode endpoint coordinate node")
        node = path.getTail()
        self.assertTrue(node.isOfType(self.coin.SoCoordinate3.getClassTypeId()))
        # Sketcher raises rendered endpoints by zHighPoints (0.013) to keep them
        # visible over the sketch. Compare their X/Y positions on the sketch plane.
        return [self.app.Vector(value[0], value[1], 0) for value in node.point.getValues()]

    def _assert_drawn(self, expected, tolerance=1e-5):
        points = self._drawn_points()
        self.assertGreaterEqual(len(points), 2)
        nearest = min(points, key=lambda value: (value - expected).Length)
        self.assertLessEqual((nearest - expected).Length, tolerance,
                             "The rendered endpoint differs from the requested location")
        return nearest

    def _send(self, kind, point, button, buttons):
        self.assertTrue(self.viewport.rect().contains(point))
        self.gui_helpers.send_mouse(self.viewport, kind, point, button, buttons)
        self.last_point = point

    def _move(self, point, buttons):
        self._send(self.core.QEvent.MouseMove, point, self.core.Qt.NoButton, buttons)

    def _release_mouse(self):
        if self.mouse_down:
            self.mouse_down = False
            self._send(self.core.QEvent.MouseButtonRelease, self.last_point,
                       self.core.Qt.LeftButton, self.core.Qt.NoButton)

    def _distance_to_projected_line(self, target, first, second, segment=False):
        point = self._device(target)
        start = self.view.getPointOnScreen(first)
        end = self.view.getPointOnScreen(second)
        dx, dy = end[0] - start[0], end[1] - start[1]
        squared_length = dx * dx + dy * dy
        self.assertGreater(squared_length, 0)
        parameter = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / squared_length
        if segment:
            parameter = max(0, min(1, parameter))
        return math.hypot(point[0] - start[0] - parameter * dx,
                          point[1] - start[1] - parameter * dy)

    def _assert_long_target_clearance(self, target):
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertIsInstance(self.sketch.Geometry[0], self.part.LineSegment)
        start = self._assert_drawn(self.original_start)
        end = self._assert_drawn(self.original_end)
        distances = {
            "rendered_segment": self._distance_to_projected_line(target, start, end, True),
            "horizontal_axis": self._distance_to_projected_line(
                target, self.sketch.getPoint(-1, 1), self.sketch.getPoint(-1, 2)),
            "vertical_axis": self._distance_to_projected_line(
                target, self.sketch.getPoint(-2, 1), self.sketch.getPoint(-2, 2)),
        }
        for geometry, distance in distances.items():
            self.assertGreater(distance, 3 * self.pick_radius, geometry)

    def _short_target(self):
        # The source ignores moves smaller than three device pixels. Choose a
        # representable event inside the actual viewer's unchanged pick radius.
        start = self._device(self.start)
        for delta in range(1, math.ceil(self.pick_radius / self.scale) + 1):
            target = self.start + self.core.QPoint(0, -delta)
            device = self._device(target)
            distance = math.hypot(device[0] - start[0], device[1] - start[1])
            if 3 <= distance < self.pick_radius:
                self._assert_endpoint_pick(target)
                return target
        self.fail("No representable short drag inside this viewer's pick radius")

    def _drag(self, target, short):
        self._assert_endpoint_pick(self.start)
        device_start, device_target = self._device(self.start), self._device(target)
        distance = math.dist(device_start, device_target)
        if short:
            self.assertGreaterEqual(distance, 3)
            self.assertLess(distance, self.pick_radius)
            self._assert_endpoint_pick(target)
        else:
            self.assertGreater(distance, 3 * self.pick_radius)
            # A miss clears Sketcher's internal hit state without necessarily
            # clearing the global preselection record. Admit clearance from
            # rendered geometry and projected axes independently of that record.
            self._preselection_at(target)
            self._assert_long_target_clearance(target)
        expected = self._world(target)
        step = (self.view.getPoint(device_target[0] + 1, device_target[1]) - expected).Length
        self.assertGreater(step, 0)
        self._move(self.start, self.core.Qt.NoButton)
        self._pump(30)
        preselection = self.gui.Selection.getPreselection()
        self.assertEqual(preselection.ObjectName, self.sketch.Name)
        self.assertIn("Vertex2", preselection.SubElementNames)
        self.mouse_down = True
        self._send(self.core.QEvent.MouseButtonPress, self.start,
                   self.core.Qt.LeftButton, self.core.Qt.LeftButton)
        # The first move starts the drag. The next applies its temporary solver move.
        self._move(target, self.core.Qt.LeftButton)
        self._move(target, self.core.Qt.LeftButton)
        self._pump(30)
        preview = self._assert_drawn(expected, max(step * 0.6, 1e-5))
        self.assertGreater((preview - self.original_end).Length, step * 2)
        self.assertLess((self.sketch.getPoint(0, 2) - self.original_end).Length, 1e-9,
                        "Preview admission requires an uncommitted solver move")
        self._assert_drawn(self.original_start)
        self.assertEqual(self.sketch.ConstraintCount, 0)

        self._release_mouse()
        self._pump(50)
        committed = self.sketch.getPoint(0, 2)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoCount, self.undo_before + 1)
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertFalse(self.sketch.ViewObject.Autoconstraints)
        self.assertEqual(self.gui_doc.getInEdit().Object, self.sketch)
        self.assertTrue(self.gui.Control.activeDialog(self.gui_doc))
        self.assertIsNone(self.widgets.QApplication.activeModalWidget())
        self.assertIsNone(self.widgets.QApplication.activePopupWidget())
        self.assertLess((self.sketch.getPoint(0, 1) - self.original_start).Length, 1e-9)
        self.assertLess((committed - preview).Length, 1e-4,
                        "Mouse release must preserve the admitted drag preview")
        self._assert_drawn(committed)

    def test_long_endpoint_drag_control(self):
        delta = math.ceil(4 * self.pick_radius / self.scale)
        self._drag(self.start + self.core.QPoint(0, -delta), short=False)

    def test_short_endpoint_drag_inside_pick_radius(self):
        self._drag(self._short_target(), short=True)
