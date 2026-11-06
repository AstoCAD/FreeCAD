# SPDX-License-Identifier: LGPL-2.1-or-later
"""DXF export: the block of a linear dimension keeps its extension lines perpendicular."""

import tempfile
import time
import unittest
from pathlib import Path

import FreeCAD as App
import Part
import TechDraw
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDxfLinearDimBlockTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DxfLinearDimBlock")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Geometry")
        self.source.Shape = Part.makeCompound([
            Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
            Part.makeLine(App.Vector(0, 20, 0), App.Vector(10, 30, 0))])
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
        deadline = time.monotonic() + 20
        while not self.view.getVisibleEdges() or "Up-to-date" not in self.view.State:
            self.assertLess(time.monotonic(), deadline, self.view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

    def _addDimension(self, name, edge, x, y):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", name)
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(self.view, "")]
        dimension.References3D = [(self.source, edge)]
        # text (and so the dimension line) placed well beyond the end of the measured span
        dimension.X = x
        dimension.Y = y
        return dimension

    @staticmethod
    def _blockLines(path, blockName):
        lines = path.read_text(encoding="utf-8").splitlines()
        pairs = [(int(code.strip()), value.strip()) for code, value in zip(lines[::2], lines[1::2])]
        result = []
        inBlock = False
        entity = None
        current = None
        for code, value in pairs:
            if code == 0:
                entity = value
                if current is not None:
                    result.append(current)
                    current = None
                if value == "ENDBLK":
                    inBlock = False
                elif inBlock and value == "LINE":
                    current = {}
            elif code == 2 and entity == "BLOCK" and value == blockName:
                inBlock = True
            elif current is not None and code in (10, 20, 11, 21):
                current[code] = float(value)
        return [
            (App.Vector(line[10], line[20], 0), App.Vector(line[11], line[21], 0))
            for line in result
        ]

    def testExtensionLinesPerpendicularToDimensionLine(self):
        dimensions = [
            self._addDimension("Horizontal", "Edge1", 40, 15),
            self._addDimension("Oblique", "Edge2", 40, 40),
        ]
        self.doc.recompute()
        for dimension in dimensions:
            self.assertIn("Up-to-date", dimension.State)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dims.dxf"
            TechDraw.writeDXFPage(self.page, str(path))
            for dimension in dimensions:
                with self.subTest(dimension=dimension.Name):
                    blockLines = self._blockLines(path, "*" + dimension.Name)
                    # extension line 2, extension line 1, dimension line, then the arrows
                    self.assertGreaterEqual(len(blockLines), 3)
                    ext2, ext1, dimLine = blockLines[:3]
                    dimDir = dimLine[1] - dimLine[0]
                    self.assertAlmostEqual(dimDir.Length, 10 * (1 if dimension.Name == "Horizontal" else 2**0.5), 6)
                    dimDir.normalize()
                    for ext in (ext1, ext2):
                        extDir = ext[1] - ext[0]
                        self.assertGreater(extDir.Length, 1.0)
                        extDir.normalize()
                        self.assertAlmostEqual(extDir.dot(dimDir), 0.0, 6)
                    # the dimension line joins the ends of the extension lines
                    self.assertLess((dimLine[0] - ext1[1]).Length, 1e-6)
                    self.assertLess((dimLine[1] - ext2[1]).Length, 1e-6)


if __name__ == "__main__":
    unittest.main()
