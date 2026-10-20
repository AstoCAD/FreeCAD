# SPDX-License-Identifier: LGPL-2.1-or-later
"""Mass Properties must allow native keys in other writable editors."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import MatGui
import Materials
import Measure
import Part
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class TestMassPropertiesKeysGui(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        previous_name = previous.Name if previous else None

        def restoreActive():
            if previous_name in App.listDocuments():
                App.setActiveDocument(previous_name)

        self.addCleanup(restoreActive)
        self.doc = App.newDocument("MassPropertiesKeysRegression")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(Gui.Selection.clearSelection)
        self.addCleanup(Gui.Control.closeDialog, Gui.getDocument(self.doc.Name))
        self.strong_widgets = []
        self.editor = None
        self.addCleanup(self._closeEditor)

    @staticmethod
    def _pump():
        Gui.updateGui()
        QtCore.QCoreApplication.processEvents()
        QtTest.QTest.qWait(30)

    def _closeEditor(self):
        if self.editor is not None:
            self.editor.reject()
            self._pump()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    def _sample(self, name):
        material = Materials.Material()
        material.Name = "Native key test material"
        material.addPhysicalModel(Materials.UUIDs().Density)
        material.setPhysicalValue("Density", "1000 kg/m^3")
        obj = self.doc.addObject("Part::Feature", name)
        obj.Shape = Part.makeBox(10, 10, 10)
        obj.ShapeMaterial = material
        return obj

    def _taskWidget(self, kind, name):
        task = Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name))
        self.assertIsNotNone(task)
        self.strong_widgets.append(task)
        contents = task.getDialogContent()
        self.strong_widgets.extend(contents)
        for content in contents:
            widget = content.findChild(kind, name)
            if widget is not None:
                self.strong_widgets.append(widget)
                return widget
        self.fail("Actual Mass Properties widget not found: " + name)

    def _focus(self, widget):
        window = widget.window()
        self.strong_widgets.append(window)
        QtWidgets.QApplication.setActiveWindow(window)
        widget.setFocus(QtCore.Qt.OtherFocusReason)
        self._pump()
        self.assertTrue(widget.hasFocus())

    def _checkEditor(self, mass_open):
        sample = self._sample("Sample")
        self.doc.recompute()
        before = (sample.Label, sample.Shape.Volume, sample.ViewObject.Visibility)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(sample)
        if mass_open:
            Gui.runCommand("Std_MassProperties")
            self._pump()
            custom = self._taskWidget(QtWidgets.QLineEdit, "customEdit")
            self.assertTrue(custom.isReadOnly())
        # This existing nonmodal command remains active while a task is open.
        Gui.runCommand("Material_Edit")
        self._pump()
        candidates = [widget for widget in QtWidgets.QApplication.topLevelWidgets()
                      if widget.isVisible() and "MaterialsEditor" in widget.metaObject().className()
                      and widget.findChild(QtWidgets.QLineEdit, "editName") is not None]
        self.assertEqual(len(candidates), 1)
        self.editor = candidates[0]
        self.strong_widgets.append(self.editor)
        field = self.editor.findChild(QtWidgets.QLineEdit, "editName")
        self.strong_widgets.append(field)
        self.assertFalse(field.isReadOnly())
        self.assertTrue(field.isEnabled())
        self._focus(field)
        field.setText("seed")
        field.setCursorPosition(4)
        QtTest.QTest.keyClicks(field, "xyz")
        typed = field.text()
        field.setText("abcd")
        field.setCursorPosition(4)
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Backspace)
        self.assertEqual(field.text(), "abc")
        field.setText("abcd")
        field.setCursorPosition(1)
        QtTest.QTest.keyClick(field, QtCore.Qt.Key_Delete)
        self.assertEqual(field.text(), "acd")
        self.assertIsNotNone(self.doc.getObject(sample.Name))
        self.assertEqual((sample.Label, sample.Shape.Volume, sample.ViewObject.Visibility), before)
        self.assertEqual(typed, "seedxyz", "Ordinary native keys must reach the writable editor")

    def _checkObjectList(self, key):
        first, second = self._sample("First"), self._sample("Second")
        names = (first.Name, second.Name)
        self.doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(first)
        Gui.Selection.addSelection(second)
        Gui.runCommand("Std_MassProperties")
        self._pump()
        objects = self._taskWidget(QtWidgets.QListWidget, "objectList")
        self.assertEqual(objects.count(), 2)
        objects.setCurrentRow(0)
        self._focus(objects)
        QtTest.QTest.keyClick(objects, key)
        self._pump()
        self.assertEqual(objects.count(), 1)
        selected = Gui.Selection.getSelection()
        self.assertEqual(len(selected), 1)
        self.assertIn(selected[0].Name, names)
        for name in names:
            self.assertIsNotNone(self.doc.getObject(name))
            self.assertAlmostEqual(self.doc.getObject(name).Shape.Volume, 1000)

    def testMaterialEditorWithoutMassProperties(self):
        self._checkEditor(False)

    def testMaterialEditorWithMassProperties(self):
        self._checkEditor(True)

    def testObjectListDelete(self):
        self._checkObjectList(QtCore.Qt.Key_Delete)

    def testObjectListBackspace(self):
        self._checkObjectList(QtCore.Qt.Key_Backspace)

    def _taskScopeState(self, objects, names):
        task_open = bool(Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name)))
        return {
            "task_open": task_open,
            "list_count": objects.count() if task_open else None,
            "row": objects.currentRow() if task_open else None,
            "selection": sorted(obj.Name for obj in Gui.Selection.getSelection()),
            "previews": sorted(obj.Name for obj in self.doc.Objects if obj.TypeId == "Measure::Result"),
            "samples": {
                name: (self.doc.getObject(name).TypeId, self.doc.getObject(name).Label,
                       self.doc.getObject(name).ViewObject.Visibility,
                       self.doc.getObject(name).ViewObject.ShowInTree,
                       self.doc.getObject(name).Shape.Volume)
                for name in names if self.doc.getObject(name) is not None
            },
        }

    def _checkTaskKeyScope(self, key, removes_item=False):
        first, second = self._sample("First"), self._sample("Second")
        names = (first.Name, second.Name)
        self.doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(first)
        Gui.Selection.addSelection(second)
        Gui.runCommand("Std_MassProperties")
        self._pump()
        objects = self._taskWidget(QtWidgets.QListWidget, "objectList")
        self.assertEqual(objects.count(), 2)

        # Retain all ancestors and standard buttons even if a failing Escape
        # closes the task. Avoid accessing deleted widgets in the snapshot.
        task = Gui.Control.activeTaskDialog(Gui.getDocument(self.doc.Name))
        self.assertIsNotNone(task)
        self.strong_widgets.append(task)
        contents = task.getDialogContent()
        self.strong_widgets.extend(contents)
        panel = contents[0]
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
        objects.setCurrentRow(0)
        self._focus(objects)
        before = self._taskScopeState(objects, names)
        self.assertEqual(len(before["previews"]), 1)
        QtTest.QTest.keyClick(objects, key)
        self._pump()
        after = self._taskScopeState(objects, names)
        if removes_item:
            self.assertTrue(after["task_open"])
            self.assertEqual(after["list_count"], 1)
            self.assertEqual(len(after["selection"]), 1)
            self.assertEqual(after["samples"], before["samples"])
            self.assertEqual(after["previews"], before["previews"])
        else:
            self.assertEqual(after, before,
                             "Typing in another editor must not change the task's existing key handling")

    def testTaskEscapePreservesExistingState(self):
        self._checkTaskKeyScope(QtCore.Qt.Key_Escape)

    def testTaskDownPreservesExistingState(self):
        self._checkTaskKeyScope(QtCore.Qt.Key_Down)

    def testTaskDeletePreservesModelObjects(self):
        self._checkTaskKeyScope(QtCore.Qt.Key_Delete, removes_item=True)
