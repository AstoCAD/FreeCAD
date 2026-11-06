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

import math
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


class FileTypeRegistrationTest(unittest.TestCase):
    """Every module registered as an importer or exporter must be installed."""

    @staticmethod
    def _modules(types):
        modules = set()
        for value in types.values():
            modules.update(value if isinstance(value, (list, tuple)) else [value])
        return modules

    def testRegisteredModulesExist(self):
        import importlib.util
        import sys

        modules = self._modules(App.getImportType()) | self._modules(App.getExportType())
        self.assertIn("Import", modules)
        for module in sorted(modules):
            top = module.split(".")[0]
            with self.subTest(module=module):
                # Only locate the top-level module: nothing gets imported.
                self.assertTrue(top in sys.modules or importlib.util.find_spec(top) is not None)


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

    def testSingleNonShapeObjectIsRejected(self):
        """Passing a single object without a shape must raise, not crash"""
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        with self.assertRaises(TypeError):
            Import.writeDXFObject(group, self.fileName)


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


class DxfImportEllipseTest(unittest.TestCase):
    """The start and end parameters of a DXF ELLIPSE must be kept"""

    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportDxfImportEllipseTest.dxf")
        self.paramPath = "User parameter:BaseApp/Preferences/Mod/Import/TestDxfImportEllipse"
        param = App.ParamGet(self.paramPath)
        param.SetInt("DxfImportMode", 2)  # individual shapes
        param.SetBool("dxfUseDraftVisGroups", False)
        param.SetBool("dxfGetOriginalColors", False)
        param.SetFloat("dxfScaling", 1.0)
        self.doc = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        App.ParamGet("User parameter:BaseApp/Preferences/Mod/Import").RemGroup(
            "TestDxfImportEllipse"
        )
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def _import(self, start, end, normalZ=1.0):
        # ellipse centered at (1, 2), major axis 5 along +Y, minor radius 2
        records = ["0", "SECTION", "2", "ENTITIES",
                   "0", "ELLIPSE", "8", "0",
                   "10", "1.0", "20", "2.0", "30", "0.0",
                   "11", "0.0", "21", "5.0", "31", "0.0",
                   "210", "0.0", "220", "0.0", "230", str(normalZ),
                   "40", "0.4", "41", str(start), "42", str(end),
                   "0", "ENDSEC", "0", "EOF"]  # fmt: skip
        with open(self.fileName, "w", encoding="utf-8") as f:
            f.write("\n".join(records) + "\n")
        Import.readDXF(self.fileName, self.doc.Name, True, self.paramPath)
        edges = [e for o in self.doc.Objects if hasattr(o, "Shape") for e in o.Shape.Edges]
        self.assertEqual(len(edges), 1)
        return edges[0]

    @staticmethod
    def _point(t, normalZ=1.0):
        # DXF ellipse parameter t, counter-clockwise from the major axis around the
        # extrusion direction: center + cos(t) * major + sin(t) * ratio * (normal x major)
        return App.Vector(1.0 - normalZ * 2.0 * math.sin(t), 2.0 + 5.0 * math.cos(t), 0.0)

    def _assertEnds(self, edge, start, end, normalZ=1.0):
        ends = [edge.valueAt(edge.FirstParameter), edge.valueAt(edge.LastParameter)]
        for t in (start, end):
            self.assertTrue(
                any(p.distanceToPoint(self._point(t, normalZ)) < 1e-6 for p in ends),
                "no arc end at parameter {}".format(t),
            )

    def testEllipticalArc(self):
        import Part

        edge = self._import(0.3, 2.0)
        self.assertFalse(edge.isClosed())
        expected = Part.ArcOfEllipse(Part.Ellipse(App.Vector(), 5, 2), 0.3, 2.0).toShape()
        self.assertAlmostEqual(edge.Length, expected.Length, places=6)
        self._assertEnds(edge, 0.3, 2.0)

    def testEllipticalArcAcrossStartOfParameterRange(self):
        import Part

        edge = self._import(5.0, 1.0)
        self.assertFalse(edge.isClosed())
        expected = Part.ArcOfEllipse(
            Part.Ellipse(App.Vector(), 5, 2), 5.0, 1.0 + 2 * math.pi
        ).toShape()
        self.assertAlmostEqual(edge.Length, expected.Length, places=6)
        self._assertEnds(edge, 5.0, 1.0)

    def testEllipticalArcExtrudedDownwards(self):
        # an extrusion direction of -Z (mirrored geometry) reverses the parameter direction
        import Part

        edge = self._import(0.3, 2.0, normalZ=-1.0)
        self.assertFalse(edge.isClosed())
        expected = Part.ArcOfEllipse(Part.Ellipse(App.Vector(), 5, 2), 0.3, 2.0).toShape()
        self.assertAlmostEqual(edge.Length, expected.Length, places=6)
        self._assertEnds(edge, 0.3, 2.0, normalZ=-1.0)
        # the arc goes through its own middle, not through the mirrored one
        middle = Part.Vertex(self._point(1.15, normalZ=-1.0))
        self.assertLess(edge.distToShape(middle)[0], 1e-6)

    def testFullEllipse(self):
        for end in (2 * math.pi, 6.28318):
            for o in self.doc.Objects:
                self.doc.removeObject(o.Name)
            edge = self._import(0.0, end)
            self.assertTrue(edge.isClosed())


