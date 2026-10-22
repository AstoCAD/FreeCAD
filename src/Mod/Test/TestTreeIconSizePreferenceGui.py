# SPDX-License-Identifier: LGPL-2.1-or-later
"""Explicit tree icon sizes apply to new and existing ordinary object icons."""

import json
import time
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import PartGui  # noqa: F401
    from PySide import QtCore, QtGui, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the native document tree and icon engine")
class TestTreeIconSizePreferenceGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        self.doc_name = None
        self.boxes = []
        self.edited_size = False
        if int(QtCore.qVersion().split(".")[0]) < 6:
            self.skipTest("Requires the Qt 6 explicit-DPR QIcon pixmap API")
        self.assertEqual(App.listDocuments(), {}, "Use an isolated GUI process")
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        self._events(300)
        self.main = Gui.getMainWindow()
        self.native_dpr = QtWidgets.QApplication.instance().devicePixelRatio()
        supported_dpr = (1.0, 1.25, 1.5, 1.75, 2.0)
        if self.native_dpr not in supported_dpr:
            self.skipTest("Requires a supported native display scale: " + str(supported_dpr))
        self.assertIn(self.native_dpr, supported_dpr)
        self.parameters = App.ParamGet("User parameter:BaseApp/Preferences/TreeView")
        self.original_parameter = self._parameter()
        self.assertLessEqual(len(self.original_parameter), 1)
        if self.original_parameter:
            self.assertEqual(self.original_parameter[0][0], "Integer")
        self.main_geometry = QtCore.QRect(self.main.geometry())
        self.main_state = self.main.windowState()
        self.workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        areas = self.main.findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]
        self.initial_windows = tuple(self.area.subWindowList())
        self.trees = [
            tree
            for tree in self.main.findChildren(QtWidgets.QTreeWidget)
            if tree.inherits("Gui::TreeWidget")
        ]
        self.assertTrue(self.trees)
        self.original_sizes = [(tree, QtCore.QSize(tree.iconSize())) for tree in self.trees]
        self.reports = [
            (widget, widget.toPlainText())
            for widget in self.main.findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(self.reports)
        self.addCleanup(self._cleanup)
        self.doc = App.newDocument("TreeIcon15873_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self._events(300)

    def _parameter(self):
        return tuple(
            entry for entry in (self.parameters.GetContents() or []) if entry[1] == "IconSize"
        )

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self._events()
        return bool(predicate())

    def _set_size(self, size):
        self.edited_size = True
        self.parameters.SetInt("IconSize", size)
        self._events(200)
        self.assertEqual(self.parameters.GetInt("IconSize"), size)
        for tree in self.trees:
            self.assertEqual(tree.iconSize(), QtCore.QSize(size, size))

    def _items(self, box):
        return [
            (tree, tree.findItems(box.Label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0))
            for tree in self.trees
        ]

    def _box(self, name):
        box = self.doc.addObject("Part::Box", name)
        box.Label = self.doc_name + "_" + name
        box.Length, box.Width, box.Height = 2, 3, 4
        self.boxes.append(box)
        self.doc.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertEqual(len(box.Shape.Solids), 1)
        self.assertAlmostEqual(box.Shape.Volume, 24.0)
        self.assertTrue(
            self._wait(lambda: all(len(items) == 1 for _tree, items in self._items(box)))
        )
        self._events(200)
        return box

    @staticmethod
    def _selection_identity():
        return tuple(
            (entry.DocumentName, entry.ObjectName, tuple(entry.SubElementNames))
            for entry in Gui.Selection.getSelectionEx("*")
        )

    def _native_selection(self):
        def row(tree, item):
            if item is None:
                return None
            return (item.type(), tuple(item.text(column) for column in range(tree.columnCount())))

        return tuple(
            (
                row(tree, tree.currentItem()),
                tuple(row(tree, item) for item in tree.selectedItems()),
            )
            for tree in self.trees
        )

    def _model(self):
        return (
            tuple((obj.Name, obj.TypeId, obj.Label) for obj in self.doc.Objects),
            tuple(
                (
                    box.Name,
                    box.Shape.Volume,
                    tuple(box.Placement.toMatrix().A),
                    box.ViewObject.Visibility,
                )
                for box in self.boxes
            ),
            tuple(self.doc.UndoNames),
            tuple(self.doc.RedoNames),
            self.doc.HasPendingTransaction,
            Gui.getDocument(self.doc_name).Modified,
        )

    def _assert_icon_height(self, box, height):
        provider_icon = box.ViewObject.Icon
        self.assertIsInstance(provider_icon, QtGui.QIcon)
        self.assertFalse(provider_icon.isNull())
        provider_pixmap = provider_icon.pixmap(
            QtCore.QSize(height, height), QtGui.QIcon.Normal, QtGui.QIcon.Off
        )
        self.assertFalse(provider_pixmap.isNull())
        self.assertEqual(provider_pixmap.devicePixelRatioF(), self.native_dpr)
        self.assertEqual(provider_pixmap.height() / provider_pixmap.devicePixelRatioF(), height)
        expected_physical_height = provider_pixmap.height()
        for tree, items in self._items(box):
            self.assertEqual(len(items), 1)
            icon = items[0].icon(0)
            self.assertFalse(icon.isNull())
            request = QtCore.QSize(256, 256)
            actual = icon.actualSize(request, QtGui.QIcon.Normal, QtGui.QIcon.Off)
            pixmap = icon.pixmap(request, 1.0, QtGui.QIcon.Normal, QtGui.QIcon.Off)
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.devicePixelRatioF(), 1.0)
            physical_height = pixmap.height() / pixmap.devicePixelRatioF()
            print(
                "TREE_ICON15873",
                json.dumps(
                    {
                        "tree": tree.objectName(),
                        "visible": tree.isVisibleTo(self.main),
                        "box": box.Name,
                        "expected_height": height,
                        "expected_physical_height": expected_physical_height,
                        "provider_pixmap": [provider_pixmap.width(), provider_pixmap.height()],
                        "provider_dpr": provider_pixmap.devicePixelRatioF(),
                        "application_dpr": QtWidgets.QApplication.instance().devicePixelRatio(),
                        "native_icon_size": [tree.iconSize().width(), tree.iconSize().height()],
                        "actual_size": [actual.width(), actual.height()],
                        "pixmap": [pixmap.width(), pixmap.height()],
                        "pixmap_dpr": pixmap.devicePixelRatioF(),
                        "available_sizes": [[s.width(), s.height()] for s in icon.availableSizes()],
                        "qt": QtCore.qVersion(),
                    }
                ),
            )
            with self.subTest(box=box.Name, tree=tree.objectName(), oracle="actualSize"):
                self.assertEqual(actual.height(), expected_physical_height)
            with self.subTest(box=box.Name, tree=tree.objectName(), oracle="pixmapPhysicalHeight"):
                self.assertEqual(physical_height, expected_physical_height)

    def test_explicit_16_override_new_object_control(self):
        self._set_size(24)
        self._set_size(16)
        box = self._box("Control16")
        before = self._model()
        self._assert_icon_height(box, 16)
        self.assertEqual(self._model(), before)

    def test_new_object_after_32_override_control(self):
        self._set_size(16)
        self._set_size(32)
        box = self._box("Control32")
        before = self._model()
        self._assert_icon_height(box, 32)
        self.assertEqual(self._model(), before)

    def test_existing_object_icon_updates_after_16_to_32_override(self):
        self._set_size(24)
        self._set_size(16)
        box = self._box("Existing")
        self._assert_icon_height(box, 16)
        expected_selection = ((self.doc_name, box.Name, ()),)
        Gui.Selection.addSelection(self.doc_name, box.Name)
        self.assertTrue(
            self._wait(
                lambda: self._selection_identity() == expected_selection
                and all(items[0].isSelected() for _tree, items in self._items(box))
            )
        )
        self.assertEqual(self._selection_identity(), expected_selection)
        for tree, items in self._items(box):
            self.assertTrue(items[0].isSelected())
            self.assertEqual(len(tree.selectedItems()), 1)
            self.assertEqual(tree.selectedItems()[0].text(0), box.Label)
        before_selection = self._native_selection()
        before = self._model()
        self._set_size(32)
        self._assert_icon_height(box, 32)
        self.assertEqual(self._native_selection(), before_selection)
        self.assertEqual(self._selection_identity(), expected_selection)
        self.assertEqual(self._model(), before)
        fresh = self._box("FreshAfter32")
        self._assert_icon_height(fresh, 32)

    def _cleanup(self):
        Gui.Selection.clearSelection()
        name = self.doc_name
        self.boxes.clear()
        self.doc = None
        if name is not None and name in App.listDocuments():
            App.closeDocument(name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._events(300)
        if self.edited_size:
            if self.original_parameter:
                self.parameters.SetInt("IconSize", self.original_parameter[0][2])
            else:
                self.parameters.RemInt("IconSize")
            for tree, size in self.original_sizes:
                tree.setIconSize(size)
            self._events(300)
        self.assertEqual(self._parameter(), self.original_parameter)
        for tree, size in self.original_sizes:
            self.assertEqual(tree.iconSize(), size)
        self.assertEqual(App.listDocuments(), {})
        self.assertNotIn(name, App.listDocuments())
        self.assertFalse(Gui.Control.activeDialog())
        self.assertIsNone(QtWidgets.QApplication.activeModalWidget())
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        self.assertEqual(tuple(self.area.subWindowList()), self.initial_windows)
        self.assertEqual(self.main.geometry(), self.main_geometry)
        self.assertEqual(self.main.windowState(), self.main_state)
        workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        self.assertEqual(workbench, self.workbench)
        for report, previous in self.reports:
            current = report.toPlainText()
            self.assertTrue(current.startswith(previous))
            added = current[len(previous) :]
            for marker in (
                "Traceback",
                "Unhandled Base::Exception",
                "Access violation",
                "Python exception",
            ):
                self.assertNotIn(marker, added)
