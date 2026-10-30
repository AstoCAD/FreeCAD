# SPDX-License-Identifier: LGPL-2.1-or-later
"""Fillet on a vertex between two curves explains why it is not possible (#24562)."""

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtWidgets

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestFilletCurveVertexGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        # Show notifications as message boxes so that the test can see them.
        self.notifParams = App.ParamGet(
            "User parameter:BaseApp/Preferences/NotificationArea"
        )
        self.hadNonIntrusive = "NonIntrusiveNotificationsEnabled" in self.notifParams.GetBools()
        self.oldNonIntrusive = self.notifParams.GetBool("NonIntrusiveNotificationsEnabled", True)
        self.notifParams.SetBool("NonIntrusiveNotificationsEnabled", False)

        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("FilletCurveVertexTest")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")

    def tearDown(self):
        try:
            if self.hadNonIntrusive:
                self.notifParams.SetBool("NonIntrusiveNotificationsEnabled", self.oldNonIntrusive)
            else:
                self.notifParams.RemBool("NonIntrusiveNotificationsEnabled")
        finally:
            super().tearDown()

    def startEditing(self):
        self.doc.recompute()
        Gui.getMainWindow().show()
        self.assertTrue(Gui.getDocument(self.doc.Name).setEdit(self.sketch.Name))
        self.flush_gui(200)
        view = Gui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self.flush_gui(150)
        return view

    def clickVertex(self, view, point):
        """Click the vertex at point with the fillet tool, and return the message boxes seen."""
        viewport = view.graphicsView().viewport()
        target = self.clamp_to_widget(
            viewport,
            self.viewport_to_qpoint(view, viewport, view.getPointOnScreen(point)),
        )
        Gui.Selection.clearSelection()
        Gui.runCommand("Sketcher_CreateFillet")
        self.flush_gui(200)

        seen = []

        def closeMessageBox():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                seen.append(modal.text())
                modal.accept()

        closer = QtCore.QTimer(Gui.getMainWindow())
        closer.timeout.connect(closeMessageBox)
        closer.start(25)
        try:
            self.move(viewport, target)
            self.move(viewport, target)
            self.click(viewport, target)
            self.flush_gui(200)
        finally:
            closer.stop()
            closer.deleteLater()
        return seen

    def testCurveVertexShowsWarning(self):
        # Two arcs meeting at (10, 0).
        self.sketch.addGeometry(
            Part.ArcOfCircle(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), 0, 1.5)
        )
        self.sketch.addGeometry(
            Part.ArcOfCircle(Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 10), 1.6, 3.14159265)
        )
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 2))
        view = self.startEditing()
        geometryCount = self.sketch.GeometryCount

        seen = self.clickVertex(view, App.Vector(10, 0, 0))

        self.assertEqual(len(seen), 1, "Expected one warning about the curve vertex")
        self.assertIn("only works between two lines", seen[0])
        self.assertEqual(self.sketch.GeometryCount, geometryCount)
        self.assertEqual(Gui.Selection.getSelectionEx(), [])

    def testLineVertexStillFillets(self):
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        self.sketch.addGeometry(Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 10, 0)))
        self.sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
        view = self.startEditing()
        geometryCount = self.sketch.GeometryCount

        seen = self.clickVertex(view, App.Vector(10, 0, 0))

        self.assertEqual(seen, [])
        self.assertTrue(
            self.wait_until(lambda: self.sketch.GeometryCount > geometryCount, timeout_ms=2000),
            "Expected a fillet at the vertex between two lines",
        )
