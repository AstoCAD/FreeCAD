# SPDX-License-Identifier: LGPL-2.1-or-later

"""Exercise caption restoration through ordinary native GUI page lifecycles."""

import hashlib
from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part  # noqa: F401
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtWidgets

try:
    from shiboken6 import isValid
except ImportError:
    from shiboken2 import isValid

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


class _CaptionGuiTestCase(unittest.TestCase):
    def setUp(self):
        self.names = []
        self.directory = tempfile.TemporaryDirectory(prefix="td_caption_")
        self.reports = [(widget, widget.toPlainText())
                        for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
                        if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.message_observer = _MessageObserver()
        QtWidgets.QApplication.instance().installEventFilter(self.message_observer)

    def _close_document(self, name):
        doc = App.getDocument(name)
        page = doc.getObject("Page")
        owned_views = self._page_views(page) if page is not None else []
        App.closeDocument(name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self._events(30)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self.assertTrue(all(not isValid(widget) for widget in owned_views),
                        "Ordinarily closed document must release its actual PageView")

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
            self.assertTrue(self.reports, "Actual Report view must detect native caption errors")
            self.assertNotIn("access violation",
                             "\n".join(output + self.message_observer.messages).lower())
        finally:
            QtWidgets.QApplication.instance().removeEventFilter(self.message_observer)
            self.directory.cleanup()

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

    def _text_items(self, page):
        result = []
        for widget in self._page_views(page):
            for item in widget.scene().items():
                # TechDraw custom type() values expose a QGraphicsItem wrapper.
                # Qt discovers the actual QObject-backed text item safely.
                text_item = (item if isinstance(item, QtWidgets.QGraphicsTextItem)
                             else item.toGraphicsObject())
                if isinstance(text_item, QtWidgets.QGraphicsTextItem):
                    result.append(text_item.toPlainText())
        return result

    def _open(self, path):
        doc = App.openDocument(str(path))
        self.names.append(doc.Name)
        return doc

    def _assert_rendered(self, doc, expected_caption):
        self.assertEqual(doc.View.Caption, expected_caption)
        doc.Page.ViewObject.show()
        self.assertTrue(self._wait(lambda: len(doc.View.getVisibleEdges()) == 4),
                        "Expected four visible box-outline edges")
        self.assertTrue(self._wait(lambda: any(
            widget.scene().items() for widget in self._page_views(doc.Page))),
            "Page must have a visible graphics view with a populated scene")
        if expected_caption:
            self.assertTrue(self._wait(lambda: expected_caption in self._text_items(doc.Page)),
                            "Exact caption must appear in the actual page scene")
        self._events(200)
        self.assertNotIn("Invalid", doc.View.State)

    def _stock_page(self):
        doc = App.newDocument("CaptionRestore33134")
        self.names.append(doc.Name)
        box = doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 20, 10, 5
        page = doc.addObject("TechDraw::DrawPage", "Page")
        template = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        page.Template = template
        view = doc.addObject("TechDraw::DrawViewPart", "View")
        page.addView(view)
        view.Source = [box]
        view.Direction = App.Vector(0, -1, 0)
        view.ScaleType = "Custom"
        view.Scale = 2
        view.X, view.Y = 80, 80
        doc.recompute()
        self._assert_rendered(doc, "")
        return doc

    def _stock_roundtrip(self, caption):
        doc = self._stock_page()
        doc.View.Caption = caption
        self._assert_rendered(doc, caption)
        path = Path(self.directory.name) / "saved.FCStd"
        doc.saveAs(str(path))
        self._events(200)
        self._close_document(doc.Name)
        self._events(100)
        self._assert_rendered(self._open(path), caption)


class DrawViewCaptionGuiTest(_CaptionGuiTestCase):
    def _published(self, filename, expected_hash):
        path = TDTEST / filename
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected_hash)
        return self._open(path)

    def test_published_empty_caption_control(self):
        doc = self._published(
            "TestCaptionRestore33134Empty.FCStd",
            "53b1aaa3f1f743cadc9391e31303e37fa1e808a2e04371ed801ecb67bd69e070")
        self._assert_rendered(doc, "")

    def test_published_caption_archive(self):
        doc = self._published(
            "TestCaptionRestore33134.FCStd",
            "b4b02a29752352e945c1758c7c6bae10bd4b16c844d27229fbf4d9e25b3908e4")
        self._assert_rendered(doc, "Front")

    def test_stock_empty_caption_save_reopen_control(self):
        self._stock_roundtrip("")

    def test_stock_caption_save_reopen(self):
        self._stock_roundtrip("Front")
