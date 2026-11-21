# SPDX-License-Identifier: LGPL-2.1-or-later
"""Assigning GeomFormat wrappers whose format was deleted to DrawViewPart.GeomFormats.

GeomFormats owns its entries and replaces all of them on every change, so a
wrapper read from the list before (e.g. before clearGeomFormats()) no longer has
a format. Assigning it back dereferenced a null pointer (access violation on
Windows, segmentation fault elsewhere); a single deleted wrapper was silently
ignored.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

RED = (1.0, 0.0, 0.0, 1.0)


class DrawGeomFormatDeletedWrapperTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDGeomFormatDeletedWrapper")
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)
        self.view.decorateLine("Edge0", 2, 0.5, RED, True)
        self.view.decorateLine("Edge1", 2, 0.5, RED, True)
        self.assertEqual(len(self.view.GeomFormats), 2)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testDeletedWrappersInListAreRefused(self):
        formats = self.view.GeomFormats
        self.view.clearGeomFormats()
        with self.assertRaises(ReferenceError):
            self.view.GeomFormats = formats
        self.assertEqual(len(self.view.GeomFormats), 0)

    def testDeletedSingleWrapperIsRefused(self):
        format0 = self.view.GeomFormats[0]
        self.view.clearGeomFormats()
        with self.assertRaises(ReferenceError):
            self.view.GeomFormats = format0
        self.assertEqual(len(self.view.GeomFormats), 0)

    def testCurrentWrappersStillAssigned(self):
        self.view.GeomFormats = self.view.GeomFormats
        self.assertEqual(len(self.view.GeomFormats), 2)
        self.view.GeomFormats = self.view.GeomFormats[1]
        self.assertEqual(len(self.view.GeomFormats), 1)


if __name__ == "__main__":
    unittest.main()
