# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dimension helper APIs require a parent page before modifying a document."""

import time
import unittest

import FreeCAD as App
import Part
import TechDraw
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionApiTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DimensionApiRegression")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Source")
        self.source.Shape = Part.makeBox(10, 10, 10)
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        deadline = time.monotonic() + 20
        while not self.view.getVisibleEdges() or "Up-to-date" not in self.view.State:
            self.assertLess(time.monotonic(), deadline, self.view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def snapshot(self):
        return {
            "objects": tuple(obj.Name for obj in self.doc.Objects),
            "page_views": tuple(obj.Name for obj in self.page.Views),
            "cosmetic_vertices": tuple(vertex.Tag for vertex in self.view.CosmeticVertexes),
            "edge_lengths": tuple(edge.Length for edge in self.view.getVisibleEdges()),
            "coordinates": (self.view.X.Value, self.view.Y.Value),
            "source_volume": self.source.Shape.Volume,
        }

    def arguments(self, api):
        if api == "makeExtentDim":
            return self.view, [], 0
        return self.view, "Distance", App.Vector(0, 0, 0), App.Vector(10, 0, 0)

    def check_unattached(self, api):
        # A computed view can become unparented when removed or moved between pages.
        self.page.removeView(self.view)
        self.assertIsNone(self.view.findParentPage())
        self.assertEqual(len(self.view.getVisibleEdges()), 4)
        before = self.snapshot()
        with self.assertRaises(Exception) as raised:
            getattr(TechDraw, api)(*self.arguments(api))
        self.assertEqual(self.snapshot(), before)
        self.assertIsInstance(raised.exception, ValueError)
        self.assertRegex(str(raised.exception), "page")

    def check_attached(self, api):
        result = getattr(TechDraw, api)(*self.arguments(api))
        self.doc.recompute()
        dimensions = [obj for obj in self.doc.Objects
                      if obj.isDerivedFrom("TechDraw::DrawViewDimension")]
        self.assertEqual(len(dimensions), 1)
        dimension = dimensions[0]
        self.assertEqual(dimension.Document.Name, self.doc.Name)
        self.assertEqual(dimension.findParentPage(), self.page)
        self.assertAlmostEqual(dimension.getRawValue(), 10)
        if api == "makeDistanceDim3d":
            self.assertIsNone(result)
        else:
            self.assertEqual(result.Name, dimension.Name)

    def testExtentRejectsUnattachedViewWithoutMutation(self):
        self.check_unattached("makeExtentDim")

    def testDistanceRejectsUnattachedViewWithoutMutation(self):
        self.check_unattached("makeDistanceDim")

    def testDistance3dRejectsUnattachedViewWithoutMutation(self):
        self.check_unattached("makeDistanceDim3d")

    def testExtentAttachedView(self):
        self.check_attached("makeExtentDim")

    def testDistanceAttachedView(self):
        self.check_attached("makeDistanceDim")

    def testDistance3dAttachedView(self):
        self.check_attached("makeDistanceDim3d")

    def testExtentWrongFirstArgumentKeepsNoneReturn(self):
        for argument in (None, self.source, self.page):
            with self.subTest(argument=argument):
                before = self.snapshot()
                self.assertIsNone(TechDraw.makeExtentDim(argument, [], 0))
                self.assertEqual(self.snapshot(), before)
