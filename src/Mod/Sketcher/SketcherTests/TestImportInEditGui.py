# SPDX-License-Identifier: LGPL-2.1-or-later
"""File > Import stays available while a sketch is edited: its task dialog takes SVG files."""

import FreeCAD
from PySide import QtGui

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase


class _Panel:
    """A task panel that, like most, takes no import."""

    def __init__(self):
        self.form = QtGui.QWidget()


class TestImportInEditGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("ImportInEdit")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()
        self.command = FreeCADGui.Command.get("Std_Import")

    def testImportIsOfferedWhileEditingASketch(self):
        self.assertTrue(self.command.isActive())

        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.flush_gui(50)
        self.assertIsNotNone(FreeCADGui.Control.activeDialog())
        self.assertTrue(self.command.isActive())

        FreeCADGui.ActiveDocument.resetEdit()
        self.flush_gui(50)
        self.assertTrue(self.command.isActive())

    def testImportIsRefusedByOtherTaskDialogs(self):
        FreeCADGui.Control.showDialog(_Panel())
        self.flush_gui(50)
        self.assertFalse(self.command.isActive())

        FreeCADGui.Control.closeDialog()
        self.flush_gui(50)
        self.assertTrue(self.command.isActive())
