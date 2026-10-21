# SPDX-License-Identifier: LGPL-2.1-or-later
"""Repeated area-dimension redraw preserves an unchanged leader point and document state."""

import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    import TechDraw  # noqa: F401
    import TechDrawGui
    from PySide import QtCore, QtWidgets
    from TDTest import TechDrawTestUtilities


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestAreaLeaderRedrawGui(unittest.TestCase):
    border_ids = ("path6", "path8", "path10", "path12")

    def setUp(self):
        self.doc_name = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = [
            (entry.DocumentName, entry.ObjectName, tuple(entry.SubElementNames))
            for entry in Gui.Selection.getSelectionEx()
        ]
        self.addCleanup(self._cleanup)
        self.assertFalse(Gui.Control.activeDialog())
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.mdi_area = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
        self.assertIsNotNone(self.mdi_area)
        self.directory = Path(tempfile.mkdtemp(prefix="techdraw-unopened-export-"))
        print(
            "UNOPENED_EXPORT_ARTIFACTS "
            + json.dumps({"test": self.id(), "path": str(self.directory)}),
            flush=True,
        )
        self.template_path = Path(TechDrawTestUtilities.__file__).with_name("TestTemplate.svg")
        self.assertTrue(self.template_path.is_file())
        self.template_source = ET.parse(self.template_path).getroot()
        self.source_by_id = {
            element.get("id"): element
            for element in self.template_source.iter()
            if element.get("id")
        }
        for identifier in self.border_ids:
            self.assertIn(identifier, self.source_by_id)
            self.assertTrue(self.source_by_id[identifier].get("d"))
        self.assertIn("text3282", self.source_by_id)

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            self._pump()
        return bool(predicate())

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.closeDocument(self.doc_name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._pump()
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        for document, name, subnames in self.previous_selection:
            if document in App.listDocuments() and App.getDocument(document).getObject(name):
                if subnames:
                    for subname in subnames:
                        Gui.Selection.addSelection(document, name, subname)
                else:
                    Gui.Selection.addSelection(document, name)

    def _ui_state(self):
        active = self.mdi_area.activeSubWindow()
        return {
            "windows": tuple(
                sorted(window.windowTitle() for window in self.mdi_area.subWindowList())
            ),
            "active_window": active.windowTitle() if active else None,
            "active_document": App.ActiveDocument.Name if App.ActiveDocument else None,
            "page_visibility": self.page.ViewObject.Visibility,
        }

    def _page_is_open(self):
        return any(
            window.windowTitle().replace("[*]", "").rstrip("*") == self.page.Label
            for window in self.mdi_area.subWindowList()
        )

    @staticmethod
    def _geometry(view):
        return tuple(
            sorted(
                (
                    round(edge.Length, 8),
                    tuple(
                        sorted(
                            tuple(round(value, 8) for value in vertex.Point)
                            for vertex in edge.Vertexes
                        )
                    ),
                )
                for edge in view.getVisibleEdges()
            )
        )

    def _create(self, filename_first):
        self.doc = App.newDocument("UnopenedTemplate_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.box = self.doc.addObject("Part::Box", "Box")
        self.box.Length, self.box.Width, self.box.Height = 20, 12, 5
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        self.page.Label = "Unopened export " + uuid4().hex[:10]
        self.template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        if filename_first:
            self.template.Template = str(self.template_path)
            self.page.Template = self.template
        else:
            self.page.Template = self.template
            self.template.Template = str(self.template_path)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.X, self.view.Y = 70, 100
        self.doc.recompute()
        previous = None
        stable = 0

        def geometry_is_ready():
            nonlocal previous, stable
            geometry = self._geometry(self.view)
            if "Up-to-date" in self.view.State and geometry == previous and len(geometry) == 4:
                stable += 1
            else:
                stable = 0
            previous = geometry
            return stable >= 3

        self.assertTrue(self._wait(geometry_is_ready), "The ordinary box projection must finish")
        self.assertEqual(self.doc.FileName, "")
        self.assertEqual(self.page.Template, self.template)
        self.assertEqual(self.page.Views, [self.view])
        self.assertEqual(self.view.Source, [self.box])
        self.assertEqual([item[0] for item in self._geometry(self.view)], [12, 12, 20, 20])
        self.assertAlmostEqual(self.box.Shape.Volume, 1200)
        self.assertAlmostEqual(self.template.Width.Value, 297)
        self.assertAlmostEqual(self.template.Height.Value, 210)
        self.assertTrue(self.template.EditableTexts["FC-Title"])
        self.assertFalse(self._page_is_open(), "The fixture must not have opened its drawing page")
        self.geometry = self._geometry(self.view)

    def _open(self):
        Gui.getDocument(self.doc_name).getObject(self.page.Name).show()
        self.assertTrue(
            self._wait(self._page_is_open), "Open the page through its ordinary provider"
        )
        self._pump()

    def _prepare_area(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/View")
        self.old_screen_mode = self.preferences.GetBool("ScreenMode", True)
        self.old_screen_present = any(
            item[1] == "ScreenMode" for item in (self.preferences.GetContents() or [])
        )
        self.addCleanup(self._restore_screen_mode)
        self.addCleanup(self._abort_test_transaction)
        self.preferences.SetBool("ScreenMode", True)
        self._create(filename_first=False)
        self.doc.UndoMode = 1
        faces = self.view.getFaces()
        candidates = [
            index
            for index, face in enumerate(faces)
            if not face.isNull() and abs(face.Area - 240) < 1e-7
        ]
        self.assertEqual(len(candidates), 1, "The projected box has one rectangular face")
        self.face_index = candidates[0]
        self.face = faces[self.face_index]
        self.dimension = self.doc.addObject("TechDraw::DrawViewDimension", "AreaDimension")
        self.page.addView(self.dimension)
        self.dimension.Type = "Area"
        self.dimension.References2D = [(self.view, "Face" + str(self.face_index))]
        self.dimension.X, self.dimension.Y = 25, 20
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: "Up-to-date" in self.dimension.State))
        center, filled_area, actual_area = self.dimension.getAreaPoints()
        self.assertAlmostEqual(filled_area, 240)
        self.assertAlmostEqual(actual_area, 240)
        self.assertAlmostEqual(center.x, 0)
        self.assertAlmostEqual(center.y, 0)
        self.assertFalse(self.dimension.TheoreticalExact)
        self._open()
        self.assertTrue(self._wait(lambda: len(self._area_labels()) == 1))
        scene = TechDrawGui.getSceneForPage(self.page)
        self.scene_units_per_mm = scene.sceneRect().width() / (3 * self.template.Width.Value)
        self.assertGreater(self.scene_units_per_mm, 0)
        self.assertAlmostEqual(
            self.scene_units_per_mm,
            scene.sceneRect().height() / (3 * self.template.Height.Value),
        )
        self.assertTrue(self.dimension.isValid())
        print(
            "AREA_REDRAW_ADMISSION "
            + json.dumps(
                {
                    "test": self.id(),
                    "reference": "Face" + str(self.face_index),
                    "area_points": [tuple(center), filled_area, actual_area],
                    "scene_units_per_mm": self.scene_units_per_mm,
                    "state": self._state(),
                }
            ),
            flush=True,
        )

    def _restore_screen_mode(self):
        if self.old_screen_present:
            self.preferences.SetBool("ScreenMode", self.old_screen_mode)
        else:
            self.preferences.RemBool("ScreenMode")

    def _abort_test_transaction(self):
        if self.doc_name in App.listDocuments():
            doc = App.getDocument(self.doc_name)
            if doc.HasPendingTransaction or doc.getBookedTransactionID():
                doc.abortTransaction()

    def _area_labels(self):
        scene = TechDrawGui.getSceneForPage(self.page)
        roots = [
            item
            for item in scene.items()
            if item.data(0) == "QGIV" and item.data(1) == self.dimension.Name
        ]
        if len(roots) != 1:
            return []
        labels = [item for item in roots[0].childItems() if item.type() == 65536 + 15]
        return [
            label
            for label in labels
            if any(
                isinstance(child, QtWidgets.QGraphicsRectItem) and child.isVisible()
                for child in label.childItems()
            )
        ]

    def _leader_position(self):
        labels = self._area_labels()
        self.assertEqual(len(labels), 1)
        label = labels[0]
        point = label.mapToParent(label.boundingRect().center())
        return (point.x() / self.scene_units_per_mm, point.y() / self.scene_units_per_mm)

    def _drag_leader(self, dx_mm, dy_mm):
        # Same public scene-event mechanism as DrawViewPositionTest.drag_view.
        labels = self._area_labels()
        self.assertEqual(len(labels), 1)
        item = labels[0]
        scene = item.scene()
        self.assertTrue(item.isVisible())
        self.assertGreater(item.boundingRect().width(), 0)
        self.assertGreater(item.boundingRect().height(), 0)
        start = item.boundingRect().center()
        start_scene = item.mapToScene(start)
        end_scene = start_scene + QtCore.QPointF(
            dx_mm * self.scene_units_per_mm, dy_mm * self.scene_units_per_mm
        )
        before = tuple(self.dimension.AreaLeaderPoint)
        button = QtCore.Qt.LeftButton
        for kind, point in (
            (QtCore.QEvent.GraphicsSceneMousePress, start_scene),
            (QtCore.QEvent.GraphicsSceneMouseMove, end_scene),
            (QtCore.QEvent.GraphicsSceneMouseRelease, end_scene),
        ):
            event = QtWidgets.QGraphicsSceneMouseEvent(kind)
            event.setButton(
                button if kind != QtCore.QEvent.GraphicsSceneMouseMove else QtCore.Qt.NoButton
            )
            event.setButtons(
                button if kind != QtCore.QEvent.GraphicsSceneMouseRelease else QtCore.Qt.NoButton
            )
            event.setPos(item.mapFromScene(point))
            event.setScenePos(point)
            event.setLastPos(item.mapFromScene(start_scene))
            event.setLastScenePos(start_scene)
            event.setButtonDownPos(button, start)
            event.setButtonDownScenePos(button, start_scene)
            scene.sendEvent(item, event)
            if kind == QtCore.QEvent.GraphicsSceneMousePress:
                self.assertTrue(item.isSelected(), "The actual origin label must receive the drag")
        self._pump()
        self.assertEqual(self._geometry(self.view), self.geometry)
        print(
            "AREA_REDRAW_DRAG "
            + json.dumps(
                {
                    "test": self.id(),
                    "delta_mm": [dx_mm, dy_mm],
                    "before": before,
                    "after": tuple(self.dimension.AreaLeaderPoint),
                    "label_position": self._leader_position(),
                }
            ),
            flush=True,
        )

    def _point_is_inside(self):
        return self.face.isInside(self.dimension.AreaLeaderPoint, 1e-7, True)

    def _model_values(self):
        return {
            "leader_point": tuple(self.dimension.AreaLeaderPoint),
            "use_leader": self.dimension.UseAreaLeaderPoint,
            "dimension_type": self.dimension.Type,
            "dimension_position": (self.dimension.X.Value, self.dimension.Y.Value),
            "references": [(obj.Name, tuple(names)) for obj, names in self.dimension.References2D],
            "areas": [
                tuple(self.dimension.getAreaPoints()[0]),
                *self.dimension.getAreaPoints()[1:],
            ],
            "box_volume": self.box.Shape.Volume,
            "geometry": self._geometry(self.view),
            "template_size": (self.template.Width.Value, self.template.Height.Value),
            "editable_texts": dict(self.template.EditableTexts),
        }

    def _state(self):
        windows = []
        for window in self.mdi_area.subWindowList():
            widget = window.widget()
            windows.append(
                (
                    window.windowTitle(),
                    window.isWindowModified(),
                    widget.isWindowModified() if widget else None,
                )
            )
        return {
            "model_values": self._model_values(),
            "doc_touched": self.doc.isTouched(),
            "object_states": {obj.Name: tuple(obj.State) for obj in self.doc.Objects},
            "gui_modified": Gui.getDocument(self.doc_name).Modified,
            "window_flags": sorted(windows),
            "main_window_modified": Gui.getMainWindow().isWindowModified(),
            "pending": self.doc.HasPendingTransaction,
            "booked_id": self.doc.getBookedTransactionID(),
            "undo_names": tuple(self.doc.UndoNames),
            "redo_names": tuple(self.doc.RedoNames),
        }

    def _save_after_drag(self):
        self._prepare_area()
        before = tuple(self.dimension.AreaLeaderPoint)
        self._drag_leader(3, 2)
        self.assertNotEqual(tuple(self.dimension.AreaLeaderPoint), before)
        self.assertTrue(self._point_is_inside())
        Gui.Selection.clearSelection()
        self.doc.recompute()
        self._pump()
        self.doc.recompute()
        path = self.directory / "area-redraw.FCStd"
        self.doc.saveAs(str(path))
        self.assertTrue(Gui.getDocument(self.doc_name).save())
        self._pump()
        self.assertTrue(path.is_file())
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertEqual(self.doc.getBookedTransactionID(), 0)
        self.assertFalse(
            self.doc.isTouched(), "The ordinary saved input must be clean before redraw"
        )
        self.assertFalse(Gui.getDocument(self.doc_name).Modified)
        self.assertTrue(self._point_is_inside())

    def _redraw_with_normal_preference(self):
        old_mode = self.preferences.GetBool("ScreenMode", True)
        before = self._state()
        try:
            self.preferences.SetBool("ScreenMode", not old_mode)
            immediate = self._state()
        finally:
            self.preferences.SetBool("ScreenMode", old_mode)
        self._pump()
        after = self._state()
        print(
            "AREA_REDRAW_STATE "
            + json.dumps(
                {
                    "test": self.id(),
                    "before": before,
                    "immediate": immediate,
                    "after": after,
                }
            ),
            flush=True,
        )
        self.assertEqual(self.preferences.GetBool("ScreenMode", True), old_mode)
        self.assertEqual(after["model_values"], before["model_values"])
        for field in (
            "doc_touched",
            "object_states",
            "gui_modified",
            "window_flags",
            "main_window_modified",
            "pending",
            "booked_id",
            "undo_names",
            "redo_names",
        ):
            with self.subTest(state_field=field):
                self.assertEqual(
                    after[field], before[field], "Redraw with an unchanged point must retain state"
                )

    def test_first_and_changed_inside_drags_control(self):
        self._prepare_area()
        first = tuple(self.dimension.AreaLeaderPoint)
        self._drag_leader(3, 2)
        second = tuple(self.dimension.AreaLeaderPoint)
        self.assertNotEqual(second, first)
        self.assertTrue(self._point_is_inside())
        self._drag_leader(2, -1)
        self.assertNotEqual(tuple(self.dimension.AreaLeaderPoint), second)
        self.assertTrue(self._point_is_inside())
        self.assertTrue(self.dimension.isValid())

    def test_drag_outside_face_preserves_last_valid_point_control(self):
        self._prepare_area()
        self._drag_leader(3, 2)
        before = tuple(self.dimension.AreaLeaderPoint)
        self.assertTrue(self._point_is_inside())
        self._drag_leader(100, 0)
        self.assertEqual(tuple(self.dimension.AreaLeaderPoint), before)
        self.assertTrue(self._point_is_inside())
        self.assertTrue(self.dimension.isValid())

    def test_unchanged_redraw_preserves_saved_document_state(self):
        self._save_after_drag()
        self._redraw_with_normal_preference()

    def test_unchanged_redraw_preserves_booked_transaction(self):
        self._save_after_drag()
        self.doc.openTransaction("Area leader redraw booked witness")
        self.assertNotEqual(self.doc.getBookedTransactionID(), 0)
        self.assertFalse(self.doc.HasPendingTransaction)
        self._redraw_with_normal_preference()
