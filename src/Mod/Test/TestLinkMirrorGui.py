# SPDX-License-Identifier: LGPL-2.1-or-later
"""The "Mirror link" action of the link context menu keeps a non-uniform scale."""

import unittest

import FreeCAD as App

_part_available = False
if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtGui, QtWidgets

    try:
        import Part  # noqa: F401

        _part_available = True
    except ImportError:
        pass


def _pump(count=10):
    for _ in range(count):
        QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(10)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
@unittest.skipUnless(_part_available, "Requires the Part module")
class TestLinkMirrorGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("LinkMirrorGui")
        self.doc.UndoMode = 1
        self.box = self.doc.addObject("Part::Box", "Box")
        self.link = self.doc.addObject("App::Link", "Link")
        self.link.LinkedObject = self.box
        self.doc.recompute()
        Gui.updateGui()

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def _treeWidget(self):
        for widget in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            if widget.metaObject().className() == "Gui::TreeWidget":
                return widget
        self.fail("No tree widget")

    def _treeItem(self, tree, label):
        iterator = QtWidgets.QTreeWidgetItemIterator(tree)
        while iterator.value():
            if iterator.value().text(0) == label:
                return iterator.value()
            iterator += 1
        self.fail("No tree item " + label)

    def _mirrorAction(self, trigger):
        """Opens the tree context menu of the link and returns whether "Mirror link" was
        checked, triggering it when asked."""
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.link.Name)
        _pump()
        tree = self._treeWidget()
        item = self._treeItem(tree, self.link.Label)
        tree.scrollToItem(item)

        def selected():
            return [selectedItem.text(0) for selectedItem in tree.selectedItems()]

        # The tree follows the selection on a timer; its context menu needs the selected item
        for _ in range(50):
            if selected() == [self.link.Label]:
                break
            _pump(1)
        self.assertEqual(selected(), [self.link.Label])
        center = tree.visualItemRect(item).center()
        text = QtCore.QCoreApplication.translate("QObject", "Mirror link")
        found = []
        errors = []
        timer = QtCore.QTimer(Gui.getMainWindow())

        def useMenu():
            menu = QtWidgets.QApplication.activePopupWidget()
            if menu is None:
                return
            timer.stop()
            try:
                action = next(action for action in menu.actions() if action.text() == text)
                found.append(action.isChecked())
                if trigger:
                    action.trigger()
            except BaseException as error:
                errors.append(repr(error))
            finally:
                menu.close()

        timer.timeout.connect(useMenu)
        timer.start(50)
        try:
            event = QtGui.QContextMenuEvent(
                QtGui.QContextMenuEvent.Mouse, center, tree.viewport().mapToGlobal(center)
            )
            QtWidgets.QApplication.sendEvent(tree.viewport(), event)
            _pump()
        finally:
            timer.stop()
            timer.deleteLater()
        self.assertFalse(errors, errors)
        self.assertEqual(len(found), 1, "no Mirror link action in the context menu")
        return found[0]

    def testMirrorKeepsNonUniformScale(self):
        self.link.ScaleVector = App.Vector(1, 2, 3)
        self.assertFalse(self._mirrorAction(trigger=True))
        self.assertEqual(self.link.ScaleVector, App.Vector(-1, -2, -3))
        self.assertTrue(self._mirrorAction(trigger=True))
        self.assertEqual(self.link.ScaleVector, App.Vector(1, 2, 3))

    def testMirroredScaleVectorIsShownChecked(self):
        # Mirrored about one plane: Scale cannot hold it and stays 1
        self.link.ScaleVector = App.Vector(-1, 1, 1)
        self.assertEqual(self.link.Scale, 1.0)
        self.assertTrue(self._mirrorAction(trigger=True))
        self.assertEqual(self.link.ScaleVector, App.Vector(1, -1, -1))
        self.assertFalse(self._mirrorAction(trigger=False))

    def testMirrorUniformScale(self):
        self.link.Scale = 2.0
        self.assertFalse(self._mirrorAction(trigger=True))
        self.assertEqual(self.link.Scale, -2.0)
        self.assertEqual(self.link.ScaleVector, App.Vector(-2, -2, -2))
        self.doc.undo()
        self.assertEqual(self.link.Scale, 2.0)
        self.assertEqual(self.link.ScaleVector, App.Vector(2, 2, 2))
