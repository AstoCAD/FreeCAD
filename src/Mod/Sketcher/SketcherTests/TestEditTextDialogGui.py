# SPDX-License-Identifier: LGPL-2.1-or-later
"""Editing a sketch text must start with its current value selected (#33352)."""

import os

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestEditTextDialogGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        font = os.path.join(App.getResourceDir(), "examples", "osifont-lgpl3fe.ttf")
        if not os.path.isfile(font):
            self.skipTest("Bundled osifont not found")
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("EditTextDialogTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        handle = self.sketch.addGeometry(
            Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)), True
        )
        self.textConstraint = self.sketch.addConstraint(
            Sketcher.Constraint("Text", [handle, 0], "Hello", font, True)
        )
        self.sketch.setTextAndFont(self.textConstraint, "Hello", font, True, False)
        self.doc.recompute()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(100)

    def testTextIsPreselected(self):
        lists = [
            widget
            for widget in Gui.getMainWindow().findChildren(
                QtWidgets.QListWidget, "listWidgetConstraints"
            )
            if widget.count() > self.textConstraint
        ]
        if not lists:
            self.skipTest("Constraint task panel not available")
        item = lists[0].item(self.textConstraint)

        seen = []

        def inspect_dialog():
            modal = QtWidgets.QApplication.activeModalWidget()
            if modal is None:
                return
            edit = modal.findChild(QtWidgets.QLineEdit, "lineEdit_text")
            seen.append((edit.text(), edit.selectedText()) if edit else None)
            modal.reject()

        closer = QtCore.QTimer(Gui.getMainWindow())
        closer.timeout.connect(inspect_dialog)
        closer.start(25)
        try:
            lists[0].itemActivated.emit(item)
            self.flush_gui(50)
        finally:
            closer.stop()
            closer.deleteLater()

        self.assertTrue(seen, "Edit text dialog did not open")
        self.assertEqual(seen[0], ("Hello", "Hello"))
