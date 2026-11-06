# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2020 Antoine Lafr                                       *
# *   Copyright (c) 2025 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft Workbench, DraftGeomUtils module tests."""

import Part
import DraftGeomUtils
from FreeCAD import Vector
from drafttests import test_base
from draftutils.messages import _msg


class TestDraftGeomUtils(test_base.DraftTestCaseNoDoc):
    """Testing the functions in the file DraftGeomUtils.py"""

    def check_wire(self, wire):
        offset_values = (2000.0, 0.0, -1000, -2000, -3000, -5500)
        for offset_start in offset_values:
            for offset_end in offset_values:
                if offset_start + offset_end > -wire.Length:
                    # print ("'start={0}, end={1}' failed".format(offset_start, offset_end))
                    try:
                        extended = DraftGeomUtils.get_extended_wire(wire, offset_start, offset_end)
                        # Test that the extended wire's length is correctly changed
                        self.assertAlmostEqual(
                            extended.Length,
                            wire.Length + offset_start + offset_end,
                            DraftGeomUtils.precision(),
                            "'start={0}, end={1}' failed".format(offset_start, offset_end),
                        )
                        if offset_start == 0.0:
                            # If offset_start is 0.0, check that the wire's start point is unchanged
                            self.assertAlmostEqual(
                                extended.OrderedVertexes[0].Point.distanceToPoint(
                                    wire.OrderedVertexes[0].Point
                                ),
                                0.0,
                                DraftGeomUtils.precision(),
                                "'start={0}, end={1}' failed".format(offset_start, offset_end),
                            )
                        if offset_end == 0.0:
                            # If offset_end is 0.0, check that the wire's end point is unchanged
                            self.assertAlmostEqual(
                                extended.OrderedVertexes[-1].Point.distanceToPoint(
                                    wire.OrderedVertexes[-1].Point
                                ),
                                0.0,
                                DraftGeomUtils.precision(),
                                "'start={0}, end={1}' failed".format(offset_start, offset_end),
                            )
                    except Exception as exc:
                        print(
                            "get_extended_wire failed for 'start={0}, end={1}'".format(
                                offset_start, offset_end
                            )
                        )
                        raise exc

    def test_get_extended_wire1(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire1"
        _msg("  Test '{}'".format(operation))

        # Build wires made with straight edges and various combination of Orientation: the wires 1-4 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 2500.0),
        ]

        edges = []
        for start, end in zip(points[:-1], points[1:]):
            edge = Part.makeLine(start, end)
            edges.append(edge)
        wire = Part.Wire(edges)
        self.check_wire(wire)

    def test_get_extended_wire2(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire2"
        _msg("  Test '{}'".format(operation))

        # Build wires made with straight edges and various combination of Orientation: the wires 1-4 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 2500.0),
        ]

        edges = []
        for start, end in zip(points[:-1], points[1:]):
            edge = Part.makeLine(end, start)
            edge.Orientation = "Reversed"
            edges.append(edge)
        wire = Part.Wire(edges)
        self.check_wire(wire)

    def test_get_extended_wire3(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire3"
        _msg("  Test '{}'".format(operation))

        # Build wires made with straight edges and various combination of Orientation: the wires 1-4 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 2500.0),
        ]

        edges = []
        for start, end in zip(points[:-1], points[1:]):
            edge = Part.makeLine(start, end)
            edge.Orientation = "Reversed"
            edges.insert(0, edge)
        wire = Part.Wire(edges)
        wire.Orientation = "Reversed"
        self.check_wire(wire)

    def test_get_extended_wire4(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire4"
        _msg("  Test '{}'".format(operation))

        # Build wires made with straight edges and various combination of Orientation: the wires 1-4 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 0.0),
            Vector(4500.0, 2000.0, 2500.0),
        ]

        edges = []
        for start, end in zip(points[:-1], points[1:]):
            edge = Part.makeLine(end, start)
            edges.insert(0, edge)
        wire = Part.Wire(edges)
        wire.Orientation = "Reversed"
        self.check_wire(wire)

    def test_get_extended_wire5(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire5"
        _msg("  Test '{}'".format(operation))

        # Build wires made with arcs and various combination of Orientation: the wires 5-8 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1000.0, 1000.0, 0.0),
            Vector(2000.0, 0.0, 0.0),
            Vector(3000.0, 0.0, 1000.0),
            Vector(4000.0, 0.0, 0.0),
        ]

        edges = []
        for start, mid, end in zip(points[:-2], points[1:-1], points[2:]):
            edge = Part.Arc(start, mid, end).toShape()
            edges.append(edge)
        wire = Part.Wire(edges)
        self.check_wire(wire)

    def test_get_extended_wire6(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire6"
        _msg("  Test '{}'".format(operation))

        # Build wires made with arcs and various combination of Orientation: the wires 5-8 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1000.0, 1000.0, 0.0),
            Vector(2000.0, 0.0, 0.0),
            Vector(3000.0, 0.0, 1000.0),
            Vector(4000.0, 0.0, 0.0),
        ]

        edges = []
        for start, mid, end in zip(points[:-2], points[1:-1], points[2:]):
            edge = Part.Arc(end, mid, start).toShape()
            edge.Orientation = "Reversed"
            edges.append(edge)
        wire = Part.Wire(edges)
        self.check_wire(wire)

    def test_get_extended_wire7(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire7"
        _msg("  Test '{}'".format(operation))

        # Build wires made with arcs and various combination of Orientation: the wires 5-8 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1000.0, 1000.0, 0.0),
            Vector(2000.0, 0.0, 0.0),
            Vector(3000.0, 0.0, 1000.0),
            Vector(4000.0, 0.0, 0.0),
        ]

        edges = []
        for start, mid, end in zip(points[:-2], points[1:-1], points[2:]):
            edge = Part.Arc(start, mid, end).toShape()
            edge.Orientation = "Reversed"
            edges.insert(0, edge)
        wire = Part.Wire(edges)
        wire.Orientation = "Reversed"
        self.check_wire(wire)

    def test_get_extended_wire8(self):
        """Test the DraftGeomUtils.get_extended_wire function."""
        operation = "DraftGeomUtils.get_extended_wire8"
        _msg("  Test '{}'".format(operation))

        # Build wires made with arcs and various combination of Orientation: the wires 5-8 are all equivalent
        points = [
            Vector(0.0, 0.0, 0.0),
            Vector(1000.0, 1000.0, 0.0),
            Vector(2000.0, 0.0, 0.0),
            Vector(3000.0, 0.0, 1000.0),
            Vector(4000.0, 0.0, 0.0),
        ]

        edges = []
        for start, mid, end in zip(points[:-2], points[1:-1], points[2:]):
            edge = Part.Arc(end, mid, start).toShape()
            edges.insert(0, edge)
        wire = Part.Wire(edges)
        wire.Orientation = "Reversed"
        self.check_wire(wire)

    def test_make_segment_face_repairs_crossed_connectors(self):
        """The segment face builder should retry with the alternate endpoint pairing."""
        operation = "DraftGeomUtils._make_segment_face crossed connectors"
        _msg("  Test '{}'".format(operation))

        edge1 = Part.makeLine(Vector(10369.55, 6924.675, 0), Vector(10077.45, 6924.675, 0))
        edge2 = Part.makeLine(Vector(10175.875, 7118.35, 0), Vector(10271.125, 7118.35, 0))

        default_start = Part.LineSegment(edge1.Vertexes[0].Point, edge2.Vertexes[0].Point).toShape()
        default_end = Part.LineSegment(edge1.Vertexes[-1].Point, edge2.Vertexes[-1].Point).toShape()
        default_face = Part.Face(
            Part.Wire(edge1.Edges + [default_start] + edge2.Edges + [default_end])
        )
        self.assertTrue(
            default_start.section(default_end).Vertexes,
            "The default connector pairing should reproduce the crossed-strip case.",
        )
        self.assertFalse(default_face.isValid(), "The default face should be invalid.")

        fixed_face = DraftGeomUtils.bind(edge1, edge2)
        self.assertIsNotNone(fixed_face, "The repaired segment face should be created.")
        self.assertTrue(fixed_face.isValid(), "The repaired segment face should be valid.")
        self.assertAlmostEqual(
            fixed_face.Area,
            37510.005625,
            places=2,
            msg="The repaired segment face area is incorrect.",
        )

    def test_bind_repairs_collinear_segment_face_for_extrusion(self):
        """A segment-bound face should produce a valid solid."""
        points = [
            Vector(0.0, y, 0.0)
            for y in (
                -11969.75,
                -10979.15,
                -9201.15,
                -6902.45,
                -5734.05,
                -4514.85,
                -2870.2,
                -1092.2,
                0.0,
            )
        ]
        wire = Part.Wire([Part.makeLine(start, end) for start, end in zip(points[:-1], points[1:])])
        width = 120.65
        offset = Vector(-width, 0.0, 0.0)
        offset_args = {
            "widthList": [width] * len(wire.Edges),
            "alignList": ["Right"] * len(wire.Edges),
            "normal": Vector(0.0, 0.0, 1.0),
            "basewireOffset": [0.0] * len(wire.Edges),
            "wireNedge": True,
        }
        outer_wire = DraftGeomUtils.offsetWire(
            wire, offset, bind=False, occ=False, offsetMode=None, **offset_args
        )[0]
        base_wire = DraftGeomUtils.offsetWire(
            wire, offset, bind=False, occ=False, offsetMode="BasewireMode", **offset_args
        )[0]

        face = DraftGeomUtils.bind(base_wire, outer_wire, per_segment=True)

        self.assertIsNotNone(face)
        self.assertTrue(face.extrude(Vector(0.0, 0.0, 3000.0)).isValid())

    def test_get_spline_normal(self):
        """get_spline_normal returns the normal of a planar spline, None for a straight one."""
        curve = Part.BSplineCurve()
        curve.interpolate([Vector(0, 0, 0), Vector(5, 5, 0), Vector(10, 0, 0)])
        normal = DraftGeomUtils.get_spline_normal(curve.toShape())
        self.assertIsNotNone(normal)
        self.assertAlmostEqual(abs(normal.z), 1.0, places=6)

        straight = Part.BSplineCurve()
        straight.interpolate([Vector(0, 0, 0), Vector(5, 0, 0), Vector(10, 0, 0)])
        self.assertIsNone(DraftGeomUtils.get_spline_normal(straight.toShape()))

    def test_project_onto_vector_of_squared_length_15(self):
        """DraftVecUtils.project must not return a null vector when |v|^2 == 15."""
        import math
        import DraftVecUtils

        v = Vector(3, math.sqrt(6), 0)
        self.assertEqual(v.dot(v), 15.0)
        proj = DraftVecUtils.project(Vector(3, 0, 0), v)
        expected = Vector(v).multiply(9.0 / 15.0)
        self.assertAlmostEqual((proj - expected).Length, 0.0, places=9)

    def _assert_circles(self, circles, expected):
        """Compare (center, radius) of circles with the expected ones, in any order."""
        self.assertIsNotNone(circles)
        found = sorted(
            (round(c.Center.x, 6), round(c.Center.y, 6), round(c.Radius, 6)) for c in circles
        )
        self.assertEqual(found, sorted(expected))

    def test_circle_from_line_and_two_points(self):
        """circlefrom1Line2Points returns both circles through 2 points tangent to a line."""
        edge = Part.LineSegment(Vector(0, 0, 0), Vector(10, 0, 0)).toShape()
        circles = DraftGeomUtils.circlefrom1Line2Points(edge, Vector(0, 2, 0), Vector(0, 8, 0))
        self._assert_circles(circles, [(-4.0, 5.0, 5.0), (4.0, 5.0, 5.0)])

    def test_circle_from_point_line_radius(self):
        """circleFromPointLineRadius also works for a point on the line."""
        edge = Part.LineSegment(Vector(0, 0, 0), Vector(10, 0, 0)).toShape()
        circles = DraftGeomUtils.circleFromPointLineRadius(Vector(5, 0, 0), edge, 3)
        self._assert_circles(circles, [(5.0, -3.0, 3.0), (5.0, 3.0, 3.0)])
        circles = DraftGeomUtils.circleFromPointLineRadius(Vector(5, 2, 0), edge, 3)
        offset = 8**0.5
        self._assert_circles(
            circles, [(round(5 - offset, 6), 3.0, 3.0), (round(5 + offset, 6), 3.0, 3.0)]
        )

    def _assert_points(self, points, expected):
        """Compare points with the expected (x, y, z) tuples, in any order."""
        found = sorted((round(p.x, 6), round(p.y, 6), round(p.z, 6)) for p in points)
        self.assertEqual(found, sorted(expected))

    def test_find_intersection_lines_3d(self):
        """findIntersection of coplanar lines whose plane contains (1, 1, 1)."""
        line1 = Part.makeLine(Vector(0, 0, 0), Vector(1, 1, 1))
        line2 = Part.makeLine(Vector(2, 2, 0), Vector(2, 2, 1))
        points = DraftGeomUtils.findIntersection(line1, line2, True, True)
        self._assert_points(points, [(2, 2, 2)])
        points = DraftGeomUtils.findIntersection(
            Vector(0, 0, 0), Vector(1, 1, 0), Vector(3, 3, 5), Vector(3, 3, 6), True, True
        )
        self._assert_points(points, [(3, 3, 0)])

    def test_find_intersection_circle_line_off_plane(self):
        """findIntersection of a circle and a line that is not in its plane."""
        circle = Part.makeCircle(5, Vector(1, 2, 3))
        # The line pierces the plane of the circle on the circle:
        line = Part.makeLine(Vector(6, 2, 2), Vector(6, 2, 4))
        points = DraftGeomUtils.findIntersection(circle, line, True, True)
        self._assert_points(points, [(6, 2, 3)])
        # The line pierces the plane of the circle at its center:
        line = Part.makeLine(Vector(1, 2, 2), Vector(1, 2, 4))
        self.assertEqual(DraftGeomUtils.findIntersection(circle, line, True, True), [])
        self.assertEqual(DraftGeomUtils.findIntersection(line, circle, True, True), [])

    def test_find_intersection_circles_not_coplanar(self):
        """findIntersection of two circles in different planes."""
        circle1 = Part.makeCircle(5, Vector(1, 0, 0))
        circle2 = Part.makeCircle(4, Vector(4, 0, 0), Vector(1, 0, 0))
        points = DraftGeomUtils.findIntersection(circle1, circle2, True, True)
        self._assert_points(points, [(4, -4, 0), (4, 4, 0)])
        points = DraftGeomUtils.findIntersection(circle1, circle2, dts=False)
        self._assert_points(points, [(4, -4, 0), (4, 4, 0)])

    def test_orient_edge_trimmed_bspline(self):
        """orientEdge keeps the trimmed range of a B-spline edge."""
        curve = Part.BSplineCurve()
        curve.interpolate([Vector(0, 0, 5), Vector(5, 5, 5), Vector(10, 0, 5), Vector(15, 5, 5)])
        edge = curve.toShape(0.2, 0.8)
        geom = DraftGeomUtils.orientEdge(edge, Vector(0, 0, 1))
        new = geom.toShape()
        self.assertAlmostEqual(new.Length, edge.Length, places=6)
        self.assertTrue(new.Vertexes[0].Point.isEqual(edge.Vertexes[0].Point, 1e-6))
        self.assertTrue(new.Vertexes[-1].Point.isEqual(edge.Vertexes[-1].Point, 1e-6))
        # an untrimmed B-spline is returned as it is
        geom = DraftGeomUtils.orientEdge(curve.toShape(), Vector(0, 0, 1))
        self.assertAlmostEqual(geom.toShape().Length, curve.toShape().Length, places=6)

    def test_offset_circle(self):
        """offset of a circular edge returns the complete offset circle unless trim is True."""
        arc = Part.ArcOfCircle(Part.Circle(Vector(1, 2, 0), Vector(0, 0, 1), 5), 0, 1).toShape()
        new = DraftGeomUtils.offset(arc, Vector(2, 0, 0))
        self.assertIsNotNone(new)
        self.assertTrue(new.isClosed())
        self.assertAlmostEqual(new.Curve.Radius, 7, places=6)
        self.assertTrue(new.Curve.Center.isEqual(Vector(1, 2, 0), 1e-9))
        new = DraftGeomUtils.offset(arc, Vector(2, 0, 0), trim=True)
        self.assertFalse(new.isClosed())
        self.assertAlmostEqual(new.Curve.Radius, 7, places=6)


# suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestDraftGeomUtils)
# unittest.TextTestRunner().run(suite)
