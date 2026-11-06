# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests that SketchObject.extend() updates the sketch and can be undone, for arcs as for lines."""

import math
import unittest

import FreeCAD as App
import Part

V = App.Vector


class TestSketchExtendUndo(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchExtendUndo")
        self.addCleanup(self._closeDocument)
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _extendUndoRedo(self, increment, endPoint, expectedLength):
        self.doc.recompute()
        before = self.sketch.Shape.Length
        self.doc.openTransaction("Extend")
        self.sketch.extend(0, increment, endPoint)
        self.doc.commitTransaction()
        self.assertIn("Touched", self.sketch.State)
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Geometry[0].length(), expectedLength)
        self.assertAlmostEqual(self.sketch.Shape.Length, expectedLength)

        self.doc.undo()
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Geometry[0].length(), before)
        self.assertAlmostEqual(self.sketch.Shape.Length, before)

        self.doc.redo()
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Geometry[0].length(), expectedLength)
        self.assertAlmostEqual(self.sketch.Shape.Length, expectedLength)

    def _assertPoint(self, pos, angle):
        point = self.sketch.getPoint(0, pos)
        self.assertAlmostEqual(point.x, 5 * math.cos(angle))
        self.assertAlmostEqual(point.y, 5 * math.sin(angle))

    def testExtendArcAtEnd(self):
        self.sketch.addGeometry(Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5), 0.3, 2.5))
        self._extendUndoRedo(1.0, 2, 5 * 3.2)
        self._assertPoint(1, 0.3)
        self._assertPoint(2, 3.5)

    def testExtendArcAtStart(self):
        self.sketch.addGeometry(Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5), 0.3, 2.5))
        self._extendUndoRedo(0.5, 1, 5 * 2.7)
        self._assertPoint(1, -0.2)
        self._assertPoint(2, 2.5)

    def testExtendLine(self):
        # control: lines are extended through moveGeometry and always worked
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self._extendUndoRedo(2.0, 2, 12.0)

    def testExtendArcWithoutTransaction(self):
        self.sketch.addGeometry(Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5), 0.0, math.pi / 2))
        self.doc.recompute()
        self.sketch.extend(0, math.pi / 2, 2)
        self.doc.recompute()
        self.assertAlmostEqual(self.sketch.Shape.Length, 5 * math.pi)
        self.assertAlmostEqual(self.sketch.getPoint(0, 2).x, -5.0)
        self.assertAlmostEqual(self.sketch.getPoint(0, 2).y, 0.0)
