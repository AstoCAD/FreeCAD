# SPDX-License-Identifier: LGPL-2.1-or-later
"""Undo after removing a cosmetic edge, vertex or center line.

The cosmetic edge, vertex and center line list properties do not own their
entries, and their undo copies share the same objects. Removing an entry
deleted it, so undoing the removal put a dangling pointer back into the view
(access violation). This is what the Cosmetic Eraser, the Delete key and
Extend/Shorten line do inside an undoable transaction.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCosmeticRemoveUndoTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticRemoveUndo")
        self.doc.UndoMode = 1
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _churn(self):
        """Reuse freed heap blocks so a dangling pointer is not silently readable."""
        doc = FreeCAD.newDocument("TDCosmeticRemoveUndoChurn")
        try:
            box = doc.addObject("Part::Box", "Box")
            view = doc.addObject("TechDraw::DrawViewPart", "View")
            view.Source = [box]
            view.Direction = FreeCAD.Vector(0, 0, 1)
            doc.recompute()
            for i in range(200):
                view.makeCosmeticLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(i + 1, 1, 0))
                view.makeCosmeticVertex(FreeCAD.Vector(i, 1, 0))
        finally:
            FreeCAD.closeDocument(doc.Name)

    def _removeAndUndo(self, add, remove, listName):
        self.doc.openTransaction("add")
        tag = add()
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual([item.Tag for item in getattr(self.view, listName)], [tag])

        self.doc.openTransaction("remove")
        remove(tag)
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(getattr(self.view, listName), [])

        self._churn()
        self.doc.undo()
        self.assertEqual([item.Tag for item in getattr(self.view, listName)], [tag])
        self.doc.recompute()

        self.doc.redo()
        self.assertEqual(getattr(self.view, listName), [])
        self.doc.undo()
        self.assertEqual([item.Tag for item in getattr(self.view, listName)], [tag])
        self.doc.recompute()

    def testUndoRemovedCosmeticEdge(self):
        self._removeAndUndo(
            lambda: self.view.makeCosmeticLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(5, 5, 0)),
            self.view.removeCosmeticEdge,
            "CosmeticEdges",
        )

    def testUndoRemovedCosmeticVertex(self):
        self._removeAndUndo(
            lambda: self.view.makeCosmeticVertex(FreeCAD.Vector(1, 2, 0)),
            self.view.removeCosmeticVertex,
            "CosmeticVertexes",
        )

    def testUndoRemovedCenterLine(self):
        self._removeAndUndo(
            lambda: self.view.makeCenterLine(["Edge0", "Edge2"], 2),
            self.view.removeCenterLine,
            "CenterLines",
        )


if __name__ == "__main__":
    unittest.main()
