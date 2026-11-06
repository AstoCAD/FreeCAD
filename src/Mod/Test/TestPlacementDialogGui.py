# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cancelling the placement dialog must only undo its own changes."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestPlacementDialogGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PlacementDialog27865")
        self.doc.UndoMode = 1
        self.obj = self.doc.addObject("App::FeaturePython", "Feature")
        self.obj.addProperty("App::PropertyPlacement", "AttachmentOffset")
        self.doc.recompute()
        self.doc.commitTransaction()
        self.dialog = Gui.TaskPlacement()
        self.dialog.setPropertyName("AttachmentOffset")
        self.dialog.setSelection([self.obj])
        self.dialog.bindObject()
        self.dialog.open()
        Gui.updateGui()

    def tearDown(self):
        self.dialog.form = None
        App.closeDocument(self.doc.Name)

    def testRejectRevertsOwnChanges(self):
        self.obj.AttachmentOffset = App.Placement(App.Vector(1, 2, 3), App.Rotation())
        self.dialog.reject()
        self.assertEqual(self.obj.AttachmentOffset.Base, App.Vector(0, 0, 0))

    def testRejectKeepsObjectsOfAnotherCommand(self):
        # https://github.com/FreeCAD/FreeCAD/issues/27865
        # A command run while the dialog is open (e.g. PartDesign Pad) opens its own
        # transaction and creates objects, then asks to close the dialog.
        self.doc.openTransaction("Other command")
        self.doc.addObject("App::FeaturePython", "Other")
        self.dialog.reject()
        self.assertIsNotNone(self.doc.getObject("Other"))
        self.doc.commitTransaction()
        self.assertIn("Other command", self.doc.UndoNames)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestPlacementDialogApplyGui(unittest.TestCase):
    """For the "Placement" property the dialog applies a recorded Python command."""

    def setUp(self):
        self.doc = App.newDocument("PlacementDialogApply")
        self.obj = self.doc.addObject("App::FeaturePython", "Feature")
        self.obj.addProperty("App::PropertyPlacement", "Placement")
        self.doc.recompute()
        self.dialog = Gui.TaskPlacement()
        self.dialog.setSelection([self.obj])
        self.dialog.open()
        Gui.updateGui()

    def tearDown(self):
        self.dialog.form = None
        App.closeDocument(self.doc.Name)

    def testAcceptKeepsAllDigits(self):
        # the command held only 6 significant digits: 12345.67 became 12345.7
        target = App.Placement(
            App.Vector(12345.67, -98765.43, 1000.25), App.Rotation(App.Vector(0, 0, 1), 30)
        )
        self.dialog.setPlacement(target)
        Gui.updateGui()
        self.assertTrue(self.dialog.accept())
        result = self.obj.Placement
        self.assertAlmostEqual(result.Base.x, 12345.67, places=6)
        self.assertAlmostEqual(result.Base.y, -98765.43, places=6)
        self.assertAlmostEqual(result.Base.z, 1000.25, places=6)
        self.assertAlmostEqual(result.Rotation.Angle, target.Rotation.Angle, places=6)
