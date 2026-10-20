# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure shortcuts preserve native Spreadsheet editing and task/3D controls."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import MeasureGui
try:
    import Spreadsheet
    import SpreadsheetGui
except ModuleNotFoundError as error:
    if error.name not in {"Spreadsheet", "SpreadsheetGui"}:
        raise
    Spreadsheet = None
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
    from shiboken6 import getCppPointer, isValid, wrapInstance
except ImportError:
    from PySide2 import QtTest
    from shiboken2 import getCppPointer, isValid, wrapInstance


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
@unittest.skipIf(Spreadsheet is None, "Requires the Spreadsheet module")
class TestMeasureShortcutGui(unittest.TestCase):
    def setUp(self):
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.doc = App.newDocument("MeasureShortcutGuiTest")
        self.addCleanup(self._cleanup)
        self.box = self.doc.addObject("Part::Box", "Box")
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet")
        self.sheet.set("A1", "7")
        self.doc.recompute()
        self.view = Gui.activeDocument().activeView()
        self.graphics = self.view.graphicsView()
        self.viewport = self.graphics.viewport()
        self.view.fitAll()
        self.strong_editors = []
        self.strong_widgets = []
        self.task_buttons = None
        self.sheet_table = None
        self.sheet_index = None
        Gui.Selection.clearSelection()
        Gui.updateGui()

    def _cancel_pending_editor(self):
        if self.sheet_table is None or not isValid(self.sheet_table):
            return
        for editor in self.strong_editors:
            if not isValid(editor) or not editor.isVisible():
                continue
            # The delegate emits this signal for normal Escape cancellation.
            # Use it only in cleanup, so a consumed Return cannot leave a live
            # scene editor attached to the following test's new document.
            delegate = self.sheet_table.itemDelegateForIndex(self.sheet_index)
            self.strong_widgets.append(delegate)
            delegate.closeEditor.emit(editor, QtWidgets.QAbstractItemDelegate.RevertModelCache)
            Gui.updateGui()
            QtTest.QTest.qWait(20)

    def _cleanup(self):
        try:
            self._cancel_pending_editor()
        finally:
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
            if self.previous in App.listDocuments():
                App.setActiveDocument(self.previous)

    def _wait(self, predicate, message):
        clock = QtCore.QElapsedTimer()
        clock.start()
        while not predicate() and clock.elapsed() < 2000:
            Gui.updateGui()
            QtTest.QTest.qWait(20)
        self.assertTrue(predicate(), message)

    def _snapshot(self):
        group = self.doc.getObject("Measurements")
        return {
            "measurements": sorted(obj.Name for obj in self.doc.Objects
                                   if obj.isDerivedFrom("Measure::MeasureBase")),
            "saved": sorted(obj.Name for obj in group.Group) if group else [],
            "selection": [(item.Object.Name, list(item.SubElementNames))
                          for item in Gui.Selection.getSelectionEx()],
            "task_open": bool(Gui.Control.activeDialog()),
        }

    def _buttons(self):
        if self.task_buttons is not None:
            return self.task_buttons
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        contents = task.getDialogContent()
        self.strong_widgets.extend([task, *contents])
        panel = contents[0]
        while True:
            parent = panel.parentWidget()
            self.assertIsNotNone(parent)
            self.strong_widgets.append(parent)
            if isinstance(parent, QtWidgets.QStackedWidget):
                break
            panel = parent
        buttons = panel.findChild(QtWidgets.QDialogButtonBox)
        self.assertIsNotNone(buttons)
        self.strong_widgets.append(buttons)
        self.strong_widgets.extend(buttons.buttons())
        self.task_buttons = buttons
        return buttons

    def _open_measure(self):
        Gui.Selection.addSelection(self.doc.Name, self.box.Name, "Edge1")
        Gui.runCommand("Std_Measure")
        self._wait(lambda: Gui.Control.activeDialog(), "Measure task did not open")
        self._wait(lambda: self._buttons().button(QtWidgets.QDialogButtonBox.Apply).isEnabled(),
                   "Real edge did not produce a savable measurement")
        state = self._snapshot()
        self.assertEqual(len(state["measurements"]), 1)
        self.assertEqual(state["saved"], [])
        self.preview = state["measurements"][0]

    def _sheet_widgets(self):
        self.sheet.ViewObject.showSheetMdi()
        self.sheet_view = self.sheet.ViewObject.getView()
        self.strong_widgets.append(self.sheet_view)
        Gui.updateGui()
        QtTest.QTest.qWait(100)
        Gui.updateGui()
        widgets = QtWidgets.QApplication.allWidgets()
        self.strong_widgets.extend(widgets)
        candidates = []
        for widget in widgets:
            if not (widget.inherits("QTableView") and widget.objectName() == "cells"
                    and widget.isVisible()):
                continue
            table = widget
            if not isinstance(table, QtWidgets.QTableView):
                table = wrapInstance(getCppPointer(widget)[0], QtWidgets.QTableView)
                self.strong_widgets.append(table)
            proxy = table.graphicsProxyWidget()
            self.assertIsNotNone(proxy, "Native cell table has no graphics proxy")
            self.strong_widgets.append(proxy)
            scene = proxy.scene()
            self.assertIsNotNone(scene)
            self.strong_widgets.append(scene)
            views = scene.views()
            self.strong_widgets.extend(views)
            for view in views:
                if view.inherits("ZoomableView") and view.isVisible():
                    self.sheet_scene = scene
                    candidates.append((table, view))
        self.assertEqual(len(candidates), 1, "Expected one actual visible Spreadsheet cell table")
        self.strong_widgets.extend(candidates[0])
        self.sheet_table = candidates[0][0]
        return candidates[0]

    def _edit_sheet(self):
        table, zoom = self._sheet_widgets()
        index = table.model().index(0, 0)
        self.sheet_index = index
        self.assertTrue(index.isValid())
        table.setCurrentIndex(index)
        table.setFocus()
        table.edit(index)
        Gui.updateGui()
        QtTest.QTest.qWait(50)
        Gui.updateGui()
        items = self.sheet_scene.items()
        self.strong_widgets.extend(items)
        candidate_widgets = {}

        def add_widget(widget, origin):
            if widget is None or not isValid(widget):
                return
            self.strong_widgets.append(widget)
            pointer = getCppPointer(widget)[0]
            if pointer not in candidate_widgets:
                candidate_widgets[pointer] = [widget, []]
            candidate_widgets[pointer][1].append(origin)

        for widget in table.findChildren(QtWidgets.QLineEdit):
            add_widget(widget, "table-descendant")
        viewport = table.viewport()
        self.strong_widgets.append(viewport)
        for widget in viewport.findChildren(QtWidgets.QLineEdit):
            add_widget(widget, "viewport-descendant")
        for item in items:
            proxy = item
            # A proxy can be exposed only as QGraphicsItem. Do not try to
            # reinterpret a multiple-inheritance base pointer as the proxy.
            # The live QWidget inventory below still identifies its editor.
            if isinstance(proxy, QtWidgets.QGraphicsProxyWidget):
                embedded = proxy.widget()
                if embedded is not None:
                    self.strong_widgets.append(embedded)
                    if embedded.inherits("QLineEdit"):
                        add_widget(embedded, "scene-proxy-root")
                    for widget in embedded.findChildren(QtWidgets.QLineEdit):
                        add_widget(widget, "scene-proxy-descendant")
        all_widgets = QtWidgets.QApplication.allWidgets()
        self.strong_widgets.extend(all_widgets)
        for widget in all_widgets:
            if isValid(widget) and widget.inherits("QLineEdit"):
                add_widget(widget, "all-native-line-edits")
        editors = []
        for widget, origins in candidate_widgets.values():
            edit = widget
            if not isinstance(edit, QtWidgets.QLineEdit):
                edit = wrapInstance(getCppPointer(widget)[0], QtWidgets.QLineEdit)
                self.strong_widgets.append(edit)
            meta = edit.metaObject().className()
            parents = []
            parent = edit.parentWidget()
            while parent is not None and len(parents) < 8:
                self.strong_widgets.append(parent)
                parents.append(parent)
                parent = parent.parentWidget()
            own_proxy = edit.graphicsProxyWidget()
            in_scene = False
            if own_proxy is not None:
                self.strong_widgets.append(own_proxy)
                in_scene = own_proxy.scene() == self.sheet_scene
            related = table.isAncestorOf(edit) or in_scene or any(
                origin != "all-native-line-edits" for origin in origins
            )
            is_native_editor = meta == "SpreadsheetGui::LineEdit"
            if is_native_editor and related and edit.isVisible() and not edit.isReadOnly():
                editors.append(edit)
        self.assertEqual(len(editors), 1, "The real Spreadsheet delegate editor was not created")
        editor = editors[0]
        self.strong_editors.append(editor)
        self.assertEqual(editor.text(), "7")
        editor.setFocus()
        # QWidget focus inside a scene does not activate its containing view.
        # Give the real canvas keyboard focus before sending editor keys.
        zoom.setFocus(QtCore.Qt.OtherFocusReason)
        Gui.updateGui()
        editor_proxy = editor.graphicsProxyWidget()
        self.assertIsNotNone(editor_proxy)
        self.strong_widgets.append(editor_proxy)
        self.assertEqual(editor_proxy.scene(), self.sheet_scene)

        def editor_has_focus():
            return editor.hasFocus() and editor_proxy.hasFocus()

        self._wait(editor_has_focus, "Native scene did not focus the cell editor")
        receiver = QtWidgets.QApplication.focusWidget()
        self.assertIsNotNone(receiver)
        self.strong_widgets.append(receiver)
        self.assertTrue(receiver == editor or receiver == zoom or zoom.isAncestorOf(receiver))
        QtTest.QTest.keyClick(receiver, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        QtTest.QTest.keyClicks(receiver, "42")
        self.assertEqual(editor.text(), "42", "Keys did not reach the real scene editor")
        self.assertEqual(self.sheet.getContents("A1"), "7", "Cell was not pending an actual commit")
        return receiver

    def _check_sheet_return(self, measure):
        if measure:
            self._open_measure()
        receiver = self._edit_sheet()
        before = self._snapshot()
        QtTest.QTest.keyClick(receiver, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        self.doc.recompute()
        after = self._snapshot()
        self.assertEqual(self.sheet.getContents("A1"), "42", "Measure consumed Spreadsheet Return")
        if measure:
            self.assertEqual(after, before, "Spreadsheet Return changed the Measure task state")

    def test_spreadsheet_return_with_measure_open(self):
        self._check_sheet_return(measure=True)

    def test_spreadsheet_return_without_measure_control(self):
        self._check_sheet_return(measure=False)

    def _check_sheet_escape(self, measure):
        if measure:
            self._open_measure()
        receiver = self._edit_sheet()
        before = self._snapshot()
        QtTest.QTest.keyClick(receiver, QtCore.Qt.Key_Escape)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        self.doc.recompute()
        after = self._snapshot()
        editor = self.strong_editors[-1]
        editor_closed = not isValid(editor) or not editor.isVisible()
        self.assertEqual(self.sheet.getContents("A1"), "7")
        self.assertTrue(editor_closed, "Spreadsheet Escape did not cancel its pending editor")
        if measure:
            self.assertEqual(after, before, "Spreadsheet Escape changed the Measure task state")

    def test_spreadsheet_escape_with_measure_open(self):
        self._check_sheet_escape(measure=True)

    def test_spreadsheet_escape_without_measure_control(self):
        self._check_sheet_escape(measure=False)

    def _focus_readonly_result(self):
        task = Gui.Control.activeTaskDialog()
        self.strong_widgets.append(task)
        contents = task.getDialogContent()
        self.strong_widgets.extend(contents)
        candidates = [edit for content in contents
                      for edit in content.findChildren(QtWidgets.QLineEdit)
                      if edit.isVisible() and edit.isReadOnly()]
        self.strong_widgets.extend(candidates)
        self.assertEqual(len(candidates), 1, "Expected the native readonly measurement result")
        target = candidates[0]
        target.setFocus()
        self._wait(lambda: QtWidgets.QApplication.focusWidget() == target,
                   "Readonly measurement result did not receive focus")
        return target

    def test_readonly_result_return_preserves_preview_control(self):
        self._open_measure()
        target = self._focus_readonly_result()
        before = self._snapshot()
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        # ShortcutManager reserves keys for every QLineEdit, including readonly
        # results. Preserve the existing task preview rather than invoking Save.
        self.assertEqual(self._snapshot(), before)

    def test_readonly_result_escape_closes_task_control(self):
        self._open_measure()
        target = self._focus_readonly_result()
        before = self._snapshot()
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Escape)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        after = self._snapshot()
        # The ordinary key reaches TaskView's Abort button after QLineEdit.
        self.assertFalse(after["task_open"])
        self.assertEqual(after["measurements"], [])
        self.assertEqual(after["saved"], [])
        self.assertEqual(after["selection"], before["selection"])

    def _activate_original_3d(self):
        Gui.activateView("Gui::View3DInventor", False)
        Gui.updateGui()
        self._wait(lambda: self.graphics.isVisible(), "Original 3D view did not reactivate")
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        contents = task.getDialogContent()
        self.strong_widgets.extend([task, *contents])
        self.assertTrue(contents)
        target = self._focus_context(task=False)
        Gui.updateGui()
        self._wait(lambda: all(content.isVisible() for content in contents),
                   "Task content must be visible for native application shortcuts")
        return target

    def test_editor_return_then_3d_return_same_task(self):
        self._open_measure()
        receiver = self._edit_sheet()
        before = self._snapshot()
        QtTest.QTest.keyClick(receiver, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        sheet_state = self._snapshot()
        self.assertEqual(self.sheet.getContents("A1"), "42")
        self.assertEqual(sheet_state, before)
        target = self._activate_original_3d()
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        after = self._snapshot()
        self.assertEqual(after["saved"], [self.preview], "3D Return stayed disabled after cell editing")
        self.assertTrue(after["task_open"])
        self.assertEqual(after["selection"], [])

    def test_editor_return_then_3d_escape_same_task(self):
        self._open_measure()
        receiver = self._edit_sheet()
        before = self._snapshot()
        self.assertEqual(before["selection"], [(self.box.Name, ["Edge1"])])
        QtTest.QTest.keyClick(receiver, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        sheet_state = self._snapshot()
        self.assertEqual(self.sheet.getContents("A1"), "42")
        self.assertEqual(sheet_state, before)
        editor = self.strong_editors[-1]
        self.assertTrue(not isValid(editor) or not editor.isVisible())
        target = self._activate_original_3d()
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Escape)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        after = self._snapshot()
        self.assertTrue(after["task_open"])
        self.assertEqual(after["measurements"], [], "3D Escape stayed disabled after cell editing")
        self.assertEqual(after["saved"], [])
        self.assertEqual(after["selection"], [])

    def _focus_context(self, task):
        if task:
            target = self._buttons().button(QtWidgets.QDialogButtonBox.Reset)
            target.setFocus()
            self._wait(lambda: QtWidgets.QApplication.focusWidget() == target,
                       "Task button did not receive focus")
        else:
            self.viewport.setFocus()
            self._wait(lambda: QtWidgets.QApplication.focusWidget() == self.graphics
                       or self.graphics.isAncestorOf(QtWidgets.QApplication.focusWidget()),
                       "3D viewer did not receive focus")
        return QtWidgets.QApplication.focusWidget()

    def _check_save_return(self, task):
        self._open_measure()
        target = self._focus_context(task)
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Return)
        QtTest.QTest.qWait(80)
        Gui.updateGui()
        after = self._snapshot()
        self.assertEqual(after["saved"], [self.preview])
        self.assertTrue(after["task_open"])
        self.assertEqual(after["selection"], [])

    def test_3d_return_saves_control(self):
        self._check_save_return(task=False)

    def test_task_return_saves_control(self):
        self._check_save_return(task=True)

    def _check_escape(self, task):
        self._open_measure()
        target = self._focus_context(task)
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Escape)
        QtTest.QTest.qWait(50)
        Gui.updateGui()
        first = self._snapshot()
        self.assertTrue(first["task_open"])
        self.assertEqual(first["selection"], [])
        self.assertEqual(first["measurements"], [])
        self.assertEqual(first["saved"], [])
        target = self._focus_context(task)
        QtTest.QTest.keyClick(target, QtCore.Qt.Key_Escape)
        QtTest.QTest.qWait(50)
        Gui.updateGui()
        self.assertFalse(Gui.Control.activeDialog())

    def test_3d_escape_resets_then_closes_control(self):
        self._check_escape(task=False)

    def test_task_escape_resets_then_closes_control(self):
        self._check_escape(task=True)
