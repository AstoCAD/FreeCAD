# SPDX-License-Identifier: LGPL-2.1-or-later
"""PartDesign_Clone keeps the colors of the cloned body, also for clones of clones."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import PartDesign
import PartDesignGui
from PySide import QtCore


class TestCloneColorGui(unittest.TestCase):
    COLOR = (0.8, 0.1, 0.2)

    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("CloneColorGui")
        App.setActiveDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.box = self.body.newObject("PartDesign::AdditiveBox", "Box")
        self.doc.recompute()

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def color(self, obj):
        return tuple(round(c, 3) for c in obj.ViewObject.ShapeAppearance[0].DiffuseColor[:3])

    def clone(self, source):
        before = set(self.doc.Objects)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, source.Name)
        Gui.runCommand("PartDesign_Clone", 0)
        self.pump()
        new = [obj for obj in self.doc.Objects if obj not in before]
        clones = [obj for obj in new if obj.TypeId == "PartDesign::FeatureBase"]
        bodies = [obj for obj in new if obj.TypeId == "PartDesign::Body"]
        self.assertEqual(len(clones), 1)
        self.assertEqual(len(bodies), 1)
        return bodies[0], clones[0]

    def testCloneOfCloneKeepsColor(self):
        # https://github.com/FreeCAD/FreeCAD/issues/11011
        material = self.body.ViewObject.ShapeAppearance[0]
        material.DiffuseColor = self.COLOR + (1.0,)
        self.body.ViewObject.ShapeAppearance = [material]
        self.assertEqual(self.color(self.box), self.COLOR)

        body1, clone1 = self.clone(self.body)
        self.assertEqual(self.color(clone1), self.COLOR)

        body2, clone2 = self.clone(body1)
        self.assertEqual(self.color(clone2), self.COLOR)

        # The new bodies carry the color too, so later features and clones keep it.
        self.assertEqual(self.color(body1), self.COLOR)
        self.assertEqual(self.color(body2), self.COLOR)
