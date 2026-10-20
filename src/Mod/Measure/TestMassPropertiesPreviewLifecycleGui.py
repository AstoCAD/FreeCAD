# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Mass Properties preview follows the lifetime of its exact owner task."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Materials
import Measure
import Part
from PySide import QtCore, QtWidgets


class TestMassPropertiesPreviewLifecycleGui(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous = previous.Name if previous else None
        self.doc = App.newDocument("MassPreviewLifecycleRegression")
        self.documents = [self.doc.Name]
        self.owner_gui = Gui.getDocument(self.doc.Name)
        self.strong_widgets = [self.owner_gui]
        self.observers = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for observer in self.observers:
            App.removeDocumentObserver(observer)
        Gui.Control.closeDialog(self.owner_gui)
        Gui.Selection.clearSelection()
        for name in reversed(self.documents):
            if name in App.listDocuments():
                App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    @staticmethod
    def _pump():
        Gui.updateGui()
        QtCore.QCoreApplication.processEvents()

    @staticmethod
    def _objects(doc):
        return {(obj.Name, obj.TypeId) for obj in doc.Objects}

    @staticmethod
    def _snapshot(doc, name):
        obj = doc.getObject(name)
        if obj is None:
            return None
        state = {"type": obj.TypeId, "label": obj.Label,
                 "visible": obj.ViewObject.Visibility, "show_in_tree": obj.ViewObject.ShowInTree}
        if "LifecycleMarker" in obj.PropertiesList:
            state["marker"] = obj.LifecycleMarker
        if "Shape" in obj.PropertiesList:
            state["volume"] = obj.Shape.Volume
        return state

    @staticmethod
    def _sample(doc):
        material = Materials.Material()
        material.Name = "Preview lifecycle material"
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        sample = doc.addObject("Part::Feature", "Sample")
        sample.Shape = Part.makeBox(10, 10, 10)
        sample.ShapeMaterial = material
        doc.recompute()
        return sample

    @staticmethod
    def _sentinel(doc, name):
        sentinel = doc.addObject("Part::Feature", name)
        sentinel.Shape = Part.makeBox(7, 8, 9)
        sentinel.Label = "User replacement"
        sentinel.addProperty("App::PropertyString", "LifecycleMarker")
        sentinel.LifecycleMarker = "user-owned-data"
        sentinel.ViewObject.Visibility = False
        sentinel.ViewObject.ShowInTree = True
        return sentinel

    def _retainTask(self):
        task = Gui.Control.activeTaskDialog(self.owner_gui)
        self.assertIsNotNone(task, "The owner document's Mass Properties task must be open")
        self.strong_widgets.append(task)
        self.contents = task.getDialogContent()
        self.strong_widgets.extend(self.contents)
        panel = self.contents[0]
        while True:
            parent = panel.parentWidget()
            self.assertIsNotNone(parent)
            self.strong_widgets.append(parent)
            if isinstance(parent, QtWidgets.QStackedWidget):
                break
            panel = parent
        buttons = panel.findChild(QtWidgets.QDialogButtonBox)
        self.assertIsNotNone(buttons)
        self.strong_widgets.append(buttons)
        self.strong_widgets.extend(buttons.buttons())
        self.close_button = buttons.button(QtWidgets.QDialogButtonBox.Abort)
        self.reset_button = buttons.button(QtWidgets.QDialogButtonBox.Reset)
        self.assertIsNotNone(self.close_button)
        self.assertIsNotNone(self.reset_button)

    def _taskWidget(self, kind, name):
        for content in self.contents:
            widget = content.findChild(kind, name)
            if widget is not None:
                self.strong_widgets.append(widget)
                return widget
        self.fail("Actual task widget not found: " + name)

    def _start(self, sample=None):
        if sample is None:
            sample = self._sample(self.doc)
        App.setActiveDocument(self.doc.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sample)
        Gui.runCommand("Std_MassProperties")
        self._pump()
        self._retainTask()
        previews = [obj for obj in self.doc.Objects if obj.TypeId == "Measure::Result"]
        self.assertEqual(len(previews), 1, "A real initial preview must exist")
        return sample, previews[0].Name

    def _assertClosed(self):
        self.assertFalse(Gui.Control.activeTaskDialog(self.owner_gui))

    def testOrdinaryCloseRemovesPreview(self):
        sample, preview_name = self._start()
        before = self._snapshot(self.doc, sample.Name)
        self.close_button.click()
        self._pump()
        self._assertClosed()
        self.assertIsNone(self.doc.getObject(preview_name))
        self.assertEqual(self._snapshot(self.doc, sample.Name), before)

    def testClosePreservesSameNameReplacement(self):
        sample, preview_name = self._start()
        before_sample = self._snapshot(self.doc, sample.Name)
        self.doc.removeObject(preview_name)
        replacement = self._sentinel(self.doc, preview_name)
        self.assertEqual(replacement.Name, preview_name)
        before = self._snapshot(self.doc, preview_name)
        self.close_button.click()
        self._pump()
        self._assertClosed()
        self.assertEqual(self._snapshot(self.doc, preview_name), before,
                         "The replacement has the same name but is not the owned preview")
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)

    def testInactiveOwnerCloseRemovesOnlyOwnedPreview(self):
        sample, preview_name = self._start()
        before_sample = self._snapshot(self.doc, sample.Name)
        other = App.newDocument("MassPreviewLifecycleOther")
        self.documents.append(other.Name)
        sentinel = self._sentinel(other, preview_name)
        before_other = self._snapshot(other, sentinel.Name)
        App.setActiveDocument(other.Name)
        Gui.Control.closeDialog(self.owner_gui)
        self._pump()
        self._assertClosed()
        self.assertEqual(App.activeDocument().Name, other.Name)
        self.assertEqual(self._snapshot(other, sentinel.Name), before_other)
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)
        self.assertIsNone(self.doc.getObject(preview_name),
                          "Closing the inactive owner's task must remove its preview")

    def testControlCloseRemovesPreview(self):
        sample, preview_name = self._start()
        before_sample = self._snapshot(self.doc, sample.Name)
        Gui.Control.closeDialog(self.owner_gui)
        self._pump()
        self._assertClosed()
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)
        self.assertIsNone(self.doc.getObject(preview_name),
                          "Direct task destruction must remove the owned preview")

    def testResetCancelsQueuedPreview(self):
        sample, _ = self._start()
        before_sample = self._snapshot(self.doc, sample.Name)
        combo = self._taskWidget(QtWidgets.QComboBox, "unitsComboBox")
        # Queue a preview update, then Reset before processing that callback.
        combo.setCurrentIndex(1 if combo.currentIndex() == 0 else 0)
        self.reset_button.click()
        self._pump()
        still_open = bool(Gui.Control.activeTaskDialog(self.owner_gui))
        previews_after_reset = [obj.Name for obj in self.doc.Objects if obj.TypeId == "Measure::Result"]
        selection_after_reset = len(Gui.Selection.getSelection())
        if still_open:
            self.close_button.click()
            self._pump()
        self._assertClosed()
        self.assertTrue(still_open, "Reset must leave the task open")
        self.assertEqual(selection_after_reset, 0)
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)
        self.assertEqual(previews_after_reset, [], "A cancelled callback must not recreate the preview")

    def _checkCreationObserver(self, closes_task):
        sample = self._sample(self.doc)
        before = self._objects(self.doc)
        before_sample = self._snapshot(self.doc, sample.Name)
        owner_name = self.doc.Name
        owner_gui = self.owner_gui
        record = {"created": [], "errors": []}

        class Observer:
            def slotCreatedObject(self, obj):
                if obj.Document.Name != owner_name or obj.TypeId != "Measure::Result":
                    return
                record["created"].append(obj.Name)
                if closes_task:
                    try:
                        Gui.Control.closeDialog(owner_gui)
                    except Exception as exc:
                        record["errors"].append(str(exc))

        observer = Observer()
        self.observers.append(observer)
        App.addDocumentObserver(observer)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sample)
        Gui.runCommand("Std_MassProperties")
        self._pump()
        open_after_creation = bool(Gui.Control.activeTaskDialog(self.owner_gui))
        if not closes_task:
            self._retainTask()
            self.close_button.click()
            self._pump()
        self._assertClosed()
        self.assertEqual(record["errors"], [])
        self.assertEqual(len(record["created"]), 1)
        self.assertEqual(open_after_creation, not closes_task)
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)
        self.assertEqual(self._objects(self.doc), before,
                         "Closing during addObject must not leave the newly created preview orphaned")

    def testCreationObserverWithoutClosure(self):
        self._checkCreationObserver(False)

    def testCreationObserverClosesTask(self):
        self._checkCreationObserver(True)

    def _checkDeletionObserver(self, closes_task):
        sample = self._sample(self.doc)
        other = App.newDocument("MassPreviewDeletionObserverOther")
        self.documents.append(other.Name)
        other_sample = self._sample(other)
        before_owner, before_other = self._objects(self.doc), self._objects(other)
        before_sample = self._snapshot(self.doc, sample.Name)
        before_other_sample = self._snapshot(other, other_sample.Name)
        _, preview_name = self._start(sample)
        owner_name = self.doc.Name
        owner_gui = self.owner_gui
        record = {"deleted": [], "errors": []}

        class Observer:
            def slotDeletedObject(self, obj):
                if obj.Document.Name != owner_name or obj.Name != preview_name:
                    return
                record["deleted"].append((obj.Name, obj.TypeId))
                if closes_task:
                    try:
                        Gui.Control.closeDialog(owner_gui)
                    except Exception as exc:
                        record["errors"].append(str(exc))

        observer = Observer()
        self.observers.append(observer)
        App.addDocumentObserver(observer)
        # Keep the old selection: clearing it would delete the preview before
        # tryUpdate reaches its cross-document cleanup branch.
        App.setActiveDocument(other.Name)
        self.assertIsNotNone(self.doc.getObject(preview_name))
        Gui.Selection.addSelection(other_sample)
        self._pump()
        open_after_refresh = bool(Gui.Control.activeTaskDialog(self.owner_gui))
        after_owner, after_other = self._objects(self.doc), self._objects(other)
        active_after_refresh = App.activeDocument().Name
        Gui.Control.closeDialog(self.owner_gui)
        self._pump()
        self._assertClosed()
        self.assertEqual(record["errors"], [])
        self.assertEqual(record["deleted"], [(preview_name, "Measure::Result")],
                         "Cross-document refresh must remove the old preview and reach its observer")
        self.assertEqual(open_after_refresh, not closes_task)
        self.assertEqual(active_after_refresh, other.Name)
        self.assertEqual(after_owner, before_owner)
        if closes_task:
            self.assertEqual(after_other, before_other,
                             "A cancelled task must not create a preview in the new document")
        else:
            new_objects = after_other - before_other
            self.assertEqual(len(new_objects), 1)
            self.assertEqual(next(iter(new_objects))[1], "Measure::Result")
        self.assertEqual(self._objects(self.doc), before_owner)
        self.assertEqual(self._objects(other), before_other)
        self.assertEqual(self._snapshot(self.doc, sample.Name), before_sample)
        self.assertEqual(self._snapshot(other, other_sample.Name), before_other_sample)

    def testCrossDocumentRefreshMovesPreview(self):
        self._checkDeletionObserver(False)

    def testDeletionObserverClosesTaskDuringRefresh(self):
        self._checkDeletionObserver(True)
