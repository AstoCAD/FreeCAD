# SPDX-License-Identifier: LGPL-2.1-or-later
"""Opening a sketch can leave the camera untouched (#12895)."""

import FreeCAD
import Part

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"
PARAM_NAME = "AlignCameraOnEdit"


class TestAlignCameraOnEditGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.params = FreeCAD.ParamGet(PARAM_PATH)
        self.hadValue = PARAM_NAME in self.params.GetBools()
        self.oldValue = self.params.GetBool(PARAM_NAME, True)
        self.doc = FreeCAD.newDocument("AlignCameraOnEdit")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 5, 0)), False
        )
        self.doc.recompute()
        self.flush_gui(50)
        self.view = FreeCADGui.ActiveDocument.ActiveView
        self.view.viewIsometric()
        self.flush_gui(50)
        self.isometric = self.view.getCameraOrientation()

    def tearDown(self):
        if self.hadValue:
            self.params.SetBool(PARAM_NAME, self.oldValue)
        else:
            self.params.RemBool(PARAM_NAME)
        super().tearDown()

    def _isOrientation(self, rotation):
        return self.view.getCameraOrientation().isSame(rotation, 1e-5)

    def _openSketch(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.assertTrue(
            self.wait_until(lambda: FreeCADGui.ActiveDocument.getInEdit() is not None)
        )

    def testCameraUnchangedWhenPreferenceOff(self):
        self.params.SetBool(PARAM_NAME, False)
        camera = self.view.getCamera()
        self._openSketch()
        self.flush_gui(300)
        self.assertTrue(self._isOrientation(self.isometric))
        self.assertEqual(self.view.getCamera(), camera)

    def testCameraAlignedWhenPreferenceOn(self):
        self.params.SetBool(PARAM_NAME, True)
        self._openSketch()
        # The sketch lies on XY, so the camera ends up looking down Z (top view)
        self.assertTrue(self.wait_until(lambda: self._isOrientation(FreeCAD.Rotation()), 3000))
