# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawProjectionGroupTest(unittest.TestCase):
    def setUp(self):
        """Creates a box and sphere to make a fusions from them.
        Then creates a page and projection group"""
        FreeCAD.newDocument("TDGroup")
        FreeCAD.setActiveDocument("TDGroup")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDGroup")
        self.document = FreeCAD.ActiveDocument
        print("document created")

        # make Fusion feature
        box = FreeCAD.ActiveDocument.addObject("Part::Box", "Box")
        box.recompute()
        print("box created")
        sphere = FreeCAD.ActiveDocument.addObject("Part::Sphere", "Sphere")
        sphere.recompute()
        print("sphere created")
        self.fusion = FreeCAD.ActiveDocument.addObject("Part::MultiFuse", "Fusion")
        FreeCAD.ActiveDocument.Fusion.Shapes = [box, sphere]
        self.fusion.recompute()
        print("Fusion created")

        # make a page
        print("making a page")
        self.page = createPageWithSVGTemplate()
        print("Page created")

    def tearDown(self):
        FreeCAD.closeDocument("TDGroup")

    def testMissingProjectionPosition(self):
        """An absent projection must raise instead of dereferencing a null view."""
        group = self.document.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        self.page.addView(group)
        group.ProjectionType = "Third angle"
        group.AutoDistribute = False
        with self.assertRaises(ValueError):
            group.getXYPosition("Right")
        self.assertEqual(group.getXYPosition("Front"), FreeCAD.Vector())
        group.addProjection("Front")
        right = group.addProjection("Right")
        right.X = 12
        right.Y = 34
        self.assertEqual(group.getXYPosition("Right"), FreeCAD.Vector(12, 34, 0))

    def testSecondaryProjectionWithoutAnchor(self):
        """A secondary projection is refused, without leaving an item behind, when there is no Front"""
        group = self.document.addObject("TechDraw::DrawProjGroup", "ProjGroup")
        self.page.addView(group)
        group.Source = [self.fusion]
        objectCount = len(self.document.Objects)
        with self.assertRaises(RuntimeError):
            group.addProjection("Top")
        self.assertEqual(group.Views, [])
        self.assertEqual(len(self.document.Objects), objectCount)

        # the group is still usable once it has its anchor
        group.addProjection("Front")
        top = group.addProjection("Top")
        self.assertEqual([view.Type for view in group.Views], ["Front", "Top"])
        self.assertNotEqual(top.Direction, group.Anchor.Direction)

    def testMakeProjectionGroup(self):
        """Tests if a projection group can be added to view1"""
        # make projection group
        print("making a projection group")
        self.document.openTransaction("Create Proj Group")
        groupName = "ProjGroup"
        group = FreeCAD.ActiveDocument.addObject("TechDraw::DrawProjGroup", groupName)
        self.page.addView(group)
        print("Group created")
        group.Source = [self.fusion]

        print("adding views")
        group.addProjection("Front")  # need an Anchor
        print("added Front")

        # update group
        anchorDir = FreeCAD.Vector(0.0, 0.0, 1.0)
        anchorRot = FreeCAD.Vector(1.0, 0.0, 0.0)
        group.Anchor.Direction = anchorDir
        group.Anchor.RotationVector = anchorRot
        print("Anchor values set")
        group.Anchor.recompute()
        self.document.commitTransaction()
        print("Front/Anchor recomputed")
        group.addProjection("Left")
        print("added Left")
        group.addProjection("Top")
        print("added Top")
        group.addProjection("Right")
        print("added Right")
        group.addProjection("Rear")
        print("added Rear")
        group.addProjection("Bottom")
        print("added Bottom")

        # remove a view from projection group
        group.removeProjection("Left")
        print("removed Left")

        # test getItemByLabel method
        print("testing getItemByLabel")
        label = "Top"
        item = group.getItemByLabel(label)
        print("Item Label: " + label + " Item Name: " + item.Name)

        print("recomputing document")
        FreeCAD.ActiveDocument.recompute()

        for v in group.Views:
            print("View: " + v.Label + " " + v.TypeId)
            v.autoPosition()

        group.recompute()

        self.assertTrue("Up-to-date" in group.State)


if __name__ == "__main__":
    unittest.main()
