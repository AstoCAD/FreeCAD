# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw.edgeWalker, findOuterWire and scrubEdges ignore null edges.

An empty Part.Edge() in the edge list was passed on to the edge scrubbing code,
which crashed with an access violation.
"""

import unittest

import FreeCAD
import Part
import TechDraw


def _square(size=10.0):
    v = [
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(size, 0, 0),
        FreeCAD.Vector(size, size, 0),
        FreeCAD.Vector(0, size, 0),
    ]
    return [Part.makeLine(v[i], v[(i + 1) % 4]) for i in range(4)]


class DrawEdgeWalkerNullEdgeTest(unittest.TestCase):
    def testOnlyNullEdge(self):
        self.assertIsNone(TechDraw.scrubEdges([Part.Edge()]))
        self.assertIsNone(TechDraw.findOuterWire([Part.Edge()]))
        self.assertIsNone(TechDraw.edgeWalker([Part.Edge()]))

    def testNullEdgeAmongEdges(self):
        edges = [Part.Edge()] + _square()

        scrubbed = TechDraw.scrubEdges(edges)
        self.assertEqual(len(scrubbed), 4)

        outer = TechDraw.findOuterWire(edges)
        self.assertIsNotNone(outer)
        self.assertTrue(outer.isClosed())
        self.assertAlmostEqual(outer.Length, 40.0, places=6)

        wires = TechDraw.edgeWalker(edges)
        self.assertTrue(wires)
        for wire in wires:
            self.assertAlmostEqual(wire.Length, 40.0, places=6)


if __name__ == "__main__":
    unittest.main()
