# SPDX-License-Identifier: LGPL-2.1-or-later

"""Weld symbol on a leader line that has a single waypoint.

QGIWeldSymbol orients its tail text along the leader's last segment
(DrawLeaderLine::lastSegmentDirection). With one waypoint there is no
segment, and the direction was computed from the element before the
start of the waypoint list. It must fall back to the horizontal default
used for a leader without waypoints.
"""

from pathlib import Path
import math
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")
TAIL = "TAILR12"


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawWeldSymbolOnePointLeaderGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDWeldOnePointLeader")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.base = self.doc.addObject("TechDraw::DrawViewPart", "BaseView")
        self.page.addView(self.base)
        self.base.Source = [self.box]
        self.base.Direction = App.Vector(0, 0, 1)
        self.base.X, self.base.Y = 80, 100
        self.leader = self.doc.addObject("TechDraw::DrawLeaderLine", "Leader")
        self.page.addView(self.leader)
        self.leader.LeaderParent = self.base
        # one waypoint away from the leader origin
        self.leader.WayPoints = [App.Vector(20, 10, 0)]
        self.weld = self.doc.addObject("TechDraw::DrawWeldSymbol", "Weld")
        self.page.addView(self.weld)
        self.weld.Leader = self.leader
        self.weld.TailText = TAIL
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(lambda: len(self.base.getVisibleEdges()) >= 4),
            "The base view was not projected",
        )
        self._pump(300)

    def tearDown(self):
        Gui.Selection.clearSelection()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
            self._pump(100)
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        self._pump(100)
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    @staticmethod
    def _pump(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                return False
            self._pump()
        return True

    @staticmethod
    def _tail_texts():
        window = Gui.getMainWindow()
        result = []
        for view in window.findChildren(QtWidgets.QGraphicsView):
            if view.objectName() != "PageView" or view.scene() is None:
                continue
            for item in view.scene().items():
                if isinstance(item, QtWidgets.QGraphicsTextItem) and item.toPlainText() == TAIL:
                    result.append(item)
        return result

    def test_tail_text_is_horizontal_on_one_point_leader(self):
        self.assertTrue(self._wait(lambda: bool(self._tail_texts())), "The weld tail text was not drawn")
        for item in self._tail_texts():
            angle = item.rotation()
            self.assertTrue(math.isfinite(angle))
            self.assertAlmostEqual(math.remainder(angle, 360.0), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
