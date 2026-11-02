# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for Std_IsolateSelection and Std_EndIsolation.

Isolation works on any document, not only in an assembly
(https://github.com/FreeCAD/FreeCAD/issues/12142).
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


def _wait(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


@unittest.skipUnless(App.GuiUp, "requires GUI")
class TestIsolationGui(unittest.TestCase):
    def setUp(self):
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.tmp = tempfile.mkdtemp()
        self.doc = App.newDocument("IsolationTest")
        self.boxes = []
        for i in range(3):
            box = self.doc.addObject("Part::Box", "Box%d" % i)
            box.Placement.Base = App.Vector(20 * i, 0, 0)
            self.boxes.append(box)
        self.doc.recompute()
        self.gui_doc = Gui.getDocument(self.doc.Name)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        Gui.Selection.clearSelection()
        for name in list(App.listDocuments()):
            if name.startswith("IsolationTest"):
                App.closeDocument(name)
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    def _selectable(self):
        return [bool(box.ViewObject.Selectable) for box in self.boxes]

    def _isolate(self, obj, sub=""):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, obj.Name, sub)
        Gui.runCommand("Std_IsolateSelection")

    def test_isolates_plain_objects(self):
        self._isolate(self.boxes[1], "Face1")
        self.assertEqual(self._selectable(), [False, True, False])
        self.assertTrue(Gui.Command.get("Std_EndIsolation").isActive())

        Gui.runCommand("Std_EndIsolation")
        self.assertEqual(self._selectable(), [True, True, True])
        self.assertFalse(Gui.Command.get("Std_EndIsolation").isActive())

    def test_keeps_previous_selectability(self):
        self.boxes[2].ViewObject.Selectable = False
        self._isolate(self.boxes[0])
        Gui.runCommand("Std_EndIsolation")
        self.assertEqual(self._selectable(), [True, True, False])

    def test_isolating_a_container_keeps_its_children(self):
        part = self.doc.addObject("App::Part", "Part")
        part.addObject(self.boxes[0])
        part.addObject(self.boxes[1])
        self.doc.recompute()
        self._isolate(part)
        self.assertEqual(self._selectable(), [True, True, False])
        Gui.runCommand("Std_EndIsolation")

        # A child picked through its container keeps only itself
        self._isolate(part, "Box1.Face1")
        self.assertEqual(self._selectable(), [False, True, False])
        Gui.runCommand("Std_EndIsolation")

    def test_isolating_a_link_keeps_the_link(self):
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = self.boxes[2]
        link.Placement.Base = App.Vector(0, 40, 0)
        self.doc.recompute()
        self._isolate(link, "Face1")
        self.assertTrue(link.ViewObject.Selectable)
        self.assertEqual(self._selectable(), [False, False, True])
        Gui.runCommand("Std_EndIsolation")
        self.assertTrue(link.ViewObject.Selectable)

    def test_does_not_modify_the_document(self):
        # The App save leaves the view providers' pending changes: start from a clean state
        self.gui_doc.Modified = False
        self._isolate(self.boxes[0])
        self.assertFalse(self.gui_doc.Modified)
        Gui.runCommand("Std_EndIsolation")
        self.assertFalse(self.gui_doc.Modified)

    def test_saving_keeps_the_isolation_out_of_the_file(self):
        path = os.path.join(self.tmp, "isolation.FCStd")
        self.doc.saveAs(path)
        self._isolate(self.boxes[0])
        self.doc.save()
        # The isolation goes on after the save
        self.assertEqual(self._selectable(), [True, False, False])

        copy = os.path.join(self.tmp, "copy.FCStd")
        shutil.copy(path, copy)
        other = App.openDocument(copy)
        try:
            for name in ("Box0", "Box1", "Box2"):
                self.assertTrue(other.getObject(name).ViewObject.Selectable, name)
        finally:
            App.closeDocument(other.Name)
        Gui.runCommand("Std_EndIsolation")

    def test_deleting_and_closing_during_isolation(self):
        self._isolate(self.boxes[0])
        self.doc.removeObject(self.boxes[1].Name)
        del self.boxes[1]
        Gui.runCommand("Std_EndIsolation")
        self.assertEqual(self._selectable(), [True, True])

        self._isolate(self.boxes[0])
        App.closeDocument(self.doc.Name)
        if App.ActiveDocument:
            self.assertFalse(Gui.Command.get("Std_EndIsolation").isActive())

    def test_task_box_ends_isolation(self):
        def shown(widget):
            while widget is not None and not isinstance(widget, QtWidgets.QStackedWidget):
                if widget.isHidden():
                    return False
                widget = widget.parentWidget()
            return True

        def end_buttons():
            return [
                button
                for button in Gui.getMainWindow().findChildren(QtWidgets.QToolButton)
                if button.defaultAction()
                and button.defaultAction().objectName() == "Std_EndIsolation"
                and shown(button)
            ]

        self.assertEqual(end_buttons(), [])
        self._isolate(self.boxes[0])
        buttons = end_buttons()
        self.assertEqual(len(buttons), 1)

        # Let the main window's action update enable the command, as it does for a user
        _wait(400)
        self.assertTrue(buttons[0].defaultAction().isEnabled())
        buttons[0].click()
        self.assertEqual(self._selectable(), [True, True, True])
        self.assertEqual(end_buttons(), [])
