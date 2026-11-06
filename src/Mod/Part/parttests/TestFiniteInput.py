# SPDX-License-Identifier: LGPL-2.1-or-later

"""Part's Python entry points reject NaN and infinite coordinates.

OpenCASCADE accepts a NaN or infinite point, direction or radius silently and only fails later, in
whatever algorithm consumes the geometry (or crashes there). The geometry constructors, attribute
setters and Part.makeXXX() factories therefore raise ValueError for them.
"""

import math
import unittest
import warnings

import FreeCAD
import Part
from FreeCAD import Base
from FreeCAD import Vector as V
from Part import Geom2d

V2 = Base.Vector2d


def _setter(factory, name, value):
    def apply():
        obj = factory()
        with warnings.catch_warnings():
            # some of the attributes (e.g. Conic.Center) are deprecated aliases
            warnings.simplefilter("ignore", DeprecationWarning)
            setattr(obj, name, value)
        return obj

    return apply


def _bspline():
    return Part.BSplineCurve([V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)])


def _bezier():
    return Part.BezierCurve([V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)])


def _arc_of_circle():
    return Part.ArcOfCircle(Part.Circle(), 0, 1)


def _bspline_with_inner_knots():
    # degree 2, knots 0, 1, 2, 3
    poles = [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0), V(3, 1, 0), V(4, 0, 0)]
    curve = Part.BSplineCurve()
    curve.buildFromPolesMultsKnots(poles, [3, 1, 1, 3], [0, 1, 2, 3], False, 2)
    return curve


def _bspline_surface():
    surface = Part.BSplineSurface()
    surface.interpolate([[V(i, j, (i * j) % 2) for j in range(6)] for i in range(6)])
    return surface


def _bezier_surface():
    surface = Part.BezierSurface()
    surface.increase(2, 2)
    return surface


def _matrix(v):
    matrix = FreeCAD.Matrix()
    matrix.A14 = v
    return matrix


def _surface_of_revolution():
    return Part.SurfaceOfRevolution(
        Part.LineSegment(V(1, 0, 0), V(1, 0, 1)), V(0, 0, 0), V(0, 0, 1)
    )


def _box_solid():
    return Part.makeBox(1, 1, 1).Solids[0]


def _bspline2d():
    poles = [V2(0, 0), V2(1, 1), V2(2, 0), V2(3, 1), V2(4, 0)]
    curve = Geom2d.BSplineCurve2d()
    curve.buildFromPolesMultsKnots(poles, [3, 1, 1, 3], [0, 1, 2, 3], False, 2)
    return curve


def _bezier2d():
    return Geom2d.BezierCurve2d([V2(0, 0), V2(1, 1), V2(2, 0)])


def _call(factory, method, *args):
    def apply():
        return getattr(factory(), method)(*args)

    return apply


