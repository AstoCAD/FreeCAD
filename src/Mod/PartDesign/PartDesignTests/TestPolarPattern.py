# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
import TestSketcherApp


class TestPolarPattern(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestPolarPattern")

    def testXAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Box]
        self.PolarPattern.Axis = (self.Doc.X_Axis, [""])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    def testYAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Box]
        self.PolarPattern.Axis = (self.Doc.Y_Axis, [""])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    def testZAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Box]
        self.PolarPattern.Axis = (self.Doc.Z_Axis, [""])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    def testNormalSketchAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 10
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Pad]
        self.PolarPattern.Axis = (self.PadSketch, ["N_Axis"])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    def testVerticalSketchAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 10
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Pad]
        self.PolarPattern.Axis = (self.PadSketch, ["V_Axis"])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    def testHorizontalSketchAxisPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 10
        self.Doc.recompute()
        self.PolarPattern = self.Doc.addObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Pad]
        self.PolarPattern.Axis = (self.PadSketch, ["H_Axis"])
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 4
        self.PolarPattern.Refine = True
        self.Body.addObject(self.PolarPattern)
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)
        # 26 original plus 3 new instances:
        # First and second have 4 new vertexes, 8 new edges and 5 new faces
        # Final one has  2 new vertexes, 5 new edges and original loses one face.
        # That makes 40.
        # self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 66)  # TODO
        self.assertEqual(self.PolarPattern.Shape.ElementMapSize, 26)

    # https://github.com/FreeCAD/FreeCAD/issues/10442
    def testSymmetricPolarPattern(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Body.newObject("PartDesign::AdditiveBox", "Box")
        self.Box.Length = self.Box.Width = self.Box.Height = 10
        self.Doc.recompute()
        self.PolarPattern = self.Body.newObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Box]
        self.PolarPattern.Axis = (self.Doc.Z_Axis, [""])
        self.PolarPattern.Angle = 90
        self.PolarPattern.Occurrences = 2
        self.PolarPattern.Symmetric = True
        self.Doc.recompute()
        shape = self.PolarPattern.Shape
        self.assertAlmostEqual(shape.Volume, 3000)
        self.assertTrue(shape.isInside(FreeCAD.Vector(-5, 5, 5), 1e-7, True))
        self.assertTrue(shape.isInside(FreeCAD.Vector(5, -5, 5), 1e-7, True))
        self.assertFalse(shape.isInside(FreeCAD.Vector(-5, -5, 5), 1e-7, True))

        # The angle applies to each side, a full turn included.
        self.PolarPattern.Angle = 360
        self.PolarPattern.Occurrences = 5
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 4000)

        self.PolarPattern.Mode = "Spacing"
        self.PolarPattern.Offset = 90
        self.PolarPattern.Occurrences = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.PolarPattern.Shape.Volume, 3000)
        self.assertFalse(self.PolarPattern.Shape.isInside(FreeCAD.Vector(-5, -5, 5), 1e-7, True))

    def testNaNAnglePolarPatternFails(self):
        # A NaN angle passed every range check and the NaN transformations crashed
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Body.newObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Pad = self.Body.newObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 5
        self.Doc.recompute()
        self.PolarPattern = self.Body.newObject("PartDesign::PolarPattern", "PolarPattern")
        self.PolarPattern.Originals = [self.Pad]
        self.PolarPattern.Axis = (self.Doc.Z_Axis, [""])
        self.PolarPattern.Occurrences = 3
        self.Doc.recompute()
        self.assertIn("Up-to-date", self.PolarPattern.State)
        self.PolarPattern.Angle = float("nan")
        self.Doc.recompute()
        self.assertIn("Invalid", self.PolarPattern.State)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestPolarPattern")
        # print ("omit closing document for debugging")
