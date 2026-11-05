# SPDX-License-Identifier: LGPL-2.1-or-later

"""Tests for the read-only Normal property of sketches (FreeCAD#20992)."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App


def _zAxis(placement):
    return placement.Rotation.multVec(App.Vector(0, 0, 1))


class TestSketchNormal(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SketchNormal")
        self.addCleanup(self._closeDocument)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def _closeDocument(self):
        if self.doc and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def assertVectorAlmostEqual(self, actual, expected):
        self.assertAlmostEqual((actual - expected).Length, 0.0, places=9, msg=f"{actual} != {expected}")

    def testDefaultNormalIsZ(self):
        self.assertVectorAlmostEqual(self.sketch.Normal, App.Vector(0, 0, 1))

    def testNormalIsReadOnlyAndNotSaved(self):
        # The flags are static property types, which getPropertyStatus reports as numbers
        status = self.sketch.getTypeOfProperty("Normal")
        self.assertIn("ReadOnly", status)
        self.assertIn("Transient", status)
        self.assertIn("Output", status)

    def testNormalFollowsPlacement(self):
        self.sketch.Placement = App.Placement(
            App.Vector(1, 2, 3), App.Rotation(App.Vector(1, 0, 0), 90)
        )
        self.assertVectorAlmostEqual(self.sketch.Normal, App.Vector(0, -1, 0))

        self.sketch.Placement = App.Placement(
            App.Vector(), App.Rotation(App.Vector(0, 1, 0), -90)
        )
        self.assertVectorAlmostEqual(self.sketch.Normal, App.Vector(-1, 0, 0))

    def testNormalFollowsAttachment(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.sketch.AttachmentSupport = [(box, "Face1")]
        self.sketch.MapMode = "FlatFace"
        self.doc.recompute()

        self.assertVectorAlmostEqual(self.sketch.Normal, _zAxis(self.sketch.Placement))
        self.assertAlmostEqual(abs(self.sketch.Normal.x), 1.0)

    def testNormalInExpression(self):
        self.sketch.Placement = App.Placement(
            App.Vector(), App.Rotation(App.Vector(1, 0, 0), 90)
        )
        consumer = self.doc.addObject("App::FeaturePython", "Consumer")
        consumer.addProperty("App::PropertyVector", "Direction")
        consumer.setExpression("Direction", "Sketch.Normal")
        self.doc.recompute()
        self.assertVectorAlmostEqual(consumer.Direction, App.Vector(0, -1, 0))

        self.sketch.Placement = App.Placement()
        self.doc.recompute()
        self.assertVectorAlmostEqual(consumer.Direction, App.Vector(0, 0, 1))

    def testNormalRestoredFromPlacement(self):
        self.sketch.Placement = App.Placement(
            App.Vector(), App.Rotation(App.Vector(0, 1, 0), 90)
        )
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "SketchNormal.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)

        self.doc = App.openDocument(path)
        sketch = self.doc.getObject("Sketch")
        self.assertVectorAlmostEqual(sketch.Normal, App.Vector(1, 0, 0))
