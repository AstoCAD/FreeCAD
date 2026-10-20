# SPDX-License-Identifier: LGPL-2.1-or-later
"""Section selection and the workflows that must regenerate its graphics."""

from pathlib import Path
import tempfile
import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import TechDrawGui
from PySide import QtCore, QtGui

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewSectionSelectionTest(unittest.TestCase):
    EDGE_TYPE = 65536 + 19
    FACE_TYPE = 65536 + 20

    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.doc = App.newDocument("SectionSelectionRegression")
        self.addCleanup(self.close_document)
        self.addCleanup(Gui.Selection.clearSelection)
        self.source = self.doc.addObject("Part::Feature", "Source")
        self.source.Shape = Part.makeBox(10, 10, 10)
        self.page = createPageWithSVGTemplate(self.doc)
        self.page.KeepUpdated = True
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.page.addView(self.view)
        self.view.X, self.view.Y = 60, 100
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        self.page.addView(self.section)
        self.section.Source = [self.source]
        self.section.BaseView = self.view
        self.section.Direction = App.Vector(0, 1, 0)
        self.section.SectionNormal = App.Vector(0, 1, 0)
        self.section.SectionOrigin = App.Vector(5, 5, 5)
        self.section.ScaleType = "Custom"
        self.section.Scale = 1
        self.section.X, self.section.Y = 150, 100
        self.doc.recompute()
        self.page.ViewObject.show()
        self.wait_for(lambda: all(view.getVisibleEdges() and "Up-to-date" in view.State
                                 for view in (self.view, self.section)))
        self.stable_paint_state(self.section)

    def close_document(self):
        if self.doc is not None:
            App.closeDocument(self.doc.Name)
            self.doc = None

    @staticmethod
    def process_events(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def wait_for(self, predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "Section drawing did not settle")
            self.process_events()

    def view_item(self, view):
        scene = TechDrawGui.getSceneForPage(self.page)
        items = [item for item in scene.items()
                 if item.data(0) == "QGIV" and item.data(1) == view.Name]
        self.assertEqual(len(items), 1, view.Name)
        return items[0]

    def paint_state(self, view):
        scene = TechDrawGui.getSceneForPage(self.page)
        image = QtGui.QImage(800, 600, QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtCore.Qt.white)
        painter = QtGui.QPainter(image)
        try:
            scene.render(painter)
        finally:
            painter.end()
        # QGIPrimPath::paint copies the effective pen/brush to the Qt item.
        # Read fresh children after painting; redraw can delete earlier wrappers.
        children = self.view_item(view).childItems()
        edges = [item for item in children if item.type() == self.EDGE_TYPE]
        faces = [item for item in children
                 if item.type() == self.FACE_TYPE and item.zValue() == 40]
        points = []
        for edge in edges:
            path = edge.path()
            for index in range(path.elementCount()):
                element = path.elementAt(index)
                point = edge.mapToParent(QtCore.QPointF(element.x, element.y))
                points.append((point.x(), point.y()))
        spans = ()
        if points:
            spans = tuple(sorted((max(point[axis] for point in points)
                                  - min(point[axis] for point in points))
                                 for axis in (0, 1)))
        return {
            "edges": len(edges),
            "selected": sum(item.isSelected() for item in edges),
            "colors": tuple(sorted(item.pen().color().name() for item in edges)),
            "spans": spans,
            "face_colors": tuple(sorted(item.brush().color().name() for item in faces)),
        }

    def stable_paint_state(self, view):
        previous = None
        stable = 0
        deadline = time.monotonic() + 10
        while stable < 3:
            current = self.paint_state(view)
            stable = stable + 1 if current == previous else 0
            previous = current
            self.assertLess(time.monotonic(), deadline, current)
            self.process_events()
        return current

    def perimeter(self):
        return sum(edge.Length for edge in self.section.getVisibleEdges())

    def check_selection(self, view):
        Gui.Selection.clearSelection()
        self.process_events()
        before = self.stable_paint_state(view)
        self.assertEqual(before["edges"], 4)
        self.assertEqual(before["selected"], 0)
        self.assertGreater(view.getEdgeBySelection("Edge0").Length, 0)
        geometry_before = tuple(edge.Length for edge in view.getVisibleEdges())
        coordinates_before = (view.X.Value, view.Y.Value)
        Gui.Selection.addSelection(self.doc.Name, view.Name, "Edge0")
        self.process_events()
        after = self.stable_paint_state(view)
        logical = [(entry.ObjectName, list(entry.SubElementNames))
                   for entry in Gui.Selection.getSelectionEx(self.doc.Name)]
        self.assertEqual(logical, [(view.Name, ["Edge0"])])
        self.assertEqual(after["selected"], 1, after)
        self.assertNotEqual(after["colors"], before["colors"], after)
        self.assertEqual(after["spans"], before["spans"])
        self.assertEqual(tuple(edge.Length for edge in view.getVisibleEdges()), geometry_before)
        self.assertEqual((view.X.Value, view.Y.Value), coordinates_before)
        Gui.Selection.clearSelection()
        self.process_events()
        cleared = self.stable_paint_state(view)
        self.assertEqual(cleared["selected"], 0)
        self.assertEqual(cleared["colors"], before["colors"])

    def testOrdinaryViewEdgeSelection(self):
        self.check_selection(self.view)

    def testSectionEdgeSelection(self):
        self.check_selection(self.section)

    def testRestoredSectionGeometryAndSelection(self):
        before = self.stable_paint_state(self.section)
        lengths_before = sorted(edge.Length for edge in self.section.getVisibleEdges())
        filename = Path(self.storage.name) / "section_selection.FCStd"
        self.doc.saveAs(str(filename))
        self.close_document()
        self.doc = App.openDocument(str(filename))
        self.source = self.doc.Source
        self.page = self.doc.Page
        self.view = self.doc.View
        self.section = self.doc.Section
        self.page.ViewObject.show()
        self.wait_for(lambda: all(view.getVisibleEdges() and "Up-to-date" in view.State
                                 for view in (self.view, self.section)))
        after = self.stable_paint_state(self.section)
        self.assertEqual(after["edges"], 4)
        self.assertEqual(after["spans"], before["spans"])
        self.assertEqual(sorted(edge.Length for edge in self.section.getVisibleEdges()),
                         lengths_before)
        self.assertAlmostEqual(self.source.Shape.Volume, 1000)
        self.check_selection(self.view)
        self.check_selection(self.section)

    def testSourceGeometryRecomputesSectionGraphics(self):
        before = self.stable_paint_state(self.section)
        self.assertAlmostEqual(self.perimeter(), 40)
        self.source.Shape = Part.makeBox(20, 10, 10)
        self.doc.recompute()
        self.wait_for(lambda: "Up-to-date" in self.section.State
                      and abs(self.perimeter() - 60) < 1e-7)
        after = self.stable_paint_state(self.section)
        self.assertEqual(after["edges"], 4)
        self.assertAlmostEqual(after["spans"][0], before["spans"][0])
        self.assertAlmostEqual(after["spans"][1], 2 * before["spans"][1])

    def testCutSurfaceColorRepaintsSection(self):
        self.section.CutSurfaceDisplay = "Color"
        self.section.ViewObject.CutSurfaceTransparency = 0
        for rgb, expected in (((1.0, 0.0, 0.0), "#ff0000"),
                              ((0.0, 0.0, 1.0), "#0000ff")):
            with self.subTest(color=expected):
                self.section.ViewObject.CutSurfaceColor = rgb
                self.wait_for(lambda: expected in self.paint_state(self.section)["face_colors"])
                state = self.stable_paint_state(self.section)
                self.assertEqual(state["edges"], 4)
                self.assertTrue(state["face_colors"])
                self.assertEqual(set(state["face_colors"]), {expected})

    def testSectionCutOnlyRebuildsGraphics(self):
        self.assertEqual(self.stable_paint_state(self.section)["edges"], 4)
        self.section.SectionCutOnly = True
        self.doc.recompute()
        self.wait_for(lambda: self.paint_state(self.section)["edges"] == 0)
        cut_only = self.stable_paint_state(self.section)
        self.assertTrue(cut_only["face_colors"])
        self.section.SectionCutOnly = False
        self.doc.recompute()
        self.wait_for(lambda: self.paint_state(self.section)["edges"] == 4)
        self.assertEqual(self.stable_paint_state(self.section)["edges"], 4)

    def testRedrawCommandUpdatesFrozenSection(self):
        before = self.stable_paint_state(self.section)
        self.page.KeepUpdated = False
        self.source.Shape = Part.makeBox(20, 10, 10)
        self.doc.recompute()
        self.process_events()
        self.assertAlmostEqual(self.perimeter(), 40)
        self.assertEqual(self.stable_paint_state(self.section)["spans"], before["spans"])
        Gui.Selection.addSelection(self.doc.Name, self.page.Name)
        try:
            Gui.runCommand("TechDraw_RedrawPage")
        finally:
            Gui.Selection.clearSelection()
        self.wait_for(lambda: abs(self.perimeter() - 60) < 1e-7)
        after = self.stable_paint_state(self.section)
        self.assertEqual(after["edges"], 4)
        self.assertAlmostEqual(after["spans"][0], before["spans"][0])
        self.assertAlmostEqual(after["spans"][1], 2 * before["spans"][1])
        self.assertFalse(self.page.KeepUpdated)
