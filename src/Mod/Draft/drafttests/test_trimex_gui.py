# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2026 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This file is free software; you can redistribute it and/or modify it  *
# *   under the terms of the GNU Lesser General Public License (LGPL)       *
# *   as published by the Free Software Foundation; either version 2.1 of  *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft Trimex GUI command."""

import math
from unittest import mock

import FreeCAD as App
import Part
import Draft

from draftguitools import gui_trimex
from drafttests.test_base import DraftTestCaseDoc


class DraftTrimexGui(DraftTestCaseDoc):
    """Tests for Trimex coordinate handling."""

    def test_global_shape_in_translated_part(self):
        """Trimex geometry should include the placement of an App Part."""
        part = self.doc.addObject("App::Part", "Part")
        part.Placement.Base = App.Vector(400, 400, 0)
        line = Draft.make_line(App.Vector(100, 100, 0), App.Vector(500, 100, 0))
        part.addObject(line)
        line.Placement.Base = App.Vector(-400, -400, 0)
        self.doc.recompute()

        self.assertEqual(
            [vertex.Point for vertex in line.Shape.Vertexes],
            [App.Vector(-300, -300, 0), App.Vector(100, -300, 0)],
        )
        # The selection path starts at the root object (the App Part).
        shape = gui_trimex._get_global_shape(part, f"{line.Name}.")
        self.assertEqual(
            [vertex.Point for vertex in shape.Vertexes],
            [App.Vector(100, 100, 0), App.Vector(500, 100, 0)],
        )

    def test_global_shape_preserves_root_object_placement(self):
        """Root-level Trimex geometry should remain unchanged."""
        line = self.doc.addObject("Part::Feature", "Line")
        line.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
        line.Placement.Base = App.Vector(20, 30, 0)
        self.doc.recompute()

        shape = gui_trimex._get_global_shape(line)
        self.assertEqual(
            [vertex.Point for vertex in shape.Vertexes],
            [App.Vector(20, 30, 0), App.Vector(30, 30, 0)],
        )

    def test_resolve_selection_through_link(self):
        """Trimex should use the selected link instance coordinates."""
        part = self.doc.addObject("App::Part", "Part")
        line = Draft.make_line(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
        part.addObject(line)
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = part
        link.Placement.Base = App.Vector(20, 30, 0)
        self.doc.recompute()
        selection = mock.Mock(Object=link, SubElementNames=(f"{line.Name}.Edge1",))

        obj, placement, shape = gui_trimex._resolve_selection(selection)

        self.assertEqual(obj, line)
        self.assertEqual(placement.Base, App.Vector(20, 30, 0))
        self.assertEqual(
            [vertex.Point for vertex in shape.Vertexes],
            [App.Vector(20, 30, 0), App.Vector(30, 30, 0)],
        )

    def test_extend_object_through_link(self):
        """Trimex should write linked-instance geometry back locally."""
        part = self.doc.addObject("App::Part", "Part")
        horizontal = Draft.make_line(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
        vertical = Draft.make_line(App.Vector(20, -5, 0), App.Vector(20, 5, 0))
        part.addObject(horizontal)
        part.addObject(vertical)
        link = self.doc.addObject("App::Link", "Link")
        link.LinkedObject = part
        link.Placement.Base = App.Vector(100, 100, 0)
        self.doc.recompute()
        selection = mock.Mock(Object=link, SubElementNames=(f"{horizontal.Name}.Edge1",))

        obj, placement, shape = gui_trimex._resolve_selection(selection)
        command = gui_trimex.Trimex()
        command.obj = obj
        command.placement = placement
        command.edges = shape.Edges
        command.ghost = [mock.Mock()]
        command.activePoint = 0
        command.lockedActivePoint = None
        command.axisSetter = None
        command.force = None
        command.doc = self.doc
        command.extrudeMode = False
        command.point = App.Vector(120, 100, 0)
        command.snapped = {
            "ParentObject": link,
            "SubName": f"{vertical.Name}.Edge1",
        }
        command.shift = False
        command.alt = False

        command.trimObject()

        # The start and end points keep their identity (#19189).
        self.assertEqual(horizontal.Points, [App.Vector(0, 0, 0), App.Vector(20, 0, 0)])

    def test_extend_to_object_in_translated_part(self):
        """Trimex should extend between world-space shapes in an App Part."""
        part = self.doc.addObject("App::Part", "Part")
        part.Placement.Base = App.Vector(400, 400, 0)
        horizontal = Draft.make_line(App.Vector(100, 100, 0), App.Vector(500, 100, 0))
        vertical = Draft.make_line(App.Vector(700, 0, 0), App.Vector(700, 200, 0))
        part.addObject(horizontal)
        part.addObject(vertical)
        horizontal.Placement.Base = App.Vector(-400, -400, 0)
        vertical.Placement.Base = App.Vector(-400, -400, 0)
        self.doc.recompute()

        command = gui_trimex.Trimex()
        # Selection and snapping paths start at the root object (the App Part).
        snapped = {"ParentObject": part, "SubName": f"{vertical.Name}.Edge1"}
        command.edges = gui_trimex._get_global_shape(part, f"{horizontal.Name}.").Edges
        command.ghost = [mock.Mock()]
        command.activePoint = 0
        command.lockedActivePoint = None
        command.axisSetter = None
        command.force = None
        edges = command.redraw(App.Vector(700, 100, 0), snapped, real=True)

        points = [vertex.Point for vertex in Part.Wire(edges).Vertexes]
        self.assertEqual(points, [App.Vector(700, 100, 0), App.Vector(100, 100, 0)])

        command.obj = horizontal
        command.doc = self.doc
        command.placement = horizontal.getGlobalPlacement()
        command.extrudeMode = False
        command.point = App.Vector(700, 100, 0)
        command.snapped = snapped
        command.shift = False
        command.alt = False
        command.trimObject()
        self.assertEqual(
            horizontal.Points,
            [App.Vector(100, 100, 0), App.Vector(700, 100, 0)],
        )

    def _make_wire_command(self, wire, point):
        command = gui_trimex.Trimex()
        command.obj = wire
        command.placement = wire.getGlobalPlacement()
        command.edges = gui_trimex._get_global_shape(wire).Wires[0].Edges
        command.ghost = [mock.Mock() for _ in command.edges]
        command.activePoint = 0
        command.lockedActivePoint = None
        command.axisSetter = None
        command.force = None
        command.doc = self.doc
        command.extrudeMode = False
        command.point = point
        command.snapped = None
        command.shift = False
        command.alt = False
        return command

    def test_trim_wire_keeps_start_and_end(self):
        """Moving either end of a wire must not swap its start and end (#19189)."""
        points = [App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 10, 0)]
        wire = Draft.make_wire(points)
        self.doc.recompute()

        # Extend the end point.
        self._make_wire_command(wire, App.Vector(10, 15, 0)).trimObject()
        self.assertEqual(
            wire.Points,
            [App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 15, 0)],
        )

        # Shorten the start point.
        self._make_wire_command(wire, App.Vector(4, 0, 0)).trimObject()
        self.assertEqual(
            wire.Points,
            [App.Vector(4, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 15, 0)],
        )

    def test_value_typed_before_mouse_move(self):
        """Typing a value before the mouse has moved must not fail (#33411)."""
        points = [App.Vector(0, 0, 0), App.Vector(10, 0, 0)]
        wire = Draft.make_wire(points)
        self.doc.recompute()
        command = self._make_wire_command(wire, None)

        with mock.patch.object(command, "finish") as finish:
            command.numericRadius(5)

        finish.assert_not_called()
        self.assertEqual(wire.Points, points)

    def _trim_arc(self, rotation, point):
        """Extend or trim a Draft arc (0 to 90 degrees) with the given rotation."""
        import FreeCADGui as Gui
        from draftguitools import gui_trackers as trackers

        if not hasattr(Gui, "draftToolBar"):
            # The trackers need the working plane set up by the workbench.
            Gui.activateWorkbench("DraftWorkbench")
        placement = App.Placement(App.Vector(0, 0, 0), rotation)
        arc = Draft.make_circle(10, placement=placement, startangle=0, endangle=90)
        self.doc.recompute()
        command = gui_trimex.Trimex()
        command.obj = arc
        command.placement = arc.getGlobalPlacement()
        command.edges = gui_trimex._get_global_shape(arc).Edges
        command.ghost = [trackers.arcTracker()]
        command.activePoint = 0
        command.lockedActivePoint = None
        command.axisSetter = None
        command.force = None
        command.doc = self.doc
        command.extrudeMode = False
        command.point = point
        command.snapped = None
        command.shift = False
        command.alt = False
        try:
            command.trimObject()
        finally:
            command.ghost[0].finalize()
        return arc

    def _assert_arc_ends(self, arc, first, last):
        """Check the global end points of the arc."""
        edge = arc.Shape.Edges[0]
        self.assertTrue(edge.Vertexes[0].Point.isEqual(first, 1e-6), edge.Vertexes[0].Point)
        self.assertTrue(edge.Vertexes[-1].Point.isEqual(last, 1e-6), edge.Vertexes[-1].Point)

    def test_trim_rotated_arc(self):
        """Trimex must respect the placement rotation of arcs (#22913)."""
        # Arc from 30 to 120 degrees (global), extend the end to 150 degrees.
        rotation = App.Rotation(App.Vector(0, 0, 1), 30)
        target = App.Vector(10 * math.cos(math.radians(150)), 10 * math.sin(math.radians(150)), 0)
        arc = self._trim_arc(rotation, target)
        self.assertAlmostEqual(arc.FirstAngle.Value, 0, places=6)
        self.assertAlmostEqual(arc.LastAngle.Value, 120, places=6)
        self._assert_arc_ends(arc, rotation.multVec(App.Vector(10, 0, 0)), target)

    def test_trim_flipped_arc(self):
        """Trimex must handle arcs whose Z axis points down (#22913)."""
        # Arc from 0 to -90 degrees (global), extend the -90 end to -120 degrees.
        rotation = App.Rotation(App.Vector(1, 0, 0), 180)
        target = App.Vector(10 * math.cos(math.radians(-120)), 10 * math.sin(math.radians(-120)), 0)
        arc = self._trim_arc(rotation, target)
        self.assertAlmostEqual(arc.FirstAngle.Value, 0, places=6)
        self.assertAlmostEqual(arc.LastAngle.Value, 120, places=6)
        self._assert_arc_ends(arc, App.Vector(10, 0, 0), target)
