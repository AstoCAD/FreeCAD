# SPDX-License-Identifier: LGPL-2.1-or-later
"""An active object reached through a link to another document is shown in the tree (issue #17904)."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the document tree")
class TestTreeLinkActiveObjectGui(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.docs = []
        self.addCleanup(self._cleanup)

        self.partDoc = self._newDocument("TreeLinkActivePart17904")
        self.part = self.partDoc.addObject("App::Part", "Part")
        self.body = self.partDoc.addObject("PartDesign::Body", "Body")
        self.part.addObject(self.body)
        self.partDoc.recompute()
        self.partDoc.saveAs(os.path.join(self.tempdir, "TreeLinkActivePart17904.FCStd"))

        self.asmDoc = self._newDocument("TreeLinkActiveAsm17904")
        self.asmDoc.saveAs(os.path.join(self.tempdir, "TreeLinkActiveAsm17904.FCStd"))
        self.link = self.asmDoc.addObject("App::Link", "Link")
        self.link.setLink(self.part)
        self.asmDoc.recompute()
        Gui.setActiveDocument(self.asmDoc.Name)
        self._events(200)

        self.trees = [
            tree
            for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget)
            if tree.inherits("Gui::TreeWidget")
        ]
        self.assertTrue(self.trees)

    def _newDocument(self, name):
        doc = App.newDocument(name)
        self.docs.append(doc.Name)
        return doc

    def _cleanup(self):
        for name in reversed(self.docs):
            if name in App.listDocuments():
                App.closeDocument(name)
        self._events(200)
        shutil.rmtree(self.tempdir, ignore_errors=True)

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _bodyItemStatesUnderLink(self):
        """Return whether each tree item of the body below the link in the
        assembly document is highlighted.

        The state is read during the traversal: the item wrappers are not owned
        by Python and become invalid once their parent wrappers are released."""
        states = []
        for tree in self.trees:
            for i in range(tree.topLevelItemCount()):
                top = tree.topLevelItem(i)
                if top.text(0) != self.asmDoc.Label:
                    continue
                stack = [top]
                while stack:
                    item = stack.pop()
                    for j in range(item.childCount()):
                        child = item.child(j)
                        if child.text(0) == self.body.Label:
                            states.append(self._isHighlighted(child))
                        stack.append(child)
        return states

    @staticmethod
    def _isHighlighted(item):
        return item.font(0).bold() or item.background(0).style() != QtCore.Qt.NoBrush

    def testActiveBodyThroughCollapsedLinkIsHighlighted(self):
        # The link item has never been expanded, so the body has no tree item
        # in the assembly document yet.
        self.assertEqual(self._bodyItemStatesUnderLink(), [])

        view = Gui.getDocument(self.asmDoc.Name).ActiveView
        view.setActiveObject("pdbody", self.body)
        self._events(200)
        try:
            self.assertEqual(view.getActiveObject("pdbody"), self.body)
            states = self._bodyItemStatesUnderLink()
            self.assertTrue(states, "The active body has no item below the link")
            self.assertTrue(any(states), "The active body is not highlighted below the link")
        finally:
            view.setActiveObject("pdbody", None)
            self._events(200)

        self.assertFalse(any(self._bodyItemStatesUnderLink()))
