# SPDX-License-Identifier: LGPL-2.1-or-later
"""Page choosers distinguish displayed labels from internal object names."""

from pathlib import Path
import time
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


@unittest.skipUnless("TechDrawWorkbench" in Gui.listWorkbenches(), "TechDraw is unavailable")
class DrawMoveViewPageChooserGuiTest(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/Document")
        self.had_duplicate_labels = any(
            item[1] == "DuplicateLabels" for item in self.settings.GetContents() or []
        )
        self.old_duplicate_labels = self.settings.GetBool("DuplicateLabels", False)
        self.doc_name = None
        self.task = None
        self.task_finished = False
        self.task_shown = False
        self.choosers = []
        self.retained = []
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog())
        self.settings.SetBool("DuplicateLabels", True)
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("PageChooser_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.gui_doc = Gui.getDocument(self.doc_name)
        template_path = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(template_path.is_file())
        self.pages = []
        for name in ("FirstPage", "SecondPage"):
            page = self.doc.addObject("TechDraw::DrawPage", name)
            template = self.doc.addObject("TechDraw::DrawSVGTemplate", name + "Template")
            template.Template = str(template_path)
            page.Template = template
            self.pages.append(page)
        self.view = self.doc.addObject("TechDraw::DrawViewAnnotation", "ChooserAnnotation")
        self.view.Text = ["Page chooser marker"]
        self.pages[1].addView(self.view)
        self.doc.recompute()
        self.assertIn(self.view, self.pages[1].Views)
        self.assertNotIn(self.view, self.pages[0].Views)
        self.doc.clearUndos()

    @staticmethod
    def _pump(milliseconds=30):
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
        if self.doc_name in App.listDocuments():
            App.setActiveDocument(self.doc_name)
            if self.task is not None:
                if not self.task_finished:
                    self.task.reject()
                if self.task_shown:
                    Gui.Control.closeDialog()
                    self.task_shown = False
                elif self.task.form is not None:
                    self.task.form.deleteLater()
            for chooser in self.choosers:
                chooser.close()
                chooser.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.had_duplicate_labels:
            self.settings.SetBool("DuplicateLabels", self.old_duplicate_labels)
        else:
            self.settings.RemBool("DuplicateLabels")
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _set_labels(self, duplicate=True):
        for index, page in enumerate(self.pages):
            page.Label = "Shared drawing" if duplicate else ("Drawing " + str(index + 1))
        if duplicate:
            self.assertEqual(self.pages[0].Label, self.pages[1].Label)
        self.assertNotEqual(self.pages[0].Name, self.pages[1].Name)
        for page in self.pages:
            self.assertNotEqual(page.Label, page.Name)

    def _show_task(self, share=False):
        if share:
            from TechDrawTools.TaskShareView import TaskShareView

            self.task = TaskShareView()
        else:
            from TechDrawTools.TaskMoveView import TaskMoveView

            self.task = TaskMoveView()
        self.task.setValues(self.view.Name, self.pages[1].Name, self.pages[0].Name)
        Gui.Control.showDialog(self.task)
        self.task_shown = True
        self.assertTrue(self._wait(lambda: self.task.form.isVisible()))
        self.assertEqual(App.activeDocument(), self.doc)
        self.retained.append(self.task.form)

    def _choose_page(self, source, chosen):
        application = QtWidgets.QApplication.instance()
        previous_modals = [
            widget
            for widget in application.topLevelWidgets()
            if isinstance(widget, QtWidgets.QDialog)
        ]
        self.retained.extend(previous_modals)
        self.assertIsNone(application.activeModalWidget())
        state = {"dialog": None, "rows": None, "errors": [], "expired": False, "picking": True}
        testcase = self

        def choose(dialog):
            if not state["picking"]:
                return
            try:
                listing = dialog.findChild(QtWidgets.QListWidget, "lwPages")
                buttons = dialog.findChild(QtWidgets.QDialogButtonBox, "bbButtons")
                testcase.assertIsNotNone(listing)
                testcase.assertIsNotNone(buttons)
                if not listing.viewport().isVisible():
                    QtCore.QTimer.singleShot(10, lambda: choose(dialog))
                    return
                testcase.assertIn(
                    dialog.objectName(),
                    ("TechDrawGui::DlgPageChooser", "TechDrawGui__DlgPageChooser"),
                )
                items = [listing.item(index) for index in range(listing.count())]
                state["rows"] = [(item.data(QtCore.Qt.UserRole), item.text()) for item in items]
                testcase.assertEqual(
                    set(name for name, text in state["rows"]),
                    {page.Name for page in testcase.pages},
                )
                selected = [item for item in items if item.data(QtCore.Qt.UserRole) == chosen.Name]
                testcase.assertEqual(len(selected), 1)
                rectangle = listing.visualItemRect(selected[0])
                testcase.assertTrue(rectangle.isValid())
                testcase.assertTrue(listing.viewport().rect().contains(rectangle.center()))
                ok = buttons.button(QtWidgets.QDialogButtonBox.Ok)
                testcase.assertIsNotNone(ok)
                testcase.retained.extend([dialog, listing, buttons, ok, *items])
                QtTest.QTest.mouseClick(
                    listing.viewport(),
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.NoModifier,
                    rectangle.center(),
                )
                testcase.assertEqual(listing.selectedItems(), selected)
                QtTest.QTest.mouseClick(ok, QtCore.Qt.LeftButton)
            except Exception as error:
                state["errors"].append(repr(error))
                dialog.reject()

        class WatchChooser(QtCore.QObject):
            def eventFilter(self, watched, event):
                if (
                    state["picking"]
                    and state["dialog"] is None
                    and event.type() == QtCore.QEvent.Show
                    and isinstance(watched, QtWidgets.QDialog)
                    and watched not in previous_modals
                    and watched.findChild(QtWidgets.QListWidget, "lwPages") is not None
                    and watched.findChild(QtWidgets.QDialogButtonBox, "bbButtons") is not None
                    and testcase.task.dialogOpen
                ):
                    state["dialog"] = watched
                    testcase.choosers.append(watched)
                    QtCore.QTimer.singleShot(0, lambda: choose(watched))
                return False

        watcher = WatchChooser()
        deadline = QtCore.QTimer()
        deadline.setSingleShot(True)

        def cancel_owned_timeout():
            state["expired"] = True
            dialog = state["dialog"]
            if dialog is not None:
                dialog.reject()
                return
            modal = application.activeModalWidget()
            if (
                isinstance(modal, QtWidgets.QDialog)
                and modal not in previous_modals
                and modal.findChild(QtWidgets.QListWidget, "lwPages") is not None
                and modal.findChild(QtWidgets.QDialogButtonBox, "bbButtons") is not None
                and self.task.dialogOpen
            ):
                self.choosers.append(modal)
                modal.reject()

        deadline.timeout.connect(cancel_owned_timeout)
        application.installEventFilter(watcher)
        deadline.start(3000)
        try:
            button = self.task.form.pbFromPage if source else self.task.form.pbToPage
            button.click()
        finally:
            state["picking"] = False
            deadline.stop()
            application.removeEventFilter(watcher)
        self.assertFalse(state["expired"], "The actual owned chooser must complete")
        self.assertEqual(state["errors"], [])
        self.assertIsNotNone(state["dialog"])
        self.assertIsNotNone(state["rows"])
        self.assertFalse(self.task.dialogOpen)
        self.assertEqual(App.activeDocument(), self.doc)
        if source:
            self.assertEqual(self.task.fromPageName, chosen.Name)
            self.assertEqual(self.task.form.leFromPage.text(), chosen.Name)
        else:
            self.assertEqual(self.task.toPageName, chosen.Name)
            self.assertEqual(self.task.form.leToPage.text(), chosen.Name)
        return dict(state["rows"])

    def _assert_display(self, rows):
        for page in self.pages:
            with self.subTest(page=page.Name):
                self.assertEqual(rows[page.Name], page.Label + " / " + page.Name)

    def _accept_and_check(self, share):
        self.assertTrue(self.task.accept())
        self.task_finished = True
        Gui.Control.closeDialog()
        self.task_shown = False
        self.doc.recompute()
        self.assertIn(self.view, self.pages[0].Views)
        if share:
            self.assertIn(self.view, self.pages[1].Views)
        else:
            self.assertNotIn(self.view, self.pages[1].Views)

    def test_move_source_unique_labels_show_internal_names(self):
        self._set_labels(duplicate=False)
        self._show_task()
        rows = self._choose_page(source=True, chosen=self.pages[1])
        self._assert_display(rows)

    def test_move_source_duplicate_labels_remain_distinguishable(self):
        self._set_labels()
        self._show_task()
        rows = self._choose_page(source=True, chosen=self.pages[1])
        self._assert_display(rows)
        with self.subTest(oracle="distinct_displayed_page_names"):
            self.assertEqual(len(set(rows.values())), 2)

    def test_move_source_choice_uses_internal_name(self):
        self._set_labels()
        self._show_task()
        self._choose_page(source=True, chosen=self.pages[1])
        self._accept_and_check(share=False)

    def test_move_destination_choice_displays_and_uses_internal_name(self):
        self._set_labels()
        self._show_task()
        rows = self._choose_page(source=False, chosen=self.pages[0])
        self._assert_display(rows)
        self._accept_and_check(share=False)

    def test_share_source_choice_displays_and_uses_internal_name(self):
        self._set_labels()
        self._show_task(share=True)
        rows = self._choose_page(source=True, chosen=self.pages[1])
        self._assert_display(rows)
        self._accept_and_check(share=True)

    def test_share_destination_choice_displays_and_uses_internal_name(self):
        self._set_labels()
        self._show_task(share=True)
        rows = self._choose_page(source=False, chosen=self.pages[0])
        self._assert_display(rows)
        self._accept_and_check(share=True)
