# SPDX-License-Identifier: LGPL-2.1-or-later
"""Centerline commands tolerate selected edges removed by a source edit."""

import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawBoltCircleTest(unittest.TestCase):
    def setUp(self):
        previous_workbench = Gui.activeWorkbench().name()
        self.addCleanup(Gui.activateWorkbench, previous_workbench)
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("BoltCircleRegression")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.addCleanup(Gui.Selection.clearSelection)
        self.source = self.doc.addObject("Part::Feature", "Source")
        self.circles = [Part.makeCircle(1, App.Vector(*center))
                        for center in ((-5, 0, 0), (5, 0, 0), (0, 5, 0), (0, -5, 0))]
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.page_shown = False

    def setCircleCount(self, count):
        self.source.Shape = Part.makeCompound(self.circles[:count])
        self.doc.recompute()
        deadline = time.monotonic() + 20
        while (len(self.view.getVisibleEdges()) != count
               or "Up-to-date" not in self.view.State):
            self.assertLess(time.monotonic(), deadline, self.view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()
        if not self.page_shown:
            self.page.ViewObject.show()
            self.page_shown = True
        Gui.updateGui()

    def selectEdges(self, *indices):
        Gui.Selection.clearSelection()
        for index in indices:
            Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Edge" + str(index))

    def selectedEdges(self):
        return tuple(name for item in Gui.Selection.getSelectionEx()
                     if item.ObjectName == self.view.Name for name in item.SubElementNames)

    def runCommand(self, command):
        messages, exceptions = [], []

        class MessageObserver(QtCore.QObject):
            def eventFilter(self, watched, event):
                if (event.type() == QtCore.QEvent.Show
                        and isinstance(watched, QtWidgets.QMessageBox)):
                    messages.append(watched.text())
                return False

        reports = [widget for widget in Gui.getMainWindow().findChildren(QtWidgets.QTextEdit)
                   if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.assertTrue(reports, "The actual Report view must be available to detect native errors")
        before = [widget.toPlainText() for widget in reports]
        observer = MessageObserver()
        QtWidgets.QApplication.instance().installEventFilter(observer)

        def dismiss_warning():
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                    widget.reject()

        timer = QtCore.QTimer()
        timer.timeout.connect(dismiss_warning)
        timer.start(25)
        try:
            Gui.runCommand(command)
        except Exception as error:
            exceptions.append((type(error).__name__, str(error)))
        finally:
            timer.stop()
            timer.deleteLater()
            QtWidgets.QApplication.instance().removeEventFilter(observer)
        Gui.updateGui()
        output = []
        for widget, previous in zip(reports, before):
            current = widget.toPlainText()
            output.append(current[len(previous):] if current.startswith(previous) else current)
        self.assertFalse(exceptions)
        self.assertNotIn("access violation", "\n".join(messages + output).lower())
        return messages

    def snapshot(self):
        return (tuple(obj.Name for obj in self.doc.Objects), tuple(self.page.Views),
                len(self.view.CosmeticEdges), tuple(edge.Length for edge in self.source.Shape.Edges))

    def testThreeCircleControl(self):
        self.setCircleCount(3)
        self.selectEdges(0, 1, 2)
        self.assertFalse(self.runCommand("TechDraw_ExtensionHoleCircle"))
        self.assertEqual(len(self.view.CosmeticEdges), 4)

    def testStaleSelectedEdgeAfterSourceShrink(self):
        self.setCircleCount(3)
        self.selectEdges(2)
        self.setCircleCount(1)
        self.assertEqual(self.selectedEdges(), ("Edge2",))
        before = self.snapshot()
        messages = self.runCommand("TechDraw_ExtensionHoleCircle")
        expected = QtCore.QCoreApplication.translate("QObject", "Fewer than three circles selected")
        self.assertIn(expected, messages)
        self.assertEqual(self.snapshot(), before)

    def testValidCirclesWithStaleSelectedEdge(self):
        self.setCircleCount(4)
        self.selectEdges(0, 1, 2, 3)
        self.setCircleCount(3)
        self.assertEqual(self.selectedEdges(), ("Edge0", "Edge1", "Edge2", "Edge3"))
        self.assertFalse(self.runCommand("TechDraw_ExtensionHoleCircle"))
        self.assertEqual(len(self.view.CosmeticEdges), 4)

    def testCircleCenterlineStaleSelectionControl(self):
        self.setCircleCount(3)
        self.selectEdges(2)
        self.setCircleCount(1)
        self.assertEqual(self.selectedEdges(), ("Edge2",))
        before = self.snapshot()
        self.assertFalse(self.runCommand("TechDraw_ExtensionCircleCenterLines"))
        self.assertEqual(self.snapshot(), before)
