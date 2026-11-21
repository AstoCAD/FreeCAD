# SPDX-License-Identifier: LGPL-2.1-or-later
"""TechDraw.nearestFraction handles negative and non-finite values.

The continued fraction loop expects a positive value: -0.3 returned (42, -139).
NaN never left the loop (the call hung) and infinity ended in an integer
division by zero (the process crashed).

The numerator of the fraction fits in an int: 1500000000.5 returned
(-443585805, 999). A page scale of 2^31 or more ended in an integer division
by zero when a template filled in the scale.
"""

import os
import tempfile
import unittest

import FreeCAD
import TechDraw

SCALE_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:freecad="https://www.freecad.org/wiki/index.php?title=Svg_Namespace"
     width="297mm" height="210mm" viewBox="0 0 297 210">
  <text freecad:editable="Scale" freecad:autofill="scale" x="10" y="10"><tspan>1 : 1</tspan></text>
</svg>
"""


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

    def testNumeratorFitsInInt(self):
        self.assertEqual(TechDraw.nearestFraction(1500000000.5), (1500000000, 1))
        self.assertEqual(TechDraw.nearestFraction(-1500000000.5), (-1500000000, 1))
        self.assertEqual(TechDraw.nearestFraction(1000000000.5), (2000000001, 2))
        self.assertEqual(TechDraw.nearestFraction(2147483647.0), (2147483647, 1))

    def testTemplateScaleOfLargePage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "ScaleTemplate.svg")
            with open(path, "w", encoding="utf-8") as svg:
                svg.write(SCALE_TEMPLATE)
            doc = FreeCAD.newDocument("NearestFractionScale")
            try:
                page = doc.addObject("TechDraw::DrawPage", "Page")
                page.Scale = 5e9
                template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
                page.Template = template
                template.Template = path
                self.assertEqual(template.EditableTexts["Scale"], "2147483647 : 1")
            finally:
                FreeCAD.closeDocument(doc.Name)


if __name__ == "__main__":
    unittest.main()
