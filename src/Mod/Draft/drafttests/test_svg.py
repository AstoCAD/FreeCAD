# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2013 Yorik van Havre <yorik@uncreated.net>              *
# *   Copyright (c) 2019 Eliud Cabrera Castillo <e.cabrera-castillo@tum.de> *
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
"""Unit tests for the Draft Workbench, SVG import and export tests."""

## @package test_svg
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, SVG import and export tests.

## \addtogroup drafttests
# @{

import math
import os
import tempfile
import unittest
from unittest import mock

import FreeCAD as App
import Draft
import Part
import draftfunctions.svgshapes as svgshapes
import importSVG
from drafttests import auxiliary as aux
from drafttests import test_base
from draftutils.messages import _msg

try:
    import Arch
except ModuleNotFoundError:
    have_arch = False
else:
    have_arch = True


class DraftSVG(test_base.DraftTestCaseDoc):
    """Test reading and writing of SVGs with Draft."""

    def test_read_svg(self):
        """Read an SVG file and import its elements as Draft objects."""
        operation = "importSVG.import"
        _msg("  Test '{}'".format(operation))
        _msg("  This test requires an SVG file to read.")

        file = "Mod/Draft/drafttest/test.svg"
        in_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(in_file))
        _msg("  exists={}".format(os.path.exists(in_file)))

        obj = aux.fake_function(in_file)
        self.assertTrue(obj, "'{}' failed".format(operation))

    def test_export_svg(self):
        """Create some figures and export them to an SVG file."""
        operation = "importSVG.export"
        _msg("  Test '{}'".format(operation))

        file = "Mod/Draft/drafttest/out_test.svg"
        out_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(out_file))
        _msg("  exists={}".format(os.path.exists(out_file)))

        obj = aux.fake_function(out_file)
        self.assertTrue(obj, "'{}' failed".format(operation))

    @unittest.skipIf(not have_arch, "BIM module is not installed")
    def test_get_svg_from_arch_space_with_zero_vector(self):
        """Try to get a svg string from an Arch Space with a zero-vector as direction."""
        import Part
        import Draft

        sb = Part.makeBox(1, 1, 1)
        b = self.doc.addObject("Part::Feature", "Box")
        b.Shape = sb

        s = Arch.makeSpace(b)
        self.doc.recompute()

        try:
            Draft.get_svg(s, direction=App.Vector(0, 0, 0))
        except AttributeError as err:
            self.fail("Cryptic exception thrown: {}".format(err))
        except ValueError as err:
            App.Console.PrintLog("Exception thrown, OK: {}".format(err))
        else:
            self.fail("no exception thrown")


