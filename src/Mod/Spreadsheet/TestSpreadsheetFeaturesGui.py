# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI entry points of the spreadsheet editing features (sort, find, ...)."""

import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui, QtWidgets


@unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD GUI mode")
class TestSpreadsheetFeaturesGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("SheetFeaturesGui")
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.doc.recompute()

    def _cleanup(self):
        if self.doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc_name)

    def _process(self, count=20):
        for _ in range(count):
            QtWidgets.QApplication.processEvents()

    def _tableView(self):
        self.sheet.ViewObject.doubleClicked()
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            # the table sits in a graphics proxy, it is not a child of the main window
            for widget in QtWidgets.QApplication.allWidgets():
                if widget.metaObject().className() == "SpreadsheetGui::SheetTableView":
                    return widget
        self.fail("the spreadsheet view was not opened")

    def _action(self, table, text):
        action_class = getattr(QtGui, "QAction", None) or QtWidgets.QAction
        for action in table.findChildren(action_class):
            if action.text() == text:
                return action
        self.fail(f"no action '{text}' in the spreadsheet view")

    def _select(self, table, top, left, bottom, right, current=None):
        model = table.model()
        selection = QtCore.QItemSelection(model.index(top, left), model.index(bottom, right))
        table.selectionModel().select(selection, QtCore.QItemSelectionModel.ClearAndSelect)
        row, col = current if current else (top, left)
        table.selectionModel().setCurrentIndex(
            model.index(row, col), QtCore.QItemSelectionModel.NoUpdate
        )

    def testSortFromContextMenuActions(self):
        for row, (name, value) in enumerate([("b", "2"), ("c", "3"), ("a", "1")], start=1):
            self.sheet.set(f"A{row}", name)
            self.sheet.set(f"B{row}", value)
        self.doc.recompute()
        table = self._tableView()
        # Sorts the selection by the column of the current cell
        self._select(table, 0, 0, 2, 1, current=(0, 1))
        self._action(table, "Sort Descending").trigger()
        self._process()
        self.assertEqual([self.sheet.get(f"B{row}") for row in range(1, 4)], [3, 2, 1])
        self._select(table, 0, 0, 2, 1)
        self._action(table, "Sort Ascending").trigger()
        self._process()
        self.assertEqual([self.sheet.getContents(f"A{row}") for row in range(1, 4)], ["'a", "'b", "'c"])
        # One undo step
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual([self.sheet.get(f"B{row}") for row in range(1, 4)], [3, 2, 1])


if __name__ == "__main__":
    unittest.main()
