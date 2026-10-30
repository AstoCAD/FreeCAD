# SPDX-License-Identifier: LGPL-2.1-or-later
"""Set Tip on the Body's Origin maps to Tip = None (issue #25185)."""

import unittest

import FreeCAD as App


class TestSetTipOrigin(unittest.TestCase):
    def setUp(self):
        self.Doc = App.newDocument("PartDesignTestSetTipOrigin")
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Body.newObject("PartDesign::AdditiveBox", "Box")
        self.Doc.recompute()

    def tearDown(self):
        App.closeDocument(self.Doc.Name)

    def testTipNoneInsertsNextFeatureFirst(self):
        self.assertEqual(self.Body.Tip, self.Box)
        # This is what PartDesign_MoveTip emits for the Origin (and for the Body)
        self.Body.Tip = None
        self.Doc.recompute()
        self.assertIsNone(self.Body.Tip)

        cylinder = self.Body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.Doc.recompute()
        self.assertEqual(self.Body.Group, [cylinder, self.Box])
        self.assertEqual(self.Body.Tip, cylinder)
        self.assertIsNone(cylinder.BaseFeature)
        self.assertEqual(self.Box.BaseFeature, cylinder)

    def testTipNoneInsertsSketchBeforeFirstSolid(self):
        self.Body.Tip = None
        sketch = self.Body.newObject("Sketcher::SketchObject", "Sketch")
        self.assertEqual(self.Body.Group, [sketch, self.Box])
        self.assertIsNone(self.Body.Tip)

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
        self.assertEqual(body.Group, [base, second, first])
        self.assertEqual(base.BaseFeature, part_box)
        self.assertEqual(second.BaseFeature, base)
        self.assertEqual(first.BaseFeature, second)

    def testTipNoneSurvivesSaveAndRestore(self):
        self.Body.Tip = None
        self.Doc.recompute()
        path = App.getTempPath() + "PartDesignTestSetTipOrigin.FCStd"
        self.Doc.saveAs(path)
        App.closeDocument(self.Doc.Name)
        self.Doc = App.openDocument(path)
        body = self.Doc.getObject("Body")
        self.assertIsNone(body.Tip)
        self.assertEqual([o.Name for o in body.Group], ["Box"])
