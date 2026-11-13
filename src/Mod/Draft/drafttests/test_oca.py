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

"""Unit tests for the Draft Workbench, OCA import and export tests."""

## @package test_oca
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, OCA import and export tests.

## \addtogroup drafttests
# @{

import os
import shutil
import tempfile

import FreeCAD as App
import Part
import Draft
from drafttests import auxiliary as aux
from drafttests import test_base
from draftutils.messages import _msg


class DraftOCA(test_base.DraftTestCaseDoc):
    """Test reading and writing of OCA files with Draft."""

    def test_read_oca(self):
        """Read an OCA file and import its elements as Draft objects."""
        operation = "importOCA.import"
        _msg("  Test '{}'".format(operation))
        _msg("  This test requires an OCA file to read.")

        file = "Mod/Draft/drafttest/test.oca"
        in_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(in_file))
        _msg("  exists={}".format(os.path.exists(in_file)))

        obj = aux.fake_function(in_file)
        self.assertTrue(obj, "'{}' failed".format(operation))

    def test_export_oca(self):
        """Create some figures and export them to an OCA file."""
        operation = "importOCA.export"
        _msg("  Test '{}'".format(operation))

        file = "Mod/Draft/drafttest/out_test.oca"
        out_file = os.path.join(App.getResourceDir(), file)
        _msg("  file={}".format(out_file))
        _msg("  exists={}".format(os.path.exists(out_file)))

        obj = aux.fake_function(out_file)
        self.assertTrue(obj, "'{}' failed".format(operation))


class DraftOCARoundTrip(test_base.DraftTestCaseDoc):
    """Test that the OCA importer reads what the OCA exporter writes."""

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        # areas are only imported with this preference
        grp = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
        if "ocaareas" in grp.GetBools():
            self.addCleanup(grp.SetBool, "ocaareas", grp.GetBool("ocaareas"))
        else:
            self.addCleanup(grp.RemBool, "ocaareas")
        grp.SetBool("ocaareas", True)

    def _add(self, name, shape):
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = shape
        return obj

    def _assert_points(self, shape, points):
        found = sorted(tuple(round(c, 9) for c in v.Point) for v in shape.Vertexes)
        self.assertEqual(found, sorted(points))

    def test_export_import_round_trip(self):
        """Lines, arcs, circles and faces survive an export and an import."""
        import importOCA

        Vector = App.Vector
        objs = [
            self._add("Line", Part.makeLine(Vector(0, 0, 0), Vector(10, 0, 0))),
            self._add("Arc", Part.makeCircle(5, Vector(20, 0, 0), Vector(0, 0, 1), 0, 90)),
            self._add("Circle", Part.makeCircle(5, Vector(40, 0, 0))),
            self._add("Square", Part.makePlane(10, 10, Vector(50, 0, 0))),
        ]
        self.doc.recompute()
        path = os.path.join(self.tmpdir, "round_trip.oca")
        importOCA.export(objs, path)

        dest = App.newDocument("OCARoundTrip")
        self.addCleanup(App.closeDocument, dest.Name)
        importOCA.insert(path, dest.Name)
        self.assertEqual(sorted(o.Name for o in dest.Objects), ["A4", "C2", "C3", "L1"])

        line = dest.getObject("L1").Shape
        self._assert_points(line, [(0, 0, 0), (10, 0, 0)])

        arc = dest.getObject("C2").Shape
        self.assertEqual(len(arc.Edges), 1)
        self.assertIsInstance(arc.Edges[0].Curve, Part.Circle)
        self.assertAlmostEqual(arc.Edges[0].Curve.Radius, 5, places=6)
        self.assertTrue(arc.Edges[0].Curve.Center.isEqual(Vector(20, 0, 0), 1e-6))
        self._assert_points(arc, [(20, 5, 0), (25, 0, 0)])

        circle = dest.getObject("C3").Shape
        self.assertEqual(len(circle.Edges), 1)
        self.assertTrue(circle.Edges[0].isClosed())
        self.assertAlmostEqual(circle.Edges[0].Curve.Radius, 5, places=6)
        self.assertTrue(circle.Edges[0].Curve.Center.isEqual(Vector(40, 0, 0), 1e-6))

        # areas are imported as closed polygons; a wrong vertex order
        # gives a self-intersecting polygon without the square's area
        area = dest.getObject("A4").Shape
        self.assertEqual(area.ShapeType, "Wire")
        self.assertTrue(area.isClosed())
        self.assertEqual(len(area.Edges), 4)
        self._assert_points(area, [(50, 0, 0), (50, 10, 0), (60, 0, 0), (60, 10, 0)])
        self.assertAlmostEqual(Part.Face(area).Area, 100, places=6)


## @}
