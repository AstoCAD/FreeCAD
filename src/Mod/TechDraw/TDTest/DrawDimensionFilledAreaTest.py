# SPDX-License-Identifier: LGPL-2.1-or-later
"""The filled area of an area dimension with a 3d reference.

With UseActualArea false an area dimension gives the area inside the face's
outer boundary. For a 3d reference this was approximated from a polygon of the
outer wire, which gave 1200 instead of 800 for a 40 x 20 face with a hole and
78.536 for a disc of radius 5. The same dimension with a 2d reference was
right.
"""

import math
import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionFilledAreaTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TDDimensionFilledArea")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.page = createPageWithSVGTemplate(self.doc)

    def areas(self, shape, faceZ):
        """Filled and actual area of the horizontal face at faceZ, by 3d and 2d reference."""
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = shape
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = App.Vector(0, 0, 1)
        view.ScaleType = "Custom"
        view.Scale = 1
        self.doc.recompute()
        faces = ["Face%d" % (i + 1) for i, f in enumerate(shape.Faces)
                 if abs(f.normalAt(0, 0).z) > 0.99 and abs(f.CenterOfMass.z - faceZ) < 1e-6]
        self.assertEqual(len(faces), 1)
        result = {}
        for actual in (False, True):
            for refs in ("3d", "2d"):
                dim = self.doc.addObject("TechDraw::DrawViewDimension", "Area")
                self.page.addView(dim)
                dim.Type = "Area"
                if refs == "3d":
                    dim.References2D = [(view, "")]
                    dim.References3D = [(source, faces[0])]
                else:
                    dim.References2D = [(view, "Face0")]
                dim.UseActualArea = actual
                self.doc.recompute()
                self.assertIn("Up-to-date", dim.State)
                result[(refs, actual)] = dim.getRawValue()
        return result

    def testFaceWithHole(self):
        shape = Part.makeBox(40, 20, 10).cut(
            Part.makeCylinder(4, 12, App.Vector(30, 10, -1)))
        holeArea = math.pi * 16
        for z in (10, 0):
            with self.subTest(z=z):
                areas = self.areas(shape, z)
                self.assertAlmostEqual(areas[("3d", False)], 800, places=6)
                self.assertAlmostEqual(areas[("3d", True)], 800 - holeArea, places=6)
                self.assertAlmostEqual(areas[("2d", False)], 800, places=6)
                self.assertAlmostEqual(areas[("2d", True)], 800 - holeArea, places=6)

    def testDisc(self):
        areas = self.areas(Part.makeCylinder(5, 10), 10)
        self.assertAlmostEqual(areas[("3d", False)], math.pi * 25, places=6)
        self.assertAlmostEqual(areas[("3d", True)], math.pi * 25, places=6)


if __name__ == "__main__":
    unittest.main()
