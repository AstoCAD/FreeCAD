# SPDX-License-Identifier: LGPL-2.1-or-later
"""The spreadsheet view context menu offers the "Document window" submenu.

https://github.com/FreeCAD/FreeCAD/issues/29276

Its Fill Down and Fill Right entries are commands with shortcuts the user can change.
"""

import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtGui, QtWidgets


@unittest.skipUnless(FreeCAD.GuiUp, "Requires FreeCAD GUI mode")
class TestSpreadsheetContextMenuGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("SheetDocumentWindow")
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        self.doc.recompute()

    def _cleanup(self):
        if self.doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc_name)

    def _tableView(self):
        self.sheet.ViewObject.doubleClicked()
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            # the table sits in a graphics proxy, it is not a child of the main window
            for widget in QtWidgets.QApplication.allWidgets():
                if widget.metaObject().className() == "SpreadsheetGui::SheetTableView":
                    return widget
        self.fail("the spreadsheet view was not opened")

    def testContextMenuHasDocumentWindowSubmenu(self):
        table = self._tableView()
        cmd = FreeCADGui.Command.get("Std_ViewDockUndockFullscreen")
        # the submenu title is the translated menu text of the command
        title = QtCore.QCoreApplication.translate(
            "StdViewDockUndockFullscreen", cmd.getInfo()["menuText"]
        )
        found = []
        errors = []

        def inspect():
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                found.append(
                    bool(menu)
                    and any(a.text() == title and a.menu() is not None for a in menu.actions())
                )
            except Exception as exc:
                errors.append(repr(exc))
            finally:
                if menu:
                    menu.close()

        QtCore.QTimer.singleShot(100, inspect)
        viewport = table.viewport()
        pos = viewport.rect().center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, pos, viewport.mapToGlobal(pos)
        )
        QtWidgets.QApplication.sendEvent(viewport, event)
        for _ in range(100):
            if found or errors:
                break
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents, 20)
        self.assertFalse(errors, errors)
        self.assertEqual(found, [True])

    def _process(self, count=20):
        for _ in range(count):
            QtWidgets.QApplication.processEvents()

    def _select(self, table, top, left, bottom, right):
        model = table.model()
        selection = QtCore.QItemSelection(model.index(top, left), model.index(bottom, right))
        table.selectionModel().select(selection, QtCore.QItemSelectionModel.ClearAndSelect)
        table.selectionModel().setCurrentIndex(
            model.index(top, left), QtCore.QItemSelectionModel.NoUpdate
        )
        self._process()

    def _claimsKey(self, table, key, modifiers):
        """Whether the cells take the key before the application shortcuts."""
        event = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, key, modifiers)
        event.ignore()
        QtWidgets.QApplication.sendEvent(table, event)
        return event.isAccepted()

    def testFillDownAndFillRightCommands(self):
        for row in range(1, 4):
            self.sheet.set(f"B{row}", str(row))
        self.sheet.set("A1", "=B1*2")
        self.sheet.set("C1", "x")
        self.doc.recompute()
        table = self._tableView()
        self._select(table, 0, 0, 2, 0)
        FreeCADGui.runCommand("Spreadsheet_FillDown")
        self._process()
        self.doc.recompute()
        self.assertEqual(self.sheet.getContents("A3"), "=B3 * 2")
        self.assertEqual(self.sheet.A3, 6)
        self._select(table, 0, 2, 0, 3)
        FreeCADGui.runCommand("Spreadsheet_FillRight")
        self._process()
        self.assertEqual(self.sheet.getContents("D1"), "'x")

    def testFillShortcutsCanBeChanged(self):
        fill_down = FreeCADGui.Command.get("Spreadsheet_FillDown")
        fill_right = FreeCADGui.Command.get("Spreadsheet_FillRight")
        self.addCleanup(fill_down.resetShortcut)
        self.addCleanup(fill_right.resetShortcut)
        table = self._tableView()
        table.setFocus()
        self._process()
        ctrl = QtCore.Qt.ControlModifier
        self.assertEqual(fill_down.getShortcut(), "Ctrl+D")
        self.assertEqual(fill_right.getShortcut(), "Ctrl+R")
        # The cells take the keys of their commands before the application
        # shortcuts bound to the same keys (Std_SetAppearance has Ctrl+D)
        self.assertTrue(self._claimsKey(table, QtCore.Qt.Key_D, ctrl))
        self.assertTrue(self._claimsKey(table, QtCore.Qt.Key_R, ctrl))
        # ... and follow the shortcuts the user gives the commands
        fill_down.setShortcut("Ctrl+Shift+D")
        fill_right.setShortcut("")
        self._process()
        self.assertFalse(self._claimsKey(table, QtCore.Qt.Key_D, ctrl))
        self.assertFalse(self._claimsKey(table, QtCore.Qt.Key_R, ctrl))
        self.assertTrue(self._claimsKey(table, QtCore.Qt.Key_D, ctrl | QtCore.Qt.ShiftModifier))


if __name__ == "__main__":
    unittest.main()
