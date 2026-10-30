# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw.nearestFraction handles negative and non-finite values.

The continued fraction loop expects a positive value: -0.3 returned (42, -139).
NaN never left the loop (the call hung) and infinity ended in an integer
division by zero (the process crashed).
"""

import unittest

import TechDraw


class DrawNearestFractionTest(unittest.TestCase):
    def testPositiveValues(self):
        self.assertEqual(TechDraw.nearestFraction(0.5), (1, 2))
        self.assertEqual(TechDraw.nearestFraction(0.25), (1, 4))
        self.assertEqual(TechDraw.nearestFraction(0.3), (3, 10))
        self.assertEqual(TechDraw.nearestFraction(2.0), (2, 1))
        self.assertEqual(TechDraw.nearestFraction(0.0), (0, 1))

    def testNegativeValues(self):
        self.assertEqual(TechDraw.nearestFraction(-0.5), (-1, 2))
        self.assertEqual(TechDraw.nearestFraction(-0.3), (-3, 10))
        self.assertEqual(TechDraw.nearestFraction(-2.0), (-2, 1))

    def testInfiniteValue(self):
        for value in (float("inf"), float("-inf"), 1e300):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    TechDraw.nearestFraction(value)

    def testNanValue(self):
        with self.assertRaises(ValueError):
            TechDraw.nearestFraction(float("nan"))


if __name__ == "__main__":
    unittest.main()
