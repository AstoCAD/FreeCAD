# SPDX-License-Identifier: LGPL-2.1-or-later
"""Detail views in console mode are computed once, synchronously.

Without the gui, DrawViewDetail::detailExec() made the detail shape in the
calling thread and then started the same work again in a background thread
whose completion is never reported. The detail stayed "waiting" for good, so
later changes were ignored, and removing the detail while that thread ran
aborted the process (see also #33900).
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewDetailConsoleTest(unittest.TestCase):
    def setUp(self):
        if FreeCAD.GuiUp:
            self.skipTest("console mode only")
        self.doc = FreeCAD.newDocument("TDDetailConsole")
        self.doc.UndoMode = 0
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 100
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()

        self.detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        self.detail.BaseView = self.view
        self.detail.Direction = self.view.Direction
        self.detail.XDirection = self.view.XDirection
        self.detail.AnchorPoint = FreeCAD.Vector(0, 0, 0)
        self.detail.Radius = 10
        self.detail.ScaleType = "Custom"
        self.detail.Scale = 1
        self.page.addView(self.detail)
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _extent(self):
        points = [v.Point for e in self.detail.getVisibleEdges() for v in e.Vertexes]
        points += [e.valueAt(e.FirstParameter) for e in self.detail.getVisibleEdges()]
        self.assertTrue(points)
        return max(max(abs(p.x), abs(p.y)) for p in points)

    def testDetailIsReady(self):
        self.assertTrue(self.detail.isProjectionReady())
        self.assertGreater(self._extent(), 9.9)
        self.assertLess(self._extent(), 10.5)

    def testDetailFollowsRadiusChange(self):
        self.detail.Radius = 20
        self.doc.recompute()
        self.assertTrue(self.detail.isProjectionReady())
        self.assertGreater(self._extent(), 19.9)
        self.assertLess(self._extent(), 20.5)

    def testRemoveDetailAfterRecompute(self):
        name = self.detail.Name
        self.doc.removeObject(name)
        self.assertIsNone(self.doc.getObject(name))


if __name__ == "__main__":
    unittest.main()
