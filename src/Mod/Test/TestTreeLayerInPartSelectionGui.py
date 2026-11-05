# SPDX-License-Identifier: LGPL-2.1-or-later
"""Objects of a Draft layer whose layer container is inside a Std_Part can be
selected in the tree (issue #19374)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the document tree")
class TestTreeLayerInPartSelectionGui(unittest.TestCase):
    def setUp(self):
        from draftmake.make_layer import make_layer

        self.doc = App.newDocument("TreeLayerInPart19374")
        self.addCleanup(self._cleanup)
        Gui.setActiveDocument(self.doc.Name)

        self.box = self.doc.addObject("Part::Box", "Box")
        self.layer = make_layer("Layer19374")
        self.layer.Proxy.addObject(self.layer, self.box)
        self.container = self.layer.getParentGroup()
        self.part = self.doc.addObject("App::Part", "Part")
        self.part.addObject(self.container)
        self.doc.recompute()
        self._events(200)

        # The layer content is not part of the Std_Part: the Group link of a
        # layer is hidden, so the box stays outside the part's coordinate system.
        self.assertTrue(self.part.hasObject(self.layer))
        self.assertFalse(self.part.hasObject(self.box))

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        self._events(200)

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _findBoxItem(self):
        """Return (tree, item) of the box below Part > LayerContainer > Layer."""
        path = [self.part.Label, self.container.Label, self.layer.Label, self.box.Label]
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            if not tree.inherits("Gui::TreeWidget"):
                continue
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                if item.text(0) != self.doc.Label:
                    continue
                for label in path:
                    tree.expandItem(item)
                    self._events(50)
                    found = None
                    for j in range(item.childCount()):
                        if item.child(j).text(0) == label:
                            found = item.child(j)
                            break
                    item = found
                    if item is None:
                        break
                if item is not None:
                    return tree, item
        return None, None

    def testSelectLayerObjectInsidePart(self):
        tree, item = self._findBoxItem()
        self.assertIsNotNone(item, "The box has no tree item below the layer in the part")

        tree.clearSelection()
        Gui.Selection.clearSelection()
        item.setSelected(True)
        self._events(200)

        selection = Gui.Selection.getSelectionEx("", 0)
        self.assertEqual(
            [sel.Object.Name for sel in selection],
            [self.box.Name],
            "Selecting the box in the tree did not select it",
        )