class DraftSVGImportRegression(test_base.DraftTestCaseDoc):
    """Regression tests for SVG import edge cases."""

    def test_read_svg_recursive_use(self):
        """Recursive use tags and use tags pointing to defs must not hang the import."""
        body = (
            '<rect id="r" width="10" height="10"/>'
            '<use xlink:href="#r" x="20"/>'
            '<use id="u" xlink:href="#u"/>'
            '<g id="a"><use xlink:href="#b"/></g>'
            '<g id="b"><use xlink:href="#a"/></g>'
            '<defs id="d"><circle r="5"/></defs>'
            '<use xlink:href="#d"/>'
        )
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">' + body + "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "recursive_use.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            result = importSVG.replace_use_with_reference(in_file)
            importSVG.insert(in_file, self.doc.Name)
        self.assertNotIn("<use", result)
        # 'r' itself and its valid use
        self.assertEqual(result.count("<rect"), 2)

    def test_getsize_css_centimeters(self):
        """1 cm must convert to the same number of pixels as 10 mm."""
        for mode in ("css90.0", "css96.0"):
            with self.subTest(mode=mode):
                self.assertAlmostEqual(
                    importSVG.getsize("1cm", mode), importSVG.getsize("10mm", mode), places=9
                )
                self.assertAlmostEqual(
                    importSVG.getsize("2.54cm", mode), importSVG.getsize("1in", mode), places=9
                )

    def test_getsize_units_consistent_with_dpi(self):
        """pt and pc are absolute (1/72 and 1/6 in); em and ex follow the dpi in every mode."""
        for dpi in ("90.0", "96.0"):
            for mode in ("css" + dpi, "mm" + dpi):
                with self.subTest(mode=mode):
                    one_inch = importSVG.getsize("1in", mode)
                    self.assertAlmostEqual(importSVG.getsize("72pt", mode), one_inch, places=9)
                    self.assertAlmostEqual(importSVG.getsize("6pc", mode), one_inch, places=9)
            px_to_mm = 25.4 / float(dpi)
            for unit in ("em", "ex", "pt", "pc"):
                with self.subTest(dpi=dpi, unit=unit):
                    self.assertAlmostEqual(
                        importSVG.getsize("1" + unit, "mm" + dpi),
                        importSVG.getsize("1" + unit, "css" + dpi) * px_to_mm,
                        places=9,
                    )

    def test_read_svg_width_in_points_at_90_dpi(self):
        """A 72pt wide document (1 inch) must import 25.4 mm wide, also at 90 dpi."""
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
            'inkscape:version="0.91 r13725" sodipodi:docname="pt.svg" '
            'width="72pt" height="72pt" viewBox="0 0 72 72">'
            '<rect id="r" x="0" y="0" width="72" height="36" '
            'style="fill:none;stroke:#000000"/></svg>\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "points.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        shapes = [o.Shape for o in self.doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        self.assertEqual(len(shapes), 1)
        self.assertAlmostEqual(shapes[0].BoundBox.XLength, 25.4, places=3)
        self.assertAlmostEqual(shapes[0].BoundBox.YLength, 12.7, places=3)

    def test_read_svg_path_arc_compact_flags(self):
        """Arc flags written without separators ("a5 5 0 0010 0") are parsed."""
        import SVGPath

        cases = {
            "compact": "M0 0a5 5 0 0010 0",
            "compact_large_sweep": "M0 0a5 5 0 1110 0",
            "spaced": "M0 0 a5 5 0 0 0 10 0",
            "commas": "M0,0 a5,5,0,0,0,10,0",
            "float_flags": "M0 0 a5 5 0 0.0 1.0 10 0",
        }
        expected = {
            "compact": [5, 5, 0, 0, 0, 10, 0],
            "compact_large_sweep": [5, 5, 0, 1, 1, 10, 0],
            "spaced": [5, 5, 0, 0, 0, 10, 0],
            "commas": [5, 5, 0, 0, 0, 10, 0],
            "float_flags": [5, 5, 0, 0, 1, 10, 0],
        }
        for name, d in cases.items():
            with self.subTest(name=name):
                parser = SVGPath.SvgPathParser({"d": [d]}, name)
                parser.parse()
                edges = [e for edges in parser.shapes for e in edges]
                self.assertEqual(len(edges), 1)
                self.assertAlmostEqual(edges[0].Length, 5 * math.pi, places=6)
                arcs = [args for cmd, args in parser.commands if cmd in "Aa"]
                self.assertEqual(parser.arc_args(arcs[0]), expected[name])

    def test_read_svg_transform_compact_numbers(self):
        """Transform arguments without separators ("translate(20-30)") are parsed."""
        results = {}
        for name, transform in {
            "spaced": "translate(20,-30) scale(0.5 0.5)",
            "compact": "translate(20-30)scale(.5.5)",
        }.items():
            doc = App.newDocument("svg_" + name)
            try:
                svg = (
                    '<?xml version="1.0"?>\n'
                    '<svg xmlns="http://www.w3.org/2000/svg" '
                    'width="100mm" height="100mm" viewBox="0 0 100 100">'
                    '<rect x="0" y="0" width="10" height="10" transform="{}" '
                    'style="fill:none;stroke:#000000"/></svg>\n'.format(transform)
                )
                with tempfile.TemporaryDirectory() as temp_dir:
                    in_file = os.path.join(temp_dir, name + ".svg")
                    with open(in_file, "w", encoding="utf-8") as svg_file:
                        svg_file.write(svg)
                    importSVG.insert(in_file, doc.Name)
                shapes = [o.Shape for o in doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
                self.assertEqual(len(shapes), 1, name)
                bb = shapes[0].BoundBox
                results[name] = [round(v, 6) for v in (bb.XMin, bb.YMin, bb.XMax, bb.YMax)]
            finally:
                App.closeDocument(doc.Name)
        self.assertEqual(results["spaced"][0], 20)
        self.assertEqual(results["spaced"][2], 25)
        self.assertEqual(results["compact"], results["spaced"])

    def test_read_svg_polygon_compact_points(self):
        """Polygon points without separators ("0 0 10-5") are parsed."""
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">'
            '<polygon points="0,0 10-0 10-10" style="fill:none;stroke:#000000"/></svg>\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "polygon.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        shapes = [o.Shape for o in self.doc.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        self.assertEqual(len(shapes), 1)
        self.assertEqual(len(shapes[0].Edges), 3)
        self.assertAlmostEqual(shapes[0].Length, 20 + 200**0.5, places=6)
        self.assertEqual(importSVG.get_numbers("10-5.5.5 1e1,-2E-1"), [10, -5.5, 0.5, 10, -0.2])

    def test_read_svg_transform_list_with_matrix_and_skew(self):
        """matrix/skewX/skewY in a transform list must be applied in SVG order."""
        transforms = {
            # name: (transform, expected center of a circle at the origin, in FreeCAD coordinates)
            "scale": ("scale(2) translate(10,5)", App.Vector(20, -10, 0)),
            "matrix_first": ("matrix(2,0,0,2,0,0) translate(10,5)", App.Vector(20, -10, 0)),
            "matrix_last": ("translate(10,5) matrix(2,0,0,2,0,0)", App.Vector(10, -5, 0)),
            "skewx": ("skewX(45) translate(10,5)", App.Vector(15, -5, 0)),
            "skewy": ("skewY(45) translate(10,5)", App.Vector(10, -15, 0)),
        }
        body = "".join(
            '<circle id="{}" cx="0" cy="0" r="1" transform="{}"/>'.format(name, tr)
            for name, (tr, _) in transforms.items()
        )
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">' + body + "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "transform_list.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        for name, (_, expected) in transforms.items():
            with self.subTest(transform=name):
                # the imported circle faces are approximated (about 0.01 off even
                # for a plain scale); a wrong transform order is 5 to 10 mm off
                center = self.doc.getObject(name).Shape.Faces[0].CenterOfMass
                self.assertTrue(
                    center.isEqual(expected, 0.05), "{}: {} != {}".format(name, center, expected)
                )

    def test_read_svg_rect_corner_radius_clamped(self):
        """rx/ry larger than half the width/height must be clamped to half of it (SVG spec)."""
        body = (
            '<rect id="clamped" x="0" y="0" width="10" height="10" rx="8" fill="none" stroke="black"/>'
            '<rect id="clampedy" x="20" y="0" width="10" height="4" ry="3" fill="none" stroke="black"/>'
        )
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">' + body + "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "rounded_rect.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        # rx = ry = 8 on a 10 x 10 rect is clamped to 5: a circle of radius 5
        shape = self.doc.getObject("clamped").Shape
        self.assertAlmostEqual(shape.Length, 10 * math.pi, places=3)
        self.assertAlmostEqual(shape.BoundBox.XLength, 10, places=3)
        self.assertAlmostEqual(shape.BoundBox.YLength, 10, places=3)
        # ry = 3 (and rx = ry) on a 10 x 4 rect: ry is clamped to 2, rx stays 3,
        # giving elliptical corners and two 4 mm straight edges
        shape = self.doc.getObject("clampedy").Shape
        ellipse = Part.Ellipse(App.Vector(), 3, 2).toShape()
        self.assertAlmostEqual(shape.Length, 2 * 4 + ellipse.Length, places=3)
        self.assertAlmostEqual(shape.BoundBox.XLength, 10, places=3)
        self.assertAlmostEqual(shape.BoundBox.YLength, 4, places=3)

    def test_read_svg_gaps_can_be_welded_for_sketch(self):
        """Outlines drawn as paths that nearly meet are closed by welding their end points."""
        import SketcherBlock

        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "gaps.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(
                    '<?xml version="1.0"?>\n'
                    '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" '
                    'height="100mm" viewBox="0 0 100 100">'
                    '<g fill="none" stroke="black">'
                    '<path d="M 0,0 L 10,0 L 10,5"/>'
                    '<path d="M 10.0004,5 L 0,5 L 0,0.0004"/>'
                    "</g></svg>\n"
                )
            geometry = importSVG.readSketchGeometry(in_file)
            self.assertEqual(SketcherBlock.count_near_coincident(geometry, 1e-3), 2)
            # Without the GUI nothing is asked and nothing is changed.
            if not App.GuiUp:
                self.assertEqual(importSVG.offerEndpointWeld(geometry), 0)
                self.assertEqual(SketcherBlock.count_near_coincident(geometry, 1e-3), 2)
            self.assertEqual(SketcherBlock.weld_endpoints(geometry, 1e-3), 2)
            sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
            for geo in geometry:
                sketch.addGeometry(geo, False)
            self.doc.recompute()
            wires = sketch.Shape.Wires
            self.assertEqual(len(wires), 1)
            self.assertTrue(wires[0].isClosed())

    def test_read_svg_circular_arcs_stay_connected_in_sketch(self):
        """Circular corners and arcs (equal rx and ry) keep their end points in a sketch."""
        bodies = {
            "rounded_rect": '<rect x="1" y="2" width="30" height="20" rx="3" ry="3"/>',
            "path_arc": '<path d="M 10,10 A 5,5 0 0 1 15,15 L 10,15 Z"/>',
            "path_arc_other_sweep": '<path d="M 10,10 A 5,5 0 0 0 15,15 L 15,10 Z"/>',
            "rotated": '<g transform="rotate(33)"><rect width="30" height="20" rx="3"/></g>',
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, body in bodies.items():
                with self.subTest(name=name):
                    in_file = os.path.join(temp_dir, name + ".svg")
                    with open(in_file, "w", encoding="utf-8") as svg_file:
                        svg_file.write(
                            '<?xml version="1.0"?>\n'
                            '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" '
                            'height="100mm" viewBox="0 0 100 100">'
                            '<g fill="none" stroke="black">' + body + "</g></svg>\n"
                        )
                    source = importSVG.readShapes(in_file)
                    self.assertEqual(len(source), 1)
                    sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
                    for geometry in importSVG.readSketchGeometry(in_file):
                        sketch.addGeometry(geometry, False)
                    self.doc.recompute()
                    wires = sketch.Shape.Wires
                    self.assertEqual(len(wires), 1)
                    self.assertTrue(wires[0].isClosed())
                    self.assertAlmostEqual(wires[0].Length, source[0].Length, places=6)


    def test_read_svg_text_non_ascii(self):
        """Non-ASCII text is imported unchanged, not reduced to Latin-1."""
        # accented Latin, Greek and CJK characters
        texts = [
            "Caf\u00e9 \u00c9t\u00e9",
            "\u03a9\u03bc\u03ad\u03b3\u03b1",
            "\u65e5\u672c\u8a9e",
        ]
        body = "".join(
            '<text x="10" y="{}" font-size="5">{}</text>'.format(10 * (i + 1), text)
            for i, text in enumerate(texts)
        )
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">' + body + "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "non_ascii_text.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        labels = [o.LabelText for o in self.doc.Objects if o.isDerivedFrom("App::Annotation")]
        self.assertEqual(labels, [[text] for text in texts])


class DraftSVGExportRegression(test_base.DraftTestCaseDoc):
    """Regression tests for SVG export edge cases."""

    @staticmethod
    def _make_face_with_circular_island():
        outer = Part.makePolygon(
            [
                App.Vector(0, 0, 0),
                App.Vector(20, 0, 0),
                App.Vector(20, 20, 0),
                App.Vector(0, 20, 0),
                App.Vector(0, 0, 0),
            ]
        )
        inner = Part.Wire([Part.makeCircle(5, App.Vector(10, 10, 0), App.Vector(0, 0, 1))])
        return Part.Face([outer, inner])

    @staticmethod
    def _make_circular_face():
        wire = Part.Wire([Part.makeCircle(5, App.Vector(0, 0, 0), App.Vector(0, 0, 1))])
        return Part.Face([wire])

    @staticmethod
    def _make_face_with_rectangular_island_in_circle():
        outer = Part.Wire([Part.makeCircle(10, App.Vector(10, 10, 0), App.Vector(0, 0, 1))])
        inner = Part.makePolygon(
            [
                App.Vector(7, 8, 0),
                App.Vector(13, 8, 0),
                App.Vector(13, 12, 0),
                App.Vector(7, 12, 0),
                App.Vector(7, 8, 0),
            ]
        )
        return Part.Face([outer, inner])

    def _add_shape(self, name, shape):
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = shape
        self.doc.recompute()
        return obj

    def _assert_island_svg(self, svg):
        self.assertIn("<path ", svg)
        self.assertIn("fill-rule: evenodd", svg)
        self.assertNotIn("<circle ", svg)
        self.assertEqual(svg.count("M "), 2)
        self.assertEqual(svg.count("Z "), 2)
        self.assertEqual(svg.count("A "), 2)
        self.assertEqual(svg.count("L "), 4)

    @staticmethod
    def _iter_island_cases():
        return (
            ("rect_outer_circle_hole", DraftSVGExportRegression._make_face_with_circular_island),
            (
                "circle_outer_rect_hole",
                DraftSVGExportRegression._make_face_with_rectangular_island_in_circle,
            ),
        )

    @staticmethod
    def _force_circle_fallback():
        return mock.patch.object(svgshapes.TechDraw, "projectToSVG", return_value="")

    def test_get_svg_from_face_with_circular_island(self):
        with self._force_circle_fallback():
            for name, shape_factory in self._iter_island_cases():
                with self.subTest(case=name):
                    obj = self._add_shape(f"IslandFace_{name}", shape_factory())
                    svg = Draft.get_svg(obj, direction=App.Vector(0, 0, 1))
                    self._assert_island_svg(svg)

    def test_get_svg_from_face_with_circular_island_for_techdraw(self):
        with self._force_circle_fallback():
            for name, shape_factory in self._iter_island_cases():
                with self.subTest(case=name):
                    obj = self._add_shape(f"TechDrawIslandFace_{name}", shape_factory())
                    svg = Draft.get_svg(obj, direction=App.Vector(0, 0, 1), techdraw=True)
                    self._assert_island_svg(svg)

    def test_export_svg_from_face_with_circular_island(self):
        with self._force_circle_fallback():
            for name, shape_factory in self._iter_island_cases():
                with self.subTest(case=name):
                    obj = self._add_shape(f"ExportIslandFace_{name}", shape_factory())
                    with tempfile.TemporaryDirectory() as temp_dir:
                        out_file = os.path.join(temp_dir, "island_face.svg")
                        importSVG.export([obj], out_file)
                        with open(out_file, "r", encoding="utf-8") as svg_file:
                            svg = svg_file.read()
                    self._assert_island_svg(svg)

    def test_get_svg_from_circular_face_stays_compact(self):
        obj = self._add_shape("DiskFace", self._make_circular_face())

        svg = Draft.get_svg(obj, direction=App.Vector(0, 0, 1))

        self.assertIn("<circle ", svg)
        self.assertNotIn("fill-rule: evenodd", svg)

    def test_get_svg_from_arc_uses_hlr_for_all_occ_versions(self):
        """Arcs must be exported with the HLR projection on OCC >= 7.1.

        Issue #33345: with OCC 8.0 the version check failed (minor version 0)
        and the manual fallback wrote arcs with a wrong sweep flag.
        """
        import TechDraw

        edge = Part.ArcOfCircle(
            Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), 0, math.pi / 2
        ).toShape()
        obj = self._add_shape("Arc", edge)
        for version in ("7.1.0", "7.8.1", "8.0.0", "8.0.0.p1", "8.1.0.dev"):
            with self.subTest(occ=version):
                with mock.patch.object(Part, "OCC_VERSION", version), mock.patch.object(
                    svgshapes.TechDraw, "projectToSVG", wraps=TechDraw.projectToSVG
                ) as project:
                    svg = Draft.get_svg(obj, direction=App.Vector(0, 0, 1))
                project.assert_called()
                # Counter-clockwise quarter arc: large-arc flag 0, sweep flag 1.
                self.assertRegex(svg, r"A ?10 10 0 0 1 ")
        for version in ("6.9.1", "7.0.0"):
            with self.subTest(occ=version):
                with mock.patch.object(Part, "OCC_VERSION", version), mock.patch.object(
                    svgshapes.TechDraw, "projectToSVG"
                ) as project:
                    Draft.get_svg(obj, direction=App.Vector(0, 0, 1))
                project.assert_not_called()

    def test_get_svg_linecap(self):
        """The linecap argument replaces the default square line caps.

        Issue #27866: TechDraw Draft views must follow the TechDraw line cap
        preference.
        """
        line = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 5, 0)])
        obj = self._add_shape("Line", line)
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        group.addObject(obj)
        for source in (obj, group):
            with self.subTest(source=source.Name):
                default = Draft.get_svg(source, direction=App.Vector(0, 0, 1))
                self.assertIn("stroke-linecap:square", default)
                self.assertEqual(
                    Draft.get_svg(source, direction=App.Vector(0, 0, 1), linecap="square"),
                    default,
                )
                for cap in ("round", "butt"):
                    svg = Draft.get_svg(source, direction=App.Vector(0, 0, 1), linecap=cap)
                    self.assertNotIn("square", svg)
                    self.assertIn("stroke-linecap:" + cap, svg)
                    self.assertEqual(
                        svg.replace("stroke-linecap:" + cap, "stroke-linecap:square"), default
                    )
                self.assertEqual(
                    Draft.get_svg(source, direction=App.Vector(0, 0, 1), linecap="bogus"),
                    default,
                )

    @unittest.skipIf(not App.GuiUp, "Fill patterns are only exported in GUI mode")
    def test_get_svg_linecap_keeps_fill_pattern(self):
        """The linecap argument does not change the line caps of a fill pattern."""
        # a user pattern drawn with square caps
        pattern = (
            '<pattern id="SquareCaps" patternUnits="userSpaceOnUse" x="0" y="0" width="1" '
            'height="1"><path d="M0,0 L1,1" style="stroke:#000000;stroke-linecap:square" />'
            "</pattern>"
        )
        points = [App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 5, 0)]
        obj = self._add_shape("Face", Part.Face(Part.makePolygon(points + points[:1])))
        with mock.patch("draftfunctions.svg.get_pattern", return_value=pattern):
            svg = Draft.get_svg(
                obj, direction=App.Vector(0, 0, 1), fillstyle="SquareCaps", linecap="butt"
            )
        self.assertIn(pattern, svg)
        self.assertIn("stroke-linecap:butt", svg)


