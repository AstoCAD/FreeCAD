# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cosmetic edges and center lines keep their tags through save and reload.

Only cosmetic vertices saved their tag. Every reload gave the cosmetic edges
and center lines new random tags, so a tag returned by makeCosmeticLine,
makeCosmeticCircle(Arc) or makeCenterLine no longer found its object in
getCosmeticEdge, getCenterLine, removeCosmeticEdge or removeCenterLine after
the document was reopened.
"""

import os
import tempfile
import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticTagRestoreTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticTagRestore")
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(view.getVisibleEdges()), 4)
        self.tempDir = tempfile.TemporaryDirectory()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        self.tempDir.cleanup()

    def reload(self):
        path = os.path.join(self.tempDir.name, "tags.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(path)
        self.doc.recompute()
        return self.doc.getObject("View")

    def testTagsSurviveReload(self):
        view = self.doc.View
        vector = FreeCAD.Vector
        edgeTags = [
            view.makeCosmeticLine(vector(0, 0, 0), vector(5, 5, 0)),
            view.makeCosmeticCircle(vector(-10, 20, 0), 3.0),
            view.makeCosmeticCircleArc(vector(10, 20, 0), 5.0, 0.0, 90.0),
        ]
        lineTag = view.makeCenterLine(["Edge0", "Edge1"], 0)
        vertexTag = view.makeCosmeticVertex(vector(1, 2, 0))
        self.doc.recompute()

        view = self.reload()
        self.assertEqual([edge.Tag for edge in view.CosmeticEdges], edgeTags)
        self.assertEqual([line.Tag for line in view.CenterLines], [lineTag])
        self.assertEqual([vertex.Tag for vertex in view.CosmeticVertexes], [vertexTag])
        self.assertEqual(view.getCosmeticEdge(edgeTags[0]).End, vector(5, 5, 0))
        self.assertEqual(view.getCenterLine(lineTag).Edges, ["Edge0", "Edge1"])

        # the drawn geometry carries the restored tags, so selection finds them
        self.assertEqual(view.getCosmeticEdgeBySelection("Edge4").Tag, edgeTags[0])

        view.removeCosmeticEdge(edgeTags[1])
        view.removeCenterLine(lineTag)
        self.assertEqual([edge.Tag for edge in view.CosmeticEdges], [edgeTags[0], edgeTags[2]])
        self.assertEqual(view.CenterLines, [])

        # and they are kept by a second save and reload
        view = self.reload()
        self.assertEqual([edge.Tag for edge in view.CosmeticEdges], [edgeTags[0], edgeTags[2]])


if __name__ == "__main__":
    unittest.main()
