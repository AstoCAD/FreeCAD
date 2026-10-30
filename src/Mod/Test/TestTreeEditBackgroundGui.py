# SPDX-License-Identifier: LGPL-2.1-or-later
"""Leaving edit mode restores the tree highlight of an active object (issue #15819)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the document tree")
class TestTreeEditBackgroundGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TreeEditBackground15819")
        self.addCleanup(self._cleanup)
        self.part = self.doc.addObject("App::Part", "Part")
        self.doc.recompute()
        self._events(200)
        self.trees = [
            tree
            for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget)
            if tree.inherits("Gui::TreeWidget")
        ]
        self.assertTrue(self.trees)

    def _cleanup(self):
        gdoc = Gui.getDocument(self.doc.Name)
        if gdoc and gdoc.getInEdit():
            gdoc.resetEdit()
        App.closeDocument(self.doc.Name)
        self._events(200)

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _items(self, obj):
        items = []
        for tree in self.trees:
            items += tree.findItems(obj.Label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)
        self.assertTrue(items)
        return items

    def _backgrounds(self, obj):
        result = []
        for item in self._items(obj):
            brush = item.background(0)
            if brush.style() == QtCore.Qt.NoBrush:
                result.append(None)
            else:
                result.append(brush.color().rgba())
        return result

    def _edit_and_reset(self, obj):
        gdoc = Gui.getDocument(self.doc.Name)
        gdoc.setEdit(obj, 1)  # Transform
        self._events(200)
        self.assertIsNotNone(gdoc.getInEdit())
        gdoc.resetEdit()
        self._events(200)
        self.assertIsNone(gdoc.getInEdit())

    def testActivePartKeepsHighlightAfterTransform(self):
        view = Gui.getDocument(self.doc.Name).ActiveView
        view.setActiveObject("part", self.part)
        self._events(200)
        active = self._backgrounds(self.part)
        self.assertNotIn(None, active)

        self._edit_and_reset(self.part)

        self.assertEqual(self._backgrounds(self.part), active)
        view.setActiveObject("part", None)
        self._events(200)
        self.assertEqual(set(self._backgrounds(self.part)), {None})

    def testInactiveObjectHasNoBackgroundAfterTransform(self):
        self._edit_and_reset(self.part)
        self.assertEqual(set(self._backgrounds(self.part)), {None})
