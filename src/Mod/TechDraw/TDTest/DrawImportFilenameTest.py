# SPDX-License-Identifier: LGPL-2.1-or-later
"""Real import commands preserve filenames when constructing recorded Python."""

from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import TechDraw
import TechDrawGui
from PySide import QtCore, QtGui, QtSvg, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawImportFilenameTest(unittest.TestCase):
    def setUp(self):
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        contents = preferences.GetContents() or []
        had_preference = any(entry[1] == "DontUseNativeDialog" for entry in contents)
        previous_preference = preferences.GetBool("DontUseNativeDialog", False)

        def restore_preferences():
            if had_preference:
                preferences.SetBool("DontUseNativeDialog", previous_preference)
            else:
                preferences.RemBool("DontUseNativeDialog")

        self.addCleanup(restore_preferences)
        preferences.SetBool("DontUseNativeDialog", True)
        previous_workbench = Gui.activeWorkbench().name()
        self.addCleanup(Gui.activateWorkbench, previous_workbench)
        Gui.activateWorkbench("TechDrawWorkbench")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.doc = App.newDocument("ImportFilenameRegression")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(Gui.Selection.clearSelection)
        self.page = createPageWithSVGTemplate(self.doc)
        self.doc.recompute()
        self.page.ViewObject.show()
        Gui.updateGui()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.page.Name)

    def runCommandWithFile(self, command, path):
        """Drive the actual Qt picker after its directory model has loaded."""
        trace = {"picker_count": 0, "selected": [], "errors": []}
        deadline = time.monotonic() + 15
        ready_at = None
        submitted = False
        timer = QtCore.QTimer()

        def choose_file():
            nonlocal ready_at, submitted
            dialogs = [widget for widget in QtWidgets.QApplication.topLevelWidgets()
                       if isinstance(widget, QtWidgets.QFileDialog) and widget.isVisible()]
            if time.monotonic() >= deadline:
                trace["errors"].append("File selection timed out")
                for dialog in dialogs:
                    dialog.reject()
                timer.stop()
                return
            if not dialogs or submitted:
                return
            dialog = dialogs[0]
            try:
                if not trace["picker_count"]:
                    trace["picker_count"] += 1
                    self.assertTrue(dialog.testOption(QtWidgets.QFileDialog.DontUseNativeDialog))
                    dialog.setDirectory(str(path.parent))
                    ready_at = time.monotonic() + 0.25
                    return
                if time.monotonic() < ready_at:
                    return
                filename_edit = dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                self.assertIsNotNone(filename_edit)
                filename_edit.setText('"' + str(path) + '"')
                trace["selected"] = dialog.selectedFiles()
                if (len(trace["selected"]) != 1
                        or Path(trace["selected"][0]).resolve() != path.resolve()):
                    return
                submitted = True
                dialog.accept()
            except Exception as error:
                trace["errors"].append(repr(error))
                dialog.reject()

        timer.timeout.connect(choose_file)
        timer.start(25)
        insert_preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw")
        preference_name = "DontShowInsertFileMessage"
        had_preference = any(entry[1] == preference_name
                             for entry in (insert_preferences.GetContents() or []))
        previous_preference = insert_preferences.GetBool(preference_name, False)
        if command == "TechDraw_View":
            insert_preferences.SetBool(preference_name, True)
        try:
            Gui.runCommand(command)
        finally:
            timer.stop()
            timer.deleteLater()
            if command == "TechDraw_View":
                if had_preference:
                    insert_preferences.SetBool(preference_name, previous_preference)
                else:
                    insert_preferences.RemBool(preference_name)
        self.assertEqual(trace["picker_count"], 1, trace)
        self.assertFalse(trace["errors"], trace)
        self.assertEqual(len(trace["selected"]), 1, trace)
        self.assertEqual(Path(trace["selected"][0]).resolve(), path.resolve(), trace)

    def assertOnlyImportedObject(self, imported, before):
        self.assertEqual(tuple(obj.Name for obj in self.doc.Objects if obj != imported), before)
        self.assertEqual(self.page.Views, [imported])
        self.assertEqual(self.page.Template, self.doc.getObject("Template"))
        self.assertFalse(any(obj.isDerivedFrom("Part::Feature") for obj in self.doc.Objects))

    def checkImage(self, basename, command="TechDraw_Image"):
        path = Path(self.directory.name) / (basename + ".png")
        image = QtGui.QImage(8, 8, QtGui.QImage.Format_ARGB32)
        image.fill(QtGui.QColor("#ff0000"))
        self.assertTrue(image.save(str(path)))
        before = tuple(obj.Name for obj in self.doc.Objects)
        self.runCommandWithFile(command, path)
        images = [obj for obj in self.doc.Objects if obj.TypeId == "TechDraw::DrawViewImage"]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].findParentPage(), self.page)
        self.assertEqual(Path(images[0].ImageFile).resolve(), path.resolve())
        loaded = QtGui.QImage(images[0].ImageFile)
        self.assertEqual((loaded.width(), loaded.height()), (8, 8))
        self.assertEqual(loaded.pixelColor(0, 0), QtGui.QColor("#ff0000"))
        self.assertOnlyImportedObject(images[0], before)

    def checkSymbol(self, basename, command="TechDraw_Symbol"):
        path = Path(self.directory.name) / (basename + ".svg")
        # Distinct content prevents a failed read from reusing a prior console 'svg'.
        content = ('<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" '
                   'viewBox="0 0 20 10"><rect id="asset-' + basename
                   + '" width="20" height="10" fill="#0000ff"/></svg>')
        path.write_text(content, encoding="utf-8")
        before = tuple(obj.Name for obj in self.doc.Objects)
        self.runCommandWithFile(command, path)
        symbols = [obj for obj in self.doc.Objects if obj.TypeId == "TechDraw::DrawViewSymbol"]
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0].findParentPage(), self.page)
        self.assertEqual(symbols[0].Symbol, content)
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(symbols[0].Symbol.encode("utf-8")))
        self.assertTrue(renderer.isValid())
        self.assertOnlyImportedObject(symbols[0], before)

    def checkDxf(self, basename, route="command"):
        path = Path(self.directory.name) / (basename + ".dxf")
        annotation = self.doc.addObject("TechDraw::DrawViewAnnotation", "DxfText")
        annotation.Text = ["DXF filename control"]
        self.page.addView(annotation)
        self.doc.recompute()
        before = (tuple(obj.Name for obj in self.doc.Objects), tuple(self.page.Views),
                  tuple(annotation.Text), annotation.X.Value, annotation.Y.Value)
        if route == "command":
            self.runCommandWithFile("TechDraw_ExportPageDXF", path)
        elif route == "gui_export":
            TechDrawGui.export([self.page], str(path))
        else:
            TechDraw.writeDXFPage(self.page, str(path))
        after = (tuple(obj.Name for obj in self.doc.Objects), tuple(self.page.Views),
                 tuple(annotation.Text), annotation.X.Value, annotation.Y.Value)
        self.assertEqual(after, before)
        self.assertTrue(path.is_file(), str(path))
        lines = path.read_text(encoding="utf-8").splitlines()
        texts = []
        in_text = False
        for code, value in zip(lines[::2], lines[1::2]):
            if int(code.strip()) == 0:
                in_text = value.strip() == "TEXT"
            elif in_text and int(code.strip()) == 1:
                texts.append(value.strip())
        self.assertEqual(texts, ["DXF filename control"])

    def testImageOrdinaryFilename(self):
        self.checkImage("ordinary")

    def testImageUnicodeFilename(self):
        self.checkImage("image_é_測定")

    def testImageApostropheFilename(self):
        self.checkImage("O'Brien")

    def testSymbolOrdinaryFilename(self):
        self.checkSymbol("ordinary")

    def testSymbolUnicodeFilename(self):
        self.checkSymbol("symbol_é_測定")

    def testSymbolApostropheFilename(self):
        self.checkSymbol("O'Brien")

    def testGenericImageOrdinaryFilename(self):
        self.checkImage("ordinary", "TechDraw_View")

    def testGenericImageApostropheFilename(self):
        self.checkImage("O'Brien", "TechDraw_View")

    def testGenericSymbolOrdinaryFilename(self):
        self.checkSymbol("ordinary", "TechDraw_View")

    def testGenericSymbolApostropheFilename(self):
        self.checkSymbol("O'Brien", "TechDraw_View")

    def testDxfOrdinaryFilename(self):
        self.checkDxf("ordinary")

    def testDxfUnicodeFilename(self):
        self.checkDxf("drawing_é_測定")

    def testDxfApostropheFilename(self):
        self.checkDxf("O'Brien")

    def testDxfGuiExportOrdinaryFilename(self):
        self.checkDxf("ordinary", "gui_export")

    def testDxfGuiExportApostropheFilename(self):
        self.checkDxf("O'Brien", "gui_export")

    def testDxfDirectExportApostropheFilename(self):
        self.checkDxf("O'Brien", "direct_export")
