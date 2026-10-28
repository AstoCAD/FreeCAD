# SPDX-License-Identifier: LGPL-2.1-or-later
"""Ordinary Material_Edit 2D-array acceptance and cancellation regressions.

An explicitly selected disposable profile is required. These tests never save
material cards and use actual delegate editors and normal dialog buttons.
"""

import json
import os
from pathlib import Path
import math
import time
import sys
import traceback
import unittest

import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


UUID = "c6c64159-19c1-40b5-859c-10561f20f979"
EDITOR = "MatGui::MaterialsEditor"
ARRAY = "MatGui::Array2D"
TIMEOUT = 12.0


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def events(ms=20):
    QtTest.QTest.qWait(ms)


def wait(predicate, message, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        events()
    raise AssertionError(message)


def dialogs(name):
    return [
        widget for widget in QtWidgets.QApplication.topLevelWidgets()
        if isinstance(widget, QtWidgets.QDialog)
        and widget.inherits(name) and widget.isVisible()
    ]


def one(parent, kind, name):
    found = parent.findChildren(kind, name)
    require(len(found) == 1, "Expected exactly one " + name)
    return found[0]


def button(dialog, role):
    box = one(dialog, QtWidgets.QDialogButtonBox, "standardButtons")
    result = box.button(role)
    require(result is not None and result.isEnabled(), "Missing enabled dialog button")
    return result


def enum_int(value):
    return value.value if hasattr(value, "value") else int(value)


def find_index(model, role, value, parent=None):
    if parent is None:
        parent = QtCore.QModelIndex()
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        if str(model.data(index, role)) == value:
            return index
        result = find_index(model, role, value, index)
        if result.isValid():
            return result
    return QtCore.QModelIndex()


def show_index(tree, index):
    require(index.isValid(), "Cannot show invalid model index")
    parent = index.parent()
    while parent.isValid():
        tree.expand(parent)
        parent = parent.parent()
    tree.scrollTo(index)
    events()
    rect = tree.visualRect(index)
    require(rect.isValid() and not rect.isEmpty(), "Model index has no visible rectangle")
    return rect.center()


def open_editor():
    require(not dialogs(EDITOR) and not dialogs(ARRAY), "Material dialog already open")
    require(QtWidgets.QApplication.activeModalWidget() is None, "Foreign modal already open")
    Gui.runCommand("Material_Edit")
    wait(lambda: len(dialogs(EDITOR)) == 1, "Material_Edit did not show its editor")
    editor = dialogs(EDITOR)[0]
    require(editor.parentWidget() == Gui.getMainWindow(), "Unexpected editor owner")
    editor.raise_()
    editor.activateWindow()
    wait(lambda: QtWidgets.QApplication.activeWindow() == editor,
         "Material editor did not become active")
    tree = one(editor, QtWidgets.QTreeView, "treeMaterials")
    index = find_index(tree.model(), QtCore.Qt.UserRole, UUID)
    require(index.isValid(), "Bundled Test Material UUID absent")
    point = show_index(tree, index)
    QtTest.QTest.mouseClick(tree.viewport(), QtCore.Qt.LeftButton,
                           QtCore.Qt.NoModifier, point)
    name = one(editor, QtWidgets.QLineEdit, "editName")
    wait(lambda: name.text() == "Test Material", "Test Material selection did not load")
    tabs = one(editor, QtWidgets.QTabWidget, "tabWidget")
    page = one(editor, QtWidgets.QWidget, "tabProperties")
    tab = tabs.indexOf(page)
    require(tab >= 0, "Physical tab missing")
    QtTest.QTest.mouseClick(tabs.tabBar(), QtCore.Qt.LeftButton,
                           QtCore.Qt.NoModifier, tabs.tabBar().tabRect(tab).center())
    wait(lambda: tabs.currentWidget() == page, "Physical tab did not activate")
    property_index(editor)
    return editor


def property_index(editor):
    tree = one(editor, QtWidgets.QTreeView, "treePhysicalProperties")
    index = find_index(tree.model(), enum_int(QtCore.Qt.UserRole) + 1, "TestArray2D")
    require(index.isValid(), "TestArray2D property absent")
    type_index = index.sibling(index.row(), 2)
    require(str(tree.model().data(type_index, QtCore.Qt.DisplayRole)) == "2DArray",
            "Selected property is not a 2D array")
    return tree, index.sibling(index.row(), 1)


def quantity(value):
    require(hasattr(value, "Value") and hasattr(value, "Unit"),
            "Qt DisplayRole did not expose a Base.Quantity copy")
    number = float(value.Value)
    require(math.isfinite(number), "Non-finite test quantity")
    return {"value": number, "unit": str(value.Unit)}


def snapshot(dialog):
    table = one(dialog, QtWidgets.QTableView, "tableView")
    model = table.model()
    require(model is not None, "Array table has no model")
    rows = model.rowCount()
    columns = model.columnCount()
    require(rows >= 1 and columns == 2, "Unexpected 2D array shape")
    result = {
        "row_count": rows,
        "column_count": columns,
        "headers": [str(model.headerData(c, QtCore.Qt.Horizontal,
                                         QtCore.Qt.DisplayRole)) for c in range(columns)],
        "last_row_header": str(model.headerData(rows - 1, QtCore.Qt.Vertical,
                                                QtCore.Qt.DisplayRole)),
        "cells": [
            [quantity(model.data(model.index(r, c), QtCore.Qt.DisplayRole))
             for c in range(columns)]
            for r in range(rows - 1)
        ],
    }
    require(result["last_row_header"] == "*", "Blank insertion row missing")
    return result


def same_quantity(actual, expected):
    return actual["unit"] == expected["unit"] and math.isclose(
        actual["value"], expected["value"], rel_tol=1e-12, abs_tol=1e-12)


def assert_baseline(data):
    require(data["row_count"] == 4 and data["column_count"] == 2,
            "Bundled baseline row/column count differs")
    require(data["headers"] == ["Temperature", "Density"],
            "Bundled baseline headers differ")
    for row, number in enumerate((10, 20, 30)):
        for column, unit in enumerate(("C", "kg/m^3")):
            expected = quantity(App.Units.Quantity(str(number) + " " + unit))
            require(same_quantity(data["cells"][row][column], expected),
                    "Bundled baseline quantity differs at %s,%s" % (row, column))


def edit_density(dialog, row=0, text="11 kg/m^3", expected_rows=4, commit=True):
    table = one(dialog, QtWidgets.QTableView, "tableView")
    model = table.model()
    changed = []
    model.dataChanged.connect(lambda *args: changed.append(True))
    index = model.index(row, 1)
    require(dialog.isVisible() and table.isVisibleTo(dialog),
            "Actual array child/table is not visible")
    dialog.raise_()
    dialog.activateWindow()
    wait(lambda: QtWidgets.QApplication.activeWindow() == dialog,
         "Array child did not become the active window")
    table.scrollTo(index)
    table.setFocus(QtCore.Qt.OtherFocusReason)
    events()
    rect = table.visualRect(index)
    require(rect.isValid() and not rect.isEmpty()
            and table.viewport().rect().contains(rect.center()),
            "Actual editable cell has no visible viewport rectangle")
    point = rect.center()
    QtTest.QTest.mouseClick(table.viewport(), QtCore.Qt.LeftButton,
                           QtCore.Qt.NoModifier, point)
    events()
    require(table.currentIndex() == index, "Ordinary cell click did not select its index")
    QtTest.QTest.mouseDClick(table.viewport(), QtCore.Qt.LeftButton,
                            QtCore.Qt.NoModifier, point)

    def spinbox():
        focus = QtWidgets.QApplication.focusWidget()
        while focus is not None and focus != table:
            if focus.inherits("Gui::QuantitySpinBox"):
                return focus
            focus = focus.parentWidget()
        return None

    def edit_activation_diagnostic():
        chain = []
        focus = QtWidgets.QApplication.focusWidget()
        while focus is not None and len(chain) < 20:
            chain.append({"class": focus.metaObject().className(),
                          "name": focus.objectName(),
                          "visible": focus.isVisible(), "focus": focus.hasFocus()})
            focus = focus.parentWidget()
        candidates = [
            {"class": widget.metaObject().className(), "name": widget.objectName(),
             "visible": widget.isVisible(), "focus": widget.hasFocus()}
            for widget in table.findChildren(QtWidgets.QWidget)
            if widget.inherits("QAbstractSpinBox") or widget.inherits("QLineEdit")
        ]
        return json.dumps({"focus_chain": chain, "edit_candidates": candidates},
                          sort_keys=True)

    try:
        wait(lambda: spinbox() is not None, "Real QuantitySpinBox editor did not open", timeout=5)
    except AssertionError as error:
        raise AssertionError(str(error) + "; " + edit_activation_diagnostic()) from error
    editor = spinbox()
    require(table.isAncestorOf(editor), "Quantity editor is not owned by the array table")
    line = editor.findChild(QtWidgets.QLineEdit)
    require(line is not None, "Quantity editor has no line edit")
    line.selectAll()
    QtTest.QTest.keyClicks(line, text)
    if not commit:
        require(line.hasFocus(), "Typed pending quantity editor lost line focus")
        require(line.text().replace(" ", "") == text.replace(" ", ""),
                "Pending quantity text differs from the ordinary typed input")
        pending = snapshot(dialog)
        pending["pending_editor"] = {"text": line.text(), "focused": line.hasFocus()}
        return pending
    QtTest.QTest.keyClick(line, QtCore.Qt.Key_Tab)
    expected = quantity(App.Units.Quantity(text))

    def committed():
        actual = quantity(model.data(index, QtCore.Qt.DisplayRole))
        return bool(changed) and same_quantity(actual, expected)

    wait(committed, "Ordinary quantity edit did not commit before closing")
    after = snapshot(dialog)
    require(after["row_count"] == expected_rows, "Ordinary edit produced the wrong row count")
    return after


def is_owned_modal(modal, editor):
    if modal is None:
        return False
    if modal.inherits(ARRAY) and modal in dialogs(ARRAY):
        return True
    parent = modal.parentWidget()
    while parent is not None:
        if parent == editor or parent.inherits(ARRAY):
            return True
        parent = parent.parentWidget()
    return False


def normal_cancel_modal(editor):
    modal = QtWidgets.QApplication.activeModalWidget()
    if not is_owned_modal(modal, editor):
        return False
    if isinstance(modal, QtWidgets.QMessageBox):
        cancel = modal.button(QtWidgets.QMessageBox.Cancel)
        require(cancel is not None, "Owned message box has no Cancel button")
        cancel.click()
        return True
    if modal.inherits(ARRAY):
        button(modal, QtWidgets.QDialogButtonBox.Cancel).click()
        return True
    return False


def child(editor, operation=None, accept=False, mouse_accept=False):
    """Timer acts inside the real modal exec; all callback errors are transported."""
    tree, index = property_index(editor)
    point = show_index(tree, index)
    require(not dialogs(ARRAY), "Unexpected existing Array2D dialog")
    state = {"done": False, "errors": [], "before": None, "after_edit": None}
    deadline = time.monotonic() + TIMEOUT
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    watchdog = QtCore.QTimer()
    watchdog.setInterval(100)

    def fail_callback():
        state["errors"].append(traceback.format_exc())

    def tick():
        try:
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is None or not modal.inherits(ARRAY):
                if time.monotonic() >= deadline:
                    raise AssertionError("Array2D modal did not open")
                timer.start(20)
                return
            require(len(dialogs(ARRAY)) == 1, "More than one array dialog")
            state["before"] = snapshot(modal)
            if operation is not None:
                state["after_edit"] = operation(modal)
            else:
                state["after_edit"] = state["before"]
            role = (QtWidgets.QDialogButtonBox.Ok if accept
                    else QtWidgets.QDialogButtonBox.Cancel)
            close_button = button(modal, role)
            if mouse_accept:
                require(accept, "Mouse acceptance is only used with the real OK button")
                require(close_button.isVisibleTo(modal), "Real OK button is not visible")
                QtTest.QTest.mouseClick(close_button, QtCore.Qt.LeftButton)
            else:
                close_button.click()
            state["done"] = True
        except BaseException:
            fail_callback()
            try:
                normal_cancel_modal(editor)
            except BaseException:
                fail_callback()
            state["done"] = True

    def timeout_tick():
        if time.monotonic() < deadline:
            return
        if not state.get("deadline_reported"):
            state["errors"].append("Array callback exceeded its bounded deadline")
            state["deadline_reported"] = True
        try:
            normal_cancel_modal(editor)
        except BaseException:
            fail_callback()
        state["done"] = True

    timer.timeout.connect(tick)
    watchdog.timeout.connect(timeout_tick)
    timer.start(0)
    watchdog.start()
    try:
        QtTest.QTest.mouseDClick(tree.viewport(), QtCore.Qt.LeftButton,
                                QtCore.Qt.NoModifier, point)
        wait(lambda: state["done"], "Array controller did not complete", TIMEOUT + 1)
    finally:
        timer.stop()
        watchdog.stop()
    events()
    require(not dialogs(ARRAY), "Owned child remained visible after normal button close")
    require(not state["errors"], "Array callback error:\n" + "\n".join(state["errors"]))
    require(state["before"] is not None, "Array callback never captured its table")
    return {"before": state["before"], "after_edit": state["after_edit"]}


def parent_dirty(editor):
    """Click real parent OK; observe and Cancel the real unsaved prompt if present."""
    state = {"done": False, "dirty": None, "errors": []}
    deadline = time.monotonic() + TIMEOUT
    timer = QtCore.QTimer()
    timer.setInterval(20)

    def tick():
        try:
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox) and modal.parentWidget() == editor:
                wanted = (QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard
                          | QtWidgets.QMessageBox.Cancel)
                require(modal.standardButtons() == wanted, "Unexpected parent message box")
                require(modal.text() == QtCore.QCoreApplication.translate(
                    "QObject", "Save changes to the material before closing?"),
                    "Unexpected unsaved-material prompt text")
                state["dirty"] = True
                modal.button(QtWidgets.QMessageBox.Cancel).click()
                state["done"] = True
                timer.stop()
                return
            if not dialogs(EDITOR):
                state["dirty"] = False
                state["done"] = True
                timer.stop()
                return
            if time.monotonic() >= deadline:
                raise AssertionError("Parent OK neither closed nor showed its unsaved prompt")
        except BaseException:
            state["errors"].append(traceback.format_exc())
            try:
                normal_cancel_modal(editor)
            except BaseException:
                state["errors"].append(traceback.format_exc())
            state["done"] = True
            timer.stop()

    timer.timeout.connect(tick)
    timer.start()
    try:
        close_button = button(editor, QtWidgets.QDialogButtonBox.Ok)
        close_button.click()
        wait(lambda: state["done"], "Parent dirty controller did not complete", TIMEOUT + 1)
    finally:
        timer.stop()
    require(not state["errors"], "Parent callback error:\n" + "\n".join(state["errors"]))
    require(state["dirty"] is not None, "No parent dirty observation")
    return state["dirty"]


