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
from FreeCAD import Base
import TestSketcherApp
from TestPropertyFloatNaN import restoreValueAsFromFile


class TestPad(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestPad")

    def testBoxCase(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchOnBasePlane(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.PadSketch.AttachmentSupport = (self.Doc.XY_Plane, [""])
        self.PadSketch.MapMode = "FlatFace"
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Body.addObject(self.Pad)
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchOnDatumPlane(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.DatumPlane = self.Doc.addObject("PartDesign::Plane", "DatumPlane")
        self.DatumPlane.AttachmentSupport = (self.Doc.XY_Plane, [""])
        self.DatumPlane.MapMode = "FlatFace"
        self.Body.addObject(self.DatumPlane)
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.PadSketch.AttachmentSupport = (self.DatumPlane, [""])
        self.PadSketch.MapMode = "FlatFace"
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Body.addObject(self.Pad)
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchAttachmentDoesNotImportExternalBody(self):
        source_body = self.Doc.addObject("PartDesign::Body", "SourceBody")
        source_box = source_body.newObject("PartDesign::AdditiveBox", "SourceBox")
        source_box.Length = 1
        source_box.Width = 1
        source_box.Height = 1

        target_body = self.Doc.addObject("PartDesign::Body", "TargetBody")
        sketch = target_body.newObject("Sketcher::SketchObject", "SketchPad")
        sketch.AttachmentSupport = (source_body, [""])
        sketch.MapMode = "ObjectXY"
        TestSketcherApp.CreateRectangleSketch(sketch, (2, 0), (1, 1))

        pad = target_body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 1
        self.Doc.recompute()

        self.assertIsNone(pad.BaseFeature)
        self.assertEqual(len(pad.Shape.Solids), 1)
        self.assertAlmostEqual(pad.Shape.Volume, 1)

    def testSketchOnFaceOfOtherBodyDoesNotImportIt(self):
        # https://github.com/FreeCAD/FreeCAD/issues/15971
        # The first Pad of a Body whose sketch is attached to a face of another
        # Body must not contain that other Body's feature.
        source_body = self.Doc.addObject("PartDesign::Body", "SourceBody")
        source_box = source_body.newObject("PartDesign::AdditiveBox", "SourceBox")
        source_box.Length = 10
        source_box.Width = 10
        source_box.Height = 2
        self.Doc.recompute()
        top = [
            "Face{}".format(i + 1)
            for i, face in enumerate(source_box.Shape.Faces)
            if abs(face.CenterOfMass.z - 2) < 1e-7
        ][0]

        target_body = self.Doc.addObject("PartDesign::Body", "TargetBody")
        target_body.Placement.Base = FreeCAD.Vector(0, 0, 20)
        sketch = target_body.newObject("Sketcher::SketchObject", "SketchPad")
        sketch.AttachmentSupport = (source_box, [top])
        sketch.MapMode = "FlatFace"
        TestSketcherApp.CreateRectangleSketch(sketch, (1, 1), (2, 3))

        pad = target_body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 4
        self.Doc.recompute()

        self.assertIsNone(pad.BaseFeature)
        self.assertEqual(len(pad.Shape.Solids), 1)
        self.assertAlmostEqual(pad.Shape.Volume, 2 * 3 * 4)
        self.assertAlmostEqual(target_body.Shape.Volume, 2 * 3 * 4)

    def testStartOffsetAndReference(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.StartType = "Offset"
        self.Pad.StartOffset = 2
        self.Pad.Length = 3
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 2.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 5.0)

        reference = self.Doc.addObject("Part::Feature", "Reference")
        outer = Part.makeCylinder(2, 1, Base.Vector(0, 0, 10))
        inner = Part.makeCylinder(1, 1, Base.Vector(0, 0, 10))
        reference.Shape = outer.cut(inner)
        top_face = max(
            range(1, len(reference.Shape.Faces) + 1),
            key=lambda index: reference.Shape.Faces[index - 1].CenterOfMass.z,
        )
        self.Pad.StartReference = (reference, [f"Face{top_face}"])
        self.Pad.StartType = "Reference"
        self.Pad.StartOffset = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 13.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 16.0)

    def testStartReferenceInternalSketchFace(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        reference = self.Doc.addObject("Sketcher::SketchObject", "Reference")
        reference.MakeInternals = True
        reference.Placement.Base = Base.Vector(0, 0, 10)
        TestSketcherApp.CreateRectangleSketch(reference, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 3
        self.Pad.StartReference = (reference, ["InternalFace1"])
        self.Pad.StartType = "Reference"
        self.Pad.StartOffset = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 12.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 15.0)

    def testStartOffsetForTwoSidedAndSymmetricPad(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.StartType = "Offset"
        self.Pad.StartOffset = 2
        self.Pad.SideType = "Two sides"
        self.Pad.Length = 1
        self.Pad.Length2 = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 1.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 3.0)

        self.Pad.SideType = "Symmetric"
        self.Pad.Length = 4
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 0.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 4.0)

    def testPadToFirstCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 2
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.0)

    def testPadtoLastCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0.5, 1), (0.5, 2))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 1
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 3.0)

    def testPadToFaceCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to face on first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 3
        self.Pad1.UpToFace = (self.Pad, ["Face3"])
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.0)

    def testPadTwoDimensionsCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to face on first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.SideType = 1
        self.Pad1.Length = 1.0
        self.Pad1.Length2 = 2.0
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 4.0)

    def testPadToConcaveCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make a half revolution
        self.RevolutionSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.RevolutionSketch)
        TestSketcherApp.CreateRectangleSketch(self.RevolutionSketch, (9, 0), (10, 5))
        self.Doc.recompute()
        self.Revolution = self.Doc.addObject("PartDesign::Revolution", "Revolution")
        self.Body.addObject(self.Revolution)
        self.Revolution.Profile = self.RevolutionSketch
        self.Revolution.ReferenceAxis = (self.RevolutionSketch, ["V_Axis"])
        self.Revolution.Angle = 180
        self.Doc.recompute()
        # Make a sketch and pad to first
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Type = 2
        self.Pad.Reversed = True
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.Volume, 2208.0963, places=4)

    def testPadToShapeCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.PadSketch1.AttachmentOffset.Rotation.Axis = Base.Vector(0, 1, 0)
        self.PadSketch1.AttachmentOffset.Rotation.Angle = 0.436332  # 25°
        self.PadSketch1.AttachmentOffset.Base.z = 1
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (1, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 5
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.58787, places=4)

    def testPadToPlaneCustomDir(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Type = 3
        self.Doc.Pad.UseCustomVector = True
        self.Doc.Pad.Direction = Base.Vector(0, 1, 1)
        self.Pad.UpToFace = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.Volume, 1.5)

    @staticmethod
    def _frustumVolume(r1, r2, h):
        return math.pi * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)

    def testPadTaperedSmallCircle(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33427
        # An inward taper on a small circle used to crash in OCC's 2D offset algorithm
        body = self.Doc.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 1), False)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 10
        for angle in (-1, -5, 3):
            pad.TaperAngle = angle
            self.Doc.recompute()
            self.assertTrue(pad.isValid(), f"Pad failed for taper angle {angle}")
            self.assertTrue(pad.Shape.isValid())
            r2 = 1 + 10 * math.tan(math.radians(angle))
            self.assertAlmostEqual(
                pad.Shape.Volume, self._frustumVolume(1, r2, 10), places=4
            )

        # a taper making the circle collapse must fail cleanly
        pad.TaperAngle = -10
        self.Doc.recompute()
        self.assertFalse(pad.isValid())

    def testPadTaperedRing(self):
        # Inner circles must keep being offset in the same direction as the outer one
        body = self.Doc.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 10), False)
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 5), False)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 10
        for angle in (5, -5):
            pad.TaperAngle = angle
            self.Doc.recompute()
            self.assertTrue(pad.isValid())
            self.assertTrue(pad.Shape.isValid())
            d = 10 * math.tan(math.radians(angle))
            expected = self._frustumVolume(10, 10 + d, 10) - self._frustumVolume(5, 5 + d, 10)
            self.assertAlmostEqual(pad.Shape.Volume, expected, places=4)

    def testPadUpToPoint(self):
        # https://github.com/FreeCAD/FreeCAD/issues/5724
        # A vertex or a datum point as "up to face" ends the pad on the plane through it
        body = self.Doc.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 3), False)
        vertex = self.Doc.addObject("Part::Vertex", "Vertex")
        vertex.X = 20
        vertex.Z = 7
        datumPoint = body.newObject("PartDesign::Point", "DatumPoint")
        datumPoint.MapMode = "Deactivated"
        datumPoint.Placement.Base = FreeCAD.Vector(-5, 4, 9)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Type = "UpToFace"
        for ref, height in (((vertex, ["Vertex1"]), 7), ((datumPoint, [""]), 9)):
            pad.UpToFace = ref
            self.Doc.recompute()
            self.assertTrue(pad.isValid(), pad.getStatusString())
            self.assertAlmostEqual(pad.Shape.BoundBox.ZMin, 0)
            self.assertAlmostEqual(pad.Shape.BoundBox.ZMax, height)
            self.assertAlmostEqual(pad.Shape.Volume, math.pi * 9 * height)

        # the plane through the point keeps working with an offset
        pad.Offset = 1
        self.Doc.recompute()
        self.assertAlmostEqual(pad.Shape.BoundBox.ZMax, 10)

    def testPocketUpToPoint(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = 20
        box.Height = 10
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = [(box, "Face6")]
        sketch.MapMode = "FlatFace"
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(10, 10, 0), FreeCAD.Vector(0, 0, 1), 3), False)
        self.Doc.recompute()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = sketch
        pocket.Type = "UpToFace"
        bottom = next(
            i for i, v in enumerate(box.Shape.Vertexes, 1) if abs(v.Point.z) < 1e-7
        )
        pocket.UpToFace = (box, [f"Vertex{bottom}"])  # a bottom corner of the box
        self.Doc.recompute()
        self.assertTrue(pocket.isValid(), pocket.getStatusString())
        self.assertAlmostEqual(pocket.Shape.Volume, 20 * 20 * 10 - math.pi * 9 * 10)

    def testRefineKeepsValidShapeAtCylinderSeam(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32645
        # A tab tangent to the inner face of a tube at its seam: refining the
        # fused result breaks it, so the unrefined valid shape must be kept
        body = self.Doc.addObject("PartDesign::Body", "Body")
        tubeSketch = body.newObject("Sketcher::SketchObject", "TubeSketch")
        tubeSketch.AttachmentSupport = (self.Doc.getObject("XY_Plane"), [""])
        tubeSketch.MapMode = "FlatFace"
        tubeSketch.addGeometry(
            [
                Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 5),
                Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 7),
            ],
            False,
        )
        self.Doc.recompute()
        tube = body.newObject("PartDesign::Pad", "Tube")
        tube.Profile = tubeSketch
        tube.Length = 10
        tube.Refine = False
        tabSketch = body.newObject("Sketcher::SketchObject", "TabSketch")
        tabSketch.AttachmentSupport = (self.Doc.getObject("XY_Plane"), [""])
        tabSketch.MapMode = "FlatFace"
        TestSketcherApp.CreateRectangleSketch(tabSketch, (5, -2), (10, 4))
        self.Doc.recompute()
        tab = body.newObject("PartDesign::Pad", "Tab")
        tab.Profile = tabSketch
        tab.Length = 5
        tab.Refine = False
        self.Doc.recompute()
        self.assertTrue(tab.isValid(), tab.getStatusString())
        self.assertTrue(tab.Shape.isValid())
        unrefinedVolume = tab.Shape.Volume
        tab.Refine = True
        self.Doc.recompute()
        self.assertTrue(tab.isValid(), tab.getStatusString())
        self.assertTrue(tab.Shape.isValid())
        self.assertAlmostEqual(tab.Shape.Volume, unrefinedVolume)

    def testRefineValidityCheckOnlyNeedsChangedFaces(self):
        # The validity check after refine only analyses the faces refine rebuilt:
        # every face refine does not touch must stay the very same face
        box1 = Part.makeBox(10, 10, 10)
        box2 = Part.makeBox(10, 10, 10, FreeCAD.Vector(10, 0, 0))
        fused = box1.fuse(box2).Solids[0]
        refined = fused.removeSplitter()
        self.assertEqual(len(fused.Faces), 10)
        self.assertEqual(len(refined.Faces), 6)
        untouched = [f for f in refined.Faces if any(f.isSame(g) for g in fused.Faces)]
        self.assertEqual(len(untouched), 2)  # the two end faces
        # nothing to merge: all faces are kept
        fused = box1.fuse(Part.makeBox(5, 5, 5, FreeCAD.Vector(2, 2, 10))).Solids[0]
        refined = fused.removeSplitter()
        self.assertEqual(len(refined.Faces), len(fused.Faces))
        self.assertTrue(all(any(f.isSame(g) for g in fused.Faces) for f in refined.Faces))

        # and a refined feature still gets its faces merged into a valid solid
        body = self.Doc.addObject("PartDesign::Body", "Body")
        sketch1 = body.newObject("Sketcher::SketchObject", "Sketch1")
        sketch1.AttachmentSupport = (self.Doc.getObject("XY_Plane"), [""])
        sketch1.MapMode = "FlatFace"
        TestSketcherApp.CreateRectangleSketch(sketch1, (0, 0), (10, 10))
        pad1 = body.newObject("PartDesign::Pad", "Pad1")
        pad1.Profile = sketch1
        pad1.Length = 10
        sketch2 = body.newObject("Sketcher::SketchObject", "Sketch2")
        sketch2.AttachmentSupport = (self.Doc.getObject("XY_Plane"), [""])
        sketch2.MapMode = "FlatFace"
        TestSketcherApp.CreateRectangleSketch(sketch2, (10, 0), (10, 10))
        pad2 = body.newObject("PartDesign::Pad", "Pad2")
        pad2.Profile = sketch2
        pad2.Length = 10
        pad2.Refine = True
        self.Doc.recompute()
        self.assertTrue(pad2.isValid(), pad2.getStatusString())
        self.assertTrue(pad2.Shape.isValid())
        self.assertEqual(len(pad2.Shape.Faces), 6)
        self.assertAlmostEqual(pad2.Shape.Volume, 2000)

    def _makeLengthFeature(self, typeName):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        if typeName == "PartDesign::Pocket":
            box = body.newObject("PartDesign::AdditiveBox", "Box")
            box.Length = box.Width = box.Height = 20
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = (self.Doc.XY_Plane, [""])
        sketch.MapMode = "FlatFace"
        TestSketcherApp.CreateRectangleSketch(sketch, (0, 0), (10, 10))
        feature = body.newObject(typeName, "Feature")
        feature.Profile = sketch
        self.Doc.recompute()
        self.assertIn("Up-to-date", feature.State)
        return feature

    def testPadNaNLengthFails(self):
        # NaN passed the zero length check and crashed while making the prism
        pad = self._makeLengthFeature("PartDesign::Pad")
        # assigning NaN raises: it can only come from a file
        restoreValueAsFromFile(pad, "Length", float("nan"))
        self.Doc.recompute()
        self.assertIn("Invalid", pad.State)

    def testPadInfiniteLengthFails(self):
        pad = self._makeLengthFeature("PartDesign::Pad")
        pad.Length = float("inf")
        self.Doc.recompute()
        self.assertIn("Invalid", pad.State)

    def testPadNaNSecondLengthFails(self):
        pad = self._makeLengthFeature("PartDesign::Pad")
        pad.SideType = "Two sides"
        restoreValueAsFromFile(pad, "Length2", float("nan"))
        self.Doc.recompute()
        self.assertIn("Invalid", pad.State)

    def testPocketNaNLengthFails(self):
        pocket = self._makeLengthFeature("PartDesign::Pocket")
        restoreValueAsFromFile(pocket, "Length", float("nan"))
        self.Doc.recompute()
        self.assertIn("Invalid", pocket.State)

    def testPadNaNCustomDirectionFails(self):
        # NaN passed the null vector check of the custom direction and crashed the prism
        pad = self._makeLengthFeature("PartDesign::Pad")
        pad.UseCustomVector = True
        restoreValueAsFromFile(pad, "Direction", Base.Vector(float("nan"), 0, 1))
        self.Doc.recompute()
        self.assertIn("Invalid", pad.State)

    def testPocketNaNCustomDirectionFails(self):
        pocket = self._makeLengthFeature("PartDesign::Pocket")
        pocket.UseCustomVector = True
        restoreValueAsFromFile(pocket, "Direction", Base.Vector(float("nan"), 0, 1))
        self.Doc.recompute()
        self.assertIn("Invalid", pocket.State)

    def testConstructionOnlySketchMessage(self):
        # A sketch holding only construction geometry has no shape; the error must say why
        body = self.Doc.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "ConstructionSketch")
        sketch.addGeometry(Part.Circle(Base.Vector(0, 0, 0), Base.Vector(0, 0, 1), 5), True)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 5
        self.Doc.recompute()
        self.assertIn("Invalid", pad.State)
        self.assertIn("construction geometry", pad.getStatusString())

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestPad")
        # print ("omit closing document for debugging")
