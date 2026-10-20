# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual scene positions and interaction locks for TechDraw views."""

from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDrawGui
from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewPositionTest(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.doc = App.newDocument("ViewPositionRegression")
        self.addCleanup(self.close_document)
        self.addCleanup(Gui.Selection.clearSelection)
        self.page = createPageWithSVGTemplate(self.doc)
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = Part.makeBox(10, 10, 10)
        for name, x, locked in (("Locked", 150, True), ("Unlocked", 250, False)):
            view = self.doc.addObject("TechDraw::DrawViewPart", name)
            view.Source = [source]
            view.Direction = App.Vector(0, 0, 1)
            view.ScaleType = "Custom"
            view.Scale = 1
            self.page.addView(view)
            view.X, view.Y = x, 100
            view.LockPosition = locked
        self.doc.recompute()
        self.page.ViewObject.show()
        self.wait_for(lambda: all(self.doc.getObject(name).getVisibleEdges()
                                 and "Up-to-date" in self.doc.getObject(name).State
                                 for name in ("Locked", "Unlocked")))
        self.stable_positions()

    def close_document(self):
        if self.doc is not None:
            App.closeDocument(self.doc.Name)
            self.doc = None

    @staticmethod
    def process_events(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def wait_for(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "Drawing did not settle")
            self.process_events()

    def item(self, name):
        scene = TechDrawGui.getSceneForPage(self.page)
        items = [item for item in scene.items()
                 if item.data(0) == "QGIV" and item.data(1) == name]
        self.assertEqual(len(items), 1, name)
        return items[0]

    def positions(self):
        result = {}
        for name in ("Locked", "Unlocked"):
            point = self.item(name).scenePos()
            result[name] = (point.x(), point.y())
        return result

    def stable_positions(self):
        previous = None
        stable = 0
        deadline = time.monotonic() + 10
        while stable < 3:
            current = self.positions()
            stable = stable + 1 if current == previous else 0
            previous = current
            self.assertLess(time.monotonic(), deadline, current)
            self.process_events()
        return current

    def check_restore(self, hidden_page):
        before = self.stable_positions()
        self.assertGreater(abs(before["Locked"][0]), 1)
        self.assertAlmostEqual(before["Locked"][0] / before["Unlocked"][0], 150 / 250)
        if hidden_page:
            self.page.ViewObject.hide()
        filename = Path(self.storage.name) / "locked_views.FCStd"
        self.doc.saveAs(str(filename))
        self.close_document()
        self.doc = App.openDocument(str(filename))
        self.page = self.doc.Page
        self.page.ViewObject.show()
        self.wait_for(lambda: all(self.doc.getObject(name).getVisibleEdges()
                                 and "Up-to-date" in self.doc.getObject(name).State
                                 for name in ("Locked", "Unlocked")))
        after = self.stable_positions()
        for name, x, locked in (("Unlocked", 250, False), ("Locked", 150, True)):
            with self.subTest(view=name, hidden_page=hidden_page):
                view = self.doc.getObject(name)
                self.assertEqual((view.X.Value, view.Y.Value), (x, 100))
                self.assertEqual(view.LockPosition, locked)
                self.assertAlmostEqual(after[name][0], before[name][0])
                self.assertAlmostEqual(after[name][1], before[name][1])

    def testRestoreLockedAndUnlockedScenePositions(self):
        self.check_restore(False)

    def testRestoreHiddenPageScenePositions(self):
        self.check_restore(True)

    def drag_view(self, name):
        """Send real scene mouse events through the graphics item's drag handlers."""
        item = self.item(name)
        scene = item.scene()
        start = item.boundingRect().center()
        start_scene = item.mapToScene(start)
        end_scene = start_scene + QtCore.QPointF(200, 200)
        button = QtCore.Qt.LeftButton
        for kind, point in ((QtCore.QEvent.GraphicsSceneMousePress, start_scene),
                            (QtCore.QEvent.GraphicsSceneMouseMove, end_scene),
                            (QtCore.QEvent.GraphicsSceneMouseRelease, end_scene)):
            event = QtWidgets.QGraphicsSceneMouseEvent(kind)
            event.setButton(button if kind != QtCore.QEvent.GraphicsSceneMouseMove
                            else QtCore.Qt.NoButton)
            event.setButtons(button if kind != QtCore.QEvent.GraphicsSceneMouseRelease
                             else QtCore.Qt.NoButton)
            event.setPos(item.mapFromScene(point))
            event.setScenePos(point)
            event.setLastPos(item.mapFromScene(start_scene))
            event.setLastScenePos(start_scene)
            event.setButtonDownPos(button, start)
            event.setButtonDownScenePos(button, start_scene)
            scene.sendEvent(item, event)
        self.process_events()

    def check_lock(self, name, locked):
        view = self.doc.getObject(name)
        view.LockPosition = locked
        movable = QtWidgets.QGraphicsItem.ItemIsMovable
        self.wait_for(lambda: bool(self.item(name).flags() & movable) != locked)
        self.assertEqual("ReadOnly" in view.getEditorMode("X"), locked)
        self.assertEqual("ReadOnly" in view.getEditorMode("Y"), locked)
        before_scene = self.positions()[name]
        before_model = (view.X.Value, view.Y.Value)
        self.drag_view(name)
        self.assertEqual(view.LockPosition, locked)
        after_scene = self.positions()[name]
        after_model = (view.X.Value, view.Y.Value)
        if locked:
            self.assertEqual(after_scene, before_scene)
            self.assertEqual(after_model, before_model)
        else:
            self.assertNotEqual(after_scene, before_scene)
            self.assertNotEqual(after_model, before_model)
        Gui.Selection.clearSelection()

    def testInteractiveLockPreventsDragging(self):
        for name, locked in (("Locked", True), ("Unlocked", False),
                             ("Locked", False), ("Locked", True)):
            with self.subTest(view=name, locked=locked):
                self.check_lock(name, locked)

    def testExplicitCoordinatesKeepLockedSceneSynchronized(self):
        """Explicit model assignments remain possible without unlocking mouse movement."""
        view = self.doc.Locked
        scale = self.positions()["Unlocked"][0] / self.doc.Unlocked.X.Value
        view.X, view.Y = 160, 105
        self.assertEqual((view.X.Value, view.Y.Value), (160, 105))
        self.assertTrue(view.LockPosition)
        self.assertIn("ReadOnly", view.getEditorMode("X"))
        self.assertIn("ReadOnly", view.getEditorMode("Y"))
        self.assertFalse(self.item("Locked").flags() & QtWidgets.QGraphicsItem.ItemIsMovable)
        after = self.stable_positions()["Locked"]
        self.assertAlmostEqual(after[0], 160 * scale)
        self.assertAlmostEqual(after[1], -105 * scale)
