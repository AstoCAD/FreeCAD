# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
import Part
from fcsprocket import fcsprocket, sprocket

EDGES_PER_TOOTH = 8


class TestSprocket(unittest.TestCase):
    def makeProfile(self, pitch, teeth, roller):
        # Same construction as SprocketFeature.Sprocket.execute()
        builder = fcsprocket.FCWireBuilder()
        sprocket.CreateSprocket(builder, pitch, teeth, roller)
        return Part.Wire([o.toShape() for o in builder.wire])

    def assertToothMatches(self, first, other, angle):
        rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), angle)
        for a, b in zip(first, other):
            self.assertEqual(type(a.Curve).__name__, type(b.Curve).__name__)
            self.assertAlmostEqual(a.Length, b.Length, places=7)
            for t in (0.0, 0.5, 1.0):
                pa = a.valueAt(a.FirstParameter + t * (a.LastParameter - a.FirstParameter))
                pb = b.valueAt(b.FirstParameter + t * (b.LastParameter - b.FirstParameter))
                self.assertLess((rotation.multVec(pa) - pb).Length, 1e-7)

    def testAllTeethHaveTheSameProfile(self):
        """Every tooth is a rotated copy of the first one, including its rising flank"""
        for pitch, teeth, roller in ((12.7, 20, 7.92), (15.875, 13, 10.16)):
            wire = self.makeProfile(pitch, teeth, roller)
            self.assertTrue(wire.isClosed())
            edges = wire.Edges
            self.assertEqual(len(edges), EDGES_PER_TOOTH * teeth)
            first = edges[:EDGES_PER_TOOTH]
            for tooth in (1, teeth // 2, teeth - 1):
                other = edges[EDGES_PER_TOOTH * tooth : EDGES_PER_TOOTH * (tooth + 1)]
                self.assertToothMatches(first, other, -360.0 * tooth / teeth)
