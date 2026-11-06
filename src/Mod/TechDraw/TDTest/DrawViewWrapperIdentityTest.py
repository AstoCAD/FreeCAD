# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw methods must return the views' own Python objects.

DrawProjGroup.addProjection/getItemByLabel, DrawPage.getViews/getAllViews and
TechDraw.makeLeader built a second Python wrapper around the C++ view. Such a
wrapper is not invalidated when the view is deleted, so using it afterwards
read freed memory instead of raising ReferenceError.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewWrapperIdentityTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDWrapperIdentity")
        self.doc.UndoMode = 0  # removed objects are deleted at once
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.group = self.doc.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        self.page.addView(self.group)
        self.group.Source = [self.box]

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testProjectionGroupReturnsOwnObjects(self):
        front = self.group.addProjection("Front")
        self.assertIs(front, self.doc.getObject(front.Name))
        right = self.group.addProjection("Right")
        self.assertIs(right, self.doc.getObject(right.Name))
        self.assertIs(self.group.getItemByLabel("Front"), front)

    def testRemovedProjectionWrapperIsInvalidated(self):
        self.group.addProjection("Front")
        right = self.group.addProjection("Right")
        self.assertIs(right, self.doc.getObject(right.Name))
        name = right.Name
        self.group.removeProjection("Right")
        self.assertIsNone(self.doc.getObject(name))
        with self.assertRaises(ReferenceError):
            right.Label

    def testPageViewsAreOwnObjects(self):
        self.group.addProjection("Front")
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [self.box]
        self.doc.recompute()
        views = self.page.getViews()
        self.assertTrue(views)
        for item in views:
            self.assertIs(item, self.doc.getObject(item.Name))
        allViews = self.page.getAllViews()
        self.assertGreater(len(allViews), len(views))  # includes the group items
        for item in allViews:
            self.assertIs(item, self.doc.getObject(item.Name))

    def testMakeLeaderReturnsOwnObject(self):
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [self.box]
        self.doc.recompute()
        leader = TechDraw.makeLeader(
            view, [FreeCAD.Vector(40, 50, 0), FreeCAD.Vector(50, 60, 0)]
        )
        self.assertIs(leader, self.doc.getObject(leader.Name))


if __name__ == "__main__":
    unittest.main()