class DraftSVGColorRegression(test_base.DraftTestCaseDoc):
    """Regression tests for SVG colors given as presentation attributes."""

    def test_read_svg_rgba_fill_attribute(self):
        """A fill="rgba(...)" attribute must be read like the same value in a style."""
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">'
            '<rect x="0" y="0" width="10" height="10" fill="rgba(255, 0, 0, 0.5)"/>'
            "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "rgba_fill.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            shapes = importSVG.readShapes(in_file)
        self.assertEqual(len(shapes), 1)
        self.assertAlmostEqual(shapes[0].Area, 100.0, places=6)


class DraftSVGExportLabelRegression(test_base.DraftTestCaseDoc):
    """Regression tests for the files written by importSVG.export."""

    def test_export_svg_declares_freecad_namespace(self):
        """freecad:* attributes written by get_svg need a declared namespace prefix."""
        import xml.etree.ElementTree as ET

        obj = self.doc.addObject("Part::Feature", "Face")
        obj.Shape = Part.makePlane(10, 10)
        self.doc.recompute()
        # Dimensions, texts and arrows carry freecad:* attributes; they need the GUI,
        # so stand in for them.
        fake_svg = '<path freecad:skip="1" d="M 0 0 L 10 0" stroke="#000000"/>\n'
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "namespace.svg")
            with mock.patch.object(importSVG, "get_svg", return_value=fake_svg):
                importSVG.export([obj], out_file)
            with open(out_file, "rb") as svg_file:
                ET.fromstring(svg_file.read())  # namespace-aware parse
            # the importer parses its input with ElementTree as well
            self.assertIn("freecad:skip", importSVG.replace_use_with_reference(out_file))

    def test_export_svg_title_is_label(self):
        """The title of an exported object is its label, escaped, in a well-formed UTF-8 file."""
        import xml.dom.minidom

        obj = self.doc.addObject("Part::Feature", "Face")
        obj.Shape = Part.makePlane(10, 10)
        label = "R&D " + chr(0xE9) + " <1>"  # e acute
        obj.Label = label
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "label.svg")
            importSVG.export([obj], out_file)
            with open(out_file, "rb") as svg_file:
                data = svg_file.read()
        dom = xml.dom.minidom.parseString(data)
        titles = dom.getElementsByTagName("title")
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles[0].firstChild.data, label)

    @unittest.skipIf(App.GuiUp, "Without the GUI, texts have no bounding box")
    def test_export_svg_with_text_without_gui(self):
        """A text in the export list does not stop the export of the other objects."""
        import re

        obj = self.doc.addObject("Part::Feature", "Face")
        obj.Shape = Part.makePlane(10, 10)
        Draft.make_text(["Text"], App.Vector(100, 100, 0))
        self.doc.recompute()
        with tempfile.TemporaryDirectory() as temp_dir:
            out_file = os.path.join(temp_dir, "face.svg")
            importSVG.export([obj], out_file)
            with open(out_file, "rb") as svg_file:
                face_only = svg_file.read()
            out_file = os.path.join(temp_dir, "face_and_text.svg")
            importSVG.export(self.doc.Objects, out_file)
            with open(out_file, "rb") as svg_file:
                with_text = svg_file.read()
        # the text adds an empty group and does not change the page size
        text_group = re.compile(rb'<g id="Text" [^>]*>\r?\n<title>Text</title>\r?\n</g>\r?\n')
        self.assertEqual(len(text_group.findall(with_text)), 1)
        self.assertEqual(text_group.sub(b"", with_text), face_only)


