# SPDX-License-Identifier: LGPL-2.1-or-later
"""Empty duplicate selections preserve existing document transactions."""

import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher  # noqa: F401
from PySide import QtCore, QtWidgets


class TestPartDesignDuplicateCancellationGui(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.doc_name = None
        self.retained = []
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/General")
        self.saved_settings = {
            key: (
                any(item[1] == key for item in self.settings.GetContents() or []),
                self.settings.GetBool(key, True),
            )
            for key in ("ObjectSelectionAutoDeps", "ObjectSelectionShowDeps")
        }
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("PartDesignWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("DuplicateCancellation_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.gui_doc = Gui.getDocument(self.doc_name)
        self.doc.UndoMode = 1
        self.source_body = self.doc.addObject("PartDesign::Body", "SourceBody")
        self.profile = self.source_body.newObject("Sketcher::SketchObject", "SourceProfile")
        points = [(0, 0), (20, 0), (20, 10), (0, 10)]
        for index, first in enumerate(points):
            second = points[(index + 1) % len(points)]
            self.profile.addGeometry(
                Part.LineSegment(App.Vector(*first, 0), App.Vector(*second, 0)), False
            )
        self.source = self.source_body.newObject("PartDesign::Pad", "SourcePad")
        self.source.Profile = self.profile
        self.source.Length = 7
        self.target_body = self.doc.addObject("PartDesign::Body", "TargetBody")
        self.doc.recompute()
        self.assertTrue(self.source.isValid())
        self.assertAlmostEqual(self.source.Shape.Volume, 1400)
        self.assertIn(self.profile, self.source.OutListRecursive)
        self.gui_doc.activeView().setActiveObject("pdbody", self.target_body)
        self.assertEqual(self.gui_doc.activeView().getActiveObject("pdbody"), self.target_body)
        self.doc.clearUndos()
        self.assertEqual(self.doc.FileName, "")

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            task = Gui.Control.activeTaskDialog(self.gui_doc)
            if task:
                task.reject()
                self._pump()
            if self.gui_doc.getInEdit():
                self.gui_doc.resetEdit()
            Gui.Selection.clearSelection()
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        for key, (present, value) in self.saved_settings.items():
            if present:
                self.settings.SetBool(key, value)
            else:
                self.settings.RemBool(key)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _select_source(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.source)
        selection = Gui.Selection.getSelection()
        self.assertEqual(selection, [self.source])

    def _model(self):
        return {
            "objects": tuple(sorted((obj.Name, obj.TypeId, obj.Label) for obj in self.doc.Objects)),
            "source_group": tuple(obj.Name for obj in self.source_body.Group),
            "target_group": tuple(obj.Name for obj in self.target_body.Group),
            "source_tip": self.source_body.Tip.Name if self.source_body.Tip else None,
            "target_tip": self.target_body.Tip.Name if self.target_body.Tip else None,
            "source_profile": self.source.Profile[0].Name,
            "source_volume": self.source.Shape.Volume,
            "source_valid": self.source.isValid(),
        }

    def _snapshot(self):
        return {
            "model": self._model(),
            "pending": self.doc.HasPendingTransaction,
            "booked": self.doc.getBookedTransactionID(),
            "undo": tuple(self.doc.UndoNames),
            "redo": tuple(self.doc.RedoNames),
            "selection": tuple(
                (entry.Object.Name, tuple(entry.SubElementNames))
                for entry in Gui.Selection.getSelectionEx("", 0)
            ),
        }

    def _run(self, command_name, response=None):
        window = Gui.getMainWindow()
        seen, errors = [], []
        testcase = self

        class ObjectSelectionResponder(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() != QtCore.QEvent.Show or not isinstance(watched, QtWidgets.QDialog):
                    return False
                if (
                    watched.objectName() in ("Gui::DlgObjectSelection", "Gui__DlgObjectSelection")
                    and watched.parentWidget() == window
                ):
                    testcase.retained.append(watched)
                    seen.append(watched.objectName())

                    def answer():
                        try:
                            testcase.assertIn(response, ("accept", "cancel"))
                            tree = watched.findChild(QtWidgets.QTreeWidget, "treeWidget")
                            buttons = watched.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
                            testcase.assertIsNotNone(tree)
                            testcase.assertGreater(tree.topLevelItemCount(), 0)
                            testcase.assertIsNotNone(buttons)
                            role = (
                                QtWidgets.QDialogButtonBox.Ok
                                if response == "accept"
                                else QtWidgets.QDialogButtonBox.Cancel
                            )
                            button = buttons.button(role)
                            testcase.assertIsNotNone(button)
                            testcase.retained.extend([tree, buttons, button])
                            button.click()
                        except Exception as error:
                            errors.append(repr(error))
                            watched.reject()

                    QtCore.QTimer.singleShot(0, answer)
                return False

        outputs = [
            widget
            for widget in window.findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(outputs)
        report_before = [widget.toPlainText() for widget in outputs]
        responder = ObjectSelectionResponder()
        application = QtWidgets.QApplication.instance()
        application.installEventFilter(responder)
        try:
            command = Gui.Command.get(command_name)
            self.assertIsNotNone(command)
            self.assertTrue(command.isActive())
            Gui.runCommand(command_name)
        finally:
            application.removeEventFilter(responder)
        self._pump()
        self.assertEqual(errors, [])
        self.assertEqual(len(seen), int(response is not None))
        for widget, prior in zip(outputs, report_before):
            text = widget.toPlainText()
            added = text[len(prior) :] if text.startswith(prior) else text
            for error in ("Traceback", "Access violation", "<Exception>"):
                self.assertNotIn(error, added)

    def _unchanged(self, command, response=None):
        before = self._snapshot()
        self._run(command, response)
        after = self._snapshot()
        for key in before:
            with self.subTest(unchanged=key):
                self.assertEqual(after[key], before[key])

    def _pending_case(self, command, response=None, select=True):
        if select:
            self._select_source()
        else:
            Gui.Selection.clearSelection()
        original = self.source.Label
        self.doc.openTransaction("Unrelated pending edit")
        self.source.Label = "Uncommitted source label"
        self.assertTrue(self.doc.HasPendingTransaction)
        self._unchanged(command, response)
        self.doc.abortTransaction()
        with self.subTest(oracle="original_transaction_still_abortable"):
            self.assertEqual(self.source.Label, original)
        with self.subTest(oracle="aborted_edit_not_committed"):
            self.assertEqual(self.doc.UndoNames, [])

    def test_partdesign_empty_selection_preserves_unrelated_pending_edit(self):
        self._pending_case("PartDesign_DuplicateSelection", select=False)

    def test_standard_cancel_pending_transaction_control(self):
        self._pending_case("Std_DuplicateSelection", "cancel")

    def test_fit_all_pending_transaction_control(self):
        self._pending_case("Std_ViewFitAll")

    def test_partdesign_cancel_fresh_document_control(self):
        self._select_source()
        self._unchanged("PartDesign_DuplicateSelection", "cancel")

    def test_partdesign_cancel_preserves_existing_redo_history(self):
        self.doc.openTransaction("Existing redo edit")
        self.source.Label = "Undone source label"
        self.doc.commitTransaction()
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.doc.RedoNames, ["Existing redo edit"])
        self._select_source()
        self._unchanged("PartDesign_DuplicateSelection", "cancel")

    def test_valid_partdesign_duplicate_and_undo_control(self):
        self._select_source()
        before = self._model()
        original_names = {obj.Name for obj in self.doc.Objects}
        self._run("PartDesign_DuplicateSelection", "accept")
        self.doc.recompute()
        copies = [
            obj
            for obj in self.doc.Objects
            if obj.Name not in original_names and obj.isDerivedFrom("PartDesign::Pad")
        ]
        self.assertEqual(len(copies), 1)
        duplicate = copies[0]
        duplicate_name = duplicate.Name
        self.assertTrue(duplicate.isValid())
        self.assertAlmostEqual(duplicate.Shape.Volume, 1400)
        self.assertIsNotNone(duplicate.Profile)
        self.assertEqual(duplicate.Profile[0].GeometryCount, 4)
        self.assertIn(duplicate, self.target_body.Group)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertTrue(self.doc.UndoNames)
        self.doc.undo()
        self.doc.recompute()
        with self.subTest(oracle="one_undo_removes_duplicate"):
            self.assertIsNone(self.doc.getObject(duplicate_name))
        with self.subTest(oracle="one_undo_restores_original_model"):
            self.assertEqual(self._model(), before)
