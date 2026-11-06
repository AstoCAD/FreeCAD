# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Flip flag of a center line survives saving and reopening the document.

CenterLine::Restore() read the flag inverted, so every save and reload flipped
the two-line center lines to the other pair of points.
"""

import os
import tempfile
import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCenterLineFlipRestoreTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCenterLineFlipRestore")
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.tempDir = tempfile.TemporaryDirectory()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        self.tempDir.cleanup()

    def _reloadedFlip(self, flip):
        view = self.doc.View
        tag = view.makeCenterLine(["Face0"], 0)
        line = view.getCenterLine(tag)
        line.Flip = flip
        self.assertEqual(view.getCenterLine(tag).Flip, flip)
        self.doc.recompute()

        path = os.path.join(self.tempDir.name, "flip.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(path)
        restored = self.doc.View.CenterLines
        self.assertEqual(len(restored), 1)
        return restored[0].Flip

    def testFlipOffIsRestored(self):
        self.assertFalse(self._reloadedFlip(False))

    def testFlipOnIsRestored(self):
        self.assertTrue(self._reloadedFlip(True))


if __name__ == "__main__":
    unittest.main()
