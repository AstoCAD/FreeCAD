# SPDX-License-Identifier: LGPL-2.1-or-later
"""Python serialization preserves dimensional values and locale-independent literals."""

import locale
import math
import unittest

import FreeCAD as App
import Part
import Sketcher


class TestConstraintValuePythonRoundTrip(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ConstraintValueRoundTrip")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def _roundtrip(self, kind, value):
        source = self.doc.addObject("Sketcher::SketchObject", "Source")
        if kind == "Radius":
            geometry = Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), value)
        elif kind == "Distance":
            geometry = Part.LineSegment(App.Vector(0, 0, 0), App.Vector(value, 0, 0))
        elif kind == "Angle":
            geometry = Part.LineSegment(
                App.Vector(0, 0, 0),
                App.Vector(10 * math.cos(value), 10 * math.sin(value), 0),
            )
        else:
            self.fail("Unsupported test geometry")
        source.addGeometry(geometry, False)
        source.addConstraint(Sketcher.Constraint(kind, 0, value))
        self.doc.recompute()
        self.assertEqual(source.solve(), 0, "Source must be a valid solved sketch")
        self.assertEqual(source.ConstraintCount, 1)
        self.assertEqual(source.Constraints[0].Value, value, "Fixture must retain input precision")
        original_value = source.Constraints[0].Value
        commands = tuple(source.toPythonCommands())
        self.assertTrue(commands)

        target = self.doc.addObject("Sketcher::SketchObject", "Target")
        scope = {"App": App, "Part": Part, "Sketcher": Sketcher, "ActiveSketch": target}
        for command in commands:
            exec(command, scope)
        self.doc.recompute()
        self.assertEqual(target.solve(), 0, "Replay must produce a valid solved sketch")
        self.assertEqual(target.GeometryCount, 1)
        self.assertEqual(target.ConstraintCount, 1)
        self.assertEqual(target.Constraints[0].Type, kind)
        self.assertEqual(source.Constraints[0].Value, original_value, "Export must not mutate source")
        self.assertEqual(
            target.Constraints[0].Value,
            original_value,
            "Python replay silently changed the dimensional constraint value; commands="
            + repr(commands),
        )

    def test_radius_constraint_value_retains_all_double_digits(self):
        self._roundtrip("Radius", 1.234567891234568)

    def test_distance_constraint_value_retains_all_double_digits(self):
        self._roundtrip("Distance", 12.34567891234568)

    def test_angle_constraint_value_retains_all_double_digits(self):
        self._roundtrip("Angle", 0.3456789123456789)

    def test_radius_exact_six_decimal_control(self):
        self._roundtrip("Radius", 12.125)

    def test_distance_exact_six_decimal_control(self):
        self._roundtrip("Distance", 10.25)

    def test_angle_exact_six_decimal_control(self):
        self._roundtrip("Angle", 0.375)


