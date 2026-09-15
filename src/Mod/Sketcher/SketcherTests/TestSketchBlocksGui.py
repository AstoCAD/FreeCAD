# SPDX-License-Identifier: LGPL-2.1-or-later

from pathlib import Path
import tempfile

import FreeCAD as App
import SketcherBlock
from PySide import QtCore, QtGui, QtWidgets
from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestSketchBlocksGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("SketchBlocksGuiTest")
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()
        Gui.activeDocument().setEdit(self.sketch.Name)

    def tearDown(self):
        super().tearDown()
        self.directory.cleanup()

    def svg(self, circle=False):
        path = Path(self.directory.name) / "import 'é.svg"
        shape = '<circle cx="5" cy="5" r="5"/>' if circle else '<rect width="10" height="5"/>'
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10mm" '
                        'height="10mm" viewBox="0 0 10 10">' + shape + '</svg>', encoding="utf-8")
        return path

    def testStandardImportInEditAndUndo(self):
        path = self.svg()
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/General")
        dialogs = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        old_filter = preferences.GetString("FileImportFilter")
        old_native = dialogs.GetBool("DontUseNativeDialog")
        preferences.SetString("FileImportFilter", "SVG as geometry")
        dialogs.SetBool("DontUseNativeDialog", True)
        errors = []

        def choose():
            try:
                candidates = [w for w in QtWidgets.QApplication.topLevelWidgets()
                              if isinstance(w, QtWidgets.QFileDialog) and w.isVisible()]
                if not candidates:
                    QtCore.QTimer.singleShot(100, choose)
                    return
                dialog = candidates[0]
                filter_name = next(name for name in dialog.nameFilters() if 'SVG as geometry' in name)
                dialog.selectNameFilter(filter_name)
                dialog.setDirectory(str(path.parent))
                # QFileSystemModel loads a new directory asynchronously.
                def finish():
                    filename_edit = dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit")
                    filename_edit.setText('"' + str(path) + '"')
                    dialog.accept()
                QtCore.QTimer.singleShot(200, finish)
            except Exception as error:
                errors.append(error)
                for widget in QtWidgets.QApplication.topLevelWidgets():
                    if isinstance(widget, QtWidgets.QDialog) and widget.isVisible():
                        widget.reject()

        try:
            timeout = QtCore.QTimer()
            timeout.setSingleShot(True)
            def cancel_picker():
                errors.append(TimeoutError("Import file picker did not accept the test file"))
                for widget in QtWidgets.QApplication.topLevelWidgets():
                    if isinstance(widget, QtWidgets.QFileDialog) and widget.isVisible():
                        widget.reject()
            timeout.timeout.connect(cancel_picker)
            timeout.start(5000)
            QtCore.QTimer.singleShot(100, choose)
            Gui.runCommand("Std_Import", 0)
            timeout.stop()
            self.assertFalse(errors, errors)
        finally:
            preferences.SetString("FileImportFilter", old_filter)
            dialogs.SetBool("DontUseNativeDialog", old_native)
        self.assertEqual(len(self.doc.Objects), 1)
        self.assertEqual(self.sketch.GeometryCount, 5)
        group = self.sketch.Constraints[0]
        self.assertEqual(group.Type, "Group")
        self.assertEqual(group.File, str(path))
        self.assertEqual(Gui.activeDocument().getInEdit().Object, self.sketch)
        self.assertEqual(self.sketch.solve(), 0)
        self.doc.undo()
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.doc.redo()
        self.assertEqual(self.sketch.GeometryCount, 5)

    def testSvgReloadAndTemporaryDocumentIsolation(self):
        import importSVG
        path = self.svg()
        sentinel = App.newDocument("SvgImport", hidden=True, temp=True)
        App.setActiveDocument(self.doc.Name)
        try:
            importSVG.insert(str(path), self.doc.Name)
            self.assertIn(sentinel.Name, App.listDocuments())
            self.assertEqual(App.ActiveDocument, self.doc)
            before = self.sketch.Geometry[self.sketch.Constraints[0].First]
            self.svg(True)
            importSVG.reloadSketchGroup(self.sketch, 0)
            self.assertEqual(self.sketch.solve(), 0)
            group = self.sketch.Constraints[0]
            after = self.sketch.Geometry[group.First]
            self.assertLess((before.StartPoint - after.StartPoint).Length, 1e-6)
            self.assertLess((before.EndPoint - after.EndPoint).Length, 1e-6)
            self.assertEqual(self.sketch.GeometryCount, 2)
        finally:
            App.closeDocument(sentinel.Name)

    def testCopyPastePreservesSource(self):
        import importSVG
        path = self.svg()
        importSVG.insert(str(path), self.doc.Name)
        s = self.sketch
        group = s.Constraints[0]
        clipboard = QtWidgets.QApplication.clipboard()
        saved = clipboard.text()
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(s, f"Edge{group.First + 1}")
            Gui.runCommand("Sketcher_CopyClipboard", 0)
            copied = clipboard.text()
            self.assertIn("len(objectStr.Geometry)", copied)
            copied_file = Path(self.directory.name) / "copied.txt"
            copied_file.write_text(copied, encoding="utf-8")
            self.assertEqual(len(SketcherBlock.read(copied_file)), s.GeometryCount)
            Gui.runCommand("Sketcher_Paste", 0)
            self.assertEqual(s.solve(), 0)
            self.assertEqual(len(s.Constraints), 2)
            self.assertEqual(s.Constraints[1].File, group.File)
            self.assertEqual(s.Constraints[1].FileHeight, group.FileHeight)
        finally:
            clipboard.setText(saved)

    def testInsertBlockTool(self):
        self.assertIn("Sketcher_InsertBlock", Gui.listCommands())
        view = Gui.activeDocument().activeView()
        view.setCamera('#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 '
                       'orientation 0 0 1 0 focalDistance 100 height 100 }')
        self.flush_gui(100)
        Gui.runCommand("Sketcher_InsertBlock", 0)
        self.flush_gui(100)
        combos = Gui.getMainWindow().findChildren(QtWidgets.QComboBox)
        library = next(combo for combo in combos if combo.findText("CE") >= 0)
        library.setCurrentIndex(library.findText("CE"))
        viewport = view.graphicsView().viewport()
        for x, y in ((-20, -10), (20, -10)):
            point = self.viewport_to_qpoint(view, viewport,
                                            view.getPointOnScreen(App.Vector(x, y, 0)))
            self.move(viewport, point)
            self.click(viewport, point)
        self.assertEqual(self.sketch.solve(), 0)
        groups = [c for c in self.sketch.Constraints if c.Type == "Group"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(Path(groups[0].File).name, "CE.txt")
        self.assertGreater(self.sketch.GeometryCount, 1)

    def testSvgImportOutsideEdit(self):
        import importSVG
        Gui.activeDocument().resetEdit()
        path = self.svg()
        importSVG.insert(str(path), self.doc.Name)
        self.assertEqual(self.sketch.GeometryCount, 0)
        self.assertGreater(len(self.doc.Objects), 1)

    def testInsertCustomSingleCurveBlock(self):
        path = Path(self.directory.name) / "custom 'é.txt"
        path.write_text("# Copied from sketcher.\ngeoList = []\n"
                        "geoList.append(Part.Circle(App.Vector(0,0,0), App.Vector(0,0,1), 5))\n"
                        "objectStr.addGeometry(geoList, False)\n", encoding="utf-8")
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        old_native = preferences.GetBool("DontUseNativeDialog")
        preferences.SetBool("DontUseNativeDialog", True)
        view = Gui.activeDocument().activeView()
        view.setCamera('#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 '
                       'orientation 0 0 1 0 focalDistance 100 height 100 }')
        self.flush_gui(100)
        Gui.runCommand("Sketcher_InsertBlock", 0)
        combos = Gui.getMainWindow().findChildren(QtWidgets.QComboBox)
        library = next(combo for combo in combos if combo.findText("CE") >= 0)
        errors = []

        def choose():
            dialog = next(w for w in QtWidgets.QApplication.topLevelWidgets()
                          if isinstance(w, QtWidgets.QFileDialog) and w.isVisible())
            try:
                dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit").setText('"' + str(path) + '"')
                dialog.accept()
            except Exception as error:
                errors.append(error)
                dialog.reject()

        try:
            QtCore.QTimer.singleShot(100, choose)
            library.setCurrentIndex(library.count() - 1)
        finally:
            preferences.SetBool("DontUseNativeDialog", old_native)
        self.assertFalse(errors, errors)
        viewport = view.graphicsView().viewport()
        for x, y in ((-20, -10), (20, -10)):
            point = self.viewport_to_qpoint(view, viewport,
                                            view.getPointOnScreen(App.Vector(x, y, 0)))
            self.move(viewport, point)
            self.click(viewport, point)
        self.assertEqual(self.sketch.GeometryCount, 2)
        self.assertEqual(self.sketch.solve(), 0)
        group = next(c for c in self.sketch.Constraints if c.Type == "Group")
        self.assertEqual(Path(group.File), path)

    def testReloadContextMenuAndUndo(self):
        import importSVG
        path = self.svg()
        importSVG.insert(str(path), self.doc.Name)
        self.svg(True)
        self.flush_gui(100)
        constraints = Gui.getMainWindow().findChild(QtWidgets.QListWidget, "listWidgetConstraints")
        constraints.setCurrentRow(0)
        errors = []

        def reload_action():
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                action = next(action for action in menu.actions() if action.text() == "Reload From File")
                action.trigger()
            except Exception as error:
                errors.append(error)
            finally:
                if menu:
                    menu.close()

        QtCore.QTimer.singleShot(100, reload_action)
        point = QtCore.QPoint(5, 5)
        event = QtGui.QContextMenuEvent(QtGui.QContextMenuEvent.Mouse, point,
                                       constraints.viewport().mapToGlobal(point))
        QtWidgets.QApplication.sendEvent(constraints.viewport(), event)
        self.assertFalse(errors, errors)
        self.assertEqual(self.sketch.GeometryCount, 2)
        self.assertEqual(self.sketch.solve(), 0)
        self.doc.undo()
        self.assertEqual(self.sketch.GeometryCount, 5)

    def prepareBlockSelection(self):
        import Part
        self.sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
        self.sketch.addGeometry(Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 8, 0)), True)
        self.sketch.addGeometry(Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        Gui.Selection.clearSelection()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(self.sketch, edge)
        self.flush_gui(100)

    def testCreateBlockMenuAvailability(self):
        self.prepareBlockSelection()
        command = Gui.Command.get("Sketcher_CreateBlock")
        action = command.getAction()[0]
        self.assertTrue(any(action in menu.actions()
                            for menu in Gui.getMainWindow().findChildren(QtWidgets.QMenu)))
        self.assertFalse(any(action in bar.actions()
                             for bar in Gui.getMainWindow().findChildren(QtWidgets.QToolBar)))
        viewport = Gui.activeDocument().activeView().graphicsView().viewport()
        for names, expected in (([], False), (["Edge1"], False),
                                (["Edge1", "Vertex1"], False), (["Edge1", "Edge2"], True)):
            with self.subTest(selection=names):
                Gui.Selection.clearSelection()
                for name in names:
                    Gui.Selection.addSelection(self.sketch, name)
                self.flush_gui(100)
                self.assertEqual(command.isActive(), expected)
                found = []

                def inspect_menu():
                    menu = QtWidgets.QApplication.activePopupWidget()
                    found.append(isinstance(menu, QtWidgets.QMenu) and action in menu.actions())
                    if menu:
                        menu.close()

                QtCore.QTimer.singleShot(100, inspect_menu)
                self.right_click(viewport, QtCore.QPoint(20, 20))
                self.assertEqual(found, [expected])

    def testCreateBlockSaveAndCancel(self):
        self.prepareBlockSelection()
        clipboard = QtWidgets.QApplication.clipboard()
        previous = clipboard.text()
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Dialog")
        old_native = preferences.GetBool("DontUseNativeDialog")
        preferences.SetBool("DontUseNativeDialog", True)
        path = Path(self.directory.name) / "created 'é.txt"
        errors = []
        before = [geo.Content for geo in self.sketch.Geometry]

        def choose_save():
            dialog = QtWidgets.QApplication.activeModalWidget()
            try:
                self.assertIsInstance(dialog, QtWidgets.QFileDialog)
                self.assertEqual(dialog.acceptMode(), QtWidgets.QFileDialog.AcceptSave)
                self.assertEqual(Path(dialog.directory().absolutePath()),
                                 Path(App.getResourceDir()) / "Mod/Sketcher/Blocks")
                dialog.findChild(QtWidgets.QLineEdit, "fileNameEdit").setText(
                    '"' + str(path.with_suffix("")) + '"')
                dialog.accept()
            except Exception as error:
                errors.append(error)
                if dialog:
                    dialog.reject()

        def create_from_menu():
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                self.assertIsInstance(menu, QtWidgets.QMenu)
                action = Gui.Command.get("Sketcher_CreateBlock").getAction()[0]
                self.assertIn(action, menu.actions())
                QtCore.QTimer.singleShot(100, choose_save)
                action.trigger()
            except Exception as error:
                errors.append(error)
            finally:
                if menu:
                    menu.close()

        try:
            Gui.runCommand("Sketcher_CopyClipboard", 0)
            expected = clipboard.text()
            clipboard.setText("Preserve the clipboard")
            QtCore.QTimer.singleShot(100, create_from_menu)
            viewport = Gui.activeDocument().activeView().graphicsView().viewport()
            self.right_click(viewport, QtCore.QPoint(20, 20))
            self.assertFalse(errors, errors)
            self.assertEqual(path.read_text(encoding="utf-8"), expected)
            geometry = SketcherBlock.read(path)
            self.assertEqual(len(geometry), 2)
            self.assertEqual([SketcherBlock.Sketcher.GeometryFacade(geo).Construction
                              for geo in geometry], [False, True])
            self.assertEqual(clipboard.text(), "Preserve the clipboard")
            self.assertEqual([geo.Content for geo in self.sketch.Geometry], before)

            def cancel_save():
                dialog = QtWidgets.QApplication.activeModalWidget()
                if dialog:
                    dialog.reject()

            QtCore.QTimer.singleShot(100, cancel_save)
            Gui.runCommand("Sketcher_CreateBlock", 0)
            self.assertEqual(list(Path(self.directory.name).iterdir()), [path])
            self.assertEqual(path.read_text(encoding="utf-8"), expected)
            self.assertEqual(clipboard.text(), "Preserve the clipboard")
            self.assertEqual([geo.Content for geo in self.sketch.Geometry], before)
        finally:
            clipboard.setText(previous)
            preferences.SetBool("DontUseNativeDialog", old_native)
