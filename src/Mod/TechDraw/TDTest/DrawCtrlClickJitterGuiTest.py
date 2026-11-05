# SPDX-License-Identifier: LGPL-2.1-or-later

"""Ctrl+click on drawing edges must tolerate a small press/release offset.

A pen or touch device rarely releases at the exact press position. Qt only
toggles a Ctrl+click selection when both positions are equal, so edges and
vertices could not be added to the selection reliably with a pen.
https://github.com/FreeCAD/FreeCAD/issues/32440
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtGui, QtWidgets


TDTEST = Path(__file__).resolve().parent
QGIEDGE_TYPE = 65536 + 19  # TechDrawGui::UserType::QGIEdge


class DrawCtrlClickJitterGuiTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("CtrlClickJitter")
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 40, 10, 20
        page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        page.Template = template
        view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = App.Vector(0, -1, 0)
        view.ScaleType = "Custom"
        view.Scale = 2
        view.X, view.Y = 100, 100
        self.doc.recompute()
        page.ViewObject.show()
        self.assertTrue(self._wait(lambda: len(view.getVisibleEdges()) == 4),
                        "The box view must have four visible outline edges")
        self.assertTrue(self._wait(lambda: len(self._edges()) == 4),
                        "The page scene must show the four outline edges")
        self.widget = self._page_view()
        Gui.Selection.clearSelection()
        self._events(100)

    def tearDown(self):
        Gui.Selection.clearSelection()
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

    def _page_view(self):
        window = Gui.getMainWindow()
        widgets = [widget for widget in window.findChildren(QtWidgets.QGraphicsView)
                   if widget.objectName() == "PageView"
                   and widget.scene() is not None and widget.isVisibleTo(window)]
        # The page view of this test's document is the most recently created one.
        return widgets[-1] if widgets else None

    def _edges(self):
        widget = self._page_view()
        if widget is None:
            return []
        return [item for item in widget.scene().items() if item.type() == QGIEDGE_TYPE]

    def _edge_points(self):
        """Viewport points on the middle of each visible edge."""
        viewport = self.widget.viewport()
        points = []
        for edge in self._edges():
            point = self.widget.mapFromScene(edge.sceneBoundingRect().center())
            hit = self.widget.itemAt(point)
            if viewport.rect().contains(point) and hit is not None \
                    and hit.type() == QGIEDGE_TYPE:
                points.append(point)
        self.assertGreaterEqual(len(points), 2, "Two edges must be clickable in the viewport")
        return points

    def _selected_edges(self):
        return [item for item in self._edges() if item.isSelected()]

    def _mouse(self, event_type, position, buttons, modifiers):
        viewport = self.widget.viewport()
        event = QtGui.QMouseEvent(event_type, QtCore.QPointF(position),
                                  QtCore.QPointF(viewport.mapToGlobal(position)),
                                  QtCore.Qt.LeftButton, buttons, modifiers)
        QtWidgets.QApplication.sendEvent(viewport, event)
        self._events(25)

    def _click(self, position, modifiers=QtCore.Qt.NoModifier, jitter=0):
        self._mouse(QtCore.QEvent.MouseButtonPress, position, QtCore.Qt.LeftButton, modifiers)
        self._mouse(QtCore.QEvent.MouseButtonRelease, position + QtCore.QPoint(jitter, 0),
                    QtCore.Qt.NoButton, modifiers)

    def _selected_subelements(self):
        names = []
        for sel in Gui.Selection.getSelectionEx():
            names.extend(sel.SubElementNames)
        return [name for name in names if name.startswith("Edge")]

    def test_ctrl_click_without_jitter(self):
        first, second = self._edge_points()[:2]
        self._click(first)
        self.assertEqual(len(self._selected_edges()), 1)
        self._click(second, QtCore.Qt.ControlModifier)
        self.assertEqual(len(self._selected_edges()), 2)
        self.assertEqual(len(self._selected_subelements()), 2)

    def test_ctrl_click_with_jitter_adds_edge(self):
        first, second = self._edge_points()[:2]
        self._click(first)
        self.assertEqual(len(self._selected_edges()), 1)
        self._click(second, QtCore.Qt.ControlModifier, jitter=1)
        self.assertEqual(len(self._selected_edges()), 2,
                         "Ctrl+click released one pixel away must add the edge")
        self.assertEqual(len(self._selected_subelements()), 2)

    def test_ctrl_click_with_jitter_removes_edge(self):
        first, second = self._edge_points()[:2]
        self._click(first)
        self._click(second, QtCore.Qt.ControlModifier)
        self.assertEqual(len(self._selected_edges()), 2)
        self._click(second, QtCore.Qt.ControlModifier, jitter=1)
        self.assertEqual(len(self._selected_edges()), 1,
                         "Ctrl+click released one pixel away must remove the edge")
        self.assertEqual(len(self._selected_subelements()), 1)


if __name__ == "__main__":
    unittest.main()
