# SPDX-License-Identifier: LGPL-2.1-or-later
"""Unit tests for the ReverseEngineering module."""

import unittest

import FreeCAD as App
import Points
import ReverseEngineering


def _grid(count):
    """Point cloud of count x count points"""
    return Points.Points([
        App.Vector(i, j, 0.1 * i * j)
        for i in range(count)
        for j in range(count)
    ])


def _tuples(count):
    """count x count points as a list of tuples"""
    return [tuple(point) for point in _grid(count).Points]


class TestApproxSurface(unittest.TestCase):
    def test_empty_input_is_rejected(self):
        # An empty input used to allocate an array of size_t(-1) points
        # with OCCT 8 and crash.
        with self.assertRaises(ValueError):
            ReverseEngineering.approxSurface(Points.Points())
        with self.assertRaises(ValueError):
            ReverseEngineering.approxSurface([])

    def test_too_few_points_are_rejected(self):
        with self.assertRaises(ValueError):
            ReverseEngineering.approxSurface(_grid(5))
        with self.assertRaises(ValueError):
            ReverseEngineering.approxSurface(_tuples(5))

    def test_all_points_are_used(self):
        # 6 x 6 points are exactly enough for the default 6 x 6 poles.
        for data in (_grid(6), _tuples(6)):
            surface = ReverseEngineering.approxSurface(data)
            self.assertEqual(surface.NbUPoles, 6)
            self.assertEqual(surface.NbVPoles, 6)

    def test_larger_grid(self):
        surface = ReverseEngineering.approxSurface(_grid(8))
        self.assertEqual(surface.NbUPoles, 6)
        self.assertEqual(surface.NbVPoles, 6)
        point = surface.value(0.5, 0.5)
        self.assertTrue(0.0 <= point.x <= 7.0)
