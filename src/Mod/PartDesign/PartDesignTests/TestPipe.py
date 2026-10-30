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
import unittest

import FreeCAD
import Part
import Sketcher
import TestSketcherApp

App = FreeCAD


class TestPipe(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestPipe")

    def testSimpleAdditivePipeCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.ProfileSketch = self.Doc.addObject("Sketcher::SketchObject", "ProfileSketch")
        self.Body.addObject(self.ProfileSketch)
        TestSketcherApp.CreateCircleSketch(self.ProfileSketch, (0, 0), 1)
        self.Doc.recompute()
        self.SpineSketch = self.Doc.addObject("Sketcher::SketchObject", "SpineSketch")
        self.Body.addObject(self.SpineSketch)
        self.SpineSketch.MapMode = "FlatFace"
        self.SpineSketch.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        self.SpineSketch.addGeometry(
            Part.LineSegment(App.Vector(0.0, 0.0, 0), App.Vector(0, 1, 0)), False
        )
        self.SpineSketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        self.SpineSketch.addConstraint(Sketcher.Constraint("PointOnObject", 0, 2, -2))
        self.SpineSketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 0, 2, 1))
        self.Doc.recompute()
        self.AdditivePipe = self.Doc.addObject("PartDesign::AdditivePipe", "AdditivePipe")
        self.Body.addObject(self.AdditivePipe)
        self.AdditivePipe.Profile = self.ProfileSketch
        self.AdditivePipe.Spine = self.SpineSketch
        self.Doc.recompute()
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, 3.14159265)

    def testSimpleSubtractivePipeCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.ProfileSketch = self.Doc.addObject("Sketcher::SketchObject", "ProfileSketch")
        self.Body.addObject(self.ProfileSketch)
        TestSketcherApp.CreateCircleSketch(self.ProfileSketch, (0, 0), 1)
        self.Doc.recompute()
        self.SpineSketch = self.Doc.addObject("Sketcher::SketchObject", "SpineSketch")
        self.Body.addObject(self.SpineSketch)
        self.SpineSketch.MapMode = "FlatFace"
        self.SpineSketch.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        self.SpineSketch.addGeometry(
            Part.LineSegment(App.Vector(0.0, 0.0, 0), App.Vector(0, 1, 0)), False
        )
        self.SpineSketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        self.SpineSketch.addConstraint(Sketcher.Constraint("PointOnObject", 0, 2, -2))
        self.SpineSketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 0, 2, 1))
        self.Doc.recompute()
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "PadSketch")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (-5, -5), (10, 10))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1.0
        self.Doc.recompute()
        self.SubtractivePipe = self.Doc.addObject("PartDesign::SubtractivePipe", "SubtractivePipe")
        self.Body.addObject(self.SubtractivePipe)
        self.SubtractivePipe.Profile = self.ProfileSketch
        self.SubtractivePipe.Spine = self.SpineSketch
        self.Doc.recompute()
        self.assertAlmostEqual(self.SubtractivePipe.Shape.Volume, 100 - 3.14159265)

    def createSquarePipe(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.ProfileSketch = self.Body.newObject("Sketcher::SketchObject", "ProfileSketch")
        TestSketcherApp.CreateRectangleSketch(self.ProfileSketch, (-1, -1), (2, 2))
        self.SectionSketch = self.Body.newObject("Sketcher::SketchObject", "SectionSketch")
        TestSketcherApp.CreateRectangleSketch(self.SectionSketch, (-0.5, -0.5), (1, 1))
        self.SectionSketch.Placement = App.Placement(App.Vector(0, 0, 1), App.Rotation())
        self.SpineSketch = self.Body.newObject("Sketcher::SketchObject", "SpineSketch")
        self.SpineSketch.MapMode = "FlatFace"
        self.SpineSketch.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.SpineSketch.addGeometry(
            Part.LineSegment(App.Vector(0.0, 0.0, 0), App.Vector(0, 1, 0)), False
        )
        self.Doc.recompute()
        self.AdditivePipe = self.Body.newObject("PartDesign::AdditivePipe", "AdditivePipe")
        self.AdditivePipe.Spine = self.SpineSketch

    def testPipeSketchEdgeProfile(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33966
        # Picking an edge of a sketch in the 3D view selects the whole sketch
        self.createSquarePipe()
        self.AdditivePipe.Profile = (self.ProfileSketch, ["Edge1"])
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid(), self.AdditivePipe.getStatusString())
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, 4.0)

    def testMultisectionPipeSketchEdgeSection(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33966
        self.createSquarePipe()
        self.AdditivePipe.Profile = self.ProfileSketch
        self.AdditivePipe.Transformation = "Multisection"
        self.AdditivePipe.Sections = [(self.SectionSketch, [""])]
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid(), self.AdditivePipe.getStatusString())
        wholeVolume = self.AdditivePipe.Shape.Volume
        self.AdditivePipe.Sections = [(self.SectionSketch, ["Edge2"])]
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid(), self.AdditivePipe.getStatusString())
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, wholeVolume)

    def testMultisectionPipeSketchVertexSection(self):
        # A single vertex picked in a sketch is still used as a point section
        self.createSquarePipe()
        self.AdditivePipe.Profile = self.ProfileSketch
        self.AdditivePipe.Transformation = "Multisection"
        self.AdditivePipe.Sections = [(self.SectionSketch, ["Vertex1"])]
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid(), self.AdditivePipe.getStatusString())
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, 4.0 / 3.0)

    def testClosedPathPipeKeepsProfileIsland(self):
        # https://github.com/FreeCAD/FreeCAD/issues/24996
        # A profile with an island swept along a closed path must stay hollow
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.ProfileSketch = self.Body.newObject("Sketcher::SketchObject", "ProfileSketch")
        self.ProfileSketch.addGeometry(
            [
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 1.0),
                Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 0.5),
            ],
            False,
        )
        self.SpineSketch = self.Body.newObject("Sketcher::SketchObject", "SpineSketch")
        self.SpineSketch.MapMode = "FlatFace"
        self.SpineSketch.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.SpineSketch.addGeometry(
            Part.Circle(App.Vector(5, 0, 0), App.Vector(0, 0, 1), 5.0), False
        )
        self.Doc.recompute()
        self.AdditivePipe = self.Body.newObject("PartDesign::AdditivePipe", "AdditivePipe")
        self.AdditivePipe.Profile = self.ProfileSketch
        self.AdditivePipe.Spine = self.SpineSketch
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid())
        # torus with the tube cross-section of a ring: 2*pi*R * pi*(r1^2 - r2^2)
        expected = 2 * math.pi * 5 * math.pi * (1.0**2 - 0.5**2)
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, expected, places=3)
        self.assertEqual(len(self.AdditivePipe.Shape.Solids), 1)
        self.assertEqual(len(self.AdditivePipe.AddSubShape.Solids), 1)
        self.assertAlmostEqual(self.AdditivePipe.AddSubShape.Volume, expected, places=3)

        # The subtractive pipe must only remove the ring, not the island
        self.BoxSketch = self.Body.newObject("Sketcher::SketchObject", "BoxSketch")
        self.BoxSketch.MapMode = "FlatFace"
        self.BoxSketch.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        TestSketcherApp.CreateRectangleSketch(self.BoxSketch, (-2, -7), (14, 14))
        self.Doc.recompute()
        self.Pad = self.Body.newObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.BoxSketch
        self.Pad.Midplane = True
        self.Pad.Length = 4.0
        self.Doc.recompute()
        padVolume = self.Pad.Shape.Volume
        self.SubtractivePipe = self.Body.newObject("PartDesign::SubtractivePipe", "SubtractivePipe")
        self.SubtractivePipe.Profile = self.ProfileSketch
        self.SubtractivePipe.Spine = self.SpineSketch
        self.Doc.recompute()
        self.assertTrue(self.SubtractivePipe.isValid())
        self.assertAlmostEqual(self.SubtractivePipe.Shape.Volume, padVolume - expected, places=3)

    def testPipeReportsSpineError(self):
        # https://github.com/FreeCAD/FreeCAD/issues/28860
        # Errors must be reported, not hidden behind a generic message
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Body.newObject("PartDesign::AdditiveBox", "Box")
        self.ProfileSketch = self.Body.newObject("Sketcher::SketchObject", "ProfileSketch")
        TestSketcherApp.CreateCircleSketch(self.ProfileSketch, (0, 0), 1)
        self.Doc.recompute()
        self.AdditivePipe = self.Body.newObject("PartDesign::AdditivePipe", "AdditivePipe")
        self.AdditivePipe.Profile = self.ProfileSketch
        self.AdditivePipe.Spine = self.Box  # a solid is not a valid spine
        self.Doc.recompute()
        self.assertFalse(self.AdditivePipe.isValid())
        status = self.AdditivePipe.getStatusString()
        self.assertNotIn("fatal error", status)
        self.assertIn("Spine is neither an edge nor a wire", status)

    def testPipeSpineSketchWithIsolatedPoints(self):
        # https://github.com/FreeCAD/FreeCAD/issues/26853
        # Points of the spine sketch are not part of the path and must be ignored
        self.createSquarePipe()
        self.SpineSketch.addGeometry(Part.Point(App.Vector(0, 0.5, 0)), False)
        self.SpineSketch.addGeometry(Part.Point(App.Vector(3, 3, 0)), False)
        self.AdditivePipe.Profile = self.ProfileSketch
        self.Doc.recompute()
        self.assertTrue(self.AdditivePipe.isValid(), self.AdditivePipe.getStatusString())
        self.assertAlmostEqual(self.AdditivePipe.Shape.Volume, 4.0)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestPipe")
        # print ("omit closing document for debugging")
