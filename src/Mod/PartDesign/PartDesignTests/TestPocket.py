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

import math
import re
import unittest

import FreeCAD
import Part
import TestSketcherApp


class TestPocket(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestPocket")

    def testPocketDimensionCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Pad.Reversed = 1
        self.Doc.recompute()
        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pocket.Shape.Volume, 75.0)

    def testPocketPreservesTaperDirection(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (-10, -10), (20, 20))

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 10
        self.Doc.recompute()

        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        self.PocketSketch.Placement = FreeCAD.Placement(
            FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)
        )
        self.PocketSketch.MakeInternals = False
        radius = 2.0
        self.PocketSketch.addGeometry(
            Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), radius), False
        )

        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 5
        self.Pocket.TaperAngle = 20
        self.assertFalse(self.Pocket.UseLegacyTaperDirection)
        self.Doc.recompute()

        oneSidedVolume = self.Pocket.Shape.Volume
        expectedRadius = radius + self.Pocket.Length.Value * math.tan(math.radians(20))
        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, expectedRadius)

        self.Pocket.StartType = "Offset"
        self.Pocket.StartOffset = 1
        self.Doc.recompute()

        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, expectedRadius)

        self.Pocket.StartType = "Profile plane"
        self.Pocket.SideType = "Two sides"
        self.Pocket.Length2 = 5
        self.Doc.recompute()

        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, expectedRadius)
        self.assertAlmostEqual(self.Pocket.Shape.Volume, oneSidedVolume)

        self.Pocket.StartType = "Offset"
        self.Doc.recompute()

        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, expectedRadius)

        self.Pocket.UseLegacyTaperDirection = True
        self.Pocket.SideType = "One side"
        self.Doc.recompute()

        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, radius)

        self.Pocket.StartType = "Profile plane"
        self.Pocket.SideType = "Two sides"
        self.Doc.recompute()

        self.assertAlmostEqual(self.Pocket.AddSubShape.BoundBox.XMax, radius)

    def testStartOffset(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Pad.Reversed = 1
        self.Doc.recompute()

        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.StartType = "Offset"
        self.Pocket.StartOffset = 0.5
        self.Pocket.Length = 0.25
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pocket.Shape.Volume, 93.75)

    def testPocketThroughAllCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Pad.Reversed = 1
        self.Doc.recompute()
        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 1
        self.Doc.recompute()
        self.PocketSketch1 = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch1)
        self.PocketSketch1.MapMode = "FlatFace"
        self.PocketSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch1, (2.5, -0.75), (5, 0.50))
        self.Doc.recompute()
        self.Pocket001 = self.Doc.addObject("PartDesign::Pocket", "Pocket001")
        self.Body.addObject(self.Pocket001)
        self.Pocket001.Profile = self.PocketSketch1
        self.Pocket001.Type = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pocket001.Shape.Volume, 62.5)

    def testPocketToFirstCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Pad.Reversed = 1
        self.Doc.recompute()
        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 1
        self.Doc.recompute()
        self.PocketSketch1 = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch1)
        self.PocketSketch1.MapMode = "FlatFace"
        self.PocketSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch1, (2.5, -1), (5, 1))
        self.Doc.recompute()
        self.Pocket001 = self.Doc.addObject("PartDesign::Pocket", "Pocket001")
        self.Body.addObject(self.Pocket001)
        self.Pocket001.Profile = self.PocketSketch1
        self.Pocket001.Type = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pocket001.Shape.Volume, 62.5)

    def testPocketToFaceCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Pad.Reversed = 1
        self.Doc.recompute()
        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 1
        self.Doc.recompute()
        self.PocketSketch1 = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch1)
        self.PocketSketch1.MapMode = "FlatFace"
        self.PocketSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch1, (0, -1), (10, 1))
        self.Doc.recompute()
        self.Pocket001 = self.Doc.addObject("PartDesign::Pocket", "Pocket001")
        self.Body.addObject(self.Pocket001)
        self.Pocket001.Profile = self.PocketSketch1
        self.Pocket001.Type = 3
        # Handle face-naming inconsistency in OCC < 7
        self.FaceNumber = 7
        self.Pocket001.UpToFace = (self.Pocket, ["Face" + str(self.FaceNumber)])
        self.Doc.recompute()
        while (
            "Invalid" in self.Pocket001.State or round(self.Pocket001.Shape.Volume, 7) != 50.0
        ) and self.FaceNumber < 11:
            self.FaceNumber += 1
            self.Pocket001.UpToFace = (self.Pocket, ["Face" + str(self.FaceNumber)])
            self.Doc.recompute()
        self.assertAlmostEqual(self.Pocket001.Shape.Volume, 50.0)

    def testRecomputeDoesNotGrowProfileShape(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33926
        # The tapered Pad, the Pocket and the Groove must not attach new pcurves
        # and surfaces to the edges of their sketch on every recompute.
        def representations(shape):
            brep = shape.exportBrepToString()
            return [int(re.search(key + r" (\d+)", brep).group(1))
                    for key in ("Curve2ds", "Surfaces", "Locations")]

        body = self.Doc.addObject("PartDesign::Body", "Body")
        padSketch = body.newObject("Sketcher::SketchObject", "PadSketch")
        TestSketcherApp.CreateRectangleSketch(padSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = padSketch
        pad.Length = 5
        pad.Reversed = 1
        pad.TaperAngle = 5
        self.Doc.recompute()
        pocketSketch = body.newObject("Sketcher::SketchObject", "PocketSketch")
        TestSketcherApp.CreateRectangleSketch(pocketSketch, (2.5, 2.5), (5, 5))
        self.Doc.recompute()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = pocketSketch
        pocket.Length = 1
        self.Doc.recompute()
        grooveSketch = body.newObject("Sketcher::SketchObject", "GrooveSketch")
        grooveSketch.Placement = FreeCAD.Placement(
            FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
        )
        TestSketcherApp.CreateRectangleSketch(grooveSketch, (5, -4), (3, 3))
        self.Doc.recompute()
        groove = body.newObject("PartDesign::Groove", "Groove")
        groove.Profile = grooveSketch
        groove.ReferenceAxis = (grooveSketch, ["V_Axis"])
        groove.Angle = 90
        self.Doc.recompute()
        self.assertTrue(groove.Shape.isValid())

        padBefore = representations(padSketch.Shape)
        pocketBefore = representations(pocketSketch.Shape)
        grooveBefore = representations(grooveSketch.Shape)
        for i in range(5):
            pad.Length = 5 + (i % 2)
            pocket.Length = 1 + (i % 2)
            groove.Angle = 90 + 30 * (i % 2)
            self.Doc.recompute()
        self.assertTrue(groove.Shape.isValid())
        self.assertEqual(representations(padSketch.Shape), padBefore)
        self.assertEqual(representations(pocketSketch.Shape), pocketBefore)
        self.assertEqual(representations(grooveSketch.Shape), grooveBefore)
    def testPocketWithoutBaseIsNotAdditive(self):
        # https://github.com/FreeCAD/FreeCAD/issues/28712
        # A pocket that has no base shape (e.g. after the feature in front of it
        # was deleted) must fail instead of producing its tool as a solid.
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PocketSketch = self.Doc.addObject("Sketcher::SketchObject", "PocketSketch")
        self.Body.addObject(self.PocketSketch)
        TestSketcherApp.CreateRectangleSketch(self.PocketSketch, (0, 0), (10, 10))
        self.Doc.recompute()
        self.Pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        self.Body.addObject(self.Pocket)
        self.Pocket.Profile = self.PocketSketch
        self.Pocket.Length = 5
        self.Doc.recompute()
        self.assertIn("Invalid", self.Pocket.State)
        self.assertTrue(self.Pocket.Shape.isNull() or self.Pocket.Shape.Volume < 1e-7)
        self.assertTrue(self.Body.Shape.isNull() or self.Body.Shape.Volume < 1e-7)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestPocket")
        # print ("omit closing document for debugging")
