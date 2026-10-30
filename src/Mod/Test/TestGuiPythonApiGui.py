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
