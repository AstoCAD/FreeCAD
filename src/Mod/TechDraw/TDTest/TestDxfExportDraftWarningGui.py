# SPDX-License-Identifier: LGPL-2.1-or-later
"""DXF export warns about views it cannot export.

The DXF exporter skips BIM and Draft views. The toolbar command only warned
about BIM views and the page's context-menu "Export DXF" did not warn at all
(https://github.com/FreeCAD/FreeCAD/issues/20960). Both paths now share one
check. No file is written: every save dialog is cancelled.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    try:
        import shiboken6 as shiboken
    except ImportError:
        import shiboken2 as shiboken


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")
DRAFT_TEXT = "Page contains a Draft view which will not be exported. Continue?"
BIM_TEXT = "Page contains a BIM view which will not be exported. Continue?"


def _translated(text):
    return QtCore.QCoreApplication.translate("QObject", text)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestDxfExportDraftWarningGui(unittest.TestCase):
    def setUp(self):
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        self.app = QtWidgets.QApplication.instance()
        self.assertIsNone(self.app.activeModalWidget())
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.dialog_settings = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        self.previous_native = self._parameter(
            self.dialog_settings, "Boolean", "DontUseNativeDialog"
        )
        self.general_settings = App.ParamGet("User parameter:BaseApp/Preferences/General")
        self.previous_save_path = self._parameter(
            self.general_settings, "String", "FileOpenSavePath"
        )
        self.doc = None
        self.addCleanup(self._cleanup)
        # Qt's own dialog can be driven and cancelled from the test.
        self.dialog_settings.SetBool("DontUseNativeDialog", True)
        Gui.activateWorkbench("TechDrawWorkbench")

        self.doc = App.newDocument("TDDxfDraftWarning")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.annotation = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        self.annotation.Text = ["DXF export"]
        self.page.addView(self.annotation)
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)

        before = {shiboken.getCppPointer(w)[0] for w in self._page_views()}
        self.page.ViewObject.show()
        self.assertTrue(self._wait(lambda: self._new_page_view(before) is not None))
        self.view = self._new_page_view(before)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.page.Name)
        self.command = Gui.Command.get("TechDraw_ExportPageDXF")
        self.assertTrue(self._wait(self.command.isActive))

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
            self._pump(100)
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        present, value = self.previous_native
        if present:
            self.dialog_settings.SetBool("DontUseNativeDialog", value)
        else:
            self.dialog_settings.RemBool("DontUseNativeDialog")
        present, value = self.previous_save_path
        if present:
            self.general_settings.SetString("FileOpenSavePath", value)
        else:
            self.general_settings.RemString("FileOpenSavePath")

    @staticmethod
    def _parameter(group, kind, name):
        found = [
            value
            for entry_kind, key, value in group.GetContents() or []
            if entry_kind == kind and key == name
        ]
        return bool(found), found[0] if found else None

    @staticmethod
    def _pump(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                return False
            self._pump()
        return True

    @staticmethod
    def _page_views():
        return [
            widget
            for widget in QtWidgets.QApplication.allWidgets()
            if widget.metaObject().className() == "TechDrawGui::MDIViewPage"
        ]

    def _new_page_view(self, before):
        for widget in self._page_views():
            if shiboken.getCppPointer(widget)[0] not in before:
                return widget
        return None

    def _context_menu_action(self):
        text = QtCore.QCoreApplication.translate("TechDrawGui::MDIViewPage", "Export DXF")
        for child in self.view.children():
            if child.metaObject().className() == "QAction" and child.text() == text:
                return child
        self.fail("The page view has no Export DXF action")

    def _run(self, trigger, answer):
        """Run an export and record the dialogs shown.

        answer is the button used on the warning; every save dialog is
        cancelled so no file is written.
        """
        shown = []
        testcase = self

        class Dialogs(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() != QtCore.QEvent.Show:
                    return False
                if isinstance(watched, QtWidgets.QMessageBox):
                    shown.append(("message", watched.text()))
                    button = watched.button(answer)
                    QtCore.QTimer.singleShot(
                        0, button.click if button is not None else watched.reject
                    )
                elif isinstance(watched, QtWidgets.QFileDialog):
                    shown.append(("file", watched.windowTitle()))
                    QtCore.QTimer.singleShot(0, watched.reject)
                return False

        def timeout():
            modal = testcase.app.activeModalWidget()
            if isinstance(modal, QtWidgets.QDialog):
                shown.append(("timeout", modal.metaObject().className()))
                modal.reject()

        observer = Dialogs()
        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(timeout)
        self.app.installEventFilter(observer)
        watchdog.start(10000)
        try:
            trigger()
            self._pump(100)
        finally:
            watchdog.stop()
            self.app.removeEventFilter(observer)
        self.assertIsNone(self.app.activeModalWidget())
        return [kind if kind != "message" else (kind, text) for kind, text in shown]

    def _toolbar(self):
        self.command.getAction()[0].trigger()

    def _context_menu(self):
        self._context_menu_action().trigger()

    def _add_draft_view(self):
        view = self.doc.addObject("TechDraw::DrawViewDraft", "DraftView")
        self.page.addView(view)
        self.doc.recompute()
        return view

    def test_toolbar_warns_about_draft_view_and_cancels(self):
        self._add_draft_view()
        shown = self._run(self._toolbar, QtWidgets.QMessageBox.No)
        self.assertEqual(shown, [("message", _translated(DRAFT_TEXT))])

    def test_context_menu_warns_about_draft_view_and_cancels(self):
        self._add_draft_view()
        shown = self._run(self._context_menu, QtWidgets.QMessageBox.No)
        self.assertEqual(shown, [("message", _translated(DRAFT_TEXT))])

    def test_context_menu_warning_continues_to_save_dialog(self):
        self._add_draft_view()
        shown = self._run(self._context_menu, QtWidgets.QMessageBox.Yes)
        self.assertEqual(shown, [("message", _translated(DRAFT_TEXT)), "file"])

    def test_context_menu_warns_about_bim_view(self):
        view = self.doc.addObject("TechDraw::DrawViewArch", "ArchView")
        self.page.addView(view)
        self.doc.recompute()
        shown = self._run(self._context_menu, QtWidgets.QMessageBox.No)
        self.assertEqual(shown, [("message", _translated(BIM_TEXT))])

    def test_no_warning_without_draft_or_bim_view_control(self):
        for trigger in (self._toolbar, self._context_menu):
            with self.subTest(trigger=trigger.__name__):
                self.assertEqual(self._run(trigger, QtWidgets.QMessageBox.No), ["file"])


if __name__ == "__main__":
    unittest.main()
