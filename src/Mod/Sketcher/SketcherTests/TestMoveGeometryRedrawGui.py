# SPDX-License-Identifier: LGPL-2.1-or-later
"""Moving geometry from Python in edit mode must update the view (#18703)."""

import FreeCAD as App
import Part

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestMoveGeometryRedrawGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("MoveGeometryRedrawTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        self.doc.recompute()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)

    def drawnPoints(self):
        from pivy import coin

        search = coin.SoSearchAction()
        search.setName("PointsCoordinate0")
        search.setSearchingAll(True)
        search.apply(Gui.activeDocument().activeView().getSceneGraph())
        path = search.getPath()
        self.assertIsNotNone(path)
        coords = path.getTail()
        return [(p[0], p[1]) for p in coords.point.getValues()]

    def isDrawn(self, x, y):
        return any(abs(px - x) < 1e-4 and abs(py - y) < 1e-4 for px, py in self.drawnPoints())

    def testMoveGeometryRedrawsInEditMode(self):
        self.assertTrue(self.isDrawn(10.0, 0.0))

        self.sketch.moveGeometry(0, 2, App.Vector(20, 5, 0))
        self.flush_gui(100)
        self.assertTrue(self.isDrawn(20.0, 5.0), "moved end point is not drawn")

        self.sketch.moveGeometries([(0, 1)], App.Vector(-3, 4, 0))
        self.flush_gui(100)
        self.assertTrue(self.isDrawn(-3.0, 4.0), "moved start point is not drawn")

        Gui.ActiveDocument.resetEdit()
        self.flush_gui(100)
