# SPDX-License-Identifier: LGPL-2.1-or-later
"""Display-only section properties must report their change to the document.

SectionCutOnly, ShowOutsidePartialBoundaries, ConnectionLine and
LockRelativePositionToSource only change how a section is drawn. Changing one
must not ask for a recompute, but the document must still be told about the
change: the view provider redraws from it and the GUI marks the document as
modified from it.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class _ChangeRecorder:
    def __init__(self):
        self.changes = []

    def slotChangedObject(self, obj, prop):
        self.changes.append((obj.Name, prop))


class DrawViewSectionDisplayPropertyTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDSectionDisplayProperty")
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        page.addView(self.section)
        self.section.BaseView = view
        self.section.Source = [box]
        self.section.SectionNormal = FreeCAD.Vector(0, 1, 0)
        self.section.Direction = FreeCAD.Vector(0, 1, 0)
        self.section.SectionOrigin = FreeCAD.Vector(5, 5, 5)
        self.doc.recompute()
        self.recorder = _ChangeRecorder()
        FreeCAD.addDocumentObserver(self.recorder)

    def tearDown(self):
        FreeCAD.removeDocumentObserver(self.recorder)
        FreeCAD.closeDocument(self.doc.Name)

    def testDisplayPropertyChangeIsSignalledWithoutRecompute(self):
        for name in (
            "SectionCutOnly",
            "ShowOutsidePartialBoundaries",
            "ConnectionLine",
            "LockRelativePositionToSource",
        ):
            with self.subTest(property=name):
                self.assertNotIn("Touched", self.section.State)
                self.recorder.changes.clear()
                setattr(self.section, name, not getattr(self.section, name))
                self.assertIn((self.section.Name, name), self.recorder.changes)
                self.assertNotIn("Touched", self.section.State)


if __name__ == "__main__":
    unittest.main()
