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
        # viewIsometric() may be animated: wait until the camera stops moving
        self.isometric = None

        def settled():
            current = self.view.getCameraOrientation()
            done = self.isometric is not None and current.isSame(self.isometric, 1e-9)
            self.isometric = current
            return done

        self.assertTrue(self.wait_until(settled, 3000, 100))

    def tearDown(self):
        if self.hadValue:
            self.params.SetBool(PARAM_NAME, self.oldValue)
        else:
            self.params.RemBool(PARAM_NAME)
        super().tearDown()

    def _isOrientation(self, rotation):
        return self.view.getCameraOrientation().isSame(rotation, 1e-5)

    def _camera(self):
        # near/far clipping planes are recomputed from the scene content, which changes in edit
        lines = self.view.getCamera().splitlines()
        return [l for l in lines if not l.strip().startswith(("nearDistance", "farDistance"))]

    def _openSketch(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.assertTrue(
            self.wait_until(lambda: FreeCADGui.ActiveDocument.getInEdit() is not None)
        )

    def testCameraUnchangedWhenPreferenceOff(self):
        self.params.SetBool(PARAM_NAME, False)
        camera = self._camera()
        self._openSketch()
        self.flush_gui(300)
        self.assertTrue(self._isOrientation(self.isometric))
        self.assertEqual(self._camera(), camera)

    def testCameraAlignedWhenPreferenceOn(self):
        self.params.SetBool(PARAM_NAME, True)
        self._openSketch()
        # The sketch lies on XY, so the camera ends up looking down Z (top view)
        self.assertTrue(self.wait_until(lambda: self._isOrientation(FreeCAD.Rotation()), 3000))