class DxfImportLayerTest(unittest.TestCase):
    """Layers must be created in the target document, even if it is not the active one"""

    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportDxfImportLayerTest.dxf")
        self.paramPath = "User parameter:BaseApp/Preferences/Mod/Import/TestDxfImportLayer"
        param = App.ParamGet(self.paramPath)
        param.SetInt("DxfImportMode", 2)  # individual shapes
        param.SetBool("dxfUseDraftVisGroups", True)
        param.SetBool("dxfGetOriginalColors", False)
        param.SetFloat("dxfScaling", 1.0)
        self.prevActive = App.ActiveDocument
        self.target = App.newDocument()
        self.other = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.other.Name)
        App.closeDocument(self.target.Name)
        if self.prevActive is not None:
            App.setActiveDocument(self.prevActive.Name)
        App.ParamGet("User parameter:BaseApp/Preferences/Mod/Import").RemGroup(
            "TestDxfImportLayer"
        )
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def testLayerIsCreatedInTargetDocument(self):
        records = ["0", "SECTION", "2", "ENTITIES",
                   "0", "LINE", "8", "MyLayer",
                   "10", "0.0", "20", "0.0", "30", "0.0",
                   "11", "1.0", "21", "0.0", "31", "0.0",
                   "0", "ENDSEC", "0", "EOF"]  # fmt: skip
        with open(self.fileName, "w", encoding="utf-8") as f:
            f.write("\n".join(records) + "\n")
        App.setActiveDocument(self.other.Name)
        Import.readDXF(self.fileName, self.target.Name, True, self.paramPath)
        self.assertEqual(App.ActiveDocument.Name, self.other.Name)
        self.assertEqual(len(self.other.Objects), 0)
        layers = [o for o in self.target.Objects if o.Label == "MyLayer"]
        self.assertEqual(len(layers), 1)
        self.assertEqual(len(layers[0].Group), 1)


class DxfExportDegenerateEdgeTest(unittest.TestCase):
    """An OCCT exception while exporting a degenerate shape must not terminate the application"""

    def setUp(self):
        self.fileName = os.path.join(tempfile.gettempdir(), "ImportDxfExportDegenerateEdgeTest.dxf")
        self.doc = App.newDocument()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def testTinyLine(self):
        import Part

        feature = self.doc.addObject("Part::Feature", "TinyLine")
        # Shorter than the precision: OCCT builds an edge without a usable curve
        feature.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(1e-8, 0, 0))
        self.doc.recompute()
        for version in (12, 14):
            for polyline in (False, True):
                with self.subTest(version=version, polyline=polyline):
                    try:
                        Import.writeDXFObject([feature], self.fileName, version, polyline)
                    except Exception:
                        pass  # an error is fine, a crash is not
                    try:
                        Import.writeDXFShape([feature.Shape], self.fileName, version, polyline)
                    except Exception:
                        pass


class ImportCompoundWithoutSolidsTest(unittest.TestCase):
    """The legacy importer (no link groups) dropped compounds without solids or shells"""

    def setUp(self):
        self.doc = App.newDocument()
        self.files = []
        self.igesParam = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Part/IGES")
        self.brepMode = self.igesParam.GetBool("BrepMode", False)
        # write IGES in face mode: a solid becomes a group of free faces
        self.igesParam.SetBool("BrepMode", False)

    def tearDown(self):
        self.igesParam.SetBool("BrepMode", self.brepMode)
        App.closeDocument(self.doc.Name)
        for fileName in self.files:
            if os.path.exists(fileName):
                os.remove(fileName)

    def _export(self, shape, ext):
        feature = self.doc.addObject("Part::Feature", "Shape")
        feature.Shape = shape
        self.doc.recompute()
        fileName = os.path.join(tempfile.gettempdir(), "ImportCompoundWithoutSolidsTest." + ext)
        self.files.append(fileName)
        Import.export([feature], fileName)
        return fileName

    def _import(self, fileName, merge):
        doc = App.newDocument()
        try:
            Import.insert(fileName, doc.Name, useLinkGroup=False, merge=merge)
            shapes = [o.Shape for o in doc.Objects if o.isDerivedFrom("Part::Feature")]
            return [(len(s.Faces), len(s.Edges), round(s.Area, 6)) for s in shapes]
        finally:
            App.closeDocument(doc.Name)

    def testIgesFaces(self):
        import Part

        fileName = self._export(Part.makeBox(1, 2, 3), "iges")
        for merge in (False, True):
            with self.subTest(merge=merge):
                self.assertEqual(self._import(fileName, merge), [(6, 24, 22.0)])

    def testStepWire(self):
        import Part

        # STEP stores a wire as a compound of its edges
        wire = Part.Wire(Part.makePolygon([(0, 0, 0), (1, 0, 0), (1, 1, 0)]))
        fileName = self._export(wire, "step")
        self.assertEqual(self._import(fileName, False), [(0, 2, 0.0)])


class StepMergeLinkGroupTest(unittest.TestCase):
    """Merging an imported link group must not leave dangling objects in the color list."""

    def setUp(self):
        self.doc = App.newDocument()
        self.fileName = os.path.join(tempfile.gettempdir(), "StepMergeLinkGroupTest.step")

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        if os.path.exists(self.fileName):
            os.remove(self.fileName)

    def testMergeTwoFreeShapes(self):
        box = self.doc.addObject("Part::Box", "Box")
        cylinder = self.doc.addObject("Part::Cylinder", "Cylinder")
        cylinder.Placement.Base = App.Vector(20, 0, 0)
        self.doc.recompute()
        Import.export([box, cylinder], self.fileName)

        doc = App.newDocument()
        try:
            colors = Import.insert(self.fileName, doc.Name, merge=True, useLinkGroup=True)
            features = [o for o in doc.Objects if o.isDerivedFrom("Part::Feature")]
            self.assertEqual(len(features), 1)
            self.assertEqual(len(features[0].Shape.Solids), 2)
            for feature, _ in colors or []:
                self.assertEqual(feature.Name, features[0].Name)
        finally:
            App.closeDocument(doc.Name)
