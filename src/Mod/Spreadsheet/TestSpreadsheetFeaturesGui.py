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

    def _findDialog(self, table):
        self._action(table, "Find and Replace…").trigger()
        self._process()
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.objectName() == "SpreadsheetFindReplace" and widget.isVisible():
                self.addCleanup(widget.close)
                return widget
        self.fail("the find dialog was not opened")

    def testFindAndReplaceDialog(self):
        self.sheet.set("A1", "apple")
        self.sheet.set("B2", "Apple pie")
        self.sheet.set("C3", "pear")
        self.doc.recompute()
        table = self._tableView()
        self._select(table, 0, 0, 0, 0)
        dialog = self._findDialog(table)
        dialog.findChild(QtWidgets.QLineEdit, "findText").setText("apple")
        dialog.findChild(QtWidgets.QPushButton, "findNext").click()
        self.assertEqual((table.currentIndex().row(), table.currentIndex().column()), (1, 1))
        # Wraps around
        dialog.findChild(QtWidgets.QPushButton, "findNext").click()
        self.assertEqual((table.currentIndex().row(), table.currentIndex().column()), (0, 0))
        dialog.findChild(QtWidgets.QPushButton, "findPrevious").click()
        self.assertEqual((table.currentIndex().row(), table.currentIndex().column()), (1, 1))
        # Replace acts on the current match, then moves to the next one
        dialog.findChild(QtWidgets.QLineEdit, "replaceText").setText("plum")
        dialog.findChild(QtWidgets.QPushButton, "replace").click()
        self.assertEqual(self.sheet.getContents("B2"), "'plum pie")
        self.assertEqual(self.sheet.getContents("A1"), "'apple")
        # Replace All is one undo step
        dialog.findChild(QtWidgets.QLineEdit, "findText").setText("p")
        dialog.findChild(QtWidgets.QLineEdit, "replaceText").setText("P")
        dialog.findChild(QtWidgets.QCheckBox, "matchCase").setChecked(True)
        dialog.findChild(QtWidgets.QPushButton, "replaceAll").click()
        self.assertEqual(self.sheet.getContents("A1"), "'aPPle")
        self.assertEqual(self.sheet.getContents("C3"), "'Pear")
        self.doc.undo()
        self.assertEqual(self.sheet.getContents("A1"), "'apple")
        self.assertEqual(self.sheet.getContents("C3"), "'pear")
        self.assertEqual(self.sheet.getContents("B2"), "'plum pie")

    def testIncreaseDecreaseDecimalsCommands(self):
        self.sheet.set("A1", "1.5")
        self.sheet.set("A2", "2")
        self.doc.recompute()
        table = self._tableView()
        self._select(table, 0, 0, 1, 0)
        decimals = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Units").GetInt(
            "Decimals", 2
        )
        FreeCADGui.runCommand("Spreadsheet_IncreaseDecimals")
        self._process()
        self.assertEqual(self.sheet.getDecimals("A1"), decimals + 1)
        self.assertEqual(self.sheet.getDecimals("A2"), decimals + 1)
        FreeCADGui.runCommand("Spreadsheet_DecreaseDecimals")
        FreeCADGui.runCommand("Spreadsheet_DecreaseDecimals")
        self._process()
        self.assertEqual(self.sheet.getDecimals("A1"), max(decimals - 1, 0))
        # The display follows
        text = table.model().data(table.model().index(1, 0))
        self.assertEqual(text.count("0"), max(decimals - 1, 0))

    def testPasteFormattingAndClearFormat(self):
        self.sheet.set("A1", "1")
        self.sheet.setStyle("A1", "bold")
        self.sheet.setBorders("A1", "bottom")
        self.sheet.set("B3", "2")
        self.doc.recompute()
        table = self._tableView()
        self._select(table, 0, 0, 0, 0)
        self._action(table, "Copy").trigger()
        self._select(table, 2, 1, 2, 1)
        self._action(table, "Paste Formatting").trigger()
        self._process()
        self.assertEqual(self.sheet.getStyle("B3"), {"bold"})
        self.assertEqual(self.sheet.getBorders("B3"), {"bottom"})
        self.assertEqual(self.sheet.getContents("B3"), "2")
        FreeCADGui.runCommand("Spreadsheet_ClearFormat")
        self._process()
        self.assertIsNone(self.sheet.getStyle("B3"))
        self.assertIsNone(self.sheet.getBorders("B3"))
        self.assertEqual(self.sheet.getContents("B3"), "2")

    def testBordersCommands(self):
        table = self._tableView()
        self._select(table, 0, 0, 1, 1)
        FreeCADGui.runCommand("Spreadsheet_BordersOutside")
        self._process()
        self.assertEqual(self.sheet.getBorders("A1"), {"top", "left"})
        self.assertEqual(self.sheet.getBorders("B2"), {"bottom", "right"})
        FreeCADGui.runCommand("Spreadsheet_BordersAll")
        self._process()
        self.assertEqual(self.sheet.getBorders("A2"), {"top", "left", "bottom", "right"})
        # One undo step per command
        self.doc.undo()
        self.assertEqual(self.sheet.getBorders("A2"), {"left", "bottom"})
        FreeCADGui.runCommand("Spreadsheet_BordersNone")
        self._process()
        self.assertIsNone(self.sheet.getBorders("A1"))
        self.assertIsNone(self.sheet.getBorders("B2"))

    def _clickCell(self, table, row, col):
        """Click a cell through the graphics view that hosts the table, like a user."""
        try:
            from PySide6 import QtTest
        except ImportError:
            from PySide2 import QtTest
        rect = table.visualRect(table.model().index(row, col))
        point = table.viewport().mapTo(table, rect.center())
        proxy = table.graphicsProxyWidget()
        view = proxy.scene().views()[0]
        target = view.mapFromScene(proxy.mapToScene(QtCore.QPointF(point)))
        QtTest.QTest.mouseClick(
            view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, target
        )
        self._process()

    def testClickToReferenceInCellEditor(self):
        try:
            from PySide6 import QtTest
        except ImportError:
            from PySide2 import QtTest
        table = self._tableView()
        editor = self._editCell(table, 0, 0)
        QtTest.QTest.keyClicks(editor, "=2*")
        self._clickCell(table, 2, 2)
        self.assertEqual(editor.text(), "=2*C3")
        # A second click replaces the reference
        self._clickCell(table, 1, 1)
        self.assertEqual(editor.text(), "=2*B2")
        self.assertEqual(table.currentIndex().row(), 0)
        QtTest.QTest.keyClick(editor, QtCore.Qt.Key_Return)
        self._process()
        self.doc.recompute()
        self.assertEqual(self.sheet.getContents("A1"), "=2 * B2")

    def _editCell(self, table, row, col):
        index = table.model().index(row, col)
        table.setCurrentIndex(index)
        table.edit(index)
        self._process()
        # The cell editor embeds itself in the graphics scene: it is not a child of the table
        editor = table.indexWidget(index)
        self.assertIsInstance(editor, QtWidgets.QLineEdit, "no cell editor")
        return editor

    def testClickOutsideTheCellsEndsTheFormulaEdit(self):
        try:
            from PySide6 import QtTest
        except ImportError:
            from PySide2 import QtTest
        table = self._tableView()
        editor = self._editCell(table, 0, 0)
        QtTest.QTest.keyClicks(editor, "=2*")
        self._clickCell(table, 2, 2)
        self.assertEqual(editor.text(), "=2*C3")
        # A click on the header of the edited row inserts no reference and does not move
        # the current cell: the edit ends as after any other click, it is not left open
        header = table.verticalHeader()
        y = header.sectionViewportPosition(0) + header.sectionSize(0) // 2
        point = header.viewport().mapTo(table, QtCore.QPoint(header.width() // 2, y))
        proxy = table.graphicsProxyWidget()
        view = proxy.scene().views()[0]
        target = view.mapFromScene(proxy.mapToScene(QtCore.QPointF(point)))
        QtTest.QTest.mouseClick(view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, target)
        self._process()
        self.assertIsNone(table.indexWidget(table.model().index(0, 0)))
        self.doc.recompute()
        self.assertEqual(self.sheet.getContents("A1"), "=2 * C3")

    def testClickToReferenceInFormulaBar(self):
        try:
            from PySide6 import QtTest
        except ImportError:
            from PySide2 import QtTest
        table = self._tableView()
        table.setCurrentIndex(table.model().index(0, 0))
        self._process()
        bar = None
        for widget in QtWidgets.QApplication.allWidgets():
            if widget.objectName() == "cellContent" and widget.isVisible():
                bar = widget
        self.assertIsNotNone(bar, "no formula bar")
        self.sheet.set("B2", "3")
        self.sheet.setAlias("B2", "width")
        self.doc.recompute()
        bar.setFocus()
        QtTest.QTest.keyClicks(bar, "=1+")
        # A cell with an alias is referenced by its alias
        self._clickCell(table, 1, 1)
        self.assertEqual(bar.text(), "=1+width")
        self.assertEqual(table.currentIndex().row(), 0)
        QtTest.QTest.keyClick(bar, QtCore.Qt.Key_Return)
        self._process()
        self.doc.recompute()
        self.assertEqual(self.sheet.getContents("A1"), "=1 + width")
        self.assertEqual(self.sheet.A1, 4)
        # Not after an operator: a click moves the selection as usual
        self._clickCell(table, 2, 2)
        self.assertEqual((table.currentIndex().row(), table.currentIndex().column()), (2, 2))

    def testAlternatingRowColorsPreference(self):
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Spreadsheet")
        had = param.GetBool("AlternatingRowColors", False)
        self.addCleanup(param.SetBool, "AlternatingRowColors", had)
        param.SetBool("AlternatingRowColors", True)
        table = self._tableView()
        self.assertTrue(table.alternatingRowColors())


if __name__ == "__main__":
    unittest.main()
