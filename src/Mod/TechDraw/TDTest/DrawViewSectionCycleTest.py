# SPDX-License-Identifier: LGPL-2.1-or-later
"""A section whose BaseView chain leads back to itself must not crash.

DrawViewSection::getShapeToCut() asks a base section for its shape to cut, and
that one asks its own base. A section used as its own BaseView, or two sections
used as each other's BaseView, made this recursion endless and the recompute
crashed (stack overflow).
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewSectionCycleTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDSectionCycle")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.section = self._addSection("Section", self.view, FreeCAD.Vector(1, 0, 0))
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _addSection(self, name, base, normal):
        section = self.doc.addObject("TechDraw::DrawViewSection", name)
        self.page.addView(section)
        section.BaseView = base
        section.Source = [self.box]
        section.SectionNormal = normal
        section.Direction = normal
        section.SectionOrigin = FreeCAD.Vector(5, 5, 5)
        return section

    def testSectionOfItself(self):
        self.section.BaseView = self.section
        self.doc.recompute()
        self.assertIn("Invalid", self.section.State)

        self.section.BaseView = self.view
        self.doc.recompute()
        self.assertNotIn("Invalid", self.section.State)

    def testTwoSectionsOfEachOther(self):
        other = self._addSection("Other", self.section, FreeCAD.Vector(0, 1, 0))
        self.doc.recompute()
        self.assertNotIn("Invalid", other.State)

        self.section.BaseView = other
        self.doc.recompute()
        # the recompute order inside the loop is not defined; the section that
        # runs first reports the loop
        self.assertTrue("Invalid" in self.section.State or "Invalid" in other.State)

        self.section.BaseView = self.view
        other.touch()
        self.doc.recompute()
        self.assertNotIn("Invalid", self.section.State)
        self.assertNotIn("Invalid", other.State)


if __name__ == "__main__":
    unittest.main()
