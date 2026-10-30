# SPDX-License-Identifier: LGPL-2.1-or-later
"""Set Tip on the Body's Origin maps to Tip = None (issue #25185).

Tip = None keeps its upstream meaning: new features are appended at the end of the body.
"""

import os
import unittest

import FreeCAD as App
import Part
import Sketcher


def addSquareSketch(body, name, x0):
    sketch = body.newObject("Sketcher::SketchObject", name)
    xy_plane = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
    sketch.AttachmentSupport = (xy_plane, [""])
    sketch.MapMode = "FlatFace"
    points = [
        App.Vector(x0, 0, 0),
        App.Vector(x0 + 10, 0, 0),
        App.Vector(x0 + 10, 10, 0),
        App.Vector(x0, 10, 0),
    ]
    for i in range(4):
        sketch.addGeometry(Part.LineSegment(points[i], points[(i + 1) % 4]), False)
    for i in range(4):
        sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    return sketch


class TestSetTipOrigin(unittest.TestCase):
    def setUp(self):
        self.Doc = App.newDocument("PartDesignTestSetTipOrigin")
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Body.newObject("PartDesign::AdditiveBox", "Box")
        self.Doc.recompute()
        self.paths = []

    def tearDown(self):
        App.closeDocument(self.Doc.Name)
        for path in self.paths:
            if os.path.exists(path):
                os.remove(path)

    def testTipNoneAppendsNextFeature(self):
        self.assertEqual(self.Body.Tip, self.Box)
        # This is what PartDesign_MoveTip emits for the Origin (and for the Body)
        self.Body.Tip = None
        self.Doc.recompute()
        self.assertIsNone(self.Body.Tip)

        cylinder = self.Body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.Doc.recompute()
        self.assertEqual(self.Body.Group, [self.Box, cylinder])
        self.assertEqual(self.Body.Tip, cylinder)
        self.assertIsNone(self.Box.BaseFeature)
        self.assertEqual(cylinder.BaseFeature, self.Box)

    def testTipNoneAppendsSketch(self):
        self.Body.Tip = None
        sketch = self.Body.newObject("Sketcher::SketchObject", "Sketch")
        self.assertEqual(self.Body.Group, [self.Box, sketch])
        self.assertIsNone(self.Body.Tip)

    def testTipDeletedByScriptAppendsPad(self):
        # Deleting the Tip from Python (not through Body.removeObject) leaves Tip = None
        top = self.Body.newObject("PartDesign::AdditiveCylinder", "Top")
        self.Doc.recompute()
        self.assertEqual(self.Body.Tip, top)
        self.Doc.removeObject(top.Name)
        self.Doc.recompute()
        self.assertIsNone(self.Body.Tip)

        sketch = addSquareSketch(self.Body, "Sketch", 20)
        pad = self.Body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 10
        self.Doc.recompute()
        self.assertEqual(self.Body.Group, [self.Box, sketch, pad])
        self.assertEqual(self.Body.Tip, pad)
        self.assertIsNone(self.Box.BaseFeature)
        self.assertEqual(pad.BaseFeature, self.Box)
        self.assertTrue(pad.isValid())
        # Box 10x10x10 plus a separate 10x10x10 pad
        self.assertAlmostEqual(self.Body.Shape.Volume, 2000, places=6)

    def testTipNoneKeepsInternalBaseFeatureFirst(self):
        doc = self.Doc
        part_box = doc.addObject("Part::Box", "PartBox")
        body = doc.addObject("PartDesign::Body", "BodyWithBase")
        body.BaseFeature = part_box
        doc.recompute()
        base = body.Group[0]
        self.assertEqual(base.TypeId, "PartDesign::FeatureBase")
        first = body.newObject("PartDesign::AdditiveBox", "First")
        doc.recompute()
        body.Tip = None
        second = body.newObject("PartDesign::AdditiveCylinder", "Second")
        doc.recompute()
        self.assertEqual(body.Group, [base, first, second])
        self.assertEqual(base.BaseFeature, part_box)
        self.assertEqual(first.BaseFeature, base)
        self.assertEqual(second.BaseFeature, first)

    def testTipNoneSurvivesSaveAndRestore(self):
        self.Body.Tip = None
        self.Doc.recompute()
        path = App.getTempPath() + "PartDesignTestSetTipOrigin.FCStd"
        self.paths.append(path)
        self.Doc.saveAs(path)
        App.closeDocument(self.Doc.Name)
        self.Doc = App.openDocument(path)
        body = self.Doc.getObject("Body")
        self.assertIsNone(body.Tip)
        self.assertEqual([o.Name for o in body.Group], ["Box"])

    def testFileWithTipNoneAppendsNextFeature(self):
        # Files written with Tip = None and features (as upstream FreeCAD writes them)
        self.Body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.Doc.recompute()
        self.Body.Tip = None
        self.Doc.recompute()
        path = App.getTempPath() + "PartDesignTestSetTipOriginFile.FCStd"
        self.paths.append(path)
        self.Doc.saveAs(path)
        App.closeDocument(self.Doc.Name)
        self.Doc = App.openDocument(path)
        body = self.Doc.getObject("Body")
        box = self.Doc.getObject("Box")
        cylinder = self.Doc.getObject("Cylinder")
        self.assertIsNone(body.Tip)
        cone = body.newObject("PartDesign::AdditiveCone", "Cone")
        self.Doc.recompute()
        self.assertEqual(body.Group, [box, cylinder, cone])
        self.assertEqual(body.Tip, cone)
        self.assertIsNone(box.BaseFeature)
        self.assertEqual(cylinder.BaseFeature, box)
        self.assertEqual(cone.BaseFeature, cylinder)

    def testTipOnFeatureInsertsAfterIt(self):
        cylinder = self.Body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.Doc.recompute()
        self.Body.Tip = self.Box
        cone = self.Body.newObject("PartDesign::AdditiveCone", "Cone")
        self.Doc.recompute()
        self.assertEqual(self.Body.Group, [self.Box, cone, cylinder])
        self.assertEqual(self.Body.Tip, cone)
        self.assertEqual(cone.BaseFeature, self.Box)
        self.assertEqual(cylinder.BaseFeature, cone)
