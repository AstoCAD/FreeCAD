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

App = FreeCAD


class TestDraft(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestDraft")

    def testSimpleDraft(self):
        # fix: create datum plane on YZ. create datum line on Z + 10i
        # find top face by first making list comprehension of Z-normal faces
        # and then find which has the higher center of mass Z-value
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.DatumPlane = self.Doc.addObject("PartDesign::Plane", "DatumPlane")
        self.DatumPlane.AttachmentSupport = [(self.Doc.YZ_Plane, "")]
        self.DatumPlane.MapMode = "FlatFace"
        self.Body.addObject(self.DatumPlane)
        self.Doc.recompute()
        self.DatumLine = self.Doc.addObject("PartDesign::Line", "DatumLine")
        self.DatumLine.AttachmentSupport = [(self.Doc.X_Axis, "")]
        self.DatumLine.MapMode = "TwoPointLine"
        self.Body.addObject(self.DatumLine)
        self.Doc.recompute()
        self.Draft = self.Doc.addObject("PartDesign::Draft", "Draft")
        # Draft.Base needs to be top face
        self.Faces = self.Box.Shape.Faces
        # Grab the two faces with Z-normals and find the higher one
        self.ZFaceIndexes = [
            i for i in range(len(self.Faces)) if self.Faces[i].Surface.Axis == App.Vector(0, 0, 1)
        ]
        if (
            self.Faces[self.ZFaceIndexes[0]].CenterOfMass.z
            > self.Faces[self.ZFaceIndexes[1]].CenterOfMass.z
        ):
            self.TopFaceIndex = self.ZFaceIndexes[0]
        else:
            self.TopFaceIndex = self.ZFaceIndexes[1]
        self.Draft.Base = (self.Box, ["Face" + str(self.TopFaceIndex + 1)])
        self.Draft.NeutralPlane = (self.DatumPlane, [""])
        self.Draft.PullDirection = (self.DatumLine, [""])
        self.Draft.Angle = 45.0
        self.Draft.Reversed = 1
        self.Body.addObject(self.Draft)
        self.Doc.recompute()
        if "Invalid" in self.Draft.State:
            self.Draft.Reversed = 0
            self.Doc.recompute()
        self.assertAlmostEqual(self.Draft.Shape.Volume, 1500)

    def testFaceThatCannotBeDraftedIsSkipped(self):
        # The top face of the box is parallel to the neutral plane, so OCCT
        # cannot draft it.  It must be skipped and the other faces drafted,
        # whatever the Reversed setting (it used to fail when not reversed).
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = 20.0
        box.Width = 20.0
        box.Height = 10.0
        self.Doc.recompute()
        xyPlane = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]

        def draftVolume(faces, reversed):
            draft = body.newObject("PartDesign::Draft", "Draft")
            draft.Base = (box, faces)
            draft.NeutralPlane = (xyPlane, [""])
            draft.Angle = 5.0
            draft.Reversed = reversed
            self.Doc.recompute()
            valid = draft.isValid()
            volume = draft.Shape.Volume if valid else None
            body.removeObject(draft)
            self.Doc.removeObject(draft.Name)
            self.Doc.recompute()
            return valid, volume

        for reversed in (False, True):
            valid, expected = draftVolume(["Face1", "Face2"], reversed)
            self.assertTrue(valid)
            for faces in (["Face1", "Face2", "Face6"], ["Face6", "Face1", "Face2"]):
                valid, volume = draftVolume(faces, reversed)
                self.assertTrue(valid, "faces %s, Reversed %s" % (faces, reversed))
                self.assertAlmostEqual(volume, expected, places=6)

    def testTooLargeDraftAngleReportsError(self):
        # Drafting the sides of a 10 mm cube by 45 degrees about its bottom face would make
        # them cross: OCCT cannot build it, and the feature failed without any message
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        self.Doc.recompute()
        sides = [
            "Face%d" % (i + 1)
            for i, face in enumerate(box.Shape.Faces)
            if abs(face.normalAt(0, 0).z) < 1e-6
        ]
        bottom = [
            "Face%d" % (i + 1)
            for i, face in enumerate(box.Shape.Faces)
            if face.normalAt(0, 0).z < -0.5
        ]
        draft = body.newObject("PartDesign::Draft", "Draft")
        draft.Base = (box, sides)
        draft.NeutralPlane = (box, bottom)
        draft.Angle = 45
        self.Doc.recompute()
        self.assertIn("Invalid", draft.State)
        self.assertNotEqual(draft.getStatusString().strip(), "")
        # a feasible angle still drafts the faces
        draft.Angle = 10
        self.Doc.recompute()
        self.assertIn("Up-to-date", draft.State)
        self.assertLess(draft.Shape.Volume, 1000)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestDraft")
        # print ("omit closing document for debugging")