class TestConstraintPythonRoundTripCompatibility(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ConstraintRoundTripCompatibility")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def _source(self, geometries, constraint):
        source = self.doc.addObject("Sketcher::SketchObject", "Source")
        source.addGeometry(geometries, False)
        source.addConstraint(constraint)
        self.doc.recompute()
        self.assertEqual(source.solve(), 0, "Source geometry/constraint must solve")
        self.assertEqual(source.ConstraintCount, 1)
        return source

    @staticmethod
    def _fields(sketch):
        c = sketch.Constraints[0]
        return (c.Type, c.First, c.FirstPos, c.Second, c.SecondPos, c.Third,
                c.ThirdPos, sketch.getActive(0), sketch.getDriving(0))

    def _replay(self, source):
        fields = self._fields(source)
        expected = source.Constraints[0].Value
        commands = tuple(source.toPythonCommands())
        self.assertTrue(commands)
        target = self.doc.addObject("Sketcher::SketchObject", "Target")
        scope = {"App": App, "Part": Part, "Sketcher": Sketcher, "ActiveSketch": target}
        try:
            for command in commands:
                exec(command, scope)
        except Exception as exc:
            self.fail("Valid sketch replay raised {}: {}; commands={!r}".format(
                type(exc).__name__, exc, commands))
        self.doc.recompute()
        self.assertEqual(target.solve(), 0, "Replayed geometry/constraint must solve")
        self.assertEqual(target.GeometryCount, source.GeometryCount)
        self.assertEqual(target.ConstraintCount, 1)
        self.assertEqual(self._fields(target), fields, "Identity/flags must remain unchanged")
        self.assertEqual(source.Constraints[0].Value, expected, "Source must not mutate")
        self.assertEqual(target.Constraints[0].Value, expected,
                         "Dimensional precision changed; commands=" + repr(commands))
        return target

    def test_submicro_radius_is_nonzero_and_replays(self):
        value = 4.56789123456789e-7
        source = self._source(
            [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), value)],
            Sketcher.Constraint("Radius", 0, value),
        )
        self.assertGreater(source.Geometry[0].Radius, 1e-7)
        self.assertLess(source.Geometry[0].Radius, 1e-6)
        self.assertGreater(source.Constraints[0].Value, 0)
        target = self._replay(source)
        self.assertGreater(target.Geometry[0].Radius, 0)

    def test_snells_law_dimensionless_ratio_replays(self):
        source = self._source(
            [Part.LineSegment(App.Vector(-5, -10, 0), App.Vector(0, 0, 0)),
             Part.LineSegment(App.Vector(0, 0, 0), App.Vector(3, 10, 0)),
             Part.LineSegment(App.Vector(-10, 0, 0), App.Vector(10, 0, 0))],
            Sketcher.Constraint("SnellsLaw", 0, 2, 1, 1, 2, 1.234567891234568),
        )
        self.assertEqual(source.Constraints[0].Value, 1.234567891234568)
        self._replay(source)

    def test_signed_point_distance_with_inactive_flag_replays(self):
        value = -1.234567891234568
        source = self._source(
            [Part.LineSegment(App.Vector(value, 2, 0), App.Vector(value + 1, 3, 0))],
            Sketcher.Constraint("DistanceX", 0, 1, value, False, True),
        )
        self.assertFalse(source.getActive(0))
        self.assertTrue(source.getDriving(0))
        self._replay(source)

    def test_negative_zero_point_distance_preserves_sign_control(self):
        source = self._source(
            [Part.LineSegment(App.Vector(0, 2, 0), App.Vector(1, 3, 0))],
            Sketcher.Constraint("DistanceX", 0, 1, -0.0, False, True),
        )
        self.assertEqual(source.Constraints[0].Value, 0.0)
        self.assertLess(math.copysign(1.0, source.Constraints[0].Value), 0)
        target = self._replay(source)
        self.assertLess(math.copysign(1.0, target.Constraints[0].Value), 0,
                        "Float -0.0 must not become the integer literal -0")

    def test_comma_numeric_locale_replays_ordinary_radius(self):
        previous = locale.setlocale(locale.LC_NUMERIC)
        try:
            selected = None
            for candidate in ("fr_FR.UTF-8", "fr_FR", "French_France.1252", "French_France", "fr-FR"):
                try:
                    locale.setlocale(locale.LC_NUMERIC, candidate)
                except locale.Error:
                    continue
                if locale.localeconv()["decimal_point"] == ",":
                    selected = candidate
                    break
            if selected is None:
                self.skipTest("No installed comma LC_NUMERIC locale")
            self.assertEqual(locale.localeconv()["decimal_point"], ",")
            source = self._source(
                [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 12.125)],
                Sketcher.Constraint("Radius", 0, 12.125),
            )
            self._replay(source)
        finally:
            locale.setlocale(locale.LC_NUMERIC, previous)

    def test_inactive_reference_radius_flags_and_sentinels_control(self):
        source = self._source(
            [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 12.125)],
            Sketcher.Constraint("Radius", 0, 12.125, False, False),
        )
        self.assertFalse(source.getActive(0))
        self.assertFalse(source.getDriving(0))
        self._replay(source)


