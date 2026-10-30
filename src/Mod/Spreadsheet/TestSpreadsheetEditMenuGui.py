# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Edit menu acts on the cells of a focused spreadsheet view.

Edit > Select All selects all cells, and Cut, Copy and Delete are enabled
by the view only when cells are selected.

https://github.com/FreeCAD/FreeCAD/issues/13393
"""

import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtWidgets


def _events(count=5):
    for _ in range(count):
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)


@unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD GUI mode")
class TestSpreadsheetEditMenuGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("SheetEditMenu")
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.sheet.set("A1", "1")
        self.sheet.set("B1", "2")
        self.sheet.set("A2", "3")
        self.doc.recompute()
        FreeCADGui.Selection.clearSelection()

    def _cleanup(self):
        FreeCADGui.Selection.clearSelection()
        if self.doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc_name)
        _events()

    def _focusedTable(self):
        self.sheet.ViewObject.doubleClicked()
        mw = FreeCADGui.getMainWindow()
        tables = []
        for _ in range(50):
            _events(1)
            tables = [
                w
                for w in QtWidgets.QApplication.allWidgets()
                if w.metaObject().className() == "SpreadsheetGui::SheetTableView"
                and w.isVisible()
            ]
            if tables:
                break
        self.assertTrue(tables, "the spreadsheet table was not found")
        table = tables[0]
        def inSheetView():
            # The table sits in a graphics proxy, so the application focus widget
            # is the sheet view (or a widget in it) while the table has the focus.
            focus = QtWidgets.QApplication.focusWidget()
            while focus is not None:
                if focus.metaObject().className() == "SpreadsheetGui::SheetView":
                    return table.hasFocus()
                focus = focus.parentWidget()
            return False

        for _ in range(200):
            if inSheetView():
                break
            if QtWidgets.QApplication.activeWindow() != mw:
                mw.raise_()
                mw.activateWindow()
            table.setFocus(QtCore.Qt.OtherFocusReason)
            _events(1)
        self.assertTrue(inSheetView(), "the spreadsheet view has no focus")
        # the double click selects the sheet in the tree; start from a clean state
        FreeCADGui.Selection.clearSelection()
        table.clearSelection()
        _events()
        return table

    def testSelectAllSelectsAllCells(self):
        table = self._focusedTable()
        self.assertFalse(table.selectionModel().hasSelection())

        FreeCADGui.runCommand("Std_SelectAll", 0)
        _events()

        model = table.model()
        selection = table.selectionModel()
        self.assertTrue(selection.isSelected(model.index(0, 0)))
        last = model.index(model.rowCount() - 1, model.columnCount() - 1)
        self.assertTrue(selection.isSelected(last))
        # the document objects are left alone
        self.assertEqual(FreeCADGui.Selection.getSelection(), [])

    def testCutCopyDeleteNeedSelectedCells(self):
        table = self._focusedTable()
        for name in ("Std_Cut", "Std_Copy", "Std_Delete"):
            self.assertFalse(
                FreeCADGui.Command.get(name).isActive(), name + " is enabled without cells"
            )

        table.setCurrentIndex(table.model().index(0, 0))
        _events()
        self.assertTrue(table.selectionModel().hasSelection())
        for name in ("Std_Cut", "Std_Copy", "Std_Delete"):
            self.assertTrue(
                FreeCADGui.Command.get(name).isActive(), name + " is disabled with a cell"
            )

        # Edit > Delete clears the selected cells, not the sheet object
        FreeCADGui.runCommand("Std_Delete", 0)
        self.doc.recompute()
        _events()
        self.assertIsNotNone(self.doc.getObject("Spreadsheet"))
        self.assertEqual(self.sheet.getContents("A1"), "")
        self.assertEqual(self.sheet.getContents("B1"), "2")


if __name__ == "__main__":
    unittest.main()
