# SPDX-License-Identifier: LGPL-2.1-or-later
"""Template field commands skip native pages without attached templates."""

import copy
import csv
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    from PySide import QtCore, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestTemplateFieldsMissingTemplateGui(unittest.TestCase):
    def setUp(self):
        self.assertIsNone(Gui.Control.activeTaskDialog(), "An idle task panel is required")
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = tuple(
            (item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx("*", 0)
        )
        self.doc_name = None
        self.temporary_directory = None
        self.pages = []
        self.views = []
        self.retained = []
        self.addCleanup(self._cleanup)
        self._owned_temporary_directory()
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.command = Gui.Command.get("TechDraw_FillTemplateFields")
        self.assertIsNotNone(self.command)
        self.csv_path = Path(App.getResourceDir()) / "Mod/TechDraw/CSVdata/FillTemplateFields.csv"
        self.assertTrue(self.csv_path.is_file())
        with self.csv_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(
                reader.fieldnames,
                [
                    "CreatedByChkLst",
                    "ScaleChkLst",
                    "LabelChkLst",
                    "CommentChkLst",
                    "CompanyChkLst",
                    "LicenseChkLst",
                    "CreatedDateChkLst",
                    "LastModifiedDateChkLst",
                ],
            )
            self.assertIn("fc-title", [row["LabelChkLst"] for row in reader])
        sibling_template = Path(__file__).with_name("TestTemplate.svg")
        installed_template = Path(App.getHomePath()) / "Mod/TechDraw/TDTest/TestTemplate.svg"
        resource = sibling_template if sibling_template.is_file() else installed_template
        self.assertTrue(resource.is_file())
        self.template_path = self.temporary_directory / "OrdinaryTemplate.svg"
        self.assertFalse(self.template_path.exists())
        shutil.copyfile(resource, self.template_path)
        self.assertEqual(self.template_path.read_bytes(), resource.read_bytes())
        self.doc = App.newDocument("TemplateMissing_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.Label = "Owned template document"
        self.doc.CreatedBy = "Template author"
        self.doc.UndoMode = 1
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 20, 30, 10
        self.doc.recompute()
        self.assertTrue(self.source.Shape.isValid())
        self.assertAlmostEqual(self.source.Shape.Volume, 6000)

    def _owned_temporary_directory(self):
        parent = Path(tempfile.gettempdir()).resolve()
        if os.environ.get("ASTO_AUDIT_CASE") or os.environ.get("ASTO_AUDIT_LABEL"):
            label = os.environ.get("ASTO_AUDIT_LABEL", "")
            self.assertTrue(label)
            self.assertNotIn("/", label)
            self.assertNotIn("\\", label)
            profile = Path(os.environ["FREECAD_USER_HOME"]).resolve()
            output = profile.parent
            self.assertEqual(profile.name, label + "-profile")
            self.assertEqual(output.name, "issue-audit-20261019")
            self.assertEqual(output.parent.name, ".codex-test-bin")
            workspace = output.parent.parent
            self.assertTrue((workspace / ".git").exists())
            self.assertTrue(Path(__file__).resolve().is_relative_to(workspace))
            self.assertEqual(
                Path(os.environ["ASTO_AUDIT_SOURCE"]).resolve(), Path(__file__).resolve()
            )
            self.assertEqual(Path(App.ConfigGet("UserParameter")).resolve(), profile / "user.cfg")
            self.assertTrue(Path(App.getUserAppDataDir()).resolve().is_relative_to(profile))
            parent = (profile / "temp").resolve()
            self.assertEqual(Path(os.environ["TEMP"]).resolve(), parent)
        self.temporary_parent = parent
        self.assertTrue(parent.is_dir())
        self.temporary_directory = Path(
            tempfile.mkdtemp(prefix="template-missing-owned-", dir=parent)
        ).resolve()
        self.assertEqual(self.temporary_directory.parent, parent)

    @staticmethod
    def _pump(milliseconds=20):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    @staticmethod
    def _field_title(page):
        # The production dialog marks this literal with NOOP; it does not call translate.
        return (
            QtCore.QT_TRANSLATE_NOOP("TechDraw_FillTemplateFields", "Fill Template Fields In ")
            + page.Label
        )

    @staticmethod
    def _missing_views_warning(page):
        # Match the production warning's exact context, casing and NOOP behavior.
        return (
            QtCore.QT_TRANSLATE_NOOP(
                "Techdraw_FillTemplateFields", "View or projection group missing"
            ),
            QtCore.QT_TRANSLATE_NOOP(
                "Techdraw_FillTemplateFields",
                "There must be a view or projection group to"
                " establish data for the scale field in " + page.Label,
            ),
        )

    def _cleanup(self):
        try:
            if self.doc_name in App.listDocuments():
                App.setActiveDocument(self.doc_name)
                titles = {self._field_title(page) for page in self.pages}
                for widget in QtWidgets.QApplication.topLevelWidgets():
                    if isinstance(widget, QtWidgets.QDialog) and widget.windowTitle() in titles:
                        if widget.isVisible():
                            widget.reject()
                owner = Gui.getDocument(self.doc_name)
                dialog = Gui.Control.activeTaskDialog(owner)
                if dialog is not None:
                    self.assertEqual(dialog.getDocumentName(), self.doc_name)
                    dialog.reject()
                    self._pump()
                if owner.getInEdit():
                    owner.resetEdit()
                document = App.getDocument(self.doc_name)
                if document.HasPendingTransaction:
                    document.abortTransaction()
                Gui.Selection.clearSelection()
                App.closeDocument(self.doc_name)
            self.pages = []
            self.views = []
            self.retained = []
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            QtWidgets.QApplication.processEvents()
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
            if self.temporary_directory is not None:
                self.assertNotIn(self.doc_name, App.listDocuments())
                owned = self.temporary_directory.resolve()
                self.assertEqual(owned.parent, self.temporary_parent)
                self.assertTrue(owned.name.startswith("template-missing-owned-"))
                self.assertTrue(owned.is_relative_to(self.temporary_parent))
                self.assertFalse(owned.is_symlink())
                self.assertFalse(self.temporary_directory.is_symlink())
                for path in owned.rglob("*"):
                    self.assertTrue(path.resolve().is_relative_to(owned))
                    self.assertFalse(path.is_symlink())
                shutil.rmtree(owned)
                self.assertFalse(owned.exists())
                self.temporary_directory = None

    def _page(self, name, template=True, view=True):
        page = self.doc.addObject("TechDraw::DrawPage", name)
        page.Label = "Owned " + name
        self.pages.append(page)
        if template:
            attached = self.doc.addObject("TechDraw::DrawSVGTemplate", name + "Template")
            attached.Template = str(self.template_path)
            page.Template = attached
            self.assertIn("FC-Title", attached.EditableTexts)
        else:
            self.assertIsNone(page.Template)
        if view:
            drawing = self.doc.addObject("TechDraw::DrawViewPart", name + "View")
            drawing.Source = [self.source]
            drawing.Direction = App.Vector(0, 0, 1)
            drawing.XDirection = App.Vector(1, 0, 0)
            drawing.ScaleType = "Custom"
            drawing.Scale = 1
            page.addView(drawing)
            self.views.append(drawing)
        return page

    def _settle(self):
        self.doc.recompute()
        deadline = time.monotonic() + 20
        for view in self.views:
            while not view.getVisibleEdges() or "Up-to-date" not in view.State:
                self.assertLess(time.monotonic(), deadline, "Ordinary box projection must settle")
                self._pump()
        self.doc.clearUndos()
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), 0)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])
        self.assertEqual(App.activeDocument().Name, self.doc_name)
        self.assertIsNone(Gui.Control.activeTaskDialog())

    def _model(self):
        return {
            "objects": tuple((obj.Name, obj.TypeId, obj.Label) for obj in self.doc.Objects),
            "box_dimensions": (
                self.source.Length.Value,
                self.source.Width.Value,
                self.source.Height.Value,
            ),
            "box_placement": (
                tuple(self.source.Placement.Base),
                tuple(self.source.Placement.Rotation.Q),
            ),
            "box_volume": self.source.Shape.Volume,
            "pages": tuple(
                {
                    "name": page.Name,
                    "template": page.Template.Name if page.Template is not None else None,
                    "template_file": page.Template.Template if page.Template is not None else None,
                    "views": tuple(view.Name for view in page.Views),
                    "scale": page.Scale,
                    "projection": page.ProjectionType,
                    "keep_updated": page.KeepUpdated,
                    "texts": (
                        tuple(sorted(page.Template.EditableTexts.items()))
                        if page.Template is not None
                        else None
                    ),
                }
                for page in self.pages
            ),
            "views": tuple(
                (
                    view.Name,
                    tuple(obj.Name for obj in view.Source),
                    view.Scale,
                    view.ScaleType,
                    view.X.Value,
                    view.Y.Value,
                    tuple(view.Direction),
                    tuple(view.XDirection),
                )
                for view in self.views
            ),
        }

    def _report_snapshot(self):
        reports = [
            widget
            for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(reports)
        return [(widget, widget.toPlainText()) for widget in reports]

    def _assert_no_report_error(self, previous):
        for widget, before in previous:
            current = widget.toPlainText()
            delta = current[len(before) :] if current.startswith(before) else current
            for marker in ("traceback", "attributeerror", "nonetype", "<exception>"):
                self.assertNotIn(marker, delta.lower())

    def _admission(self, expected):
        before = self._model()
        report = self._report_snapshot()
        self.assertEqual(self.command.isActive(), expected)
        self._pump()
        self._assert_no_report_error(report)
        self.assertEqual(self._model(), before)
        self.assertEqual(self.doc.getBookedTransactionID(), 0)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(self.doc.RedoNames, [])

    def _invoke(self, page, accept=False, warning_page=None):
        expected_title = self._field_title(page)
        owned_titles = {self._field_title(item) for item in self.pages}
        warning_title = self._missing_views_warning(page)[0]
        warning_text = (
            self._missing_views_warning(warning_page)[1] if warning_page is not None else None
        )
        seen, warnings, errors = [], [], []
        shown = set()
        testcase = self

        class RespondToOwnedDialog(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() != QtCore.QEvent.Show or not isinstance(watched, QtWidgets.QDialog):
                    return False
                if id(watched) in shown:
                    return False
                if isinstance(watched, QtWidgets.QMessageBox):
                    if watched.windowTitle() != warning_title or not any(
                        watched.text().endswith(item.Label) for item in testcase.pages
                    ):
                        return False
                    shown.add(id(watched))
                    testcase.retained.append(watched)
                    warnings.append((watched.windowTitle(), watched.text()))

                    def answer_warning():
                        try:
                            button = watched.button(QtWidgets.QMessageBox.Ok)
                            testcase.assertIsNotNone(button)
                            testcase.retained.append(button)
                            button.click()
                        except Exception as error:
                            errors.append(repr(error))
                            watched.reject()

                    QtCore.QTimer.singleShot(0, answer_warning)
                    return False
                if watched.windowTitle() not in owned_titles:
                    return False
                shown.add(id(watched))
                testcase.retained.append(watched)
                seen.append(watched.windowTitle())

                def answer_fields():
                    try:
                        testcase.assertEqual(App.activeDocument().Name, testcase.doc_name)
                        testcase.assertIsNone(Gui.Control.activeTaskDialog())
                        buttons = watched.findChild(QtWidgets.QDialogButtonBox)
                        testcase.assertIsNotNone(buttons)
                        testcase.retained.append(buttons)
                        if accept and watched.windowTitle() == expected_title:
                            chosen = watched.findChild(QtWidgets.QCheckBox, "FC-Title")
                            testcase.assertIsNotNone(chosen)
                            testcase.assertTrue(chosen.isChecked())
                            testcase.retained.append(chosen)
                            for checkbox in watched.findChildren(QtWidgets.QCheckBox):
                                if checkbox.objectName() and checkbox is not chosen:
                                    if checkbox.isChecked():
                                        checkbox.click()
                            layout = watched.layout()
                            index = layout.indexOf(chosen)
                            testcase.assertGreaterEqual(index, 0)
                            row, _column, _row_span, _column_span = layout.getItemPosition(index)
                            editor = layout.itemAtPosition(row, 3).widget()
                            testcase.assertIsInstance(editor, QtWidgets.QLineEdit)
                            testcase.retained.append(editor)
                            editor.setFocus()
                            editor.selectAll()
                            QtTest.QTest.keyClicks(editor, "Template field updated")
                            testcase.assertEqual(editor.text(), "Template field updated")
                            button = buttons.button(QtWidgets.QDialogButtonBox.Ok)
                        else:
                            button = buttons.button(QtWidgets.QDialogButtonBox.Cancel)
                        testcase.assertIsNotNone(button)
                        testcase.retained.append(button)
                        button.click()
                    except Exception as error:
                        errors.append(repr(error))
                        watched.reject()

                QtCore.QTimer.singleShot(0, answer_fields)
                return False

        application = QtWidgets.QApplication.instance()
        responder = RespondToOwnedDialog()
        report = self._report_snapshot()
        application.installEventFilter(responder)
        try:
            Gui.runCommand("TechDraw_FillTemplateFields")
        finally:
            application.removeEventFilter(responder)
        self._pump()
        self.assertEqual(errors, [])
        self._assert_no_report_error(report)
        self.assertEqual(seen, [] if warning_page is not None else [expected_title])
        self.assertEqual(
            warnings, [(warning_title, warning_text)] if warning_page is not None else []
        )
        self.assertEqual(App.activeDocument().Name, self.doc_name)
        self.assertIsNone(Gui.Control.activeTaskDialog())
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), 0)

    def _cancel_case(self, missing_view=None):
        if missing_view is not None:
            self._page("MissingTemplate", template=False, view=missing_view)
        page = self._page("UsablePage")
        self._settle()
        before = self._model()
        self._invoke(page)
        self._admission(True)
        self.assertEqual(self._model(), before)
        self.assertEqual(self.doc.UndoNames, [])

    def _accept_undo_case(self, missing_view=None):
        if missing_view is not None:
            self._page("MissingTemplate", template=False, view=missing_view)
        page = self._page("UsablePage")
        self._settle()
        before = self._model()
        original_texts = dict(page.Template.EditableTexts)
        self._invoke(page, accept=True)
        expected = dict(original_texts)
        expected["FC-Title"] = "Template field updated"
        self.assertEqual(dict(page.Template.EditableTexts), expected)
        expected_model = copy.deepcopy(before)
        for item in expected_model["pages"]:
            if item["name"] == page.Name:
                item["texts"] = tuple(sorted(expected.items()))
        self.assertEqual(self._model(), expected_model)
        self.assertEqual(len(self.doc.UndoNames), 1)
        self.assertEqual(self.doc.RedoNames, [])
        self.doc.undo()
        self.doc.recompute()
        self._pump()
        self.assertEqual(self._model(), before)
        self.assertEqual(self.doc.UndoNames, [])
        self.assertEqual(len(self.doc.RedoNames), 1)
        self.doc.redo()
        self.doc.recompute()
        self._pump()
        self.assertEqual(dict(page.Template.EditableTexts), expected)
        self.assertEqual(self._model(), expected_model)
        self.assertEqual(len(self.doc.UndoNames), 1)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_document_without_pages_disabled_control(self):
        self._settle()
        self._admission(False)

    def test_valid_template_cancel_control(self):
        self._cancel_case()

    def test_valid_template_accept_undo_redo_control(self):
        self._accept_undo_case()

    def test_templated_zero_views_warning_and_stop_control(self):
        first = self._page("TemplatedNoViews", view=False)
        self._settle()
        self._admission(False)
        second = self._page("UsablePage")
        self._settle()
        self._admission(True)
        before = self._model()
        self._invoke(second, warning_page=first)
        self.assertEqual(self._model(), before)
        self.assertEqual(self.doc.UndoNames, [])

    def test_untemplated_page_disabled_without_errors(self):
        self._page("MissingTemplate", template=False, view=False)
        self._settle()
        self._admission(False)

    def test_untemplated_first_page_does_not_disable_later_template(self):
        self._page("MissingTemplate", template=False, view=False)
        self._page("UsablePage")
        self._settle()
        self._admission(True)

    def test_untemplated_first_page_skipped_for_native_cancel(self):
        self._cancel_case(missing_view=False)

    def test_untemplated_first_page_skipped_for_native_accept_and_undo(self):
        self._accept_undo_case(missing_view=False)
