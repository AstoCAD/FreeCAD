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

