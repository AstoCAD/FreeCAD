# SPDX-License-Identifier: LGPL-2.1-or-later

"""Leader line options in the Leader Line task panel.

AutoHorizontal, Scalable and RotatesWithParent were only reachable through the
property view (and the AutoHorizontal preference through the parameter editor).
The task panel now has a check box for each of them
(https://github.com/FreeCAD/FreeCAD/issues/26448).
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")
OPTIONS = {
    "cbAutoHorizontal": "AutoHorizontal",
    "cbScalable": "Scalable",
    "cbRotatesWithParent": "RotatesWithParent",
}


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawLeaderOptionsGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDLeaderOptions")
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
        self.leader = self.doc.addObject("TechDraw::DrawLeaderLine", "Leader")
        self.page.addView(self.leader)
        self.leader.LeaderParent = self.base
        self.leader.WayPoints = [App.Vector(0, 0, 0), App.Vector(20, 20, 0)]
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(lambda: len(self.base.getVisibleEdges()) >= 4),
            "The base view was not projected",
        )
        self._pump(300)

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

    @staticmethod
    def _check_boxes():
        window = Gui.getMainWindow()
        boxes = {name: window.findChild(QtWidgets.QCheckBox, name) for name in OPTIONS}
        if any(box is None for box in boxes.values()):
            return None
        return boxes

    def _open_edit(self):
        Gui.ActiveDocument.setEdit(self.leader.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self.assertTrue(self._wait(lambda: self._check_boxes() is not None),
                        "The leader task panel has no option check boxes")
        self._pump(200)
        return self._check_boxes()

    def _set_leader(self, values):
        for prop, value in values.items():
            setattr(self.leader, prop, value)
        self.doc.recompute()

    def test_edit_panel_shows_the_leader_options(self):
        for values in (
            {"AutoHorizontal": False, "Scalable": True, "RotatesWithParent": False},
            {"AutoHorizontal": True, "Scalable": False, "RotatesWithParent": True},
        ):
            with self.subTest(values=values):
                self._set_leader(values)
                boxes = self._open_edit()
                for name, prop in OPTIONS.items():
                    self.assertEqual(boxes[name].isChecked(), values[prop], name)
                Gui.Control.activeTaskDialog().reject()
                self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()),
                                "The edit task did not close")
                self._pump(200)

    def test_ok_applies_the_options(self):
        self._set_leader({"AutoHorizontal": False, "Scalable": False, "RotatesWithParent": True})
        boxes = self._open_edit()
        boxes["cbAutoHorizontal"].setChecked(True)
        boxes["cbScalable"].setChecked(True)
        boxes["cbRotatesWithParent"].setChecked(False)
        Gui.Control.activeTaskDialog().accept()
        self._pump(300)
        self.assertTrue(self.leader.AutoHorizontal)
        self.assertTrue(self.leader.Scalable)
        self.assertFalse(self.leader.RotatesWithParent)

    def test_cancel_keeps_the_options(self):
        values = {"AutoHorizontal": False, "Scalable": False, "RotatesWithParent": True}
        self._set_leader(values)
        boxes = self._open_edit()
        for box in boxes.values():
            box.setChecked(not box.isChecked())
        Gui.Control.activeTaskDialog().reject()
        self._pump(300)
        for prop, value in values.items():
            self.assertEqual(getattr(self.leader, prop), value, prop)

    def test_create_panel_uses_the_property_defaults(self):
        auto = App.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/TechDraw/LeaderLine"
        ).GetBool("AutoHorizontal", True)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.base.Name)
        Gui.runCommand("TechDraw_LeaderLine")
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The creation task did not open")
        self.assertTrue(self._wait(lambda: self._check_boxes() is not None),
                        "The leader task panel has no option check boxes")
        boxes = self._check_boxes()
        self.assertEqual(boxes["cbAutoHorizontal"].isChecked(), auto)
        self.assertFalse(boxes["cbScalable"].isChecked())
        self.assertTrue(boxes["cbRotatesWithParent"].isChecked())
        Gui.Control.activeTaskDialog().reject()
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()),
                        "The creation task did not close")


if __name__ == "__main__":
    unittest.main()
