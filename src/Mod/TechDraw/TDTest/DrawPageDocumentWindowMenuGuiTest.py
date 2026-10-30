# SPDX-License-Identifier: LGPL-2.1-or-later
"""The page view context menu offers the "Document window" submenu.

https://github.com/FreeCAD/FreeCAD/issues/29276
"""

from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets


def documentWindowSubmenu(menu):
    """Return the submenu of menu holding the Std_ViewDockUndockFullscreen actions"""
    expected = [a.text() for a in Gui.Command.get("Std_ViewDockUndockFullscreen").getAction()]
    for action in menu.actions():
        sub = action.menu()
        if sub and [a.text() for a in sub.actions()] == expected:
            return sub
    return None


class DrawPageDocumentWindowMenuGuiTest(unittest.TestCase):
    def setUp(self):
        wb = Gui.activeWorkbench()
        self.previous_workbench = wb.name() if wb else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("PageDocumentWindow_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.addCleanup(self._cleanup)
        temporary = tempfile.TemporaryDirectory(prefix="asto-document-window-")
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "template.svg"
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="80mm" viewBox="0 0 100 80"></svg>\n',
            encoding="utf-8",
        )
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(path)
        self.page.Template = template
        self.doc.recompute()

    def _cleanup(self):
        if self.doc_name in App.listDocuments():
            App.closeDocument(self.doc_name)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _pageView(self):
        self.page.ViewObject.doubleClicked()
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            for widget in QtWidgets.QApplication.allWidgets():
                if widget.metaObject().className() == "TechDrawGui::MDIViewPage":
                    return widget
        self.fail("the page view was not opened")

    def testContextMenuHasDocumentWindowSubmenu(self):
        view = self._pageView()
        found = []

        def inspect():
            menu = QtWidgets.QApplication.activePopupWidget()
            try:
                if menu:
                    found.append(documentWindowSubmenu(menu) is not None)
            finally:
                if menu:
                    menu.close()

        QtCore.QTimer.singleShot(100, inspect)
        pos = view.rect().center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, pos, view.mapToGlobal(pos)
        )
        QtWidgets.QApplication.sendEvent(view, event)
        self.assertEqual(found, [True])


if __name__ == "__main__":
    unittest.main()
