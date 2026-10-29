# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cosmetic vertices, center lines and geometry formats can be cleared after
Python has read them (#33806).

Each of these objects caches a Python wrapper that owns it. Before the fix,
clearing the list deleted the object, which released its wrapper, which deleted
the same object again (heap corruption, the test process aborts). A wrapper kept
by Python pointed to freed memory instead of raising ReferenceError.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticLifetimeTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticLifetime")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _addVertex(self):
        tag = self.view.makeCosmeticVertex(FreeCAD.Vector(1, 2, 0))
        self.doc.recompute()
        return tag

    def _addCenterLine(self):
        tag = self.view.makeCenterLine(["Edge0", "Edge2"], 2)
        self.doc.recompute()
        return tag

    def _addFormat(self):
        self.view.formatGeometricEdge(0, 2, 0.5, FreeCAD.Vector(1, 0, 0), True)
        self.doc.recompute()

    def testClearVerticesAfterReadingList(self):
        self._addVertex()
        self.assertEqual(len(self.view.CosmeticVertexes), 1)
        self.view.clearCosmeticVertices()
        self.doc.recompute()
        self.assertEqual(self.view.CosmeticVertexes, [])

    def testClearedVertexWrapperIsInvalid(self):
        tag = self._addVertex()
        retained = self.view.CosmeticVertexes
        self.assertEqual(retained[0].Tag, tag)
        self.view.clearCosmeticVertices()
        self.doc.recompute()
        with self.assertRaises(ReferenceError):
            _ = retained[0].Tag

    def testClearCenterLinesAfterReadingList(self):
        self._addCenterLine()
        self.assertEqual(len(self.view.CenterLines), 1)
        self.view.clearCenterLines()
        self.doc.recompute()
        self.assertEqual(self.view.CenterLines, [])

    def testClearedCenterLineWrapperIsInvalid(self):
        tag = self._addCenterLine()
        retained = self.view.CenterLines
        self.assertEqual(retained[0].Tag, tag)
        self.view.clearCenterLines()
        self.doc.recompute()
        with self.assertRaises(ReferenceError):
            _ = retained[0].Tag

    def testClearGeomFormatsAfterReadingList(self):
        self._addFormat()
        self.assertEqual(len(self.view.GeomFormats), 1)
        self.view.clearGeomFormats()
        self.doc.recompute()
        self.assertEqual(self.view.GeomFormats, [])


if __name__ == "__main__":
    unittest.main()
