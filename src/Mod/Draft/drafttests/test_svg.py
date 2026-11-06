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


## @}
