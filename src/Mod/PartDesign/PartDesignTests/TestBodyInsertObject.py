# SPDX-License-Identifier: LGPL-2.1-or-later
"""Body.insertObject() with a target that is not in the Body's Group."""

import unittest

import FreeCAD as App
import PartDesign


class TestBodyInsertObject(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("BodyInsertObject")
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.pad = self.body.newObject("PartDesign::Pad", "Pad")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def checkRejected(self, target):
        for after in (False, True):
            feature = self.doc.addObject("PartDesign::Pocket", "Pocket")
            # The Origin and its features belong to the Body (hasObject) but are
            # not in Group; inserting after them used an end() + 1 iterator.
            with self.assertRaises(Exception):
                self.body.insertObject(feature, target, after)
            self.assertEqual(self.body.Group, [self.pad])
            self.doc.removeObject(feature.Name)

    def testInsertRelativeToOriginIsRejected(self):
        self.checkRejected(self.body.Origin)

    def testInsertRelativeToOriginFeatureIsRejected(self):
        for feature in self.body.Origin.OriginFeatures:
            with self.subTest(feature=feature.Name):
                self.checkRejected(feature)

    def testInsertRelativeToGroupMemberStillWorks(self):
        before = self.doc.addObject("PartDesign::Pocket", "Before")
        self.body.insertObject(before, self.pad, False)
        after = self.doc.addObject("PartDesign::Pocket", "After")
        self.body.insertObject(after, self.pad, True)
        first = self.doc.addObject("PartDesign::Pocket", "First")
        self.body.insertObject(first, None, True)
        self.assertEqual(self.body.Group, [first, before, self.pad, after])

    def testInsertGroupMemberIsRejected(self):
        # A second Group entry also rerouted the BaseFeature chain: the feature was based on
        # itself (after=True) or on the feature based on it (after=False).
        pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
        for target, after in ((self.pad, False), (self.pad, True), (None, False), (None, True)):
            with self.subTest(target=target and target.Name, after=after):
                with self.assertRaises(Exception):
                    self.body.insertObject(pocket, target, after)
                self.assertEqual(self.body.Group, [self.pad, pocket])
                self.assertIsNone(self.pad.BaseFeature)
                self.assertEqual(pocket.BaseFeature, self.pad)

    def testAddGroupMemberChangesNothing(self):
        pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
        self.assertEqual(self.body.Tip, pocket)
        self.body.addObject(self.pad)
        self.assertEqual(self.body.Group, [self.pad, pocket])
        self.assertEqual(self.body.Tip, pocket)
        self.assertIsNone(self.pad.BaseFeature)
        self.assertEqual(pocket.BaseFeature, self.pad)
