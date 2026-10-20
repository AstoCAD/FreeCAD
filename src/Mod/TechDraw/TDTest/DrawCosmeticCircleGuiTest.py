# SPDX-License-Identifier: LGPL-2.1-or-later
"""Native cosmetic circle task creation, defaults, cancel and edit regressions.

The source UI's existing radius10 applies to a single center point. Two-point
radius derivation, scaled/rotated views and the separate edit path stay covered.
"""

import math
from pathlib import Path
import sys
import time
import unittest

import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtWidgets




@unittest.skipIf(not App.GuiUp, "Native GUI command qualification")
class _CosmeticCircleGuiTestCase(unittest.TestCase):
    def _phase(self, label, **values):
        sys.stderr.write("CIRCLE18850 " + label + " " + repr(values) + "\n")
        sys.stderr.flush()


    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "Run each case in an isolated GUI process")
        self.previous_workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        self.doc_name = None
        self.retained = []
        self.messages = []
        self.reports = [(widget, widget.toPlainText())
                        for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
                        if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.assertTrue(self.reports, "Actual Report view must observe caught native errors")
        testcase = self

        class ObserveMessages(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.Show and isinstance(watched, QtWidgets.QMessageBox):
                    testcase.messages.append(watched.text())
                return False

        self.message_observer = ObserveMessages()
        QtWidgets.QApplication.instance().installEventFilter(self.message_observer)
        self.dismiss_timer = QtCore.QTimer()
        self.dismiss_timer.timeout.connect(self._dismiss_messages)
        self.dismiss_timer.start(20)
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("CosmeticCircle18850")
        self.doc_name = self.doc.Name
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 10, 5
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(Path(__file__).with_name("TestTemplate.svg"))
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.Rotation = 0
        self.view.X, self.view.Y = 100, 100
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: len(self.view.getVisibleEdges()) == 4))
        self.page.ViewObject.show()
        self.assertTrue(self._wait(lambda: bool(self._page_views())))
        self.assertEqual(len(self._vertices()), 4)
        self.assertEqual(len(self.view.CosmeticEdges), 0)
        self.original_geometry = (App.Placement(self.source.Placement), self.source.Shape.Volume)


    @staticmethod
    def _events(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()


    def _wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._events()
        return bool(predicate())


    def _page_views(self):
        window = Gui.getMainWindow()
        return [widget for widget in window.findChildren(QtWidgets.QGraphicsView)
                if widget.objectName() == "PageView" and widget.scene() is not None
                and widget.isVisibleTo(window)]


    def _vertices(self):
        result = []
        for index in range(100):
            try:
                result.append((index, self.view.getVertexByIndex(index).Point))
            except ValueError:
                break
        return result


    def _dismiss_messages(self):
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                widget.reject()


    def _assert_no_native_errors(self):
        output = []
        for widget, previous in self.reports:
            current = widget.toPlainText()
            output.append(current[len(previous):] if current.startswith(previous) else current)
        text = "\n".join(output + self.messages).lower()
        for marker in ("access violation", "segmentation fault", "<exception>", "out_of_range"):
            self.assertNotIn(marker, text)
        self.assertFalse(self.messages, "Valid circle selections must not require warnings")


    def _cleanup(self):
        try:
            if Gui.Control.activeDialog():
                dialog = Gui.Control.activeTaskDialog()
                self.retained.append(dialog)
                dialog.reject()
                if Gui.Control.activeDialog():
                    Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            if self.doc_name in App.listDocuments():
                self._phase("before_close")
                App.closeDocument(self.doc_name)
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
                self._events(50)
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
                self._phase("after_close")
            self._assert_no_native_errors()
        finally:
            self.dismiss_timer.stop()
            QtWidgets.QApplication.instance().removeEventFilter(self.message_observer)
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)


    def _accept_user_radius(self, center):
        self.assertTrue(self.radius.setProperty("rawValue", 7.5))
        self.assertAlmostEqual(float(self.radius.property("rawValue")), 7.5)
        self._phase("before_accept")
        self.task.accept()
        self._phase("after_accept")
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()))
        self.assertEqual(len(self.view.CosmeticEdges), 1)
        edge = self.view.CosmeticEdges[0]
        self.assertAlmostEqual(edge.Radius, 7.5)
        self.assertLess((edge.Center - center).Length, 1e-8)
        self.assertNotIn("Invalid", self.view.State)
        self.assertEqual((self.source.Placement, self.source.Shape.Volume), self.original_geometry)
        self.assertTrue(self._page_views())
        self._assert_no_native_errors()


