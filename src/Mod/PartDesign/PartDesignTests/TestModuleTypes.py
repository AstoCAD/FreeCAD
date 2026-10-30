# SPDX-License-Identifier: LGPL-2.1-or-later
"""The PartDesign module exposes the Python types of its objects."""

import unittest

import FreeCAD as App
import PartDesign


class TestModuleTypes(unittest.TestCase):
    """https://github.com/FreeCAD/FreeCAD/issues/18201"""

    def setUp(self):
        self.doc = App.newDocument("PartDesignModuleTypes18201")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def testBodyAndFeatureTypesAreExposed(self):
        body = self.doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        self.doc.recompute()

        self.assertTrue(hasattr(PartDesign, "Body"), "PartDesign.Body is missing")
        self.assertTrue(hasattr(PartDesign, "Feature"), "PartDesign.Feature is missing")
        self.assertIs(type(body), PartDesign.Body)
        self.assertIsInstance(box, PartDesign.Feature)
        self.assertNotIsInstance(body, PartDesign.Feature)