def _cases(v):
    """Calls that are valid for v == 1 and must raise ValueError for a non-finite v."""
    return [
        # points and vertices
        ("Point(vector)", lambda: Part.Point(V(v, 0, 0))),
        ("Point.X", _setter(Part.Point, "X", v)),
        ("Point.Y", _setter(Part.Point, "Y", v)),
        ("Point.Z", _setter(Part.Point, "Z", v)),
        ("Vertex(vector)", lambda: Part.Vertex(V(v, 0, 0))),
        ("Vertex(x, y, z)", lambda: Part.Vertex(v, 0, 0)),
        ("Vertex(tuple)", lambda: Part.Vertex((v, 0, 0))),
        # lines
        ("Line(p, q)", lambda: Part.Line(V(0, 0, 0), V(v, 0, 0))),
        ("Line.Location", _setter(Part.Line, "Location", V(v, 0, 0))),
        ("Line.Direction", _setter(Part.Line, "Direction", V(v, 0, 0))),
        ("Line.Direction(tuple)", _setter(Part.Line, "Direction", (v, 0, 0))),
        # conics
        ("Circle(center)", lambda: Part.Circle(V(v, 0, 0), V(0, 0, 1), 1)),
        ("Circle(normal)", lambda: Part.Circle(V(0, 0, 0), V(0, 0, v), 1)),
        ("Circle(radius)", lambda: Part.Circle(V(0, 0, 0), V(0, 0, 1), v)),
        ("Circle(3 points)", lambda: Part.Circle(V(v, 0, 0), V(0, 1, 0), V(-1, 0, 0))),
        ("Circle(circle, distance)", lambda: Part.Circle(Part.Circle(), v)),
        ("Circle.Radius", _setter(Part.Circle, "Radius", v)),
        ("Circle.Location", _setter(Part.Circle, "Location", V(v, 0, 0))),
        ("Circle.Center", _setter(Part.Circle, "Center", V(v, 0, 0))),
        ("Circle.Axis", _setter(Part.Circle, "Axis", V(0, 0, v))),
        ("Circle.XAxis", _setter(Part.Circle, "XAxis", V(v, 0, 0))),
        ("Circle.YAxis", _setter(Part.Circle, "YAxis", V(0, v, 0))),
        ("Circle.AngleXU", _setter(Part.Circle, "AngleXU", v)),
        ("Ellipse(center)", lambda: Part.Ellipse(V(v, 0, 0), 2, 1)),
        ("Ellipse(major)", lambda: Part.Ellipse(V(0, 0, 0), 2 * v, 1)),
        ("Ellipse(minor)", lambda: Part.Ellipse(V(0, 0, 0), 2, v)),
        ("Ellipse(3 points)", lambda: Part.Ellipse(V(2 * v, 0, 0), V(0, 1, 0), V(0, 0, 0))),
        ("Ellipse.MajorRadius", _setter(Part.Ellipse, "MajorRadius", 3 * v)),
        ("Ellipse.MinorRadius", _setter(Part.Ellipse, "MinorRadius", v)),
        ("Hyperbola(center)", lambda: Part.Hyperbola(V(v, 0, 0), 2, 1)),
        ("Hyperbola(3 points)", lambda: Part.Hyperbola(V(2 * v, 0, 0), V(0, 1, 0), V(0, 0, 0))),
        ("Hyperbola.MajorRadius", _setter(Part.Hyperbola, "MajorRadius", 2 * v)),
        ("Hyperbola.MinorRadius", _setter(Part.Hyperbola, "MinorRadius", v)),
        ("Parabola(focus)", lambda: Part.Parabola(V(v, 0, 0), V(0, 0, 0), V(0, 0, 1))),
        ("Parabola.Focal", _setter(Part.Parabola, "Focal", v)),
        (
            "Parabola.compute",
            lambda: Part.Parabola().compute(V(v, -1, 0), V(0, 0, 0), V(1, 1, 0)),
        ),
        ("ArcOfCircle.Location", _setter(_arc_of_circle, "Location", V(v, 0, 0))),
        ("ArcOfCircle.Center", _setter(_arc_of_circle, "Center", V(v, 0, 0))),
        ("ArcOfCircle.Axis", _setter(_arc_of_circle, "Axis", V(0, 0, v))),
        ("ArcOfCircle.XAxis", _setter(_arc_of_circle, "XAxis", V(v, 0, 0))),
        ("ArcOfCircle.YAxis", _setter(_arc_of_circle, "YAxis", V(0, v, 0))),
        ("ArcOfCircle.AngleXU", _setter(_arc_of_circle, "AngleXU", v)),
        # B-spline and Bezier curves
        ("BSplineCurve(poles)", lambda: Part.BSplineCurve([V(0, 0, 0), V(1, v, 0), V(2, 0, 0)])),
        (
            "BSplineCurve.buildFromPoles",
            lambda: Part.BSplineCurve().buildFromPoles([V(0, 0, 0), V(1, v, 0), V(2, 0, 0)]),
        ),
        ("BSplineCurve.setPole", lambda: _bspline().setPole(2, V(1, v, 0))),
        ("BSplineCurve.movePoint", lambda: _bspline().movePoint(0.5, V(1, v, 0), 2, 2)),
        ("BezierCurve(poles)", lambda: Part.BezierCurve([V(0, 0, 0), V(1, v, 0), V(2, 0, 0)])),
        (
            "BezierCurve.setPoles",
            lambda: Part.BezierCurve().setPoles([V(0, 0, 0), V(1, v, 0), V(2, 0, 0)]),
        ),
        ("BezierCurve.setPole", lambda: _bezier().setPole(2, V(1, v, 0))),
        ("BezierCurve.insertPoleAfter", lambda: _bezier().insertPoleAfter(1, V(1, v, 0))),
        ("BezierCurve.insertPoleBefore", lambda: _bezier().insertPoleBefore(2, V(1, v, 0))),
        # surfaces
        ("Plane(location)", lambda: Part.Plane(V(v, 0, 0), V(0, 0, 1))),
        ("Plane(normal)", lambda: Part.Plane(V(0, 0, 0), V(0, 0, v))),
        ("Plane(3 points)", lambda: Part.Plane(V(v, 0, 0), V(0, 1, 0), V(0, 0, 0))),
        ("Plane(a, b, c, d)", lambda: Part.Plane(0, 0, v, 0)),
        ("Plane(plane, distance)", lambda: Part.Plane(Part.Plane(), v)),
        ("Plane.Position", _setter(Part.Plane, "Position", V(v, 0, 0))),
        ("Plane.Axis", _setter(Part.Plane, "Axis", V(0, 0, v))),
        ("Cylinder(3 points)", lambda: Part.Cylinder(V(0, 0, 0), V(0, 0, v), V(1, 0, 0))),
        ("Cylinder(cylinder, distance)", lambda: Part.Cylinder(Part.Cylinder(), v)),
        ("Cylinder.Radius", _setter(Part.Cylinder, "Radius", v)),
        ("Cylinder.Center", _setter(Part.Cylinder, "Center", V(v, 0, 0))),
        ("Cylinder.Axis", _setter(Part.Cylinder, "Axis", V(0, 0, v))),
        ("Cone(points, radii)", lambda: Part.Cone(V(0, 0, 0), V(0, 0, 1), v, 0.5)),
        ("Cone(point)", lambda: Part.Cone(V(0, 0, 0), V(0, 0, v), 1, 0.5)),
        ("Cone.Radius", _setter(Part.Cone, "Radius", v)),
        ("Cone.SemiAngle", _setter(Part.Cone, "SemiAngle", 0.5 * v)),
        ("Cone.Center", _setter(Part.Cone, "Center", V(v, 0, 0))),
        ("Cone.Axis", _setter(Part.Cone, "Axis", V(0, 0, v))),
        ("Sphere.Radius", _setter(Part.Sphere, "Radius", v)),
        ("Sphere.Center", _setter(Part.Sphere, "Center", V(v, 0, 0))),
        ("Sphere.Axis", _setter(Part.Sphere, "Axis", V(0, 0, v))),
        ("Toroid.MajorRadius", _setter(Part.Toroid, "MajorRadius", 5 * v)),
        ("Toroid.MinorRadius", _setter(Part.Toroid, "MinorRadius", v)),
        ("Toroid.Center", _setter(Part.Toroid, "Center", V(v, 0, 0))),
        ("Toroid.Axis", _setter(Part.Toroid, "Axis", V(0, 0, v))),
        # shape factories
        ("makeLine(vectors)", lambda: Part.makeLine(V(0, 0, 0), V(v, 0, 0))),
        ("makeLine(tuples)", lambda: Part.makeLine((0, 0, 0), (v, 0, 0))),
        ("makePolygon(vectors)", lambda: Part.makePolygon([V(0, 0, 0), V(v, 0, 0), V(1, 1, 0)])),
        ("makePolygon(tuples)", lambda: Part.makePolygon([(0, 0, 0), (v, 0, 0), (1, 1, 0)])),
        ("makeCircle(radius)", lambda: Part.makeCircle(v)),
        ("makeCircle(center)", lambda: Part.makeCircle(1, V(v, 0, 0))),
        ("makeCircle(direction)", lambda: Part.makeCircle(1, V(0, 0, 0), V(0, 0, v))),
        ("makeCircle(angle)", lambda: Part.makeCircle(1, V(0, 0, 0), V(0, 0, 1), 0, 90 * v)),
        ("makeBox(length)", lambda: Part.makeBox(v, 1, 1)),
        ("makeBox(height)", lambda: Part.makeBox(1, 1, v)),
        ("makeBox(point)", lambda: Part.makeBox(1, 1, 1, V(v, 0, 0))),
        ("makeBox(direction)", lambda: Part.makeBox(1, 1, 1, V(0, 0, 0), V(0, 0, v))),
        ("makeWedge", lambda: Part.makeWedge(0, 0, 0, 0, 0, v, 1, 1, 1, 1)),
        ("makePlane(length)", lambda: Part.makePlane(v, 1)),
        ("makePlane(point)", lambda: Part.makePlane(1, 1, V(v, 0, 0))),
        ("makePlane(normal)", lambda: Part.makePlane(1, 1, V(0, 0, 0), V(0, 0, v))),
        (
            "makePlane(x direction)",
            lambda: Part.makePlane(1, 1, V(0, 0, 0), V(0, 0, 1), V(v, 0, 0)),
        ),
        ("makeSphere(radius)", lambda: Part.makeSphere(v)),
        ("makeSphere(center)", lambda: Part.makeSphere(1, V(v, 0, 0))),
        ("makeSphere(angle)", lambda: Part.makeSphere(1, V(0, 0, 0), V(0, 0, 1), -90 * v)),
        ("makeCylinder(radius)", lambda: Part.makeCylinder(v, 1)),
        ("makeCylinder(height)", lambda: Part.makeCylinder(1, v)),
        ("makeCylinder(point)", lambda: Part.makeCylinder(1, 1, V(v, 0, 0))),
        ("makeCone(height)", lambda: Part.makeCone(1, 0.5, v)),
        ("makeCone(direction)", lambda: Part.makeCone(1, 0.5, 1, V(0, 0, 0), V(0, 0, v))),
        ("makeTorus(radius)", lambda: Part.makeTorus(5, v)),
        ("makeTorus(point)", lambda: Part.makeTorus(5, 1, V(v, 0, 0))),
    ]


