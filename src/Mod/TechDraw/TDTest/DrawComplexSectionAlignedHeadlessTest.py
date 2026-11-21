# SPDX-License-Identifier: LGPL-2.1-or-later
"""An aligned complex section is generated without the GUI.

The aligned pieces are made in a worker thread whose completion is reported by
a Qt signal. Without the GUI there is no event loop to deliver it, so the
section never finished and stayed empty.
"""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawComplexSectionAlignedHeadlessTest(unittest.TestCase):
    def setUp(self):
        if FreeCAD.GuiUp:
            # with the gui the section is cut in threads
            self.skipTest("console mode only")
        self.doc = FreeCAD.newDocument("TDComplexSectionAligned")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testAlignedSectionUnfoldsProfile(self):
        profile = self.doc.addObject("Part::Feature", "AlignedProfile")
        profile.Shape = Part.makePolygon(
            [FreeCAD.Vector(0.0, 5.0, 5.0),
             FreeCAD.Vector(5.0, 5.0, 5.0),
             FreeCAD.Vector(10.0, 10.0, 5.0)]
        )
        section = self.doc.addObject("TechDraw::DrawComplexSection", "AlignedSection")
        self.page.addView(section)
        section.Source = [self.box]
        section.BaseView = self.view
        section.CuttingToolWireObject = profile
        section.ProjectionStrategy = "Aligned"
        section.Direction = FreeCAD.Vector(0, 1, 0)
        section.SectionNormal = FreeCAD.Vector(0, 1, 0)
        section.ScaleType = "Custom"
        section.Scale = 1.0
        self.doc.recompute()

        edges = section.getVisibleEdges()
        self.assertTrue(edges, "Aligned section did not generate")
        xs = [vertex.Point.x for edge in edges for vertex in edge.Vertexes]
        # Both profile segments cross the box completely: 5 + 5 * sqrt(2) unfolded.
        self.assertAlmostEqual(max(xs) - min(xs), 5.0 + 5.0 * 2.0**0.5, places=2)


if __name__ == "__main__":
    unittest.main()
