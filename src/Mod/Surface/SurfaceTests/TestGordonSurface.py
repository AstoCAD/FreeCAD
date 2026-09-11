# SPDX-License-Identifier: LGPL-2.1-or-later

import os
import tempfile
import unittest

import FreeCAD as App
import Part
import Surface


class TestGordonSurface(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("CurveNetworkTest")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def curve(self, points):
        obj = self.doc.addObject("Surface::FreehandBSpline", "Curve")
        obj.Points = [App.Vector(*p) for p in points]
        self.doc.recompute()
        self.assertTrue(obj.isValid(), obj.getStatusString())
        return obj

    def network(self, curved=True):
        def z(x, y):
            return (0.03 * x * x + 0.07 * x * y - 0.02 * y * y) if curved else 0

        profiles, guides = [], []
        # Interpolation parameters deliberately differ between curves.
        for y in (0, 4, 10):
            profiles.append(self.curve([(x, y, z(x, y)) for x in (0, 2, 6, 10)]))
        for x in (0, 6, 10):
            guides.append(self.curve([(x, y, z(x, y)) for y in (0, 4, 8, 10)]))
        surface = self.doc.addObject("Surface::GordonSurface", "Gordon")
        surface.Profiles = [(p, [""]) for p in profiles]
        surface.Guides = [(g, [""]) for g in guides]
        surface.Tolerance = 0.01
        self.doc.recompute()
        return profiles, guides, surface

    def assertNetwork(self, surface, profiles, guides):
        self.assertTrue(surface.isValid(), surface.getStatusString())
        self.assertEqual(len(surface.Shape.Faces), 1)
        self.assertTrue(surface.Shape.isValid())
        self.assertLessEqual(surface.ApproximationError, surface.Tolerance)
        for curve in profiles + guides:
            for point in curve.Shape.discretize(35):
                self.assertLessEqual(
                    surface.Shape.distToShape(Part.Vertex(point))[0], surface.Tolerance * 1.1
                )

    def test_planar_gordon(self):
        profiles, guides, surface = self.network(False)
        self.assertNetwork(surface, profiles, guides)
        self.assertAlmostEqual(surface.Shape.Area, 100, places=5)

    def test_curved_gordon(self):
        profiles, guides, surface = self.network()
        self.assertNetwork(surface, profiles, guides)

    def test_unordered_network(self):
        profiles, guides, surface = self.network(False)
        surface.Profiles = [(profiles[i], [""]) for i in (1, 2, 0)]
        surface.Guides = [(guides[i], [""]) for i in (2, 0, 1)]
        self.doc.recompute()
        self.assertNetwork(surface, profiles, guides)

    def test_reversed_network_and_subedges(self):
        profiles, guides, surface = self.network(False)
        for obj in (profiles[1], guides[2]):
            obj.Points = list(reversed(obj.Points))
        surface.Profiles = [(obj, ["Edge1"]) for obj in profiles]
        surface.Guides = [(obj, ["Edge1"]) for obj in guides]
        self.doc.recompute()
        self.assertNetwork(surface, profiles, guides)

    def test_missing_intersection_and_recovery(self):
        profiles, guides, surface = self.network(False)
        guides[1].Placement.Base = App.Vector(0, 0, 10)
        self.doc.recompute()
        self.assertFalse(surface.isValid())
        self.assertTrue(surface.Shape.isNull())
        guides[1].Placement.Base = App.Vector()
        self.doc.recompute()
        self.assertNetwork(surface, profiles, guides)

    def test_flip_and_save_restore(self):
        profiles, guides, surface = self.network(False)
        normal = surface.Shape.Faces[0].normalAt(0.5, 0.5)
        surface.FlipNormal = True
        self.doc.recompute()
        self.assertLess(normal.dot(surface.Shape.Faces[0].normalAt(0.5, 0.5)), -0.99)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Network.FCStd")
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.doc.Gordon.touch()
            self.doc.recompute()
            self.assertTrue(self.doc.Gordon.isValid(), self.doc.Gordon.getStatusString())
            self.assertEqual(len(self.doc.Gordon.Shape.Faces), 1)
            App.closeDocument(self.doc.Name)
            self.doc = App.newDocument("CurveNetworkTest")
