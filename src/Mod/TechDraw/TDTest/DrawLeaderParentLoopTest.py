# SPDX-License-Identifier: LGPL-2.1-or-later
"""Leaders and rich annotations attached to themselves must not hang.

DrawLeaderLine::keepUpdated() and getScale() ask the LeaderParent, and
DrawRichAnno::findParentPage() asks the AnnoParent. A leader or annotation
used as its own parent, directly or through another one, made these calls
endless and the recompute never returned.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawLeaderParentLoopTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDLeaderParentLoop")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _leader(self):
        leader = TechDraw.makeLeader(
            self.view, [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 10, 0)]
        )
        self.doc.recompute()
        return leader

    def _anno(self, parent):
        anno = self.doc.addObject("TechDraw::DrawRichAnno", "Anno")
        anno.AnnoParent = parent
        self.page.addView(anno)
        self.doc.recompute()
        return anno

    def testLeaderOfItself(self):
        leader = self._leader()
        leader.LeaderParent = leader
        self.doc.recompute()
        leader.LeaderParent = self.view
        self.doc.recompute()
        self.assertNotIn("Invalid", leader.State)

    def testScalableLeaderOfItself(self):
        leader = self._leader()
        leader.Scalable = True
        leader.AutoHorizontal = True
        leader.LeaderParent = leader
        self.assertAlmostEqual(leader.getScale(), 1.0)
        self.doc.recompute()
        leader.LeaderParent = self.view
        self.doc.recompute()
        self.assertNotIn("Invalid", leader.State)
        self.assertAlmostEqual(leader.getScale(), self.view.getScale())

    def testTwoLeadersOfEachOther(self):
        first = self._leader()
        second = self._leader()
        first.LeaderParent = second
        second.LeaderParent = first
        self.doc.recompute()
        first.LeaderParent = self.view
        second.LeaderParent = self.view
        self.doc.recompute()
        self.assertNotIn("Invalid", first.State)
        self.assertNotIn("Invalid", second.State)

    def testAnnotationOfItself(self):
        anno = self._anno(self.view)
        anno.AnnoParent = anno
        self.doc.recompute()
        self.assertEqual(anno.findParentPage().Name, self.page.Name)

    def testTwoAnnotationsOfEachOther(self):
        first = self._anno(self.view)
        second = self._anno(first)
        first.AnnoParent = second
        self.doc.recompute()
        self.assertEqual(first.findParentPage().Name, self.page.Name)
        self.assertEqual(second.findParentPage().Name, self.page.Name)


if __name__ == "__main__":
    unittest.main()
