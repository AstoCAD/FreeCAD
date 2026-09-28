# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

import FreeCAD
import Part

from SprocketFeature import Sprocket
from fcsprocket import fcsprocket, sprocket


class TestSprocket(unittest.TestCase):
    def test_iso_606_roller_diameters(self):
        # ISO 606 B-series roller diameters, in millimetres.
        expected = {
            "ISO 606 06B": 6.35,
            "ISO 606 08B": 8.51,
            "ISO 606 10B": 10.16,
            "ISO 606 12B": 12.07,
            "ISO 606 16B": 15.88,
            "ISO 606 20B": 19.05,
            "ISO 606 24B": 25.40,
        }
        for pitch_inches, diameter_inches, _, name in Sprocket.SprocketReferenceRollerTable.values():
            if name not in expected:
                continue
            with self.subTest(name=name):
                self.assertAlmostEqual(diameter_inches * 25.4, expected[name])
                wire = fcsprocket.FCWireBuilder()
                sprocket.CreateSprocket(wire, pitch_inches * 25.4, 50, expected[name])
                shape = Part.Wire([segment.toShape() for segment in wire.wire])
                self.assertTrue(shape.isValid())
                self.assertTrue(shape.isClosed())
