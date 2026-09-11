# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exercise the native editor through Qt events and its actual task controls."""

import unittest
import FreeCAD as App


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestGordonSurfaceGui(unittest.TestCase):
    def setUp(self):
        import FreeCADGui as Gui
        from PySide import QtCore, QtGui, QtWidgets

        self.Gui, self.Core, self.GuiQt = Gui, QtCore, QtGui
        self.Widgets = QtWidgets
        self.previousWorkbench = Gui.activeWorkbench().name()
        Gui.activateWorkbench("SurfaceWorkbench")
        self.doc = App.newDocument("CurveEditorTest")
        self.curve = self.doc.addObject("Surface::FreehandBSpline", "Curve")
        self.curve.Points = [
            App.Vector(0, 0, 0),
            App.Vector(10, 10, 0),
            App.Vector(20, 0, 0),
            App.Vector(30, 5, 0),
        ]
        self.doc.recompute()
        QtWidgets.QApplication.processEvents()
        self.view = Gui.getDocument(self.doc.Name).activeView()
        self.view.viewTop()
        self.view.fitAll()
        Gui.getDocument(self.doc.Name).setEdit(self.curve.Name)
        QtWidgets.QApplication.processEvents()
        self.panel = Gui.getMainWindow().findChild(QtWidgets.QWidget, "FreehandBSplineEditor")
        self.assertIsNotNone(self.panel)
        self.table = self.panel.findChild(QtWidgets.QTableWidget, "interpolationPoints")
        self.gl = max(
            (
                w
                for w in Gui.getMainWindow().findChildren(QtWidgets.QWidget)
                if w.metaObject().className() == "QOpenGLWidget"
            ),
            key=lambda w: w.width() * w.height(),
        )

    def tearDown(self):
        guiDoc = self.Gui.getDocument(self.doc.Name)
        if guiDoc.getInEdit():
            self.doc.abortTransaction()
            guiDoc.resetEdit()
        self.Core.QCoreApplication.sendPostedEvents(None, self.Core.QEvent.DeferredDelete)
        App.closeDocument(self.doc.Name)
        self.Gui.activateWorkbench(self.previousWorkbench)

    def screen(self, point):
        x, y = self.view.getPointOnScreen(point)
        ratio = self.gl.devicePixelRatioF()
        return self.Core.QPointF(x / ratio, self.gl.height() - y / ratio)

    def mouse(self, kind, pos, button=None, buttons=None, modifiers=None):
        qt = self.Core.Qt
        event = self.GuiQt.QMouseEvent(
            kind,
            pos,
            self.gl.mapToGlobal(pos.toPoint()),
            button or qt.NoButton,
            buttons or qt.NoButton,
            modifiers or qt.NoModifier,
        )
        self.Widgets.QApplication.sendEvent(self.gl, event)

    def click(self, pos, modifiers=None):
        qt, event = self.Core.Qt, self.Core.QEvent
        self.mouse(event.MouseButtonPress, pos, qt.LeftButton, qt.LeftButton, modifiers)
        self.mouse(event.MouseButtonRelease, pos, qt.LeftButton, modifiers=modifiers)

    def key(self, key, modifiers=None):
        event = self.GuiQt.QKeyEvent(
            self.Core.QEvent.KeyPress, key, modifiers or self.Core.Qt.NoModifier
        )
        self.Widgets.QApplication.sendEvent(self.gl, event)

    def drag(self, pos, delta, modifiers=None, key=None):
        qt, event = self.Core.Qt, self.Core.QEvent
        self.mouse(event.MouseButtonPress, pos, qt.LeftButton, qt.LeftButton)
        if key is not None:
            self.key(key)
        self.mouse(event.MouseMove, pos + delta, buttons=qt.LeftButton, modifiers=modifiers)
        self.mouse(event.MouseButtonRelease, pos + delta, qt.LeftButton)

    def button(self, name):
        return self.panel.findChild(self.Widgets.QPushButton, name)

    def finish(self, accept=False):
        role = self.Widgets.QDialogButtonBox.Ok if accept else self.Widgets.QDialogButtonBox.Cancel
        boxes = self.Gui.getMainWindow().findChildren(self.Widgets.QDialogButtonBox)
        button = next(
            box.button(role)
            for box in boxes
            if box.button(role) is not None and box.button(role).isVisible()
        )
        button.click()
        self.Widgets.QApplication.processEvents()

    def test_gordon_task_assignment_and_undo(self):
        import Part

        self.finish()
        profiles, guides = [], []
        for y in (0, 10):
            profile = self.doc.addObject("Part::Feature", "Profile")
            profile.Shape = Part.makeLine(App.Vector(0, y, 0), App.Vector(10, y, 0))
            profiles.append(profile)
        for x in (0, 10):
            guide = self.doc.addObject("Part::Feature", "Guide")
            guide.Shape = Part.makeLine(App.Vector(x, 0, 0), App.Vector(x, 10, 0))
            guides.append(guide)
        self.doc.recompute()
        self.Gui.runCommand("Surface_GordonSurface")
        self.Widgets.QApplication.processEvents()
        panel = self.Gui.getMainWindow().findChild(self.Widgets.QWidget, "GordonSurfaceEditor")
        self.assertIsNotNone(panel)
        for objects, button in ((profiles, "profilesAdd"), (guides, "guidesAdd")):
            self.Gui.Selection.clearSelection()
            for obj in objects:
                self.Gui.Selection.addSelection(obj)
            panel.findChild(self.Widgets.QPushButton, button).click()
        panel.findChild(self.Widgets.QPushButton, "updatePreview").click()
        self.assertEqual(len(self.doc.GordonSurface.Shape.Faces), 1)
        self.finish(True)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject("GordonSurface"))
        self.doc.redo()
        self.assertEqual(len(self.doc.GordonSurface.Shape.Faces), 1)
