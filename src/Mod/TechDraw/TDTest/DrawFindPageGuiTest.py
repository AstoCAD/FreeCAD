# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDrawGui.findPage() finds the page to work on, as the TechDraw commands do.

https://github.com/FreeCAD/FreeCAD/issues/19469
"""

from pathlib import Path
import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets


@unittest.skipUnless("TechDrawWorkbench" in Gui.listWorkbenches(), "TechDraw is unavailable")
class DrawFindPageGuiTest(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.doc_name = None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("FindPage_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.pages = []

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.closeDocument(self.doc_name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _addPages(self, count):
        template_path = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(template_path.is_file())
        for index in range(count):
            page = self.doc.addObject("TechDraw::DrawPage", "Page%d" % index)
            template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template%d" % index)
            template.Template = str(template_path)
            page.Template = template
            self.pages.append(page)
        self.doc.recompute()

    def _findPageWithChooser(self, chosen):
        """Calls findPage() and answers the page chooser with the chosen page (None: cancel)"""
        application = QtWidgets.QApplication.instance()
        state = {"rows": None, "tries": 0}

        def answer():
            dialog = application.activeModalWidget()
            listing = dialog.findChild(QtWidgets.QListWidget, "lwPages") if dialog else None
            if listing is None:
                state["tries"] += 1
                if state["tries"] < 100:
                    QtCore.QTimer.singleShot(50, answer)
                elif dialog is not None:
                    # never leave an unexpected modal dialog open
                    dialog.reject()
                return
            items = [listing.item(index) for index in range(listing.count())]
            state["rows"] = sorted(item.data(QtCore.Qt.UserRole) for item in items)
            if chosen is None:
                dialog.reject()
                return
            matches = [item for item in items if item.data(QtCore.Qt.UserRole) == chosen.Name]
            if not matches:
                # accepting without a selection would open a modal message box
                dialog.reject()
                return
            listing.setCurrentItem(matches[0])
            matches[0].setSelected(True)
            dialog.accept()

        QtCore.QTimer.singleShot(0, answer)
        import TechDrawGui

        page = TechDrawGui.findPage(self.doc)
        self.assertEqual(state["rows"], sorted(page.Name for page in self.pages))
        return page

    def test_only_page(self):
        self._addPages(1)
        import TechDrawGui

        self.assertEqual(TechDrawGui.findPage(self.doc), self.pages[0])
        # the active document is the default
        App.setActiveDocument(self.doc_name)
        self.assertEqual(TechDrawGui.findPage(), self.pages[0])

    def test_selected_page(self):
        self._addPages(2)
        import TechDrawGui

        Gui.Selection.addSelection(self.pages[1])
        self.assertEqual(TechDrawGui.findPage(self.doc), self.pages[1])

    def test_active_page_view(self):
        self._addPages(2)
        import TechDrawGui

        self.pages[1].ViewObject.doubleClicked()
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
        self.assertEqual(Gui.activeView().getPage().Name, self.pages[1].Name)
        self.assertEqual(TechDrawGui.findPage(self.doc), self.pages[1])

    def test_page_chooser(self):
        self._addPages(2)
        self.assertEqual(self._findPageWithChooser(self.pages[1]), self.pages[1])

    def test_page_chooser_cancelled(self):
        self._addPages(2)
        self.assertIsNone(self._findPageWithChooser(None))

    def test_bad_argument(self):
        import TechDrawGui

        with self.assertRaises(TypeError):
            TechDrawGui.findPage("not a document")


if __name__ == "__main__":
    unittest.main()
