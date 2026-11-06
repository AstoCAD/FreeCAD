# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
from FreeCAD import Vector, Base, newDocument, closeDocument
import Part

import math
import os

if "BUILD_SKETCHER" in FreeCAD.__cmake__:
    import Sketcher

import unittest


class RegressionTests(unittest.TestCase):

    # pylint: disable=attribute-defined-outside-init

    def setUp(self):
        """Create a document for each test in the test suite"""
        self.Doc = newDocument("PartRegressionTest." + self._testMethodName)
        self.KeepTestDoc = False

    def test_issue_4456(self):
        """
        0004456: Regression : Part.Plane.Intersect does not accept plane as argument
        """
        p1 = Part.Plane()
        p2 = Part.Plane(Vector(0, 0, 0), Vector(1, 0, 0))

        result = p1.intersect(p2)
        line = result.pop()
        self.assertEqual(line.Location, Vector(0, 0, 0))
        self.assertEqual(line.Direction, Vector(0, 1, 0))
        # We should now have empty list...
        with self.assertRaises(IndexError):
            result.pop()

    def test_issue_15735(self):
        """
        15735: Point in sketch as loft profile won't work in dev, but works in stable
        The following test is a simplified version of the issue, but the outcome is the same
        """

        if "BUILD_SKETCHER" in FreeCAD.__cmake__:
            # Arrange
            ArcSketch = self.Doc.addObject("Sketcher::SketchObject", "ArcSketch")
            ArcSketch.Placement = Base.Placement(
                Base.Vector(0.000000, 0.000000, 0.000000),
                Base.Rotation(0.500000, 0.500000, 0.500000, 0.500000),
            )
            ArcSketch.MapMode = "Deactivated"

            geoList = []
            geoList.append(
                Part.ArcOfCircle(
                    Part.Circle(
                        Base.Vector(0.000000, 0.000000, 0.000000),
                        Base.Vector(0.000000, 0.000000, 1.000000),
                        10.000000,
                    ),
                    3.141593,
                    6.283185,
                )
            )
            ArcSketch.addGeometry(geoList, False)
            del geoList

            constraintList = []
            ArcSketch.addConstraint(Sketcher.Constraint("Radius", 0, 10.000000))
            constraintList.append(Sketcher.Constraint("Coincident", 0, 3, -1, 1))
            constraintList.append(Sketcher.Constraint("PointOnObject", 0, 2, -1))
            constraintList.append(Sketcher.Constraint("PointOnObject", 0, 1, -1))
            ArcSketch.addConstraint(constraintList)
            del constraintList

            self.Doc.recompute()

            PointSketch = self.Doc.addObject("Sketcher::SketchObject", "PointSketch")
            PointSketch.Placement = Base.Placement(
                Base.Vector(-10.000000, 0.000000, 0.000000),
                Base.Rotation(0.500000, 0.500000, 0.500000, 0.500000),
            )
            PointSketch.MapMode = "Deactivated"

            PointSketch.addGeometry(Part.Point(Base.Vector(0.000000, 0.000000, 0)))

            PointSketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))

            self.Doc.recompute()

            Loft = self.Doc.addObject("Part::Loft", "Loft")
            Loft.Sections = [
                ArcSketch,
                PointSketch,
            ]
            Loft.Solid = False
            Loft.Ruled = False
            Loft.Closed = False

            # Act
            self.Doc.recompute()

            # Assert
            self.assertTrue(Loft.isValid())
            self.KeepTestDoc = not Loft.isValid()

    def test_OptimalBox(self):
        box = Part.makeBox(1, 1, 1)
        self.assertTrue(box.optimalBoundingBox(True, False).isValid())

    def test_CircularReference(self):

        cube = self.Doc.addObject("Part::Box", "Cube")
        cube.setExpression("Length", "Width + 10mm")
        with self.assertRaises(RuntimeError) as context:
            cube.setExpression("Width", "Length + 10mm")
        assert "Width reference creates a cyclic dependency." in str(context.exception)

        cube.setExpression(".Placement.Base.x", ".Placement.Base.y + 10mm")
        with self.assertRaises(RuntimeError) as context:
            cube.setExpression(".Placement.Base.y", ".Placement.Base.x + 10mm")
        assert ".Placement.Base.y reference creates a cyclic dependency." in str(context.exception)

        cube.recompute()
        v1 = cube.Placement.Base
        cube.recompute()
        assert cube.Placement.Base.isEqual(v1, 1e-6)

    def test_TangentMode3_Issue24254(self):
        """In FreeCAD 1.1 we changed the behavior of the mmTangentPlane, but added code to handle old files
        that relied upon the original tangent plane behavior. This test ensures that old files open with the expected
        tangent plane setup."""

        location = os.path.dirname(os.path.realpath(__file__))
        FreeCAD.openDocument(os.path.join(location, "TestTangentMode3-0.21.FCStd"), True)

        def check_plane(name, expected_pos, expected_normal, expected_xaxis):
            obj = FreeCAD.ActiveDocument.getObject(name)
            if not obj:
                FreeCAD.Console.PrintError(f"{name}: object not found\n")
                return

            pos = obj.Placement.Base
            rot = obj.Placement.Rotation
            normal = rot.multVec(FreeCAD.Vector(0, 0, 1))
            xaxis = rot.multVec(FreeCAD.Vector(1, 0, 0))

            # position
            self.assertAlmostEqual((pos - expected_pos).Length, 0)

            # normal
            self.assertAlmostEqual(normal.getAngle(expected_normal), 0)

            # tangent x-axis
            self.assertAlmostEqual(xaxis.getAngle(expected_xaxis), 0)

        r = 10.0
        rad30 = math.radians(30)
        cos30 = math.cos(rad30)
        sin30 = math.sin(rad30)

        expected_planes = [
            (
                "Sketch001",
                FreeCAD.Vector(-1 * r, 0, 0),  # position
                FreeCAD.Vector(1, 0, 0),  # normal
                FreeCAD.Vector(0, -1, 0),
            ),  # tangent x-axis
            (
                "Sketch002",
                FreeCAD.Vector(sin30 * r, cos30 * cos30 * (-r), cos30 * sin30 * r),
                FreeCAD.Vector(sin30, cos30 * cos30 * (-1), cos30 * sin30),
                FreeCAD.Vector(0, sin30, cos30),
            ),
            (
                "Sketch003",
                FreeCAD.Vector(cos30 * cos30 * r, sin30 * r, cos30 * sin30 * r),
                FreeCAD.Vector(cos30 * cos30, sin30, cos30 * sin30),
                FreeCAD.Vector(sin30, 0, -cos30),
            ),
        ]

        for name, pos, normal, xaxis in expected_planes:
            check_plane(name, pos, normal, xaxis)

    def test_issue_29733_transformShape_bakes_in_transformation(self):
        """
        29733: transformShape(matrix, True) must bake the transformation into the
        underlying geometry, leaving the shape's Placement untouched. Part Explode
        Compound and many third-party addons depend on this behavior.
        """
        sphere = Part.makeSphere(5.0)
        move = FreeCAD.Placement(FreeCAD.Vector(10, 0, 0), FreeCAD.Rotation()).toMatrix()

        returned = sphere.transformShape(move, True)

        self.assertIs(returned, sphere)
        self.assertAlmostEqual(sphere.Placement.Base.x, 0.0)
        self.assertAlmostEqual(sphere.Placement.Base.y, 0.0)
        self.assertAlmostEqual(sphere.Placement.Base.z, 0.0)
        self.assertAlmostEqual(sphere.CenterOfGravity.x, 10.0, places=5)
        self.assertAlmostEqual(sphere.CenterOfGravity.y, 0.0, places=5)
        self.assertAlmostEqual(sphere.CenterOfGravity.z, 0.0, places=5)

    def test_transformed_returns_independent_baked_in_copy(self):
        """
        transformed() must return a new shape with the transformation baked into
        the geometry, leaving the original shape unchanged.
        """
        sphere = Part.makeSphere(5.0)
        move = FreeCAD.Placement(FreeCAD.Vector(10, 0, 0), FreeCAD.Rotation()).toMatrix()

        moved = sphere.transformed(move, copy=True)

        self.assertIsNot(moved, sphere)
        self.assertAlmostEqual(sphere.CenterOfGravity.x, 0.0, places=5)
        self.assertAlmostEqual(moved.Placement.Base.x, 0.0)
        self.assertAlmostEqual(moved.CenterOfGravity.x, 10.0, places=5)

    def test_issue_15716_AttacherEngine_sync(self):
        """
        15716: AttacherType and AttacherEngine property conflict

        When creating a Part2DObject (like a Sketch), the AttacherEngine property
        should be synchronized with AttacherType. Previously, AttacherType was
        correctly set to "Attacher::AttachEnginePlane" but AttacherEngine stayed
        at the default "Engine 3D" instead of "Engine Plane".
        """
        if "BUILD_SKETCHER" in FreeCAD.__cmake__:
            # Create a new sketch (which inherits from Part2DObject)
            sketch = self.Doc.addObject("Sketcher::SketchObject", "TestSketch")
            self.Doc.recompute()

            # The visible AttacherEngine property should match the actual engine type
            # AttacherType is the internal type name, AttacherEngine is the user-visible enum
            attacher_type = sketch.AttacherType
            attacher_engine = sketch.AttacherEngine

            # For a sketch, AttacherType should be AttachEnginePlane
            self.assertEqual(attacher_type, "Attacher::AttachEnginePlane")

            # AttacherEngine should show "Engine Plane" (not "Engine 3D")
            self.assertEqual(attacher_engine, "Engine Plane")

    def test_getSortedClusters(self):
        "Part.getSortedClusters() may crash with short edges"
        poly = self.Doc.addObject("Part::RegularPolygon", "RegularPolygon")
        poly.Circumradius = 1
        for i in range(3, 1004, 50):
            poly.Polygon = i
            poly.recompute()
            clusters = Part.getSortedClusters(poly.Shape.Edges)

            # should be only one cluster
            self.assertEqual(len(clusters), 1)

            # cluster should contain all edges
            self.assertEqual(len(clusters[0]), i)

    def test_project_null_shape_raises(self):
        "TopoShape.project() with a null shape in the list crashed in BRepAlgo_NormalProjection"
        box = Part.makeBox(1, 2, 3)
        face = box.Faces[0]
        for index, shapes in enumerate(
            ([Part.Shape()], [box, Part.Shape()], [Part.Shape(), box.Edges[0]])
        ):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    face.project(shapes)
        self.assertEqual(len(face.project([box]).Edges), 16)

    def test_tessellate_nan_tolerance_raises(self):
        "TopoShape.tessellate(nan) never returned on shapes with curved faces"
        sphere = Part.makeSphere(1)
        with self.assertRaises(ValueError):
            sphere.tessellate(float("nan"))
        points, facets = sphere.tessellate(0.1)
        self.assertGreater(len(points), 0)
        self.assertGreater(len(facets), 0)

    def test_perspective_projection_non_finite_centre_raises(self):
        "TopoShape.makePerspectiveProjection() crashed for a NaN or infinite centre"
        box = Part.makeBox(1, 2, 3)
        edge = box.Edges[0]
        for centre in (Vector(float("nan"), 0, 0), Vector(float("inf"), 0, 0)):
            for target in (box, Part.makeSphere(1)):
                with self.subTest(centre=str(centre), target=target.ShapeType):
                    with self.assertRaises(ValueError):
                        target.makePerspectiveProjection(edge, centre)
        circle = Part.makeCircle(1, Vector(0, 0, 0))
        projected = Part.makeSphere(5).makePerspectiveProjection(circle, Vector(0, 0, 0))
        self.assertEqual(len(projected.Edges), 1)

    def test_spiral_infinite_rotations(self):
        "Part::Spiral with an infinite or huge number of rotations looped forever"
        spiral = self.Doc.addObject("Part::Spiral", "Spiral")
        self.Doc.recompute()
        self.assertTrue(spiral.isValid())
        # one edge per rotation (SegmentLength 1): more than 1e4 edges are refused at once
        for rotations in (float("inf"), 1e300, 5e9, 1e9, 10001):
            spiral.Rotations = rotations
            self.Doc.recompute()
            self.assertFalse(spiral.isValid())
            self.assertIn("1e4 segments", spiral.getStatusString())
        spiral.Rotations = 101
        spiral.SegmentLength = 0.01
        self.Doc.recompute()
        self.assertFalse(spiral.isValid())
        self.assertIn("1e4 segments", spiral.getStatusString())
        spiral.SegmentLength = 1
        spiral.Rotations = 3
        self.Doc.recompute()
        self.assertTrue(spiral.isValid())
        self.assertEqual(len(spiral.Shape.Edges), 3)

    def test_geometry_nan_parameters_raise(self):
        "NaN curve/surface parameters crashed inside OCC instead of raising"
        nan = float("nan")
        curves = [
            Part.Line(Vector(0, 0, 0), Vector(1, 0, 0)),
            Part.LineSegment(Vector(0, 0, 0), Vector(1, 0, 0)),
            Part.Hyperbola(),
            Part.ArcOfHyperbola(Part.Hyperbola(), 0, 1),
            Part.Parabola(),
            Part.ArcOfParabola(Part.Parabola(), 0, 1),
            Part.BezierCurve([Vector(0, 0, 0), Vector(1, 1, 0), Vector(2, 0, 0)]),
        ]
        for curve in curves:
            for name in ("trim", "toBSpline", "toNurbs"):
                for args in ((nan,), (0, nan), (nan, 1)):
                    with self.subTest(curve=curve.TypeId, method=name, args=args):
                        with self.assertRaises(ValueError):
                            getattr(curve, name)(*args)
            if hasattr(curve, "setParameterRange"):
                for args in ((0, nan), (nan, 1)):
                    with self.subTest(curve=curve.TypeId, method="setParameterRange", args=args):
                        with self.assertRaises(ValueError):
                            curve.setParameterRange(*args)
        for geom in (
            Part.LineSegment(Vector(0, 0, 0), Vector(1, 0, 0)),
            Part.ArcOfParabola(Part.Parabola(), 0, 1),
            Part.SurfaceOfRevolution(
                Part.LineSegment(Vector(1, 0, 0), Vector(1, 0, 1)), Vector(0, 0, 0), Vector(0, 0, 1)
            ),
        ):
            with self.subTest(geom=geom.TypeId, method="scale"):
                with self.assertRaises(ValueError):
                    geom.scale(Vector(0, 0, 0), nan)
        with self.assertRaises(ValueError):
            Part.OffsetSurface(Part.Plane(), 1.0).toShape(0, 1, nan, 1)
        with self.assertRaises(ValueError):
            Part.Geom2d.Line2d().toBSpline(0, nan)
        with self.assertRaises(ValueError):
            Part.Geom2d.Line2dSegment().setParameterRange(nan, 1)
        # valid parameters still work
        self.assertAlmostEqual(curves[0].trim(0, 2).length(), 2)
        self.assertAlmostEqual(curves[0].toBSpline(0, 2).length(), 2)
        seg = Part.LineSegment(Vector(0, 0, 0), Vector(1, 0, 0))
        seg.setParameterRange(0, 3)
        self.assertAlmostEqual(seg.length(), 3)
        seg.scale(Vector(0, 0, 0), 2)
        self.assertAlmostEqual(seg.length(), 6)

    def test_2d_segment_and_arc_constructor_nan_parameters_raise(self):
        "Line2dSegment/ArcOfHyperbola2d/ArcOfParabola2d with a NaN parameter crashed FreeCAD"
        nan = float("nan")
        g2d = Part.Geom2d
        line = g2d.Line2d()
        segment = g2d.Line2dSegment(Base.Vector2d(0, 0), Base.Vector2d(1, 0))
        constructors = [
            ("Line2dSegment(Line2d)", lambda u1, u2: g2d.Line2dSegment(line, u1, u2)),
            ("Line2dSegment(Line2dSegment)", lambda u1, u2: g2d.Line2dSegment(segment, u1, u2)),
            ("ArcOfHyperbola2d", lambda u1, u2: g2d.ArcOfHyperbola2d(g2d.Hyperbola2d(), u1, u2)),
            ("ArcOfParabola2d", lambda u1, u2: g2d.ArcOfParabola2d(g2d.Parabola2d(), u1, u2)),
        ]
        for name, make in constructors:
            for args in ((0, nan), (nan, 1), (nan, nan)):
                with self.subTest(constructor=name, args=args):
                    with self.assertRaises(ValueError):
                        make(*args).length()
            with self.subTest(constructor=name, args=(-1, 2)):
                self.assertGreater(make(-1, 2).length(), 0)
        self.assertAlmostEqual(g2d.Line2dSegment(line, -1, 2).length(), 3)
        self.assertAlmostEqual(g2d.Line2dSegment(segment, 0, 3).length(), 3)

    def test_arc_constructor_nan_parameters_raise(self):
        "ArcOfHyperbola/ArcOfParabola built from a NaN parameter crashed when used"
        nan = float("nan")
        for arcType, conicType in (
            (Part.ArcOfHyperbola, Part.Hyperbola),
            (Part.ArcOfParabola, Part.Parabola),
        ):
            for args in ((0, nan), (nan, 1), (nan, nan)):
                with self.subTest(arc=arcType.__name__, args=args):
                    with self.assertRaises(ValueError):
                        arcType(conicType(), *args).toShape()
            arc = arcType(conicType(), -1, 1)
            self.assertAlmostEqual(arc.FirstParameter, -1)
            self.assertAlmostEqual(arc.LastParameter, 1)
            self.assertTrue(arc.toShape().isValid())

    def test_revolve_non_finite_angle_raises(self):
        "Shape.revolve() with an infinite angle never returned"
        face = Part.makePlane(1, 1, Vector(1, 0, 0))
        for angle in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(angle=angle):
                with self.assertRaises(ValueError):
                    face.revolve(Vector(0, 0, 0), Vector(0, 1, 0), angle)
        solid = face.revolve(Vector(0, 0, 0), Vector(0, 1, 0), 90)
        self.assertTrue(solid.isValid())
        self.assertGreater(solid.Volume, 0)

    def test_long_helix_default_is_cylindrical(self):
        "Part.makeLongHelix() without an angle built a conical helix of -1 degree"
        pitch, height, radius = 2.0, 10.0, 3.0
        length = height / pitch * math.hypot(2 * math.pi * radius, pitch)
        for helix in (
            Part.makeHelix(pitch, height, radius),
            Part.makeLongHelix(pitch, height, radius, 0.0),
            Part.makeLongHelix(pitch, height, radius),
        ):
            self.assertAlmostEqual(helix.BoundBox.ZMax - helix.BoundBox.ZMin, height, places=3)
            self.assertAlmostEqual(helix.Length, length, places=3)
            for point in helix.discretize(100):
                self.assertAlmostEqual(math.hypot(point.x, point.y), radius, places=3)
        # an explicit angle still gives a conical helix, narrowing for a negative one
        cone = Part.makeLongHelix(pitch, height, radius, -1.0)
        smallest = min(math.hypot(p.x, p.y) for p in cone.discretize(100))
        self.assertLess(smallest, radius - 0.1)

    def test_bezier_constructor_takes_poles(self):
        "Part.BezierCurve(poles) and Geom2d.BezierCurve2d(poles) silently ignored the poles"
        poles = [Vector(0, 0, 0), Vector(1, 2, 0), Vector(3, 2, 1), Vector(4, 0, 0)]
        for curve in (Part.BezierCurve(poles), Part.BezierCurve(poles=poles)):
            self.assertEqual(curve.Degree, 3)
            self.assertEqual(curve.getPoles(), poles)
        poles2d = [Base.Vector2d(0, 0), Base.Vector2d(1, 2), Base.Vector2d(3, 0)]
        curve2d = Part.Geom2d.BezierCurve2d(poles2d)
        self.assertEqual(curve2d.Degree, 2)
        self.assertEqual([(p.x, p.y) for p in curve2d.getPoles()], [(0, 0), (1, 2), (3, 0)])
        # no argument still gives the default curve, bad arguments raise instead of being ignored
        self.assertEqual(Part.BezierCurve().Degree, 1)
        self.assertEqual(Part.Geom2d.BezierCurve2d().Degree, 1)
        for cls in (Part.BezierCurve, Part.Geom2d.BezierCurve2d):
            with self.subTest(cls=cls.__name__):
                with self.assertRaises(TypeError):
                    cls(poles, 1)
                with self.assertRaises(TypeError):
                    cls(knots=[0, 1])
                with self.assertRaises(Exception):
                    cls(5)
                with self.assertRaises(Part.OCCError):
                    cls([poles[0]] if cls is Part.BezierCurve else [poles2d[0]])

    def test_fillet_chamfer_invalid_edge_reports_the_edge(self):
        "Part Fillet/Chamfer with an edge the base does not have failed with a raw OCC error"
        box = self.Doc.addObject("Part::Box", "Box")
        line = self.Doc.addObject("Part::Line", "Line")
        for type_name in ("Part::Fillet", "Part::Chamfer"):
            with self.subTest(feature=type_name):
                feature = self.Doc.addObject(type_name, type_name.replace("Part::", ""))
                feature.Base = box
                feature.Edges = [(99, 1.0, 1.0)]
                self.Doc.recompute()
                self.assertFalse(feature.isValid())
                self.assertIn("Invalid edge link: Edge99", feature.getStatusString())
                feature.Edges = [(1, 1.0, 1.0)]
                self.Doc.recompute()
                self.assertTrue(feature.isValid())
                self.assertTrue(feature.Shape.isValid())
        chamfer = self.Doc.getObject("Chamfer")
        chamfer.Base = line
        chamfer.Edges = [(1, 0.1, 0.1)]
        self.Doc.recompute()
        self.assertFalse(chamfer.isValid())
        self.assertIn("Edge has no adjacent face: Edge1", chamfer.getStatusString())

    def tearDown(self):
        """Clean up our test, optionally preserving the test document"""
        # This flag allows doing something like this:
        #   self.KeepTestDoc = True
        #   import TestApp
        #   TestApp.Test("TestPartApp.RegressionTests.test_issue_15735")
        # to leave the test document(s) around for further examination in an interactive setting.
        if hasattr(self, "KeepTestDoc") and self.KeepTestDoc:
            return
        closeDocument(self.Doc.Name)
