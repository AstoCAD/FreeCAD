# SPDX-License-Identifier: LGPL-2.1-or-later
"""A symbol or image inserted from the toolbar lands on top of the page stack.

https://github.com/FreeCAD/FreeCAD/issues/24820
"""

from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtGui, QtWidgets

TDTEST = Path(__file__).resolve().parent
RAISED = 7

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" '
    'viewBox="0 0 20 10"><rect x="0" y="0" width="20" height="10" '
    'fill="none" stroke="black"/></svg>\n'
)


@unittest.skipUnless(App.GuiUp, "Insert symbol stack order requires the GUI")
class TestInsertSymbolStackTopGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        self.temporary = tempfile.TemporaryDirectory(prefix="td_stacktop_")
        self.directory = Path(self.temporary.name)
        self.dialog_settings = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        self.general_settings = App.ParamGet("User parameter:BaseApp/Preferences/General")
        self.td_settings = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw")
        self.saved = [
            (self.dialog_settings, "Boolean", "DontUseNativeDialog"),
            (self.general_settings, "String", "FileOpenSavePath"),
            (self.td_settings, "Boolean", "DontShowInsertFileMessage"),
        ]
        self.saved = [(group, kind, name, self._parameter(group, kind, name))
                      for group, kind, name in self.saved]
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.addCleanup(self._cleanup)
        self.dialog_settings.SetBool("DontUseNativeDialog", True)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.app = QtWidgets.QApplication.instance()

        self.doc = App.newDocument("InsertSymbolStackTop")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        self.page.Template = template
        self.annotation = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        self.annotation.Text = ["Raised"]
        self.annotation.X, self.annotation.Y = 100, 100
        self.page.addView(self.annotation)
        self.doc.recompute()
        self.page.ViewObject.show()
        self._pump(100)
        self.annotation.ViewObject.StackOrder = RAISED
        self._pump()
        Gui.Selection.clearSelection()

    @staticmethod
    def _parameter(group, kind, name):
        found = [value for entry_kind, key, value in group.GetContents() or []
                 if entry_kind == kind and key == name]
        return (bool(found), found[0] if found else None)

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _run(self, command_name, path):
        """Trigger a command and answer its info box and file dialog."""
        seen, errors, expired = [], [], []

        def handle():
            modal = self.app.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                modal.accept()
                return
            if not isinstance(modal, QtWidgets.QFileDialog):
                return
            poll.stop()
            try:
                seen.append(modal.windowTitle())
                modal.selectFile(str(path))
                modal.accept()
            except Exception as error:  # pragma: no cover - diagnostic only
                errors.append(str(error))
                modal.reject()

        def timeout():
            expired.append(True)
            modal = self.app.activeModalWidget()
            if isinstance(modal, QtWidgets.QDialog):
                modal.reject()

        poll = QtCore.QTimer()
        poll.timeout.connect(handle)
        watchdog = QtCore.QTimer()
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(timeout)
        poll.start(20)
        watchdog.start(10000)
        try:
            Gui.runCommand(command_name)
        finally:
            poll.stop()
            watchdog.stop()
        self._pump(100)
        self.assertEqual(errors, [])
        self.assertEqual(expired, [])
        self.assertEqual(len(seen), 1, "Exactly one file dialog must be answered")

    def _new_view(self, type_id):
        views = [obj for obj in self.page.Views if obj.TypeId == type_id]
        self.assertEqual(len(views), 1)
        return views[0]

    def _write_svg(self):
        path = self.directory / "symbol.svg"
        path.write_text(SVG, encoding="utf-8")
        return path

    def _write_png(self):
        path = self.directory / "image.png"
        image = QtGui.QImage(16, 16, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("red"))
        self.assertTrue(image.save(str(path)))
        return path

    def _assert_on_top(self, view):
        self.assertTrue(self._wait(lambda: view.ViewObject.StackOrder > RAISED),
                        "New view StackOrder {} is not above {}".format(
                            view.ViewObject.StackOrder, RAISED))
        self.assertEqual(self.annotation.ViewObject.StackOrder, RAISED)

    def test_symbol_command_stacks_on_top(self):
        self._run("TechDraw_Symbol", self._write_svg())
        self._assert_on_top(self._new_view("TechDraw::DrawViewSymbol"))

    def test_view_command_svg_stacks_on_top(self):
        self._run("TechDraw_View", self._write_svg())
        self._assert_on_top(self._new_view("TechDraw::DrawViewSymbol"))

    def test_view_command_image_stacks_on_top(self):
        self._run("TechDraw_View", self._write_png())
        self._assert_on_top(self._new_view("TechDraw::DrawViewImage"))

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
            self._pump()
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for group, kind, name, (present, value) in self.saved:
            if present:
                getattr(group, "Set" + ("Bool" if kind == "Boolean" else "String"))(name, value)
            else:
                getattr(group, "Rem" + ("Bool" if kind == "Boolean" else "String"))(name)
        self.temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
