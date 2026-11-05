# SPDX-License-Identifier: LGPL-2.1-or-later
"""DrawViewPart.decorateLine must reject an edge name that has no geometry.

An index past the view's edges (or any edge of a view without geometry)
dereferenced a null geometry pointer: an access violation on Windows and a
segmentation fault elsewhere.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

RED = (1.0, 0.0, 0.0, 1.0)


class DrawDecorateLineInvalidEdgeTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDecorateLineInvalidEdge")
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

    def testEdgeIndexPastTheEndIsRejected(self):
        for name in ("Edge4", "Edge999"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.view.decorateLine(name, 2, 0.5, RED, True)
        self.assertEqual(len(self.view.GeomFormats), 0)

    def testViewWithoutGeometryIsRejected(self):
        empty = self.doc.addObject("TechDraw::DrawViewPart", "Empty")
        self.page.addView(empty)
        with self.assertRaises(ValueError):
            empty.decorateLine("Edge0", 2, 0.5, RED, True)
        self.assertEqual(len(empty.GeomFormats), 0)

    def testExistingEdgeStillDecorated(self):
        self.view.decorateLine("Edge0", 2, 0.5, RED, True)
        self.assertEqual(len(self.view.GeomFormats), 1)


if __name__ == "__main__":
    unittest.main()