class TestConstraintPythonThirdElementRoundTrip(unittest.TestCase):
    """Tangent/Perpendicular forms with a third element keep it in the Python commands."""

    def setUp(self):
        self.doc = App.newDocument("ConstraintThirdElementRoundTrip")
        self.addCleanup(App.closeDocument, self.doc.Name)

    @staticmethod
    def _elements(constraint):
        c = constraint
        return (c.Type, c.First, c.FirstPos, c.Second, c.SecondPos, c.Third, c.ThirdPos)

    def _replay(self, geometries, constraint):
        source = self.doc.addObject("Sketcher::SketchObject", "Source")
        source.addGeometry(geometries, False)
        source.addConstraint(constraint)
        self.doc.recompute()
        self.assertEqual(source.solve(), 0, "Source geometry/constraint must solve")
        expected = self._elements(source.Constraints[0])

        commands = tuple(source.toPythonCommands())
        target = self.doc.addObject("Sketcher::SketchObject", "Target")
        scope = {"App": App, "Part": Part, "Sketcher": Sketcher, "ActiveSketch": target}
        for command in commands:
            exec(command, scope)
        self.doc.recompute()
        self.assertEqual(target.ConstraintCount, 1)
        self.assertEqual(
            self._elements(target.Constraints[0]), expected, "commands=" + repr(commands)
        )
        self.assertEqual(target.solve(), 0)

    def test_tangent_via_point(self):
        self._replay(
            [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5),
             Part.Circle(App.Vector(10, 0, 0), App.Vector(0, 0, 1), 5),
             Part.Point(App.Vector(5, 0, 0))],
            Sketcher.Constraint("TangentViaPoint", 0, 1, 2, 1),
        )

    def test_perpendicular_via_point(self):
        self._replay(
            [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
             Part.Circle(App.Vector(5, 0, 0), App.Vector(0, 0, 1), 3),
             Part.Point(App.Vector(8, 0, 0))],
            Sketcher.Constraint("PerpendicularViaPoint", 0, 1, 2, 1),
        )

    def test_perpendicular_point_point_line(self):
        self._replay(
            [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
             Part.LineSegment(App.Vector(3, -2, 0), App.Vector(3, 4, 0))],
            Sketcher.Constraint("Perpendicular", 1, 1, 1, 2, 0),
        )

    def test_tangent_endpoint_to_endpoint_control(self):
        self._replay(
            [Part.LineSegment(App.Vector(-10, 5, 0), App.Vector(0, 5, 0)),
             Part.ArcOfCircle(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5), 0, 1.5707963267948966)],
            Sketcher.Constraint("Tangent", 0, 2, 1, 2),
        )

    def test_perpendicular_edges_control(self):
        self._replay(
            [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
             Part.LineSegment(App.Vector(3, -2, 0), App.Vector(3, 4, 0))],
            Sketcher.Constraint("Perpendicular", 0, 1),
        )


class TestReversedArcPythonRoundTrip(unittest.TestCase):
    """Arcs with a clockwise (-Z) axis, e.g. from a flipped carbon copy, replay unchanged."""

    def setUp(self):
        self.doc = App.newDocument("ReversedArcRoundTrip")
        self.addCleanup(App.closeDocument, self.doc.Name)

    def _replay(self, geometry, reverse):
        if reverse:
            # Mirroring about an in-plane axis turns the arc clockwise (axis -Z).
            geometry.mirror(App.Vector(0, 0, 0), App.Vector(1, 0, 0))
        source = self.doc.addObject("Sketcher::SketchObject", "Source")
        source.addGeometry(geometry, False)
        self.doc.recompute()
        self.assertAlmostEqual(source.Geometry[0].Axis.z, -1.0 if reverse else 1.0)
        commands = tuple(source.toPythonCommands())

        target = self.doc.addObject("Sketcher::SketchObject", "Target")
        scope = {"App": App, "Part": Part, "Sketcher": Sketcher, "ActiveSketch": target}
        for command in commands:
            exec(command, scope)
        self.doc.recompute()
        self.assertEqual(target.GeometryCount, 1)
        # Start, end and center as the sketcher sees them (counter-clockwise in XY).
        for pos in (1, 2, 3):
            self.assertAlmostEqual(
                (source.getPoint(0, pos) - target.getPoint(0, pos)).Length,
                0,
                places=6,
                msg="point %d moved; commands=%r" % (pos, commands),
            )
        middle = source.Geometry[0].value(
            (source.Geometry[0].FirstParameter + source.Geometry[0].LastParameter) / 2
        )
        self.assertAlmostEqual(
            target.Shape.distToShape(Part.Vertex(middle))[0], 0, places=6, msg=repr(commands)
        )

    def _arc(self):
        return Part.ArcOfCircle(Part.Circle(App.Vector(1, 1, 0), App.Vector(0, 0, 1), 3), 0.3, 2.0)

    def _arcOfEllipse(self):
        ellipse = Part.Ellipse(App.Vector(3, 4, 0), App.Vector(-1.6, 1.2, 0), App.Vector(0, 0, 0))
        return Part.ArcOfEllipse(ellipse, 0.5, 2.5)

    def test_reversed_arc_of_circle(self):
        self._replay(self._arc(), True)

    def test_reversed_arc_of_ellipse(self):
        self._replay(self._arcOfEllipse(), True)

    def test_arc_of_circle_control(self):
        self._replay(self._arc(), False)

    def test_arc_of_ellipse_control(self):
        self._replay(self._arcOfEllipse(), False)
