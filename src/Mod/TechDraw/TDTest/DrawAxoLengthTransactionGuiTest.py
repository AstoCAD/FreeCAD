# SPDX-License-Identifier: LGPL-2.1-or-later
"""Rejected axonometric dimensions preserve document transactions and undo history."""

from pathlib import Path
import time
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
from PySide import QtCore, QtWidgets


class TestAxoLengthTransactionGui(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        ]
        self.doc_name = None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("AxoTransaction_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(Path(__file__).with_name("TestTemplate.svg"))
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(1, 1, 1)
        self.view.XDirection = App.Vector(1, -1, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        self.assertTrue(
            self._wait(
                lambda: len(self.view.getVisibleEdges()) >= 2 and "Up-to-date" in self.view.State
            ),
            "The ordinary box view must finish projection",
        )
        self.page.ViewObject.show()
        self._pump()
        self.edge_names = self._nonparallel_edges()
        self.assertEqual(len(self.edge_names), 2)
        self.doc.recompute()
        self.doc.clearUndos()
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])
        self.assertEqual(self.doc.FileName, "")

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            doc = App.getDocument(self.doc_name)
            if doc.HasPendingTransaction:
                doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, obj, names in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(obj):
                if names:
                    for name in names:
                        Gui.Selection.addSelection(document, obj, name)
                else:
                    Gui.Selection.addSelection(document, obj)

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _nonparallel_edges(self):
        edges = []
        for index in range(len(self.view.getVisibleEdges())):
            name = "Edge" + str(index)
            edge = self.view.getEdgeBySelection(name)
            self.assertEqual(len(edge.Vertexes), 2)
            direction = edge.Vertexes[1].Point - edge.Vertexes[0].Point
            self.assertGreater(direction.Length, 0)
            for first_name, first_direction in edges:
                ratio = first_direction.cross(direction).Length / (
                    first_direction.Length * direction.Length
                )
                if ratio > 0.2:
                    return first_name, name
            edges.append((name, direction))
        self.fail("The projected box must contain two genuinely nonparallel edges")

    def _selection(self):
        return tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()
        )

    def _select(self, *names):
        Gui.Selection.clearSelection()
        if names:
            for name in names:
                Gui.Selection.addSelection(self.doc.Name, self.view.Name, name)
            self.assertEqual(self._selection(), ((self.doc.Name, self.view.Name, tuple(names)),))
        else:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name)
            self.assertEqual(self._selection(), ((self.doc.Name, self.view.Name, ()),))

    def _model_state(self):
        return {
            "objects": tuple(obj.Name for obj in self.doc.Objects),
            "page_views": tuple(view.Name for view in self.page.Views),
            "source_label": self.source.Label,
            "source_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "source_volume": self.source.Shape.Volume,
            "source_position": tuple(self.source.Placement.Base),
            "source_rotation": tuple(self.source.Placement.Rotation.Q),
            "view_source": tuple(obj.Name for obj in self.view.Source),
            "view_edge_lengths": tuple(edge.Length for edge in self.view.getVisibleEdges()),
        }

    def _snapshot(self):
        return {
            "model": self._model_state(),
            "pending": self.doc.HasPendingTransaction,
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "touched": self.doc.isTouched(),
            "selection": self._selection(),
        }

    def _run(self, expected_message=None):
        expected = [] if expected_message is None else [expected_message]
        seen, unexpected, retained = [], [], []
        active = [True]

        class OwnedMessageResponder(QtCore.QObject):
            def eventFilter(self, watched, event):
                if (
                    active[0]
                    and event.type() == QtCore.QEvent.Show
                    and isinstance(watched, QtWidgets.QMessageBox)
                ):
                    retained.append(watched)
                    identity = (watched.windowTitle(), watched.text())
                    if identity == ("TechDraw_Utils", expected_message) and not seen:
                        seen.append(watched.text())
                        QtCore.QTimer.singleShot(0, watched.accept)
                    else:
                        unexpected.append(identity)
                return False

        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports, "The native Report view must observe caught command exceptions")
        report_before = [widget.toPlainText() for widget in reports]
        responder = OwnedMessageResponder()
        app = QtWidgets.QApplication.instance()
        app.installEventFilter(responder)
        try:
            Gui.runCommand("TechDraw_AxoLengthDimension")
        finally:
            active[0] = False
            app.removeEventFilter(responder)
        self._pump()
        self.assertEqual(unexpected, [], "Only the expected validation message may be answered")
        self.assertEqual(seen, expected, "The actual command must reach selection validation")
        output = []
        for widget, previous in zip(reports, report_before):
            current = widget.toPlainText()
            output.append(current[len(previous) :] if current.startswith(previous) else current)
        text = "\n".join(output).lower()
        for marker in (
            "traceback",
            "access violation",
            "segmentation fault",
            "<exception>",
            "running the python command",
        ):
            self.assertNotIn(marker, text)

    def _rejected(self, message):
        before = self._snapshot()
        self._run(message)
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])

    def test_no_selection_preserves_transaction_state(self):
        self.assertEqual(self._selection(), ())
        self._rejected("No view selected")

    def test_view_only_selection_preserves_transaction_state(self):
        self._select()
        self._rejected("Select at least 2 edges")

    def test_single_edge_selection_preserves_transaction_state(self):
        self._select(self.edge_names[0])
        self._rejected("Select at least 2 edges")

    def test_rejection_preserves_committed_undo_history(self):
        self.doc.openTransaction("Existing committed edit")
        self.source.Label = "Committed source label"
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(self.doc.UndoNames, ["Existing committed edit"])
        self.assertFalse(self.doc.HasPendingTransaction)
        self._select()
        self._rejected("Select at least 2 edges")

    def test_rejection_preserves_redo_history(self):
        original = self.source.Label
        self.doc.openTransaction("Existing redo edit")
        self.source.Label = "Undone source label"
        self.doc.commitTransaction()
        self.doc.recompute()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.source.Label, original)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, ["Existing redo edit"])
        self._select(self.edge_names[0])
        self._rejected("Select at least 2 edges")

    def test_rejection_does_not_commit_unrelated_pending_edit(self):
        original = self.source.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.source.Label = "Uncommitted source label"
        self.assertTrue(self.doc.HasPendingTransaction)
        self._select()
        self._rejected("Select at least 2 edges")
        self.doc.abortTransaction()
        with self.subTest(oracle="original_transaction_still_abortable"):
            self.assertEqual(self.source.Label, original)
        with self.subTest(oracle="aborted_edit_not_in_undo_history"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_valid_two_edge_dimension_creation_undo_redo_control(self):
        self._select(*self.edge_names)
        before = self._model_state()
        self._run()
        dimensions = [
            obj for obj in self.doc.Objects if obj.isDerivedFrom("TechDraw::DrawViewDimension")
        ]
        self.assertEqual(len(dimensions), 1)
        dimension = dimensions[0]
        name = dimension.Name
        self.assertEqual(dimension.Type, "Distance")
        self.assertTrue(dimension.AngleOverride)
        self.assertEqual(
            [(obj.Name, tuple(subs)) for obj, subs in dimension.References2D],
            [(self.view.Name, (self.edge_names[0],))],
        )
        self.assertIn(dimension, self.page.Views)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Create axonometric length dimension"])
        self.doc.recompute()
        self.assertTrue(dimension.isValid())
        first, second = dimension.getLinearPoints()
        self.assertGreater((second - first).Length, 0)
        self.doc.undo()
        self.doc.recompute()
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual(self._model_state(), before)
        self.doc.redo()
        self.doc.recompute()
        restored = self.doc.getObject(name)
        self.assertIsNotNone(restored)
        self.assertTrue(restored.isValid())
        self.assertIn(restored, self.page.Views)

    def test_harmless_view_command_pending_transaction_control(self):
        original = self.source.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.source.Label = "Uncommitted source label"
        self.assertTrue(self.doc.HasPendingTransaction)
        self._select()
        command = Gui.Command.get("Std_ViewFitAll")
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive(), "The ordinary page Fit All command must be active")
        before = self._snapshot()
        Gui.runCommand("Std_ViewFitAll")
        self._pump()
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])
        self.doc.abortTransaction()
        with self.subTest(oracle="original_transaction_still_abortable"):
            self.assertEqual(self.source.Label, original)
        with self.subTest(oracle="aborted_edit_not_in_undo_history"):
            self.assertEqual(self.doc.UndoNames, [])

    def _next_direct_edit(self, reject_command):
        self._select()
        before = self._snapshot()
        self.assertFalse(before["pending"])
        self.assertEqual(before["undo"], ())
        booked_before = self.doc.getBookedTransactionID()
        if reject_command:
            self._run("Select at least 2 edges")
        else:
            self._pump()
        booked_after_command = self.doc.getBookedTransactionID()
        self.source.Label = "Next direct source label"
        after_edit = self._snapshot()
        with self.subTest(oracle="no_new_booked_transaction_after_rejection"):
            self.assertEqual(booked_after_command, booked_before)
        with self.subTest(oracle="next_edit_not_captured_by_rejected_command"):
            self.assertEqual(after_edit["undo"], ())
        with self.subTest(oracle="next_edit_does_not_materialize_rejected_transaction"):
            self.assertFalse(after_edit["pending"])
        self.assertEqual(self.source.Label, "Next direct source label")
        self.assertEqual(after_edit["model"]["objects"], before["model"]["objects"])
        self.assertEqual(after_edit["model"]["page_views"], before["model"]["page_views"])
        self.assertEqual(after_edit["model"]["source_volume"], before["model"]["source_volume"])
        self.assertEqual(after_edit["selection"], before["selection"])

    def test_rejected_command_does_not_capture_next_direct_edit(self):
        self._next_direct_edit(True)

    def test_direct_edit_without_axo_command_control(self):
        self._next_direct_edit(False)
