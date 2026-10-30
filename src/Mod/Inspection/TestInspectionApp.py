# SPDX-License-Identifier: LGPL-2.1-or-later

"""App-level regression tests for the Inspection module."""

import unittest

import FreeCAD as App
import Inspection  # noqa: F401  (registers Inspection::Feature)
import Mesh
import Points


class TestInspectionFeature(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TestInspectionApp")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_mesh_and_points_inspection_finishes(self):
        """Mesh/points inspection runs multithreaded; it used to hang without a GUI."""
        mesh = self.doc.addObject("Mesh::Feature", "Mesh")
        mesh.Mesh = Mesh.createBox(1, 1, 1)
        pts = self.doc.addObject("Points::Feature", "Points")
        pts.Points = Points.Points([App.Vector(0.5, 0.5, 0.5)])
        insp = self.doc.addObject("Inspection::Feature", "Inspection")
        insp.SearchRadius = 0.05

        insp.Actual = mesh
        insp.Nominals = [mesh]
        self.doc.recompute()
        self.assertTrue(insp.isValid())
        self.assertEqual(len(insp.Distances), mesh.Mesh.CountPoints)
        for dist in insp.Distances:
            self.assertAlmostEqual(dist, 0.0, places=5)

        insp.Actual = pts
        insp.Nominals = [mesh, pts]
        self.doc.recompute()
        self.assertTrue(insp.isValid())
        self.assertEqual(len(insp.Distances), 1)
