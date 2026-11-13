# SPDX-License-Identifier: LGPL-2.1-or-later
"""Removing a view also removes the break and broken-out section objects it owns."""

import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewBreakRemovalTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDViewBreakRemoval")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self._addView("TechDraw::DrawViewPart", "View")
        self.viewBreak = self._addBreak(self.view)
        self.otherView = self._addView("TechDraw::DrawViewPart", "OtherView")
        self.otherBreak = self._addBreak(self.otherView)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _addView(self, typeName, name):
        view = self.doc.addObject(typeName, name)
        self.page.addView(view)
        view.Source = [self.box]
        return view

    def _addBreak(self, view):
        viewBreak = self.doc.addObject("TechDraw::DrawViewBreak", "Break")
        viewBreak.StartPoint = FreeCAD.Vector(3.0, 0.0, 0.0)
        viewBreak.EndPoint = FreeCAD.Vector(7.0, 0.0, 0.0)
        viewBreak.Direction = FreeCAD.Vector(1.0, 0.0, 0.0)
        view.Breaks = view.Breaks + [viewBreak]
        return viewBreak

    def _addBrokenOutSection(self, view):
        section = self.doc.addObject("TechDraw::DrawViewBrokenOutSection", "BrokenOutSection")
        section.Outline = [
            FreeCAD.Vector(2.0, 2.0, 0.0),
            FreeCAD.Vector(8.0, 2.0, 0.0),
            FreeCAD.Vector(8.0, 8.0, 0.0),
            FreeCAD.Vector(2.0, 8.0, 0.0),
        ]
        section.Depth = 4.0
        view.BrokenOutSections = view.BrokenOutSections + [section]
        return section

    def testRemoveViewRemovesItsBreaks(self):
        """Removing a view removes its breaks, suppressed or not, and only its own."""
        suppressed = self._addBreak(self.view)
        suppressed.Suppressed = True
        names = [self.viewBreak.Name, suppressed.Name]

        self.doc.removeObject(self.view.Name)

        for name in names:
            self.assertIsNone(self.doc.getObject(name), name)
        self.assertIsNotNone(self.doc.getObject(self.otherBreak.Name))
        self.assertEqual(self.otherView.Breaks, [self.otherBreak])

    def testUndoRedoRemoveView(self):
        """Undo of the view removal brings back the view with its break."""
        viewName = self.view.Name
        breakName = self.viewBreak.Name
        self.doc.UndoMode = 1
        self.doc.openTransaction("Remove view")
        self.doc.removeObject(viewName)
        self.doc.commitTransaction()
        self.assertIsNone(self.doc.getObject(viewName))
        self.assertIsNone(self.doc.getObject(breakName))

        self.doc.undo()
        view = self.doc.getObject(viewName)
        viewBreak = self.doc.getObject(breakName)
        self.assertIsNotNone(view)
        self.assertIsNotNone(viewBreak)
        self.assertEqual(view.Breaks, [viewBreak])

        self.doc.redo()
        self.assertIsNone(self.doc.getObject(viewName))
        self.assertIsNone(self.doc.getObject(breakName))

    def testSharedBreakIsKept(self):
        """A break that another view also uses stays with that view."""
        self.otherView.Breaks = self.otherView.Breaks + [self.viewBreak]

        self.doc.removeObject(self.view.Name)

        self.assertIsNotNone(self.doc.getObject(self.viewBreak.Name))
        self.assertEqual(self.otherView.Breaks, [self.otherBreak, self.viewBreak])

    def testModelBreakObjectIsKept(self):
        """Model objects used as breaks by a broken view are not removed with it."""
        line = self.doc.addObject("Part::Feature", "BreakLine")
        line.Shape = Part.makeLine(FreeCAD.Vector(5, -20, 0), FreeCAD.Vector(5, 20, 0))
        view = self._addView("TechDraw::DrawBrokenView", "BrokenView")
        viewBreak = self._addBreak(view)
        view.Breaks = [line, viewBreak]

        self.doc.removeObject(view.Name)

        self.assertIsNotNone(self.doc.getObject(line.Name))
        self.assertIsNone(self.doc.getObject(viewBreak.Name))

    def testRemoveViewRemovesItsBrokenOutSections(self):
        """Removing a view removes its broken-out sections, suppressed or not, and only its own."""
        section = self._addBrokenOutSection(self.view)
        suppressed = self._addBrokenOutSection(self.view)
        suppressed.Suppressed = True
        otherSection = self._addBrokenOutSection(self.otherView)
        names = [section.Name, suppressed.Name]

        self.doc.removeObject(self.view.Name)

        for name in names:
            self.assertIsNone(self.doc.getObject(name), name)
        self.assertIsNotNone(self.doc.getObject(otherSection.Name))
        self.assertEqual(self.otherView.BrokenOutSections, [otherSection])

    def testUndoRedoRemoveViewWithBrokenOutSection(self):
        """Undo of the view removal brings back the view with its broken-out section."""
        viewName = self.view.Name
        sectionName = self._addBrokenOutSection(self.view).Name
        self.doc.UndoMode = 1
        self.doc.openTransaction("Remove view")
        self.doc.removeObject(viewName)
        self.doc.commitTransaction()
        self.assertIsNone(self.doc.getObject(viewName))
        self.assertIsNone(self.doc.getObject(sectionName))

        self.doc.undo()
        view = self.doc.getObject(viewName)
        section = self.doc.getObject(sectionName)
        self.assertIsNotNone(view)
        self.assertIsNotNone(section)
        self.assertEqual(view.BrokenOutSections, [section])

        self.doc.redo()
        self.assertIsNone(self.doc.getObject(viewName))
        self.assertIsNone(self.doc.getObject(sectionName))

    def testSharedBrokenOutSectionIsKept(self):
        """A broken-out section that another view also uses stays with that view."""
        section = self._addBrokenOutSection(self.view)
        self.otherView.BrokenOutSections = [section]

        self.doc.removeObject(self.view.Name)

        self.assertIsNotNone(self.doc.getObject(section.Name))
        self.assertEqual(self.otherView.BrokenOutSections, [section])


if __name__ == "__main__":
    unittest.main()
