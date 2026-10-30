# SPDX-License-Identifier: LGPL-2.1-or-later
"""The spreadsheet view context menu offers the "Document window" submenu.

https://github.com/FreeCAD/FreeCAD/issues/29276
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


if __name__ == "__main__":
    unittest.main()
