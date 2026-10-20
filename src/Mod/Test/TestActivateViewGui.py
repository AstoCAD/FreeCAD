# SPDX-License-Identifier: LGPL-2.1-or-later
"""Activate existing document views while a macro editor is the current window."""

from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    from PySide import QtCore, QtWidgets


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestActivateViewFromMacro30415(unittest.TestCase):
    def setUp(self):
        self.initial_documents = set(App.listDocuments())
        self.previous = App.activeDocument().Name if App.activeDocument() else None
        self.directory = TemporaryDirectory(prefix="FreeCAD30415-")
        self.editor = None
        self.main = Gui.getMainWindow()
        self.doc = App.newDocument("ActivateFromMacro30415")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length, self.box.Width, self.box.Height = 13, 7, 11
        self.doc.recompute()
        self.assertTrue(self.box.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 1001)
        self.view = Gui.getDocument(self.doc.Name).activeView()
        self.assertEqual(self.view.getTypeId(), "Gui::View3DInventor")
        self.assertTrue(self._wait(lambda: self.main.getActiveWindow() == self.view))
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertEqual(Gui.activeDocument().Document, self.doc)

    def tearDown(self):
        try:
            if self.editor is not None:
                owned_editor = self.editor
                self.assertIn(owned_editor, self.main.getWindows())
                self.main.setActiveWindow(owned_editor)
                self.assertEqual(self.main.getActiveWindow(), owned_editor)
                Gui.runCommand("Std_CloseActiveWindow", 0)
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

                def editor_destroyed():
                    try:
                        repr(owned_editor)
                    except RuntimeError:
                        return True
                    return False

                self.assertTrue(self._wait(editor_destroyed),
                                "The owned macro editor must be destroyed before its file is removed")
                self.editor = None
            for name in list(App.listDocuments()):
                if name not in self.initial_documents:
                    App.closeDocument(name)
            if self.previous in App.listDocuments():
                App.setActiveDocument(self.previous)
        finally:
            self.directory.cleanup()

    def _wait(self, condition, timeout=2.0):
        deadline = monotonic() + timeout
        while not condition() and monotonic() < deadline:
            QtWidgets.QApplication.processEvents()
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(10, loop.quit)
            loop.exec_()
        return bool(condition())

    def _open_macro(self):
        path = Path(self.directory.name) / "activate_view.FCMacro"
        path.write_text("# macro editor activation control" + chr(10), encoding="utf-8")
        Gui.open(str(path))
        self.assertTrue(self._wait(lambda: self.main.getActiveWindow() is not None
                                  and "EditorView" in self.main.getActiveWindow().getTypeId()))
        self.editor = self.main.getActiveWindow()
        self.assertIn("EditorView", self.editor.getTypeId())
        self.assertNotEqual(self.editor, self.view)
        self.assertEqual(path.read_text(encoding="utf-8"),
                         "# macro editor activation control" + chr(10))
        return path

    def _assert_active_3d(self):
        active = self.main.getActiveWindow()
        self.assertIsNotNone(active)
        self.assertEqual(active.getTypeId(), "Gui::View3DInventor",
                         "Gui.activateView must activate the document 3D window")
        self.assertEqual(active, self.view,
                         "The existing 3D view must be reused instead of opening another one")
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertEqual(Gui.activeDocument().Document, self.doc)
        self.assertTrue(self.box.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 1001)

    def test_already_active_3d_control(self):
        Gui.activateView("Gui::View3DInventor", False)
        self._assert_active_3d()

    def test_macro_same_document_activate_existing_view(self):
        self._open_macro()
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertEqual(Gui.activeDocument().Document, self.doc)
        Gui.activateView("Gui::View3DInventor", False)
        self._wait(lambda: self.main.getActiveWindow() == self.view)
        self._assert_active_3d()

    def test_macro_same_document_activate_view_with_create_enabled(self):
        self._open_macro()
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertEqual(Gui.activeDocument().Document, self.doc)
        Gui.activateView("Gui::View3DInventor", True)
        self._wait(lambda: self.main.getActiveWindow() == self.view)
        self._assert_active_3d()

    def test_macro_other_document_activation_control(self):
        other = App.newDocument("OtherActivation30415")
        other_box = other.addObject("Part::Box", "OtherBox")
        other_box.Length, other_box.Width, other_box.Height = 3, 5, 7
        other.recompute()
        self.assertTrue(other_box.Shape.isValid())
        self.assertAlmostEqual(other_box.Shape.Volume, 105)
        self.assertEqual(App.activeDocument(), other)
        self._open_macro()
        self.assertEqual(App.activeDocument(), other)
        Gui.setActiveDocument(self.doc.Name)
        Gui.activateView("Gui::View3DInventor", False)
        self._wait(lambda: self.main.getActiveWindow() == self.view)
        self._assert_active_3d()


if __name__ == "__main__":
    unittest.main()
