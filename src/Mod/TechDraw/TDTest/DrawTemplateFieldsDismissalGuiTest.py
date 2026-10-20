# SPDX-License-Identifier: LGPL-2.1-or-later
"""Template field dialogs keep each page's edited field identities."""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class DrawTemplateFieldsDismissalGuiTest(unittest.TestCase):
    def setUp(self):
        active = App.activeDocument()
        self.previous_document = active.Name if active else None
        wb = Gui.activeWorkbench()
        self.previous_workbench = wb.name() if wb else None
        self.doc_name = None
        self.retained = []
        self.temporary = tempfile.TemporaryDirectory(prefix="asto-template-page-")
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        from TechDrawTools.TaskFillTemplateFields import TaskFillTemplateFields

        self.task_type = TaskFillTemplateFields
        self.doc = App.newDocument("TemplatePages_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.CreatedBy = "Page author"
        self.doc.UndoMode = 1
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = Part.makeBox(10, 10, 10)
        self.pages = []
        self.original_texts = []
        for index, key in enumerate(("drawing_title", "author_name")):
            path = Path(self.temporary.name) / (key + ".svg")
            path.write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
                'width="100mm" height="80mm" viewBox="0 0 100 80">'
                '<text x="5" y="10" freecad:editable="' + key + '">'
                "<tspan>Original " + key + "</tspan></text></svg>\n",
                encoding="utf-8",
            )
            page = self.doc.addObject("TechDraw::DrawPage", "Page" + str(index))
            page.Label = "Page label " + str(index)
            template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template" + str(index))
            template.Template = str(path)
            page.Template = template
            view = self.doc.addObject("TechDraw::DrawViewPart", "View" + str(index))
            view.Source = [source]
            page.addView(view)
            self.pages.append(page)
        self.doc.recompute()
        for page, key in zip(self.pages, ("drawing_title", "author_name")):
            self.assertEqual(list(page.Template.EditableTexts), [key])
            self.assertEqual(len(page.Views), 1)
            self.assertTrue(page.Views[0].isValid())
            self.original_texts.append(dict(page.Template.EditableTexts))
        self.doc.clearUndos()

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _case(self, first_action):
        application = QtWidgets.QApplication.instance()
        seen, errors = [], []
        testcase = self

        class RespondToOwnedPageDialog(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() != QtCore.QEvent.Show or not isinstance(watched, QtWidgets.QDialog):
                    return False
                index = next(
                    (
                        i
                        for i, page in enumerate(testcase.pages)
                        if watched.windowTitle().endswith(page.Label)
                    ),
                    None,
                )
                if index is None:
                    return False
                testcase.retained.append(watched)
                seen.append(index)

                def respond():
                    try:
                        buttons = watched.findChild(QtWidgets.QDialogButtonBox)
                        testcase.assertIsNotNone(buttons)
                        testcase.retained.append(buttons)
                        if index == 0 and first_action == "escape":
                            QtTest.QTest.keyClick(watched, QtCore.Qt.Key_Escape)
                        elif index == 0 and first_action == "window_close":
                            watched.close()
                        elif index == 0 and first_action == "cancel_button":
                            cancel = buttons.button(QtWidgets.QDialogButtonBox.Cancel)
                            testcase.assertIsNotNone(cancel)
                            testcase.retained.append(cancel)
                            cancel.click()
                        else:
                            checkbox = watched.findChild(
                                QtWidgets.QCheckBox,
                                "drawing_title" if index == 0 else "author_name",
                            )
                            testcase.assertIsNotNone(checkbox)
                            testcase.assertTrue(checkbox.isChecked())
                            editors = watched.findChildren(QtWidgets.QLineEdit)
                            testcase.assertEqual(len(editors), 1)
                            testcase.retained.extend([checkbox, *editors])
                            editors[0].setText("Edited page " + str(index))
                            ok = buttons.button(QtWidgets.QDialogButtonBox.Ok)
                            testcase.assertIsNotNone(ok)
                            testcase.retained.append(ok)
                            ok.click()
                    except Exception as error:
                        errors.append(repr(error))
                        watched.reject()

                QtCore.QTimer.singleShot(0, respond)
                return False

        responder = RespondToOwnedPageDialog()
        application.installEventFilter(responder)
        try:
            task = self.task_type()
            self.retained.append(task)
        finally:
            application.removeEventFilter(responder)
        self.assertEqual(errors, [])
        self.assertEqual(seen, [0, 1])
        expected_first = (
            {"drawing_title": "Edited page 0"}
            if first_action == "accept"
            else self.original_texts[0]
        )
        with self.subTest(page="first"):
            self.assertEqual(dict(self.pages[0].Template.EditableTexts), expected_first)
        with self.subTest(page="second"):
            self.assertEqual(
                dict(self.pages[1].Template.EditableTexts), {"author_name": "Edited page 1"}
            )

    def test_escape_first_page_does_not_reuse_field_keys(self):
        self._case("escape")

    def test_window_close_first_page_does_not_reuse_field_keys(self):
        self._case("window_close")

    def test_cancel_button_first_page_control(self):
        self._case("cancel_button")

    def test_accept_both_pages_control(self):
        self._case("accept")
