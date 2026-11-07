# SPDX-License-Identifier: LGPL-2.1-or-later
"""DXF export of three point angle dimensions.

writeDXFPage exported the Angle dimensions but left out the Angle3Pt ones, so
they were missing from the DXF file.
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


class DrawDxfAngle3PtDimTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="FreeCADDxfAngle3PtDim-")
        self.addCleanup(self.directory.cleanup)
        self.doc = App.newDocument("DxfAngle3PtDim")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Corner")
        self.source.Shape = Part.makeCompound([
            Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
            Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 10, 0))])
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

    def _vertex(self, point):
        for i, vertex in enumerate(self.source.Shape.Vertexes):
            if (vertex.Point - point).Length < 1e-9:
                return "Vertex%d" % (i + 1)
        self.fail("no vertex at %s" % point)

    def _addDimension(self, name, dimType, references3d):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", name)
        self.page.addView(dimension)
        dimension.Type = dimType
        dimension.References2D = [(self.view, "")]
        dimension.References3D = [(self.source, sub) for sub in references3d]
        dimension.X = 5
        dimension.Y = 5
        return dimension

    def testAngle3PtIsExported(self):
        angle = self._addDimension("Angle", "Angle", ["Edge1", "Edge2"])
        angle3pt = self._addDimension("ThreePoint", "Angle3Pt", [
            self._vertex(App.Vector(10, 0, 0)),
            self._vertex(App.Vector(0, 0, 0)),
            self._vertex(App.Vector(0, 10, 0))])
        self.doc.recompute()
        self.assertAlmostEqual(angle.getRawValue(), 90, places=6)
        self.assertAlmostEqual(angle3pt.getRawValue(), 90, places=6)
        path = Path(self.directory.name) / "page.dxf"
        TechDraw.writeDXFPage(self.page, str(path))
        dimensions = _dimensions(path)
        self.assertIn("Angle", dimensions)
        self.assertIn("ThreePoint", dimensions)
        # the same legs and apex give the same angular dimension
        for code in (13, 23, 14, 24, 15, 25, 70):
            self.assertEqual(dimensions["ThreePoint"].get(code), dimensions["Angle"].get(code), code)


if __name__ == "__main__":
    unittest.main()
