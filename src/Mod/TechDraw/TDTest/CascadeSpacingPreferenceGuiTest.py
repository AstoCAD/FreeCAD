# SPDX-License-Identifier: LGPL-2.1-or-later
"""The cascade spacing of the dimension tools defaults to a preference (#14335)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions"
PARAM_NAME = "CascadeSpacing"


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class CascadeSpacingPreferenceGuiTest(unittest.TestCase):
    def setUp(self):
        self.params = App.ParamGet(PARAM_PATH)
        self.saved = [
            entry[2]
            for entry in (self.params.GetContents() or [])
            if entry[0] == "Float" and entry[1] == PARAM_NAME
        ]
        self.addCleanup(self._restore_params)

        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("CascadeSpacing14335")
        self.addCleanup(self._close)
        box = self.doc.addObject("Part::Box", "Box")
        page = createPageWithSVGTemplate(self.doc)
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        self.doc.recompute()

    def _restore_params(self):
        self.params.RemFloat(PARAM_NAME)
        for value in self.saved:
            self.params.SetFloat(PARAM_NAME, value)

    def _close(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _wait(self, predicate, ms=5000):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while timer.elapsed() < ms:
            QtWidgets.QApplication.processEvents()
            if predicate():
                return True
        return predicate()

    def _task_spacing(self):
        """Open the Select Line Attributes task, return its cascade spacing and cancel it"""
        Gui.runCommand("TechDraw_ExtensionSelectLineAttributes")
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is not None))
        spinBox = Gui.getMainWindow().findChild(QtWidgets.QDoubleSpinBox, "sbSpacing")
        self.assertIsNotNone(spinBox)
        value = spinBox.value()
        Gui.Control.closeDialog()
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is None))
        return value

    def testTaskStartsFromPreference(self):
        # the task was not accepted in this session, so the preference is used
        self.params.SetFloat(PARAM_NAME, 12.5)
        self.assertAlmostEqual(self._task_spacing(), 12.5)

        # a changed preference applies without a restart
        self.params.SetFloat(PARAM_NAME, 9.0)
        self.assertAlmostEqual(self._task_spacing(), 9.0)


if __name__ == "__main__":
    unittest.main()
