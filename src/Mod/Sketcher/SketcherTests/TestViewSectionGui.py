# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import tempfile

import FreeCAD
from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase


class TestViewSectionGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def check_section_view_document_name(self, name):
        self.doc = FreeCAD.newDocument("TestViewSectionGui")
        self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()
        filename = os.path.join(self.temp_dir.name, name + ".FCStd")
        self.doc.saveAs(filename)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(filename)
        self.assertEqual(self.doc.Name, name)

        sketch = self.doc.getObject("Sketch")
        FreeCADGui.getDocument(self.doc.Name).setEdit(sketch.Name)
        self.flush_gui()
        initial_section_view = sketch.ViewObject.SectionView

        # Issue #33325: the command must preserve the UTF-8 document name
        # when looking up the active sketch through Python.
        FreeCADGui.runCommand("Sketcher_ViewSection")
        self.flush_gui()
        self.assertEqual(sketch.ViewObject.SectionView, not initial_section_view)

        FreeCADGui.runCommand("Sketcher_ViewSection")
        self.flush_gui()
        self.assertEqual(sketch.ViewObject.SectionView, initial_section_view)

    def test_section_view_ascii_document_name(self):
        self.check_section_view_document_name("SectionView")

    def test_section_view_latin1_document_name(self):
        self.check_section_view_document_name("SectionView_\u00fc")

    def test_section_view_non_latin1_document_name(self):
        self.check_section_view_document_name("SectionView_\u6f22\u5b57")
