# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
from PySide import QtCore, QtGui
from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase


class TestOnViewParameterGui(SketcherGuiTestCase):
    KEYS = {
        "0": QtCore.Qt.Key_0,
        "1": QtCore.Qt.Key_1,
        "2": QtCore.Qt.Key_2,
        "3": QtCore.Qt.Key_3,
        "4": QtCore.Qt.Key_4,
        "5": QtCore.Qt.Key_5,
        "6": QtCore.Qt.Key_6,
        "7": QtCore.Qt.Key_7,
        "8": QtCore.Qt.Key_8,
        "9": QtCore.Qt.Key_9,
        ".": QtCore.Qt.Key_Period,
        "-": QtCore.Qt.Key_Minus,
        " ": QtCore.Qt.Key_Space,
    }

    def setUp(self):
        super().setUp()

        self.sketcher_tool_params = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Sketcher/Tools"
        )
        self.had_ovp_visibility = "OnViewParameterVisibility" in self.sketcher_tool_params.GetInts()
        self.old_ovp_visibility = self.sketcher_tool_params.GetInt("OnViewParameterVisibility", 1)
        self.sketcher_tool_params.SetInt("OnViewParameterVisibility", 1)

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("TestOnViewParameterGui")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()

    def tearDown(self):
        try:
            if self.had_ovp_visibility:
                self.sketcher_tool_params.SetInt(
                    "OnViewParameterVisibility", self.old_ovp_visibility
                )
            else:
                self.sketcher_tool_params.RemInt("OnViewParameterVisibility")
        finally:
            super().tearDown()

    def pack_color(self, color):
        r, g, b, a = color
        return (
            int(r * 255.0 + 0.5) << 24
            | int(g * 255.0 + 0.5) << 16
            | int(b * 255.0 + 0.5) << 8
            | int(a * 255.0 + 0.5)
        )

    def key_text(self, widget, text):
        for ch in text:
            self.key_click(widget, self.KEYS[ch], ch)

    def cancel_drawing_tool(self, viewport):
        viewport.setFocus()
        self.key_click(viewport, QtCore.Qt.Key_Escape)

    def active_spinbox(self):
        widget = QtGui.QApplication.focusWidget()
        if isinstance(widget, QtGui.QAbstractSpinBox):
            return widget
        if isinstance(widget, QtGui.QLineEdit):
            parent = widget.parent()
            if isinstance(parent, QtGui.QAbstractSpinBox):
                return parent
        return None

    def visible_spinboxes(self):
        main_window = FreeCADGui.getMainWindow()
        return [
            spinbox
            for spinbox in main_window.findChildren(QtGui.QAbstractSpinBox)
            if spinbox.isVisible()
        ]

    def ovp_spinboxes(self):
        spinboxes = self.visible_spinboxes()
        self.assertEqual(len(spinboxes), 2, "Expected exactly two visible rectangle OVPs")
        return spinboxes

    def focus_ovp_spinbox(self, spinbox):
        main_window = FreeCADGui.getMainWindow()
        main_window.raise_()
        main_window.activateWindow()
        spinbox.setFocus(QtCore.Qt.OtherFocusReason)
        self.flush_gui()

    def ovp_lock_icon(self, spinbox):
        return spinbox.findChild(QtGui.QLabel, "onViewParameterLockIcon")

    def active_task_dialog(self):
        return FreeCADGui.Control.activeTaskDialog()

    def assert_sketch_edit_active(self):
        edit = FreeCADGui.ActiveDocument.getInEdit()
        self.assertIsNotNone(edit, "Expected sketch edit mode to remain active")
        self.assertTrue(
            edit.isDerivedFrom("SketcherGui::ViewProviderSketch"),
            "Expected a Sketcher view provider to remain in edit mode",
        )

    def assert_sketch_edit_inactive(self):
        self.assertIsNone(
            FreeCADGui.ActiveDocument.getInEdit(),
            "Expected sketch edit mode to be inactive",
        )

    def begin_sketch_edit_with_task_dialog(self):
        FreeCADGui.getMainWindow().show()
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.pump(200)
        self.assert_sketch_edit_active()
        self.assertIsNotNone(self.active_task_dialog(), "Expected the Sketcher task dialog to open")

    def begin_rectangle_with_visible_ovp(self, command="Sketcher_CreateRectangle"):
        """Start @p command (rectangle by default, or a tool with the same two OVPs after the
        first click, e.g. the line: length and angle) and click its first point."""
        self.begin_sketch_edit_with_task_dialog()

        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(100)

        viewport = view.graphicsView().viewport()
        origin = FreeCAD.Vector(0, 0, 0)

        def wait_for_origin_point():
            origin_point = None

            def origin_is_framed():
                nonlocal origin_point

                width, height = view.getSize()
                if width <= 0 or height <= 0:
                    return False

                view.fitAll()
                point = self.viewport_to_qpoint(view, viewport, view.getPointOnScreen(origin))
                interior_rect = viewport.rect().adjusted(20, 20, -20, -20)
                if not interior_rect.contains(point):
                    return False

                origin_point = point
                return True

            self.assertTrue(
                self.wait_until(origin_is_framed, timeout_ms=5000, step_ms=100),
                "Expected the sketch origin to project to an interior viewport point",
            )
            self.assertIsNotNone(origin_point)
            return origin_point

        FreeCADGui.runCommand(command)
        self.pump(250)

        origin_point = wait_for_origin_point()
        first_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(origin_point.x() + 80, origin_point.y() - 60),
        )

        move_target = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(first_point.x() + 100, first_point.y() + 80),
        )

        self.move(viewport, first_point)
        self.click(viewport, first_point)
        self.move(viewport, move_target)

        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 2, timeout_ms=1000),
            "Expected the rectangle OVPs to become visible after the first click",
        )
        self.ovp_spinboxes()

        return viewport, first_point

    def origin_marker_index(self):
        from pivy import coin

        view = FreeCADGui.ActiveDocument.ActiveView
        root = view.getViewer().getSoRenderManager().getSceneGraph()
        search = coin.SoSearchAction()
        search.setName("OriginPointSet")
        search.setSearchingAll(True)
        search.apply(root)
        path = search.getPath()
        self.assertIsNotNone(path, "Expected the visible origin marker in the scene graph")
        return path.getTail().markerIndex.getValues()[0]

    def origin_marker_indices(self, marker_name):
        # MarkerSize is converted to a device-pixel size by the C++ view provider. Querying all
        # supported sizes keeps this semantic check independent of the display scale factor.
        return {
            FreeCADGui.getMarkerIndex(marker_name, size)
            for size in (5, 7, 9, 11, 13, 15, 20, 25, 30)
        }

    def origin_marker_is(self, marker_name):
        return self.origin_marker_index() in self.origin_marker_indices(marker_name)

    def origin_material_transparency(self, name):
        from pivy import coin

        view = FreeCADGui.ActiveDocument.ActiveView
        root = view.getViewer().getSoRenderManager().getSceneGraph()
        search = coin.SoSearchAction()
        search.setName(name)
        search.setSearchingAll(True)
        search.apply(root)
        path = search.getPath()
        self.assertIsNotNone(path, f"Expected {name} in the scene graph")
        transparency = path.getTail().transparency
        return transparency.getValues()[0], transparency.isDefault()

    def datum_labels(self, view):
        from pivy import coin

        root = view.getViewer().getSoRenderManager().getSceneGraph()
        datum_type = coin.SoType.fromName("SoDatumLabel")
        labels = []

        def visit(node):
            if node.isOfType(datum_type):
                labels.append(node)
            if node.isOfType(coin.SoGroup.getClassTypeId()):
                for index in range(node.getNumChildren()):
                    visit(node.getChild(index))

        visit(root)
        return labels

    def datum_label_points(self, label):
        return tuple(
            tuple(float(label.pnts[i][axis]) for axis in range(3))
            for i in range(label.pnts.getNum())
        )

    def record_datum_label_point_updates(self, labels):
        from pivy import coin

        updates = []
        completed_updates = []
        sensors = []

        for label_index, label in enumerate(labels):
            point_count = [label.pnts.getNum()]

            def record_update(
                data,
                sensor,
                label=label,
                label_index=label_index,
                point_count=point_count,
            ):
                points = self.datum_label_points(label)
                updates.append((label_index, points))

                # SoDatumLabel::setPoints() grows pnts before it edits both values. Coin
                # notifies the priority-0 sensor for that allocation as well as for the
                # completed edit. Ignore only the notification that changes the point
                # count; every same-sized notification is a completed assignment and
                # must be retained, including a zero-to-nonzero transition.
                current_point_count = label.pnts.getNum()
                if current_point_count == point_count[0]:
                    completed_updates.append((label_index, points))
                else:
                    point_count[0] = current_point_count

            sensor = coin.SoFieldSensor(record_update, None)
            sensor.setPriority(0)
            sensor.attach(label.pnts)
            sensors.append(sensor)

        return sensors, updates, completed_updates

    def test_origin_marker_tracks_drawing_tool_state(self):
        """The origin marker tracks drawing state during off-origin interaction."""

        self.begin_sketch_edit_with_task_dialog()
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(150)
        viewport = view.graphicsView().viewport()
        origin_point = self.viewport_to_qpoint(
            view,
            viewport,
            view.getPointOnScreen(FreeCAD.Vector(0, 0, 0)),
        )
        drawing_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(origin_point.x() + 80, origin_point.y() - 60),
        )
        filled_marker = self.origin_marker_index()
        self.assertTrue(
            self.origin_marker_is("CIRCLE_FILLED"),
            "Expected the idle origin marker to use the filled circle marker",
        )

        transparency, is_default = self.origin_material_transparency("OriginPointMaterial")
        self.assertEqual(transparency, 0.0)
        self.assertFalse(is_default, "Expected the origin transparency to be explicitly set")

        FreeCADGui.runCommand("Sketcher_CreateLine")
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_LINE"),
                timeout_ms=3000,
            ),
            "Expected the drawing tool to switch the origin marker appearance",
        )
        hollow_marker = self.origin_marker_index()

        self.assertNotEqual(
            hollow_marker,
            filled_marker,
            "Expected an active drawing tool to switch the origin marker appearance",
        )

        view_params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
        old_marker_size = view_params.GetInt("MarkerSize", 9)
        new_marker_size = 13 if old_marker_size != 13 else 15
        try:
            view_params.SetInt("MarkerSize", new_marker_size)
            self.assertTrue(
                self.wait_until(
                    lambda: self.origin_marker_is("CIRCLE_LINE")
                    and self.origin_marker_index() != hollow_marker,
                    timeout_ms=3000,
                ),
                "Expected the active origin marker to update after changing its size",
            )
            resized_hollow_marker = self.origin_marker_index()
            self.assertNotEqual(
                resized_hollow_marker,
                hollow_marker,
                "Expected an active hollow marker to be regenerated when its size changes",
            )
        finally:
            view_params.SetInt("MarkerSize", old_marker_size)
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_LINE")
                and self.origin_marker_index() != resized_hollow_marker,
                timeout_ms=3000,
            ),
            "Expected restoring the marker size to update the active marker",
        )

        self.cancel_drawing_tool(viewport)
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_FILLED"),
                timeout_ms=3000,
            ),
            "Expected leaving the drawing tool to restore the filled origin marker",
        )

        second_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(drawing_point.x() + 100, drawing_point.y() + 80),
        )
        FreeCADGui.runCommand("Sketcher_CreateLine")
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_LINE"),
                timeout_ms=3000,
            ),
            "Expected the second line tool activation to switch the origin marker appearance",
        )
        self.move(viewport, drawing_point)
        self.click(viewport, drawing_point)
        self.move(viewport, second_point)
        self.click(viewport, second_point)
        self.assertGreater(
            self.sketch.GeometryCount,
            0,
            "Expected geometry away from the origin before cancelling the tool",
        )
        self.cancel_drawing_tool(viewport)
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_FILLED"),
                timeout_ms=3000,
            ),
            "Expected cancelling the drawing tool to leave a filled origin marker",
        )
        transparency, is_default = self.origin_material_transparency("OriginPointMaterial")
        self.assertEqual(transparency, 0.0)
        self.assertFalse(is_default, "Expected the origin transparency to remain explicit")

        for command in ("Sketcher_CreateRectangle", "Sketcher_CreateCircle"):
            FreeCADGui.runCommand(command)
            self.assertTrue(
                self.wait_until(
                    lambda: self.origin_marker_is("CIRCLE_LINE"),
                    timeout_ms=3000,
                ),
                f"Expected {command} to activate the hollow origin marker",
            )
            self.cancel_drawing_tool(viewport)
            self.assertTrue(
                self.wait_until(
                    lambda: self.origin_marker_is("CIRCLE_FILLED"),
                    timeout_ms=3000,
                ),
                f"Expected {command} cancellation to restore the filled origin marker",
            )

        FreeCADGui.ActiveDocument.resetEdit()
        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected leaving sketch edit mode to close the task dialog",
        )
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_FILLED"),
                timeout_ms=3000,
            ),
            "Expected the origin marker to be filled after re-entering the sketch",
        )
        transparency, is_default = self.origin_material_transparency("OriginPointMaterial")
        self.assertEqual(transparency, 0.0)
        self.assertFalse(is_default, "Expected the re-entered origin transparency to be explicit")

    def test_origin_marker_resets_between_edit_sessions(self):
        """A hollow drawing marker must not leak into a later edit session."""

        self.begin_sketch_edit_with_task_dialog()
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(150)
        self.assertTrue(self.origin_marker_is("CIRCLE_FILLED"))

        FreeCADGui.runCommand("Sketcher_CreateLine")
        self.assertTrue(
            self.wait_until(lambda: self.origin_marker_is("CIRCLE_LINE"), timeout_ms=3000),
            "Expected the drawing tool to switch the origin marker appearance",
        )

        FreeCADGui.ActiveDocument.resetEdit()
        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected leaving sketch edit mode to close the task dialog",
        )
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)

        self.assertTrue(
            self.wait_until(
                lambda: self.origin_marker_is("CIRCLE_FILLED"),
                timeout_ms=3000,
            ),
            "Expected a new edit session to start with a filled origin marker",
        )
        transparency, is_default = self.origin_material_transparency("OriginPointMaterial")
        self.assertEqual(transparency, 0.0)
        self.assertFalse(is_default, "Expected the origin transparency to be explicit")

    def test_rectangle_ovp_transition_never_resets_to_origin(self):
        """OVP points must not be updated to the sketch origin during tool transitions."""

        self.begin_sketch_edit_with_task_dialog()
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(150)
        viewport = view.graphicsView().viewport()

        for command, needs_radius in (
            ("Sketcher_CreateRectangle", False),
            ("Sketcher_CreateRectangle_Center", False),
            ("Sketcher_CreateOblong", True),
        ):
            initial_geometry_count = self.sketch.GeometryCount
            FreeCADGui.runCommand(command)
            self.assertTrue(
                self.wait_until(lambda: self.origin_marker_is("CIRCLE_LINE"), timeout_ms=3000),
                f"Expected {command} to activate its drawing handler",
            )
            view.fitAll()
            origin = self.viewport_to_qpoint(
                view,
                viewport,
                view.getPointOnScreen(FreeCAD.Vector(0, 0, 0)),
            )
            first_point = self.clamp_to_widget(
                viewport,
                QtCore.QPoint(origin.x() + 80, origin.y() - 60),
            )
            second_point = self.clamp_to_widget(
                viewport,
                QtCore.QPoint(first_point.x() + 100, first_point.y() + 80),
            )
            radius_point = self.clamp_to_widget(
                viewport,
                QtCore.QPoint(second_point.x() + 25, second_point.y() + 20),
            )
            labels = self.datum_labels(view)
            self.assertGreaterEqual(
                len(labels),
                4,
                f"Expected {command} to create its on-view datum labels",
            )
            sensors = []
            observations = []

            def observe_current_labels():
                current_labels = self.datum_labels(view)
                self.assertGreaterEqual(
                    len(current_labels),
                    4,
                    f"Expected {command} to retain its on-view datum labels",
                )
                # Observe every label. The scene-graph order is not a stable part of the
                # handler API, and the centered rectangle does not necessarily expose its
                # dimension labels at the same positions as the diagonal rectangle. The
                # regression is specifically a complete two-point assignment at the origin,
                # so it is safe and more reliable to inspect all labels owned by this tool.
                current_sensors, current_updates, current_completed_updates = (
                    self.record_datum_label_point_updates(current_labels)
                )
                sensors.extend(current_sensors)
                observations.append((current_updates, current_completed_updates))

            self.move(viewport, first_point)
            self.flush_gui()
            observe_current_labels()
            self.click(viewport, first_point)
            self.assertTrue(
                self.wait_until(lambda: len(self.visible_spinboxes()) == 2, timeout_ms=1000),
                f"Expected {command} to activate its width and height OVPs",
            )
            self.move(viewport, second_point)
            self.flush_gui()
            observe_current_labels()
            self.click(viewport, second_point)
            if needs_radius:
                self.move(viewport, radius_point)
                self.flush_gui()
                observe_current_labels()
                self.click(viewport, radius_point)

            for sensor in sensors:
                sensor.detach()

            updates = [update for batch, _ in observations for update in batch]
            completed_updates = [update for _, batch in observations for update in batch]

            self.assertTrue(
                updates, f"Expected {command} to update OVP points during the transition"
            )
            self.assertTrue(
                completed_updates,
                f"Expected {command} to complete OVP point assignments during the transition: {updates}",
            )

            origin_updates = [
                points
                for _, points in completed_updates
                if len(points) >= 2
                and all(all(abs(coordinate) < 1e-9 for coordinate in point) for point in points[:2])
            ]
            self.assertFalse(
                origin_updates,
                f"{command} left both OVP points at (0, 0, 0): {origin_updates}",
            )
            self.assertTrue(
                self.wait_until(
                    lambda: self.sketch.GeometryCount > initial_geometry_count,
                    timeout_ms=3000,
                ),
                f"Expected {command} to create geometry",
            )

            self.right_click(viewport, second_point)
            self.assert_sketch_edit_active()

    def test_reset_edit_closes_sketch_task_dialog(self):
        self.begin_sketch_edit_with_task_dialog()

        FreeCADGui.ActiveDocument.resetEdit()

        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected resetEdit() to close the Sketcher task dialog",
        )
        self.assert_sketch_edit_inactive()

    def test_task_dialog_reject_exits_sketch_edit(self):
        self.begin_sketch_edit_with_task_dialog()

        self.active_task_dialog().reject()

        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected reject() to close the Sketcher task dialog",
        )
        self.assert_sketch_edit_inactive()

    def test_task_dialog_accept_exits_sketch_edit(self):
        self.begin_sketch_edit_with_task_dialog()

        self.active_task_dialog().accept()

        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected accept() to close the Sketcher task dialog",
        )
        self.assert_sketch_edit_inactive()

    def test_rectangle_ovp_enter_finishes_without_crash(self):
        """
        Reproduce the rectangle OVP acceptance flow from PR #29201 review:
        click first point, type width, Tab, type height, Enter.

        If the process survives, the rectangle should be created in the sketch.
        """

        self.begin_rectangle_with_visible_ovp()

        first_spinbox = self.ovp_spinboxes()[0]
        self.focus_ovp_spinbox(first_spinbox)
        self.key_text(first_spinbox, "10")
        self.key_click(first_spinbox, QtCore.Qt.Key_Tab, "\t")

        second_spinbox = self.ovp_spinboxes()[1]
        self.assertTrue(
            self.wait_until(lambda: second_spinbox.hasFocus(), timeout_ms=1000),
            "Expected Tab to move focus to the second rectangle OVP",
        )
        self.key_text(second_spinbox, "20")
        self.key_click(second_spinbox, QtCore.Qt.Key_Return, "\r")

        self.pump(500)

        self.assertGreaterEqual(
            self.sketch.GeometryCount,
            4,
            "Expected the rectangle to be created after accepting both OVPs",
        )

    def test_clearing_committed_rectangle_ovp_releases_its_lock(self):
        """A cleared OVP must leave its committed state and resume live geometry input."""

        self.begin_rectangle_with_visible_ovp()

        first_spinbox = self.active_spinbox()
        self.assertIsNotNone(first_spinbox, "Expected the first rectangle OVP to have focus")
        self.key_text(first_spinbox, "10")
        self.key_click(first_spinbox, QtCore.Qt.Key_Tab, "\t")

        lock_icon = self.ovp_lock_icon(first_spinbox)
        self.assertIsNotNone(lock_icon)
        self.assertTrue(
            self.wait_until(lock_icon.isVisible, timeout_ms=1000),
            "Expected Tab to lock the committed first OVP",
        )

        first_edit = first_spinbox.findChild(QtGui.QLineEdit)
        self.assertIsNotNone(first_edit)
        first_spinbox.setFocus(QtCore.Qt.OtherFocusReason)
        self.pump(100)
        self.assertIs(self.active_spinbox(), first_spinbox)
        first_edit.clear()
        self.pump(60)

        self.assertTrue(
            self.wait_until(lambda: not lock_icon.isVisible(), timeout_ms=1000),
            "Expected clearing the first OVP to release its lock",
        )

        first_edit.setText("15")
        self.pump(60)
        self.key_click(first_spinbox, QtCore.Qt.Key_Tab, "\t")

        self.assertTrue(
            self.wait_until(
                lambda: self.active_spinbox() is not None
                and self.active_spinbox() is not first_spinbox,
                timeout_ms=1000,
            ),
            "Expected a replacement value to recommit the first OVP",
        )
        self.assertTrue(
            self.wait_until(lock_icon.isVisible, timeout_ms=1000),
            "Expected the replacement value to lock the first OVP again",
        )

    def test_rectangle_ovp_escape_resets_tool_without_exiting_sketch(self):
        viewport, first_point = self.begin_rectangle_with_visible_ovp()

        first_spinbox = self.ovp_spinboxes()[0]
        self.focus_ovp_spinbox(first_spinbox)
        self.key_click(first_spinbox, QtCore.Qt.Key_Escape)

        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 0, timeout_ms=1000),
            "Expected Esc to close the rectangle OVPs",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assert_sketch_edit_active()

        restart_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(first_point.x() + 120, first_point.y() + 50),
        )
        restart_move = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(restart_point.x() + 70, restart_point.y() - 40),
        )

        self.move(viewport, restart_point)
        self.click(viewport, restart_point)
        self.move(viewport, restart_move)

        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 2, timeout_ms=1000),
            "Expected Esc to reset the rectangle tool back to its first stage",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.focus_ovp_spinbox(self.ovp_spinboxes()[0])

    def test_rectangle_ovp_escape_then_right_click_exits_tool(self):
        viewport, first_point = self.begin_rectangle_with_visible_ovp()

        first_spinbox = self.ovp_spinboxes()[0]
        self.focus_ovp_spinbox(first_spinbox)
        self.key_click(first_spinbox, QtCore.Qt.Key_Escape)

        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 0, timeout_ms=1000),
            "Expected Esc to close the rectangle OVPs",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assert_sketch_edit_active()

        cancel_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(first_point.x() + 120, first_point.y() + 50),
        )
        retry_move = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(cancel_point.x() + 70, cancel_point.y() - 40),
        )

        self.right_click(viewport, cancel_point)
        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 0, timeout_ms=400),
            "Expected right click to keep the rectangle OVPs closed after canceling",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assert_sketch_edit_active()

        self.move(viewport, cancel_point)
        self.click(viewport, cancel_point)
        self.move(viewport, retry_move)

        self.assertFalse(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 2, timeout_ms=500),
            "Expected right click to exit the rectangle tool after OVP Esc",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)

    def test_rectangle_ovp_escape_then_escape_then_escape_exits_sketch(self):
        viewport, first_point = self.begin_rectangle_with_visible_ovp()

        first_spinbox = self.ovp_spinboxes()[0]
        self.focus_ovp_spinbox(first_spinbox)
        self.key_click(first_spinbox, QtCore.Qt.Key_Escape)

        self.assertTrue(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 0, timeout_ms=1000),
            "Expected the first Esc to close the rectangle OVPs",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assert_sketch_edit_active()

        view = FreeCADGui.ActiveDocument.ActiveView
        graphics_view = view.graphicsView()
        graphics_view.setFocus(QtCore.Qt.OtherFocusReason)
        self.pump(100)

        self.key_click(graphics_view, QtCore.Qt.Key_Escape)
        self.assert_sketch_edit_active()

        cancel_point = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(first_point.x() + 120, first_point.y() + 50),
        )
        retry_move = self.clamp_to_widget(
            viewport,
            QtCore.QPoint(cancel_point.x() + 70, cancel_point.y() - 40),
        )

        self.move(viewport, cancel_point)
        self.click(viewport, cancel_point)
        self.move(viewport, retry_move)

        self.assertFalse(
            self.wait_until(lambda: len(self.visible_spinboxes()) == 2, timeout_ms=500),
            "Expected the second Esc to exit the rectangle tool",
        )
        self.assertEqual(self.sketch.GeometryCount, 0)

        graphics_view.setFocus(QtCore.Qt.OtherFocusReason)
        self.pump(100)
        self.key_click(graphics_view, QtCore.Qt.Key_Escape)

        self.assertTrue(
            self.wait_until(lambda: self.active_task_dialog() is None, timeout_ms=1000),
            "Expected the third Esc to close the Sketcher task dialog",
        )
        self.assert_sketch_edit_inactive()

    def test_auto_color_restores_line_color_from_preferences(self):
        view_params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
        color_key = "SketchEdgeColor"
        had_color = color_key in view_params.GetUnsigneds()
        old_color = view_params.GetUnsigned(color_key, 0)

        try:
            manual_color = 0x112233FF
            preference_color = 0x44AA88FF

            view = self.sketch.ViewObject
            view.AutoColor = False
            view.LineColor = manual_color
            self.assertEqual(self.pack_color(view.LineColor), manual_color)

            view_params.SetUnsigned(color_key, preference_color)
            self.pump(100)
            self.assertEqual(self.pack_color(view.LineColor), manual_color)

            view.AutoColor = True
            self.pump(100)

            self.assertEqual(self.pack_color(view.LineColor), preference_color)
        finally:
            if had_color:
                view_params.SetUnsigned(color_key, old_color)
            else:
                view_params.RemUnsigned(color_key)

    # User parameters typed in on-view parameters (App/UserParameters.h)

    def type_ovp(self, spinbox, text):
        """Replace the text of an OVP. Backspace first: letters then go to the field, not to
        the 3D view shortcuts."""
        editor = spinbox.findChild(QtGui.QLineEdit)
        self.assertIsNotNone(editor)
        editor.selectAll()
        self.key_click(spinbox, QtCore.Qt.Key_Backspace)
        for ch in text:
            self.key_click(spinbox, self.KEYS.get(ch, ord(ch.upper())), ch)

    def draw_rectangle_with_ovp_texts(
        self, first_text, second_text, command="Sketcher_CreateRectangle", min_geometry=4
    ):
        viewport, _ = self.begin_rectangle_with_visible_ovp(command)
        first = self.active_spinbox()
        self.assertIsNotNone(first, "Expected the first rectangle OVP to have focus")
        self.type_ovp(first, first_text)
        self.key_click(first, QtCore.Qt.Key_Tab, "\t")

        second = [spinbox for spinbox in self.ovp_spinboxes() if spinbox is not first][0]
        self.assertTrue(
            self.wait_until(lambda: second.hasFocus(), timeout_ms=1000),
            "Expected Tab to move focus to the second rectangle OVP",
        )
        self.type_ovp(second, second_text)
        self.key_click(second, QtCore.Qt.Key_Return, "\r")
        self.pump(500)
        self.assertGreaterEqual(
            self.sketch.GeometryCount, min_geometry, "Expected the geometry of " + command
        )
        return viewport

    def bound_constraint(self, *names):
        """Index of the only constraint bound to an expression, which names @p names."""
        bindings = self.sketch.ExpressionEngine
        self.assertEqual(len(bindings), 1, bindings)
        path, expression = bindings[0]
        for name in names:
            self.assertIn(name, expression)
        return int(path[path.index("[") + 1 : path.index("]")])

    def user_parameter_names(self):
        return [(obj.Name, name) for obj, name in self.doc.getUserParameters()]

    def test_ovp_assignment_creates_bound_user_parameter(self):
        self.doc.UndoMode = 1
        viewport = self.draw_rectangle_with_ovp_texts("boxWidth=30", "20")

        self.assertEqual(self.sketch.getGroupOfProperty("boxWidth"), "UserParameters")
        self.assertAlmostEqual(self.sketch.boxWidth.Value, 30)
        index = self.bound_constraint("boxWidth")
        self.assertEqual(self.sketch.ExpressionEngine[0][1], "boxWidth")
        self.assertEqual(self.sketch.Constraints[index].Type, "Distance")
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 30)

        # One undo step removes the rectangle together with its parameter.
        self.cancel_drawing_tool(viewport)
        self.pump(100)
        geometry_when_removed = None
        for _ in range(len(self.doc.UndoNames)):
            self.doc.undo()
            if not hasattr(self.sketch, "boxWidth"):
                geometry_when_removed = self.sketch.GeometryCount
                break
        self.assertEqual(geometry_when_removed, 0)
        self.assertEqual(len(self.sketch.ExpressionEngine), 0)

    def test_ovp_assignment_drives_the_constraint(self):
        self.draw_rectangle_with_ovp_texts("boxWidth=30", "20")
        index = self.bound_constraint("boxWidth")
        self.sketch.boxWidth = 45
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 45)

    def test_ovp_expression_uses_existing_parameter(self):
        self.doc.addUserParameter(self.sketch, "base", "15 mm")
        self.draw_rectangle_with_ovp_texts("=2*base", "20")

        index = self.bound_constraint("base", "2")
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 30)
        self.assertEqual(self.user_parameter_names(), [(self.sketch.Name, "base")])

    def test_ovp_plain_numbers_create_no_parameter(self):
        self.draw_rectangle_with_ovp_texts("10", "20")

        self.assertEqual(len(self.sketch.ExpressionEngine), 0)
        self.assertEqual(self.user_parameter_names(), [])

    def test_ovp_assignment_with_used_name_is_refused(self):
        self.doc.addUserParameter(self.sketch, "taken", "5 mm")
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_ovp(first, "taken=30")
        self.key_click(first, QtCore.Qt.Key_Return, "\r")
        self.pump(200)

        self.assertIs(self.active_spinbox(), first, "Expected the OVP to stay in edit")
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assertAlmostEqual(self.sketch.taken.Value, 5)

        # The refused expression is still being edited: letters go on to the field.
        editor = first.findChild(QtGui.QLineEdit)
        editor.end(False)
        self.type_keys(first, "x")
        self.assertEqual(editor.text(), "taken=30x")

    def assert_line_angle_parameter_binds(self, name, degrees):
        """The tools write datums with 6 decimals in rad ("%f"): 30 deg becomes 0.523599 rad,
        which is not 30 deg within 1e-7. The parameter must bind anyway."""
        import math

        self.draw_rectangle_with_ovp_texts(
            "10", "{}={}".format(name, degrees), command="Sketcher_CreateLine", min_geometry=1
        )
        self.assertEqual(self.sketch.getGroupOfProperty(name), "UserParameters")
        self.assertAlmostEqual(getattr(self.sketch, name).Value, degrees)
        index = self.bound_constraint(name)
        self.assertEqual(self.sketch.ExpressionEngine[0][1], name)
        self.assertEqual(self.sketch.Constraints[index].Type, "Angle")
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, math.radians(degrees), 9)

    def test_ovp_line_angle_30_deg_binds(self):
        self.assert_line_angle_parameter_binds("a30", 30)

    def test_ovp_line_angle_45_deg_binds(self):
        self.assert_line_angle_parameter_binds("a45", 45)

    def test_ovp_line_angle_60_deg_binds(self):
        self.assert_line_angle_parameter_binds("a60", 60)

    def type_keys(self, spinbox, text):
        """Type @p text into the OVP as the user does, without clearing it first."""
        for ch in text:
            self.key_click(spinbox, self.KEYS.get(ch, ord(ch.upper())), ch)

    def visible_combo(self, name):
        for combo in FreeCADGui.getMainWindow().findChildren(QtGui.QComboBox, name):
            try:
                if combo.isVisible():
                    return combo
            except RuntimeError:  # widget of a closed tool, not yet destroyed
                continue
        return None

    def visible_check_box(self, name):
        for box in FreeCADGui.getMainWindow().findChildren(QtGui.QCheckBox, name):
            try:
                if box.isVisible():
                    return box
            except RuntimeError:  # widget of a closed tool, not yet destroyed
                continue
        return None

    def test_ovp_letters_go_to_the_field(self):
        # Letters are text in the field (`height = 20 mm`), not tool shortcuts: M does not
        # switch the construction method, and the first letter replaces the shown value and
        # its unit.
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first, "Expected the first rectangle OVP to have focus")
        method = self.visible_combo("comboBox1")
        self.assertIsNotNone(method, "Expected the construction method combobox")
        before = method.currentIndex()
        editor = first.findChild(QtGui.QLineEdit)
        editor.selectAll()
        self.type_keys(first, "m")
        self.pump(200)
        self.assertEqual(method.currentIndex(), before, "Expected M to be typed in the field")
        self.assertEqual(editor.text(), "m")

    def test_ovp_alt_tap_switches_construction_method(self):
        # In a field, tapping Alt is the M of the 3D view.
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first, "Expected the first rectangle OVP to have focus")
        method = self.visible_combo("comboBox1")
        self.assertIsNotNone(method, "Expected the construction method combobox")
        before = method.currentIndex()
        try:
            press = QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Alt, QtCore.Qt.AltModifier, ""
            )
            release = QtGui.QKeyEvent(
                QtCore.QEvent.KeyRelease, QtCore.Qt.Key_Alt, QtCore.Qt.NoModifier, ""
            )
            QtGui.QApplication.sendEvent(first, press)
            QtGui.QApplication.sendEvent(first, release)
            self.pump(200)
            self.assertNotEqual(
                method.currentIndex(), before, "Expected Alt to switch the construction method"
            )
        finally:
            method.setCurrentIndex(before)
            self.pump(100)

    def test_ovp_home_toggles_first_tool_option(self):
        # In a field, Home is the U of the 3D view: rounded corners of the rectangle.
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first, "Expected the first rectangle OVP to have focus")
        rounded = self.visible_check_box("checkBoxTS1")
        self.assertIsNotNone(rounded, "Expected the rounded corners check box")
        before = rounded.isChecked()
        try:
            self.key_click(first, QtCore.Qt.Key_Home)
            self.pump(200)
            self.assertNotEqual(rounded.isChecked(), before, "Expected Home to toggle it")
        finally:
            rounded.setChecked(before)
            self.pump(100)

    def test_ovp_letters_after_equal_sign_go_to_the_field(self):
        # After '=', letters are the expression, not tool shortcuts ('h' would start the
        # Horizontal constraint and cancel the rectangle).
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first, "Expected the first rectangle OVP to have focus")
        self.type_keys(first, "=height=30")
        self.assertEqual(first.findChild(QtGui.QLineEdit).text(), "=height=30")
        self.key_click(first, QtCore.Qt.Key_Tab, "\t")
        second = [spinbox for spinbox in self.ovp_spinboxes() if spinbox is not first][0]
        self.assertTrue(self.wait_until(lambda: second.hasFocus(), timeout_ms=1000))
        self.type_ovp(second, "20")
        self.key_click(second, QtCore.Qt.Key_Return, "\r")
        self.pump(500)

        self.assertEqual(self.sketch.getGroupOfProperty("height"), "UserParameters")
        self.bound_constraint("height")

    def test_ovp_equal_sign_drops_the_shown_value_and_unit(self):
        # '=' over "10 mm" starts an empty expression, not "= mm".
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_keys(first, "=")
        self.assertEqual(first.findChild(QtGui.QLineEdit).text(), "=")

    def test_ovp_equal_sign_keeps_a_typed_name(self):
        # A name typed before '=' is an assignment in progress and is kept, also when it is a
        # unit symbol ("h" is the hour).
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_ovp(first, "h")
        self.type_keys(first, "=")
        self.assertTrue(first.findChild(QtGui.QLineEdit).text().startswith("h="))

    def test_ovp_expression_of_parameter_without_unit(self):
        self.doc.addUserParameter(self.sketch, "base", "15 mm")
        viewport, _ = self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_keys(first, "=base")
        self.key_click(first, QtCore.Qt.Key_Tab, "\t")
        second = [spinbox for spinbox in self.ovp_spinboxes() if spinbox is not first][0]
        self.assertTrue(self.wait_until(lambda: second.hasFocus(), timeout_ms=1000))
        self.type_ovp(second, "20")
        self.key_click(second, QtCore.Qt.Key_Return, "\r")
        self.pump(500)

        index = self.bound_constraint("base")
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 15)

    def test_ovp_polyline_segment_binds(self):
        # The polyline adds its constraints segment by segment: they are bound there too.
        viewport = self.draw_rectangle_with_ovp_texts(
            "seg=30", "20", command="Sketcher_CreatePolyline", min_geometry=1
        )
        self.cancel_drawing_tool(viewport)
        self.pump(200)

        self.assertEqual(self.sketch.getGroupOfProperty("seg"), "UserParameters")
        index = self.bound_constraint("seg")
        self.assertEqual(self.sketch.ExpressionEngine[0][1], "seg")
        self.assertEqual(self.sketch.Constraints[index].Type, "Distance")
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 30)

    def test_ovp_completer_offers_parameters(self):
        self.doc.addUserParameter(self.sketch, "heightValue", "15 mm")
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_keys(first, "=heightV")
        completer = first.findChild(QtGui.QCompleter)
        self.assertIsNotNone(completer, "Expected a completer on the OVP")
        self.assertTrue(
            self.wait_until(lambda: completer.popup().isVisible(), timeout_ms=1000),
            "Expected the completer popup",
        )
        model = completer.completionModel()
        shown = [model.index(row, 0).data() for row in range(model.rowCount())]
        self.assertTrue(any(s.startswith("heightValue") for s in shown), shown)
        completer.popup().hide()

    def test_ovp_expression_uses_parameter_typed_in_the_other_ovp(self):
        # The parameter of the first OVP is created with the rectangle, after the second OVP is
        # accepted: the second one can use it all the same.
        self.draw_rectangle_with_ovp_texts("height=10", "=2*height")

        self.assertEqual(self.user_parameter_names(), [(self.sketch.Name, "height")])
        bindings = dict(self.sketch.ExpressionEngine)
        self.assertEqual(len(bindings), 2, bindings)
        values = {}
        for path, expression in bindings.items():
            index = int(path[path.index("[") + 1 : path.index("]")])
            values[expression.replace(" ", "")] = self.sketch.Constraints[index].Value
        self.assertAlmostEqual(values["height"], 10)
        self.assertAlmostEqual(values["2*height"], 20)

        self.sketch.height = 15
        self.doc.recompute()
        for path, expression in self.sketch.ExpressionEngine:
            index = int(path[path.index("[") + 1 : path.index("]")])
            expected = 30 if "2" in expression else 15
            self.assertAlmostEqual(self.sketch.Constraints[index].Value, expected)

    def test_ovp_completer_offers_parameter_typed_in_the_other_ovp(self):
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_ovp(first, "boxHeight=10")
        self.key_click(first, QtCore.Qt.Key_Tab, "\t")
        second = [spinbox for spinbox in self.ovp_spinboxes() if spinbox is not first][0]
        self.assertTrue(self.wait_until(lambda: second.hasFocus(), timeout_ms=1000))
        self.type_ovp(second, "=boxH")
        completer = second.findChild(QtGui.QCompleter)
        self.assertIsNotNone(completer, "Expected a completer on the OVP")
        self.assertTrue(
            self.wait_until(lambda: completer.popup().isVisible(), timeout_ms=1000),
            "Expected the completer popup",
        )
        model = completer.completionModel()
        shown = [model.index(row, 0).data() for row in range(model.rowCount())]
        self.assertTrue(any(s.startswith("boxHeight") for s in shown), shown)
        completer.popup().hide()

    def test_ovp_name_typed_in_the_other_ovp_is_refused(self):
        self.begin_rectangle_with_visible_ovp()
        first = self.active_spinbox()
        self.assertIsNotNone(first)
        self.type_ovp(first, "twice=10")
        self.key_click(first, QtCore.Qt.Key_Tab, "\t")
        second = [spinbox for spinbox in self.ovp_spinboxes() if spinbox is not first][0]
        self.assertTrue(self.wait_until(lambda: second.hasFocus(), timeout_ms=1000))
        self.type_ovp(second, "twice=20")
        self.key_click(second, QtCore.Qt.Key_Return, "\r")
        self.pump(200)

        self.assertIs(self.active_spinbox(), second, "Expected the OVP to stay in edit")
        self.assertEqual(self.sketch.GeometryCount, 0)

    def begin_rectangle_without_ovp_focus(self):
        """Start the rectangle with the 3D view focused, before any OVP shows."""
        self.begin_sketch_edit_with_task_dialog()
        FreeCADGui.runCommand("Sketcher_CreateRectangle")
        self.pump(200)
        view = FreeCADGui.ActiveDocument.ActiveView.graphicsView()
        view.setFocus()
        self.pump(50)
        return view

    def test_alt_tap_in_3d_view_switches_construction_method(self):
        view = self.begin_rectangle_without_ovp_focus()
        method = self.visible_combo("comboBox1")
        self.assertIsNotNone(method, "Expected the construction method combobox")
        before = method.currentIndex()
        try:
            override = QtGui.QKeyEvent(
                QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_Alt, QtCore.Qt.AltModifier, ""
            )
            override.ignore()
            QtGui.QApplication.sendEvent(view, override)
            self.assertTrue(override.isAccepted(), "Expected Alt to be kept from the menu bar")

            press = QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Alt, QtCore.Qt.AltModifier, ""
            )
            release = QtGui.QKeyEvent(
                QtCore.QEvent.KeyRelease, QtCore.Qt.Key_Alt, QtCore.Qt.NoModifier, ""
            )
            QtGui.QApplication.sendEvent(view, press)
            QtGui.QApplication.sendEvent(view, release)
            self.pump(200)
            self.assertNotEqual(
                method.currentIndex(), before, "Expected Alt to switch the construction method"
            )
        finally:
            method.setCurrentIndex(before)
            self.pump(100)

    def test_home_in_3d_view_toggles_first_tool_option(self):
        view = self.begin_rectangle_without_ovp_focus()
        rounded = self.visible_check_box("checkBoxTS1")
        self.assertIsNotNone(rounded, "Expected the rounded corners check box")
        before = rounded.isChecked()
        try:
            # Home is also the shortcut of Std_ViewHome: the tool claims it.
            override = QtGui.QKeyEvent(
                QtCore.QEvent.ShortcutOverride, QtCore.Qt.Key_Home, QtCore.Qt.NoModifier, ""
            )
            override.ignore()
            QtGui.QApplication.sendEvent(view, override)
            self.assertTrue(override.isAccepted(), "Expected Home to be kept from Std_ViewHome")

            self.key_click(view, QtCore.Qt.Key_Home)
            self.pump(200)
            self.assertNotEqual(rounded.isChecked(), before, "Expected Home to toggle it")
        finally:
            rounded.setChecked(before)
            self.pump(100)

    def test_ovp_short_length_with_many_decimals_binds(self):
        # 1 mm/3 is written as 0.333333 mm, 3.3e-7 away from the value of the expression.
        self.draw_rectangle_with_ovp_texts("w=1/3", "20")
        self.assertEqual(self.sketch.getGroupOfProperty("w"), "UserParameters")
        index = self.bound_constraint("w")
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Constraints[index].Value, 1.0 / 3.0, 12)
