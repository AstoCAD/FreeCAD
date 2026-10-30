# SPDX-License-Identifier: LGPL-2.1-or-later
"""Round-trip tests for the CSG exporter."""

from pathlib import Path
import tempfile
import unittest

import FreeCAD as App
import exportCSG
import importCSG


class TestExportCSGBooleanPlacement(unittest.TestCase):
    """Issue #33826: the Placement of a boolean feature must be exported."""

    def setUp(self):
        self.before = set(App.listDocuments())
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-csg-export-")
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        self.temp.cleanup()

    def _roundtrip(self, type_id, placement):
        doc = App.newDocument("ExportCSGBooleanPlacement")
        base = doc.addObject("Part::Box", "Base")
        base.Length = 20
        base.Width = 10
        base.Height = 5
        tool = doc.addObject("Part::Box", "Tool")
        tool.Length = 5
        tool.Width = 5
        tool.Height = 10
        tool.Placement.Base = App.Vector(2, 2, -1)
        op = doc.addObject(type_id, "Op")
        if type_id.startswith("Part::Multi"):
            op.Shapes = [base, tool]
        else:
            op.Base = base
            op.Tool = tool
        doc.recompute()
        op.Placement = placement
        doc.recompute()

        path = Path(self.temp.name) / "Boolean.csg"
        exportCSG.export([op], str(path))
        imported = importCSG.open(str(path))
        roots = [obj for obj in imported.RootObjects if hasattr(obj, "Shape")]
        self.assertEqual(len(roots), 1)
        expected = op.Shape.BoundBox
        actual = roots[0].Shape.BoundBox
        self.assertAlmostEqual(roots[0].Shape.Volume, op.Shape.Volume, places=6)
        for name in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"):
            self.assertAlmostEqual(getattr(actual, name), getattr(expected, name),
                                   places=6, msg=type_id + " " + name)

    def _check_all(self, placement):
        for type_id in ("Part::Cut", "Part::Fuse", "Part::Common",
                        "Part::MultiFuse", "Part::MultiCommon"):
            with self.subTest(type_id=type_id):
                self._roundtrip(type_id, placement)

    def test_rotated_and_moved_boolean(self):
        self._check_all(App.Placement(App.Vector(1, 2, 3),
                                      App.Rotation(App.Vector(0, 0, 1), 90)))

    def test_identity_placement_control(self):
        self._check_all(App.Placement())
