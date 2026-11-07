# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dimensions with 3d references on rotated views and on detail views.

A dimension with 3d references projects its points onto the view. The
projection left out the view's Rotation, so on a rotated view the dimension
was placed as if the view was not rotated and a horizontal dimension measured
in the wrong direction. On a detail view the vertex of an angle dimension (and
the center of a radius or area dimension) was projected as on a plain view,
so the angle was wrong (63.4 instead of 90 degrees). The same dimensions with
2d references were right.
"""

import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimension3dReferenceViewTest(unittest.TestCase):
    def setUp(self):
        if App.GuiUp:
            # with the gui the detail shapes are made in threads
            self.skipTest("console mode only")
        self.doc = App.newDocument("TDDimension3dReferenceView")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = 40
        box.Width = 20
        box.Height = 10
        hole = self.doc.addObject("Part::Cylinder", "Hole")
        hole.Radius = 4
        hole.Height = 12
        hole.Placement.Base = App.Vector(30, 10, -1)
        self.source = self.doc.addObject("Part::Cut", "Cut")
        self.source.Base = box
        self.source.Tool = hole
        self.doc.recompute()
        self.page = createPageWithSVGTemplate(self.doc)

    def edge3d(self, start, end):
        for i, edge in enumerate(self.source.Shape.Edges):
            ends = {tuple(round(c, 6) for c in v.Point) for v in edge.Vertexes}
            if ends == {start, end}:
                return "Edge%d" % (i + 1)
        self.fail("no edge %s - %s" % (start, end))

    def vertex3d(self, point):
        for i, vertex in enumerate(self.source.Shape.Vertexes):
            if tuple(round(c, 6) for c in vertex.Point) == point:
                return "Vertex%d" % (i + 1)
        self.fail("no vertex %s" % (point,))

    def holeEdge3d(self):
        for i, edge in enumerate(self.source.Shape.Edges):
            if isinstance(edge.Curve, Part.Circle) and abs(edge.Curve.Center.z - 10) < 1e-6:
                return "Edge%d" % (i + 1)
        self.fail("no hole edge")

    def makeView(self, rotation, scale):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [self.source]
        view.Direction = App.Vector(0, 0, 1)
        view.XDirection = App.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = scale
        view.Rotation = rotation
        self.doc.recompute()
        return view

    def makeDetail(self, base, anchor, radius, rotation=0):
        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        self.page.addView(detail)
        detail.BaseView = base
        detail.Source = base.Source
        detail.Direction = base.Direction
        detail.XDirection = base.XDirection
        detail.AnchorPoint = anchor
        detail.Radius = radius
        detail.ScaleType = "Custom"
        detail.Scale = 2
        detail.Rotation = rotation
        self.doc.recompute()
        return detail

    def dimension(self, view, dimType, references3d=None, references2d=None):
        dim = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(dim)
        dim.Type = dimType
        if references3d:
            dim.References2D = [(view, "")]
            dim.MeasureType = "Projected"
            dim.References3D = [(self.source, sub) for sub in references3d]
        else:
            dim.References2D = [(view, sub) for sub in references2d]
        self.doc.recompute()
        self.assertIn("Up-to-date", dim.State)
        return dim

    def vertexPoints2d(self, view):
        """The view's vertices as 2d dimensions see them."""
        count = len(view.getVisibleVertexes())
        points = []
        for i in range(1, count):
            dim = self.dimension(view, "Distance", references2d=["Vertex0", "Vertex%d" % i])
            points.extend(dim.getLinearPoints())
            self.doc.removeObject(dim.Name)
        return points

    def assertOnPoints(self, point, points):
        self.assertTrue(any((point - other).Length < 1e-6 for other in points),
                        "%s not in %s" % (point, points))

    def testDistanceOnRotatedView(self):
        view = self.makeView(30, 2)
        right = self.edge3d((40, 0, 10), (40, 20, 10))
        vertices = self.vertexPoints2d(view)
        distance = self.dimension(view, "Distance", references3d=[right])
        self.assertAlmostEqual(distance.getRawValue(), 20, places=6)
        for point in distance.getLinearPoints():
            self.assertOnPoints(point, vertices)
        # the edge is 20 long and turned by 30 degrees on the paper
        horizontal = self.dimension(view, "DistanceX", references3d=[right])
        self.assertAlmostEqual(horizontal.getRawValue(), 10, places=6)
        vertical = self.dimension(view, "DistanceY", references3d=[right])
        self.assertAlmostEqual(vertical.getRawValue(), 20 * 3**0.5 / 2, places=6)

    def testRadiusCenterOnRotatedView(self):
        view = self.makeView(30, 2)
        circles = ["Edge%d" % i for i, e in enumerate(view.getVisibleEdges())
                   if isinstance(e.Curve, Part.Circle)]
        self.assertEqual(len(circles), 1)
        radius2d = self.dimension(view, "Radius", references2d=circles)
        radius3d = self.dimension(view, "Radius", references3d=[self.holeEdge3d()])
        self.assertAlmostEqual(radius3d.getRawValue(), 4, places=6)
        center2d = radius2d.getArcPoints()[0]
        center3d = radius3d.getArcPoints()[0]
        self.assertLess((center3d - center2d).Length, 1e-6, (center3d, center2d))

    def testAnglesOnDetailView(self):
        view = self.makeView(0, 1)
        detail = self.makeDetail(view, App.Vector(10, 0, 0), 15)
        right = self.edge3d((40, 0, 10), (40, 20, 10))
        front = self.edge3d((0, 0, 10), (40, 0, 10))
        angle = self.dimension(detail, "Angle", references3d=[right, front])
        self.assertAlmostEqual(angle.getRawValue(), 90, places=6)
        angle3pt = self.dimension(detail, "Angle3Pt", references3d=[
            self.vertex3d((40, 20, 10)), self.vertex3d((40, 0, 10)), self.vertex3d((0, 0, 10))])
        self.assertAlmostEqual(angle3pt.getRawValue(), 90, places=6)

    def checkCornerOnDetail(self, detail):
        # only the corner at (40, 20) is inside the detail
        vertices = detail.getVisibleVertexes()
        self.assertEqual(len(vertices), 1)
        angle3pt = self.dimension(detail, "Angle3Pt", references3d=[
            self.vertex3d((40, 0, 10)), self.vertex3d((40, 20, 10)), self.vertex3d((0, 20, 10))])
        self.assertAlmostEqual(angle3pt.getRawValue(), 90, places=6)
        apex = angle3pt.getAnglePoints()[2]
        self.assertLess((apex - vertices[0]).Length, 1e-6, (apex, vertices[0]))

    def testRotatedDetailView(self):
        view = self.makeView(0, 1)
        self.checkCornerOnDetail(self.makeDetail(view, App.Vector(17, 7, 0), 7, rotation=30))

    def testDetailOfRotatedView(self):
        view = self.makeView(30, 1)
        self.checkCornerOnDetail(self.makeDetail(view, App.Vector(11, 16, 0), 7))

    def testDistanceXBetweenCirclesOnRotatedView(self):
        source = self.doc.addObject("Part::Feature", "Circles")
        source.Shape = Part.makeCompound([
            Part.makeCylinder(5, 10, App.Vector(0, 0, 0), App.Vector(0, 1, 0)),
            Part.makeCylinder(3, 10, App.Vector(30, 0, 40), App.Vector(0, 1, 0))])
        circles3d = ["Edge%d" % (i + 1) for i, e in enumerate(source.Shape.Edges)
                     if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Center.y) < 1e-9]
        self.assertEqual(len(circles3d), 2)
        self.source = source
        view = self.doc.addObject("TechDraw::DrawViewPart", "Front")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = App.Vector(0, -1, 0)
        view.XDirection = App.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.Rotation = 90
        self.doc.recompute()
        circles2d = ["Edge%d" % i for i, e in enumerate(view.getVisibleEdges())
                     if isinstance(e.Curve, Part.Circle)]
        self.assertEqual(len(circles2d), 2)
        # turned by 90 degrees, the horizontal distance is the vertical one of the front view
        for dimType, expected in (("DistanceX", 32.0), ("DistanceY", 22.0)):
            with self.subTest(type=dimType):
                dim2d = self.dimension(view, dimType, references2d=circles2d)
                dim3d = self.dimension(view, dimType, references3d=circles3d)
                self.assertAlmostEqual(dim2d.getRawValue(), expected, places=6)
                self.assertAlmostEqual(dim3d.getRawValue(), expected, places=6)


if __name__ == "__main__":
    unittest.main()
