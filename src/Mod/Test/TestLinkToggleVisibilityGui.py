# SPDX-License-Identifier: LGPL-2.1-or-later
"""Std_ToggleVisibility on objects reached through a link to a container."""

import unittest

import FreeCAD as App

_part_available = False
if App.GuiUp:
    import FreeCADGui as Gui

    try:
        import Part  # noqa: F401

        _part_available = True
    except ImportError:
        pass


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
@unittest.skipUnless(_part_available, "Requires the Part module")
class TestLinkToggleVisibilityGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("LinkToggleVisibility21823")
        self.part = self.doc.addObject("App::Part", "Part")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.peer = self.doc.addObject("Part::Box", "Peer")
        self.part.addObject(self.box)
        self.part.addObject(self.peer)
        self.link = self.doc.addObject("App::Link", "Link")
        self.link.LinkedObject = self.part
        self.doc.recompute()
        Gui.updateGui()
        Gui.Selection.clearSelection()

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def _toggle(self, subname):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.link.Name, subname)
        Gui.runCommand("Std_ToggleVisibility")
        Gui.updateGui()

    def testToggleObjectInsideLinkedPart(self):
        # https://github.com/FreeCAD/FreeCAD/issues/21823
        # Selecting a child of the linked Part as a whole (as in the tree) must toggle
        # that child, not hide the whole link.
        self.assertTrue(self.box.Visibility)
        self._toggle(self.box.Name + ".")
        self.assertTrue(self.link.Visibility)
        self.assertFalse(self.box.Visibility)
        self.assertTrue(self.peer.Visibility)
        self._toggle(self.box.Name + ".")
        self.assertTrue(self.link.Visibility)
        self.assertTrue(self.box.Visibility)

    def testTogglePickedElementHidesLink(self):
        # A face picked in the 3D view toggles the link instance, not the original object.
        self._toggle(self.box.Name + ".Face1")
        self.assertFalse(self.link.Visibility)
        self.assertTrue(self.box.Visibility)
        self._toggle(self.box.Name + ".Face1")
        self.assertTrue(self.link.Visibility)
        self.assertTrue(self.box.Visibility)
