# SPDX-License-Identifier: LGPL-2.1-or-later
"""A detail whose BaseView is another detail shows that detail's area.

The AnchorPoint of a detail is given in the coordinates of its BaseView. A
detail of a detail read it in the coordinates of the first detail's own base
view and clipped that view's whole source, so it showed the wrong area.
Details and sections recompute the views based on them when their own shape
is ready, so a loop of BaseViews must not make them recompute each other
forever.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


def _edgeSummary(view):
    """Lengths and end points of the visible edges of a view, in a stable order."""
    result = []
    for edge in view.getVisibleEdges():
        ends = sorted((v.Point.x, v.Point.y) for v in edge.Vertexes)
        result.append([edge.Length] + [c for point in ends for c in point])
    return sorted(result, key=lambda values: [round(value, 1) for value in values])


class DrawViewDetailOfDetailTest(unittest.TestCase):
    def setUp(self):
        if FreeCAD.GuiUp:
            # with the gui the detail shapes are made in threads
            self.skipTest("console mode only")
        self.doc = FreeCAD.newDocument("TDDetailOfDetail")
        self.doc.UndoMode = 0
        self.page = createPageWithSVGTemplate(self.doc)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def assertSameEdges(self, view, reference):
        edges = _edgeSummary(view)
        referenceEdges = _edgeSummary(reference)
        self.assertEqual(len(edges), len(referenceEdges), (edges, referenceEdges))
        for edge, referenceEdge in zip(edges, referenceEdges):
            self.assertEqual(len(edge), len(referenceEdge), (edges, referenceEdges))
            for value, referenceValue in zip(edge, referenceEdge):
                self.assertAlmostEqual(value, referenceValue, 3, (edges, referenceEdges))

    def _addView(self, sources):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = sources
        view.Direction = FreeCAD.Vector(0, 0, 1)
        view.XDirection = FreeCAD.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        return view

    def _addDetail(self, base, anchor, radius):
        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        self.page.addView(detail)
        detail.BaseView = base
        detail.Source = base.Source
        detail.Direction = base.Direction
        detail.XDirection = base.XDirection
        detail.AnchorPoint = anchor
        detail.Radius = radius
        detail.ScaleType = "Custom"
        detail.Scale = 1
        return detail

    def _addBox(self, length, width, height, position=FreeCAD.Vector()):
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = length
        box.Width = width
        box.Height = height
        box.Placement.Base = position
        return box

    def testDetailOfDetailUsesItsBaseCoordinates(self):
        # top view of a 40 x 20 box: the box corner (40, 20) is at (20, 10) in the view
        view = self._addView([self._addBox(40, 20, 10)])
        detail = self._addDetail(view, FreeCAD.Vector(15, 5, 0), 8)
        # (5, 5) in the detail is (20, 10) in the view: the box corner
        detailOfDetail = self._addDetail(detail, FreeCAD.Vector(5, 5, 0), 3)
        reference = self._addDetail(view, FreeCAD.Vector(20, 10, 0), 3)
        self.doc.recompute()

        for v in (detail, detailOfDetail, reference):
            self.assertNotIn("Invalid", v.State, v.Name)
        self.assertEqual(len(_edgeSummary(reference)), 3)
        self.assertSameEdges(detailOfDetail, reference)

        # the detail of the detail follows a change of the detail it is based on:
        # (5, 5) in the detail is now (5, 5) in the view, inside the box
        detail.AnchorPoint = FreeCAD.Vector(0, 0, 0)
        detail.Radius = 12
        reference.AnchorPoint = FreeCAD.Vector(5, 5, 0)
        self.doc.recompute()
        self.assertNotIn("Invalid", detailOfDetail.State)
        self.assertEqual(len(_edgeSummary(reference)), 1)
        self.assertSameEdges(detailOfDetail, reference)

    def testDetailOfDetailAwayFromTheMiddleInDepth(self):
        # a thin plate at the bottom and a thin plate 48 higher, apart from it
        low = self._addBox(20, 20, 2)
        high = self._addBox(20, 20, 2, FreeCAD.Vector(40, 0, 48))
        view = self._addView([low, high])
        # the view is centred on (30, 10), in the gap between the plates;
        # the high plate's middle is at (20, 0)
        detail = self._addDetail(view, FreeCAD.Vector(20, 0, 0), 6)
        # the detail of the detail only shows the high plate, far above the
        # middle of the view in depth
        detailOfDetail = self._addDetail(detail, FreeCAD.Vector(2, 1, 0), 3)
        reference = self._addDetail(view, FreeCAD.Vector(22, 1, 0), 3)
        self.doc.recompute()

        for v in (detail, detailOfDetail, reference):
            self.assertNotIn("Invalid", v.State, v.Name)
        self.assertTrue(_edgeSummary(reference))
        self.assertSameEdges(detailOfDetail, reference)

    def testDetailOfItself(self):
        view = self._addView([self._addBox(40, 20, 10)])
        detail = self._addDetail(view, FreeCAD.Vector(15, 5, 0), 8)
        self.doc.recompute()
        self.assertNotIn("Invalid", detail.State)

        detail.BaseView = detail
        self.doc.recompute()
        self.assertIn("Invalid", detail.State)

        detail.BaseView = view
        self.doc.recompute()
        self.assertNotIn("Invalid", detail.State)

    def testDetailsOfEachOther(self):
        view = self._addView([self._addBox(40, 20, 10)])
        detail = self._addDetail(view, FreeCAD.Vector(15, 5, 0), 8)
        other = self._addDetail(detail, FreeCAD.Vector(0, 0, 0), 3)
        self.doc.recompute()
        self.assertNotIn("Invalid", other.State)

        detail.BaseView = other
        self.doc.recompute()
        # the recompute order inside the loop is not defined; the detail that
        # runs first reports the loop and the document then skips the views
        # that depend on it
        self.assertTrue("Invalid" in detail.State or "Invalid" in other.State)
        # each of them reports the loop when it is recomputed
        for looping in (detail, other):
            looping.recompute()
            self.assertIn("Invalid", looping.State, looping.Name)

        detail.BaseView = view
        other.touch()
        self.doc.recompute()
        self.assertNotIn("Invalid", detail.State)
        self.assertNotIn("Invalid", other.State)

    def testDetailAndSectionOfEachOther(self):
        box = self._addBox(40, 20, 10)
        view = self._addView([box])
        detail = self._addDetail(view, FreeCAD.Vector(15, 5, 0), 8)
        section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        self.page.addView(section)
        section.BaseView = detail
        section.Source = [box]
        section.SectionNormal = FreeCAD.Vector(1, 0, 0)
        section.Direction = FreeCAD.Vector(1, 0, 0)
        section.SectionOrigin = FreeCAD.Vector(0, 0, 0)
        self.doc.recompute()

        # each one recomputes the views based on it once its shape is ready
        detail.BaseView = section
        self.doc.recompute()
        self.assertIn("Invalid", detail.State)

        detail.BaseView = view
        section.touch()
        self.doc.recompute()
        self.assertNotIn("Invalid", detail.State)


if __name__ == "__main__":
    unittest.main()
