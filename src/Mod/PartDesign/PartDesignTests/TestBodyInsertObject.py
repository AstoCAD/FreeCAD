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
