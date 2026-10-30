# SPDX-License-Identifier: LGPL-2.1-or-later
"""The Snell's law command uses the regular datum dialog (#30500)."""

import FreeCAD as App
import Part
from PySide import QtCore, QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase

HISTORY_PATH = "User parameter:BaseApp/History/SketcherRefrIndexRatio"
PREF_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher"


class TestSnellsLawCommandGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        Gui.activateWorkbench("SketcherWorkbench")
        self.history = App.ParamGet(HISTORY_PATH)
        self.hadRatio = "DatumValue" in self.history.GetStrings()
        self.oldRatio = self.history.GetString("DatumValue")
        self.history.SetString("DatumValue", "1.5")
        self.prefs = App.ParamGet(PREF_PATH)
        self.oldShowDialog = self.prefs.GetBool("ShowDialogOnDistanceConstraint", True)
        self.prefs.SetBool("ShowDialogOnDistanceConstraint", True)

        self.doc = App.newDocument("SnellsLawCommand")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        # incoming ray, outgoing ray and boundary
        self.sketch.addGeometry(
            Part.LineSegment(App.Vector(-10, 10, 0), App.Vector(0, 0, 0)), False
        )
        self.sketch.addGeometry(
            Part.LineSegment(App.Vector(0, 0, 0), App.Vector(6, -10, 0)), False
        )
        self.sketch.addGeometry(
            Part.LineSegment(App.Vector(-20, 0, 0), App.Vector(20, 0, 0)), False
        )
        self.doc.recompute()
        Gui.activeDocument().setEdit(self.sketch.Name)
        self.flush_gui(50)

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            if self.hadRatio:
                self.history.SetString("DatumValue", self.oldRatio)
            else:
                self.history.RemString("DatumValue")
            self.prefs.SetBool("ShowDialogOnDistanceConstraint", self.oldShowDialog)

    def _runCommand(self, onDialog=None):
        found = {}

        def handle():
            if found.get("done"):
                return
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                QtCore.QTimer.singleShot(50, handle)
                return
            found["dialog"] = True
            found["value"] = (
                self.sketch.Constraints[-1].Value if self.sketch.ConstraintCount else None
            )
            if onDialog:
                onDialog(dialog)
            else:
                dialog.accept()

        QtCore.QTimer.singleShot(0, handle)
        Gui.Selection.clearSelection()
        for name in ("Vertex2", "Vertex3", "Edge3"):
            Gui.Selection.addSelection(self.sketch, name)
        Gui.runCommand("Sketcher_ConstrainSnellsLaw")
        self.flush_gui(100)
        found["done"] = True
        return found

    def _snellsLaw(self):
        constraints = [c for c in self.sketch.Constraints if c.Type == "SnellsLaw"]
        self.assertEqual(len(constraints), 1)
        return constraints[0]

    def testCreatedWithLastUsedRatio(self):
        found = self._runCommand()
        self.assertTrue(found.get("dialog"))
        # The constraint exists while the dialog is open, so the dialog can bind to it
        self.assertAlmostEqual(found.get("value"), 1.5)
        self.assertAlmostEqual(self._snellsLaw().Value, 1.5)

        self.doc.undo()
        self.assertEqual(self.sketch.ConstraintCount, 0)

    def testCancelRemovesConstraint(self):
        found = self._runCommand(lambda dialog: dialog.reject())
        self.assertTrue(found.get("dialog"))
        self.assertEqual(self.sketch.ConstraintCount, 0)

    def testNoDialogWhenDisabled(self):
        self.prefs.SetBool("ShowDialogOnDistanceConstraint", False)
        found = self._runCommand(lambda dialog: dialog.reject())
        self.assertFalse(found.get("dialog"))
        self.assertAlmostEqual(self._snellsLaw().Value, 1.5)
