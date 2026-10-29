# SPDX-License-Identifier: LGPL-2.1-or-later

"""Annotations keep consecutive spaces on the page."""

from pathlib import Path
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import TechDraw  # noqa: F401
import TechDrawGui  # noqa: F401
from PySide import QtCore, QtWidgets

try:
    import shiboken6 as shiboken
except ImportError:
    import shiboken2 as shiboken

# TechDrawGui::UserType::QGCustomText (QGIUserTypes.h), a QGraphicsTextItem
QG_CUSTOM_TEXT_TYPE = QtWidgets.QGraphicsItem.UserType + 6


class DrawViewAnnotationSpacesGuiTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("TDAnnotationSpaces")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(Path(__file__).with_name("TestTemplate.svg"))
        self.page.Template = template

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    @staticmethod
    def _events(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._events()
        return bool(predicate())

    def _page_texts(self):
        window = Gui.getMainWindow()
        texts = []
        for view in window.findChildren(QtWidgets.QGraphicsView):
            if view.objectName() != "PageView" or view.scene() is None:
                continue
            for item in view.scene().items():
                if item.type() == QG_CUSTOM_TEXT_TYPE:
                    # QGraphicsTextItem starts with its QObject, not with the QGraphicsItem
                    pointer = shiboken.getCppPointer(item.toGraphicsObject())[0]
                    texts.append(
                        shiboken.wrapInstance(pointer, QtWidgets.QGraphicsTextItem).toPlainText()
                    )
        return texts

    # https://github.com/FreeCAD/FreeCAD/issues/33863
    def testConsecutiveSpacesAreKept(self):
        annotation = self.doc.addObject("TechDraw::DrawViewAnnotation", "Annotation")
        annotation.Text = ["x    x", "xxxxxx"]
        self.page.addView(annotation)
        self.doc.recompute()
        self.page.ViewObject.show()
        self.assertTrue(self._wait(lambda: any("xxxxxx" in text for text in self._page_texts())))
        texts = [text for text in self._page_texts() if "xxxxxx" in text]
        self.assertIn("x    x", texts[0])


if __name__ == "__main__":
    unittest.main()
