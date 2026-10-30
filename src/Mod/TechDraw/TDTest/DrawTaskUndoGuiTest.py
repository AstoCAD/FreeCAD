# SPDX-License-Identifier: LGPL-2.1-or-later

"""Undo while a TechDraw task is open.

TechDraw_View and TechDraw_ProjectionGroup create their objects in an open
transaction and then show the projection group task. Std_Undo removes these
objects, but the task kept raw pointers to them: any later click in the task
(e.g. a projection check box) crashed FreeCAD. Likewise, undoing the creation
of a section view while editing it left a task whose OK and Cancel crashed.
These tasks must close on undo.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawTaskUndoGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDViewCreateUndo")
        self.doc.UndoMode = 1
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self._pump(200)
        self.doc.clearUndos()

    def tearDown(self):
        Gui.Selection.clearSelection()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
            self._pump(100)
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        self._pump(100)
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

    def _create_then_undo(self, command):
        names = {obj.Name for obj in self.doc.Objects}
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.box.Name)
        Gui.runCommand(command)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The creation task did not open")
        created = [obj.Name for obj in self.doc.Objects if obj.Name not in names]
        self.assertTrue(created, "The command did not create a view")
        self._pump(300)

        Gui.runCommand("Std_Undo")
        self._pump(300)

        self.assertEqual([obj.Name for obj in self.doc.Objects if obj.Name not in names], [],
                         "Undo must remove the views created by the task")
        self.assertFalse(Gui.Control.activeDialog(),
                         "The task must close when undo removes the view it edits")

    def test_undo_closes_view_task(self):
        self._create_then_undo("TechDraw_View")

    def test_undo_closes_projection_group_task(self):
        self._create_then_undo("TechDraw_ProjectionGroup")


if __name__ == "__main__":
    unittest.main()
