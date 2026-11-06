# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw module functions raise ValueError for a view of a closed document.

The Python wrapper outlives its object: the functions dereferenced the null
object (an access violation) instead of raising.
"""

import os
import tempfile
import unittest

import FreeCAD
import TechDraw


class DrawClosedDocumentViewTest(unittest.TestCase):
    def setUp(self):
        doc = FreeCAD.newDocument("TDClosedView")
        self.view = doc.addObject("TechDraw::DrawViewPart", "View")
        self.page = doc.addObject("TechDraw::DrawPage", "Page")
        FreeCAD.closeDocument(doc.Name)

    def testViewOfClosedDocumentRaises(self):
        v = FreeCAD.Vector
        calls = {
            "viewPartAsDxf": lambda: TechDraw.viewPartAsDxf(self.view),
            "viewPartAsSvg": lambda: TechDraw.viewPartAsSvg(self.view),
            "writeDXFView": lambda: TechDraw.writeDXFView(
                self.view, os.path.join(tempfile.gettempdir(), "TDClosedView.dxf")
            ),
            "writeDXFPage": lambda: TechDraw.writeDXFPage(
                self.page, os.path.join(tempfile.gettempdir(), "TDClosedPage.dxf")
            ),
            "makeExtentDim": lambda: TechDraw.makeExtentDim(self.view, [], 0),
            "makeDistanceDim": lambda: TechDraw.makeDistanceDim(
                self.view, "DistanceX", v(0, 0, 0), v(1, 0, 0)
            ),
            "makeDistanceDim3d": lambda: TechDraw.makeDistanceDim3d(
                self.view, "DistanceX", v(0, 0, 0), v(1, 0, 0)
            ),
            "makeCanonicalPoint": lambda: TechDraw.makeCanonicalPoint(self.view, v(1, 1, 0)),
            "makeLeader": lambda: TechDraw.makeLeader(self.view, [v(0, 0, 0), v(1, 1, 0)]),
        }
        for name, call in calls.items():
            with self.subTest(function=name):
                with self.assertRaises(ValueError):
                    call()


if __name__ == "__main__":
    unittest.main()
