# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regression tests for empty Extend/Shorten selections and transaction safety.

No cosmetic wrapper or CosmeticEdges property is read.  Geometry observations
use independent Part edge copies returned by the public view APIs.
"""

import math
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import TechDraw  # noqa: F401
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "GUI command diagnostic")
class TestExtendShortenTransactionGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("ExtendShortenTransaction")
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        fixture = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(fixture.is_file())
        template.Template = str(fixture)
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        self.assertTrue(
            self._wait(
                lambda: "Up-to-date" in self.view.State and len(self.view.getVisibleEdges()) >= 4
            )
        )
        self.assertGreaterEqual(len(self.view.getVisibleEdges()), 4)
        self.base_edge_count = len(self.view.getVisibleEdges()) + len(self.view.getHiddenEdges())
        self.assertGreater(self.base_edge_count, 0)
        self.projected_edge = "Edge0"
        self.assertGreater(self.view.getEdgeBySelection(self.projected_edge).Length, 0)
        vertex = self.view.getVertexBySelection("Vertex1")
        self.assertTrue(all(math.isfinite(value) for value in vertex.Point))

        # add1CEToGE appends to the geometry edge vector; both public edge lists
        # partition that vector, including its hidden entries.
        tag = self.view.makeCosmeticLine(App.Vector(41, 17, 0), App.Vector(48, 17, 0))
        self.assertIsInstance(tag, str)
        self.assertTrue(tag)
        self.cosmetic_edge = "Edge" + str(self.base_edge_count)
        self.doc.recompute()
        self.assertTrue(
            self._wait(
                lambda: "Up-to-date" in self.view.State
                and len(self.view.getVisibleEdges()) + len(self.view.getHiddenEdges())
                == self.base_edge_count + 1
            )
        )
        self.assertEqual(
            len(self.view.getVisibleEdges()) + len(self.view.getHiddenEdges()),
            self.base_edge_count + 1,
        )
        line = self.view.getEdgeBySelection(self.cosmetic_edge)
        self.assertAlmostEqual(line.Length, 7.0, places=8)
        self.assertAlmostEqual(line.BoundBox.XMin, 41.0, places=8)
        self.assertAlmostEqual(line.BoundBox.XMax, 48.0, places=8)
        self.assertAlmostEqual(line.BoundBox.YMin, 17.0, places=8)
        self.assertAlmostEqual(line.BoundBox.YMax, 17.0, places=8)
        self.page.ViewObject.show()
        self._pump()
        self.doc.recompute()
        self.assertTrue(self._wait(self.view.isProjectionReady))
        self.doc.clearUndos()
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate):
        deadline = time.monotonic() + 20
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc.Name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._pump()
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _select(self, name=None):
        Gui.Selection.clearSelection()
        if name is None:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name)
            expected = ()
        else:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name, name)
            expected = (name,)
        selected = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].DocumentName, self.doc.Name)
        self.assertEqual(selected[0].ObjectName, self.view.Name)
        self.assertEqual(tuple(selected[0].SubElementNames), expected)

    def _geometry(self):
        edges = []
        for edge in self.view.getVisibleEdges() + self.view.getHiddenEdges():
            points = tuple(
                tuple(round(value, 9) for value in vertex.Point) for vertex in edge.Vertexes
            )
            edges.append((round(edge.Length, 9), min(points, tuple(reversed(points)))))
        return tuple(sorted(edges))

    def _model(self):
        return {
            "objects": tuple((obj.Name, obj.TypeId) for obj in self.doc.Objects),
            "page_views": tuple(obj.Name for obj in self.page.Views),
            "source_label": self.source.Label,
            "source_volume": self.source.Shape.Volume,
            "source_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "geometry": self._geometry(),
        }

    def _snapshot(self):
        return {
            "model": self._model(),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
        }

    def _run(self, command_name):
        command = Gui.Command.get(command_name)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive(), "The ordinary GUI command must be enabled")
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports)
        before = [widget.toPlainText() for widget in reports]
        self.messages = []
        retained = []
        testcase = self

        class MessageObserver(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.Show and isinstance(
                    watched, QtWidgets.QMessageBox
                ):
                    retained.append(watched)
                    testcase.messages.append((watched.windowTitle(), watched.text()))
                return False

        observer = MessageObserver()
        application = QtWidgets.QApplication.instance()
        application.installEventFilter(observer)
        try:
            Gui.runCommand(command_name)
        finally:
            application.removeEventFilter(observer)
        self._pump()
        self.assertEqual(self.messages, [], "These ordinary selection paths do not show a warning")
        output = []
        for widget, previous in zip(reports, before):
            current = widget.toPlainText()
            output.append(current[len(previous) :] if current.startswith(previous) else current)
        text = "\n".join(output).lower()
        for marker in ("traceback", "access violation", "segmentation fault", "<exception>"):
            self.assertNotIn(marker, text)

    def _pending(self):
        original = self.source.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.source.Label = "Uncommitted source label"
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertNotEqual(self.source.Label, original)
        self.assertEqual(self.doc.UndoNames, ["Unrelated pending edit"])
        return original

    def _preserve_pending(self, command_name, selected_name):
        self._select(selected_name)
        original = self._pending()
        before = self._snapshot()
        self._run(command_name)
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])
        self.doc.abortTransaction()
        with self.subTest(oracle="pending_edit_remains_abortable"):
            self.assertEqual(self.source.Label, original)
        with self.subTest(oracle="aborted_edit_has_no_undo_record"):
            self.assertEqual(self.doc.UndoNames, [])

    def _accepted(self, command_name, expected_length):
        self._select(self.cosmetic_edge)
        before = self._model()
        self._run(command_name)
        self.doc.recompute()
        self.assertTrue(self._wait(self.view.isProjectionReady))
        after = self._model()
        self.assertNotEqual(after["geometry"], before["geometry"])
        for key in before:
            if key != "geometry":
                self.assertEqual(after[key], before[key])
        self.assertAlmostEqual(
            self.view.getEdgeBySelection(self.cosmetic_edge).Length, expected_length, places=8
        )
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Extend/shorten line"])
        self.doc.undo()
        self.doc.recompute()
        self.assertTrue(self._wait(self.view.isProjectionReady))
        self.assertEqual(self._model(), before)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, ["Extend/shorten line"])
        self.doc.redo()
        self.doc.recompute()
        self.assertTrue(self._wait(self.view.isProjectionReady))
        self.assertEqual(self._model(), after)
        self.assertEqual(self.doc.UndoNames, ["Extend/shorten line"])
        self.assertEqual(self.doc.RedoNames, [])

    def test_fit_all_preserves_pending_edit_control(self):
        self._preserve_pending("Std_ViewFitAll", None)

    def test_extend_cosmetic_edge_undo_redo_control(self):
        self._accepted("TechDraw_ExtensionExtendLine", 11.0)

    def test_shorten_cosmetic_edge_undo_redo_control(self):
        self._accepted("TechDraw_ExtensionShortenLine", 3.0)

    def test_projected_edge_retains_existing_transaction_policy_control(self):
        self._select(self.projected_edge)
        original = self._pending()
        before = self._model()
        self._run("TechDraw_ExtensionExtendLine")
        self.assertEqual(self._model(), before)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, ["Unrelated pending edit"])
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.source.Label, original)

    def test_extend_view_only_preserves_pending_edit(self):
        self._preserve_pending("TechDraw_ExtensionExtendLine", None)

    def test_shorten_view_only_preserves_pending_edit(self):
        self._preserve_pending("TechDraw_ExtensionShortenLine", None)
