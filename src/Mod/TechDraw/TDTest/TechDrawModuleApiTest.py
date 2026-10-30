# SPDX-License-Identifier: LGPL-2.1-or-later
"""Errors of the TechDraw module functions reach Python as exceptions.

The module translated C++/OpenCASCADE exceptions only for functions taking
positional arguments. Functions also accepting keywords (projectToSVG) let the
C++ exception escape into the Python interpreter, which aborts the running
script or crashes FreeCAD instead of raising a Python exception.
"""

import unittest

import FreeCAD
import Part
import TechDraw


class TechDrawModuleApiTest(unittest.TestCase):
    def setUp(self):
        self.box = Part.makeBox(10, 10, 10)

    def testProjectToSVG(self):
        svg = TechDraw.projectToSVG(self.box, FreeCAD.Vector(0, 0, 1))
        self.assertIn("<g", svg)

    def testProjectToSVGNullDirectionRaises(self):
        with self.assertRaises(Part.OCCError):
            TechDraw.projectToSVG(self.box, FreeCAD.Vector(0, 0, 0))

    def testProjectToSVGNullDirectionWithKeywordsRaises(self):
        with self.assertRaises(Part.OCCError):
            TechDraw.projectToSVG(
                topoShape=self.box, direction=FreeCAD.Vector(0, 0, 0), type="ShowHiddenLines"
            )

    def testProjectNullDirectionRaises(self):
        # positional-only function, already translated before: kept as a reference
        with self.assertRaises(Part.OCCError):
            TechDraw.project(self.box, FreeCAD.Vector(0, 0, 0))


if __name__ == "__main__":
    unittest.main()
