# SPDX-License-Identifier: LGPL-2.1-or-later
"""Public creation helpers operate in their parent view's owning document."""

import time
import unittest

import FreeCAD as App
import Part
import TechDraw
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawCreationDocumentTest(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        previous_name = previous.Name if previous else None

        def restoreActive():
            if previous_name in App.listDocuments():
                App.setActiveDocument(previous_name)

        self.addCleanup(restoreActive)

    def _drawing(self, name):
        doc = App.newDocument(name)
        self.addCleanup(App.closeDocument, doc.Name)
        source = doc.addObject("Part::Feature", "Geometry")
        source.Shape = Part.makeBox(10, 10, 10)
        page = createPageWithSVGTemplate(doc)
        view = doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [source]
        view.Direction = App.Vector(0, 0, 1)
        view.XDirection = App.Vector(1, 0, 0)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.X, view.Y = 30, 40
        doc.recompute()
        deadline = time.monotonic() + 20
        while not view.getVisibleEdges() or "Up-to-date" not in view.State:
            self.assertLess(time.monotonic(), deadline, view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()
        return {"doc": doc, "source": source, "page": page, "view": view}

    @staticmethod
    def _snapshot(drawing):
        doc = drawing["doc"]
        result = {"objects": tuple((obj.Name, obj.TypeId, obj.Label) for obj in doc.Objects)}
        if "page" in drawing:
            result["views"] = tuple(obj.Name for obj in drawing["page"].Views)
            result["cosmetics"] = tuple(vertex.Tag for vertex in drawing["view"].CosmeticVertexes)
            result["source_volume"] = drawing["source"].Shape.Volume
            result["source_links"] = tuple((obj.Document.Name, obj.Name)
                                           for obj in drawing["view"].Source)
            result["position"] = (drawing["view"].X.Value, drawing["view"].Y.Value)
        return result

    def _checkCreation(self, api, scenario, unicode_owner=False):
        owner_name = "CreationOwner_測定_é" if unicode_owner else "CreationOwner"
        owner = self._drawing(owner_name)
        self.assertEqual(owner["doc"].Name, owner_name)
        if scenario == "empty":
            other_doc = App.newDocument("CreationOther")
            self.addCleanup(App.closeDocument, other_doc.Name)
            other = {"doc": other_doc}
        else:
            other = self._drawing("CreationOther")
            self.assertEqual(owner["page"].Name, other["page"].Name)
            self.assertEqual(owner["view"].Name, other["view"].Name)
        active = owner["doc"] if scenario == "active" else other["doc"]
        App.setActiveDocument(active.Name)
        before_other = self._snapshot(other)
        before_owner = self._snapshot(owner)
        view = owner["view"]
        result = None
        error = None
        try:
            if api == "makeLeader":
                result = TechDraw.makeLeader(view, [App.Vector(40, 50, 0), App.Vector(50, 60, 0)])
            elif api == "makeExtentDim":
                result = TechDraw.makeExtentDim(view, [], 0)
            else:
                result = getattr(TechDraw, api)(view, "Distance", App.Vector(0, 0, 0),
                                               App.Vector(10, 0, 0))
        except Exception as exc:
            error = exc
        self.assertEqual(App.activeDocument().Name, active.Name)
        self.assertEqual(self._snapshot(other), before_other)
        self.assertIsNone(error, f"{api} failed for the explicit parent view: {error}")

        type_name = "TechDraw::DrawLeaderLine" if api == "makeLeader" else "TechDraw::DrawViewDimension"
        created = [obj for obj in owner["doc"].Objects if obj.isDerivedFrom(type_name)]
        self.assertEqual(len(created), 1)
        created = created[0]
        self.assertEqual(created.Document.Name, owner["doc"].Name)
        self.assertEqual(created.findParentPage(), owner["page"])
        if api == "makeDistanceDim3d":
            self.assertIsNone(result)
        else:
            self.assertEqual(result.Document.Name, owner["doc"].Name)
            self.assertEqual(result.Name, created.Name)
        if api == "makeLeader":
            self.assertEqual(created.LeaderParent, view)
            self.assertEqual(len(created.WayPoints), 2)
        else:
            owner["doc"].recompute()
            self.assertAlmostEqual(created.getRawValue(), 10)
            self.assertTrue(created.References2D)
            for referenced, _sub_names in created.References2D:
                self.assertEqual((referenced.Document.Name, referenced.Name),
                                 (owner["doc"].Name, view.Name))

        after_owner = self._snapshot(owner)
        cosmetic_count = 2 if api in ("makeDistanceDim", "makeDistanceDim3d") else 0
        self.assertEqual(len(after_owner["cosmetics"]), len(before_owner["cosmetics"]) + cosmetic_count)
        self.assertEqual(after_owner["source_volume"], before_owner["source_volume"])
        self.assertEqual(after_owner["source_links"], before_owner["source_links"])
        self.assertEqual(after_owner["position"], before_owner["position"])
        self.assertEqual(App.activeDocument().Name, active.Name)
        self.assertEqual(self._snapshot(other), before_other)

    def testLeaderOwnerActive(self):
        self._checkCreation("makeLeader", "active")

    def testExtentOwnerActive(self):
        self._checkCreation("makeExtentDim", "active")

    def testDistanceOwnerActive(self):
        self._checkCreation("makeDistanceDim", "active")

    def testDistance3dOwnerActive(self):
        self._checkCreation("makeDistanceDim3d", "active")

    def testLeaderInactiveOwner(self):
        self._checkCreation("makeLeader", "colliding")

    def testExtentInactiveOwner(self):
        self._checkCreation("makeExtentDim", "colliding")

    def testDistanceInactiveOwner(self):
        self._checkCreation("makeDistanceDim", "colliding")

    def testDistance3dInactiveOwner(self):
        self._checkCreation("makeDistanceDim3d", "colliding")

    def testLeaderWithEmptyActiveDocument(self):
        self._checkCreation("makeLeader", "empty")

    def testExtentWithEmptyActiveDocument(self):
        self._checkCreation("makeExtentDim", "empty")

    def testDistanceWithEmptyActiveDocument(self):
        self._checkCreation("makeDistanceDim", "empty")

    def testDistance3dWithEmptyActiveDocument(self):
        self._checkCreation("makeDistanceDim3d", "empty")

    def testLeaderUnicodeOwnerActive(self):
        self._checkCreation("makeLeader", "active", unicode_owner=True)

    def testExtentUnicodeOwnerActive(self):
        self._checkCreation("makeExtentDim", "active", unicode_owner=True)

    def testDistanceUnicodeOwnerActive(self):
        self._checkCreation("makeDistanceDim", "active", unicode_owner=True)

    def testDistance3dUnicodeOwnerActive(self):
        self._checkCreation("makeDistanceDim3d", "active", unicode_owner=True)
