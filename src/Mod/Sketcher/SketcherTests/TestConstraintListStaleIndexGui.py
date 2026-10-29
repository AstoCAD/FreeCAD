# SPDX-License-Identifier: LGPL-2.1-or-later
"""The constraint list must tolerate a Constraints property replaced behind its back (#33175)."""

import FreeCAD
import Part
import Sketcher
from PySide import QtCore, QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase


class TestConstraintListStaleIndexGui(SketcherGuiTestCase):
    CONSTRAINT_COUNT = 40

    def setUp(self):
        super().setUp()
        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("ConstraintListStaleIndex")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for i in range(self.CONSTRAINT_COUNT):
            self.sketch.addGeometry(
                Part.LineSegment(FreeCAD.Vector(0, i, 0), FreeCAD.Vector(10, i, 0)), False
            )
            self.sketch.addConstraint(Sketcher.Constraint("Horizontal", i))
        self.doc.recompute()
        self.assertTrue(FreeCADGui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(100)

    def find_constraint_widgets(self):
        main_window = FreeCADGui.getMainWindow()
        lists = [
            widget
            for widget in main_window.findChildren(
                QtWidgets.QListWidget, "listWidgetConstraints"
            )
            if widget.count() > 0
        ]
        buttons = main_window.findChildren(QtWidgets.QToolButton, "showHideButton")
        return lists, buttons

    def test_show_hide_all_after_constraints_replaced(self):
        lists, buttons = self.find_constraint_widgets()
        if not lists or not buttons:
            self.skipTest("Constraint task panel not available")
        self.assertEqual(lists[0].count(), self.CONSTRAINT_COUNT)

        # Replace the property directly: this does not resync the open list, so
        # its items keep indices past the end of the (now empty) property.
        self.sketch.Constraints = []
        self.flush_gui()
        self.assertEqual(self.sketch.ConstraintCount, 0)

        # Previously read out of bounds in ConstraintItem::isInVirtualSpace() and
        # passed the stale indices on to setVirtualSpace(), which raised an error
        # dialog. Close and record any modal dialog so a regression cannot hang.
        modal_titles = []

        def close_modal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is not None:
                modal_titles.append(modal.windowTitle())
                modal.close()

        closer = QtCore.QTimer(FreeCADGui.getMainWindow())
        closer.timeout.connect(close_modal)
        closer.start(25)
        try:
            buttons[0].click()
            self.flush_gui(50)
            buttons[0].click()
            self.flush_gui(50)
        finally:
            closer.stop()
            closer.deleteLater()

        self.assertEqual(modal_titles, [])
        self.assertEqual(self.sketch.ConstraintCount, 0)
