# SPDX-License-Identifier: LGPL-2.1-or-later
"""App-only Body single/bulk removal contracts and transaction diagnostics."""

import unittest

import FreeCAD as App
import Part
import PartDesign


class TestBodyBulkRemoval(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BodyBulkRemoval14516")
        self.doc.UndoMode = 1

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def makeBody(self, name, count):
        body = self.doc.addObject("PartDesign::Body", name)
        features = []
        for index in range(count):
            # Ordinary valid feature solids isolate membership/Tip/BaseFeature
            # bookkeeping from additive kernel construction or UI selection order.
            feature = body.newObject("PartDesign::Feature", name + "Feature%d" % index)
            feature.Shape = Part.makeBox(2 + index, 3, 5)
            features.append(feature)
        self.doc.recompute()
        self.assertEqual(body.Group, features)
        self.assertEqual(body.Tip, features[-1] if features else None)
        self.assertEqual([feature.BaseFeature for feature in features],
                         [None] + features[:-1] if features else [])
        if features:
            self.assertFalse(body.Shape.isNull())
        return body, features

    def state(self, body):
        return {"group": [obj.Name for obj in body.Group],
                "tip": body.Tip.Name if body.Tip else None,
                "out": [obj.Name for obj in body.OutList],
                "base": {obj.Name: obj.BaseFeature.Name if obj.BaseFeature else None
                         for obj in body.Group if "BaseFeature" in obj.PropertiesList}}

    def assertConsistent(self, body, moved=()):
        with self.subTest(body=body.Name, invariant="Tip belongs to remaining Group"):
            self.assertTrue(body.Tip is None or body.Tip in body.Group,
                            "A Body Tip cannot retain a removed feature")
        for feature in moved:
            with self.subTest(body=body.Name, invariant="No stale OutList", feature=feature.Name):
                self.assertNotIn(feature, body.OutList,
                                 "The old Body must not retain a child-scope link to a moved feature")

    def moveOnlyFeature(self, bulk):
        source, features = self.makeBody("Source", 1)
        target, _ = self.makeBody("Target", 0)
        if bulk:
            removed = source.removeObjects(features)
        else:
            removed = source.removeObject(features[0])
        self.assertEqual(removed, features)
        self.assertEqual(source.Group, [])
        target.addObjects(features)
        self.doc.recompute()
        self.assertEqual(target.Group, features)
        self.assertEqual(target.Tip, features[0])
        self.assertIsNone(features[0].BaseFeature)
        self.assertEqual(features[0].getParentGeoFeatureGroup(), target)
        self.assertConsistent(target)
        self.assertConsistent(source, features)

    def testBulkMoveOnlyFeature(self):
        self.moveOnlyFeature(True)

    def testSingleMoveOnlyFeatureControl(self):
        self.moveOnlyFeature(False)

    def moveChain(self, bulk, reverse_request=False):
        source, features = self.makeBody("Source", 3)
        target, _ = self.makeBody("Target", 0)
        requested = list(reversed(features)) if reverse_request else features
        if bulk:
            removed = source.removeObjects(requested)
            # GeoFeatureGroup bulk removal intentionally follows Local dependencies.
            # Every dependency is explicitly requested here; do not infer a new
            # contract about leaving part of that graph in its original Body.
            self.assertEqual({obj.Name for obj in removed}, {obj.Name for obj in features})
        else:
            for feature in reversed(features):
                self.assertEqual(source.removeObject(feature), [feature])
        self.assertEqual(source.Group, [])
        # Preserve the model's original dependency order independently of the
        # order of the bulk removal request.
        target.addObjects(features)
        self.doc.recompute()
        self.assertEqual(target.Group, features)
        self.assertEqual(target.Tip, features[-1])
        self.assertEqual([feature.BaseFeature for feature in features], [None] + features[:-1])
        self.assertEqual([feature.getParentGeoFeatureGroup() for feature in features],
                         [target] * len(features))
        self.assertConsistent(target)
        self.assertConsistent(source, features)

    def testBulkMoveDependentChainInModelOrder(self):
        self.moveChain(True)

    def testBulkMoveDependentChainReverseRemovalOrder(self):
        self.moveChain(True, reverse_request=True)

    def testSingleMoveDependentChainControl(self):
        self.moveChain(False)

    def testSingleRemoveMiddleReroutesBaseFeatureControl(self):
        source, features = self.makeBody("Source", 3)
        first, middle, last = features
        self.assertEqual(source.removeObject(middle), [middle])
        self.doc.recompute()
        self.assertEqual(source.Group, [first, last])
        self.assertEqual(source.Tip, last)
        self.assertEqual(last.BaseFeature, first)
        self.assertConsistent(source, [middle])

    def testBulkMoveUndoRedo(self):
        source, features = self.makeBody("Source", 3)
        target, _ = self.makeBody("Target", 0)
        initial_source = self.state(source)
        initial_target = self.state(target)
        self.doc.openTransaction("Move all features")
        source.removeObjects(features)
        target.addObjects(features)
        self.doc.recompute()
        self.doc.commitTransaction()
        moved_source = self.state(source)
        moved_target = self.state(target)
        # Subtests keep the undo and redo controls reachable even when the
        # initial moved state exposes the stale Tip.
        with self.subTest(stage="moved"):
            self.assertConsistent(source, features)
        self.doc.undo()
        self.doc.recompute()
        self.assertEqual(self.state(source), initial_source)
        self.assertEqual(self.state(target), initial_target)
        self.assertEqual([feature.BaseFeature for feature in features], [None] + features[:-1])
        self.doc.redo()
        self.doc.recompute()
        self.assertEqual(self.state(source), moved_source)
        self.assertEqual(self.state(target), moved_target)
        self.assertEqual(target.Group, features)
        self.assertEqual(target.Tip, features[-1])
        with self.subTest(stage="redone"):
            self.assertConsistent(source, features)

    def testOrdinaryGroupBulkRemovalControl(self):
        group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        objects = [self.doc.addObject("App::FeaturePython", "Item%d" % index)
                   for index in range(3)]
        group.addObjects(objects)
        self.assertEqual(group.removeObjects([objects[1]]), [objects[1]])
        self.assertEqual(group.Group, [objects[0], objects[2]])
        self.assertNotIn(objects[1], group.OutList)


class TestBodyPartialLocalClosure(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BodyPartialClosure14516")
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.features = []
        for index in range(3):
            feature = self.body.newObject("PartDesign::Feature", "Feature%d" % index)
            feature.Shape = Part.makeBox(index + 2, 3, 5)
            self.features.append(feature)
        self.doc.recompute()
        self.assertEqual(self.body.Group, self.features)
        self.assertEqual([obj.BaseFeature for obj in self.features],
                         [None] + self.features[:-1])
        self.assertEqual(self.body.Tip, self.features[-1])

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def checkBulkRequest(self, requested):
        before = [obj.BaseFeature for obj in self.features]
        removed = self.body.removeObjects([requested])
        # Existing bulk semantics remove the complete Local BaseFeature chain,
        # in both directions. Retain that contract; a per-object loop differs.
        self.assertEqual({obj.Name for obj in removed},
                         {obj.Name for obj in self.features})
        self.assertEqual(self.body.Group, [])
        self.assertEqual([obj.BaseFeature for obj in self.features], before)
        self.assertIsNone(self.body.Tip, "The now-empty Body must not retain a removed Tip")

    def testBulkTipRequestKeepsDependencyClosure(self):
        self.checkBulkRequest(self.features[-1])

    def testBulkMiddleRequestKeepsDependencyClosure(self):
        self.checkBulkRequest(self.features[1])

    def testSingleTipRemovalLeavesEarlierFeaturesControl(self):
        tip = self.features[-1]
        self.assertEqual(self.body.removeObject(tip), [tip])
        self.assertEqual(self.body.Group, self.features[:-1])
        self.assertEqual(self.body.Tip, self.features[-2])
        self.assertEqual(self.features[1].BaseFeature, self.features[0])
        self.assertNotIn(tip, self.body.OutList)

    def testBulkRemovalLeavesIndependentGraphAndTipControl(self):
        independent = self.body.newObject("PartDesign::Feature", "Independent")
        independent.Shape = Part.makeBox(2, 2, 2)
        independent.BaseFeature = None
        self.doc.recompute()
        self.assertIsNone(independent.BaseFeature)
        self.assertEqual(self.body.Tip, independent)
        removed = self.body.removeObjects([self.features[1]])
        self.assertEqual({obj.Name for obj in removed},
                         {obj.Name for obj in self.features})
        self.assertEqual(self.body.Group, [independent])
        self.assertEqual(self.body.Tip, independent)
        self.assertIsNone(independent.BaseFeature)
        self.doc.recompute()
        self.assertAlmostEqual(self.body.Shape.Volume, 8)
        for feature in self.features:
            self.assertNotIn(feature, self.body.OutList)
