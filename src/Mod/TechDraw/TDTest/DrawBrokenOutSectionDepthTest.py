# SPDX-License-Identifier: LGPL-2.1-or-later
"""A broken-out section opens the viewed shape from its front.

The depth of a broken-out section is measured from the front of the viewed
shape. That front was taken from the shape's vertices only, but the front of a
cylinder seen from its side, or of a sphere, lies on a curved face away from
every vertex. The cut then started inside the material and left a hidden void
instead of opening the view.
"""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawBrokenOutSectionDepthTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDBrokenOutSectionDepth")
        self.page = createPageWithSVGTemplate(self.doc)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _visibleEdgeCounts(self, shape):
        """Visible edges of a front view of shape, before and after a broken-out section."""
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = shape
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = FreeCAD.Vector(0, -1, 0)
        view.XDirection = FreeCAD.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1.0
        self.doc.recompute()
        before = len(view.getVisibleEdges())

        section = self.doc.addObject("TechDraw::DrawViewBrokenOutSection", "BrokenOutSection")
        section.Outline = [
            FreeCAD.Vector(-5, 0, 15),
            FreeCAD.Vector(5, 0, 15),
            FreeCAD.Vector(5, 0, 25),
            FreeCAD.Vector(-5, 0, 25),
        ]
        section.Depth = 4.0
        view.BrokenOutSections = [section]
        self.doc.recompute()
        self.assertIn("Up-to-date", view.State)
        return before, len(view.getVisibleEdges())

    def testFlatFront(self):
        before, after = self._visibleEdgeCounts(
            Part.makeBox(20, 20, 40, FreeCAD.Vector(-10, -10, 0))
        )
        self.assertGreater(after, before)

    def testCylinderSeenFromItsSide(self):
        before, after = self._visibleEdgeCounts(Part.makeCylinder(10, 40))
        self.assertGreater(after, before, "the broken-out section did not open the cylinder")

    def testSphere(self):
        before, after = self._visibleEdgeCounts(
            Part.makeSphere(20, FreeCAD.Vector(0, 0, 20))
        )
        self.assertGreater(after, before, "the broken-out section did not open the sphere")


if __name__ == "__main__":
    unittest.main()
