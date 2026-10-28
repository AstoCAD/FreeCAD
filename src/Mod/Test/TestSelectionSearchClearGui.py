# SPDX-License-Identifier: LGPL-2.1-or-later
"""Ordinary Selection View clear-search regression coverage for issue 30009.

These tests use ASCII labels, actual Backspace/Clear-button actions, and ordinary
open documents. Document closure occurs only during cleanup. A disposable profile
is required because the native selection panel writes its visibility preference.
"""

import os
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestSelectionSearchClearGui(unittest.TestCase):
    needle = "ClearSearchUniqueNeedle"

    def setUp(self):
        self.profile = self._owned_profile()
        self.names = []
        self.saved_selection = self._selection_snapshot()
        self.saved_document = App.ActiveDocument.Name if App.ActiveDocument else None
        self.main = Gui.getMainWindow()
        self.saved_focus = QtWidgets.QApplication.focusWidget()
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Selection")
        entries = self.preferences.GetContents() or ()
        self.saved_auto_present = any(entry[1] == "AutoShowSelectionView" for entry in entries)
        self.saved_auto = self.preferences.GetBool("AutoShowSelectionView", False)
        self.addCleanup(self._cleanup)
        self.preferences.SetBool("AutoShowSelectionView", False)
        self.dock = self.main.findChild(QtWidgets.QDockWidget, "Selection view")
        self.assertIsNotNone(self.dock, "The native Selection View dock must exist")
        self.saved_dock_visible = self.dock.isVisible()
        self.panel = self.dock.widget()
        self.assertIsNotNone(self.panel)
        self.assertTrue(self.panel.inherits("Gui::DockWnd::SelectionView"))
        header = self.panel.layout().itemAt(0).layout()
        self.assertIsNotNone(header)
        self.field = header.itemAt(0).widget()
        self.clear_button = header.itemAt(1).widget()
        self.count_label = header.itemAt(2).widget()
        self.listing = self.panel.layout().itemAt(1).widget()
        self.assertIsInstance(self.field, QtWidgets.QLineEdit)
        self.assertIsInstance(self.clear_button, QtWidgets.QToolButton)
        self.assertIsInstance(self.count_label, QtWidgets.QLabel)
        self.assertIsInstance(self.listing, QtWidgets.QListWidget)
        self.dock.show()
        self.dock.raise_()
        self.main.raise_()
        self.main.activateWindow()
        self.assertTrue(self._wait(lambda: self.panel.isVisibleTo(self.main)))
        # Disarm any earlier query before taking ownership of the selection.
        self.field.setText("ClearSearchSetupNoMatchingObject")
        self.field.clear()
        Gui.Selection.clearSelection()
        self.first = self._document("SelectionSearchClearA", "KeptSelectionA", (2, 3, 5))
        self.second = self._document("SelectionSearchClearB", "KeptSelectionB", (3, 5, 7))
        self.match = self.first.addObject("Part::Box", "SearchMatch")
        self.match.Label = self.needle
        self.match.Length, self.match.Width, self.match.Height = 5, 7, 11
        self.first.recompute()
        self.assertTrue(self.match.Shape.isValid())
        self.assertAlmostEqual(self.match.Shape.Volume, 385)
        App.setActiveDocument(self.first.Name)
        Gui.Selection.addSelection(self.first.Name, self.first.Kept.Name, "Face1")
        Gui.Selection.addSelection(self.second.Name, self.second.Kept.Name)
        self._events()
        self.initial = self._selected()
        self.assertEqual(self.initial, sorted([
            (self.first.Name, self.first.Kept.Name, "Face1"),
            (self.second.Name, self.second.Kept.Name, ""),
        ]))
        self._assert_rows(self.initial)
        self.assertEqual(self.field.text(), "")
        self._assert_geometry()

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

    @staticmethod
    def _events():
        QtTest.QTest.qWait(20)

    def _wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._events()
        return True

    def _document(self, name, label, dimensions):
        document = App.newDocument(name)
        self.names.append((document.Name, str(document.Uid)))
        box = document.addObject("Part::Box", "Kept")
        box.Label = label
        box.Length, box.Width, box.Height = dimensions
        document.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertAlmostEqual(box.Shape.Volume, dimensions[0] * dimensions[1] * dimensions[2])
        return document

    @staticmethod
    def _selection_snapshot():
        result = []
        for selected in Gui.Selection.getSelectionEx("*", 0):
            points = tuple((point.x, point.y, point.z) for point in selected.PickedPoints)
            result.append((selected.DocumentName, selected.ObjectName,
                           tuple(selected.SubElementNames), points))
        return result

    @classmethod
    def _selected(cls):
        return sorted((document, name, subname)
                      for document, name, subnames, _points in cls._selection_snapshot()
                      for subname in (subnames or ("",)))

    def _rows(self):
        rows = []
        for index in range(self.listing.count()):
            item = self.listing.item(index)
            identity = item.data(QtCore.Qt.UserRole)
            self.assertIsNotNone(identity)
            self.assertEqual(len(identity), 2)
            subname = item.data(QtCore.Qt.UserRole + 1) or ""
            rows.append((identity[0], identity[1], subname))
        return sorted(rows)

    def _assert_rows(self, expected):
        self.assertTrue(self._wait(lambda: self._rows() == expected),
                        "Displayed rows must be exactly the actual selected identities")
        self.assertEqual(self._rows(), expected)
        self.assertEqual(self.count_label.text(), str(len(expected)))

    def _assert_geometry(self):
        self.assertTrue(self.first.Kept.Shape.isValid())
        self.assertAlmostEqual(self.first.Kept.Shape.Volume, 30)
        self.assertTrue(self.second.Kept.Shape.isValid())
        self.assertAlmostEqual(self.second.Kept.Shape.Volume, 105)
        self.assertTrue(self.match.Shape.isValid())
        self.assertAlmostEqual(self.match.Shape.Volume, 385)

    def _focus_field(self):
        self.assertTrue(self.field.isVisibleTo(self.main))
        self.assertTrue(self.field.isEnabled())
        self.main.raise_()
        self.main.activateWindow()
        self.field.setFocus(QtCore.Qt.OtherFocusReason)
        self.assertTrue(self._wait(lambda:
            QtWidgets.QApplication.applicationState() == QtCore.Qt.ApplicationActive
            and QtWidgets.QApplication.activeWindow() is self.main
            and QtWidgets.QApplication.focusWidget() is self.field
            and self.field.hasFocus()), "The actual visible search editor must receive input")

    def _search(self):
        self._focus_field()
        QtTest.QTest.keyClicks(self.field, self.needle)
        self.assertEqual(self.field.text(), self.needle)
        self._assert_rows([(self.first.Name, self.match.Name, "")])
        self.assertEqual(self._selected(), self.initial)

    def _return(self):
        self._focus_field()
        QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Return)
        self._events()

    def _focus_out(self):
        self.listing.setFocus(QtCore.Qt.OtherFocusReason)
        self.assertTrue(self._wait(lambda: self.listing.hasFocus()
                                  and not self.field.hasFocus()))
        self._events()

    def _clear_search(self, method):
        self._focus_field()
        if method == "backspace":
            self.field.selectAll()
            QtTest.QTest.keyClick(self.field, QtCore.Qt.Key_Backspace)
        else:
            self.assertEqual(method, "button")
            self.assertTrue(self.clear_button.isVisibleTo(self.main))
            self.assertTrue(self.clear_button.isEnabled())
            self.assertTrue(self.clear_button.rect().isValid())
            QtTest.QTest.mouseClick(self.clear_button, QtCore.Qt.LeftButton)
        self._events()
        self.assertEqual(self.field.text(), "")

    def _check_clear(self, method, selected):
        if not selected:
            Gui.Selection.clearSelection()
            self._events()
            self.initial = []
            self._assert_rows([])
        self._search()
        self._clear_search(method)
        # Assert selection before rows, so clearing cannot hide model mutation.
        self.assertEqual(self._selected(), self.initial,
                         "Clearing the filter must not select the old search results")
        self._assert_rows(self.initial)
        self._focus_out()
        self.assertEqual(self._selected(), self.initial)
        self._assert_rows(self.initial)
        self._return()
        self.assertEqual(self._selected(), self.initial,
                         "Empty-search Return must not reapply a discarded query")
        self._assert_rows(self.initial)
        self._assert_geometry()

    def test_fresh_empty_return_control(self):
        self._return()
        self.assertEqual(self._selected(), self.initial)
        self._assert_rows(self.initial)
        self._assert_geometry()

    def test_nonempty_return_control(self):
        self._search()
        self._return()
        expected = [(self.first.Name, self.match.Name, "")]
        self.assertEqual(self._selected(), expected)
        self._assert_rows(expected)
        self._assert_geometry()

    def test_backspace_restores_selected_rows(self):
        self._check_clear("backspace", True)

    def test_clear_button_restores_selected_rows(self):
        self._check_clear("button", True)

    def test_backspace_with_no_selection_clears_rows(self):
        self._check_clear("backspace", False)

    def test_clear_button_with_no_selection_clears_rows(self):
        self._check_clear("button", False)

    def _cleanup(self):
        try:
            if hasattr(self, "field"):
                self.field.setText("ClearSearchCleanupNoMatchingObject")
                self.field.clear()
            Gui.Selection.clearSelection()
            for name, uid in reversed(self.names):
                document = App.getDocument(name) if name in App.listDocuments() else None
                if document is not None and str(document.Uid) == uid:
                    App.closeDocument(name)
            if self.saved_document and self.saved_document in App.listDocuments():
                App.setActiveDocument(self.saved_document)
            for document, name, subnames, points in self.saved_selection:
                if document not in App.listDocuments() or App.getDocument(document).getObject(name) is None:
                    continue
                for index, subname in enumerate(subnames or ("",)):
                    if index < len(points):
                        Gui.Selection.addSelection(document, name, subname, *points[index])
                    else:
                        Gui.Selection.addSelection(document, name, subname)
            if hasattr(self, "saved_dock_visible"):
                self.dock.setVisible(self.saved_dock_visible)
            self._events()
        finally:
            if self.saved_auto_present:
                self.preferences.SetBool("AutoShowSelectionView", self.saved_auto)
            else:
                self.preferences.RemBool("AutoShowSelectionView")
