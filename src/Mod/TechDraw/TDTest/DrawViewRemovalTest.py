# SPDX-License-Identifier: LGPL-2.1-or-later
"""Removing a view or a page also removes the objects that depend on it (#33799)."""

import unittest

import FreeCAD
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewRemovalTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDViewRemoval")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.views = []
        self.dependents = []
        for index in range(2):
            view = self.doc.addObject("TechDraw::DrawViewPart", "View")
            self.page.addView(view)
            view.Source = [self.box]
            self.views.append(view)

            dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
            self.page.addView(dimension)
            dimension.Type = "Distance"
            dimension.References2D = [(view, "Edge0")]

            balloon = self.doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
            balloon.SourceView = view
            self.page.addView(balloon)

            hatch = self.doc.addObject("TechDraw::DrawHatch", "Hatch")
            hatch.Source = (view, ["Face0"])

            self.dependents.append([dimension.Name, balloon.Name, hatch.Name])

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testRemoveViewRemovesDependents(self):
        """Removing a view removes its dimensions, balloons and hatches."""
        viewName = self.views[0].Name
        self.doc.removeObject(viewName)
        self.assertIsNone(self.doc.getObject(viewName))
        for name in self.dependents[0]:
            self.assertIsNone(self.doc.getObject(name), name)
        # the other view and its dependents are untouched
        self.assertIsNotNone(self.doc.getObject(self.views[1].Name))
        for name in self.dependents[1]:
            self.assertIsNotNone(self.doc.getObject(name), name)

    def testRemoveDetailViewRemovesDependents(self):
        """Removing a detail view removes its dimensions, balloons and hatches."""
        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        self.page.addView(detail)
        detail.BaseView = self.views[0]
        detail.AnchorPoint = FreeCAD.Vector(5.0, 5.0, 0.0)

        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(detail, "Edge0")]

        balloon = self.doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
        balloon.SourceView = detail
        self.page.addView(balloon)

        hatch = self.doc.addObject("TechDraw::DrawHatch", "Hatch")
        hatch.Source = (detail, ["Face0"])
        names = [dimension.Name, balloon.Name, hatch.Name]

        self.doc.removeObject(detail.Name)

        for name in names:
            self.assertIsNone(self.doc.getObject(name), name)
        # the base view and its dependents are untouched
        self.assertIsNotNone(self.doc.getObject(self.views[0].Name))
        for name in self.dependents[0]:
            self.assertIsNotNone(self.doc.getObject(name), name)

    def testRemovePageRemovesEverything(self):
        """Removing a page with dimensioned views leaves no TechDraw object behind."""
        self.doc.removeObject(self.page.Name)
        leftovers = [obj.Name for obj in self.doc.Objects
                     if obj.TypeId.startswith("TechDraw::")]
        self.assertEqual(leftovers, [])
        self.assertIsNotNone(self.doc.getObject(self.box.Name))

    def testRemoveCollectionRemovesItsViews(self):
        """Removing a view collection removes all of its views without crashing."""
        collection = self.doc.addObject("TechDraw::DrawViewCollection", "Collection")
        self.page.addView(collection)
        names = []
        for index in range(4):
            view = self.doc.addObject("TechDraw::DrawViewPart", "CollectionView")
            view.Source = [self.box]
            collection.Views = collection.Views + [view]
            names.append(view.Name)
        self.doc.recompute()

        self.doc.removeObject(collection.Name)
        self.assertIsNone(self.doc.getObject("Collection"))
        for name in names:
            self.assertIsNone(self.doc.getObject(name), name)
        self.assertIsNotNone(self.doc.getObject(self.views[0].Name))

    def testRemoveComplexSectionKeepsSharedProfile(self):
        """A generated section profile still used by another section is not removed."""
        self.doc.UndoMode = 1
        profile = self.doc.addObject("Part::Feature", "SectionProfile")
        sections = []
        for _ in range(2):
            section =self.doc.addObject("TechDraw::DrawComplexSection", "ComplexSection")
            self.page.addView(section)
            section.BaseView = self.views[0]
            section.CuttingToolWireObject = profile
            sections.append(section)
        profileName = profile.Name
        firstName = sections[0].Name

        self.doc.openTransaction("Remove section")
        self.doc.removeObject(firstName)
        self.doc.commitTransaction()
        self.assertIsNone(self.doc.getObject(firstName))
        self.assertIsNotNone(self.doc.getObject(profileName))
        self.assertEqual(sections[1].CuttingToolWireObject, profile)

        self.doc.undo()
        self.assertEqual(self.doc.getObject(firstName).CuttingToolWireObject, profile)

        # the profile still goes with the last section that uses it
        self.doc.removeObject(firstName)
        self.doc.removeObject(sections[1].Name)
        self.assertIsNone(self.doc.getObject(profileName))
