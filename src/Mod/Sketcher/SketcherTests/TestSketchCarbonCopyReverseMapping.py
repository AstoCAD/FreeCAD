# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
import math, os, unittest


class TestSketchCarbonCopyReverseMapping(unittest.TestCase):
    def setUp(self):
        location = os.path.dirname(os.path.realpath(__file__))
        self.Doc = FreeCAD.openDocument(
            os.path.join(location, "TestSketchCarbonCopyReverseMapping.FCStd"), True
        )

    def test_CarbonCopyReverseMapping(self):
        r = 10.0
        rad30 = math.radians(30)
        cos30 = math.cos(rad30)
        sin30 = math.sin(rad30)

        expected_geometries_pattern_001 = {
            "Sketch001": {
                0: {"start": FreeCAD.Vector(10, 10, 0), "end": FreeCAD.Vector(20, 10, 0)},
                1: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 + cos30 * r, 10 + sin30 * r, 0),
                },
                2: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 + sin30 * r, 10 + cos30 * r, 0),
                },
                3: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 - sin30 * r, 10 + cos30 * r, 0),
                },
                4: {"location": FreeCAD.Vector(-10, 10, 0)},
                5: {"location": FreeCAD.Vector(10, -10, 0)},
                6: {
                    "start": FreeCAD.Vector(5, 15, 0),
                    "end": FreeCAD.Vector(5 + sin30 * r, 15 + cos30 * r, 0),
                },
                7: {
                    "start": FreeCAD.Vector(15, 15, 0),
                    "end": FreeCAD.Vector(15 - sin30 * r, 15 + cos30 * r, 0),
                },
            },
            "Sketch002": {
                0: {"start": FreeCAD.Vector(-10, 10, 0), "end": FreeCAD.Vector(-20, 10, 0)},
                1: {
                    "start": FreeCAD.Vector(-10, 10, 0),
                    "end": FreeCAD.Vector(-10 - cos30 * r, 10 + sin30 * r, 0),
                },
                2: {
                    "start": FreeCAD.Vector(-10, 10, 0),
                    "end": FreeCAD.Vector(-10 - sin30 * r, 10 + cos30 * r, 0),
                },
                3: {
                    "start": FreeCAD.Vector(-10, 10, 0),
                    "end": FreeCAD.Vector(-10 + sin30 * r, 10 + cos30 * r, 0),
                },
                4: {"location": FreeCAD.Vector(10, 10, 0)},
                5: {"location": FreeCAD.Vector(-10, -10, 0)},
                6: {
                    "start": FreeCAD.Vector(-5, 15, 0),
                    "end": FreeCAD.Vector(-5 - sin30 * r, 15 + cos30 * r, 0),
                },
                7: {
                    "start": FreeCAD.Vector(-15, 15, 0),
                    "end": FreeCAD.Vector(-15 + sin30 * r, 15 + cos30 * r, 0),
                },
            },
            "Sketch003": {
                0: {"start": FreeCAD.Vector(10, -10, 0), "end": FreeCAD.Vector(20, -10, 0)},
                1: {
                    "start": FreeCAD.Vector(10, -10, 0),
                    "end": FreeCAD.Vector(10 + cos30 * r, -10 - sin30 * r, 0),
                },
                2: {
                    "start": FreeCAD.Vector(10, -10, 0),
                    "end": FreeCAD.Vector(10 + sin30 * r, -10 - cos30 * r, 0),
                },
                3: {
                    "start": FreeCAD.Vector(10, -10, 0),
                    "end": FreeCAD.Vector(10 - sin30 * r, -10 - cos30 * r, 0),
                },
                4: {"location": FreeCAD.Vector(-10, -10, 0)},
                5: {"location": FreeCAD.Vector(10, 10, 0)},
                6: {
                    "start": FreeCAD.Vector(5, -15, 0),
                    "end": FreeCAD.Vector(5 + sin30 * r, -15 - cos30 * r, 0),
                },
                7: {
                    "start": FreeCAD.Vector(15, -15, 0),
                    "end": FreeCAD.Vector(15 - sin30 * r, -15 - cos30 * r, 0),
                },
            },
            "Sketch004": {
                0: {"start": FreeCAD.Vector(-10, -10, 0), "end": FreeCAD.Vector(-20, -10, 0)},
                1: {
                    "start": FreeCAD.Vector(-10, -10, 0),
                    "end": FreeCAD.Vector(-10 - cos30 * r, -10 - sin30 * r, 0),
                },
                2: {
                    "start": FreeCAD.Vector(-10, -10, 0),
                    "end": FreeCAD.Vector(-10 - sin30 * r, -10 - cos30 * r, 0),
                },
                3: {
                    "start": FreeCAD.Vector(-10, -10, 0),
                    "end": FreeCAD.Vector(-10 + sin30 * r, -10 - cos30 * r, 0),
                },
                4: {"location": FreeCAD.Vector(10, -10, 0)},
                5: {"location": FreeCAD.Vector(-10, 10, 0)},
                6: {
                    "start": FreeCAD.Vector(-5, -15, 0),
                    "end": FreeCAD.Vector(-5 - sin30 * r, -15 - cos30 * r, 0),
                },
                7: {
                    "start": FreeCAD.Vector(-15, -15, 0),
                    "end": FreeCAD.Vector(-15 + sin30 * r, -15 - cos30 * r, 0),
                },
            },
            "Sketch005": {
                0: {"start": FreeCAD.Vector(10, 10, 0), "end": FreeCAD.Vector(20, 10, 0)},
                1: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 + cos30 * r, 10 + sin30 * r, 0),
                },
                2: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 + sin30 * r, 10 + cos30 * r, 0),
                },
                3: {
                    "start": FreeCAD.Vector(10, 10, 0),
                    "end": FreeCAD.Vector(10 - sin30 * r, 10 + cos30 * r, 0),
                },
                4: {"location": FreeCAD.Vector(-10, 10, 0)},
                5: {"location": FreeCAD.Vector(10, -10, 0)},
                6: {
                    "start": FreeCAD.Vector(5, 15, 0),
                    "end": FreeCAD.Vector(5 + sin30 * r, 15 + cos30 * r, 0),
                },
                7: {
                    "start": FreeCAD.Vector(15, 15, 0),
                    "end": FreeCAD.Vector(15 - sin30 * r, 15 + cos30 * r, 0),
                },
            },
        }

        expected_geometries_pattern_006 = {
            "Sketch007": {
                0: {"start": FreeCAD.Vector(-35, -15, 0), "end": FreeCAD.Vector(-35, -5, 0)},
                1: {"start": FreeCAD.Vector(-35, -5, 0), "end": FreeCAD.Vector(-20, -5, 0)},
                2: {"start": FreeCAD.Vector(-20, -5, 0), "end": FreeCAD.Vector(-20, -15, 0)},
                3: {"start": FreeCAD.Vector(-20, -15, 0), "end": FreeCAD.Vector(-35, -15, 0)},
            }
        }

        def execute_carbon_copy(src, dist):
            obj = FreeCAD.ActiveDocument.getObject(dist)
            obj.setAllowUnaligned(False)
            obj.carbonCopy(src, False)
            FreeCAD.ActiveDocument.recompute()

        def check_placement(expected_dict):
            for sketch, correct_points in expected_dict.items():
                obj = FreeCAD.ActiveDocument.getObject(sketch)
                for i, pts in correct_points.items():
                    geom = obj.Geometry[i]
                    if "start" in pts:
                        start = geom.StartPoint
                        end = geom.EndPoint
                        self.assertAlmostEqual((start - pts["start"]).Length, 0)
                        self.assertAlmostEqual((end - pts["end"]).Length, 0)
                    elif "location" in pts:
                        loc = geom.Location
                        self.assertAlmostEqual((loc - pts["location"]).Length, 0)

        execute_carbon_copy("Sketch001", "Sketch002")
        execute_carbon_copy("Sketch001", "Sketch003")
        execute_carbon_copy("Sketch001", "Sketch004")
        execute_carbon_copy("Sketch001", "Sketch005")
        execute_carbon_copy("Sketch006", "Sketch007")

        check_placement(expected_geometries_pattern_001)
        check_placement(expected_geometries_pattern_006)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)


