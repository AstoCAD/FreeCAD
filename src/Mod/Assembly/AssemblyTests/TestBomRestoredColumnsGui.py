# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual BOM restore-column menu and persistent column regressions.

Run in an isolated GUI process. The actual registered task, popup actions,
spreadsheet recompute and native save/reopen paths are used.
"""

import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
    import AssemblyGui  # noqa: F401
    import Part  # noqa: F401
    import CommandCreateBom
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestBomRestoredColumns(unittest.TestCase):
    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "Use a fresh isolated GUI process")
        self.previous_workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        self.owned = []
        self.retained = []
        self.temp = tempfile.TemporaryDirectory(prefix="freecad_bom_columns_")
        pref = CommandCreateBom.Preferences.preferences()
        self.preferences = {key: pref.GetBool(key) if key in pref.GetBools() else None
                            for key in ("BOMOnlyParts", "BOMDetailParts", "BOMDetailSubAssemblies")}
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("BomRestoredColumns")
        self.owned.append(self.doc.Name)
        self.sample = self.doc.addObject("Part::Box", "Sample")
        self.sample.Label = "BOM component"
        self.doc.recompute()
        self.original_geometry = (App.Placement(self.sample.Placement), self.sample.Shape.Volume)
        Gui.runCommand("Assembly_CreateBom")
        self._events()
        self.task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(self.task)
        self.retained.append(self.task)
        contents = self.task.getDialogContent()
        self.assertTrue(contents)
        self.retained.extend(contents)
        forms = []
        for widget in contents:
            self._retain(widget)
            if widget.objectName() == "TaskAssemblyCreateBom":
                forms.append(widget)
            forms.extend(widget.findChildren(QtWidgets.QWidget, "TaskAssemblyCreateBom"))
        self.assertEqual(len(forms), 1, "Actual registered BOM task form missing/ambiguous")
        self.form = forms[0]
        self.columns = self.form.findChild(QtWidgets.QListWidget, "columnList")
        self.button = self.form.findChild(QtWidgets.QPushButton, "btnAddColumn")
        self.assertIsNotNone(self.columns)
        self.assertIsNotNone(self.button)
        self.retained.extend((self.columns, self.button))
        self.assertEqual(self.columns.selectionMode(), QtWidgets.QAbstractItemView.SingleSelection)
        boms = [obj for obj in self.doc.Objects if obj.TypeId == "Assembly::BomObject"]
        self.assertEqual(len(boms), 1)
        self.bom = boms[0]
        self.initial = list(CommandCreateBom.ColumnNames)
        self.assertEqual(list(self.bom.columnsNames), self.initial)
        self.assertEqual(self._ui_names(), self.initial)

    def _events(self):
        Gui.updateGui()
        QtWidgets.QApplication.processEvents()

    def _retain(self, widget):
        while widget is not None:
            self.retained.append(widget)
            widget = widget.parentWidget()

    def _cleanup(self):
        try:
            if Gui.Control.activeDialog():
                task = Gui.Control.activeTaskDialog()
                self.retained.append(task)
                task.reject()
                if Gui.Control.activeDialog():
                    Gui.Control.closeDialog()
        finally:
            Gui.Selection.clearSelection()
            for name in reversed(self.owned):
                if name in App.listDocuments():
                    gui_doc = Gui.getDocument(name)
                    if gui_doc.getInEdit():
                        gui_doc.resetEdit()
                    App.closeDocument(name)
                    QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
                    QtWidgets.QApplication.processEvents()
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)
            pref = CommandCreateBom.Preferences.preferences()
            for key, value in self.preferences.items():
                if value is None:
                    pref.RemBool(key)
                else:
                    pref.SetBool(key, value)
            self.temp.cleanup()

    def _ui_names(self):
        result = []
        for index in range(self.columns.count()):
            name = self.columns.item(index).text()
            if name in CommandCreateBom.TranslatedColumnNames:
                name = CommandCreateBom.ColumnNames[CommandCreateBom.TranslatedColumnNames.index(name)]
            result.append(name)
        return result

    def _delete(self, name):
        row = self._ui_names().index(name)
        self.columns.setCurrentRow(row)
        self.columns.setFocus()
        QtTest.QTest.keyClick(self.columns, QtCore.Qt.Key_Delete)
        self._events()
        expected = [column for column in self.initial if column != name]
        self.assertEqual(self._ui_names(), expected)
        self.assertEqual(list(self.bom.columnsNames), expected)

    def _restore_from_real_menu(self, name):
        translated = CommandCreateBom.TranslatedColumnNames[CommandCreateBom.ColumnNames.index(name)]
        wanted = "Add '" + translated + "' column"
        errors, chosen = [], []
        timer = QtCore.QTimer(self.form)
        self.retained.append(timer)
        elapsed = QtCore.QElapsedTimer()
        elapsed.start()

        def choose():
            menu = QtWidgets.QApplication.activePopupWidget()
            if not isinstance(menu, QtWidgets.QMenu):
                if elapsed.elapsed() >= 3000:
                    timer.stop()
                    errors.append(AssertionError("Actual restore-column menu did not open"))
                    for popup in QtWidgets.QApplication.topLevelWidgets():
                        if isinstance(popup, QtWidgets.QMenu) and popup.isVisible():
                            popup.close()
                return
            timer.stop()
            self.retained.append(menu)
            try:
                actions = [action for action in menu.actions() if action.text() == wanted]
                self.assertEqual(len(actions), 1, "Actual standard-column menu action missing/ambiguous")
                self.retained.extend(actions)
                rectangle = menu.actionGeometry(actions[0])
                self.assertTrue(rectangle.isValid())
                QtTest.QTest.mouseClick(menu, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, rectangle.center())
                chosen.append(name)
            except BaseException as error:
                errors.append(error)
                menu.close()

        timer.timeout.connect(choose)
        timer.start(20)
        try:
            self.button.click()  # Enters the actual QMenu.exec_() nested event loop.
        finally:
            timer.stop()
        if errors:
            raise errors[0]
        self.assertEqual(chosen, [name])
        self._events()

    def _accept_and_check(self, expected):
        self.task.accept()  # Public TaskDialogPy accepts through real buttons and returns None.
        self._events()
        self.assertFalse(Gui.Control.activeDialog())
        self.assertNotIn("Invalid", self.bom.State)
        actual_names = list(self.bom.columnsNames)
        actual_headers = [self.bom.get(chr(65 + index) + "1") for index in range(len(actual_names))]
        with self.subTest(oracle="accepted_stored_columns"):
            self.assertEqual(actual_names, expected)
        with self.subTest(oracle="actual_sheet_headers"):
            self.assertEqual(actual_headers, expected)
        self.assertEqual((self.sample.Placement, self.sample.Shape.Volume), self.original_geometry)

    def _restore(self, name, reopen=False):
        self._delete(name)
        self._restore_from_real_menu(name)
        expected = [column for column in self.initial if column != name] + [name]
        self.assertEqual(self._ui_names(), expected, "Real menu must append the selected restored row")
        with self.subTest(oracle="immediate_model_synchronization"):
            self.assertEqual(list(self.bom.columnsNames), expected)
        bom_name = self.bom.Name
        self._accept_and_check(expected)
        if reopen:
            path = Path(self.temp.name) / "restored_column.FCStd"
            self.doc.saveAs(str(path))
            self.assertTrue(path.is_file())
            App.closeDocument(self.doc.Name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._events()
            restored = App.openDocument(str(path))
            self.owned.append(restored.Name)
            with self.subTest(oracle="saved_reopened_columns"):
                self.assertEqual(list(restored.getObject(bom_name).columnsNames), expected)
            self.assertAlmostEqual(restored.getObject("Sample").Shape.Volume, self.original_geometry[1])

    def test_restore_name_column_through_actual_menu(self):
        self._restore("Name")

    def test_restore_quantity_column_through_actual_menu(self):
        self._restore("Quantity")

    def test_restore_file_name_column_survives_save_reopen(self):
        self._restore("File Name", reopen=True)

    def test_single_column_delete_control(self):
        self._delete("Description")
        self._accept_and_check([column for column in self.initial if column != "Description"])

    def test_add_custom_column_without_restore_menu_control(self):
        self.button.click()  # All standard columns exist, so the ordinary custom-column path runs.
        self._events()
        default = App.Qt.translate("Assembly", "Default")
        expected = self.initial + [default]
        self.assertEqual(self._ui_names(), expected)
        self.assertEqual(list(self.bom.columnsNames), expected)
        self._accept_and_check(expected)


if __name__ == "__main__":
    unittest.main()
