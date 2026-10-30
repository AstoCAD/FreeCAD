# SPDX-License-Identifier: LGPL-2.1-or-later

"""Regression tests for SketchObject.removeAxesAlignment (FreeCAD#9269)."""

import unittest

import FreeCAD as App
import Part
import Sketcher


class TestRemoveAxesAlignment(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("RemoveAxesAlignment")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _addLine(self, start, end):
        return self.sketch.addGeometry(
            Part.LineSegment(App.Vector(start[0], start[1], 0), App.Vector(end[0], end[1], 0))
        )

    def testNegativeHorizontalDistanceKeepsSolvableLength(self):
        # The line runs right to left, so its horizontal distance is negative.
        line = self._addLine((10, 1), (0, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", line))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceX", line, 1, line, 2, -10))
        self.assertEqual(self.sketch.solve(), 0)

        self.sketch.removeAxesAlignment([line])

        constraints = self.sketch.Constraints
        self.assertEqual([c.Type for c in constraints], ["Distance"])
        self.assertAlmostEqual(constraints[0].Value, 10.0)
        self.assertEqual(self.sketch.solve(), 0)
        self.assertAlmostEqual(self.sketch.Geometry[line].length(), 10.0)

    def testPointDistanceToOriginIsKept(self):
        # DistanceX/DistanceY of a single point fix its position relative to the origin.
        # Turning them into Distance constraints would constrain the length of the whole
        # line instead (twice, with conflicting values).
        line = self._addLine((10, 1), (0, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", line))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceX", line, 1, 10))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceY", line, 1, 1))
        self.assertEqual(self.sketch.solve(), 0)

        self.sketch.removeAxesAlignment([line])

        constraints = self.sketch.Constraints
        self.assertEqual([c.Type for c in constraints], ["DistanceX", "DistanceY"])
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(list(self.sketch.ConflictingConstraints), [])
        start = self.sketch.Geometry[line].StartPoint
        self.assertAlmostEqual(start.x, 10.0)
        self.assertAlmostEqual(start.y, 1.0)
        self.assertAlmostEqual(self.sketch.Geometry[line].length(), 10.0)

    def testRectangleStaysRectangular(self):
        # Regression from upstream #27451: the horizontal and vertical references lost the
        # Perpendicular constraint that keeps their angle.
        points = [(0, 0), (10, 0), (10, 5), (0, 5)]
        for i in range(4):
            self._addLine(points[i], points[(i + 1) % 4])
        for i in range(4):
            self.sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))
        self.sketch.addConstraint(Sketcher.Constraint("Vertical", 1))
        self.sketch.addConstraint(Sketcher.Constraint("Vertical", 3))
        self.assertEqual(self.sketch.solve(), 0)

        self.sketch.removeAxesAlignment([0, 1, 2, 3])

        types = [c.Type for c in self.sketch.Constraints]
        self.assertEqual(types.count("Parallel"), 2)
        self.assertEqual(types.count("Perpendicular"), 1)
        self.assertNotIn("Horizontal", types)
        self.assertNotIn("Vertical", types)
        self.assertEqual(self.sketch.solve(), 0)

        # Rotate the rectangle: a corner moved off-axis must keep every angle at 90 degrees.
        self.sketch.addConstraint(Sketcher.Constraint("Angle", 0, 0.3))
        self.assertEqual(self.sketch.solve(), 0)
        edges = [g.EndPoint - g.StartPoint for g in self.sketch.Geometry]
        for i in range(4):
            self.assertAlmostEqual(edges[i].dot(edges[(i + 1) % 4]), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
