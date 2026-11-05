# SPDX-License-Identifier: LGPL-2.1-or-later

"""Constraint editing calls on a sketch whose constraint list is invalid.

Assigning the Constraints property directly with an index past the geometry marks the list
invalid: SketchObject then sees no constraints until it is fixed. Calls that take a constraint
index must reject the index (as setDriving, toggleActive and the others do), not crash.
"""

import unittest

import FreeCAD as App
import Part
import Sketcher

V = App.Vector


class TestSketchInvalidConstraintList(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchInvalidConstraintList")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        self.sketch.addGeometry(Part.LineSegment(V(10, 0, 0), V(10, 10, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10))
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 1, 10))
        self.doc.recompute()

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _invalidate(self):
        # unmanaged change with a constraint on a geometry that does not exist
        self.sketch.Constraints = list(self.sketch.Constraints) + [
            Sketcher.Constraint("Distance", 99, 5)
        ]

    def testValidListStillWorks(self):
        self.sketch.toggleDriving(0)
        self.assertFalse(self.sketch.getDriving(0))
        self.sketch.renameConstraint(1, "Width")
        self.assertEqual(self.sketch.Constraints[1].Name, "Width")

    def testToggleDrivingRejectsIndex(self):
        self._invalidate()
        with self.assertRaises(ValueError):
            self.sketch.toggleDriving(0)

    def testRenameConstraintRejectsIndex(self):
        self._invalidate()
        with self.assertRaises(IndexError):
            self.sketch.renameConstraint(0, "Width")


if __name__ == "__main__":
    unittest.main()
