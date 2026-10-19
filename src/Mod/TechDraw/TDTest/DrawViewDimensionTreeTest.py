# SPDX-License-Identifier: LGPL-2.1-or-later

import time
import unittest

import FreeCAD
import FreeCADGui
import Part  # noqa: F401
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewDimensionTreeTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDimensionTree")
        self.doc.UndoMode = 1
        self.page = createPageWithSVGTemplate(self.doc)
        self.source = self.doc.addObject("Part::Box", "Box")
        self.views = []
        for suffix in ("A", "B"):
            view = self.doc.addObject("TechDraw::DrawViewPart", "View" + suffix)
            view.Label = self.doc.Name + "_View" + suffix
            self.page.addView(view)
            view.Source = [self.source]
            view.Direction = FreeCAD.Vector(0, 0, 1)
            self.views.append(view)
        self.doc.recompute()
        self.assertTrue(self._waitUntil(
            lambda: all(view.getVisibleEdges() and "Up-to-date" in view.State
                        for view in self.views), timeout=15))
        if self._testMethodName != "testCreationBeforeShowingPage":
            self.page.ViewObject.show()
            self.assertTrue(self._waitUntil(lambda: bool(self._pageWidgets())))
        self._processEvents(150)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    @staticmethod
    def _processEvents(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _waitUntil(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._processEvents()
        return True

    def _pageWidgets(self):
        return [widget for widget in FreeCADGui.getMainWindow().findChildren(
            QtWidgets.QGraphicsView) if widget.objectName() == self.page.Name + "View"]

    def _visiblePageWidgets(self):
        window = FreeCADGui.getMainWindow()
        return [widget for widget in self._pageWidgets() if widget.isVisibleTo(window)]

    @staticmethod
    def _treePaths(label):
        results = []
        for tree in FreeCADGui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            paths = []
            for item in tree.findItems(
                    label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0):
                path = []
                while item is not None:
                    path.insert(0, item.text(0))
                    item = item.parent()
                paths.append(path)
            if paths:
                results.append(paths)
        return results

    def _assertTreeParent(self, label, owner):
        def matches():
            trees = self._treePaths(label)
            return bool(trees) and all(
                len(paths) == 1 and len(paths[0]) >= 2 and paths[0][-2] == owner.Label
                for paths in trees)

        self.assertTrue(self._waitUntil(matches),
                        "Incorrect or duplicate tree ownership: " + repr(self._treePaths(label)))
        # A second event turn must not recreate a stale owner or duplicate item.
        self._processEvents(100)
        self.assertTrue(matches(), repr(self._treePaths(label)))

    def _modelSnapshot(self):
        return {
            "source": (tuple(self.source.State), self.source.Shape.Volume,
                       self.source.Shape.Area),
            "views": [
                (tuple(view.State), tuple(obj.Name for obj in view.Source),
                 tuple(view.Direction), view.X.Value, view.Y.Value,
                 view.Rotation.Value, view.Scale)
                for view in self.views
            ],
        }

    def _createDimension(self):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "Dimension")
        dimension.Label = self.doc.Name + "_Dimension"
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(self.views[0], "Edge0")]
        self.doc.recompute()
        self._processEvents(150)
        return dimension

    def _prepareExistingDimension(self):
        dimension = self._createDimension()
        # Creation is tested separately. Establish an existing correct tree with
        # a standard GUI refresh to isolate subsequent ownership transitions.
        owner = self.views[0]
        owner.ViewObject.ShowInTree = owner.ViewObject.ShowInTree
        self._assertTreeParent(dimension.Label, owner)
        self.doc.clearUndos()
        return dimension

    def testCreationWithoutBalloon(self):
        """Creating a dimension refreshes its owner without another child doing so."""
        previous = self._modelSnapshot()
        dimension = self._createDimension()
        self._assertTreeParent(dimension.Label, self.views[0])
        self.assertEqual(self._modelSnapshot(), previous)

    def testCreationBeforeShowingPage(self):
        """Tree ownership is correct before the page has ever been shown."""
        self.assertFalse(self._visiblePageWidgets())
        previous = self._modelSnapshot()
        dimension = self._createDimension()
        self._assertTreeParent(dimension.Label, self.views[0])
        self.assertEqual(self._modelSnapshot(), previous)
        self.assertFalse(self._visiblePageWidgets())

    def testDeletionUndoRedo(self):
        """Undoing dimension deletion restores the tree parent on every cycle."""
        dimension = self._prepareExistingDimension()
        name, label = dimension.Name, dimension.Label
        previous = self._modelSnapshot()
        self.doc.openTransaction("Delete dimension")
        self.doc.removeObject(name)
        self.doc.commitTransaction()
        for unused in range(2):
            self.assertTrue(self._waitUntil(lambda: not self._treePaths(label)))
            self.assertIsNone(self.doc.getObject(name))
            self.assertEqual(self._modelSnapshot(), previous)
            self.doc.undo()
            self.assertIsNotNone(self.doc.getObject(name))
            self._assertTreeParent(label, self.views[0])
            self.assertEqual(self._modelSnapshot(), previous)
            self.doc.redo()
        self.assertTrue(self._waitUntil(lambda: not self._treePaths(label)))
        self.doc.undo()
        self._assertTreeParent(label, self.views[0])
        self.assertEqual(self._modelSnapshot(), previous)

    def _exerciseReferenceChanges(self, close_page):
        dimension = self._prepareExistingDimension()
        label = dimension.Label
        if close_page:
            self.assertTrue(self._visiblePageWidgets())
            self.page.ViewObject.Visibility = False
            self.assertTrue(self._waitUntil(
                lambda: not self.page.ViewObject.Visibility and not self._visiblePageWidgets()))
        previous = self._modelSnapshot()

        self.doc.openTransaction("Change dimension owner")
        dimension.References2D = [(self.views[1], "Edge0")]
        self.doc.commitTransaction()
        self._assertTreeParent(label, self.views[1])
        self.assertEqual(self._modelSnapshot(), previous)
        self.doc.undo()
        self._assertTreeParent(label, self.views[0])
        self.assertEqual(self._modelSnapshot(), previous)
        self.doc.redo()
        self._assertTreeParent(label, self.views[1])
        self.assertEqual(self._modelSnapshot(), previous)

        self.doc.openTransaction("Clear dimension references")
        dimension.References2D = []
        self.doc.commitTransaction()
        self._assertTreeParent(label, self.doc)
        self.assertEqual(self._modelSnapshot(), previous)
        self.doc.undo()
        self._assertTreeParent(label, self.views[1])
        self.assertEqual(self._modelSnapshot(), previous)
        self.doc.redo()
        self._assertTreeParent(label, self.doc)
        self.doc.undo()
        self._assertTreeParent(label, self.views[1])

        self.doc.openTransaction("Add multiple subreferences")
        dimension.References2D = [(self.views[1], ("Edge0", "Edge1"))]
        self.doc.commitTransaction()
        self._assertTreeParent(label, self.views[1])
        self.doc.undo()
        self._assertTreeParent(label, self.views[1])
        self.doc.redo()
        self._assertTreeParent(label, self.views[1])
        self.assertEqual(self._modelSnapshot(), previous)
        if close_page:
            self.assertFalse(self.page.ViewObject.Visibility)
            self.assertFalse(self._visiblePageWidgets())

    def testReferenceChangesUndoRedo(self):
        """Old and new tree owners refresh after reference changes and undo/redo."""
        self._exerciseReferenceChanges(close_page=False)

    def testClosedPageReferenceChanges(self):
        """Tree ownership updates when the page tab is closed, including duplicates."""
        self._exerciseReferenceChanges(close_page=True)
