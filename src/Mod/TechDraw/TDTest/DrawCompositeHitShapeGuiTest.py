# SPDX-License-Identifier: LGPL-2.1-or-later

"""Balloon and leader hit shapes must be the union of their parts.

The composite shape() of QGIViewBalloon and QGILeaderLine was built with
QPainterPath::addPath(), which keeps the default odd-even fill rule, so
places covered by two parts (balloon text inside the bubble, leader arrow
on its line) became holes in the hit shape.
Upstream PR https://github.com/FreeCAD/FreeCAD/pull/34007
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtWidgets


TDTEST = Path(__file__).resolve().parent
USER_TYPE = 65536  # QGraphicsItem::UserType, see TechDrawGui::UserType
QGIARROW_TYPE = USER_TYPE + 9
QGIBALLOONLABEL_TYPE = USER_TYPE + 10
QGILEADERLINE_TYPE = USER_TYPE + 23
QGIVIEWBALLOON_TYPE = USER_TYPE + 36


class DrawCompositeHitShapeGuiTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("CompositeHitShape")
        box = self.doc.addObject("Part::Box", "Box")
        page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        page.Template = template
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.X, view.Y = 100, 100

        balloon = self.doc.addObject("TechDraw::DrawViewBalloon", "Balloon")
        balloon.SourceView = view
        balloon.OriginX = 5
        balloon.OriginY = 5
        balloon.X = 40
        balloon.Y = 40
        balloon.Text = "1"
        page.addView(balloon)

        leader = self.doc.addObject("TechDraw::DrawLeaderLine", "Leader")
        leader.LeaderParent = view
        leader.X, leader.Y = -30, -20
        leader.WayPoints = [App.Vector(0, 0, 0), App.Vector(30, 0, 0)]
        leader.StartSymbol = 0  # filled arrow
        page.addView(leader)

        self.doc.recompute()
        page.ViewObject.show()
        self.assertTrue(self._wait(lambda: self._item(QGIVIEWBALLOON_TYPE) is not None),
                        "The page scene must show the balloon")
        self.assertTrue(self._wait(lambda: self._item(QGILEADERLINE_TYPE) is not None),
                        "The page scene must show the leader line")
        self._events(200)

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        self._events(100)

    @staticmethod
    def _events(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=12):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._events()
        return True

    def _scene(self):
        window = Gui.getMainWindow()
        views = [widget for widget in window.findChildren(QtWidgets.QGraphicsView)
                 if widget.objectName() == "PageView" and widget.scene() is not None]
        # The page view of this test's document is the most recently created one.
        return views[-1].scene() if views else None

    def _item(self, item_type):
        scene = self._scene()
        if scene is None:
            return None
        items = [item for item in scene.items() if item.type() == item_type]
        return items[0] if items else None

    @staticmethod
    def _child(parent, item_type):
        children = [child for child in parent.childItems()
                    if child.type() == item_type and child.isVisible()]
        return children[0] if children else None

    def test_balloon_text_inside_bubble_is_hit(self):
        balloon = self._item(QGIVIEWBALLOON_TYPE)
        label = self._child(balloon, QGIBALLOONLABEL_TYPE)
        self.assertIsNotNone(label, "The balloon must have a visible label")
        centre = balloon.mapFromItem(label, label.boundingRect().center())
        self.assertTrue(balloon.contains(centre),
                        "The balloon text inside the bubble must be part of the hit shape")

    def test_leader_arrow_on_line_is_hit(self):
        leader = self._item(QGILEADERLINE_TYPE)
        arrow = self._child(leader, QGIARROW_TYPE)
        self.assertIsNotNone(arrow, "The leader must show its start arrow")
        # The middle of the arrow head lies on the leader line axis.
        middle = leader.mapFromItem(arrow, arrow.path().boundingRect().center())
        self.assertTrue(leader.contains(middle),
                        "The arrow head on the leader line must be part of the hit shape")


if __name__ == "__main__":
    unittest.main()
