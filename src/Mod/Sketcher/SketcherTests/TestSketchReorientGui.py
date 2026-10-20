# SPDX-License-Identifier: LGPL-2.1-or-later
"""Reorient Sketch preserves attachment on cancellation and during undo."""
import unittest

import FreeCAD as App
import Part
import Sketcher
if App.GuiUp:
    import FreeCADGui as Gui
    import SketcherGui  # noqa: F401
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestSketchReorientGui(unittest.TestCase):
    def setUp(self):
        self.previous_doc = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = []
        for item in Gui.Selection.getSelectionEx("*", 0):
            subs = list(item.SubElementNames) or [""]
            points = list(item.PickedPoints)
            for index, sub in enumerate(subs):
                point = points[index] if index < len(points) else App.Vector()
                self.previous_selection.append((item.Object.Document.Name, item.Object.Name,
                                                sub, point.x, point.y, point.z))
        self.strong_widgets = []
        self.timers = []
        self.doc = App.newDocument("SketchReorientAtomicity")
        self.doc.UndoMode = 1
        self.addCleanup(self._cleanup)
        self.assertIsNone(Gui.Control.activeTaskDialog())
        Gui.activateWorkbench("SketcherWorkbench")
        Gui.Selection.clearSelection()
        self.box = self.doc.addObject("Part::Box", "SupportBox")
        self.box.Length, self.box.Width, self.box.Height = 7, 9, 5
        self.box.Placement = App.Placement(App.Vector(11, 13, 17),
                                           App.Rotation(App.Vector(0, 0, 1), 25))
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "AttachedSketch")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(1, 2, 0), App.Vector(4, 6, 0)), False)
        self.doc.recompute()
        self.assertTrue(self.box.Shape.isValid())
        self.assertEqual(self.sketch.GeometryCount, 1)
        self.assertTrue(self.sketch.Shape.isValid())

    def _pump(self):
        Gui.updateGui()
        QtTest.QTest.qWait(50)
        Gui.updateGui()

    @staticmethod
    def _placement(value):
        return (tuple(value.Base), tuple(value.Rotation.Q))

    def _snapshot(self):
        return {
            "support": tuple((obj.Document.Name, obj.Name, tuple(subs))
                             for obj, subs in self.sketch.AttachmentSupport),
            "map_mode": self.sketch.MapMode,
            "map_reversed": self.sketch.MapReversed,
            "offset": self._placement(self.sketch.AttachmentOffset),
            "placement": self._placement(self.sketch.Placement),
            "geometry": tuple((tuple(geo.StartPoint), tuple(geo.EndPoint))
                              for geo in self.sketch.Geometry),
            "constraints": self.sketch.ConstraintCount,
            "state": tuple(self.sketch.State),
        }

    def _prepare(self, attached):
        if attached:
            self.sketch.AttachmentSupport = [(self.box, "Face6")]
            self.sketch.MapMode = "FlatFace"
            self.sketch.AttachmentOffset = App.Placement(App.Vector(1.25, 2.5, 3.75),
                                                        App.Rotation(App.Vector(0, 0, 1), 12))
        else:
            self.sketch.Placement = App.Placement(App.Vector(12, 15, 18),
                                                  App.Rotation(App.Vector(0, 0, 1), 35))
        self.doc.recompute()
        self.assertNotIn("Invalid", self.sketch.State)
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertEqual(bool(self.sketch.AttachmentSupport), attached)
        if attached:
            self.assertEqual(self.sketch.AttachmentSupport[0][0], self.box)
            self.assertEqual(self.sketch.MapMode, "FlatFace")
        self.doc.clearUndos()
        self.assertEqual(self.doc.UndoCount, 0)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.sketch.Name)
        self._pump()
        self.before = self._snapshot()

    def _run_command(self, attached, detach, accept):
        stages = []
        errors = []
        timer = QtCore.QTimer(Gui.getMainWindow())
        timer.setInterval(20)
        self.timers.append(timer)
        clock = QtCore.QElapsedTimer()
        clock.start()

        def service_modal():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                return
            try:
                self.strong_widgets.append(dialog)
                if clock.elapsed() > 5000:
                    self.fail("Native command modal did not finish before the fixture watchdog")
                if isinstance(dialog, QtWidgets.QMessageBox):
                    self.assertTrue(attached)
                    self.assertEqual(stages, [])
                    stages.append("detach")
                    role = QtWidgets.QMessageBox.Yes if detach else QtWidgets.QMessageBox.No
                    button = dialog.button(role)
                    self.assertIsNotNone(button)
                    self.strong_widgets.append(button)
                    button.click()
                    return
                self.assertEqual(dialog.objectName(), "SketcherGui__SketchOrientationDialog")
                self.assertEqual(stages, ["detach"] if attached else [])
                stages.append("orientation")
                editor = dialog.findChild(QtWidgets.QWidget, "Offset_doubleSpinBox")
                self.assertIsNotNone(editor)
                self.assertEqual(str(editor.property("unit")), "mm")
                self.assertTrue(editor.setProperty("rawValue", 11.25))
                self.assertAlmostEqual(editor.property("rawValue"), 11.25, places=12)
                xy = dialog.findChild(QtWidgets.QRadioButton, "XY_radioButton")
                reverse = dialog.findChild(QtWidgets.QCheckBox, "Reverse_checkBox")
                self.assertIsNotNone(xy)
                self.assertIsNotNone(reverse)
                self.assertTrue(xy.isChecked())
                self.assertFalse(reverse.isChecked())
                buttons = dialog.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
                self.assertIsNotNone(buttons)
                role = QtWidgets.QDialogButtonBox.Ok if accept else QtWidgets.QDialogButtonBox.Cancel
                button = buttons.button(role)
                self.assertIsNotNone(button)
                self.strong_widgets.extend([editor, xy, reverse, buttons, button])
                button.click()
            except BaseException as error:
                errors.append(error)
                dialog.reject()

        timer.timeout.connect(service_modal)
        timer.start()
        try:
            Gui.runCommand("Sketcher_ReorientSketch")
        finally:
            timer.stop()
        if errors:
            raise errors[0]
        expected = ["detach", "orientation"] if attached and detach else ["detach"] if attached else ["orientation"]
        self.assertEqual(stages, expected, "Must traverse the real expected command dialogs")
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self._pump()
        if accept:
            self.assertEqual(self.doc.UndoCount, 1)
            self.assertEqual(len(self.doc.UndoNames), 1)
            self.reorient_undo_name = self.doc.UndoNames[0]

    def _assert_unchanged(self):
        current = self._snapshot()
        for field in self.before:
            with self.subTest(field=field):
                self.assertEqual(current[field], self.before[field])
        self.assertIsNone(Gui.getDocument(self.doc.Name).getInEdit())
        self.assertEqual(self.doc.UndoCount, 0)

    def _assert_accepted(self):
        self.assertEqual(self.sketch.AttachmentSupport, [])
        self.assertLess((self.sketch.Placement.Base - App.Vector(0, 0, 11.25)).Length, 1e-10)
        self.assertLess(self.sketch.Placement.Rotation.Angle, 1e-10)
        self.assertEqual(self._snapshot()["geometry"], self.before["geometry"])
        self.assertEqual(self.sketch.ConstraintCount, 0)
        self.assertTrue(self.sketch.Shape.isValid())
        self.assertIsNotNone(Gui.getDocument(self.doc.Name).getInEdit())
        Gui.runCommand("Sketcher_LeaveSketch")
        self._pump()
        self.assertIsNone(Gui.getDocument(self.doc.Name).getInEdit())
        self.assertGreater(self.doc.UndoCount, 0)

    def _undo_redo(self):
        accepted = self._snapshot()
        self.assertIn(self.reorient_undo_name, self.doc.UndoNames)
        later_entries = 0
        # Leaving edit mode may add its own recompute transaction. Verify that
        # undoing such bookkeeping preserves the accepted model, then target
        # the actual Reorient transaction captured before entering/leaving edit.
        while self.doc.UndoNames[0] != self.reorient_undo_name:
            self.assertLess(later_entries, 3)
            self.assertGreater(self.doc.UndoCount, 1)
            self.doc.undo()
            self.doc.recompute()
            current = self._snapshot()
            for field in accepted:
                with self.subTest(stage="post-edit bookkeeping undo", field=field):
                    self.assertEqual(current[field], accepted[field])
            later_entries += 1
        self.assertEqual(self.doc.UndoNames[0], self.reorient_undo_name)
        self.doc.undo()
        self.doc.recompute()
        current = self._snapshot()
        for field in self.before:
            with self.subTest(stage="undo", field=field):
                self.assertEqual(current[field], self.before[field])
        self.doc.redo()
        self.doc.recompute()
        current = self._snapshot()
        for field in accepted:
            with self.subTest(stage="redo", field=field):
                self.assertEqual(current[field], accepted[field])
        for index in range(later_entries):
            self.assertGreater(self.doc.RedoCount, 0)
            self.doc.redo()
            self.doc.recompute()
            current = self._snapshot()
            for field in accepted:
                with self.subTest(stage="post-edit bookkeeping redo", index=index, field=field):
                    self.assertEqual(current[field], accepted[field])

    def test_attached_confirm_detach_then_cancel_is_atomic(self):
        self._prepare(True)
        self._run_command(True, True, False)
        self._assert_unchanged()

    def test_attached_decline_detach_control(self):
        self._prepare(True)
        self._run_command(True, False, False)
        self._assert_unchanged()

    def test_unattached_cancel_control(self):
        self._prepare(False)
        self._run_command(False, False, False)
        self._assert_unchanged()

    def test_attached_accept_retains_existing_reorientation_control(self):
        self._prepare(True)
        self._run_command(True, True, True)
        self._assert_accepted()

    def test_attached_accept_undo_restores_attachment(self):
        self._prepare(True)
        self._run_command(True, True, True)
        self._assert_accepted()
        self._undo_redo()

    def test_unattached_accept_undo_control(self):
        self._prepare(False)
        self._run_command(False, False, True)
        self._assert_accepted()
        self._undo_redo()

    def _cleanup(self):
        for timer in self.timers:
            timer.stop()
            timer.deleteLater()
        modal = QtWidgets.QApplication.activeModalWidget()
        if modal:
            modal.reject()
        if self.doc.Name in App.listDocuments():
            App.setActiveDocument(self.doc.Name)
            gui_doc = Gui.getDocument(self.doc.Name)
            if gui_doc.getInEdit():
                gui_doc.resetEdit()
                self._pump()
            if Gui.Control.activeTaskDialog(gui_doc):
                Gui.Control.closeDialog(gui_doc)
                self._pump()
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        if self.previous_doc in App.listDocuments():
            App.setActiveDocument(self.previous_doc)
        elif self.previous_doc is None:
            App.setActiveDocument("")
        for args in self.previous_selection:
            doc_name, obj_name = args[:2]
            if doc_name in App.listDocuments() and App.getDocument(doc_name).getObject(obj_name):
                Gui.Selection.addSelection(*args)
        self._pump()
