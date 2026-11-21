# SPDX-License-Identifier: LGPL-2.1-or-later

"""The "Reset section line" button of the Section View edit task.

The edit task hides the existing section view and its cutting line while its
own preview replaces them. "Reset section line" dropped the base view item
without showing them again, so Cancel left the section invisible on the page.
Without the page view, Reset and the position modes cleared the base view with
no way to pick a new line.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawSectionResetCancelGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDSectionResetCancel")
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
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
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

    def _scene(self):
        view = Gui.getMainWindow().findChild(QtWidgets.QGraphicsView, self.page.Name + "View")
        return view.scene() if view is not None else None

    def _section_items(self):
        scene = self._scene()
        if scene is None:
            return []
        name = self.section.Name
        return [
            item
            for item in scene.items()
            if (item.data(0) == "QGIV" and item.data(1) == name) or item.data(10) == name
        ]

    def _section_shown(self):
        items = self._section_items()
        return len(items) >= 2 and all(item.isVisible() for item in items)

    def test_cancel_after_reset_shows_section_again(self):
        self.assertTrue(
            self._wait(self._section_shown), "The section view and its cutting line are not shown"
        )
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self._pump(300)
        self.assertFalse(self._section_shown(), "The task preview replaces the section")

        reset = Gui.getMainWindow().findChild(QtWidgets.QPushButton, "pbResetSectionLine")
        self.assertIsNotNone(reset, "No reset button")
        reset.click()
        self._pump(300)
        Gui.Control.activeTaskDialog().reject()
        self.assertTrue(
            self._wait(lambda: not Gui.Control.activeDialog()), "The task did not close"
        )
        self._pump(300)

        self.assertTrue(
            self._section_shown(), "Cancel must show the section view and its cutting line again"
        )

    def test_no_line_controls_without_page_view(self):
        # Without the page view no new line can be picked: Reset and the position
        # modes would only clear the base view and leave a task that cannot be accepted.
        self.page.ViewObject.hide()
        self._pump(300)
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self._pump(300)
        window = Gui.getMainWindow()
        reset = window.findChild(QtWidgets.QPushButton, "pbResetSectionLine")
        modes = window.findChild(QtWidgets.QWidget, "sectionLinePositionButtons")
        self.assertIsNotNone(reset, "No reset button")
        self.assertIsNotNone(modes, "No position mode buttons")
        self.assertTrue(reset.isHidden(), "Reset section line needs the page view")
        self.assertTrue(modes.isHidden(), "The position modes need the page view")


if __name__ == "__main__":
    unittest.main()
