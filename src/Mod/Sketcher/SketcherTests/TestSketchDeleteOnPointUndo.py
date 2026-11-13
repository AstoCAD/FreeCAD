# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests that undoing a deletion at a point restores the constraints that were redirected."""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchDeleteOnPointUndo(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchDeleteOnPointUndo")
        self.addCleanup(self._closeDocument)
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        # three lines meeting at (10, 0)
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(10, 0, 0), V(10, 10, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(10, 0, 0), V(20, 5, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 2, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        self.doc.recompute()

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _constraints(self):
        return [
            (c.Type, c.First, c.FirstPos, c.Second, c.SecondPos) for c in self.sketch.Constraints
        ]

    def _undoRedo(self, operation):
        before = self._constraints()
        self.doc.openTransaction("Delete")
        operation()
        self.doc.commitTransaction()
        after = self._constraints()
        self.assertNotEqual(before, after)

        # The second coincidence was redirected to the point of line 1. Undo must give back the
        # constraint as it was, not the redirected one.
        self.doc.undo()
        self.assertEqual(self._constraints(), before)

        self.doc.redo()
        self.assertEqual(self._constraints(), after)

    def testUndoDelConstraintOnPoint(self):
        self._undoRedo(lambda: self.sketch.delConstraintOnPoint(0, 2))

    def testUndoDelGeometryAtJunction(self):
        self._undoRedo(lambda: self.sketch.delGeometry(0))