class TestCosmeticCircleSelection(_CosmeticCircleGuiTestCase):
    def _command(self, indices):
        Gui.Selection.clearSelection()
        for index in indices:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Vertex" + str(index))
        actual = [name for selected in Gui.Selection.getSelectionEx()
                  if selected.ObjectName == self.view.Name for name in selected.SubElementNames]
        self.assertEqual(actual, ["Vertex" + str(index) for index in indices])
        self._phase("before_command", vertices=actual)
        Gui.runCommand("TechDraw_CosmeticCircle")
        self._phase("after_command")
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is not None))
        self.task = Gui.Control.activeTaskDialog()
        self.retained.append(self.task)
        forms = []
        for widget in self.task.getDialogContent():
            self.retained.append(widget)
            candidates = [widget] + widget.findChildren(QtWidgets.QWidget)
            forms.extend(candidate for candidate in candidates
                         if candidate.objectName() == "TechDrawGui__TaskCosmeticCircle")
            ancestor = widget.parentWidget()
            while ancestor is not None:
                self.retained.append(ancestor)
                ancestor = ancestor.parentWidget()
        self.assertEqual(len(forms), 1)
        self.form = forms[0]
        self.assertTrue(self.form.inherits("TechDrawGui::TaskCosmeticCircle"))
        self.retained.append(self.form)
        self.radius = self.form.findChild(QtWidgets.QWidget, "qsbRadius")
        self.assertIsNotNone(self.radius)
        self.assertTrue(self.radius.inherits("Gui::QuantitySpinBox"))
        self.retained.append(self.radius)
        initial = float(self.radius.property("rawValue"))
        self._phase("actual_initial_radius", radius=initial)
        with self.subTest(oracle="usable_initial_radius"):
            self.assertTrue(math.isfinite(initial) and initial > 0,
                            "A single-center task must expose a finite positive initial radius")
        if len(indices) == 1:
            with self.subTest(oracle="existing_designer_default_for_single_point"):
                self.assertAlmostEqual(initial, 10.0)
        self._assert_no_native_errors()
        return initial


    def test_one_projected_center_actual_command(self):
        index, center = self._vertices()[0]
        self._command([index])
        self._accept_user_radius(center)


    def test_one_cosmetic_center_actual_command(self):
        tag = self.view.makeCosmeticVertex(App.Vector(0, 0, 0))
        self.assertTrue(tag)
        centers = [(index, point) for index, point in self._vertices() if point.Length < 1e-8]
        self.assertEqual(len(centers), 1)
        self._command([centers[0][0]])
        self._accept_user_radius(centers[0][1])


    def test_two_projected_points_derived_radius_control(self):
        first, second = self._vertices()[:2]
        initial = self._command([first[0], second[0]])
        self.assertAlmostEqual(initial, (second[1] - first[1]).Length)
        self._accept_user_radius(first[1])


    def test_direct_public_circle_creation_control(self):
        center = App.Vector(0, 0, 0)
        tag = self.view.makeCosmeticCircle(center, 7.5)
        self.assertTrue(tag)
        self.assertEqual(len(self.view.CosmeticEdges), 1)
        edge = self.view.getCosmeticEdge(tag)
        self.assertAlmostEqual(edge.Radius, 7.5)
        self.assertLess((edge.Center - center).Length, 1e-8)
        self.assertEqual((self.source.Placement, self.source.Shape.Volume), self.original_geometry)
        self._assert_no_native_errors()


