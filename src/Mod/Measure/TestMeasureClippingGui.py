# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measurement annotations are not cut by clipping planes (issue #22542)."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import MeasureGui  # noqa: F401
from PySide import QtCore, QtWidgets
from pivy import coin

try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestMeasureClippingGui(unittest.TestCase):
    def setUp(self):
        previous = App.activeDocument()
        self.previous_document = previous.Name if previous else None
        self.doc = App.newDocument("MeasureClippingTest")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.measure = self.doc.addObject("Measure::MeasureDistanceDetached", "Distance")
        self.measure.Position1 = App.Vector(0, 0, 0)
        self.measure.Position2 = App.Vector(10, 10, 10)
        self.doc.recompute()
        self._pump()
        self.view = Gui.getDocument(self.doc.Name).activeView()

    def tearDown(self):
        if self.view.hasClippingPlane():
            self.view.toggleClippingPlane(0)
        self._close_clipping_dialog()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _pump(self):
        Gui.updateGui()
        QtTest.QTest.qWait(50)
        Gui.updateGui()

    def _clipping_docks(self):
        return [dock for dock in Gui.getMainWindow().findChildren(QtWidgets.QDockWidget)
                if dock.objectName() == "Clipping"]

    def _close_clipping_dialog(self):
        for dock in self._clipping_docks():
            dock.widget().reject()
        clock = QtCore.QElapsedTimer()
        clock.start()
        while self._clipping_docks() and clock.elapsed() < 2500:
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._pump()

    def _clip_planes_above(self, node):
        """Return the clip planes that apply to node when traversing the scene graph."""
        search = coin.SoSearchAction()
        search.setNode(node)
        search.setSearchingAll(True)
        search.apply(self.view.getSceneGraph())
        path = search.getPath()
        self.assertIsNotNone(path, "Node is not in the scene graph")
        path = coin.SoFullPath.fromSoPath(path)
        planes = []
        for i in range(path.getLength() - 1):
            parent = path.getNode(i)
            for j in range(path.getIndex(i + 1)):
                child = parent.getChild(j)
                if child.isOfType(coin.SoClipPlane.getClassTypeId()):
                    planes.append(child)
        return planes

    def _check(self):
        box_root = self.box.ViewObject.RootNode
        measure_root = self.measure.ViewObject.RootNode
        self.assertTrue(self._clip_planes_above(box_root), "The box must be clipped")
        self.assertEqual(self._clip_planes_above(measure_root), [],
                         "The measurement annotation must not be clipped")

    def test_toggle_clipping_plane(self):
        self.assertEqual(self._clip_planes_above(self.measure.ViewObject.RootNode), [])
        for before_editing in (False, True):
            with self.subTest(beforeEditing=before_editing):
                self.view.toggleClippingPlane(1, beforeEditing=before_editing)
                try:
                    self._check()
                finally:
                    self.view.toggleClippingPlane(0)

    def test_clipping_dialog(self):
        Gui.runCommand("Std_ToggleClipPlane")
        self._pump()
        self.assertEqual(len(self._clipping_docks()), 1, "Clipping dialog did not open")
        self._check()
        self._close_clipping_dialog()
        self.assertEqual(self._clipping_docks(), [])
        self.assertEqual(self._clip_planes_above(self.box.ViewObject.RootNode), [])
