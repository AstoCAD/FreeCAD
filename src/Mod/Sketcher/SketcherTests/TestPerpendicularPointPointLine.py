# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the point-point-line form of the Perpendicular constraint.

Sketcher.Constraint("Perpendicular", geo1, pos1, geo2, pos2, line) makes the segment between
the two points perpendicular to the line. The solver must use the line given by its geometry
index, also when other geometry comes before it in the sketch or when it is a sketch axis.
"""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestPerpendicularPointPointLine(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PerpendicularPointPointLine")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _addSegment(self):
        # the two points to constrain: a slanted segment
        return self.sketch.addGeometry(Part.LineSegment(V(2, 1, 0), V(5, 7, 0)))

    def _assertSegmentPerpendicularTo(self, segmentId, direction):
        seg = self.sketch.Geometry[segmentId]
        d = seg.EndPoint - seg.StartPoint
        self.assertGreater(d.Length, 1e-6)
        self.assertAlmostEqual(d.normalize().dot(direction.normalize()), 0.0, places=6)

    def testLineAfterOtherGeometry(self):
        # A circle comes first, so the target line has geometry index 1 but is the first line
        # known to the solver; the segment is the second line.
        self.sketch.addGeometry(Part.Circle(V(20, 20, 0), V(0, 0, 1), 2))
        lineId = self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        segId = self._addSegment()
        self.sketch.addConstraint(Sketcher.Constraint("Block", lineId))
        self.sketch.addConstraint(Sketcher.Constraint("Perpendicular", segId, 1, segId, 2, lineId))
        self.assertEqual(self.sketch.solve(), 0)
        self._assertSegmentPerpendicularTo(segId, V(1, 0, 0))

    def testLineBeforeSegment(self):
        lineId = self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 10, 0)))
        segId = self._addSegment()
        self.sketch.addConstraint(Sketcher.Constraint("Block", lineId))
        self.sketch.addConstraint(Sketcher.Constraint("Perpendicular", segId, 1, segId, 2, lineId))
        self.assertEqual(self.sketch.solve(), 0)
        self._assertSegmentPerpendicularTo(segId, V(1, 1, 0))

    def testHorizontalAxis(self):
        segId = self._addSegment()
        self.sketch.addConstraint(Sketcher.Constraint("Perpendicular", segId, 1, segId, 2, -1))
        self.assertEqual(self.sketch.solve(), 0)
        self._assertSegmentPerpendicularTo(segId, V(1, 0, 0))

    def testVerticalAxis(self):
        segId = self._addSegment()
        self.sketch.addConstraint(Sketcher.Constraint("Perpendicular", segId, 1, segId, 2, -2))
        self.assertEqual(self.sketch.solve(), 0)
        self._assertSegmentPerpendicularTo(segId, V(0, 1, 0))


if __name__ == "__main__":
    unittest.main()
