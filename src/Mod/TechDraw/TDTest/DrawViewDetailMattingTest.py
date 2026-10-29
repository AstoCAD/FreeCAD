# SPDX-License-Identifier: LGPL-2.1-or-later
"""A square detail is aligned with the X direction of its base view (#33832).

The square cutting tool was built on a plane with an arbitrary X axis, so the
detail of a base view with a rotated XDirection (or an axonometric view) came
out rotated against the square matting drawn in the base view.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

DECORATIONS = "User parameter:BaseApp/Preferences/Mod/TechDraw/Decorations"


class DrawViewDetailMattingTest(unittest.TestCase):
    def setUp(self):
        self.params = FreeCAD.ParamGet(DECORATIONS)
        self.hadMatting = "MattingStyle" in self.params.GetInts()
        self.oldMatting = self.params.GetInt("MattingStyle", 0)
        self.params.SetInt("MattingStyle", 1)  # square
        self.doc = FreeCAD.newDocument("TDDetailMatting")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        if self.hadMatting:
            self.params.SetInt("MattingStyle", self.oldMatting)
        else:
            self.params.RemInt("MattingStyle")

    def _waitFor(self, view):
        if not FreeCAD.GuiUp:
            return
        import time
        import FreeCADGui
        from PySide import QtCore

        deadline = time.monotonic() + 60
        while not view.isProjectionReady():
            self.assertLess(time.monotonic(), deadline, "projection did not finish")
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()
            FreeCADGui.updateGui()

    def testSquareDetailFollowsXDirection(self):
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 100
        page = createPageWithSVGTemplate(self.doc)
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        view.XDirection = FreeCAD.Vector(1, 1, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        self.doc.recompute()
        self._waitFor(view)

        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        detail.BaseView = view
        detail.Direction = view.Direction
        detail.XDirection = view.XDirection
        detail.AnchorPoint = FreeCAD.Vector(0, 0, 0)
        detail.Radius = 10
        detail.ScaleType = "Custom"
        detail.Scale = 1
        page.addView(detail)
        self.doc.recompute()
        self._waitFor(detail)

        edges = detail.getVisibleEdges()
        self.assertEqual(len(edges), 4)
        for edge in edges:
            start = edge.Vertexes[0].Point
            end = edge.Vertexes[-1].Point
            # every side of the square is horizontal or vertical in the detail
            self.assertLess(min(abs(start.x - end.x), abs(start.y - end.y)), 1e-3,
                            "detail square is rotated: {} -> {}".format(start, end))
            for point in (start, end):
                self.assertAlmostEqual(abs(point.x), abs(point.y), places=3)
                self.assertLess(abs(point.x), 10.5)


if __name__ == "__main__":
    unittest.main()
