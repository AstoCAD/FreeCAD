# SPDX-License-Identifier: LGPL-2.1-or-later

"""Exercise drawing-view selection through ordinary deletion and document close."""

from pathlib import Path
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtGui, QtWidgets

try:
    from shiboken6 import isValid, ownedByPython
except ImportError:
    from shiboken2 import isValid, ownedByPython


TDTEST = Path(__file__).resolve().parent


class _MessageObserver(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def eventFilter(self, watched, event):
        if (event.type() == QtCore.QEvent.Show
                and isinstance(watched, QtWidgets.QMessageBox)):
            self.messages.append(watched.text())
        return False


class DrawViewSelectionTeardownGuiTest(unittest.TestCase):
    def setUp(self):
        self.names = []
        self.external_slots = []
        self.reports = [(widget, widget.toPlainText())
                        for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
                        if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.message_observer = _MessageObserver()
        QtWidgets.QApplication.instance().installEventFilter(self.message_observer)

    def tearDown(self):
        try:
            for name in reversed(self.names):
                if name in App.listDocuments():
                    self._close_document(name)
            self._events(100)
            output = []
            for widget, previous in self.reports:
                current = widget.toPlainText()
                output.append(current[len(previous):] if current.startswith(previous) else current)
            self.assertTrue(self.reports, "Actual Report view must detect native teardown errors")
            self.assertNotIn("access violation",
                             "\n".join(output + self.message_observer.messages).lower())
        finally:
            QtWidgets.QApplication.instance().removeEventFilter(self.message_observer)

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

    @staticmethod
    def _page_views(page):
        window = Gui.getMainWindow()
        return [widget for widget in window.findChildren(QtWidgets.QGraphicsView)
                if widget.objectName() == page.Name + "View"
                and widget.scene() is not None and widget.isVisibleTo(window)]

    def _caption(self, doc):
        widgets = self._page_views(doc.Page)
        self.assertTrue(widgets, "An actual visible PageView is required")
        widget = widgets[0]
        captions = [item.toGraphicsObject() for item in widget.scene().items()
                    if item.type() == 65548]
        captions = [item for item in captions
                    if isinstance(item, QtWidgets.QGraphicsTextItem)
                    and item.toPlainText() == "Front"]
        self.assertEqual(len(captions), 1, "The exact Front caption must be rendered")
        self.assertFalse(ownedByPython(captions[0]), "Native caption must remain C++ owned")
        return widget, captions[0]

    def _text_items(self, page):
        texts = []
        for widget in self._page_views(page):
            for item in widget.scene().items():
                text_item = (item if isinstance(item, QtWidgets.QGraphicsTextItem)
                             else item.toGraphicsObject())
                if isinstance(text_item, QtWidgets.QGraphicsTextItem):
                    texts.append(text_item.toPlainText())
        return texts

    def _assert_rendered(self, doc, count):
        doc.Page.ViewObject.show()
        self.assertTrue(self._wait(lambda: any(
            widget.scene().items() for widget in self._page_views(doc.Page))),
            "Page must have a visible graphics view with a populated scene")
        for index in range(1, count + 1):
            view = doc.getObject("View" if index == 1 else "PeerView" + str(index))
            caption = "Front" if index == 1 else "Peer " + str(index)
            self.assertIsNotNone(view)
            self.assertEqual(view.Caption, caption)
            self.assertTrue(self._wait(lambda: len(view.getVisibleEdges()) == 4),
                            "Every box view must have four visible outline edges")
            self.assertTrue(self._wait(lambda: caption in self._text_items(doc.Page)),
                            "Every exact caption must appear in the actual page scene")
            self.assertNotIn("Invalid", view.State)
        self._events(100)

    def _page_with_views(self, count):
        doc = App.newDocument("ViewSelectionTeardown")
        self.names.append(doc.Name)
        box = doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 20, 10, 5
        page = doc.addObject("TechDraw::DrawPage", "Page")
        template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        page.Template = template
        for index in range(1, count + 1):
            view = doc.addObject("TechDraw::DrawViewPart",
                                 "View" if index == 1 else "PeerView" + str(index))
            page.addView(view)
            view.Source = [box]
            view.Direction = App.Vector(0, -1, 0)
            view.ScaleType = "Custom"
            view.Scale = 2
            view.X, view.Y = 55 + 80 * (index - 1), 80
            view.Caption = "Front" if index == 1 else "Peer " + str(index)
        doc.recompute()
        self._assert_rendered(doc, count)
        widget, caption = self._caption(doc)
        # Center using scene coordinates, without wrapping the custom parent item.
        widget.centerOn(caption.scenePos())
        self._events(100)
        self.assertFalse(self._caption(doc)[1].isSelected())
        return doc

    def _mouse(self, viewport, event_type, position, button, buttons):
        event = QtGui.QMouseEvent(event_type, QtCore.QPointF(position),
                                 QtCore.QPointF(viewport.mapToGlobal(position)),
                                 button, buttons, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(viewport, event)
        self._events(25)

    def _select_caption(self, doc):
        widget, caption = self._caption(doc)
        viewport = widget.viewport()
        center = widget.mapFromScene(caption.mapToScene(caption.boundingRect().center()))
        self.assertTrue(viewport.rect().contains(center), "Caption must be in actual viewport")
        self._mouse(viewport, QtCore.QEvent.MouseButtonPress, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._mouse(viewport, QtCore.QEvent.MouseButtonRelease, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        _, caption = self._caption(doc)
        self.assertTrue(caption.isSelected(), "Actual viewport click must select the caption")
        self.assertFalse(caption.hasFocus())
        self.assertEqual(caption.textInteractionFlags(), QtCore.Qt.NoTextInteraction)

    def _store_unhovered_mouse_move(self, doc):
        # Leave the view, then let it store a mouse move over the caption
        # without dispatching it. Closing the page scrolls the view, which
        # replays that move as a hover enter after the Gui document is gone.
        widget, caption = self._caption(doc)
        viewport = widget.viewport()
        center = widget.mapFromScene(caption.mapToScene(caption.boundingRect().center()))
        QtWidgets.QApplication.sendEvent(viewport, QtCore.QEvent(QtCore.QEvent.Leave))
        self._events(25)
        widget.setInteractive(False)
        try:
            self._mouse(viewport, QtCore.QEvent.MouseMove, center,
                        QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        finally:
            widget.setInteractive(True)

    def _observe_selection(self, scene, name):
        states = []

        def selection_changed():
            # An external observer must survive the native view disconnect.
            # During teardown, only query application document membership.
            states.append(name in App.listDocuments())

        scene.selectionChanged.connect(selection_changed)
        self.external_slots.append(selection_changed)
        return states

    def _close_document(self, name):
        doc = App.getDocument(name)
        owned_views = self._page_views(doc.Page)
        owned_scenes = [widget.scene() for widget in owned_views]
        owned_captions = [item.toGraphicsObject()
                          for scene in owned_scenes for item in scene.items()
                          if item.type() == 65548]
        App.closeDocument(name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self._events(30)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertTrue(all(not isValid(widget) for widget in owned_views),
                        "Ordinary close must release the actual PageView")
        self.assertTrue(all(not isValid(scene) for scene in owned_scenes),
                        "Ordinary close must release the actual page scene")
        self.assertTrue(all(not isValid(caption) for caption in owned_captions),
                        "Ordinary close must release the native captions")

    def _selected_close(self, count):
        doc = self._page_with_views(count)
        widget, _ = self._caption(doc)
        states = self._observe_selection(widget.scene(), doc.Name)
        self._select_caption(doc)
        self.assertIn(True, states, "External observer must see ordinary live selection")
        before_close = len(states)
        self._close_document(doc.Name)
        self.assertIn(False, states[before_close:],
                      "External observer must receive teardown selection changes")

    def test_unselected_two_view_close_control(self):
        doc = self._page_with_views(2)
        self._close_document(doc.Name)

    def test_selected_single_view_close(self):
        self._selected_close(1)

    def test_selected_two_view_close(self):
        self._selected_close(2)

    def test_selected_three_view_close(self):
        self._selected_close(3)

    def test_hover_replayed_during_close(self):
        doc = self._page_with_views(1)
        self._select_caption(doc)
        self._store_unhovered_mouse_move(doc)
        self._close_document(doc.Name)

    def test_delete_selected_view_and_undo_preserves_live_peer(self):
        doc = self._page_with_views(2)
        doc.UndoMode = 1
        widget, caption = self._caption(doc)
        scene = widget.scene()
        states = self._observe_selection(scene, doc.Name)
        self._select_caption(doc)
        self.assertIn(True, states)
        before_delete = len(states)
        doc.openTransaction("Delete selected drawing view")
        doc.removeObject("View")
        doc.commitTransaction()
        doc.recompute()
        self._events(100)
        self.assertIsNone(doc.getObject("View"))
        self.assertTrue(isValid(scene), "Deleting a view must keep its live page scene")
        self.assertFalse(isValid(caption), "Deleting a view must release its caption")
        self.assertIn(True, states[before_delete:],
                      "External observer must receive live deletion selection changes")
        self.assertEqual(len(doc.PeerView2.getVisibleEdges()), 4)
        self.assertNotIn("Invalid", doc.PeerView2.State)
        self.assertIn("Peer 2", self._text_items(doc.Page))

        doc.undo()
        doc.recompute()
        self._assert_rendered(doc, 2)
        self.assertEqual({view.Name for view in doc.Page.Views}, {"View", "PeerView2"})
        self.assertTrue(isValid(scene), "Undo must retain the ordinary live page scene")
        self.assertIs(self._caption(doc)[0].scene(), scene)
