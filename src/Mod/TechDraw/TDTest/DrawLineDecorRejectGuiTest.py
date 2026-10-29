# SPDX-License-Identifier: LGPL-2.1-or-later
"""Cancelling the line appearance task removes the formats it created.

TechDraw_DecorateLine gives every selected edge without a format a new
GeomFormat. Cancelling the task removes it again with removeGeomFormat(),
which deleted the entry itself although GeomFormats.setValues() also deletes
the old entries: the same format was deleted twice (heap corruption, the
test process crashes or aborts).
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class DrawLineDecorRejectGuiTest(unittest.TestCase):
    def setUp(self):
        # A modal message would block the test, record and dismiss it instead
        self.messages = []
        self.dismiss_timer = QtCore.QTimer()
        self.dismiss_timer.timeout.connect(self._dismiss_messages)
        self.dismiss_timer.start(50)
        self.addCleanup(self.dismiss_timer.stop)

        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("LineDecorReject")
        self.addCleanup(self._close)
        box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = App.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: len(self.view.getVisibleEdges()) == 4))
        self.assertEqual(len(self.view.GeomFormats), 0)

    def _dismiss_messages(self):
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                self.messages.append(widget.text())
                widget.reject()

    def _close(self):
        Gui.Selection.clearSelection()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _wait(self, predicate, ms=5000):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while timer.elapsed() < ms:
            QtWidgets.QApplication.processEvents()
            if predicate():
                return True
        return predicate()

    def _open_task(self, edges):
        Gui.Selection.clearSelection()
        for edge in edges:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name, edge)
        Gui.runCommand("TechDraw_DecorateLine")
        self.assertTrue(
            self._wait(lambda: Gui.Control.activeTaskDialog() is not None), self.messages
        )

    def _cancel_task(self):
        Gui.Control.activeTaskDialog().reject()
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is None))

    def testCancelRemovesCreatedFormat(self):
        self._open_task(["Edge0"])
        self.assertEqual(len(self.view.GeomFormats), 1, "The task gives the edge a format")
        self._cancel_task()
        self.assertEqual(len(self.view.GeomFormats), 0, "Cancel removes the created format")
        self.doc.recompute()

    def testCancelKeepsOtherFormats(self):
        self.view.formatGeometricEdge(1, 2, 0.5, App.Vector(1, 0, 0), True)
        self.doc.recompute()
        self.assertEqual(len(self.view.GeomFormats), 1)
        kept = self.view.GeomFormats[0].Tag

        for _ in range(2):
            self._open_task(["Edge0", "Edge2"])
            self.assertEqual(len(self.view.GeomFormats), 3)
            self._cancel_task()
            formats = self.view.GeomFormats
            self.assertEqual([gf.Tag for gf in formats], [kept])
            self.doc.recompute()


if __name__ == "__main__":
    unittest.main()
