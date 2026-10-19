# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression tests for Link tree ownership after deletion and undo."""

import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets


class TestTreeLinkDeletionGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TreeDeleteUndoControl")
        self.doc.UndoMode = 1
        self.child_label = self.doc.Name + "_Child"
        timeout = App.ParamGet("User parameter:BaseApp/Preferences/TreeView").GetInt(
            "StatusTimeout", 100)
        self.settle_ms = max(250, timeout + 100)

    def tearDown(self):
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    @staticmethod
    def process_events(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def paths(self):
        results = []
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            paths = []
            for item in tree.findItems(
                    self.child_label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0):
                path = []
                while item is not None:
                    path.insert(0, item.text(0))
                    item = item.parent()
                paths.append(tuple(path))
            if paths:
                results.append(tuple(sorted(paths)))
        return tuple(results)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self.process_events()
        return True

    def check_case(self, kind, separated, gui_undo):
        child = self.doc.addObject("App::FeaturePython", "Child")
        child.Label = self.child_label
        if kind == "group":
            owners = [self.doc.addObject("App::DocumentObjectGroup", "Owner")]
            owners[0].addObject(child)
        elif kind == "link":
            owners = [self.doc.addObject("App::Link", "Owner")]
            owners[0].setLink(child)
            owners[0].LinkClaimChild = True
        else:
            group = self.doc.addObject("App::DocumentObjectGroup", "Group")
            group.addObject(child)
            link = self.doc.addObject("App::Link", "Link")
            link.setLink(group)
            owners = [group, link]
        for owner in owners:
            owner.Label = self.doc.Name + "_" + owner.Name
        self.doc.recompute()
        self.process_events(self.settle_ms)
        for tree in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget):
            for owner in owners:
                for item in tree.findItems(
                        owner.Label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0):
                    item.setExpanded(True)
        self.assertTrue(self.wait_for(lambda: self.paths()))
        self.process_events(self.settle_ms)
        initial = self.paths()
        self.assertTrue(all(len(paths) == len(set(paths)) for paths in initial), initial)
        for owner in owners:
            self.assertIn(child, owner.ViewObject.claimChildren())
            self.assertTrue(any(path[-2] == owner.Label
                                for paths in initial for path in paths), initial)
        initial_claims = [[obj.Name for obj in owner.ViewObject.claimChildren()] for owner in owners]
        self.doc.clearUndos()
        self.doc.openTransaction("Delete tree child")
        self.doc.removeObject("Child")
        self.doc.commitTransaction()
        for cycle in range(2):
            self.assertIsNone(self.doc.getObject("Child"))
            self.assertFalse(self.paths(), "Tree deletion must be synchronous")
            if separated:
                self.process_events(self.settle_ms)
            # The immediate variant deliberately pumps no events after deletion.
            if gui_undo:
                Gui.runCommand("Std_Undo")
            else:
                self.doc.undo()
            restored = self.doc.getObject("Child")
            self.assertIsNotNone(restored)
            self.assertEqual([[obj.Name for obj in owner.ViewObject.claimChildren()]
                              for owner in owners], initial_claims)
            self.assertTrue(self.wait_for(lambda: self.paths() == initial),
                            "Restored tree differs: " + repr((initial, self.paths())))
            self.process_events(self.settle_ms)
            self.assertEqual(self.paths(), initial, "Delayed refresh created a duplicate or moved child")
            if gui_undo:
                Gui.runCommand("Std_Redo")
            else:
                self.doc.redo()
        self.assertIsNone(self.doc.getObject("Child"))
        self.assertFalse(self.paths())


def make_case(kind, separated, gui_undo):
    def case(self):
        self.check_case(kind, separated, gui_undo)
    return case


for kind in ("link", "linked_group"):
    for separated in (False, True):
        for gui_undo in (False, True):
            name = "test_%s_%s_%s" % (
                kind, "separated" if separated else "immediate", "gui" if gui_undo else "app")
            setattr(TestTreeLinkDeletionGui, name, make_case(kind, separated, gui_undo))
if __name__ == "__main__":
    unittest.main()
