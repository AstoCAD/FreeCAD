# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression tests for the selection gate of a task dialog.

Issue #34120 (port of upstream PR #34155): since each document has its own task panel
page, showing a dialog on the page that is already shown, or activating its document
again, removed the selection gate the dialog had just set.

To run: FreeCAD -t TestTaskDialogGateGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets


class RejectAllGate:
    def allow(self, doc, obj, sub):
        return False


class GatedPanel:
    """Sets its gate in the constructor, before Control.showDialog(), like most task panels."""

    def __init__(self):
        self.form = QtWidgets.QWidget()
        Gui.Selection.addSelectionGate(RejectAllGate())


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestTaskDialogGateGui(unittest.TestCase):
    def setUp(self):
        Gui.Control.closeDialog()
        self.doc = App.newDocument("TestTaskDialogGateGui")
        self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        Gui.ActiveDocument = Gui.getDocument(self.doc.Name)
        Gui.Selection.clearSelection()

    def tearDown(self):
        Gui.Control.closeDialog()
        Gui.Selection.removeSelectionGate()
        Gui.Selection.clearSelection()
        App.closeDocument(self.doc.Name)

    def isBoxSelectable(self):
        Gui.Selection.addSelection(self.doc.Name, "Box")
        selected = bool(Gui.Selection.getSelection())
        Gui.Selection.clearSelection()
        return selected

    def testGateSetBeforeShowDialogStaysActive(self):
        Gui.Control.showDialog(GatedPanel())

        self.assertFalse(self.isBoxSelectable())

    def testGateStaysActiveWhenDocumentIsActivatedAgain(self):
        Gui.Control.showDialog(GatedPanel())
        App.setActiveDocument(self.doc.Name)
        Gui.ActiveDocument = Gui.getDocument(self.doc.Name)

        self.assertFalse(self.isBoxSelectable())

    def testGateIsRemovedWhenSwitchingToAnotherDocument(self):
        # Leaving the page still deactivates its dialog and drops the gate
        Gui.Control.showDialog(GatedPanel())
        other = App.newDocument("TestTaskDialogGateGuiOther")
        try:
            other.addObject("App::FeaturePython", "Obj")
            App.setActiveDocument(other.Name)
            Gui.Selection.addSelection(other.Name, "Obj")
            self.assertTrue(Gui.Selection.getSelection())
            Gui.Selection.clearSelection()
        finally:
            App.closeDocument(other.Name)
            App.setActiveDocument(self.doc.Name)
