# SPDX-License-Identifier: LGPL-2.1-or-later
"""A view collection that links to itself does not crash FreeCAD.

DrawView::findParentPage() looks for the page through the parent collections
of a view. A collection in its own in-list (a projection group anchored to
itself, a collection listing itself in Views, two collections listing each
other) made that search recurse without end: stack overflow when the property
was set or the document recomputed.
"""

import unittest

import FreeCAD
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewCollectionLoopTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCollectionLoop")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testCollectionListingItself(self):
        collection = self.doc.addObject("TechDraw::DrawViewCollection", "Collection")
        collection.Views = [collection]
        self.assertIsNone(collection.findParentPage())
        self.doc.recompute()

    def testProjectionGroupAnchoredToItself(self):
        group = self.doc.addObject("TechDraw::DrawProjGroup", "Group")
        group.Anchor = group
        self.assertIsNone(group.findParentPage())
        self.doc.recompute()

    def testCollectionsListingEachOther(self):
        first = self.doc.addObject("TechDraw::DrawViewCollection", "First")
        second = self.doc.addObject("TechDraw::DrawViewCollection", "Second")
        first.Views = [second]
        second.Views = [first]
        self.assertIsNone(first.findParentPage())
        self.assertIsNone(second.findParentPage())

    def testPageStillFoundThroughCollection(self):
        page = createPageWithSVGTemplate(self.doc)
        collection = self.doc.addObject("TechDraw::DrawViewCollection", "Collection")
        page.addView(collection)
        view = self.doc.addObject("TechDraw::DrawViewSymbol", "Symbol")
        collection.Views = [view]
        self.assertEqual(collection.findParentPage(), page)
        self.assertEqual(view.findParentPage(), page)


if __name__ == "__main__":
    unittest.main()
