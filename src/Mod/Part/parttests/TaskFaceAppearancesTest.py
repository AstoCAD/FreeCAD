# SPDX-License-Identifier: LGPL-2.1-or-later

import unittest
import FreeCAD
import FreeCADGui
from PySide import QtWidgets


class TaskFaceAppearancesGuiTest(unittest.TestCase):
    """'Appearance per Face' opens the 'Material and appearance' dialog for faces."""

    def setUp(self):
        """Set up the test document and a basic shape."""
        self.doc = FreeCAD.newDocument("FaceAppTest")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()

    def tearDown(self):
        """Clean up the selection and close the document."""
        FreeCADGui.Control.closeDialog()
        FreeCADGui.Selection.clearSelection()
        FreeCAD.closeDocument(self.doc.Name)

    def test_face_selection_updates_widget_state(self):
        """Test if the material widget state synchronizes with face selection (#27716)."""
        # This test requires the GUI module to be loaded and active
        if not FreeCAD.GuiUp:
            self.skipTest("This test requires a graphical user interface (GUI).")

        # 1. 'Appearance per Face' is the Color edit mode: it opens the task dialog of
        #    Std_SetAppearance with the face scope, and no edit mode
        FreeCADGui.Selection.addSelection(self.doc.Name, "Box")
        color_edit_mode = 3  # Gui::ViewProvider::Color
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.box, color_edit_mode)
        self.assertIsNotNone(FreeCADGui.Control.activeDialog())
        self.assertIsNone(FreeCADGui.getDocument(self.doc.Name).getInEdit())

        # Get the FreeCAD Main Window to search for the UI elements
        main_window = FreeCADGui.getMainWindow()
        self.assertIsNotNone(main_window, "Could not find the FreeCAD main window.")

        # 2. Find the relevant UI widgets by their object names directly in the Main Window
        radio_faces = main_window.findChild(QtWidgets.QRadioButton, "radioScopeFaces")
        btn_custom = main_window.findChild(QtWidgets.QPushButton, "buttonCustomAppearance")
        widget_material = main_window.findChild(QtWidgets.QWidget, "widgetMaterial")

        self.assertIsNotNone(radio_faces, "Face scope button not found in the UI.")
        self.assertIsNotNone(btn_custom, "Custom Appearance button not found in the UI.")
        self.assertIsNotNone(widget_material, "Material widget not found in the UI.")
        self.assertTrue(radio_faces.isChecked(), "The dialog must apply to faces.")

        # Scenario A: No face selected -> Widgets should be disabled
        FreeCADGui.Selection.clearSelection()
        self.assertFalse(
            widget_material.isEnabled(), "Widget should be disabled when no face is selected."
        )
        self.assertFalse(
            btn_custom.isEnabled(),
            "Custom Appearance button should be disabled when no face is selected.",
        )

        # Scenario B: Single face selected -> Widgets should be enabled
        FreeCADGui.Selection.addSelection(self.doc.Name, "Box", "Face1")
        self.assertTrue(
            widget_material.isEnabled(), "Widget should be enabled after selecting Face1."
        )
        self.assertTrue(btn_custom.isEnabled(), "Button should be enabled after selecting Face1.")

        # Scenario C: Multiple faces selected -> Widgets should remain enabled
        FreeCADGui.Selection.addSelection(self.doc.Name, "Box", "Face2")
        self.assertTrue(
            widget_material.isEnabled(), "Widget should be enabled with multiple faces selected."
        )

        # Scenario D: Clear selection -> Widgets should be disabled again
        FreeCADGui.Selection.clearSelection()
        self.assertFalse(
            widget_material.isEnabled(), "Widget should be disabled after clearing selection."
        )
