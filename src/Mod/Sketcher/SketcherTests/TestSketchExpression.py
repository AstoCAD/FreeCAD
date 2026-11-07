# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2021 Werner Mayer <werner.wm.mayer@gmx.de>              *
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
# ***************************************************************************/


import math, os, sys, unittest
import FreeCAD
import Part
import Sketcher

App = FreeCAD


class TestSketchExpression(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("TestSketchExpr")

    # See https://forum.freecad.org/viewtopic.php?f=3&t=64699
    # and https://forum.freecad.org/viewtopic.php?f=10&t=64718
    def testConstraintWithExpression(self):
        sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")

        geoList = []
        geoList.append(Part.LineSegment(App.Vector(0, 5, 0), App.Vector(5, 5, 0)))
        geoList.append(Part.LineSegment(App.Vector(5, 5, 0), App.Vector(5, 0, 0)))
        geoList.append(Part.LineSegment(App.Vector(5, 0, 0), App.Vector(0, 0, 0)))
        geoList.append(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 5, 0)))
        sketch.addGeometry(geoList, False)

        conList = []
        conList.append(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        conList.append(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
        conList.append(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
        conList.append(Sketcher.Constraint("Coincident", 3, 2, 0, 1))
        conList.append(Sketcher.Constraint("Horizontal", 0))
        conList.append(Sketcher.Constraint("Horizontal", 2))
        conList.append(Sketcher.Constraint("Vertical", 1))
        conList.append(Sketcher.Constraint("Vertical", 3))
        sketch.addConstraint(conList)
        del geoList, conList

        # Check that circular references get detected
        length = sketch.addConstraint(Sketcher.Constraint("Distance", 0, 6.0))
        height = sketch.addConstraint(Sketcher.Constraint("Distance", 3, 5.0))
        sketch.renameConstraint(length, "Length")
        sketch.renameConstraint(height, "Height")

        sketch.setExpression("Constraints[{}]".format(height), ".Constraints.Length")

        with self.assertRaises(RuntimeError) as context:
            sketch.setExpression("Constraints.Length", ".Constraints.Length * 2")
        assert ".Constraints.Length reference creates a cyclic dependency." in str(
            context.exception
        )

        with self.assertRaises(RuntimeError) as context:
            sketch.setExpression("Constraints.Length", ".Constraints.Height * 2")
        assert ".Constraints.Length reference creates a cyclic dependency." in str(
            context.exception
        )

    def testConstraintNamesThatAreNotIdentifiersSurviveSaveRestore(self):
        # https://github.com/FreeCAD/FreeCAD/issues/6593
        # https://github.com/FreeCAD/FreeCAD/issues/19866
        sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 4, 0)))
        base = sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10.0))
        height = sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 4.0))
        sketch.renameConstraint(base, "Base")
        sketch.renameConstraint(height, "Height")
        sketch.setExpression("Constraints.Height", ".Constraints.Base / 2")
        # names with a space or a unit name are not identifiers
        sketch.renameConstraint(base, "Bottom, width")
        sketch.renameConstraint(height, "mm")
        self.Doc.recompute()
        self.assertAlmostEqual(sketch.getDatum("mm").Value, 5.0)

        path = os.path.join(FreeCAD.getUserCachePath(), "TestSketchExprNames.FCStd")
        self.Doc.saveAs(path)
        FreeCAD.closeDocument(self.Doc.Name)
        self.Doc = FreeCAD.openDocument(path)
        sketch = self.Doc.getObject("Sketch")

        self.assertEqual(len(sketch.ExpressionEngine), 1)
        sketch.setDatum("Bottom, width", App.Units.Quantity("20 mm"))
        self.Doc.recompute()
        self.assertAlmostEqual(sketch.getDatum("mm").Value, 10.0)

    def _makeSketchWithRenumberedConstraints(self):
        # constraint 1 is named, constraints 2 and 3 are not
        sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        for k in range(4):
            sketch.addGeometry(
                Part.LineSegment(App.Vector(10 * k, 0, 0), App.Vector(10 * k + 5, 3 + k, 0))
            )
        sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        named = sketch.addConstraint(Sketcher.Constraint("Distance", 1, 7.0))
        sketch.renameConstraint(named, "a")
        sketch.addConstraint(Sketcher.Constraint("Distance", 2, 6.0))
        sketch.addConstraint(Sketcher.Constraint("Distance", 3, 5.0))
        sketch.setExpression("Constraints.a", ".Constraints[2] + 1 mm")
        box = self.Doc.addObject("Part::Box", "Box")
        box.setExpression("Width", "Sketch.Constraints[2] * 2")
        box.setExpression("Length", "Sketch.Constraints[3] * 2")
        self.Doc.recompute()
        self.assertAlmostEqual(sketch.getDatum("a").Value, 7.0)
        return sketch, box

    def _checkExpressionsFollowTheirConstraints(self, sketch, box):
        # The constraints that were 2 and 3 are now 1 and 2. Their new index 1 was the
        # index of the named constraint before: the expressions must not end up on it.
        self.assertEqual(sketch.Constraints[1].Name, "")
        self.assertAlmostEqual(sketch.Constraints[1].Value, 6.0)
        sketch.setDatum(1, App.Units.Quantity("8 mm"))
        sketch.setDatum(2, App.Units.Quantity("4 mm"))
        self.Doc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self.assertNotIn("Invalid", box.State)
        self.assertAlmostEqual(sketch.getDatum("a").Value, 9.0)
        self.assertAlmostEqual(box.Width.Value, 16.0)
        self.assertAlmostEqual(box.Length.Value, 8.0)

    def testDeletingAConstraintKeepsExpressionsOnTheirConstraints(self):
        sketch, box = self._makeSketchWithRenumberedConstraints()
        sketch.delConstraint(0)
        self._checkExpressionsFollowTheirConstraints(sketch, box)

    def testDeletingAGeometryKeepsExpressionsOnTheirConstraints(self):
        sketch, box = self._makeSketchWithRenumberedConstraints()
        sketch.delGeometries([0])
        self._checkExpressionsFollowTheirConstraints(sketch, box)

    def testDeletingAConstraintMovesBindingsSpelledWithADot(self):
        sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        for k in range(3):
            sketch.addGeometry(
                Part.LineSegment(App.Vector(10 * k, 0, 0), App.Vector(10 * k + 5, 3 + k, 0))
            )
            sketch.addConstraint(Sketcher.Constraint("Distance", k, 5.0 + k))
        sketch.setExpression(".Constraints[0]", "4 mm")
        sketch.setExpression(".Constraints[2]", "9 mm")
        self.Doc.recompute()
        sketch.delConstraint(0)
        # the binding of the deleted constraint is gone, the other one follows its constraint
        self.assertEqual(len(sketch.ExpressionEngine), 1)
        self.Doc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self.assertAlmostEqual(sketch.Constraints[0].Value, 6.0)
        self.assertAlmostEqual(sketch.Constraints[1].Value, 9.0)

    def testClearingAConstraintNameKeepsExpressionsOnIt(self):
        sketch, box = self._makeSketchWithRenumberedConstraints()
        box.setExpression("Height", "Sketch.Constraints.a * 3")
        self.Doc.recompute()
        sketch.renameConstraint(1, "")
        sketch.setDatum(2, App.Units.Quantity("2 mm"))
        self.Doc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self.assertNotIn("Invalid", box.State)
        self.assertAlmostEqual(sketch.Constraints[1].Value, 3.0)
        self.assertAlmostEqual(box.Height.Value, 9.0)

    def tearDown(self):
        # comment out to omit closing document for debugging
        FreeCAD.closeDocument(self.Doc.Name)