def _more_cases(v):
    """Knots, weights, 2D geometry, swept and offset geometry, shape and geometry transforms.

    Valid for v == 1, must raise ValueError for a non-finite v.
    """
    bss_knot = _bspline_surface().getUKnots()[1]
    return [
        # arc radii
        ("ArcOfCircle.Radius", _setter(_arc_of_circle, "Radius", v)),
        (
            "ArcOfEllipse.MajorRadius",
            _setter(lambda: Part.ArcOfEllipse(Part.Ellipse(), 0, 1), "MajorRadius", 3 * v),
        ),
        (
            "ArcOfEllipse.MinorRadius",
            _setter(lambda: Part.ArcOfEllipse(Part.Ellipse(), 0, 1), "MinorRadius", v),
        ),
        (
            "ArcOfHyperbola.MajorRadius",
            _setter(lambda: Part.ArcOfHyperbola(Part.Hyperbola(), 0, 1), "MajorRadius", 2 * v),
        ),
        (
            "ArcOfHyperbola.MinorRadius",
            _setter(lambda: Part.ArcOfHyperbola(Part.Hyperbola(), 0, 1), "MinorRadius", v),
        ),
        (
            "ArcOfParabola.Focal",
            _setter(lambda: Part.ArcOfParabola(Part.Parabola(), 0, 1), "Focal", v),
        ),
        # offset, revolved and extruded geometry
        ("OffsetCurve(offset)", lambda: Part.OffsetCurve(Part.Circle(), v, V(0, 0, 1))),
        ("OffsetCurve(direction)", lambda: Part.OffsetCurve(Part.Circle(), 1, V(0, 0, v))),
        (
            "OffsetCurve.OffsetValue",
            _setter(lambda: Part.OffsetCurve(Part.Circle(), 1, V(0, 0, 1)), "OffsetValue", v),
        ),
        (
            "OffsetCurve.OffsetDirection",
            _setter(
                lambda: Part.OffsetCurve(Part.Circle(), 1, V(0, 0, 1)), "OffsetDirection", V(0, 0, v)
            ),
        ),
        ("OffsetSurface(offset)", lambda: Part.OffsetSurface(Part.Plane(), v)),
        (
            "OffsetSurface.OffsetValue",
            _setter(lambda: Part.OffsetSurface(Part.Plane(), 1), "OffsetValue", v),
        ),
        (
            "SurfaceOfRevolution(location)",
            lambda: Part.SurfaceOfRevolution(Part.LineSegment(), V(0, 0, v), V(0, 0, 1)),
        ),
        (
            "SurfaceOfRevolution(direction)",
            lambda: Part.SurfaceOfRevolution(Part.LineSegment(), V(0, 0, 0), V(0, 0, v)),
        ),
        ("SurfaceOfRevolution.Location", _setter(_surface_of_revolution, "Location", V(0, 0, v))),
        ("SurfaceOfRevolution.Direction", _setter(_surface_of_revolution, "Direction", V(0, 0, v))),
        ("SurfaceOfExtrusion", lambda: Part.SurfaceOfExtrusion(Part.Circle(), V(0, 0, v))),
        (
            "SurfaceOfExtrusion.Direction",
            _setter(lambda: Part.SurfaceOfExtrusion(Part.Circle(), V(0, 0, 1)), "Direction", (0, 0, v)),
        ),
        # B-spline curve knots, weights, interpolation and approximation
        ("BSplineCurve.setWeight", _call(_bspline_with_inner_knots, "setWeight", 2, v)),
        ("BSplineCurve.setPole(weight)", _call(_bspline_with_inner_knots, "setPole", 2, V(1, 1, 0), v)),
        ("BSplineCurve.setKnot", _call(_bspline_with_inner_knots, "setKnot", 2, v)),
        ("BSplineCurve.setKnots", _call(_bspline_with_inner_knots, "setKnots", [0, v, 2, 3])),
        ("BSplineCurve.insertKnot", _call(_bspline_with_inner_knots, "insertKnot", 0.5 * v)),
        ("BSplineCurve.insertKnots", _call(_bspline_with_inner_knots, "insertKnots", [0.5 * v], [1])),
        (
            "BSplineCurve.buildFromPolesMultsKnots(knots)",
            lambda: Part.BSplineCurve().buildFromPolesMultsKnots(
                [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)], [3, 3], [0, v], False, 2
            ),
        ),
        (
            "BSplineCurve.buildFromPolesMultsKnots(weights)",
            lambda: Part.BSplineCurve().buildFromPolesMultsKnots(
                [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)], [3, 3], [0, 1], False, 2, [1, v, 1]
            ),
        ),
        (
            "BSplineCurve.interpolate(points)",
            lambda: Part.BSplineCurve().interpolate([V(0, 0, 0), V(v, 1, 0), V(2, 0, 0)]),
        ),
        (
            "BSplineCurve.interpolate(parameters)",
            lambda: Part.BSplineCurve().interpolate(
                [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)], Parameters=[0, v, 2]
            ),
        ),
        (
            "BSplineCurve.interpolate(end tangents)",
            lambda: Part.BSplineCurve().interpolate(
                [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)], InitialTangent=V(v, 0, 0), FinalTangent=V(1, 0, 0)
            ),
        ),
        (
            "BSplineCurve.interpolate(tangents)",
            lambda: Part.BSplineCurve().interpolate(
                [V(0, 0, 0), V(1, 1, 0), V(2, 0, 0)],
                Tangents=[V(1, 0, 0), V(v, 0, 0), V(1, 0, 0)],
                TangentFlags=[True, True, True],
            ),
        ),
        (
            "BSplineCurve.approximate(points)",
            lambda: Part.BSplineCurve().approximate(
                Points=[V(0, 0, 0), V(1, 1, 0), V(2 * v, 0, 0), V(3, 1, 0)]
            ),
        ),
        (
            "BSplineCurve.approximate(parameters)",
            lambda: Part.BSplineCurve().approximate(
                Points=[V(0, 0, 0), V(1, 1, 0), V(2, 0, 0), V(3, 1, 0)], Parameters=[0, 1, 2 * v, 3]
            ),
        ),
        # Bezier curve weights and interpolation
        ("BezierCurve.setWeight", _call(_bezier, "setWeight", 2, v)),
        ("BezierCurve.setPole(weight)", _call(_bezier, "setPole", 2, V(1, 1, 0), v)),
        ("BezierCurve.insertPoleAfter(weight)", _call(_bezier, "insertPoleAfter", 1, V(1, 1, 0), v)),
        ("BezierCurve.insertPoleBefore(weight)", _call(_bezier, "insertPoleBefore", 2, V(1, 1, 0), v)),
        (
            "BezierCurve.interpolate(points)",
            lambda: Part.BezierCurve().interpolate([[V(0, 0, 0)], [V(v, 1, 0)]]),
        ),
        (
            "BezierCurve.interpolate(parameters)",
            lambda: Part.BezierCurve().interpolate([[V(0, 0, 0)], [V(1, 1, 0)]], [0, v]),
        ),
        # B-spline surface
        ("BSplineSurface.setPole", _call(_bspline_surface, "setPole", 2, 2, V(v, 0, 0))),
        ("BSplineSurface.setPole(weight)", _call(_bspline_surface, "setPole", 2, 2, V(1, 1, 0), v)),
        (
            "BSplineSurface.setPoleCol",
            _call(_bspline_surface, "setPoleCol", 2, [V(v, j, 0) for j in range(6)]),
        ),
        (
            "BSplineSurface.setPoleCol(weights)",
            _call(_bspline_surface, "setPoleCol", 2, [V(1, j, 0) for j in range(6)], [v] * 6),
        ),
        (
            "BSplineSurface.setPoleRow",
            _call(_bspline_surface, "setPoleRow", 2, [V(j, v, 0) for j in range(6)]),
        ),
        ("BSplineSurface.setWeight", _call(_bspline_surface, "setWeight", 2, 2, v)),
        ("BSplineSurface.setWeightCol", _call(_bspline_surface, "setWeightCol", 2, [v] * 6)),
        ("BSplineSurface.setWeightRow", _call(_bspline_surface, "setWeightRow", 2, [v] * 6)),
        ("BSplineSurface.setUKnot", lambda: _bspline_surface().setUKnot(2, bss_knot * v)),
        ("BSplineSurface.setVKnot", lambda: _bspline_surface().setVKnot(2, bss_knot * v)),
        (
            "BSplineSurface.setUKnots",
            lambda: (lambda s: s.setUKnots([k * v for k in s.getUKnots()]))(_bspline_surface()),
        ),
        (
            "BSplineSurface.insertUKnot",
            lambda: _bspline_surface().insertUKnot(0.5 * bss_knot * v, 1, 0),
        ),
        (
            "BSplineSurface.insertVKnots",
            lambda: _bspline_surface().insertVKnots([0.5 * bss_knot * v], [1]),
        ),
        (
            "BSplineSurface.movePoint",
            _call(_bspline_surface, "movePoint", 0.5, 0.5, V(v, 0, 0), 2, 3, 2, 3),
        ),
        (
            "BSplineSurface.interpolate(points)",
            lambda: Part.BSplineSurface().interpolate(
                [[V(i, j, v if i == j == 1 else 0) for j in range(3)] for i in range(3)]
            ),
        ),
        (
            "BSplineSurface.interpolate(heights)",
            lambda: Part.BSplineSurface().interpolate([[0, 1, 0], [1, v, 1], [0, 1, 0]], 0, 1, 0, 1),
        ),
        (
            "BSplineSurface.interpolate(grid)",
            lambda: Part.BSplineSurface().interpolate([[0, 1, 0], [1, 2, 1], [0, 1, 0]], 0, v, 0, 1),
        ),
        (
            "BSplineSurface.approximate",
            lambda: Part.BSplineSurface().approximate(
                [[V(i, j, v if i == j == 1 else 0) for j in range(3)] for i in range(3)]
            ),
        ),
        (
            "BSplineSurface.buildFromPolesMultsKnots(poles)",
            lambda: Part.BSplineSurface().buildFromPolesMultsKnots(
                [[V(0, 0, 0), V(0, 1, 0)], [V(1, 0, 0), V(1, v, 0)]], [2, 2], [2, 2], [0, 1], [0, 1],
                False, False, 1, 1,
            ),
        ),
        (
            "BSplineSurface.buildFromPolesMultsKnots(knots)",
            lambda: Part.BSplineSurface().buildFromPolesMultsKnots(
                [[V(0, 0, 0), V(0, 1, 0)], [V(1, 0, 0), V(1, 1, 0)]], [2, 2], [2, 2], [0, v], [0, 1],
                False, False, 1, 1,
            ),
        ),
        (
            "BSplineSurface.buildFromPolesMultsKnots(weights)",
            lambda: Part.BSplineSurface().buildFromPolesMultsKnots(
                [[V(0, 0, 0), V(0, 1, 0)], [V(1, 0, 0), V(1, 1, 0)]], [2, 2], [2, 2], [0, 1], [0, 1],
                False, False, 1, 1, [[1, 1], [1, v]],
            ),
        ),
        # Bezier surface
        ("BezierSurface.setPole", _call(_bezier_surface, "setPole", 2, 2, V(v, 0, 0))),
        ("BezierSurface.setPole(weight)", _call(_bezier_surface, "setPole", 2, 2, V(1, 1, 0), v)),
        (
            "BezierSurface.setPoleCol",
            _call(_bezier_surface, "setPoleCol", 2, [V(v, j, 0) for j in range(3)]),
        ),
        (
            "BezierSurface.setPoleRow(weights)",
            _call(_bezier_surface, "setPoleRow", 2, [V(j, 1, 0) for j in range(3)], [1, v, 1]),
        ),
        ("BezierSurface.setWeight", _call(_bezier_surface, "setWeight", 2, 2, v)),
        ("BezierSurface.setWeightCol", _call(_bezier_surface, "setWeightCol", 2, [v] * 3)),
        (
            "BezierSurface.insertPoleColAfter",
            _call(_bezier_surface, "insertPoleColAfter", 1, [V(v, j, 0) for j in range(3)]),
        ),
        (
            "BezierSurface.insertPoleRowBefore",
            _call(_bezier_surface, "insertPoleRowBefore", 2, [V(j, v, 0) for j in range(3)]),
        ),
        # shape transforms
        ("Shape.translate", lambda: Part.makeBox(1, 1, 1).translate(V(v, 0, 0))),
        ("Shape.translate(tuple)", lambda: Part.makeBox(1, 1, 1).translate((v, 0, 0))),
        ("Shape.translated", lambda: Part.makeBox(1, 1, 1).translated(V(v, 0, 0))),
        ("Shape.rotate(center)", lambda: Part.makeBox(1, 1, 1).rotate(V(v, 0, 0), V(0, 0, 1), 10)),
        ("Shape.rotate(axis)", lambda: Part.makeBox(1, 1, 1).rotate(V(0, 0, 0), V(0, 0, v), 10)),
        ("Shape.rotate(angle)", lambda: Part.makeBox(1, 1, 1).rotate(V(0, 0, 0), V(0, 0, 1), 10 * v)),
        ("Shape.rotated(tuples)", lambda: Part.makeBox(1, 1, 1).rotated((0, 0, 0), (0, 0, v), 10)),
        ("Shape.mirror(base)", lambda: Part.makeBox(1, 1, 1).mirror(V(v, 0, 0), V(1, 0, 0))),
        ("Shape.mirror(normal)", lambda: Part.makeBox(1, 1, 1).mirror(V(0, 0, 0), V(v, 0, 0))),
        ("Shape.scale(factor)", lambda: Part.makeBox(1, 1, 1).scale(2 * v)),
        ("Shape.scale(center)", lambda: Part.makeBox(1, 1, 1).scale(2, V(v, 0, 0))),
        ("Shape.scaled", lambda: Part.makeBox(1, 1, 1).scaled(2 * v)),
        ("Shape.transformGeometry", lambda: Part.makeBox(1, 1, 1).transformGeometry(_matrix(v))),
        ("Shape.transformShape", lambda: Part.makeBox(1, 1, 1).transformShape(_matrix(v))),
        ("Shape.transformed", lambda: Part.makeBox(1, 1, 1).transformed(_matrix(v))),
        # face, shell and solid helpers
        ("Face.makeHalfSpace", lambda: Part.makeBox(1, 1, 1).Faces[0].makeHalfSpace(V(v, 0, 0))),
        ("Shell.makeHalfSpace", lambda: Part.makeBox(1, 1, 1).Shells[0].makeHalfSpace(V(2 * v, 0, 0))),
        (
            "Solid.offsetFaces",
            lambda: (lambda s: s.offsetFaces([s.Faces[0]], 0.5 * v))(_box_solid()),
        ),
        (
            "Solid.offsetFaces(dict)",
            lambda: (lambda s: s.offsetFaces({s.Faces[0]: 0.5 * v}))(_box_solid()),
        ),
        # geometry transforms
        ("Geometry.translate", _call(Part.Circle, "translate", V(v, 0, 0))),
        ("Geometry.translate(tuple)", _call(Part.Circle, "translate", (v, 0, 0))),
        ("Geometry.mirror(point)", _call(Part.Circle, "mirror", V(v, 0, 0))),
        ("Geometry.mirror(axis)", _call(Part.Circle, "mirror", V(0, 0, 0), V(v, 0, 0))),
        (
            "Geometry.rotate",
            _call(Part.Circle, "rotate", FreeCAD.Placement(V(v, 0, 0), FreeCAD.Rotation())),
        ),
        ("Geometry.scale(center)", _call(Part.Circle, "scale", V(v, 0, 0), 2)),
        ("Geometry.transform", _call(Part.Circle, "transform", _matrix(v))),
        # 2D geometry
        ("Circle2d(center)", lambda: Geom2d.Circle2d(V2(v, 0), 1)),
        ("Circle2d(radius)", lambda: Geom2d.Circle2d(V2(0, 0), v)),
        ("Circle2d(3 points)", lambda: Geom2d.Circle2d(V2(v, 0), V2(0, 1), V2(-1, 0))),
        ("Circle2d(circle, distance)", lambda: Geom2d.Circle2d(Geom2d.Circle2d(), v)),
        ("Circle2d.Radius", _setter(Geom2d.Circle2d, "Radius", v)),
        ("Circle2d.Location", _setter(Geom2d.Circle2d, "Location", V2(v, 0))),
        ("Circle2d.XAxis", _setter(Geom2d.Circle2d, "XAxis", V2(v, 0))),
        ("Circle2d.YAxis", _setter(Geom2d.Circle2d, "YAxis", V2(0, v))),
        ("Ellipse2d(center)", lambda: Geom2d.Ellipse2d(V2(v, 0), 2, 1)),
        ("Ellipse2d(major)", lambda: Geom2d.Ellipse2d(V2(0, 0), 2 * v, 1)),
        ("Ellipse2d(3 points)", lambda: Geom2d.Ellipse2d(V2(2 * v, 0), V2(0, 1), V2(0, 0))),
        ("Ellipse2d.MajorRadius", _setter(Geom2d.Ellipse2d, "MajorRadius", 3 * v)),
        ("Ellipse2d.MinorRadius", _setter(Geom2d.Ellipse2d, "MinorRadius", v)),
        ("Hyperbola2d(center)", lambda: Geom2d.Hyperbola2d(V2(v, 0), 2, 1)),
        ("Hyperbola2d(minor)", lambda: Geom2d.Hyperbola2d(V2(0, 0), 2, v)),
        ("Hyperbola2d.MajorRadius", _setter(Geom2d.Hyperbola2d, "MajorRadius", 2 * v)),
        ("Hyperbola2d.MinorRadius", _setter(Geom2d.Hyperbola2d, "MinorRadius", v)),
        ("Parabola2d.Focal", _setter(Geom2d.Parabola2d, "Focal", v)),
        ("Line2d(p, q)", lambda: Geom2d.Line2d(V2(0, 0), V2(v, 0))),
        ("Line2d.Location", _setter(Geom2d.Line2d, "Location", V2(v, 0))),
        ("Line2d.Location(tuple)", _setter(Geom2d.Line2d, "Location", (v, 0))),
        ("Line2d.Direction", _setter(Geom2d.Line2d, "Direction", V2(v, 0))),
        ("Line2d.Direction(tuple)", _setter(Geom2d.Line2d, "Direction", (v, 0))),
        ("Line2dSegment(p, q)", lambda: Geom2d.Line2dSegment(V2(0, 0), V2(v, 0))),
        (
            "Line2dSegment.StartPoint",
            _setter(lambda: Geom2d.Line2dSegment(V2(0, 0), V2(2, 0)), "StartPoint", V2(v, 0)),
        ),
        (
            "Line2dSegment.EndPoint",
            _setter(lambda: Geom2d.Line2dSegment(V2(0, 0), V2(2, 0)), "EndPoint", (v, 0)),
        ),
        (
            "ArcOfCircle2d.Radius",
            _setter(lambda: Geom2d.ArcOfCircle2d(Geom2d.Circle2d(), 0, 1), "Radius", v),
        ),
        (
            "ArcOfCircle2d.Location",
            _setter(lambda: Geom2d.ArcOfCircle2d(Geom2d.Circle2d(), 0, 1), "Location", V2(v, 0)),
        ),
        (
            "ArcOfCircle2d.XAxis",
            _setter(lambda: Geom2d.ArcOfCircle2d(Geom2d.Circle2d(), 0, 1), "XAxis", V2(v, 0)),
        ),
        (
            "ArcOfEllipse2d.MajorRadius",
            _setter(lambda: Geom2d.ArcOfEllipse2d(Geom2d.Ellipse2d(), 0, 1), "MajorRadius", 3 * v),
        ),
        (
            "ArcOfHyperbola2d.MinorRadius",
            _setter(lambda: Geom2d.ArcOfHyperbola2d(Geom2d.Hyperbola2d(), 0, 1), "MinorRadius", v),
        ),
        (
            "ArcOfParabola2d.Focal",
            _setter(lambda: Geom2d.ArcOfParabola2d(Geom2d.Parabola2d(), 0, 1), "Focal", v),
        ),
        ("OffsetCurve2d(offset)", lambda: Geom2d.OffsetCurve2d(Geom2d.Circle2d(), v)),
        (
            "OffsetCurve2d.OffsetValue",
            _setter(lambda: Geom2d.OffsetCurve2d(Geom2d.Circle2d(), 1), "OffsetValue", v),
        ),
        (
            "BSplineCurve2d.buildFromPoles",
            lambda: Geom2d.BSplineCurve2d().buildFromPoles([V2(0, 0), V2(v, 1), V2(2, 0)]),
        ),
        ("BSplineCurve2d.setPole", _call(_bspline2d, "setPole", 2, V2(v, 1))),
        ("BSplineCurve2d.setPole(weight)", _call(_bspline2d, "setPole", 2, V2(1, 1), v)),
        ("BSplineCurve2d.setWeight", _call(_bspline2d, "setWeight", 2, v)),
        ("BSplineCurve2d.setKnot", _call(_bspline2d, "setKnot", 2, v)),
        ("BSplineCurve2d.setKnots", _call(_bspline2d, "setKnots", [0, v, 2, 3])),
        ("BSplineCurve2d.insertKnot", _call(_bspline2d, "insertKnot", 0.5 * v)),
        ("BSplineCurve2d.insertKnots", _call(_bspline2d, "insertKnots", [0.5 * v], [1])),
        ("BSplineCurve2d.movePoint", _call(_bspline2d, "movePoint", 1.5, V2(v, 1), 2, 3)),
        (
            "BSplineCurve2d.interpolate(points)",
            lambda: Geom2d.BSplineCurve2d().interpolate([V2(0, 0), V2(v, 1), V2(2, 0)]),
        ),
        (
            "BSplineCurve2d.interpolate(parameters)",
            lambda: Geom2d.BSplineCurve2d().interpolate(
                [V2(0, 0), V2(1, 1), V2(2, 0)], Parameters=[0, v, 2]
            ),
        ),
        (
            "BSplineCurve2d.interpolate(end tangents)",
            lambda: Geom2d.BSplineCurve2d().interpolate(
                [V2(0, 0), V2(1, 1), V2(2, 0)], InitialTangent=V2(v, 0), FinalTangent=V2(1, 0)
            ),
        ),
        (
            "BSplineCurve2d.approximate(points)",
            lambda: Geom2d.BSplineCurve2d().approximate(
                Points=[V2(0, 0), V2(1, 1), V2(2 * v, 0), V2(3, 1)]
            ),
        ),
        (
            "BSplineCurve2d.buildFromPolesMultsKnots(poles)",
            lambda: Geom2d.BSplineCurve2d().buildFromPolesMultsKnots(
                [V2(0, 0), V2(1, v), V2(2, 0)], [3, 3], [0, 1], False, 2
            ),
        ),
        (
            "BSplineCurve2d.buildFromPolesMultsKnots(knots)",
            lambda: Geom2d.BSplineCurve2d().buildFromPolesMultsKnots(
                [V2(0, 0), V2(1, 1), V2(2, 0)], [3, 3], [0, v], False, 2
            ),
        ),
        (
            "BSplineCurve2d.buildFromPolesMultsKnots(weights)",
            lambda: Geom2d.BSplineCurve2d().buildFromPolesMultsKnots(
                [V2(0, 0), V2(1, 1), V2(2, 0)], [3, 3], [0, 1], False, 2, [1, v, 1]
            ),
        ),
        ("BezierCurve2d(poles)", lambda: Geom2d.BezierCurve2d([V2(0, 0), V2(v, 1), V2(2, 0)])),
        ("BezierCurve2d.setPole", _call(_bezier2d, "setPole", 2, V2(v, 1))),
        ("BezierCurve2d.setPole(weight)", _call(_bezier2d, "setPole", 2, V2(1, 1), v)),
        ("BezierCurve2d.setWeight", _call(_bezier2d, "setWeight", 2, v)),
        ("BezierCurve2d.insertPoleAfter", _call(_bezier2d, "insertPoleAfter", 1, V2(v, 1))),
        ("BezierCurve2d.insertPoleBefore(weight)", _call(_bezier2d, "insertPoleBefore", 2, V2(1, 1), v)),
        ("Geometry2d.translate", _call(Geom2d.Circle2d, "translate", V2(v, 0))),
        ("Geometry2d.mirror(point)", _call(Geom2d.Circle2d, "mirror", V2(v, 0))),
        ("Geometry2d.mirror(axis)", _call(Geom2d.Circle2d, "mirror", V2(0, 0), V2(v, 0))),
        ("Geometry2d.rotate(center)", _call(Geom2d.Circle2d, "rotate", V2(v, 0), 1)),
        ("Geometry2d.rotate(angle)", _call(Geom2d.Circle2d, "rotate", V2(0, 0), v)),
        ("Geometry2d.scale(center)", _call(Geom2d.Circle2d, "scale", V2(v, 0), 2)),
        ("Geometry2d.scale(factor)", _call(Geom2d.Circle2d, "scale", V2(0, 0), 2 * v)),
        ("Geometry2d.transform", _call(Geom2d.Circle2d, "transform", [1, 0, v, 0, 1, 0])),
    ]


