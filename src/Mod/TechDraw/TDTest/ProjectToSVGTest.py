# SPDX-License-Identifier: LGPL-2.1-or-later
"""The hidden line groups written by TechDraw.projectToSVG are dashed.

Their default stroke-dasharray values carried a stray ")" ("0.2, 0.1)"), which
is not a valid dash array, so SVG viewers ignored it and drew hidden lines solid.
"""

import re
import unittest
import xml.etree.ElementTree as ET

import FreeCAD
import Part
import TechDraw


def isValidDashArray(value):
    """SVG <dasharray>: "none" or non-negative numbers separated by commas and/or spaces."""
    if value.strip() == "none":
        return True
    items = re.split(r"\s*,\s*|\s+", value.strip())
    try:
        return all(float(item) >= 0.0 for item in items)
    except ValueError:
        return False


class ProjectToSVGTest(unittest.TestCase):
    def testHiddenLineDashArraysAreValid(self):
        # a sphere below a plate: hidden hard edges (H) and a hidden outline (HO)
        plate = Part.makeBox(20, 20, 5, FreeCAD.Vector(-10, -10, 10))
        sphere = Part.makeSphere(3, FreeCAD.Vector(0, 0, 0))
        shape = Part.makeCompound([plate, sphere])
        svg = TechDraw.projectToSVG(shape, FreeCAD.Vector(0, 0, 1), "ShowHiddenLines")

        root = ET.fromstring("<svg>" + svg + "</svg>")
        dashArrays = [g.get("stroke-dasharray") for g in root.iter("g") if g.get("stroke-dasharray")]
        self.assertEqual(len(dashArrays), 2, svg)
        for value in dashArrays:
            self.assertTrue(isValidDashArray(value), "invalid stroke-dasharray: " + repr(value))

    def testUserDashArrayIsKept(self):
        box = Part.makeBox(10, 20, 30)
        svg = TechDraw.projectToSVG(
            box, FreeCAD.Vector(1, 1, 1), "ShowHiddenLines", hStyle={"stroke-dasharray": "3, 1"}
        )
        root = ET.fromstring("<svg>" + svg + "</svg>")
        dashArrays = [g.get("stroke-dasharray") for g in root.iter("g") if g.get("stroke-dasharray")]
        self.assertEqual(dashArrays, ["3, 1"])


if __name__ == "__main__":
    unittest.main()