class DraftSVGImportContentRegression(test_base.DraftTestCaseDoc):
    """Regression tests for how the SVG importer reads the content of a file."""

    def test_read_svg_declared_encoding(self):
        """A file is decoded as its byte order mark or encoding declaration says."""
        body = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">\n'
            "<desc>Café</desc>\n"
            '<rect x="0" y="0" width="10" height="10"/>\n'
            "</svg>\n"
        )
        # Python writes a byte order mark for UTF-16
        for encoding in ("ISO-8859-1", "windows-1252", "UTF-16", "UTF-8"):
            with self.subTest(encoding=encoding):
                svg = '<?xml version="1.0" encoding="{}"?>\n'.format(encoding) + body
                with tempfile.TemporaryDirectory() as temp_dir:
                    in_file = os.path.join(temp_dir, "encoding.svg")
                    with open(in_file, "wb") as svg_file:
                        svg_file.write(svg.encode(encoding))
                    result = importSVG.replace_use_with_reference(in_file)
                    shapes = importSVG.readShapes(in_file)
                self.assertIn("<desc>Café</desc>", result)
                self.assertEqual(len(shapes), 1)
                self.assertAlmostEqual(shapes[0].Area, 100.0, places=6)

    def test_read_svg_text_with_entities(self):
        """A text with entities is one text object, a tspan still makes its own."""
        svg = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100">'
            '<text x="10" y="20" font-size="5">A &amp; B &lt;C&gt;</text>'
            '<text x="10" y="40" font-size="5">'
            '<tspan x="10" y="40">T1</tspan><tspan x="10" y="50">T2 &amp; 3</tspan>'
            "</text>"
            "</svg>\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            in_file = os.path.join(temp_dir, "text_entities.svg")
            with open(in_file, "w", encoding="utf-8") as svg_file:
                svg_file.write(svg)
            importSVG.insert(in_file, self.doc.Name)
        texts = [
            (obj.LabelText, round(obj.Position.y, 6))
            for obj in self.doc.Objects
            if obj.TypeId == "App::Annotation"
        ]
        self.assertEqual(texts, [(["A & B <C>"], -20.0), (["T1"], -40.0), (["T2 & 3"], -50.0)])


## @}
