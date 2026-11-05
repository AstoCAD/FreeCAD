# SPDX-License-Identifier: LGPL-2.1-or-later
"""Sketcher_Split obeys the "Continue mode" preference (FreeCAD#12608)."""

import FreeCAD
import Part
from PySide import QtCore

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

TOOLS_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/Tools"
SKETCHER_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher"


class TestSplitContinuousModeGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.tools = FreeCAD.ParamGet(TOOLS_PATH)
        self.hadOvp = "OnViewParameterVisibility" in self.tools.GetInts()
        self.oldOvp = self.tools.GetInt("OnViewParameterVisibility", 1)
        self.tools.SetInt("OnViewParameterVisibility", 0)
        self.sketcher = FreeCAD.ParamGet(SKETCHER_PATH)
        self.hadContinuous = "ContinuousCreationMode" in self.sketcher.GetBools()
        self.oldContinuous = self.sketcher.GetBool("ContinuousCreationMode", True)

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("SplitContinuousMode")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        V = FreeCAD.Vector
        self.sketch.addGeometry(Part.LineSegment(V(-30, 5, 0), V(30, 5, 0)))
        self.doc.recompute()

    def tearDown(self):
        try:
            if self.hadOvp:
                self.tools.SetInt("OnViewParameterVisibility", self.oldOvp)
            else:
                self.tools.RemInt("OnViewParameterVisibility")
            if self.hadContinuous:
                self.sketcher.SetBool("ContinuousCreationMode", self.oldContinuous)
            else:
                self.sketcher.RemBool("ContinuousCreationMode")
        finally:
            super().tearDown()

    def splitTwice(self):
        """Run Sketcher_Split, then click two locations of the line, without leaving the tool."""
        FreeCADGui.getMainWindow().show()
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.pump(200)
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.pump(150)
        viewport = view.graphicsView().viewport()

        def screen(x, y):
            return self.viewport_to_qpoint(
                view, viewport, view.getPointOnScreen(FreeCAD.Vector(x, y, 0))
            )

        FreeCADGui.runCommand("Sketcher_Split")
        self.pump(200)

        for x in (-10, 10):
            self.move(viewport, screen(x - 1, 5))
            self.move(viewport, screen(x, 5))
            self.pump(100)
            self.click(viewport, screen(x, 5))
            self.pump(200)

        viewport.setFocus()
        self.key_click(viewport, QtCore.Qt.Key_Escape)
        self.pump(100)
        FreeCADGui.Selection.clearSelection()

    def testToolEndsWithoutContinuousMode(self):
        self.sketcher.SetBool("ContinuousCreationMode", False)
        self.splitTwice()
        # The second click happens after the tool has ended: it must not split again.
        self.assertEqual(self.sketch.GeometryCount, 2)

    def testToolStaysInContinuousMode(self):
        self.sketcher.SetBool("ContinuousCreationMode", True)
        self.splitTwice()
        self.assertEqual(self.sketch.GeometryCount, 3)
