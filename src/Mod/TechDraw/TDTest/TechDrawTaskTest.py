#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import FreeCAD
import FreeCADGui
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate


class TechDrawTaskTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testDrawProjGroup(self):
        obj = self.doc.addObject("TechDraw::DrawProjGroup")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawProjGroupInvalidAnchor(self):
        """Invalid anchor links must be rejected before constructing the task panel."""
        group = self.doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        page = createPageWithSVGTemplate(self.doc)
        page.addView(group)
        template = page.Template
        part = self.doc.addObject("App::Part", "Part")
        for anchor in (page, template, part, None):
            with self.subTest(anchor=anchor):
                group.Anchor = anchor
                self.assertFalse(group.ViewObject.doubleClicked())

    def testMoveViewUndoRedo(self):
        """Moving a view between pages is recorded by the task's transaction."""
        from TechDrawTools.TaskMoveView import TaskMoveView

        self.doc.UndoMode = 1
        source_page = createPageWithSVGTemplate(self.doc)
        target_page = self.doc.addObject("TechDraw::DrawPage", "TargetPage")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "TargetTemplate")
        template.Template = source_page.Template.Template
        target_page.Template = template
        view = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        view.Text = ["Move me"]
        source_page.addView(view)
        self.doc.recompute()
        self.doc.clearUndos()

        task = TaskMoveView()
        try:
            task.setValues(view.Name, source_page.Name, target_page.Name)
            self.assertTrue(task.accept())
            self.assertNotIn(view, source_page.Views)
            self.assertIn(view, target_page.Views)
            self.doc.undo()
            self.assertIn(view, source_page.Views)
            self.assertNotIn(view, target_page.Views)
            self.doc.redo()
            self.assertNotIn(view, source_page.Views)
            self.assertIn(view, target_page.Views)
        finally:
            task.form.deleteLater()

    def testLockDraftAndArchViews(self):
        """The view lock command works for SVG-based views and records undo."""
        FreeCADGui.activateWorkbench("TechDrawWorkbench")
        self.doc.UndoMode = 1
        page = createPageWithSVGTemplate(self.doc)
        arch = self.doc.addObject("TechDraw::DrawViewArch", "ArchView")
        draft = self.doc.addObject("TechDraw::DrawViewDraft", "DraftView")
        for view in (arch, draft):
            page.addView(view)
        command = "TechDraw_ExtensionLockUnlockView"
        self.assertTrue(FreeCADGui.isCommandActive(command))
        part_view = self.doc.addObject("TechDraw::DrawViewPart", "PartView")
        page.addView(part_view)
        unrelated = self.doc.addObject("App::Part", "Unrelated")
        self.addCleanup(FreeCADGui.Selection.clearSelection)
        for view in (arch, draft, part_view):
            with self.subTest(view=view.TypeId):
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(self.doc.Name, view.Name)
                FreeCADGui.Selection.addSelection(self.doc.Name, unrelated.Name)
                view.LockPosition = False
                self.doc.clearUndos()
                FreeCADGui.runCommand(command)
                self.assertTrue(view.LockPosition)
                self.doc.undo()
                self.assertFalse(view.LockPosition)
                self.doc.redo()
                self.assertTrue(view.LockPosition)
                FreeCADGui.runCommand(command)
                self.assertFalse(view.LockPosition)

    def testDrawViewSection(self):
        obj = self.doc.addObject("TechDraw::DrawViewSection")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawComplexSection(self):
        obj = self.doc.addObject("TechDraw::DrawComplexSection")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawRichAnno(self):
        obj = self.doc.addObject("TechDraw::DrawRichAnno")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawLeaderLine(self):
        obj = self.doc.addObject("TechDraw::DrawLeaderLine")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

    def testDrawViewDetail(self):
        obj = self.doc.addObject("TechDraw::DrawViewDetail")
        with self.assertRaises(RuntimeError):
            obj.ViewObject.doubleClicked()

