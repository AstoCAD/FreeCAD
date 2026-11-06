# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests that SketchObject.addMove() can be undone and redone like the other operations."""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchMoveUndo(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchMoveUndo")
        self.addCleanup(self._closeDocument)
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _points(self):
        result = []
        for geo in self.sketch.Geometry:
            if isinstance(geo, Part.Point):
                result.append((geo.X, geo.Y))
            elif hasattr(geo, "StartPoint"):
                result.append((geo.StartPoint.x, geo.StartPoint.y, geo.EndPoint.x, geo.EndPoint.y))
            else:
                result.append((geo.Center.x, geo.Center.y))
        return result

    def _assertPointsEqual(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            for u, w in zip(a, e):
                self.assertAlmostEqual(u, w)

    def _moveUndoRedo(self, ids):
        self.doc.recompute()
        before = self._points()
        self.doc.openTransaction("Move")
        self.sketch.addMove(ids, V(0, 20, 0))
        self.doc.commitTransaction()
        self.doc.recompute()
        after = self._points()
        self.assertNotEqual(before, after)

        self.doc.undo()
        self.doc.recompute()
        self._assertPointsEqual(self._points(), before)

        self.doc.redo()
        self.doc.recompute()
        self._assertPointsEqual(self._points(), after)

    def testUndoMoveOfLine(self):
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self._moveUndoRedo([0])

    def testUndoMoveOfConstrainedGeometry(self):
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))  # 0
        self.sketch.addGeometry(Part.ArcOfCircle(Part.Circle(V(10, 3, 0), V(0, 0, 1), 3), -1.5708, 1.0))  # 1
        self.sketch.addGeometry(Part.Circle(V(-5, 5, 0), V(0, 0, 1), 2))  # 2
        self.sketch.addGeometry(Part.Point(V(4, 8, 0)))  # 3
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        self.sketch.addConstraint(Sketcher.Constraint("Radius", 2, 2.0))
        self._moveUndoRedo([0, 1, 2, 3])

    def testMoveWithoutTransactionStillMoves(self):
        # control
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self.sketch.addMove([0], V(1, 2, 0))
        self.assertAlmostEqual(self.sketch.Geometry[0].StartPoint.x, 1.0)
        self.assertAlmostEqual(self.sketch.Geometry[0].StartPoint.y, 2.0)