class PartFiniteInputTests(unittest.TestCase):
    def testNonFiniteInputRaisesValueError(self):
        for bad in (math.nan, math.inf, -math.inf):
            for name, call in _cases(bad):
                with self.subTest(entry=name, value=bad):
                    with self.assertRaisesRegex(ValueError, "must be finite"):
                        call()

    def testFiniteInputStillWorks(self):
        for name, call in _cases(1.0):
            with self.subTest(entry=name):
                call()

    def testNonFiniteKnotsWeightsAndTransformsRaiseValueError(self):
        for bad in (math.nan, math.inf, -math.inf):
            for name, call in _more_cases(bad):
                with self.subTest(entry=name, value=bad):
                    with self.assertRaisesRegex(ValueError, "must be finite"):
                        call()

    def testFiniteKnotsWeightsAndTransformsStillWork(self):
        for name, call in _more_cases(1.0):
            with self.subTest(entry=name):
                call()

    def testFiniteTransformResultsUnchanged(self):
        box = Part.makeBox(1, 1, 1)
        box.translate(V(1, 2, 3))
        self.assertEqual(box.BoundBox.XMin, 1)
        box = Part.makeBox(1, 1, 1).scaled(2, V(0, 0, 0))
        self.assertAlmostEqual(box.Volume, 8)
        self.assertAlmostEqual(Part.makeBox(1, 1, 1).rotated(V(0, 0, 0), V(0, 0, 1), 90).BoundBox.XMin, -1)
        box = Part.makeBox(1, 1, 1).transformed(_matrix(5))
        self.assertAlmostEqual(box.BoundBox.XMin, 5)
        curve = _bspline_with_inner_knots()
        curve.setWeight(2, 2)
        self.assertEqual(curve.getWeight(2), 2)
        curve.insertKnot(0.5)
        self.assertEqual(curve.getKnots(), [0, 0.5, 1, 2, 3])
        circle = Geom2d.Circle2d(V2(1, 2), 3)
        self.assertEqual((circle.Location.x, circle.Location.y), (1, 2))
        circle.translate(V2(1, 0))
        self.assertEqual((circle.Location.x, circle.Location.y), (2, 2))
        self.assertEqual(Part.OffsetCurve(Part.Circle(), 2, V(0, 0, 1)).OffsetValue, 2)

    def testFiniteResultsUnchanged(self):
        self.assertEqual(Part.Point(V(1, 2, 3)).Z, 3)
        self.assertEqual(Part.Vertex(1, 2, 3).Point, V(1, 2, 3))
        self.assertAlmostEqual(Part.makeBox(1, 2, 3, V(1, 1, 1)).Volume, 6)
        self.assertAlmostEqual(Part.makeCircle(2, V(1, 0, 0)).Length, 4 * math.pi)
        self.assertAlmostEqual(Part.makeLine(V(0, 0, 0), (3, 4, 0)).Length, 5)
        self.assertAlmostEqual(Part.makePolygon([V(0, 0, 0), V(1, 0, 0), V(1, 1, 0)]).Length, 2)
        circle = Part.Circle(V(1, 2, 3), V(0, 0, 1), 4)
        self.assertEqual(circle.Location, V(1, 2, 3))
        self.assertEqual(circle.Radius, 4)
        line = Part.Line()
        line.Direction = (0, 0, 2)
        self.assertEqual(line.Direction, V(0, 0, 1))
        self.assertEqual(_bspline().getPole(2), V(1, 1, 0))

    def testNullDirectionKeepsItsError(self):
        # a null direction is still reported by the existing error, not as a non-finite value
        with self.assertRaises(Part.OCCError):
            Part.makeBox(1, 1, 1, V(0, 0, 0), V(0, 0, 0))
        with self.assertRaises(RuntimeError) as cm:
            _setter(Part.Circle, "Axis", V(0, 0, 0))()
        self.assertNotIn("finite", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
