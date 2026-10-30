# SPDX-License-Identifier: LGPL-2.1-or-later
"""Draft and Arch views follow the TechDraw line cap preference (issue #27866)."""

import re
import unittest

import FreeCAD as App

from .TechDrawTestUtilities import createPageWithSVGTemplate

CAP_PARAM = "User parameter:BaseApp/Preferences/Mod/TechDraw/General"
CAP_ENTRY = "EdgeCapStyle"


def lineCaps(svg):
    """Return the set of stroke-linecap values used in an SVG string."""
    return set(re.findall(r'stroke-linecap(?::|=")(\w+)', svg))


class DrawViewLineCapGuiTest(unittest.TestCase):
    def setUp(self):
        try:
            import Arch
            import Draft
        except ImportError:
            self.skipTest("Draft and BIM are needed for this test")
        self.Arch = Arch
        self.Draft = Draft
        self.grp = App.ParamGet(CAP_PARAM)
        if CAP_ENTRY in self.grp.GetInts():
            self.addCleanup(self.grp.SetInt, CAP_ENTRY, self.grp.GetInt(CAP_ENTRY))
        else:
            self.addCleanup(self.grp.RemInt, CAP_ENTRY)
        self.grp.RemInt(CAP_ENTRY)
        self.doc = App.newDocument("TDLineCap")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.page = createPageWithSVGTemplate(self.doc)

    def makeDraftView(self):
        source = self.Draft.make_wire(
            [App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 5, 0)]
        )
        view = self.doc.addObject("TechDraw::DrawViewDraft", "DraftView")
        view.Source = source
        self.page.addView(view)
        return view

    def makeArchView(self):
        line = self.Draft.make_wire([App.Vector(0, 0, 0), App.Vector(2000, 0, 0)])
        wall = self.Arch.makeWall(line, height=2000)
        section = self.Arch.makeSectionPlane([wall])
        section.Placement.Base = App.Vector(0, 0, 1000)
        view = self.doc.addObject("TechDraw::DrawViewArch", "ArchView")
        view.Source = section
        view.AllOn = True
        self.page.addView(view)
        return view

    def symbolWithCap(self, view, index):
        if index is None:
            self.grp.RemInt(CAP_ENTRY)
        else:
            self.grp.SetInt(CAP_ENTRY, index)
        view.touch()
        self.doc.recompute()
        return view.Symbol

    def checkView(self, view):
        default = self.symbolWithCap(view, None)
        self.assertEqual(lineCaps(default), {"square"})
        for index, cap in ((0, "round"), (1, "square"), (2, "butt")):
            with self.subTest(index=index):
                self.assertEqual(lineCaps(self.symbolWithCap(view, index)), {cap})
        # an unknown value keeps the historical square caps
        self.assertEqual(self.symbolWithCap(view, 32), default)
        self.assertEqual(self.symbolWithCap(view, None), default)

    def testDraftViewFollowsLineCapPreference(self):
        self.checkView(self.makeDraftView())

    def testArchViewFollowsLineCapPreference(self):
        self.checkView(self.makeArchView())


if __name__ == "__main__":
    unittest.main()
