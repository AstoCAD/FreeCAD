# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tab in a tool widget parameter must move to the next parameter (#27753)."""

import FreeCAD as App
import Part
from PySide import QtCore, QtGui

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestToolWidgetTabGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.toolParams = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/Tools")
        self.hadVisibility = "OnViewParameterVisibility" in self.toolParams.GetInts()
        self.oldVisibility = self.toolParams.GetInt("OnViewParameterVisibility", 1)
        # No on-view parameter, so that Tab only cycles through the tool widget
        self.toolParams.SetInt("OnViewParameterVisibility", 0)

        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("ToolWidgetTabTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        self.doc.recompute()
        Gui.getMainWindow().show()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)

    def tearDown(self):
        try:
            if self.hadVisibility:
                self.toolParams.SetInt("OnViewParameterVisibility", self.oldVisibility)
            else:
                self.toolParams.RemInt("OnViewParameterVisibility")
        finally:
            super().tearDown()

    def focusedSpinBox(self, window):
        widget = window.focusWidget()
        while widget is not None and not isinstance(widget, QtGui.QAbstractSpinBox):
            widget = widget.parentWidget()
        return widget

    def testTabMovesToNextWidgetParameter(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Edge1")
        Gui.runCommand("Sketcher_Translate")
        self.flush_gui(200)

        mainWindow = Gui.getMainWindow()
        first = mainWindow.findChild(QtGui.QAbstractSpinBox, "parameterOne")
        second = mainWindow.findChild(QtGui.QAbstractSpinBox, "parameterTwo")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertTrue(first.isVisible() and second.isVisible())

        mainWindow.raise_()
        mainWindow.activateWindow()
        first.setFocus(QtCore.Qt.MouseFocusReason)
        self.flush_gui(50)
        self.assertIs(self.focusedSpinBox(first.window()), first)

        for widget in (first, second):
            press = QtGui.QKeyEvent(
                QtCore.QEvent.KeyPress, QtCore.Qt.Key_Tab, QtCore.Qt.NoModifier, "\t"
            )
            QtGui.QApplication.sendEvent(widget, press)
            self.flush_gui(100)
            expected = second if widget is first else first
            self.assertIs(
                self.focusedSpinBox(first.window()),
                expected,
                "Tab in %s should move the focus to %s"
                % (widget.objectName(), expected.objectName()),
            )

        Gui.ActiveDocument.resetEdit()
        self.flush_gui(100)
