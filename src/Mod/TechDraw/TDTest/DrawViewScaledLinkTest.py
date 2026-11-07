# SPDX-License-Identifier: LGPL-2.1-or-later
"""A view of an App::Link shows the link's ScaleVector.

ShapeExtractor::getShapeFromXLink read the scale of a link to a single object
but only applied its placement, so the view (and its 2d dimensions) showed the
linked object at its original size.
"""

import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewScaledLinkTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TDViewScaledLink")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.page = createPageWithSVGTemplate(self.doc)
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length = 30
        self.box.Width = 10
        self.box.Height = 5
        self.box.Placement.Base = App.Vector(1, 2, 3)

    def makeView(self, source):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = App.Vector(0, 0, 1)
        view.XDirection = App.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        return view

    def edgeLengths(self, view):
        return sorted(round(edge.Length, 6) for edge in view.getVisibleEdges())

    def checkLink(self, scale):
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = self.box
        link.Placement = App.Placement(App.Vector(100, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))
        link.ScaleVector = scale
        self.doc.recompute()
        # the same shape as a plain feature
        copy = self.doc.addObject("Part::Feature", "Copy")
        copy.Shape = Part.getShape(link)
        linkView = self.makeView(link)
        copyView = self.makeView(copy)
        self.doc.recompute()
        self.assertEqual(self.edgeLengths(linkView), self.edgeLengths(copyView))
        return linkView

    def testUniformScale(self):
        view = self.checkLink(App.Vector(2, 2, 2))
        self.assertEqual(self.edgeLengths(view), [20, 20, 60, 60])
        dim = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(dim)
        dim.Type = "Distance"
        longest = max(range(len(view.getVisibleEdges())),
                      key=lambda i: view.getVisibleEdges()[i].Length)
        dim.References2D = [(view, "Edge%d" % longest)]
        self.doc.recompute()
        self.assertAlmostEqual(dim.getRawValue(), 60, places=6)

    def testNonUniformScale(self):
        view = self.checkLink(App.Vector(2, 3, 1))
        self.assertEqual(self.edgeLengths(view), [30, 30, 60, 60])

    def testUnscaledLink(self):
        view = self.checkLink(App.Vector(1, 1, 1))
        self.assertEqual(self.edgeLengths(view), [10, 10, 30, 30])


if __name__ == "__main__":
    unittest.main()
