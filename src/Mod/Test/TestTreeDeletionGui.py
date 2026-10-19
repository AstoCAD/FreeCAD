# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression coverage for deletion of a cached claimed child.

The reverse-claim proxy imitates providers
whose children refer to their owner instead of an owner-side Group property.
"""

import traceback
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui


class ReverseClaimView:
    def __init__(self, view):
        self.Object = view.Object
        view.Proxy = self

    def attach(self, view):
        self.Object = view.Object

    def claimChildren(self):
        return sorted(
            (obj for obj in self.Object.Document.Objects
             if "Owners" in obj.PropertiesList and self.Object in obj.Owners),
            key=lambda obj: obj.Sequence)


class TestTreeDeletionGui(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("ClaimedChildCache")
        self.doc.UndoMode = 1
        self.delay = max(150, App.ParamGet(
            "User parameter:BaseApp/Preferences/TreeView").GetInt("StatusTimeout", 100) + 60)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def pump(self, milliseconds=None):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(self.delay if milliseconds is None else milliseconds, loop.quit)
        loop.exec_()

    @staticmethod
    def rows(label):
        return [(tree, item)
                for tree in Gui.getMainWindow().findChildren(QtGui.QTreeWidget)
                for item in tree.findItems(
                    label, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)]

    @classmethod
    def paths(cls, label):
        result = []
        for _tree, item in cls.rows(label):
            path = []
            while item is not None:
                path.insert(0, item.text(0))
                item = item.parent()
            result.append(path)
        return result

    def refresh(self, owners):
        for owner in owners:
            owner.ViewObject.ShowInTree = owner.ViewObject.ShowInTree
        self.pump()

    def makeScenario(self, two_owners=False, group=False):
        owners = []
        for index in range(2 if two_owners else 1):
            owner = self.doc.addObject(
                "App::DocumentObjectGroup" if group else "App::FeaturePython", "Owner")
            owner.Label = self.doc.Name + "_Owner" + str(index)
            if not group:
                ReverseClaimView(owner.ViewObject)
            owners.append(owner)
        children = []
        for sequence, name in enumerate(("First", "Target", "Last")):
            child = self.doc.addObject("App::FeaturePython", name)
            child.Label = self.doc.Name + "_" + name
            child.addProperty("App::PropertyInteger", "Sequence")
            child.Sequence = sequence
            if group:
                owners[0].addObject(child)
            else:
                child.addProperty("App::PropertyLinkList", "Owners")
                child.Owners = owners
            children.append(child)
        self.doc.recompute()
        self.refresh(owners)
        for owner in owners:
            for _tree, item in self.rows(owner.Label):
                item.setExpanded(True)
        self.pump()
        self.assertChildren(owners, [child.Label for child in children])
        self.doc.clearUndos()
        return owners, children

    def assertChildren(self, owners, labels):
        for owner in owners:
            rows = self.rows(owner.Label)
            self.assertTrue(rows, owner.Label)
            for _tree, item in rows:
                self.assertEqual([item.child(index).text(0)
                                  for index in range(item.childCount())], labels,
                                 (owner.Label, self.paths(labels[1]) if len(labels) > 1 else []))

    def checkUndo(self, two_owners=False, group=False, settled=False):
        owners, children = self.makeScenario(two_owners=two_owners, group=group)
        labels = [child.Label for child in children]
        name = children[1].Name
        sibling_names = (children[0].Name, children[2].Name)
        for cycle in range(2):
            if cycle == 0:
                self.doc.openTransaction("Delete claimed child")
                self.doc.removeObject(name)
                self.doc.commitTransaction()
            else:
                self.doc.redo()
            self.assertIsNone(self.doc.getObject(name))
            self.assertFalse(self.paths(labels[1]))
            if settled:
                self.pump()
            self.doc.undo()
            restored = self.doc.getObject(name)
            self.assertIsNotNone(restored)
            self.assertEqual([self.doc.getObject(name).Label for name in sibling_names],
                             [labels[0], labels[2]])
            if not group:
                self.assertEqual(restored.Owners, owners)
            # A valid notification after restoration must repair the hierarchy
            # even when the retained document-object pointer is unchanged.
            self.refresh(owners)
            self.assertChildren(owners, labels)
            self.assertTrue(all(path[-2] in [owner.Label for owner in owners]
                                for path in self.paths(labels[1])))

    def testImmediateReverseClaimUndo(self):
        self.checkUndo()

    def testSettledReverseClaimUndo(self):
        self.checkUndo(settled=True)

    def testImmediateTwoOwnersPreserveSiblingsAndOrder(self):
        self.checkUndo(two_owners=True)

    def testSettledTwoOwnersPreserveSiblingsAndOrder(self):
        self.checkUndo(two_owners=True, settled=True)

    def testImmediateGroupUndoControl(self):
        self.checkUndo(group=True)

    def testSettledGroupUndoControl(self):
        self.checkUndo(group=True, settled=True)

    def testOwnerRefreshReentersAfterChildRowRemoval(self):
        owners, children = self.makeScenario()
        owner, target = owners[0], children[1]
        label, name = target.Label, target.Name
        observations, errors, connections = [], [], []
        armed = [False]

        def rowsRemoved(_parent, _first, _last):
            if not armed[0] or self.paths(label):
                return
            # Disarm before pumping: a regression may insert/remove more rows.
            armed[0] = False
            try:
                before = [obj.Name for obj in owner.ViewObject.claimChildren()]
                owner.ViewObject.ShowInTree = owner.ViewObject.ShowInTree
                self.pump()
                observations.append({"claimed_before_refresh": before,
                                     "paths_after_refresh": self.paths(label),
                                     "model_present": self.doc.getObject(name) is not None})
            except Exception:
                errors.append(traceback.format_exc())

        class Observer:
            def slotDeletedObject(observer_self, provider):
                try:
                    if provider.Object != target:
                        return
                    armed[0] = True
                    # Gui observers run before Tree's deletion slot. Arm a Qt
                    # row-removal signal to pump at the later, precise boundary.
                    for tree in Gui.getMainWindow().findChildren(QtGui.QTreeWidget):
                        model = tree.model()
                        model.rowsRemoved.connect(rowsRemoved)
                        connections.append(model)
                except Exception:
                    errors.append(traceback.format_exc())

        observer = Observer()
        Gui.addDocumentObserver(observer)
        try:
            self.doc.openTransaction("Delete with reentrant owner notification")
            self.doc.removeObject(name)
            self.doc.commitTransaction()
            self.pump()
        finally:
            Gui.removeDocumentObserver(observer)
            for model in connections:
                model.rowsRemoved.disconnect(rowsRemoved)
        self.assertFalse(errors, errors)
        self.assertTrue(observations, "The after-row-removal deletion boundary was not reached")
        self.assertTrue(all(name in record["claimed_before_refresh"]
                            and record["model_present"] for record in observations), observations)
        self.assertTrue(all(not record["paths_after_refresh"] for record in observations), observations)
        self.assertIsNone(self.doc.getObject(name))
        self.assertFalse(self.paths(label), "A pending-deletion child was recreated in the tree")
