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


class DxfImportOcsTest(unittest.TestCase):
    """2D entities of a DXF file are given in their Object Coordinate System (#17046)"""

    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportDxfImportOcsTest.dxf")
        self.paramPath = "User parameter:BaseApp/Preferences/Mod/Import/TestDxfImportOcs"
        param = App.ParamGet(self.paramPath)
        param.SetInt("DxfImportMode", 2)  # individual shapes
        param.SetBool("dxfUseDraftVisGroups", False)
        param.SetBool("dxfGetOriginalColors", False)
        param.SetFloat("dxfScaling", 1.0)
        self.doc = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        App.ParamGet("User parameter:BaseApp/Preferences/Mod/Import").RemGroup(
            "TestDxfImportOcs"
        )
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def _import(self, entity):
        records = ["0", "SECTION", "2", "ENTITIES"] + entity + ["0", "ENDSEC", "0", "EOF"]
        with open(self.fileName, "w", encoding="utf-8") as f:
            f.write("\n".join(records) + "\n")
        Import.readDXF(self.fileName, self.doc.Name, True, self.paramPath)
        shapes = [o.Shape for o in self.doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        self.assertEqual(len(shapes), 1)
        return shapes[0].BoundBox

    @staticmethod
    def _lwpolyline(normal):
        # vertices (1, 0), (2, 0), (2, 1) in the OCS
        return [
            "0", "LWPOLYLINE", "8", "0", "90", "3", "70", "0",
            "10", "1.0", "20", "0.0",
            "10", "2.0", "20", "0.0",
            "10", "2.0", "20", "1.0",
            "210", str(normal[0]), "220", str(normal[1]), "230", str(normal[2]),
        ]  # fmt: skip

    def testLwPolylineWithReversedNormal(self):
        box = self._import(self._lwpolyline((0.0, 0.0, -1.0)))
        # the OCS X axis of a polyline with normal -Z is the WCS -X axis
        self.assertAlmostEqual(box.XMin, -2.0, places=6)
        self.assertAlmostEqual(box.XMax, -1.0, places=6)
        self.assertAlmostEqual(box.YMin, 0.0, places=6)
        self.assertAlmostEqual(box.YMax, 1.0, places=6)

    def testLwPolylineWithNegativeXNormal(self):
        box = self._import(self._lwpolyline((-1.0, 0.0, 0.0)))
        # arbitrary axis algorithm: OCS X = WCS Z x N = -Y, OCS Y = N x OCS X = +Z
        self.assertAlmostEqual(box.XMin, 0.0, places=6)
        self.assertAlmostEqual(box.XMax, 0.0, places=6)
        self.assertAlmostEqual(box.YMin, -2.0, places=6)
        self.assertAlmostEqual(box.YMax, -1.0, places=6)
        self.assertAlmostEqual(box.ZMin, 0.0, places=6)
        self.assertAlmostEqual(box.ZMax, 1.0, places=6)

    def testPolylineWithReversedNormal(self):
        entity = ["0", "POLYLINE", "8", "0", "66", "1", "70", "0",
                  "210", "0.0", "220", "0.0", "230", "-1.0"]  # fmt: skip
        for x, y in ((1.0, 0.0), (2.0, 0.0), (2.0, 1.0)):
            entity += ["0", "VERTEX", "8", "0", "10", str(x), "20", str(y), "30", "0.0"]
        entity += ["0", "SEQEND", "8", "0"]
        box = self._import(entity)
        self.assertAlmostEqual(box.XMin, -2.0, places=6)
        self.assertAlmostEqual(box.XMax, -1.0, places=6)
