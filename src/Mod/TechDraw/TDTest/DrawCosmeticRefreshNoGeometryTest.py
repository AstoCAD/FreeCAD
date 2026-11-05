# SPDX-License-Identifier: LGPL-2.1-or-later
"""Refreshing the cosmetics of a view without geometry must not crash.

refreshCosmeticEdges(), refreshCosmeticVertexes(), refreshCenterlines() and
refreshAllCosmetic() dereferenced the view's null geometry object before the
view had executed: an access violation on Windows and a segmentation fault
elsewhere.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

REFRESH_METHODS = (
    "refreshCosmeticEdges",
    "refreshCosmeticVertexes",
    "refreshCenterlines",
    "refreshAllCosmetic",
)


class DrawCosmeticRefreshNoGeometryTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticRefreshNoGeometry")
        self.page = createPageWithSVGTemplate(self.doc)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testRefreshViewWithoutGeometry(self):
        for method in REFRESH_METHODS:
            with self.subTest(method=method):
                empty = self.doc.addObject("TechDraw::DrawViewPart", "Empty")
                self.page.addView(empty)
                getattr(empty, method)()
                self.assertEqual(len(empty.getVisibleEdges()), 0)

    def testRefreshViewWithGeometry(self):
        box = self.doc.addObject("Part::Box", "Box")
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(view.getVisibleEdges()), 4)
        view.makeCosmeticLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(5, 5, 0))
        edgeCount = len(view.getVisibleEdges())
        for method in REFRESH_METHODS:
            with self.subTest(method=method):
                getattr(view, method)()
                self.assertEqual(len(view.getVisibleEdges()), edgeCount)


if __name__ == "__main__":
    unittest.main()
