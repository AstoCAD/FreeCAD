# SPDX-License-Identifier: LGPL-2.1-or-later
"""Undo of the OpenSCAD commands that change the document."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import OpenSCADCommands  # noqa: F401  registers the OpenSCAD commands


class TestCommandUndo(unittest.TestCase):
    """Each command must be one undo step that reverts all of its changes."""

    def setUp(self):
        # Built without transactions, like a document opened from a CSG file.
        self.doc = App.newDocument("OpenSCADCommandUndo")
        self.doc.UndoMode = 1
        cube = self.doc.addObject("Part::Box", "Cube")
        cylinder = self.doc.addObject("Part::Cylinder", "Cylinder")
        fusion = self.doc.addObject("Part::MultiFuse", "Fusion")
        fusion.Shapes = [cube, cylinder]
        fusion.Placement.Base = App.Vector(0, 0, 10)
        self.doc.recompute()
        self.before = self._state()

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def _state(self):
        state = {obj.Name: obj.Placement.Base.z for obj in self.doc.Objects}
        fusion = self.doc.getObject("Fusion")
        if fusion:
            state["Fusion.Shapes"] = [obj.Name for obj in fusion.Shapes]
        return state

    def _run_undo_redo(self, command):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.getObject("Fusion"))
        Gui.runCommand(command)
        after = self._state()
        self.assertNotEqual(after, self.before)
        self.assertEqual(len(self.doc.UndoNames), 1)

        self.doc.undo()
        self.assertEqual(self._state(), self.before)

        self.doc.redo()
        self.assertEqual(self._state(), after)
        return after

    def test_explode_group(self):
        after = self._run_undo_redo("OpenSCAD_ExplodeGroup")
        self.assertNotIn("Fusion", after)
        self.assertEqual(after["Cube"], 10)

    def test_expand_placements(self):
        after = self._run_undo_redo("OpenSCAD_ExpandPlacements")
        self.assertEqual(after["Fusion"], 0)
        self.assertEqual(after["Cube"], 10)

    def test_remove_subtree(self):
        after = self._run_undo_redo("OpenSCAD_RemoveSubtree")
        self.assertEqual(after, {})

    def test_refine_shape_feature(self):
        after = self._run_undo_redo("OpenSCAD_RefineShapeFeature")
        self.assertIn("refine", after)

    def test_increase_tolerance_feature(self):
        after = self._run_undo_redo("OpenSCAD_IncreaseToleranceFeature")
        self.assertIn("tolerance", after)
