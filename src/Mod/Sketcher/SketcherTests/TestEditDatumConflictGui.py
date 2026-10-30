# SPDX-License-Identifier: LGPL-2.1-or-later
"""Refusing to edit a datum of a conflicting sketch must not leave a transaction open (#17864)."""

import FreeCAD as App
import Part
import Sketcher

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestEditDatumConflictGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("EditDatumConflictTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10.0))
        self.sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20.0))
        self.doc.recompute()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)

    def testConflictingSketchClosesTransaction(self):
        self.sketch.solve()
        self.assertTrue(self.sketch.ConflictingConstraints)
        self.assertIsNone(App.getActiveTransaction())

        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Constraint1")
        Gui.runCommand("Sketcher_ChangeDimensionConstraint")
        self.flush_gui(100)

        # The dialog was refused: no transaction may stay open, otherwise the
        # following changes cannot be undone separately.
        self.assertIsNone(App.getActiveTransaction())
        self.assertEqual(self.sketch.Constraints[0].Value, 10.0)

        Gui.ActiveDocument.resetEdit()
        self.flush_gui(100)
