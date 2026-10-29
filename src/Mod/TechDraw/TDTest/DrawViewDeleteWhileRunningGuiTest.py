# SPDX-License-Identifier: LGPL-2.1-or-later
"""Deleting a view while its background task is running must not abort FreeCAD (#33900).

The view destructor waits for the task. The task reads the name of the view,
which is null once the view has been removed, and failed. waitForFinished()
rethrew that failure inside the destructor, which terminated the process.
"""

import time
import unittest

import FreeCAD
import Part
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate


def manyBoxes(count=20):
    """A compound of count*count boxes, so that cutting a detail of it takes a while."""
    boxes = []
    for i in range(count):
        for j in range(count):
            boxes.append(Part.makeBox(4, 4, 4, FreeCAD.Vector(i * 5, j * 5, 0)))
    return Part.makeCompound(boxes)


class DrawViewDeleteWhileRunningGuiTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDDeleteWhileRunning")
        # without undo, removeObject() destroys the view at once
        self.doc.UndoMode = 0
        self.source = self.doc.addObject("Part::Feature", "Boxes")
        self.source.Shape = manyBoxes()
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        # front view: in this direction the detail cut runs long enough in its thread
        self.view.Direction = FreeCAD.Vector(0, -1, 0)
        self.doc.recompute()
        self._waitFor(self.view)

    def tearDown(self):
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    def _waitFor(self, view, seconds=60):
        if not FreeCAD.GuiUp:
            return
        import FreeCADGui
        from PySide import QtCore

        deadline = time.monotonic() + seconds
        while not view.isProjectionReady():
            self.assertLess(time.monotonic(), deadline, "projection did not finish")
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()
            FreeCADGui.updateGui()

    def testRemoveDetailWhileCutting(self):
        detail = self.doc.addObject("TechDraw::DrawViewDetail", "Detail")
        detail.BaseView = self.view
        detail.Direction = self.view.Direction
        detail.XDirection = self.view.XDirection
        detail.AnchorPoint = FreeCAD.Vector(0, 0, 0)
        detail.Radius = 1000
        self.page.addView(detail)
        self.doc.recompute()
        name = detail.Name
        # no event processing since the recompute: the detail cut is still running
        self.doc.removeObject(name)
        self.assertIsNone(self.doc.getObject(name))
        self.assertIsNotNone(self.doc.getObject(self.view.Name))


if __name__ == "__main__":
    unittest.main()
