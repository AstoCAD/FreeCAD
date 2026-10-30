# SPDX-License-Identifier: LGPL-2.1-or-later
"""The "Show placement and sketch plane" preference (View/ShowPlacementOnSelection).

https://github.com/FreeCAD/FreeCAD/issues/19878
0 = never (default), 1 = on selection, 2 = on preselection and selection.
The placement and the plane are shown without writing the ShowPlacement/ShowPlane properties.
"""

import unittest

import FreeCAD as App

_part_available = False
_sketcher_available = False
if App.GuiUp:
    import FreeCADGui as Gui
    from pivy import coin

    try:
        import Part  # noqa: F401

        _part_available = True
    except ImportError:
        pass
    try:
        import Sketcher  # noqa: F401

        _sketcher_available = True
    except ImportError:
        pass

SO_SWITCH_NONE = -1
SO_SWITCH_ALL = -3


def _switches(vp):
    search = coin.SoSearchAction()
    search.setType(coin.SoSwitch.getClassTypeId())
    search.setInterest(coin.SoSearchAction.ALL)
    search.setSearchingAll(True)
    search.apply(vp.RootNode)
    paths = search.getPaths()
    return [paths[i].getTail() for i in range(paths.getLength())]


def _find_switch(vp, prop):
    """Find the switch node driven by the boolean view property `prop`.

    The property is toggled and restored to find it, before the preference is set.
    """
    nodes = _switches(vp)
    before = [n.whichChild.getValue() for n in nodes]
    setattr(vp, prop, True)
    after = [n.whichChild.getValue() for n in nodes]
    setattr(vp, prop, False)
    changed = [n for n, b, a in zip(nodes, before, after) if b != a]
    return changed[0] if len(changed) == 1 else None


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
@unittest.skipUnless(_part_available, "Requires the Part module")
class TestShowPlacementOnSelectionGui(unittest.TestCase):
    KEY = "ShowPlacementOnSelection"

    def setUp(self):
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/View")
        self.had_key = self.KEY in self.params.GetInts()
        self.old_value = self.params.GetInt(self.KEY, 0)
        self.addCleanup(self._restore_preference)

        self.doc = App.newDocument("ShowPlacementOnSelection19878")
        self.addCleanup(self._close_document)
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        Gui.updateGui()
        self.box_vp = self.box.ViewObject
        self.placement = _find_switch(self.box_vp, "ShowPlacement")
        self.assertIsNotNone(self.placement, "placement switch not found")
        Gui.Selection.clearSelection()
        Gui.Selection.clearPreselection()

    def _restore_preference(self):
        if self.had_key:
            self.params.SetInt(self.KEY, self.old_value)
        else:
            self.params.RemInt(self.KEY)

    def _close_document(self):
        Gui.Selection.clearSelection()
        Gui.Selection.clearPreselection()
        App.closeDocument(self.doc.Name)

    def _set_mode(self, mode):
        self.params.SetInt(self.KEY, mode)

    def _shown(self, switch):
        return switch.whichChild.getValue() == SO_SWITCH_ALL

    def testNeverIsDefault(self):
        self.params.RemInt(self.KEY)
        Gui.Selection.addSelection(self.box)
        self.assertFalse(self._shown(self.placement))
        Gui.Selection.setPreselection(self.box)
        self.assertFalse(self._shown(self.placement))
        self.assertFalse(self.box_vp.ShowPlacement)

    def testOnSelection(self):
        self._set_mode(1)
        Gui.Selection.setPreselection(self.box)
        self.assertFalse(self._shown(self.placement), "preselection must not show it")
        Gui.Selection.clearPreselection()
        Gui.Selection.addSelection(self.box)
        self.assertTrue(self._shown(self.placement))
        self.assertFalse(self.box_vp.ShowPlacement, "the property must not be written")
        Gui.Selection.clearSelection()
        self.assertFalse(self._shown(self.placement))

    def testOnSelectionHiddenObject(self):
        self._set_mode(1)
        Gui.Selection.addSelection(self.box)
        self.assertTrue(self._shown(self.placement))
        self.box_vp.Visibility = False
        self.assertFalse(self._shown(self.placement))

    def testOnPreselectionAndSelection(self):
        self._set_mode(2)
        Gui.Selection.setPreselection(self.box)
        self.assertTrue(self._shown(self.placement))
        Gui.Selection.clearPreselection()
        self.assertFalse(self._shown(self.placement))
        Gui.Selection.addSelection(self.box)
        self.assertTrue(self._shown(self.placement))
        self.assertFalse(self.box_vp.ShowPlacement)

    def testPropertyStillWins(self):
        self._set_mode(1)
        self.box_vp.ShowPlacement = True
        self.addCleanup(setattr, self.box_vp, "ShowPlacement", False)
        Gui.Selection.addSelection(self.box)
        Gui.Selection.clearSelection()
        self.assertTrue(self._shown(self.placement))

    def testBackToNever(self):
        self._set_mode(1)
        Gui.Selection.addSelection(self.box)
        self.assertTrue(self._shown(self.placement))
        self._set_mode(0)
        # applied on the next selection change
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.box)
        self.assertFalse(self._shown(self.placement))

    @unittest.skipUnless(_sketcher_available, "Requires the Sketcher module")
    def testSketchPlaneOnSelection(self):
        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()
        Gui.updateGui()
        plane = _find_switch(sketch.ViewObject, "ShowPlane")
        self.assertIsNotNone(plane, "plane switch not found")
        self._set_mode(1)
        Gui.Selection.addSelection(sketch)
        self.assertTrue(self._shown(plane))
        self.assertFalse(sketch.ViewObject.ShowPlane, "the property must not be written")
        Gui.Selection.clearSelection()
        self.assertFalse(self._shown(plane))


if __name__ == "__main__":
    unittest.main()