def cleanup():
    # Rediscover only this diagnostic's admitted dialogs; no direct deletion.
    editors = dialogs(EDITOR)
    if editors:
        normal_cancel_modal(editors[0])
    for dialog in dialogs(ARRAY):
        button(dialog, QtWidgets.QDialogButtonBox.Cancel).click()
    for editor in dialogs(EDITOR):
        button(editor, QtWidgets.QDialogButtonBox.Cancel).click()
    events()
    wait(lambda: not dialogs(EDITOR) and not dialogs(ARRAY),
         "Owned material dialogs did not close normally")
    require(QtWidgets.QApplication.activeModalWidget() is None,
            "Unexpected modal remained after diagnostic")



def delete_second_row(dialog):
    table = one(dialog, QtWidgets.QTableView, "tableView")
    model = table.model()
    require(model.rowCount() == 4, "Deletion fixture must start with three real rows")
    index = model.index(1, 1)
    table.scrollTo(index)
    table.setFocus(QtCore.Qt.OtherFocusReason)
    events()
    rect = table.visualRect(index)
    require(rect.isValid() and not rect.isEmpty(), "Deletion row is not visible")
    QtTest.QTest.mouseClick(table.viewport(), QtCore.Qt.LeftButton,
                           QtCore.Qt.NoModifier, rect.center())
    require(table.currentIndex() == index, "Ordinary deletion row selection failed")
    state = {"done": False, "errors": []}
    deadline = time.monotonic() + 5
    timer = QtCore.QTimer()
    timer.setInterval(20)

    def tick():
        try:
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox) and modal.parentWidget() == dialog:
                require(modal.standardButtons() ==
                        (QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel),
                        "Unexpected row deletion confirmation buttons")
                require(modal.text() == QtCore.QCoreApplication.translate(
                    "QObject", "Delete the row?"), "Unexpected row deletion prompt")
                modal.button(QtWidgets.QMessageBox.Ok).click()
                state["done"] = True
                timer.stop()
                return
            if time.monotonic() >= deadline:
                raise AssertionError("Ordinary Delete key did not open its confirmation")
        except BaseException:
            state["errors"].append(traceback.format_exc())
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox) and modal.parentWidget() == dialog:
                cancel = modal.button(QtWidgets.QMessageBox.Cancel)
                if cancel is not None:
                    cancel.click()
            state["done"] = True
            timer.stop()

    timer.timeout.connect(tick)
    timer.start()
    try:
        key = QtCore.Qt.Key_Backspace if sys.platform == "darwin" else QtCore.Qt.Key_Delete
        QtTest.QTest.keyClick(table, key)
        wait(lambda: state["done"], "Row deletion controller did not complete", 6)
    finally:
        timer.stop()
    require(not state["errors"], "Deletion callback error:\n" + "\n".join(state["errors"]))
    require(model.rowCount() == 3, "Confirmed deletion did not remove exactly one real row")
    return snapshot(dialog)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestArray2DCancelGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        import MatGui  # Register the command only after disposable-profile admission.
        require(not dialogs(EDITOR) and not dialogs(ARRAY), "Material dialog already open")
        require(QtWidgets.QApplication.activeModalWidget() is None, "Foreign modal already open")
        self.addCleanup(cleanup)
        self.editor = open_editor()

    def _owned_profile(self):
        selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
        if not selected:
            self.skipTest("Requires an explicitly selected disposable test profile")
        import stat

        def plain_path(path):
            for component in (path, *path.parents):
                try:
                    if component.is_symlink():
                        return False
                    is_junction = getattr(component, "is_junction", None)
                    if is_junction is not None and is_junction():
                        return False
                    attributes = getattr(component.lstat(), "st_file_attributes", 0)
                    if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                        return False
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
            return True

        raw = Path(selected)
        if not raw.is_absolute() or not plain_path(raw):
            self.skipTest("The disposable test profile must be an absolute directory without links")
        try:
            profile = raw.resolve(strict=True)
        except OSError:
            self.skipTest("The disposable test profile must already exist")
        if not profile.is_dir():
            self.skipTest("The disposable test profile must be a directory")
        configured_home = os.environ.get("FREECAD_USER_HOME")
        if not configured_home:
            self.skipTest("FREECAD_USER_HOME must explicitly select the disposable test profile")
        home = Path(configured_home)
        if not home.is_absolute() or not plain_path(home):
            self.skipTest("FREECAD_USER_HOME must be an absolute directory without links")
        try:
            matching_home = home.resolve(strict=True) == profile
        except OSError:
            matching_home = False
        if not matching_home:
            self.skipTest("FREECAD_USER_HOME does not match the disposable test profile")
        parameter_file = Path(App.ConfigGet("UserParameter"))
        data_directory = Path(App.getUserAppDataDir())
        paths = (parameter_file, data_directory)
        if not all(path.is_absolute() and plain_path(path) for path in paths):
            self.skipTest("Active profile paths must be absolute and free of links")
        if parameter_file.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside the selected test profile")
        if not all(path.resolve().is_relative_to(profile) for path in paths):
            self.skipTest("Active user configuration and data must stay in the test profile")
        return profile

    def _exercise(self, operation=None, accept=False, mouse_accept=False):
        first = child(self.editor, operation=operation, accept=accept,
                      mouse_accept=mouse_accept)
        assert_baseline(first["before"])
        reopened = child(self.editor)["before"]
        dirty = parent_dirty(self.editor)
        return first, reopened, dirty

    @staticmethod
    def _cell_expected(before):
        # Scalar snapshots are independent Python dictionaries, not material objects.
        expected = json.loads(json.dumps(before))
        expected["cells"][0][1] = quantity(App.Units.Quantity("11 kg/m^3"))
        return expected

    @staticmethod
    def _added_expected(before):
        expected = json.loads(json.dumps(before))
        expected["row_count"] = 5
        expected["cells"].append([
            quantity(App.Units.Quantity("0 C")),
            quantity(App.Units.Quantity("41 kg/m^3")),
        ])
        return expected

    @staticmethod
    def _deleted_expected(before):
        expected = json.loads(json.dumps(before))
        expected["row_count"] = 3
        del expected["cells"][1]
        return expected

    def test_no_edit_cancel_preserves_clean_material(self):
        first, reopened, dirty = self._exercise()
        self.assertEqual(first["after_edit"], first["before"])
        self.assertEqual(reopened, first["before"])
        self.assertFalse(dirty)

    def test_no_edit_ok_preserves_clean_material(self):
        first, reopened, dirty = self._exercise(accept=True)
        self.assertEqual(first["after_edit"], first["before"])
        self.assertEqual(reopened, first["before"])
        self.assertFalse(dirty)

    def test_committed_cell_edit_ok_publishes(self):
        first, reopened, dirty = self._exercise(edit_density, accept=True)
        expected = self._cell_expected(first["before"])
        self.assertEqual(first["after_edit"], expected)
        self.assertEqual(reopened, expected)
        self.assertTrue(dirty)

    def test_committed_cell_edit_cancel_preserves_material(self):
        first, reopened, dirty = self._exercise(edit_density)
        self.assertEqual(first["after_edit"], self._cell_expected(first["before"]))
        with self.subTest("array values and units"):
            self.assertEqual(reopened, first["before"])
        with self.subTest("parent remains clean"):
            self.assertFalse(dirty)

    def test_added_row_ok_publishes(self):
        first, reopened, dirty = self._exercise(
            lambda dialog: edit_density(dialog, row=3, text="41 kg/m^3", expected_rows=5),
            accept=True)
        expected = self._added_expected(first["before"])
        self.assertEqual(first["after_edit"], expected)
        self.assertEqual(reopened, expected)
        self.assertTrue(dirty)

    def test_added_row_cancel_preserves_material(self):
        first, reopened, dirty = self._exercise(
            lambda dialog: edit_density(dialog, row=3, text="41 kg/m^3", expected_rows=5))
        self.assertEqual(first["after_edit"], self._added_expected(first["before"]))
        with self.subTest("array rows values and units"):
            self.assertEqual(reopened, first["before"])
        with self.subTest("parent remains clean"):
            self.assertFalse(dirty)

    def test_deleted_row_ok_publishes(self):
        first, reopened, dirty = self._exercise(delete_second_row, accept=True)
        expected = self._deleted_expected(first["before"])
        self.assertEqual(first["after_edit"], expected)
        self.assertEqual(reopened, expected)
        self.assertTrue(dirty)

    def test_deleted_row_cancel_preserves_material(self):
        first, reopened, dirty = self._exercise(delete_second_row)
        self.assertEqual(first["after_edit"], self._deleted_expected(first["before"]))
        with self.subTest("array rows values and units"):
            self.assertEqual(reopened, first["before"])
        with self.subTest("parent remains clean"):
            self.assertFalse(dirty)

    def test_pending_cell_edit_ok(self):
        first, reopened, dirty = self._exercise(
            lambda dialog: edit_density(dialog, commit=False),
            accept=True, mouse_accept=True)
        pending = first["after_edit"]
        self.assertTrue(pending["pending_editor"]["focused"])
        self.assertEqual(pending["pending_editor"]["text"].replace(" ", ""), "11kg/m^3")
        # Typing may update the editor's quantity before the view commits its model.
        # The real button mouse click must finish the edit before acceptance publishes.
        self.assertEqual(reopened, self._cell_expected(first["before"]))
        self.assertTrue(dirty)

    @staticmethod
    def _row_api_expected(before, operation):
        expected = json.loads(json.dumps(before))
        if operation == "insert":
            expected["row_count"] += 1
            expected["cells"].insert(1, [
                quantity(App.Units.Quantity("0 C")),
                quantity(App.Units.Quantity("0 kg/m^3")),
            ])
        else:
            require(operation == "remove", "Unknown valid row operation")
            expected["row_count"] -= 1
            del expected["cells"][1]
        return expected

    def _row_api_working_table(self, dialog, operation):
        before = snapshot(dialog)
        assert_baseline(before)
        table = one(dialog, QtWidgets.QTableView, "tableView")
        model = table.model()
        inserted, removed, changed = [], [], []
        model.rowsInserted.connect(
            lambda parent, first, last: inserted.append((parent.isValid(), first, last)))
        model.rowsRemoved.connect(
            lambda parent, first, last: removed.append((parent.isValid(), first, last)))
        model.dataChanged.connect(lambda *args: changed.append(True))
        if operation == "insert":
            returned = model.insertRows(1, 1, QtCore.QModelIndex())
        else:
            self.assertEqual(operation, "remove")
            returned = model.removeRows(1, 1, QtCore.QModelIndex())
        self.assertIsInstance(returned, bool)
        # The existing false return-value defect is separate from publication.
        print("Array2D valid %sRows returned %r (return-value issue held separately)"
              % (operation, returned), flush=True)
        wanted_signal = [(False, 1, 1)]
        self.assertEqual(inserted, wanted_signal if operation == "insert" else [])
        self.assertEqual(removed, wanted_signal if operation == "remove" else [])
        self.assertEqual(changed, [])
        actual = snapshot(dialog)
        self.assertEqual(actual, self._row_api_expected(before, operation))
        return actual

    def _check_row_api(self, operation, accept):
        first, reopened, dirty = self._exercise(
            lambda dialog: self._row_api_working_table(dialog, operation),
            accept=accept)
        expected_after = self._row_api_expected(first["before"], operation)
        self.assertEqual(first["after_edit"], expected_after)
        expected_reopened = expected_after if accept else first["before"]
        with self.subTest("array rows values and units"):
            self.assertEqual(reopened, expected_reopened)
        with self.subTest("parent dirty state"):
            self.assertIs(dirty, accept)

    def test_valid_insert_rows_api_ok_publishes(self):
        self._check_row_api("insert", True)

    def test_valid_insert_rows_api_cancel_preserves_material(self):
        self._check_row_api("insert", False)

    def test_valid_remove_rows_api_ok_publishes(self):
        self._check_row_api("remove", True)

    def test_valid_remove_rows_api_cancel_preserves_material(self):
        self._check_row_api("remove", False)
