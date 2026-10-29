# SPDX-License-Identifier: LGPL-2.1-or-later
"""Collapsed property groups show an indicator in the property view (#23967)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestPropertyGroupIndicatorGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PropertyGroupIndicator23967")
        self.obj = self.doc.addObject("App::FeaturePython", "Owner")
        self.obj.addProperty("App::PropertyLength", "Size", "Dimensions")
        self.obj.addProperty("App::PropertyLength", "Depth", "Dimensions")
        self.doc.recompute()
        self.editor = self.find_editor()
        self.show_editor()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.obj)
        self.settle()
        # showing the panel can recreate the property editors
        self.editor = self.find_editor()
        self.settle(200)

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def settle(self, ms=400):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while timer.elapsed() < ms:
            QtWidgets.QApplication.processEvents()

    def find_editor(self):
        main = Gui.getMainWindow()
        for editor in main.findChildren(QtWidgets.QTreeView, "propertyEditorData"):
            parent = editor.parentWidget()
            while parent is not None and not parent.inherits("Gui::PropertyView"):
                parent = parent.parentWidget()
            if parent is not None:
                tabs = [
                    widget
                    for widget in parent.findChildren(QtWidgets.QTabWidget)
                    if widget.indexOf(editor) >= 0
                ]
                if tabs:
                    tabs[0].setCurrentIndex(tabs[0].indexOf(editor))
                return editor
        self.fail("No property editor found")

    def show_editor(self):
        # The property view only updates while it is visible
        Gui.getMainWindow().show()
        child = self.editor
        parent = child.parentWidget()
        while parent is not None:
            if isinstance(parent, QtWidgets.QStackedWidget):
                parent.setCurrentWidget(child)
            elif isinstance(parent, QtWidgets.QDockWidget):
                parent.show()
                parent.raise_()
            child = parent
            parent = parent.parentWidget()
        self.settle(200)

    def group_index(self, name):
        model = self.editor.model()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            if model.data(index) == name:
                return index
        shown = [model.data(model.index(row, 0)) for row in range(model.rowCount())]
        self.fail(f"Property group {name!r} not shown in {shown}")

    def grab_row(self, index):
        rect = self.editor.visualRect(index)
        rect.setRight(self.editor.viewport().width() - 1)
        return self.editor.viewport().grab(rect).toImage()

    def testCollapsedGroupLooksDifferent(self):
        self.settle()
        index = self.group_index("Dimensions")

        self.editor.expand(index)
        self.settle(200)
        expanded = self.grab_row(index)

        self.editor.collapse(index)
        self.settle(200)
        self.assertFalse(self.editor.isExpanded(index))
        collapsed = self.grab_row(index)

        self.assertEqual(expanded.size(), collapsed.size())
        self.assertNotEqual(expanded, collapsed, "A collapsed group has no visible indicator")
