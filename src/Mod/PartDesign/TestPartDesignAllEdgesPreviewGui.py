# SPDX-License-Identifier: LGPL-2.1-or-later
"""All Edges keeps native dress-up preview styling consistent with computation.

Only ordinary commands and public native widgets create the tested states.
An explicit disposable profile is required before any GUI or model mutation.
"""

import os
from pathlib import Path
import stat
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestPartDesignAllEdgesPreviewGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        if App.listDocuments():
            self.skipTest("Requires a disposable GUI process without existing documents")
        if QtWidgets.QApplication.activeModalWidget() is not None or Gui.Control.activeDialog():
            self.skipTest("Requires a GUI process without a foreign modal or task")
        self.document_name = None
        self.document_uid = None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.main = Gui.getMainWindow()
        self.addCleanup(self._cleanup)
        import Part  # noqa: F401
        import PartDesignGui  # noqa: F401
        Gui.activateWorkbench("PartDesignWorkbench")

    def _owned_profile(self):
        selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
        if not selected:
            self.skipTest("Requires an explicitly selected disposable test profile")

        def plain(path):
            for part in (path, *path.parents):
                try:
                    if part.is_symlink():
                        return False
                    junction = getattr(part, "is_junction", None)
                    if junction is not None and junction():
                        return False
                    if getattr(part.lstat(), "st_file_attributes", 0) & getattr(
                        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
                    ):
                        return False
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
            return True

        raw = Path(selected)
        if not raw.is_absolute() or not plain(raw):
            self.skipTest("The disposable profile must be an absolute plain directory")
        try:
            profile = raw.resolve(strict=True)
        except OSError:
            self.skipTest("The disposable profile must already exist")
        if not profile.is_dir():
            self.skipTest("The disposable profile must be a directory")
        text = os.environ.get("FREECAD_USER_HOME")
        if not text:
            self.skipTest("FREECAD_USER_HOME must explicitly select the profile")
        home = Path(text)
        if not home.is_absolute() or not plain(home):
            self.skipTest("FREECAD_USER_HOME must be an absolute plain directory")
        try:
            matching_home = home.resolve(strict=True) == profile
        except OSError:
            matching_home = False
        if not matching_home:
            self.skipTest("FREECAD_USER_HOME does not match admission")
        config = Path(App.ConfigGet("UserParameter"))
        data = Path(App.getUserAppDataDir())
        if not all(path.is_absolute() and plain(path) for path in (config, data)):
            self.skipTest("Active profile paths must be absolute and plain")
        if config.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside admission")
        if not all(path.resolve().is_relative_to(profile) for path in (config, data)):
            self.skipTest("Active profile paths must stay within admission")
        return profile

    @staticmethod
    def _pump():
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, message):
        deadline = time.monotonic() + 8
        while not predicate():
            self.assertLess(time.monotonic(), deadline, message)
            self._pump()

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.document_name and self.document_name in App.listDocuments():
            document = App.getDocument(self.document_name)
            self.assertEqual(str(document.Uid), self.document_uid)
            gui_document = Gui.getDocument(self.document_name)
            task = Gui.Control.activeTaskDialog(gui_document)
            if task is not None:
                task.reject()
                self._pump()
            self.assertIsNone(gui_document.getInEdit())
            if document.HasPendingTransaction:
                document.abortTransaction()
            App.closeDocument(self.document_name)
            self._pump()
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        self.assertEqual(App.listDocuments(), {})

    @staticmethod
    def _style(feature):
        from pivy import coin
        root = feature.ViewObject.RootNode
        preview_type = coin.SoType.fromName("SoPreviewShape")
        if preview_type.isBad():
            raise AssertionError("The native preview type is not registered")
        search = coin.SoSearchAction()
        search.setType(preview_type)
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(root)
        nodes = [path.getTail() for path in search.getPaths()]
        if len(nodes) != 2:
            raise AssertionError("The owned PD preview graph must contain primary and tool nodes")
        if not all(str(node.getTypeId().getName()) == "SoPreviewShape" for node in nodes):
            raise AssertionError("Wrong native preview node type")
        # PD attaches a tool node whose color is connected from the primary color.
        primary = [node for node in nodes if not node.getField("color").isConnected()]
        if len(primary) != 1:
            raise AssertionError("The owned primary preview must be uniquely identified")
        node = primary[0]
        return {"color": list(node.getField("color").getValue().getValue()),
                "transparency": float(node.getField("transparency").getValue()),
                "normal_color": list(feature.ViewObject.PreviewColor)[:3]}

    @staticmethod
    def _parameter(kind):
        return "Size" if kind == "Chamfer" else "Radius"

    def _model(self, fx):
        document, body, box, feature = (fx[key] for key in ("doc", "body", "box", "feature"))
        shape = feature.Shape
        parameter = self._parameter(fx["kind"])
        return {"objects": [(obj.Name, obj.TypeId) for obj in document.Objects],
                "body_group": [obj.Name for obj in body.Group],
                "body_tip": body.Tip.Name if body.Tip else None,
                "base": [feature.Base[0].Name, list(feature.Base[1])],
                "all_edges": bool(feature.UseAllEdges),
                parameter.lower(): getattr(feature, parameter).Value,
                "valid": bool(feature.isValid()), "state": list(feature.State),
                "shape_null": bool(shape.isNull()),
                "shape_valid": bool(not shape.isNull() and shape.isValid()),
                "volume": None if shape.isNull() else shape.Volume,
                "area": None if shape.isNull() else shape.Area,
                "counts": None if shape.isNull() else [len(shape.Solids), len(shape.Faces), len(shape.Edges)],
                "source_volume": box.Shape.Volume}

    def _snapshot(self, fx):
        return {"model": self._model(fx), "style": self._style(fx["feature"])}

    @staticmethod
    def _valid(snapshot_value):
        value = snapshot_value["model"]
        return (value["valid"] and value["shape_valid"] and not value["shape_null"]
                and 0 < value["volume"] < 6000 and value["counts"][0] == 1)

    @staticmethod
    def _normal(snapshot_value):
        value = snapshot_value["style"]
        return value["color"] == value["normal_color"]

    def _widgets(self, kind):
        checkboxes = self.main.findChildren(QtWidgets.QCheckBox, "checkBoxUseAllEdges")
        editor_name = "chamferSize" if kind == "Chamfer" else "filletRadius"
        sizes = self.main.findChildren(QtWidgets.QAbstractSpinBox, editor_name)
        self.assertEqual(len(checkboxes), 1)
        self.assertEqual(len(sizes), 1)
        checkbox, size = checkboxes[0], sizes[0]
        self.assertTrue(checkbox.isEnabled())
        self.assertTrue(size.isEnabled())
        self.assertTrue(size.property("binding"))
        return checkbox, size

    def _change_value(self, fx, value):
        self.assertTrue(fx["size"].setProperty("rawValue", value))
        self._pump()
        self.assertEqual(getattr(fx["feature"], self._parameter(fx["kind"])).Value, value)
        self.assertEqual(fx["size"].property("rawValue"), value)

    def _open(self, kind, selected_edge):
        if kind == "Chamfer" and not selected_edge:
            preferences = App.ParamGet("User parameter:BaseApp/Preferences/Gui/Gizmos")
            if not preferences.GetBool("EnableGizmos", True):
                self.skipTest("Ordinary Chamfer startup calibration requires enabled gizmos")
        document = App.newDocument("AllEdgesPreview" + kind)
        self.document_name, self.document_uid = document.Name, str(document.Uid)
        gui_document = Gui.getDocument(document.Name)
        body = document.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length, box.Width, box.Height = 20, 30, 10
        document.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertEqual(box.Shape.Volume, 6000)
        self.assertEqual(body.Tip, box)
        gui_document.activeView().setActiveObject("pdbody", body)
        Gui.Selection.clearSelection()
        if selected_edge:
            Gui.Selection.addSelection(document.Name, box.Name, "Edge1")
        selection = Gui.Selection.getSelectionEx()
        if selected_edge:
            self.assertEqual(len(selection), 1)
            self.assertEqual(selection[0].Object, box)
            self.assertEqual(list(selection[0].SubElementNames), ["Edge1"])
        else:
            self.assertEqual(selection, [])
        command = Gui.Command.get("PartDesign_" + kind)
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        Gui.runCommand("PartDesign_" + kind)
        self._pump()
        features = [obj for obj in document.Objects if obj.TypeId == "PartDesign::" + kind]
        self.assertEqual(len(features), 1)
        feature = features[0]
        edit = gui_document.getInEdit()
        self.assertIsNotNone(edit)
        self.assertEqual(edit.Object, feature)
        self.assertIsNotNone(Gui.Control.activeTaskDialog(gui_document))
        checkbox, size = self._widgets(kind)
        self.assertFalse(checkbox.isChecked())
        self.assertFalse(feature.UseAllEdges)
        self.assertEqual(getattr(feature, self._parameter(kind)).Value, 1)
        return {"doc": document, "body": body, "box": box, "feature": feature,
                "kind": kind, "checkbox": checkbox, "size": size}

    def _all_edges(self, fx, checked):
        self.assertNotEqual(fx["checkbox"].isChecked(), checked)
        self.assertTrue(fx["checkbox"].isEnabled())
        fx["checkbox"].click()
        self._pump()
        self.assertEqual(fx["checkbox"].isChecked(), checked)
        self.assertEqual(fx["feature"].UseAllEdges, checked)
        return self._snapshot(fx)

    def _normal_roundtrip(self, fx, before):
        self._change_value(fx, 0.75)
        self.assertTrue(fx["feature"].isValid())
        self.assertTrue(fx["feature"].Shape.isValid())
        self._change_value(fx, 1.0)
        refreshed = self._snapshot(fx)
        self.assertTrue(self._valid(refreshed))
        self.assertTrue(self._normal(refreshed))
        self.assertEqual(before["model"], refreshed["model"])
        return refreshed

    def _error_fixture(self, kind):
        fx = self._open(kind, selected_edge=False)
        feature = fx["feature"]
        initial = self._snapshot(fx)
        self.assertEqual(feature.Base[0], fx["box"])
        self.assertEqual(list(feature.Base[1]), [])
        self.assertFalse(initial["model"]["valid"])
        if kind == "Fillet":
            self._change_value(fx, 0.75)
            self.assertFalse(feature.isValid())
            self._change_value(fx, 1.0)
        error_ready = self._snapshot(fx)
        self.assertFalse(error_ready["model"]["valid"])
        self.assertFalse(self._normal(error_ready))
        self.assertEqual(feature.Base[0], fx["box"])
        self.assertEqual(list(feature.Base[1]), [])
        self.assertFalse(feature.UseAllEdges)
        return fx, error_ready

    def _selected_control(self, kind):
        fx = self._open(kind, selected_edge=True)
        initial = self._snapshot(fx)
        self.assertTrue(self._valid(initial))
        self.assertTrue(self._normal(initial))
        toggled = self._all_edges(fx, True)
        self.assertTrue(self._valid(toggled))
        refreshed = self._normal_roundtrip(fx, toggled)
        self.assertTrue(self._normal(toggled))
        self.assertEqual(toggled["style"], refreshed["style"])

    def _forward(self, kind):
        fx, error_ready = self._error_fixture(kind)
        toggled = self._all_edges(fx, True)
        self.assertTrue(self._valid(toggled))
        refreshed = self._normal_roundtrip(fx, toggled)
        self.assertNotEqual(error_ready["style"], refreshed["style"])
        with self.subTest(oracle="normal_color"):
            self.assertEqual(toggled["style"]["color"], refreshed["style"]["color"])
        with self.subTest(oracle="normal_opacity"):
            self.assertEqual(toggled["style"]["transparency"], refreshed["style"]["transparency"])

    def _backward(self, kind):
        fx, error_ready = self._error_fixture(kind)
        toggled = self._all_edges(fx, True)
        self.assertTrue(self._valid(toggled))
        # Establish normal styling through the ordinary size handler on old and new code alike.
        normal_ready = self._normal_roundtrip(fx, toggled)
        self.assertNotEqual(error_ready["style"], normal_ready["style"])
        unchecked = self._all_edges(fx, False)
        self.assertFalse(unchecked["model"]["valid"])
        self.assertEqual(fx["feature"].Base[0], fx["box"])
        self.assertEqual(list(fx["feature"].Base[1]), [])
        self.assertEqual(getattr(fx["feature"], self._parameter(kind)).Value, 1)
        with self.subTest(oracle="error_color"):
            self.assertEqual(unchecked["style"]["color"], error_ready["style"]["color"])
        with self.subTest(oracle="error_opacity"):
            self.assertEqual(unchecked["style"]["transparency"], error_ready["style"]["transparency"])

    def test_control_chamfer_selected_edge_all_edges_roundtrip(self):
        self._selected_control("Chamfer")

    def test_control_fillet_selected_edge_all_edges_roundtrip(self):
        self._selected_control("Fillet")

    def test_error_to_all_edges_chamfer_refreshes_preview_style(self):
        self._forward("Chamfer")

    def test_error_to_all_edges_fillet_refreshes_preview_style(self):
        self._forward("Fillet")

    def test_valid_to_missing_edges_chamfer_refreshes_preview_style(self):
        self._backward("Chamfer")

    def test_valid_to_missing_edges_fillet_refreshes_preview_style(self):
        self._backward("Fillet")

    def test_all_edges_chamfer_edits_after_selected_edge_disappears(self):
        import Part
        from uuid import uuid4

        preferences = App.ParamGet("User parameter:BaseApp/Preferences/Gui/Gizmos")
        if not preferences.GetBool("EnableGizmos", True):
            self.skipTest("Requires the ordinary enabled-gizmo path")

        document = App.newDocument("ChamferMissingEdge_" + uuid4().hex[:12])
        self.document_name, self.document_uid = document.Name, str(document.Uid)
        gui_document = Gui.getDocument(document.Name)
        body = document.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "Profile")
        points = [(0, 0), (20, 0), (20, 15), (15, 20), (0, 20)]
        sketch.addGeometry(
            [
                Part.LineSegment(App.Vector(*a, 0), App.Vector(*b, 0))
                for a, b in zip(points, points[1:] + points[:1])
            ],
            False,
        )
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 10
        pad.Refine = True
        document.recompute()
        self.assertTrue(pad.isValid() and pad.Shape.isValid())
        self.assertAlmostEqual(pad.Shape.Volume, 3875)

        def endpoints(edge):
            return sorted(
                (vertex.Point.x, vertex.Point.y, vertex.Point.z) for vertex in edge.Vertexes
            )

        candidates = []
        for index, edge in enumerate(pad.Shape.Edges, 1):
            ends = endpoints(edge)
            if (
                len(ends) == 2 and all(abs(point[2] - 10) < 1e-7 for point in ends)
                and abs(ends[0][0] - ends[1][0]) > 1e-7
                and abs(ends[0][1] - ends[1][1]) > 1e-7
            ):
                candidates.append(("Edge" + str(index), ends))
        self.assertEqual(len(candidates), 1, "The Pad has one real upper diagonal edge")
        edge_name, diagonal = candidates[0]
        feature = body.newObject("PartDesign::Chamfer", "Chamfer")
        feature.Base = (pad, [edge_name])
        feature.Size = 0.5
        feature.UseAllEdges = True
        document.recompute()
        fx = {"doc": document, "body": body, "box": pad,
              "feature": feature, "kind": "Chamfer"}
        self.assertTrue(self._valid({"model": self._model(fx)}))
        gui_document.activeView().setActiveObject("pdbody", body)

        def open_and_reject():
            before = self._model(fx)
            Gui.Selection.clearSelection(document.Name)
            Gui.Selection.addSelection(feature)
            self.assertTrue(gui_document.setEdit(feature.Name))
            self._pump()
            self.assertEqual(gui_document.getInEdit().Object, feature)
            task = Gui.Control.activeTaskDialog(gui_document)
            self.assertIsNotNone(task)
            checkbox, _size = self._widgets("Chamfer")
            self.assertTrue(checkbox.isChecked())
            task.reject()
            self._pump()
            self.assertIsNone(gui_document.getInEdit())
            self.assertIsNone(Gui.Control.activeTaskDialog(gui_document))
            document.recompute()
            self.assertEqual(self._model(fx), before)

        open_and_reject()
        sketch.delGeometry(2)
        sketch.addGeometry(
            [
                Part.LineSegment(App.Vector(20, 15, 0), App.Vector(20, 20, 0)),
                Part.LineSegment(App.Vector(20, 20, 0), App.Vector(15, 20, 0)),
            ],
            False,
        )
        document.recompute()
        self.assertTrue(pad.isValid() and pad.Shape.isValid())
        self.assertEqual(len(pad.Shape.Edges), 12)
        self.assertAlmostEqual(pad.Shape.Volume, 4000)
        self.assertNotIn(diagonal, [endpoints(edge) for edge in pad.Shape.Edges])
        self.assertTrue(feature.UseAllEdges)
        self.assertTrue(self._valid({"model": self._model(fx)}))
        self.assertEqual(len(feature.Base[1]), 1)
        self.assertTrue(feature.Base[1][0].startswith("?"))
        open_and_reject()
