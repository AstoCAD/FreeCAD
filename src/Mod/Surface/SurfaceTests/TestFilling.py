# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest

import FreeCAD as App
import Part  # noqa: F401  (registers the Part features)
import Surface  # noqa: F401  (registers Surface::Filling)


class TestFilling(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TestFilling")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def testSingleClosedBoundaryEdge(self):
        """A single closed boundary edge (a circle) bounds the face"""
        # The face was only built for at least two boundary edges.
        circle = self.doc.addObject("Part::Circle", "Circle")
        circle.Radius = 5
        filling = self.doc.addObject("Surface::Filling", "Filling")
        filling.BoundaryEdges = [(circle, "Edge1")]
        self.doc.recompute()
        self.assertNotIn("Invalid", filling.State)
        self.assertFalse(filling.Shape.isNull())
        self.assertTrue(filling.Shape.isValid())
        self.assertAlmostEqual(filling.Shape.Area, 25 * 3.141592653589793, delta=0.1)

    def testSingleOpenBoundaryEdge(self):
        """A single open boundary edge cannot bound a face"""
        line = self.doc.addObject("Part::Line", "Line")
        filling = self.doc.addObject("Surface::Filling", "Filling")
        filling.BoundaryEdges = [(line, "Edge1")]
        self.doc.recompute()
        self.assertIn("Invalid", filling.State)
