# SPDX-License-Identifier: LGPL-2.1-or-later
"""An angle dimension names the type of the reference that is not a line.

When the second reference of a 2d angle dimension was not a line, the error
named the type of the first reference ("second 2d reference is a Line" for a
line and a circle).
"""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionAngleReferenceTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDimensionAngleReference")
        cylinder = self.doc.addObject("Part::Cylinder", "Cylinder")
        cylinder.Radius = 10
        box = self.doc.addObject("Part::Box", "Box")
        box.Placement.Base = FreeCAD.Vector(30, 0, 0)
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [cylinder, box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        edges = self.view.getVisibleEdges()
        self.circle = next(
            "Edge%d" % i for i, e in enumerate(edges) if isinstance(e.Curve, Part.Circle))
        self.line = next(
            "Edge%d" % i for i, e in enumerate(edges) if isinstance(e.Curve, Part.Line))

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def angleStatus(self, refs):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        dimension.Type = "Angle"
        dimension.References2D = [(self.view, ref) for ref in refs]
        self.page.addView(dimension)
        self.doc.recompute()
        self.assertIn("Invalid", dimension.State)
        return dimension.getStatusString()

    def testSecondReferenceIsNamed(self):
        status = self.angleStatus([self.line, self.circle])
        self.assertIn("second 2d reference is a Circle", status)

    def testFirstReferenceIsNamedControl(self):
        status = self.angleStatus([self.circle, self.line])
        self.assertIn("first 2d reference is a Circle", status)


if __name__ == "__main__":
    unittest.main()