class TestSketchCarbonCopyReverseMappingPlaced(unittest.TestCase):
    """Reverse mappings between sketches that are not placed at the global origin."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("CarbonCopyReverseMappingPlaced")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def _carbonCopy(self, srcPlacement, dstPlacement):
        import Part

        V = FreeCAD.Vector
        src = self.Doc.addObject("Sketcher::SketchObject", "Source")
        src.Placement = srcPlacement
        src.addGeometry(Part.LineSegment(V(1, 2, 0), V(10, 4, 0)))
        src.addGeometry(Part.Point(V(7, -3, 0)))
        dst = self.Doc.addObject("Sketcher::SketchObject", "Target")
        dst.Placement = dstPlacement
        dst.setAllowUnaligned(False)
        self.Doc.recompute()
        dst.carbonCopy(src.Name, False)
        self.Doc.recompute()
        return src, dst

    def _checkSameProjection(self, src, dst):
        # The copy lies in the plane of the target sketch (z = 0 in its own coordinates)
        # and projects along the normal onto the source geometry.
        normal = dst.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        line = dst.Geometry[0]
        point = dst.Geometry[1]
        for local in (line.StartPoint, line.EndPoint, FreeCAD.Vector(point.X, point.Y, point.Z)):
            self.assertAlmostEqual(local.z, 0, places=7)
        expected = (
            (src.Geometry[0].StartPoint, line.StartPoint),
            (src.Geometry[0].EndPoint, line.EndPoint),
            (FreeCAD.Vector(7, -3, 0), FreeCAD.Vector(point.X, point.Y, point.Z)),
        )
        for srcLocal, dstLocal in expected:
            delta = src.Placement.multVec(srcLocal) - dst.Placement.multVec(dstLocal)
            inPlane = delta - normal * delta.dot(normal)
            self.assertAlmostEqual(inPlane.Length, 0, places=7)

    def test_FlippedSketchAboveTheSource(self):
        src, dst = self._carbonCopy(
            FreeCAD.Placement(),
            FreeCAD.Placement(FreeCAD.Vector(0, 0, 4), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)),
        )
        self._checkSameProjection(src, dst)

    def test_FlippedSketchAwayFromTheGlobalOrigin(self):
        src, dst = self._carbonCopy(
            FreeCAD.Placement(FreeCAD.Vector(5, 7, 0), FreeCAD.Rotation()),
            FreeCAD.Placement(FreeCAD.Vector(5, 7, 4), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)),
        )
        self._checkSameProjection(src, dst)

    def test_FlippedSketchWithRotatedAxes(self):
        rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        src, dst = self._carbonCopy(
            FreeCAD.Placement(FreeCAD.Vector(5, 7, 0), rotation),
            FreeCAD.Placement(
                FreeCAD.Vector(5, 7, 10),
                rotation.multiply(FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)),
            ),
        )
        self._checkSameProjection(src, dst)

    def test_SketchRotatedAboutItsNormalAboveTheSource(self):
        src, dst = self._carbonCopy(
            FreeCAD.Placement(),
            FreeCAD.Placement(FreeCAD.Vector(0, 0, -5), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 180)),
        )
        self._checkSameProjection(src, dst)
