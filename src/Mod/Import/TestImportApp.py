# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#                                                                         *
#   This file is part of FreeCAD.                                         *
#                                                                         *
#   FreeCAD is free software: you can redistribute it and/or modify it    *
#   under the terms of the GNU Lesser General Public License as           *
#   published by the Free Software Foundation, either version 2.1 of the  *
#   License, or (at your option) any later version.                       *
#                                                                         *
#   FreeCAD is distributed in the hope that it will be useful, but        *
#   WITHOUT ANY WARRANTY; without even the implied warranty of            *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
#   Lesser General Public License for more details.                       *
#                                                                         *
#   You should have received a copy of the GNU Lesser General Public      *
#   License along with FreeCAD. If not, see                               *
#   <https://www.gnu.org/licenses/>.                                      *
#                                                                         *
# **************************************************************************

import os
import re
import tempfile
import unittest
import FreeCAD as App
import Import


class StepExportColorTest(unittest.TestCase):
    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportStepExportColorTest.step")
        self.doc = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def testOutOfRangeAlphaIsClamped(self):
        """An out-of-range alpha must not reach OCCT unchecked (#33758)"""
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()

        # Alpha of 1 - 60 (a transparency given in percent instead of 0..1)
        Import.export([(box, [(0.6, 0.62, 0.7, -59.0)] * 6)], self.fileName)

        with open(self.fileName, encoding="utf-8") as f:
            content = f.read()
        values = [float(v) for v in re.findall(r"SURFACE_STYLE_TRANSPARENT\(([^)]*)\)", content)]
        self.assertTrue(values)
        for value in values:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class DxfSketchExportTest(unittest.TestCase):
    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportDxfSketchExportTest.dxf")
        self.doc = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def _circleCenters(self):
        with open(self.fileName, encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f.read().splitlines()]
        centers = []
        for i in range(1, len(lines)):
            if lines[i] != "CIRCLE" or lines[i - 1] != "0":
                continue
            values = {}
            j = i + 1
            while j + 1 < len(lines) and lines[j] != "0":
                values[lines[j]] = lines[j + 1]
                j += 2
            centers.append((float(values["10"]), float(values["20"])))
        return centers

    def _exportCircleSketch(self, placement):
        import Part

        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.Circle(App.Vector(4, 0, 0), App.Vector(0, 0, 1), 1))
        sketch.Placement = placement
        self.doc.recompute()
        Import.writeDXFObject([sketch], self.fileName)
        centers = self._circleCenters()
        self.assertEqual(len(centers), 1)
        return centers[0]

    def testSketchPlacementIsKept(self):
        """The sketch placement must be applied to the exported geometry (#17962)"""
        placement = App.Placement(App.Vector(2, 3, 0), App.Rotation())
        x, y = self._exportCircleSketch(placement)
        self.assertAlmostEqual(x, 6.0, places=6)
        self.assertAlmostEqual(y, 3.0, places=6)

    def testRotatedSketchPlacementIsKept(self):
        """A sketch rotated around Z keeps its global XY position (#17962)"""
        placement = App.Placement(App.Vector(2, 3, 5), App.Rotation(App.Vector(0, 0, 1), 90))
        x, y = self._exportCircleSketch(placement)
        self.assertAlmostEqual(x, 2.0, places=6)
        self.assertAlmostEqual(y, 7.0, places=6)

    def testVerticalSketchPositionIsKept(self):
        """A sketch on a vertical plane keeps its offset within that plane (#17962)"""
        placement = App.Placement(App.Vector(2, 3, 5), App.Rotation(App.Vector(1, 0, 0), 90))
        x, y = self._exportCircleSketch(placement)
        self.assertAlmostEqual(x, 6.0, places=6)
        self.assertAlmostEqual(y, 5.0, places=6)

    def _points(self):
        with open(self.fileName, encoding="utf-8", errors="replace") as f:
            lines = [line.strip() for line in f.read().splitlines()]
        points = []
        for i in range(1, len(lines)):
            if lines[i] != "POINT" or lines[i - 1] != "0":
                continue
            values = {}
            j = i + 1
            while j + 1 < len(lines) and lines[j] != "0":
                values[lines[j]] = lines[j + 1]
                j += 2
            points.append((round(float(values["10"]), 6), round(float(values["20"]), 6)))
        return points

    def testSketchPointIsExported(self):
        """A sketch point must be exported as a DXF POINT (#30675)"""
        import Part

        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        sketch.addGeometry(Part.Point(App.Vector(3, 4, 0)))
        sketch.Placement = App.Placement(App.Vector(2, 3, 0), App.Rotation())
        self.doc.recompute()
        Import.writeDXFObject([sketch], self.fileName)
        self.assertIn((5.0, 7.0), self._points())

    def testFreeVertexIsExported(self):
        """A free-standing vertex of a shape must be exported as a DXF POINT (#30675)"""
        import Part

        feature = self.doc.addObject("Part::Feature", "Feature")
        feature.Shape = Part.Compound(
            [Part.makeLine((0, 0, 0), (10, 0, 0)), Part.Vertex(App.Vector(3, 4, 0))]
        )
        self.doc.recompute()
        Import.writeDXFObject([feature], self.fileName)
        self.assertIn((3.0, 4.0), self._points())
