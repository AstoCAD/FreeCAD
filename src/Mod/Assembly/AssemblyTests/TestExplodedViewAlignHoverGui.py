# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exploded-view alignment follows native selection and viewport hover events."""

import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import CommandCreateView as Views
    import UtilsAssembly
    from PySide import QtCore, QtGui, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestExplodedViewAlignHoverGui(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx("*", 0)
        )
        self.doc_name = None
        self.panel = None
        self.previous_cursor = QtGui.QCursor.pos()
        self.alignment_mode_started = False
        pref = Views.Preferences.preferences()
        self.parts_as_solid = (
            pref.GetBool("PartsAsSingleSolid") if "PartsAsSingleSolid" in pref.GetBools() else None
        )
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog(), "An idle task panel is required")
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("ExplodedAlignHover_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.assembly.newObject("Assembly::JointGroup", "Joints")
        self.first = self.assembly.newObject("Part::Box", "First")
        self.second = self.assembly.newObject("Part::Box", "Second")
        for box in (self.first, self.second):
            box.Length, box.Width, box.Height = 10, 8, 6
        self.second.Placement.Base = App.Vector(25, 0, 0)
        self.doc.recompute()
        self.owner = Gui.getDocument(self.doc_name)
        self.owner.setEdit(self.assembly)
        self.assertTrue(self._wait(lambda: UtilsAssembly.activeAssembly() == self.assembly))
        self.assertTrue(self.assembly.ViewObject.isInEditMode())
        self.assertEqual(UtilsAssembly.number_of_components_in(self.assembly), 2)
        self.original = {
            obj.Name: (tuple(obj.Placement.Base), tuple(obj.Placement.Rotation.Q))
            for obj in (self.first, self.second)
        }
        self.original_objects = {obj.Name for obj in self.doc.Objects}
        self._assert_original()
        self.view = self.owner.activeView()
        self.view.viewFront()
        self.view.fitAll()
        self._pump()
        self.doc.clearUndos()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertTrue(Gui.Command.get("Assembly_CreateView").isActive())

    @staticmethod
    def _pump(milliseconds=20):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _cleanup(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc_name in App.listDocuments():
                App.setActiveDocument(self.doc_name)
                owner = Gui.getDocument(self.doc_name)
                dialog = Gui.Control.activeTaskDialog(owner)
                if dialog is not None:
                    self.assertEqual(dialog.getDocumentName(), self.doc_name)
                    dialog.reject()
                    self._pump()
                doc = App.getDocument(self.doc_name)
                if doc.HasPendingTransaction:
                    doc.abortTransaction()
                if owner.getInEdit():
                    owner.resetEdit()
                App.closeDocument(self.doc_name)
            self.panel = None
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            QtWidgets.QApplication.processEvents()
            pref = Views.Preferences.preferences()
            if self.parts_as_solid is None:
                pref.RemBool("PartsAsSingleSolid")
            else:
                pref.SetBool("PartsAsSingleSolid", self.parts_as_solid)
            if self.previous_document in App.listDocuments():
                App.setActiveDocument(self.previous_document)
            elif self.previous_document is None:
                App.setActiveDocument("")
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            for document, name, subnames in self.previous_selection:
                if document in App.listDocuments() and App.getDocument(document).getObject(name):
                    for subname in subnames or ("",):
                        Gui.Selection.addSelection(document, name, subname)

        finally:
            if self.alignment_mode_started:
                Gui.Selection.setSelectionStyle(Gui.Selection.SelectionStyle.NormalSelection)
                self.alignment_mode_started = False
            QtGui.QCursor.setPos(self.previous_cursor)

    def _assert_original(self):
        for obj in (self.first, self.second):
            self.assertTrue(obj.Shape.isValid())
            self.assertAlmostEqual(obj.Shape.Volume, 480, places=8)
            self.assertEqual(
                (tuple(obj.Placement.Base), tuple(obj.Placement.Rotation.Q)),
                self.original[obj.Name],
            )

    def _create(self):
        Gui.runCommand("Assembly_CreateView")
        self.assertTrue(self._wait(lambda: Gui.Control.activeDialog()))
        panel = Gui.doCommandEval("panel")
        self.assertIsInstance(panel, Views.TaskAssemblyCreateView)
        self.assertEqual(panel.assembly, self.assembly)
        dialog = Gui.Control.activeTaskDialog(self.owner)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.getDocumentName(), self.doc_name)
        self.panel = panel
        self.assertEqual(panel.viewObj.Group, [])
        self.assertFalse(panel.form.btnAlignDragger.isEnabled())
        self.assertFalse(panel.selectingFeature)
        self._assert_original()
        return panel

    def _select_second(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc_name, self.assembly.Name, self.second.Name + ".")
        self.assertTrue(self._wait(lambda: self.panel.selectedObjs == [self.second]))
        self.assertTrue(self.panel.form.btnAlignDragger.isEnabled())
        self.assertTrue(self.assembly.ViewObject.DraggerVisibility)

    def _action(self, index):
        button = self.panel.form.btnAlignDragger
        self.assertTrue(button.isEnabled())
        actions = button.menu().actions()
        self.assertEqual(len(actions), 3)
        self.assertTrue(actions[index].isEnabled())
        actions[index].trigger()
        self._pump()
        if index == 0:
            self.alignment_mode_started = True

    def _viewport(self):
        viewport = self.view.graphicsView().viewport()
        self.assertTrue(viewport.isVisible())
        self.assertGreater(viewport.width(), 100)
        self.assertGreater(viewport.height(), 100)
        return viewport

    def _move_mouse(self, point):
        viewport = self._viewport()
        self.assertTrue(viewport.rect().contains(point.toPoint()))
        viewport.setFocus(QtCore.Qt.OtherFocusReason)
        global_point = viewport.mapToGlobal(point.toPoint())
        QtGui.QCursor.setPos(global_point)
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            point,
            QtCore.QPointF(global_point),
            QtCore.Qt.NoButton,
            QtCore.Qt.NoButton,
            QtCore.Qt.NoModifier,
        )
        QtWidgets.QApplication.sendEvent(viewport, event)
        self._pump()

    def _corner(self):
        # The dock overlay manager routes mouse events by the real cursor position,
        # so use a viewport corner that no (transparent) overlay panel covers.
        viewport = self._viewport()
        width, height = viewport.width(), viewport.height()
        for x, y in ((4, 4), (4, height - 5), (width // 2, height - 5), (width // 2, 4)):
            point = QtCore.QPointF(x, y)
            hit = QtWidgets.QApplication.widgetAt(viewport.mapToGlobal(point.toPoint()))
            if hit is not None and (hit == viewport or viewport.isAncestorOf(hit)):
                return point
        self.fail("Every viewport corner is covered by another widget")

    def _screen(self, world):
        viewport = self._viewport()
        x, y = self.view.getPointOnScreen(world)
        ratio = viewport.devicePixelRatioF()
        point = QtCore.QPointF(x / ratio, viewport.height() - y / ratio)
        self.assertTrue(viewport.rect().contains(point.toPoint()))
        return point

    def _report_snapshot(self):
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports, "The native Report view must observe callback exceptions")
        return [(widget, widget.toPlainText()) for widget in reports]

    def _assert_no_report_error(self, snapshot):
        text = "\n".join(
            after[len(before) :] if after.startswith(before) else after
            for widget, before in snapshot
            for after in (widget.toPlainText(),)
        )
        self.assertNotRegex(text.lower(), r"traceback|typeerror|<exception>", text)

    def _end_alignment(self):
        if not self.panel.selectingFeature:
            return
        point = self._corner()
        self._move_mouse(point)
        viewport = self._viewport()
        global_point = QtCore.QPointF(viewport.mapToGlobal(point.toPoint()))
        for kind, buttons in (
            (QtCore.QEvent.MouseButtonPress, QtCore.Qt.RightButton),
            (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
        ):
            event = QtGui.QMouseEvent(
                kind, point, global_point, QtCore.Qt.RightButton, buttons, QtCore.Qt.NoModifier
            )
            QtWidgets.QApplication.sendEvent(viewport, event)
            self._pump()
        self.assertTrue(self._wait(lambda: not self.panel.selectingFeature))
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is not None:
            self.assertIsInstance(popup, QtWidgets.QMenu)
            QtTest.QTest.keyClick(popup, QtCore.Qt.Key_Escape)
            self._pump()
            self.assertIsNone(QtWidgets.QApplication.activePopupWidget())
        self.alignment_mode_started = False

    def _reject(self):
        self._end_alignment()
        name = self.panel.viewObj.Name
        dialog = Gui.Control.activeTaskDialog(self.owner)
        self.assertIsNotNone(dialog)
        dialog.reject()
        self.panel = None
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()))
        self.assertIsNone(self.doc.getObject(name))
        self.doc.recompute()
        self.assertEqual({obj.Name for obj in self.doc.Objects}, self.original_objects)
        self._assert_original()

    def test_idle_new_view_disables_alignment_and_cancels_control(self):
        self._create()
        self.assertEqual(Gui.Selection.getSelection(), [])
        self.assertFalse(self.panel.form.btnAlignDragger.isEnabled())
        self._reject()

    def test_native_center_and_origin_menu_actions_control(self):
        self._create()
        self._select_second()
        report = self._report_snapshot()
        self._action(2)
        self.assertLess(
            (self.assembly.ViewObject.DraggerPlacement.Base - self.second.Placement.Base).Length,
            1e-7,
        )
        self._action(1)
        self.assertLess(
            (
                self.assembly.ViewObject.DraggerPlacement.Base - self.second.Shape.BoundBox.Center
            ).Length,
            1e-7,
        )
        self._assert_no_report_error(report)
        self._reject()

    def test_native_empty_hover_has_no_alignment_control(self):
        self._create()
        self._select_second()
        report = self._report_snapshot()
        self._action(0)
        self.assertTrue(self.panel.selectingFeature)
        self._move_mouse(self._corner())
        self.assertTrue(
            self._wait(
                lambda: not self.view.getObjectInfo(self.view.getCursorPos())
                and self.panel.presel_ref is None
            ),
            "The actual viewport corner must be empty before judging the idle hover gate",
        )
        self.assertFalse(self.assembly.ViewObject.DraggerVisibility)
        self._assert_no_report_error(report)
        self._assert_original()
        self._reject()

    def test_native_step_quantity_edit_and_cancel_control(self):
        self._create()
        step = self.assembly.newObject("App::FeaturePython", "Move")
        Views.ExplodedViewStep(step, 0)
        Views.ViewProviderExplodedViewStep(step.ViewObject)
        step.References = [self.assembly, [self.second.Name + "."]]
        step.MovementTransform = App.Placement(App.Vector(5, 0, 0), App.Rotation())
        self.panel.viewObj.Group = [step]
        self.assertTrue(self._wait(lambda: self.panel.form.stepList.count() == 1))
        spinbox = self.panel.moveSpinboxes[step.Name]
        edit = spinbox.findChild(QtWidgets.QLineEdit)
        self.assertIsNotNone(edit)
        report = self._report_snapshot()
        edit.setFocus()
        QtTest.QTest.keyClick(edit, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClicks(edit, "9 mm")
        QtTest.QTest.keyClick(edit, QtCore.Qt.Key_Tab)
        self.assertIsNotNone(Gui.Control.activeTaskDialog(self.owner))
        self.assertIsNotNone(self.doc.getObject(self.panel.viewObj.Name))
        self.assertTrue(self._wait(lambda: abs(step.MovementTransform.Base.x - 9) < 1e-7))
        self.assertAlmostEqual(spinbox.property("rawValue"), 9, places=7)
        self.assertLess((self.second.Placement.Base - App.Vector(34, 0, 0)).Length, 1e-7)
        self.assertEqual(step.MoveType, "Normal")
        self.assertAlmostEqual(self.second.Shape.Volume, 480, places=8)
        self._assert_no_report_error(report)
        self._reject()

    def test_native_planar_face_hover_positions_and_orients_dragger(self):
        self._create()
        self._select_second()
        self.view.viewFront()
        self.view.fitAll()
        self._pump()
        direction = self.view.getViewDirection()
        faces = [
            (index, face)
            for index, face in enumerate(self.first.Shape.Faces, 1)
            if face.Surface.TypeId == "Part::GeomPlane"
            and face.normalAt(0, 0).dot(direction) < -0.999999
        ]
        self.assertEqual(len(faces), 1)
        face_index, face = faces[0]
        face_name = "Face" + str(face_index)
        expected_center = App.Vector(face.CenterOfGravity)
        expected_normal = App.Vector(face.normalAt(0, 0))
        report = self._report_snapshot()
        self._action(0)
        self.assertTrue(self.panel.selectingFeature)
        point = self._screen(expected_center)

        def admitted():
            native = Gui.Selection.getPreselection()
            ref = self.panel.presel_ref
            if native is None or not ref or len(native.SubElementNames) != 1:
                return False
            subname = native.SubElementNames[0]
            return (
                native.DocumentName == self.doc_name
                and native.ObjectName in (self.assembly.Name, self.first.Name)
                and subname.split(".")[-1] == face_name
                and (native.ObjectName == self.first.Name or self.first.Name in subname.split("."))
                and ref[0] in (self.assembly, self.first)
                and ref[0].Name == native.ObjectName
                and ref[1][0] == subname
            )

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self._move_mouse(point + QtCore.QPointF(-1, -1))
            self._move_mouse(point)
            if admitted():
                break
        self.assertTrue(admitted(), "Real cursor pick and native preselection must admit the face")
        preselection = Gui.Selection.getPreselection()
        self.assertEqual(len(preselection.SubObjects), 1)
        self.assertEqual(preselection.SubObjects[0].ShapeType, "Face")
        self.assertLess((preselection.SubObjects[0].CenterOfGravity - expected_center).Length, 1e-7)
        with self.subTest(contract="native hover callback has no Python argument error"):
            self._assert_no_report_error(report)
        with self.subTest(contract="native hover shows dragger"):
            self.assertTrue(self.assembly.ViewObject.DraggerVisibility)
        placement = self.assembly.ViewObject.DraggerPlacement
        with self.subTest(contract="native selected face world center"):
            self.assertLess((placement.Base - expected_center).Length, 1e-7)
        with self.subTest(contract="native selected face world normal"):
            axis = placement.Rotation.multVec(App.Vector(0, 0, 1))
            self.assertAlmostEqual(abs(axis.dot(expected_normal)), 1, places=7)
        for move, delta in enumerate((QtCore.QPointF(-2, -1), QtCore.QPointF(2, 1)), 1):
            self._move_mouse(point + delta)
            with self.subTest(
                contract="successive native hover retains the selected face", move=move
            ):
                self.assertTrue(
                    admitted(), "Native preselection and task reference must still match"
                )
            with self.subTest(
                contract="successive native hover keeps the dragger visible", move=move
            ):
                self.assertTrue(self.assembly.ViewObject.DraggerVisibility)
        with self.subTest(
            contract="successive native hover callbacks have no Python argument error"
        ):
            self._assert_no_report_error(report)
        self.assertEqual(self.panel.viewObj.Group, [])
        self._assert_original()
        self._reject()


if __name__ == "__main__":
    unittest.main()
