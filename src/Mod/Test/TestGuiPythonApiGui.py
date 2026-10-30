# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD contributors
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI regression tests for odd arguments given to the FreeCADGui Python API.

These calls used to crash the application instead of raising a Python exception.

To run tests:
    FreeCAD -t TestGuiPythonApiGui
"""

import sys
import unittest

import FreeCAD
import FreeCADGui


class TestSelectionGateGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestSelectionGate")
        self.group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        self.other = self.doc.addObject("App::FeaturePython", "Other")
        FreeCADGui.Selection.clearSelection()

    def tearDown(self):
        FreeCADGui.Selection.removeSelectionGate()
        FreeCADGui.Selection.clearSelection()
        FreeCAD.closeDocument(self.doc.Name)

    def test_filter_gate_keeps_filter_alive(self):
        selection_filter = FreeCADGui.Selection.Filter("SELECT App::DocumentObjectGroup")
        refs = sys.getrefcount(selection_filter)
        FreeCADGui.Selection.addSelectionGate(selection_filter)
        # the gate holds a reference to the filter object
        self.assertEqual(sys.getrefcount(selection_filter), refs + 1)
        FreeCADGui.Selection.removeSelectionGate()
        self.assertEqual(sys.getrefcount(selection_filter), refs)

    def test_filter_gate_with_resolve_mode(self):
        selection_filter = FreeCADGui.Selection.Filter("SELECT App::DocumentObjectGroup")
        FreeCADGui.Selection.addSelectionGate(selection_filter, 0)
        FreeCADGui.Selection.addSelection(self.other)
        FreeCADGui.Selection.addSelection(self.group)
        self.assertEqual(FreeCADGui.Selection.getSelection(), [self.group])
        FreeCADGui.Selection.removeSelectionGate()

    def test_filter_gate_outlives_python_reference(self):
        FreeCADGui.Selection.addSelectionGate(
            FreeCADGui.Selection.Filter("SELECT App::DocumentObjectGroup")
        )
        FreeCADGui.Selection.addSelection(self.other)
        FreeCADGui.Selection.addSelection(self.group)
        self.assertEqual(FreeCADGui.Selection.getSelection(), [self.group])
        FreeCADGui.Selection.removeSelectionGate()


class TestToggleTreeItemGui(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestToggleTreeItem")
        self.other_doc = FreeCAD.newDocument("TestToggleTreeItemOther")
        self.group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        self.foreign = self.other_doc.addObject("App::DocumentObjectGroup", "Foreign")
        self.gui_doc = FreeCADGui.getDocument(self.doc.Name)

    def tearDown(self):
        FreeCAD.closeDocument(self.other_doc.Name)
        FreeCAD.closeDocument(self.doc.Name)

    def test_toggle_object_of_this_document(self):
        for mode in range(4):
            self.gui_doc.toggleTreeItem(self.group, mode)

    def test_toggle_object_of_other_document_raises(self):
        with self.assertRaises(ValueError):
            self.gui_doc.toggleTreeItem(self.foreign)

    def test_toggle_deleted_object_raises(self):
        obj = self.doc.addObject("App::DocumentObjectGroup", "Deleted")
        self.doc.removeObject(obj.Name)
        with self.assertRaises(ValueError):
            self.gui_doc.toggleTreeItem(obj, 2)



class TestClosedDocumentObjectGui(unittest.TestCase):
    """Objects of a closed document have no C++ object any more."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestClosedDocumentObject")
        self.group = self.doc.addObject("App::DocumentObjectGroup", "Group")
        self.gui_doc = FreeCADGui.getDocument(self.doc.Name)
        other_doc = FreeCAD.newDocument("TestClosedDocumentObjectOther")
        self.closed = other_doc.addObject("App::DocumentObjectGroup", "Closed")
        self.closed_view = self.closed.ViewObject
        FreeCAD.closeDocument(other_doc.Name)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def test_toggle_tree_item(self):
        with self.assertRaises(ValueError):
            self.gui_doc.toggleTreeItem(self.closed)
        with self.assertRaises(ValueError):
            self.gui_doc.toggleTreeItem(self.closed, 0, "Face1")

    def test_view_object_of_closed_document(self):
        with self.assertRaises(ValueError):
            self.gui_doc.scrollToTreeItem(self.closed_view)
        with self.assertRaises(ValueError):
            self.gui_doc.toggleInSceneGraph(self.closed_view)

    def test_export(self):
        with self.assertRaises(ValueError):
            FreeCADGui.export([self.closed], "closed_document_object.iv")

    def test_selection_filter(self):
        selection_filter = FreeCADGui.Selection.Filter("SELECT App::DocumentObjectGroup")
        self.assertTrue(selection_filter.test(self.group))
        with self.assertRaises(ValueError):
            selection_filter.test(self.closed)

    def test_drag_and_drop(self):
        view = self.group.ViewObject
        with self.assertRaises(ValueError):
            view.canDragObject(self.closed)
        with self.assertRaises(ValueError):
            view.canDropObject(self.closed)
        with self.assertRaises(ValueError):
            view.canDropObject(self.group, self.closed, "", [])
        with self.assertRaises(ValueError):
            view.canDragAndDropObject(self.closed)
        with self.assertRaises(ValueError):
            view.dropObject(self.closed)
        with self.assertRaises(ValueError):
            view.dragObject(self.closed)
