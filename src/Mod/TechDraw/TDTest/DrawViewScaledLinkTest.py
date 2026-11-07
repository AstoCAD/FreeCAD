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

    def makeView(self, source, direction=App.Vector(0, 0, 1), xDirection=App.Vector(1, 0, 0)):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = direction
        view.XDirection = xDirection
        view.ScaleType = "Custom"
        view.Scale = 1
        return view

    def edgeLengths(self, view):
        return sorted(round(edge.Length, 6) for edge in view.getVisibleEdges())

    def outline(self, view):
        """Sorted edge lengths and the 2d extent of all the edges of the view."""
        edges = view.getVisibleEdges() + view.getHiddenEdges()
        points = [vertex.Point for edge in edges for vertex in edge.Vertexes]
        extent = (round(max(p.x for p in points) - min(p.x for p in points), 6),
                  round(max(p.y for p in points) - min(p.y for p in points), 6))
        return extent, sorted(round(edge.Length, 6) for edge in edges)

    def checkSameAsPart(self, source):
        """The views of source show the shape Part gives it, as in the 3d view."""
        self.doc.recompute()
        copy = self.doc.addObject("Part::Feature", "Copy")
        copy.Shape = Part.getShape(source)
        for direction, xDirection in ((App.Vector(0, 0, 1), App.Vector(1, 0, 0)),
                                      (App.Vector(1, 0, 0), App.Vector(0, 1, 0))):
            sourceView = self.makeView(source, direction, xDirection)
            copyView = self.makeView(copy, direction, xDirection)
            self.doc.recompute()
            self.assertEqual(self.outline(sourceView), self.outline(copyView), direction)
        return copy

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

    def testDimension3dOnScaledLink(self):
        # A dimension referencing the link's 3d edge measures and lands on the
        # scaled edge the view shows (Measure applied the link's scale and
        # placement twice: 120 instead of 60, drawn off the view).
        view = self.checkLink(App.Vector(2, 2, 2))
        edges = self.box.Shape.Edges
        longEdge = next("Edge%d" % (i + 1) for i, edge in enumerate(edges)
                        if abs(edge.Length - 30) < 1e-6)
        points2d = []
        for i in range(len(view.getVisibleEdges())):
            dim2d = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension2d")
            self.page.addView(dim2d)
            dim2d.Type = "Distance"
            dim2d.References2D = [(view, "Edge%d" % i)]
            self.doc.recompute()
            points2d.extend(dim2d.getLinearPoints())
        link = view.Source[0]
        for measureType in ("Projected", "True"):
            dim = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension3d")
            self.page.addView(dim)
            dim.Type = "Distance"
            dim.References2D = [(view, "")]
            dim.MeasureType = measureType
            dim.References3D = [(link, longEdge)]
            self.doc.recompute()
            self.assertAlmostEqual(dim.getRawValue(), 60, places=6, msg=measureType)
            for point in dim.getLinearPoints():
                self.assertTrue(any((point - other).Length < 1e-6 for other in points2d),
                                "%s %s not in %s" % (measureType, point, points2d))

    def testNonUniformScale(self):
        view = self.checkLink(App.Vector(2, 3, 1))
        self.assertEqual(self.edgeLengths(view), [30, 30, 60, 60])

    def testUnscaledLink(self):
        view = self.checkLink(App.Vector(1, 1, 1))
        self.assertEqual(self.edgeLengths(view), [10, 10, 30, 30])

    def testLinkTransform(self):
        # With LinkTransform the link's placement is applied on top of the linked object's own
        # placement; the view used to replace it, so the box stood upright again.
        self.box.Placement.Rotation = App.Rotation(App.Vector(1, 0, 0), 90)
        for scale in (1, 2):
            link = self.doc.addObject("App::Link", "Link")
            link.LinkedObject = self.box
            link.Placement = App.Placement(App.Vector(100, 0, 0),
                                           App.Rotation(App.Vector(0, 0, 1), 30))
            link.LinkTransform = True
            link.ScaleVector = App.Vector(scale, scale, scale)
            self.checkSameAsPart(link)
            # the box stands on its 30 x 5 face: seen from the top it is 30 x 5, not 30 x 10
            view = self.makeView(link)
            self.doc.recompute()
            self.assertEqual(self.edgeLengths(view), [5 * scale, 5 * scale, 30 * scale, 30 * scale])

    def testLinkToPartWithLinkTransform(self):
        part = self.doc.addObject("App::Part", "Part")
        part.Placement = App.Placement(App.Vector(0, 0, -50), App.Rotation(App.Vector(1, 0, 0), 90))
        part.addObject(self.box)
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = part
        link.Placement = App.Placement(App.Vector(300, 0, 0), App.Rotation(App.Vector(0, 0, 1), 30))
        link.LinkTransform = True
        link.ScaleVector = App.Vector(2, 2, 2)
        self.checkSameAsPart(link)

    def testLinkArray(self):
        # An array without visible elements used to show only its first element.
        array = self.doc.addObject("App::Link", "Array")
        array.LinkedObject = self.box
        array.ShowElement = False
        array.ElementCount = 3
        array.PlacementList = [App.Placement(App.Vector(0, 40 * i, 0), App.Rotation())
                               for i in range(3)]
        array.ScaleList = [App.Vector(1, 1, 1), App.Vector(2, 2, 2), App.Vector(1, 1, 1)]
        array.Placement = App.Placement(App.Vector(0, 0, 100), App.Rotation(App.Vector(0, 0, 1), 10))
        self.checkSameAsPart(array)
        view = self.makeView(array)
        self.doc.recompute()
        self.assertEqual(self.edgeLengths(view), [10] * 4 + [20] * 2 + [30] * 4 + [60] * 2)

    def testLinkArrayWithElements(self):
        # The placement of each visible element (ElementList) used to be applied twice.
        array = self.doc.addObject("App::Link", "Array")
        array.LinkedObject = self.box
        array.ShowElement = True
        array.ElementCount = 3
        self.doc.recompute()
        for i, element in enumerate(array.ElementList):
            element.Placement = App.Placement(App.Vector(0, 40 * i, 0), App.Rotation())
        array.ElementList[1].ScaleVector = App.Vector(2, 2, 2)
        array.Placement = App.Placement(App.Vector(0, 0, 100), App.Rotation(App.Vector(0, 0, 1), 10))
        self.checkSameAsPart(array)
        array.Placement = App.Placement()
        view = self.makeView(array)
        self.doc.recompute()
        self.assertEqual(self.edgeLengths(view), [10] * 4 + [20] * 2 + [30] * 4 + [60] * 2)
        # three elements 40 apart, the last one 10 wide
        self.assertAlmostEqual(self.outline(view)[0][1], 90, places=6)


if __name__ == "__main__":
    unittest.main()
