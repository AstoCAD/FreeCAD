# SPDX-License-Identifier: LGPL-2.1-or-later
"""A broken-out section that cannot be applied leaves its view intact."""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawBrokenOutSectionTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDBrokenOutSection")
        self.page = createPageWithSVGTemplate(self.doc)
        self.source = self.doc.addObject("Part::Feature", "Source")
        # away from the origin, so that a wrong centring shows
        self.source.Shape = Part.makeBox(20, 20, 40, FreeCAD.Vector(50, -10, 0))

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _addView(self, typeName):
        view = self.doc.addObject(typeName, "View")
        self.page.addView(view)
        view.Source = [self.source]
        view.Direction = FreeCAD.Vector(0, -1, 0)
        view.XDirection = FreeCAD.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1.0
        self.doc.recompute()
        return view

    def _addSection(self, view, outline):
        section = self.doc.addObject("TechDraw::DrawViewBrokenOutSection", "BrokenOutSection")
        section.Outline = outline
        section.Depth = 4.0
        view.BrokenOutSections = [section]
        self.doc.recompute()
        return section

    @staticmethod
    def _points(view):
        return sorted(
            (round(vertex.Point.x, 6), round(vertex.Point.y, 6))
            for edge in view.getVisibleEdges()
            for vertex in edge.Vertexes
        )

    def testRepeatedOutlinePointKeepsViewValid(self):
        """An outline point given twice is skipped instead of failing the view."""
        view = self._addView("TechDraw::DrawViewPart")
        before = len(view.getVisibleEdges())
        self._addSection(
            view,
            [
                FreeCAD.Vector(55, 0, 15),
                FreeCAD.Vector(65, 0, 15),
                FreeCAD.Vector(65, 0, 15),
                FreeCAD.Vector(65, 0, 25),
                FreeCAD.Vector(55, 0, 25),
            ],
        )
        self.assertIn("Up-to-date", view.State)
        self.assertEqual(len(view.getVisibleEdges()), before)

    def testBrokenViewListingASectionKeepsItsGeometry(self):
        """A broken view does not apply broken-out sections; listing one does not move it."""
        view = self._addView("TechDraw::DrawBrokenView")
        before = self._points(view)
        self.assertTrue(before)
        self._addSection(
            view,
            [
                FreeCAD.Vector(55, 0, 15),
                FreeCAD.Vector(65, 0, 15),
                FreeCAD.Vector(65, 0, 25),
                FreeCAD.Vector(55, 0, 25),
            ],
        )
        self.assertIn("Up-to-date", view.State)
        self.assertEqual(self._points(view), before)


if __name__ == "__main__":
    unittest.main()
