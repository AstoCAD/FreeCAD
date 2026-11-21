# SPDX-License-Identifier: LGPL-2.1-or-later

"""OK and Cancel of the projection group task after it changed the kind of view.

Ticking a secondary projection in the task turns a single view into a projection
group, and unticking the last one turns the group back into a single view. Cancel
then must undo everything done in the task without using the objects the undo
deletes, and OK and Cancel must close the transaction of the task even when the
object the task was opened on has been replaced.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")
FRONT_BOX = "chkView4"
SECONDARY_BOX = "chkView5"  # Right or Left, depending on the projection convention


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawProjGroupTaskCancelGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDProjGroupTaskCancel")
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

    def _view_box(self, name):
        boxes = [box for box in Gui.getMainWindow().findChildren(QtWidgets.QCheckBox, name)
                 if box.isVisible()]
        self.assertEqual(len(boxes), 1, f"The task has no visible {name} check box")
        return boxes[0]

    def _toggle(self, name):
        self._view_box(name).click()
        self._pump(300)

    def _groups(self):
        return [obj.Name for obj in self.doc.Objects if obj.isDerivedFrom("TechDraw::DrawProjGroup")]

    def _close(self, button):
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        getattr(dialog, button)()
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()),
                        "The task did not close")
        self._pump(300)

    def _edit_single_view(self):
        self.doc.openTransaction("Create view")
        view = self.doc.addObject("TechDraw::DrawProjGroupItem", "View")
        self.page.addView(view)
        view.Source = [self.box]
        view.Direction = App.Vector(0, -1, 0)
        self.doc.commitTransaction()
        self.doc.recompute()
        self._pump(1000)
        Gui.ActiveDocument.setEdit(view.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self._pump(300)
        return view

    def test_cancel_after_making_group_from_edited_view(self):
        view = self._edit_single_view()
        name = view.Name
        self._toggle(SECONDARY_BOX)
        self.assertEqual(len(self._groups()), 1, "Ticking a projection must make a group")

        self._close("reject")

        self.assertEqual(self._groups(), [], "Cancel must remove the group made by the task")
        view = self.doc.getObject(name)
        self.assertIsNotNone(view)
        self.assertIn(view, self.page.Views, "Cancel must put the view back on the page")
        self.assertFalse(self.doc.HasPendingTransaction)

    def _create_group_then_reduce_to_view(self):
        names = {obj.Name for obj in self.doc.Objects}
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.box.Name)
        Gui.runCommand("TechDraw_ProjectionGroup")
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The creation task did not open")
        self._pump(300)
        self.assertTrue(self._view_box(FRONT_BOX).isChecked())
        self._toggle(SECONDARY_BOX)
        self._toggle(SECONDARY_BOX)
        self.assertEqual(self._groups(), [],
                         "Unticking the last projection must turn the group into a view")
        return names

    def test_cancel_after_reducing_created_group_to_view(self):
        names = self._create_group_then_reduce_to_view()

        self._close("reject")

        self.assertEqual([obj.Name for obj in self.doc.Objects if obj.Name not in names], [],
                         "Cancel must remove everything the creation task made")
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_ok_after_reducing_created_group_to_view(self):
        names = self._create_group_then_reduce_to_view()

        self._close("accept")

        created = [obj for obj in self.doc.Objects if obj.Name not in names]
        self.assertEqual(len(created), 1, "OK must keep the remaining view")
        self.assertIn(created[0], self.page.Views)
        self.assertFalse(self.doc.HasPendingTransaction,
                         "OK must close the transaction of the task")
        self.doc.undo()
        self.assertEqual([obj.Name for obj in self.doc.Objects if obj.Name not in names], [],
                         "Undo after OK must remove the created view")