class TestCosmeticCircleCompatibility(_CosmeticCircleGuiTestCase):
    def _command(self, indices):
        Gui.Selection.clearSelection()
        for index in indices:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Vertex" + str(index))
        actual = [name for selected in Gui.Selection.getSelectionEx()
                  if selected.ObjectName == self.view.Name for name in selected.SubElementNames]
        self.assertEqual(actual, ["Vertex" + str(index) for index in indices])
        return self._open_selected_task()


    def _open_selected_task(self):
        self._phase("before_command")
        Gui.runCommand("TechDraw_CosmeticCircle")
        self._phase("after_command")
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is not None))
        self.task = Gui.Control.activeTaskDialog()
        self.retained.append(self.task)
        forms = []
        for widget in self.task.getDialogContent():
            self.retained.append(widget)
            candidates = [widget] + widget.findChildren(QtWidgets.QWidget)
            forms.extend(candidate for candidate in candidates
                         if candidate.objectName() == "TechDrawGui__TaskCosmeticCircle")
            ancestor = widget.parentWidget()
            while ancestor is not None:
                self.retained.append(ancestor)
                ancestor = ancestor.parentWidget()
        self.assertEqual(len(forms), 1)
        self.form = forms[0]
        self.assertTrue(self.form.inherits("TechDrawGui::TaskCosmeticCircle"))
        self.retained.append(self.form)
        self.radius = self.form.findChild(QtWidgets.QWidget, "qsbRadius")
        self.assertIsNotNone(self.radius)
        self.assertTrue(self.radius.inherits("Gui::QuantitySpinBox"))
        self.retained.append(self.radius)
        initial = float(self.radius.property("rawValue"))
        self._phase("actual_initial_radius", radius=initial)
        with self.subTest(oracle="usable_initial_radius"):
            self.assertTrue(math.isfinite(initial) and initial > 0,
                            "A single-center task must expose a finite positive initial radius")
        self._assert_no_native_errors()
        return initial


    def _cancel_and_check(self):
        self.task.reject()
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()))
        self.assertEqual(len(self.view.CosmeticEdges), 0)
        self.assertNotIn("Invalid", self.view.State)
        self.assertEqual((self.source.Placement, self.source.Shape.Volume), self.original_geometry)
        self.assertTrue(self._page_views())
        self._assert_no_native_errors()


    def _select_3d(self, *vertex_names):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.view.Name)
        for name in vertex_names:
            Gui.Selection.addSelection(self.doc.Name, self.source.Name, name)
        actual = [(item.ObjectName, tuple(item.SubElementNames))
                  for item in Gui.Selection.getSelectionEx()]
        self.assertEqual(actual, [(self.view.Name, ()), (self.source.Name, vertex_names)])
        initial = self._open_selected_task()
        mode = self.form.findChild(QtWidgets.QRadioButton, "rb3d1")
        self.assertIsNotNone(mode)
        self.retained.append(mode)
        self.assertTrue(mode.isChecked())
        return initial


    def test_cancel_projected_single_point_keeps_geometry_control(self):
        index, center = self._vertices()[0]
        self._command([index])
        self._cancel_and_check()


    def test_two_points_scaled_rotated_view_control(self):
        self.view.Scale = 2.25
        self.view.Rotation = 27.5
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: "Up-to-date" in self.view.State
                                   and len(self.view.getVisibleEdges()) == 4))
        first, second = self._vertices()[:2]
        initial = self._command([first[0], second[0]])
        self.assertAlmostEqual(initial, (second[1] - first[1]).Length)
        canonical_center = App.Rotation(App.Vector(0, 0, 1), -27.5).multVec(first[1])
        self._accept_user_radius(canonical_center)
        self.assertAlmostEqual(self.view.Scale, 2.25)
        self.assertAlmostEqual(self.view.Rotation, 27.5)


    def test_two_actual_3d_points_derived_radius_cancel_control(self):
        first, second = self.source.Shape.Vertexes[:2]
        initial = self._select_3d("Vertex1", "Vertex2")
        self.assertAlmostEqual(initial, (second.Point - first.Point).Length)
        self._cancel_and_check()


    def test_single_actual_3d_center_keeps_designer_radius_then_cancel(self):
        origins = [index for index, vertex in enumerate(self.source.Shape.Vertexes)
                   if vertex.Point.Length < 1e-8]
        self.assertEqual(len(origins), 1)
        initial = self._select_3d("Vertex" + str(origins[0] + 1))
        with self.subTest(oracle="single_3d_existing_designer_default"):
            self.assertAlmostEqual(initial, 10.0)
        self._cancel_and_check()


    def test_existing_circle_edit_radius_path_unchanged_control(self):
        center = App.Vector(0, 0, 0)
        tag = self.view.makeCosmeticCircle(center, 7.5)
        self.assertTrue(tag)
        indices = []
        for index in range(len(self.view.getVisibleEdges()) + 10):
            try:
                edge = self.view.getCosmeticEdgeBySelection("Edge" + str(index))
            except ValueError:
                continue
            if edge.Tag == tag:
                indices.append(index)
        self.assertEqual(len(indices), 1)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Edge" + str(indices[0]))
        initial = self._open_selected_task()
        self.assertAlmostEqual(initial, 7.5)
        self.assertTrue(self.radius.setProperty("rawValue", 8.25))
        self.task.accept()
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()))
        self.assertEqual(len(self.view.CosmeticEdges), 1)
        edge = self.view.getCosmeticEdge(tag)
        self.assertAlmostEqual(edge.Radius, 8.25)
        self.assertLess((edge.Center - center).Length, 1e-8)
        self.assertEqual((self.source.Placement, self.source.Shape.Volume), self.original_geometry)
        self.assertNotIn("Invalid", self.view.State)
        self._assert_no_native_errors()


if __name__ == "__main__":
    unittest.main()
