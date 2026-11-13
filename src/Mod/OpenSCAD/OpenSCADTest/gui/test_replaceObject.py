# SPDX-License-Identifier: LGPL-2.1-or-later
"""Undo of the OpenSCAD_ReplaceObject command."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import OpenSCADCommands  # noqa: F401  registers OpenSCAD_ReplaceObject


class TestReplaceObjectUndo(unittest.TestCase):
    """Issue #18813: undo must revert the replacement, not the previous step."""

    def setUp(self):
        self.doc = App.newDocument("ReplaceObjectUndo")
        self.doc.UndoMode = 1
        self.doc.openTransaction("Create primitives")
        self.cube = self.doc.addObject("Part::Box", "Cube")
        self.cylinder = self.doc.addObject("Part::Cylinder", "Cylinder")
        self.cone = self.doc.addObject("Part::Cone", "Cone")
        self.doc.commitTransaction()
        self.doc.openTransaction("Create fusion")
        self.fusion = self.doc.addObject("Part::MultiFuse", "Fusion")
        self.fusion.Shapes = [self.cube, self.cylinder]
        self.doc.recompute()
        self.doc.commitTransaction()

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def _shape_names(self):
        fusion = self.doc.getObject("Fusion")
        self.assertIsNotNone(fusion, "the fusion was removed")
        return [obj.Name for obj in fusion.Shapes]

    def test_undo_and_redo_replace_object(self):
        Gui.Selection.clearSelection()
        for obj in (self.cube, self.cone, self.fusion):
            Gui.Selection.addSelection(obj)
        Gui.runCommand("OpenSCAD_ReplaceObject")
        self.assertEqual(self._shape_names(), ["Cone", "Cylinder"])

        self.doc.undo()
        self.assertEqual(self._shape_names(), ["Cube", "Cylinder"])

        self.doc.redo()
        self.assertEqual(self._shape_names(), ["Cone", "Cylinder"])
