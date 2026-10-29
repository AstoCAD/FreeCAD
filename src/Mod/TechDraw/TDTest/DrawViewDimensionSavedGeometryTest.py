# SPDX-License-Identifier: LGPL-2.1-or-later
"""A dimension reference without geometry must not break undo (#30168)."""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewDimensionSavedGeometryTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDimSavedGeometry")
        self.doc.UndoMode = 1
        box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [box]
        self.doc.recompute()

        self.dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(self.dimension)
        self.dimension.Type = "Distance"
        self.dimension.References2D = [(self.view, "Edge0")]
        self.doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testMissingGeometryKeepsSavedGeometry(self):
        """A reference to missing geometry keeps the previous SavedGeometry."""
        self.assertEqual(len(self.dimension.SavedGeometry), 1)
        self.assertFalse(self.dimension.SavedGeometry[0].isNull())

        self.dimension.References2D = [(self.view, "Edge999")]
        self.doc.recompute()
        self.assertTrue(all(not shape.isNull() for shape in self.dimension.SavedGeometry))

        # repairing the reference inside a transaction copies SavedGeometry for undo
        self.doc.openTransaction("Repair dimension")
        self.dimension.References2D = [(self.view, "Edge1")]
        self.doc.commitTransaction()
        self.doc.recompute()
        self.assertEqual(self.dimension.References2D[0][1], ("Edge1",))

    def testNullShapeInListCanBeCopiedForUndo(self):
        """A PropertyTopoShapeList holding a null shape can be saved for undo."""
        self.dimension.SavedGeometry = [Part.Shape()]
        self.doc.openTransaction("Change saved geometry")
        self.dimension.SavedGeometry = [Part.makeLine((0, 0, 0), (1, 0, 0))]
        self.doc.commitTransaction()
        self.assertEqual(len(self.dimension.SavedGeometry), 1)
        self.doc.undo()
        self.assertEqual(len(self.dimension.SavedGeometry), 1)
        self.assertTrue(self.dimension.SavedGeometry[0].isNull())


if __name__ == "__main__":
    unittest.main()
