# SPDX-License-Identifier: LGPL-2.1-or-later
"""DXF export of radius and diameter dimensions that were never drawn.

The exporter took the direction of the dimension line from the arrow positions
that the Gui saves when it draws the dimension. Without the Gui (or before the
page was shown) there are none, and the exported radius and diameter
dimensions collapsed onto the circle's center.
"""

import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import Part
import TechDraw

from .TechDrawTestUtilities import createPageWithSVGTemplate


def _dimensions(path):
    """The DIMENSION entities of a DXF file as {layer: {group code: value}}."""
    lines = path.read_text(encoding="utf-8").splitlines()
    pairs = [(int(code.strip()), value.strip()) for code, value in zip(lines[::2], lines[1::2])]
    result = {}
    current = None
    for code, value in pairs:
        if code == 0:
            current = {} if value == "DIMENSION" else None
        elif current is not None:
            current.setdefault(code, value)
            if code == 8:
                result[value] = current
    return result


class DrawDxfRadialDimTest(unittest.TestCase):
    def setUp(self):
        if App.GuiUp:
            # the Gui may have drawn the dimensions and saved their arrow positions
            self.skipTest("console mode only")
        self.directory = tempfile.TemporaryDirectory(prefix="FreeCADDxfRadialDim-")
        self.addCleanup(self.directory.cleanup)
        self.doc = App.newDocument("DxfRadialDim")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Circle")
        self.source.Shape = Part.makeCircle(4, App.Vector(30, 10, 0))
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.X = 100
        self.view.Y = 100
        self.doc.recompute()

    def _addDimension(self, dimType, x, y):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", dimType)
        self.page.addView(dimension)
        dimension.Type = dimType
        dimension.References2D = [(self.view, "Edge0")]
        dimension.X = x
        dimension.Y = y
        return dimension

    def _point(self, entity, xCode):
        return App.Vector(float(entity[xCode]), float(entity[xCode + 10]), 0)

    def testRadiusAndDiameter(self):
        self._addDimension("Radius", 10, 10)
        self._addDimension("Diameter", -10, 10)
        self.doc.recompute()
        path = Path(self.directory.name) / "page.dxf"
        TechDraw.writeDXFPage(self.page, str(path))
        dimensions = _dimensions(path)
        # the circle is the only geometry, so it is centred on the view position
        center = App.Vector(100, 100, 0)

        radius = dimensions["Radius"]
        self.assertLess((self._point(radius, 10) - center).Length, 1e-6)
        arcPoint = self._point(radius, 15)
        self.assertAlmostEqual((arcPoint - center).Length, 4, places=6)
        # on the side of the label
        towardsLabel = App.Vector(1, 1, 0).normalize()
        self.assertLess((arcPoint - center - towardsLabel * 4).Length, 1e-6)

        diameter = dimensions["Diameter"]
        end1 = self._point(diameter, 10)
        end2 = self._point(diameter, 15)
        self.assertAlmostEqual((end1 - end2).Length, 8, places=6)
        self.assertLess(((end1 + end2) * 0.5 - center).Length, 1e-6)


if __name__ == "__main__":
    unittest.main()
