# SPDX-License-Identifier: LGPL-2.1-or-later
"""A Draft view recomputes in its owning document while another is active."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtSvg

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDraftViewDocumentTest(unittest.TestCase):
    def setUp(self):
        try:
            import Draft
        except ImportError:
            self.skipTest("The real Draft exporter is unavailable")
        if not callable(getattr(Draft, "get_svg", None)):
            self.skipTest("The real Draft.get_svg exporter is unavailable")
        self.Draft = Draft
        previous_workbench = Gui.activeWorkbench().name()
        previous_active = App.ActiveDocument.Name if App.ActiveDocument else None

        def restore_active():
            if previous_active in App.listDocuments():
                App.setActiveDocument(previous_active)

        self.addCleanup(Gui.activateWorkbench, previous_workbench)
        self.addCleanup(restore_active)
        self.addCleanup(Gui.Selection.clearSelection)
        Gui.activateWorkbench("TechDrawWorkbench")
        self.owner = self.createDrawing("DraftOwnerA", 10, 5, (1.0, 0.0, 0.0), 0.41)
        self.original_owner = self.recomputeActive(self.owner, 0.41)
        self.other = self.createDrawing("DraftActiveB", 30, 20, (0.0, 0.0, 1.0), 1.7)
        self.original_other = self.recomputeActive(self.other, 1.7)
        self.assertEqual(self.owner["source"].Name, self.other["source"].Name)
        self.assertEqual(self.owner["view"].Name, self.other["view"].Name)
        self.assertNotEqual(self.original_owner, self.original_other)
        self.expected_owner = self.recomputeActive(self.owner, 0.63)
        self.assertNotEqual(self.expected_owner, self.original_owner)
        self.assertEqual(self.recomputeActive(self.owner, 0.41), self.original_owner)
        self.assertEqual(self.recomputeActive(self.other, 1.7), self.original_other)

    def createDrawing(self, name, length, height, color, line_width):
        doc = App.newDocument(name)
        self.addCleanup(App.closeDocument, doc.Name)
        source = self.Draft.make_rectangle(length, height, face=False)
        source.Label = name + " genuine Draft rectangle " + str(length) + "x" + str(height)
        page = createPageWithSVGTemplate(doc)
        view = doc.addObject("TechDraw::DrawViewDraft", "DraftView")
        view.Label = name + " distinct drawing"
        view.Source = source
        view.OverrideStyle = True
        view.Color = color
        view.LineWidth = line_width
        view.Direction = App.Vector(0, 0, 1)
        view.ScaleType = "Custom"
        view.Scale = 1
        page.addView(view)
        doc.recompute()
        page.ViewObject.show()
        Gui.updateGui()
        return {"doc": doc, "source": source, "page": page, "view": view}

    def validSvg(self, view):
        self.assertRegex(view.Symbol, r"<(path|rect|line|polyline|polygon)\b")
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(view.Symbol.encode("utf-8")))
        self.assertTrue(renderer.isValid())
        self.assertNotIn("Invalid", view.State)
        return view.Symbol

    def recomputeActive(self, drawing, line_width):
        App.setActiveDocument(drawing["doc"].Name)
        drawing["view"].LineWidth = line_width
        drawing["view"].touch()
        drawing["doc"].recompute()
        Gui.updateGui()
        return self.validSvg(drawing["view"])

    def snapshot(self, drawing):
        source, view = drawing["source"], drawing["view"]
        bounds = source.Shape.BoundBox
        return {"bounds": (bounds.XLength, bounds.YLength, bounds.ZLength),
                "source_label": source.Label, "view_label": view.Label,
                "source_document": view.Source.Document.Name,
                "line_width": view.LineWidth, "color": tuple(view.Color),
                "symbol": view.Symbol, "state": tuple(view.State),
                "objects": tuple(obj.Name for obj in drawing["doc"].Objects),
                "page_views": tuple(drawing["page"].Views)}

    def recomputeInactiveOwner(self, active_document=None):
        if active_document is None:
            active_document = self.other["doc"]
        self.assertEqual(App.ActiveDocument, active_document)
        self.owner["view"].LineWidth = 0.63
        self.owner["view"].touch()
        errors = []
        try:
            self.owner["doc"].recompute()
        except Exception as error:
            errors.append((type(error).__name__, str(error)))
        self.assertFalse(errors)
        self.assertEqual(App.ActiveDocument, active_document)
        Gui.updateGui()

    def testOwnerActiveRecomputeControl(self):
        before_other = self.snapshot(self.other)
        self.assertEqual(self.recomputeActive(self.owner, 0.63), self.expected_owner)
        self.assertEqual(self.snapshot(self.other), before_other)

    def testInactiveOwnerRecomputesOwnSvg(self):
        before = self.snapshot(self.owner)
        self.recomputeInactiveOwner()
        self.assertEqual(self.validSvg(self.owner["view"]), self.expected_owner)
        after = self.snapshot(self.owner)
        for field in ("bounds", "source_label", "view_label", "objects", "page_views"):
            self.assertEqual(after[field], before[field])

    def testInactiveRecomputeDoesNotModifyOtherDocument(self):
        before = self.snapshot(self.other)
        self.recomputeInactiveOwner()
        self.assertEqual(self.snapshot(self.other), before)
        self.validSvg(self.other["view"])

    def testInactiveOwnerWithUnrelatedEmptyDocument(self):
        unrelated = App.newDocument("DraftUnrelatedEmpty")
        self.addCleanup(App.closeDocument, unrelated.Name)
        self.assertIsNone(unrelated.getObject(self.owner["source"].Name))
        self.assertIsNone(unrelated.getObject(self.owner["view"].Name))
        before_other = self.snapshot(self.other)
        self.recomputeInactiveOwner(unrelated)
        self.assertEqual(self.validSvg(self.owner["view"]), self.expected_owner)
        self.assertEqual(unrelated.Objects, [])
        self.assertEqual(self.snapshot(self.other), before_other)

    def testUnicodeDocumentOwnerActiveControl(self):
        name = "DraftOwner_測定_é"
        drawing = self.createDrawing(name, 7, 3, (0.0, 0.5, 0.0), 0.86)
        self.assertEqual(drawing["doc"].Name, name)
        original = self.validSvg(drawing["view"])
        self.assertNotEqual(self.recomputeActive(drawing, 1.1), original)
