# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for an endpoint-to-endpoint Tangent or Perpendicular between the two ends of one B-spline.

The constraint joins the start and the end of the B-spline. The angle must be taken between the
tangent at the start and the tangent at the end, also once both ends are at the same point.
"""

import math
import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector

# A loop that ends next to its start, its end tangent about 31 degrees from its start tangent.
LOOP_POLES = [V(0, 0, 0), V(10, 0, 0), V(12, 12, 0), V(-8, 12, 0), V(-6, 3, 0), V(-1, 0, 0)]
# A curve that comes back to its start, its end tangent about 132 degrees from its start tangent.
CUSP_POLES = [V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(5, 5, 0), V(0.5, 0, 0)]


def makeBSpline(poles, degree=3):
    """A clamped, non-periodic B-spline through its first and last pole."""
    inner = len(poles) - degree - 1
    knots = [float(i) for i in range(inner + 2)]
    mults = [degree + 1] + [1] * inner + [degree + 1]
    bspline = Part.BSplineCurve()
    bspline.buildFromPolesMultsKnots(poles, mults, knots, False, degree)
    return bspline


class TestSketchBSplineEndToEnd(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BSplineEndToEnd")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _endTangents(self, geoId):
        bspline = self.sketch.Geometry[geoId]
        start = bspline.FirstParameter
        end = bspline.LastParameter
        self.assertAlmostEqual((bspline.value(start) - bspline.value(end)).Length, 0.0, places=6)
        return bspline.tangent(start)[0], bspline.tangent(end)[0]

    def _endAngle(self, geoId):
        startTangent, endTangent = self._endTangents(geoId)
        return math.degrees(startTangent.getAngle(endTangent))

    def _assertSolvedWithoutRedundancy(self):
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual(self.sketch.ConflictingConstraints, [])
        self.assertEqual(self.sketch.RedundantConstraints, [])
        self.assertEqual(self.sketch.PartiallyRedundantConstraints, [])

    def testTangentJoinsTheEndsSmoothly(self):
        geoId = self.sketch.addGeometry(makeBSpline(LOOP_POLES), False)
        self.sketch.exposeInternalGeometry(geoId)
        self.sketch.addConstraint(Sketcher.Constraint("Tangent", geoId, 1, geoId, 2))
        # the end tangents are less than 90 degrees apart: same direction
        self.assertAlmostEqual(self.sketch.Constraints[-1].Value, -math.pi / 2)
        self._assertSolvedWithoutRedundancy()
        self.assertAlmostEqual(self._endAngle(geoId), 0.0, places=4)

    def testTangentKeepsReversedEnds(self):
        geoId = self.sketch.addGeometry(makeBSpline(CUSP_POLES), False)
        self.sketch.addConstraint(Sketcher.Constraint("Tangent", geoId, 2, geoId, 1))
        # the end tangents are more than 90 degrees apart: opposite directions
        self.assertAlmostEqual(self.sketch.Constraints[-1].Value, math.pi / 2)
        self._assertSolvedWithoutRedundancy()
        self.assertAlmostEqual(self._endAngle(geoId), 180.0, places=4)

    def testPerpendicularEnds(self):
        geoId = self.sketch.addGeometry(makeBSpline(LOOP_POLES), False)
        self.sketch.addConstraint(Sketcher.Constraint("Perpendicular", geoId, 1, geoId, 2))
        self._assertSolvedWithoutRedundancy()
        self.assertAlmostEqual(self._endAngle(geoId), 90.0, places=4)


if __name__ == "__main__":
    unittest.main()
