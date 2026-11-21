# SPDX-License-Identifier: LGPL-2.1-or-later

"""Closing the page tab while the Section View task is open.

The task kept a raw pointer to the page's graphics view, which is destroyed
with the page tab, while the page's scene lives on. OK or Cancel then used the
freed view, and the face selection it suppressed on the scene was never
restored. The task must survive the closed tab and restore the scene.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")
SUPPRESS_FACE_SELECTION = "TechDrawSuppressFaceSelection"


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawSectionPageClosedGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDSectionPageClosed")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.base = self.doc.addObject("TechDraw::DrawViewPart", "BaseView")
        self.page.addView(self.base)
        self.base.Source = [self.box]
        self.base.Direction = App.Vector(0, 0, 1)
        self.base.X, self.base.Y = 80, 100
        # The name TechDraw_SectionView gives; the task derives the label from it.
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "SectionView")
        self.page.addView(self.section)
        self.section.BaseView = self.base
        self.section.Source = [self.box]
        self.section.SectionNormal = App.Vector(0, -1, 0)
        self.section.SectionOrigin = App.Vector(5, 5, 5)
        self.section.Direction = App.Vector(0, -1, 0)
        self.section.X, self.section.Y = 200, 100
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(lambda: len(self.base.getVisibleEdges()) >= 4),
            "The base view was not projected",
        )

    def tearDown(self):
        Gui.Selection.clearSelection()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
            self._pump(100)
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        self._pump(100)
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    @staticmethod
    def _pump(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                return False
            self._pump()
        return True

    def _page_view(self):
        return Gui.getMainWindow().findChild(
            QtWidgets.QGraphicsView, self.page.Name + "View"
        )

    def _edit_then_close_page_tab(self):
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self._pump(300)
        view = self._page_view()
        self.assertIsNotNone(view, "The page is not shown")
        scene = view.scene()
        self.assertTrue(
            scene.property(SUPPRESS_FACE_SELECTION),
            "The task works on the shown page and suppresses face selection there",
        )

        self.page.ViewObject.hide()
        self.assertTrue(
            self._wait(lambda: self._page_view() is None),
            "Closing the page tab must destroy its graphics view",
        )
        self.assertTrue(Gui.Control.activeDialog(), "The task stays open")
        return scene

    def _assert_closed_and_restored(self, scene):
        self.assertTrue(
            self._wait(lambda: not Gui.Control.activeDialog()), "The task did not close"
        )
        self.assertFalse(
            scene.property(SUPPRESS_FACE_SELECTION),
            "Closing the task must restore face selection on the page",
        )
        self.page.ViewObject.show()
        self.assertTrue(self._wait(lambda: self._page_view() is not None), "The page reopens")
        self.assertFalse(self._page_view().scene().property(SUPPRESS_FACE_SELECTION))

    def test_cancel_after_closing_page_tab(self):
        scene = self._edit_then_close_page_tab()
        Gui.Control.activeTaskDialog().reject()
        self._assert_closed_and_restored(scene)
        self.assertIsNotNone(self.doc.getObject(self.section.Name))

    def test_ok_after_closing_page_tab(self):
        scene = self._edit_then_close_page_tab()
        Gui.Control.activeTaskDialog().accept()
        self._assert_closed_and_restored(scene)
        self.assertIsNotNone(self.doc.getObject(self.section.Name))


if __name__ == "__main__":
    unittest.main()
