# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regression coverage for operation sequences and evaluator invariants."""

import importlib
import tempfile
from pathlib import Path
import json
import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import FreeCAD as App
import Part
import Forms
from Forms import topology, brep
from Forms.cage import ControlCage
from Forms.tmesh import HierarchicalTMesh
from Forms.edit_journal import EditJournal
from Forms.preview import mesh_preview


def _content(obj):
    """Return the serialized object without the archive's entry timestamps.

    dumpContent() is a zip archive whose entries carry the time of the dump,
    so raw bytes differ whenever two dumps straddle a two-second boundary.
    """
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(bytes(obj.dumpContent(0)))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class _ToolSession:
    """The edit-session services a tool controller uses, without a 3D view."""

    def __init__(self, obj, active_tool):
        self.obj = obj
        self.active_tool = active_tool
        self.cleaned = False
        self.view = Mock()
        self.panel = Mock()

    def __getattr__(self, name):
        if name.endswith("_tool_active"):
            return self.active_tool == name[: -len("_tool_active")]
        # Task panel, selection and view refreshes are not under test.
        return getattr(self.panel, name)

    def _begin_action(self, label):
        self.obj.Document.openTransaction(label)
        return True

    def _finish_action(self, opened, commit=True):
        if not opened:
            return
        if commit:
            self.obj.Document.commitTransaction()
        else:
            self.obj.Document.abortTransaction()


def _reference_tool_session(obj, active_tool):
    """A tool session that resolves picked references like the editor does."""
    from Forms.edit_tools import FormEditToolsMixin

    session = _ToolSession(obj, active_tool)
    for name in (
        "_selection_document",
        "_global_placement",
        "_reference_selection",
        "_reference_label",
        "_reference_element",
        "_reference_edge",
        "_reference_point",
    ):
        setattr(session, name, vars(FormEditToolsMixin)[name].__get__(session))
    return session


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("FormsReviewRegression")
        from Forms.preferences import preferences
        pref = preferences()
        self.previous_preferences = {key: pref.GetBool(key, False)
                                     for key in ("MeshPreview", "GreedySelection")}

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        from Forms.preferences import preferences
        for key, value in self.previous_preferences.items():
            preferences().SetBool(key, value)

    def test_base_rewrites_reject_local_edits_without_mutation(self):
        obj = Forms.create_box(self.doc)
        Forms.subdivide_faces(obj, [0])
        points = list(obj.LocalControlPoints)
        points[0] += App.Vector(0, 0, 7)
        obj.LocalControlPoints = points
        self.doc.recompute()
        before = _content(obj)
        edge = next(iter(ControlCage.from_object(obj).edge_counts()))
        for operation, args in (
            (Forms.insert_edge_loop, (edge,)), (Forms.erase_and_fill, ([0],)),
            (Forms.fill_holes, ([edge],)),
        ):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "existing local edits"):
                    operation(obj, *args)
                self.assertEqual(before, _content(obj))

    def test_bridge_subdivided_boundaries_retains_local_displacements(self):
        from Forms.model import object_tmesh
        for subdivided, partial in (([0], False), ([0, 1], False), ([0], True), ([0, 1], True)):
            with self.subTest(subdivided=subdivided, partial=partial):
                obj = Forms.create_box(self.doc)
                ControlCage(
                    [(-5, -5, -5), (5, -5, -5), (5, 5, -5), (-5, 5, -5),
                     (-5, -5, 5), (5, -5, 5), (5, 5, 5), (-5, 5, 5)],
                    [(0, 3, 2, 1), (4, 5, 6, 7)],
                ).write(obj)
                obj.CageMode = "Editable"
                Forms.subdivide_faces(obj, subdivided)
                mesh = object_tmesh(obj)
                if partial:
                    partial_root = subdivided[-1]
                    Forms.delete_faces(obj, [face.id for face in mesh.faces.values()
                                             if face.root == partial_root and face.id != partial_root])
                    mesh = object_tmesh(obj)
                center = next(vertex for vertex, locations in mesh.parameter_locations().items()
                              if (0, 0.5, 0.5) in locations)
                edited = App.Vector(*mesh.vertices[center]) + App.Vector(0.2, 0.1, 0.7)
                points = list(obj.LocalControlPoints)
                points[center - len(obj.ControlPoints)] = edited
                obj.LocalControlPoints = points
                mesh = object_tmesh(obj)
                boundaries = [edge for edge, count in mesh.edge_counts().items() if count == 1]
                first = next(edge for edge in boundaries if all(mesh.vertices[v][2] < 0 for v in edge))
                second = next(edge for edge in boundaries if all(mesh.vertices[v][2] > 0 for v in edge))
                before = _content(obj)
                with self.assertRaisesRegex(ValueError, "exactly two"):
                    Forms.bridge_boundaries(obj, [first])
                self.assertEqual(before, _content(obj))
                Forms.bridge_boundaries(obj, [first, second])
                self.doc.recompute()
                cage = ControlCage.from_object(obj)
                self.assertTrue(cage.is_closed)
                self.assertEqual(len(cage.faces), 19 if partial else 16)
                self.assertIn(tuple(edited), cage.vertices)
                self.assertFalse(obj.TMeshData)
                self.assertFalse(obj.LocalControlPoints)
                self.assertFalse(obj.Shape.isNull(), obj.ConversionStatus)
                self.assertTrue(obj.Shape.isValid(), obj.ConversionStatus)
                self.assertEqual(len(obj.Shape.Solids), 1)

    def test_bridge_invalid_subdivided_selection_is_atomic(self):
        obj = Forms.create_box(self.doc)
        Forms.subdivide_faces(obj, [0])
        self.doc.recompute()
        before = _content(obj)
        from Forms.model import object_tmesh
        edge = next(iter(object_tmesh(obj).atomic_edges()))
        with self.assertRaisesRegex(ValueError, "open boundary"):
            Forms.bridge_boundaries(obj, [edge])
        self.assertEqual(before, _content(obj))

    @unittest.skipUnless(App.GuiUp, "Bridge command requires FreeCADGui")
    def test_gui_bridge_local_boundaries_and_undo(self):
        import FreeCADGui as Gui
        import CommandTopology
        from PySide import QtWidgets
        from Forms.edit import active_form_session
        from Forms.model import object_tmesh
        obj = Forms.create_box(self.doc)
        ControlCage(
            [(-5, -5, -5), (5, -5, -5), (5, 5, -5), (-5, 5, -5),
             (-5, -5, 5), (5, -5, 5), (5, 5, 5), (-5, 5, 5)],
            [(0, 3, 2, 1), (4, 5, 6, 7)],
        ).write(obj)
        obj.CageMode = "Editable"
        Forms.subdivide_faces(obj, [0, 1])
        self.doc.recompute()
        before = obj.TMeshData
        self.doc.UndoMode = 1
        Gui.getDocument(self.doc.Name).setEdit(obj, 0)
        session = active_form_session(obj)
        mesh = object_tmesh(obj)
        boundaries = [edge for edge, count in mesh.edge_counts().items() if count == 1]
        first = next(edge for edge in boundaries if all(mesh.vertices[v][2] < 0 for v in edge))
        second = next(edge for edge in boundaries if all(mesh.vertices[v][2] > 0 for v in edge))
        session._restore_control_selection(set(), {first, second})
        command = CommandTopology.CommandBridge()
        self.assertTrue(command.IsActive(), "Bridge ignored locally subdivided boundary edges")
        command.Activated()
        self.assertFalse(obj.TMeshData)
        self.assertTrue(obj.Shape.isValid(), obj.ConversionStatus)
        self.assertEqual(len(obj.Shape.Solids), 1)
        self.doc.undo()
        self.doc.recompute()
        QtWidgets.QApplication.processEvents()
        self.assertEqual(obj.TMeshData, before)
        self.doc.redo()
        self.doc.recompute()
        QtWidgets.QApplication.processEvents()
        self.assertTrue(ControlCage.from_object(obj).is_closed)
        session.reject()

    @unittest.skipUnless(App.GuiUp, "Crease commands require FreeCADGui")
    def test_crease_commands_need_a_selected_control_edge(self):
        import CommandTopology

        cage = ControlCage(*topology.face_control_cage(10, 10, 2, 2))
        first, _second, third, _fourth = cage.faces[0]
        targets = [("Edge", (first, third), None)]
        session = SimpleNamespace(
            obj=object(),
            has_active_tool=lambda: False,
            _selected_control_targets=lambda respect_symmetry=True: list(targets),
        )
        mapper = SimpleNamespace(mesh=None, cage=cage)
        with patch.object(CommandTopology, "_active_edit_session", return_value=session), \
                patch.object(CommandTopology, "_active_mapper", return_value=mapper):
            # A selected shape edge whose controls are not one control edge
            # (a diagonal here, a logical T-mesh edge in practice) leaves no
            # edge to crease, so the commands must stay disabled.
            self.assertEqual(CommandTopology._selected_crease_edges(), {})
            self.assertFalse(CommandTopology.CommandCrease().IsActive())
            self.assertFalse(CommandTopology.CommandUncrease().IsActive())
            targets[:] = [("Edge", (third, first), None), ("Edge", cage.faces[0][:2], None)]
            self.assertEqual(
                CommandTopology._selected_crease_edges(),
                {session.obj: {tuple(sorted(cage.faces[0][:2]))}},
            )
            self.assertTrue(CommandTopology.CommandCrease().IsActive())

    @unittest.skipUnless(App.GuiUp, "Forms commands require FreeCADGui")
    def test_cage_commands_ignore_the_selection_of_a_running_tool(self):
        import CommandTopology

        cage = ControlCage(*topology.face_control_cage(10, 10, 2, 2))
        opening_edge = cage.boundary_edges[0]
        tools = []
        session = SimpleNamespace(
            obj=object(),
            has_active_tool=lambda: bool(tools),
            _selected_control_targets=lambda respect_symmetry=True: [
                ("Edge", opening_edge, None)
            ],
        )
        mapper = SimpleNamespace(mesh=None, cage=cage)
        commands = (CommandTopology.CommandFillHole(), CommandTopology.CommandCrease())
        with patch.object(CommandTopology, "_active_edit_session", return_value=session), \
                patch.object(CommandTopology, "_active_mapper", return_value=mapper):
            self.assertTrue(all(command.IsActive() for command in commands))
            # Weld keeps its picked opening edge selected while it runs; a
            # cage edit there would change the edge the tool still holds.
            tools.append("weld")
            self.assertFalse(any(command.IsActive() for command in commands))
            self.assertIsNone(CommandTopology._selected_match_inputs())

    @unittest.skipUnless(App.GuiUp, "Forms commands require FreeCADGui")
    def test_thicken_command_is_disabled_for_dissolved_edges(self):
        import CommandTopology

        obj = Forms.create_face(self.doc)
        self.doc.recompute()
        counts = ControlCage.from_object(obj).edge_counts()
        session = SimpleNamespace(obj=obj, has_active_tool=lambda: False)
        mapper = SimpleNamespace(cage=ControlCage.from_object(obj))
        command = CommandTopology.CommandThicken()
        with patch.object(CommandTopology, "_active_edit_session", return_value=session), \
                patch.object(CommandTopology, "_active_mapper", return_value=mapper):
            self.assertTrue(command.IsActive())
            Forms.dissolve_edges(obj, [next(e for e, count in counts.items() if count == 2)])
            self.doc.recompute()
            # The Thicken tool refuses a Form with dissolved edges when it starts.
            with self.assertRaisesRegex(ValueError, "base control cage"):
                Forms.thicken_surface(obj, 1.0)
            self.assertFalse(command.IsActive())

    def test_materializing_subdivision_retains_holes_and_crease_weights(self):
        vertices, faces = topology.box_control_cage(10, 10, 10)
        base = HierarchicalTMesh.from_quad_cage(vertices, faces)
        refined, children = base.subdivide([0])
        deleted = refined.delete_faces([children[0]])
        crease = next(iter(topology.cage_edges(faces)))
        expected = topology.catmull_clark_step_details(vertices, faces, {crease: 10.0}, [0.0] * len(vertices))
        points, quads, _controls, edges, corners = brep.materialize_tmesh(
            vertices, faces, deleted, {crease: 10.0}, [0.0] * len(vertices))
        # Seeded hierarchical vertices in this direct mesh are midpoint controls;
        # all live cells and inherited permanent crease weights must survive.
        self.assertEqual(len(quads), len(faces) * 4 - 1)
        self.assertEqual(edges, expected[5])
        self.assertEqual(corners, expected[6])
        self.assertFalse(ControlCage(points, quads, corners, edges).is_closed)

    def test_retained_control_locations_survive_dissolve_delete_and_restore(self):
        for dissolve in (False, True):
            with self.subTest(dissolve=dissolve):
                obj = Forms.create_box(self.doc)
                _, children = Forms.subdivide_faces(obj, [0])
                self.doc.recompute()
                if dissolve:
                    mesh = HierarchicalTMesh.decode(obj.TMeshData)
                    counts = {}
                    for child in children:
                        for side in mesh.faces[child].sides:
                            for a, b in zip(side, side[1:]):
                                edge = tuple(sorted((a, b)))
                                counts[edge] = counts.get(edge, 0) + 1
                    Forms.dissolve_edges(obj, [e for e, count in counts.items() if count == 2])
                else:
                    Forms.delete_faces(obj, children)
                self.doc.recompute()
                self.assertFalse(obj.Shape.isNull(), obj.ConversionStatus)
                self.assertTrue(obj.Shape.isValid())
                self.assertEqual(bool(obj.Shape.Solids), dissolve)
                mesh = HierarchicalTMesh.decode(obj.TMeshData)
                self.assertTrue(all(mesh.parameter_locations().values()))
                copy = self.doc.copyObject(obj, False)
                copy.touch()
                self.doc.recompute()
                self.assertFalse(copy.Shape.isNull(), copy.ConversionStatus)

    def test_local_budget_rejects_before_uniform_evaluation(self):
        vertices, faces = topology.box_control_cage(20, 20, 20, 2, 2, 2)
        mesh = HierarchicalTMesh.from_quad_cage(vertices, faces)
        for _ in range(5):
            mesh, _ = mesh.subdivide_grid([0], 1, 1)
        with patch.object(brep, "catmull_clark_step_details") as step:
            with self.assertRaisesRegex(ValueError, "sampling limit"):
                brep._tmesh_refinement(vertices, faces, mesh)
            step.assert_not_called()

    def test_oversized_edit_keeps_the_document_unchanged(self):
        obj = Forms.create_box(self.doc)
        before = (obj.CageMode, list(obj.ControlPoints), obj.TMeshData, list(obj.LocalControlPoints))
        with self.assertRaises(ValueError):
            Forms.subdivide_faces(obj, [0], 32, 32)
        self.assertEqual(before, (obj.CageMode, list(obj.ControlPoints), obj.TMeshData, list(obj.LocalControlPoints)))

    def test_pipe_evaluates_new_local_controls(self):
        path = self.doc.addObject("Part::Feature", "Path")
        path.Shape = Part.makePolygon([App.Vector(), App.Vector(0, 0, 30)])
        obj = Forms.create_pipe(self.doc, path)
        original_count = len(obj.Shape.Faces)
        Forms.subdivide_faces(obj, [0])
        self.doc.recompute()
        self.assertEqual(len(obj.Shape.Faces), original_count + 3)
        volume = obj.Shape.Volume
        points = list(obj.LocalControlPoints)
        points[0] += App.Vector(1, 1, 1)
        obj.LocalControlPoints = points
        self.doc.recompute()
        self.assertTrue(obj.Shape.isValid())
        self.assertNotAlmostEqual(obj.Shape.Volume, volume, places=5)

    def test_unsupported_local_crease_is_rejected_without_storing_it(self):
        obj = Forms.create_box(self.doc)
        Forms.subdivide_faces(obj, [0])
        mesh = HierarchicalTMesh.decode(obj.TMeshData)
        seam = next(e for e in mesh.atomic_edges() if min(e) >= len(obj.ControlPoints))
        before = list(obj.EdgeSharpness)
        with self.assertRaisesRegex(ValueError, "not supported"):
            Forms.set_edge_crease(obj, [seam], 10)
        self.assertEqual(obj.EdgeSharpness, before)

    def test_match_uses_form_and_parent_placements(self):
        parent = self.doc.addObject("App::Part", "SupportParent")
        parent.Placement = App.Placement(App.Vector(4, 9, 12), App.Rotation(App.Vector(0, 1, 0), 25))
        support = self.doc.addObject("Part::Feature", "Support")
        support.Shape = Part.makePlane(20, 20)
        parent.addObject(support)
        obj = Forms.create_face(self.doc)
        obj.Placement = App.Placement(App.Vector(0, 0, 50), App.Rotation(App.Vector(0, 0, 1), 30))
        Forms.match_boundary(obj, ControlCage.from_object(obj).boundary_edges,
                             (support, ["Face1"]), "Connected")
        self.doc.recompute()
        world_support = support.Shape.copy()
        world_support.Placement = parent.Placement * support.Placement
        self.assertLess(obj.Shape.distToShape(world_support)[0], 1.0e-6)
        for index in obj.MatchBoundary:
            point = obj.Placement.multVec(obj.ControlPoints[index])
            self.assertLess(Part.Vertex(point).distToShape(world_support)[0], 1.0e-6)

    def test_finite_crease_limit_is_invariant_under_subdivision(self):
        vertices, faces = topology.box_control_cage(20, 20, 20)
        edges = topology.cage_edges(faces)
        for sharpness in (.5, 1., 2.5, 9.5, 10.):
            with self.subTest(sharpness=sharpness):
                corners = [sharpness] + [0.] * (len(vertices) - 1)
                creases = {edges[0]: sharpness, edges[1]: sharpness}
                before = topology.catmull_clark_limit_points(vertices, faces, creases, corners)
                vv, ff, old, _, _, ee, cc = topology.catmull_clark_step_details(
                    vertices, faces, creases, corners)
                after = topology.catmull_clark_limit_points(vv, ff, ee, cc)
                for i, value in enumerate(before):
                    self.assertLess(math.dist(value, after[old[i]]), 1.0e-10)

    def test_explicit_corner_wins_over_two_sharp_edges(self):
        vertices, faces = topology.box_control_cage(20, 20, 20)
        radial = [edge for edge in topology.cage_edges(faces) if 0 in edge][:2]
        result = topology.catmull_clark_step_details(
            vertices, faces, dict.fromkeys(radial, 10), [10.] + [0.] * (len(vertices) - 1))
        self.assertEqual(result[0][result[2][0]], vertices[0])

    def test_blender_crease_conversion_matches_its_evaluator(self):
        with patch.dict(sys.modules, {"bpy": SimpleNamespace()}):
            extract = importlib.import_module("Forms.blender_extract")
            create = importlib.import_module("Forms.blender_create")
        self.assertAlmostEqual(extract._sharpness(.5), 2.5)
        self.assertAlmostEqual(create._crease(2.5), .5)
        for value in (0, .1, .5, .9, 1):
            self.assertAlmostEqual(create._crease(extract._sharpness(value)), value)

    def test_blender_subdivision_conformance(self):
        from Forms.blender_bridge import find_blender_executable, run_blender_script
        executable = find_blender_executable()
        if not executable:
            self.skipTest("Blender integration requires an installed Blender")
        vertices, faces = topology.box_control_cage(2, 2, 2)
        radial = [edge for edge in topology.cage_edges(faces) if 0 in edge]
        cases = []
        for weights, corner in [([], 0), ([.5, .5], 0), ([1, 1], 0),
                                ([2.5, 2.5], 0), ([10, 10], 0),
                                ([.2, .7, 1.2], .3), ([10, 10], 10), ([], .5)]:
            cases.append(dict(vertices=vertices, faces=faces,
                              edges=[[*edge, value] for edge, value in zip(radial, weights)],
                              corners=[corner] + [0] * (len(vertices) - 1)))
        with tempfile.TemporaryDirectory(prefix="forms-conformance-") as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(cases), encoding="utf-8")
            run_blender_script(Path(__file__).with_name("BlenderConformance.py"), [path],
                               executable=executable, timeout=60)
            outputs = json.loads(path.with_suffix(".out.json").read_text(encoding="utf-8"))
        for case, output in zip(cases, outputs):
            with self.subTest(edges=case["edges"], corner=case["corners"][0]):
                vv, ff = case["vertices"], case["faces"]
                ee = {tuple(edge[:2]): edge[2] for edge in case["edges"]}
                cc = case["corners"]
                for _ in range(2):
                    vv, ff, _, _, _, ee, cc = topology.catmull_clark_step_details(vv, ff, ee, cc)
                self.assertEqual(len(vv), len(output))
                self.assertLess(max(min(math.dist(point, target) for target in output)
                                    for point in vv), 2.0e-6)

    @unittest.skipUnless(App.GuiUp, "GUI lifecycle requires FreeCADGui")
    def test_gui_drag_preview_and_cancel_release_resources(self):
        import FreeCADGui as Gui
        import gc
        import weakref
        from PySide import QtCore, QtWidgets
        from Forms.edit import active_form_session
        from Forms.preferences import preferences
        preferences().SetBool("MeshPreview", True)
        obj = Forms.create_box(self.doc)
        self.doc.UndoMode = 1
        original = list(obj.ControlPoints)
        gui = Gui.getDocument(self.doc.Name)
        for _ in range(3):
            gui.setEdit(obj, 0)
            session = active_form_session(obj)
            self.assertIsNotNone(session)
            session._restore_control_selection({0}, set())
            session.dragger_started(session.dragger)
            session.syncing = True
            session.dragger.translation.setValue(tuple(session.base_center + App.Vector(1, 0, 0)))
            session.syncing = False
            with patch.object(brep, "_make_surface", side_effect=AssertionError("BRep during motion")):
                session.dragger_moved(session.dragger)
            preview = weakref.ref(session.motion_preview)
            self.assertIsNotNone(preview())
            session.dragger_finished(session.dragger)
            self.assertIsNone(session.motion_preview)
            session.reject()
            self.assertTrue(session.cleaned)
            self.assertIsNone(session.edit_backup)
            self.assertEqual(original, obj.ControlPoints)
            ref = weakref.ref(session)
            del session
            QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            QtWidgets.QApplication.processEvents()
            gc.collect()
            self.assertIsNone(preview())
            self.assertIsNone(ref(), "Closed edit session retained by a GUI callback")

    @unittest.skipUnless(App.GuiUp, "Edit sessions require FreeCADGui")
    def test_gui_finished_edit_restores_the_display_mode(self):
        import FreeCADGui as Gui
        from Forms.edit import active_form_session

        obj = Forms.create_box(self.doc)
        self.doc.recompute()
        obj.ViewObject.DisplayMode = "Shaded"
        gui = Gui.getDocument(self.doc.Name)
        gui.setEdit(obj, 0)
        session = active_form_session(obj)
        self.assertIsNotNone(session)
        self.assertEqual(obj.ViewObject.DisplayMode, "Flat Lines")
        # Finishing without Cancel does not replay the edit journal.
        gui.resetEdit()
        self.assertTrue(session.cleaned)
        self.assertEqual(obj.ViewObject.DisplayMode, "Shaded")

    @unittest.skipUnless(App.GuiUp, "Preferences and selection require FreeCADGui")
    def test_gui_preference_defaults_and_background_clear(self):
        import FreeCADGui as Gui
        from PySide import QtWidgets
        from pivy import coin
        from Forms.edit import active_form_session
        from Forms.preferences import preferences, PreferencesPage
        pref = preferences()
        pref.RemBool("MeshPreview")
        pref.RemBool("GreedySelection")
        page = PreferencesPage()
        page.loadSettings()
        self.assertFalse(page.form.meshPreview.isChecked())
        self.assertFalse(page.form.greedySelection.isChecked())
        page.form.meshPreview.setChecked(True)
        page.form.greedySelection.setChecked(True)
        page.saveSettings()
        self.assertTrue(pref.GetBool("MeshPreview"))
        self.assertTrue(pref.GetBool("GreedySelection"))
        obj = Forms.create_box(self.doc)
        gui = Gui.getDocument(self.doc.Name)
        for greedy in (False, True):
            pref.SetBool("GreedySelection", greedy)
            with patch.object(Gui.Selection, "setSelectionStyle", wraps=Gui.Selection.setSelectionStyle) as style:
                gui.setEdit(obj, 0)
                session = active_form_session(obj)
                style.assert_called_with(int(greedy))
                Gui.Selection.addSelection(obj, "Edge1")
                self.assertTrue(Gui.Selection.getSelectionEx())
                event = coin.SoMouseButtonEvent()
                event.setButton(coin.SoMouseButtonEvent.BUTTON1)
                event.setPosition(coin.SbVec2s(10, 10))
                callback = SimpleNamespace(getEvent=lambda: event, getPickedPoint=lambda: None)
                event.setState(coin.SoButtonEvent.DOWN)
                session._selection_mouse_event(callback)
                event.setState(coin.SoButtonEvent.UP)
                session._selection_mouse_event(callback)
                QtWidgets.QApplication.processEvents()
                self.assertFalse(Gui.Selection.getSelectionEx())
                self.assertFalse(session.selected)
                session.reject()
                style.assert_called_with(0)
        page.form.deleteLater()

    @unittest.skipUnless(App.GuiUp, "Edge clicking requires FreeCADGui")
    def test_gui_second_edge_click_preempts_whole_object_selection(self):
        import FreeCADGui as Gui
        from PySide import QtWidgets
        from pivy import coin
        from Forms.edit import active_form_session
        from Forms.preferences import preferences
        obj = Forms.create_box(self.doc)
        for greedy in (False, True):
            preferences().SetBool("GreedySelection", greedy)
            Gui.getDocument(self.doc.Name).setEdit(obj, 0)
            session = active_form_session(obj)
            for second_edge in ("Edge2", "Edge1"):
                Gui.Selection.clearSelection()
                event = coin.SoMouseButtonEvent()
                event.setButton(coin.SoMouseButtonEvent.BUTTON1)
                event.setPosition(coin.SbVec2s(10, 10))
                event.setState(coin.SoButtonEvent.UP)
                handled = []
                callback = SimpleNamespace(getEvent=lambda: event,
                    getPickedPoint=lambda: object(), setHandled=lambda: handled.append(True))
                event.setState(coin.SoButtonEvent.DOWN)
                session._selection_mouse_event(callback)
                Gui.Selection.addSelection(obj, "Edge1")
                if second_edge == "Edge2":
                    event.setPosition(coin.SbVec2s(100, 100))
                pick_view = SimpleNamespace(getObjectInfo=lambda position: {
                    "Document": self.doc.Name, "Object": obj.Name, "Component": "Face1"})
                with patch.object(session, "view", pick_view):
                    event.setState(coin.SoButtonEvent.DOWN)
                    session._selection_mouse_event(callback)
                    self.assertEqual(session.selection_enabled_field.getValue(), second_edge != "Edge1")
                    event.setState(coin.SoButtonEvent.UP)
                    session._selection_mouse_event(callback)
                self.assertTrue(session.selection_enabled_field.getValue())
                self.assertEqual(bool(handled), second_edge == "Edge1")
                QtWidgets.QApplication.processEvents()
                selections = Gui.Selection.getSelectionEx()
                self.assertEqual(len(selections), 1)
                names = selections[0].SubElementNames
                self.assertTrue(names, "Repeated edge click selected the whole object")
                if second_edge == "Edge1":
                    self.assertGreater(len(names), 1)
                else:
                    self.assertEqual(len(names), 1)
            session.reject()

    @unittest.skipUnless(App.GuiUp, "Native picking requires FreeCADGui")
    def test_gui_double_click_after_topology_edits(self):
        import FreeCADGui as Gui
        from PySide import QtWidgets
        from pivy import coin
        from Forms.edit import active_form_session
        from Forms.preferences import preferences
        for operation in ("delete", "insert"):
            for greedy in (False, True):
                with self.subTest(operation=operation, greedy=greedy):
                    preferences().SetBool("GreedySelection", greedy)
                    obj = Forms.create_box(self.doc)
                    Gui.getDocument(self.doc.Name).setEdit(obj, 0)
                    session = active_form_session(obj)
                    if operation == "delete":
                        Forms.delete_faces(obj, [0])
                    else:
                        from Forms.operations import insert_edge_on_face
                        insert_edge_on_face(obj, 0)
                    self.doc.recompute()
                    session.topology_changed()
                    session.view.viewAxonometric()
                    session.view.fitAll()
                    QtWidgets.QApplication.processEvents()
                    manager = session.viewer.getSoRenderManager()

                    def click(position):
                        for state in (coin.SoButtonEvent.DOWN, coin.SoButtonEvent.UP):
                            event = coin.SoMouseButtonEvent()
                            event.setButton(coin.SoMouseButtonEvent.BUTTON1)
                            event.setPosition(coin.SbVec2s(*position))
                            event.setState(state)
                            action = coin.SoHandleEventAction(manager.getViewportRegion())
                            action.setPickRadius(session.viewer.getPickRadius())
                            action.setEvent(event)
                            action.apply(manager.getSceneGraph())

                    checked = 0
                    selected_loop = False
                    for edge in obj.Shape.Edges:
                        middle = edge.valueAt((edge.FirstParameter + edge.LastParameter) / 2)
                        position = session.view.getPointOnScreen(middle)
                        Gui.Selection.clearSelection()
                        click(position)
                        previous = session.last_added_edge
                        if previous is None:
                            continue
                        control_edge = session._control_edge_for_subelement(previous[2])
                        if control_edge is None:
                            continue
                        click(position)
                        QtWidgets.QApplication.processEvents()
                        selected = session._selected_control_edges()
                        self.assertIn(control_edge, selected)
                        selected_loop = selected_loop or len(selected) > 1
                        self.assertTrue(all(s.SubElementNames for s in Gui.Selection.getSelectionEx()))
                        checked += 1
                        if checked >= 3:
                            break
                    self.assertGreater(checked, 0, "No visible editable edge was exercised")
                    self.assertTrue(selected_loop, "Double clicks never expanded an edge chain")
                    session.reject()
                    self.doc.removeObject(obj.Name)

    @unittest.skipUnless(App.GuiUp, "Dragging requires FreeCADGui")
    def test_gui_default_drag_keeps_the_smooth_brep(self):
        import FreeCADGui as Gui
        from Forms.edit import active_form_session
        from Forms.preferences import preferences
        preferences().RemBool("MeshPreview")
        obj = Forms.create_box(self.doc)
        Gui.getDocument(self.doc.Name).setEdit(obj, 0)
        session = active_form_session(obj)
        session._restore_control_selection({0}, set())
        session.dragger_started(session.dragger)
        session.syncing = True
        session.dragger.translation.setValue(tuple(session.base_center + App.Vector(1, 0, 0)))
        session.syncing = False
        with patch.object(brep, "_make_surface", wraps=brep._make_surface) as fitting:
            session.dragger_moved(session.dragger)
            self.assertGreater(fitting.call_count, 0)
        self.assertIsNone(session.motion_preview)
        session.dragger_finished(session.dragger)
        session.reject()

    def test_rejected_edit_restores_the_shape_shown_outside_edit_mode(self):
        # FreeCAD never calls unsetEdit() when setEdit() returns False, which
        # is how the shared Forms editor reports an expected modeling error.
        from Forms.additive import ViewProviderPartDesignForm
        from Forms.primitives import ViewProviderFormFace
        from Forms.viewprovider import ViewProviderForm

        body = self.doc.addObject("PartDesign::Body", "Body")
        source = body.newObject("PartDesign::Feature", "Source")
        source.Shape = Part.makeBox(20, 20, 10)
        form = Forms.create_additive_form(
            body, source, "Box", placement=App.Placement(App.Vector(15, 10, 5), App.Rotation())
        )
        face = Forms.create_face(self.doc)
        self.doc.recompute()
        combined_volume = form.Shape.Volume

        with patch.object(ViewProviderForm, "setEdit", return_value=False):
            provider = object.__new__(ViewProviderPartDesignForm)
            self.assertFalse(provider.setEdit(SimpleNamespace(Object=form), 0))
            provider = object.__new__(ViewProviderFormFace)
            self.assertFalse(provider.setEdit(SimpleNamespace(Object=face), 0))

        self.assertFalse(form.EditingForm)
        self.assertEqual(form.CombinationStatus, "Valid fused additive form")
        self.assertAlmostEqual(form.Shape.Volume, combined_volume, places=6)
        self.assertFalse(getattr(face.Proxy, "_show_edit_shape", False))

    def test_public_api_exports_and_forwards_every_option(self):
        import inspect

        from Forms import additive, box, form, operations, pipe, primitives, surface

        public = {
            name
            for name, value in vars(Forms).items()
            if inspect.isfunction(value) and value.__module__ == "Forms"
        }
        self.assertEqual(public.difference(Forms.__all__), set())
        implementations = {
            "create_box": box,
            "create_form": form,
            "create_pipe": pipe,
            "create_surface": surface,
            "create_additive_form": additive,
            "create_subtractive_form": additive,
            "move_form_to_body": additive,
            "match_boundary": additive,
        }
        for name in ("create_cylinder", "create_sphere", "create_quadball", "create_face",
                     "create_torus", "create_tube"):
            implementations[name] = primitives
        for name in ("delete_faces", "dissolve_edges", "erase_and_fill", "fill_holes",
                     "bridge_boundaries", "unweld_segment", "weld_boundaries", "thicken_surface",
                     "insert_edge_loop", "insert_edge", "insert_point_edges", "subdivide_faces",
                     "set_edge_crease", "straighten_control_points", "flatten_control_points"):
            implementations[name] = operations
        for name, module in implementations.items():
            with self.subTest(function=name):
                self.assertEqual(
                    list(inspect.signature(getattr(Forms, name)).parameters),
                    list(inspect.signature(getattr(module, name)).parameters),
                )

    def test_straighten_finds_the_dominant_eigenvector(self):
        points = [(math.sqrt(1.5), 0, 0), (-math.sqrt(1.5), 0, 0), (0, 1, 1), (0, -1, -1)]
        _center, axis = topology._largest_covariance_axis(points)
        self.assertAlmostEqual(abs(axis[1] + axis[2]), math.sqrt(2))
        self.assertAlmostEqual(axis[0], 0)

    def _split_form(self):
        obj = Forms.create_cylinder(self.doc)
        obj.HeightSegments = 3
        self.doc.recompute()
        cage = ControlCage.from_object(obj)
        for edge in topology.cage_edges(cage.faces):
            seam = topology.cage_edge_loop(cage.faces, edge)
            try:
                cage.split_along_edges(seam)
            except ValueError:
                continue
            return obj, seam
        self.fail("No separating edge loop")

    def test_cancel_unweld_removes_created_object_and_is_undoable(self):
        obj, seam = self._split_form()
        self.doc.UndoMode = 1
        journal = EditJournal(obj)
        self.doc.openTransaction("Unweld")
        objects = Forms.unweld_segment(obj, seam)
        second_name = objects[1].Name
        journal.record_created(objects)
        self.doc.recompute()
        self.doc.commitTransaction()
        journal.restore()
        self.assertIsNone(self.doc.getObject(second_name))
        self.assertTrue(ControlCage.from_object(obj).is_closed)
        self.doc.undo()
        self.doc.recompute()
        self.assertIsNotNone(self.doc.getObject(second_name))
        self.doc.redo()
        self.assertIsNone(self.doc.getObject(second_name))

    def test_cancel_weld_recreates_other_form_and_reconnects_links(self):
        obj, seam = self._split_form()
        first, second = Forms.unweld_segment(obj, seam)
        self.doc.recompute()
        dependent = self.doc.addObject("App::FeaturePython", "Dependent")
        dependent.addProperty("App::PropertyLink", "Source")
        dependent.Source = second
        second_name = second.Name
        journal = EditJournal(first)
        journal.capture_removal(second)
        Forms.weld_boundaries(first, ControlCage.from_object(first).boundary_edges[0],
                              second, ControlCage.from_object(second).boundary_edges[0])
        self.doc.recompute()
        journal.restore()
        restored = self.doc.getObject(second_name)
        self.assertIsNotNone(restored)
        self.assertIs(dependent.Source, restored)
        self.assertFalse(ControlCage.from_object(first).is_closed)
        restored.touch()
        self.doc.recompute()
        self.assertTrue(restored.Shape.isValid())
        self.assertIsNotNone(restored.Proxy)

    def test_cancel_recomputes_objects_using_the_restored_form(self):
        form = Forms.create_box(self.doc)
        self.doc.recompute()
        mirror = self.doc.addObject("Part::Mirroring", "Mirror")
        mirror.Source = form
        self.doc.recompute()
        volume = form.Shape.Volume
        journal = EditJournal(form)
        points = [App.Vector(point) for point in form.ControlPoints]
        points[0] = points[0] + App.Vector(-5, -5, -5)
        form.CageMode = "Editable"
        form.ControlPoints = points
        self.doc.recompute()
        self.assertGreater(abs(mirror.Shape.Volume - volume), 1.0)
        journal.restore()
        self.assertAlmostEqual(form.Shape.Volume, volume, places=6)
        self.assertAlmostEqual(mirror.Shape.Volume, volume, places=6)
        self.assertNotIn("Touched", mirror.State)

    def test_local_refinement_preserves_disconnected_components(self):
        first = Forms.create_box(self.doc)
        second = Forms.create_box(self.doc)
        second.Placement.Base = App.Vector(40, 0, 0)
        cage = ControlCage.from_object(first).disjoint_union(ControlCage.from_object(second))
        # Separate cages geometrically before joining their topology lists.
        count = len(first.ControlPoints)
        cage.vertices[count:] = [(x + 40, y, z) for x, y, z in cage.vertices[count:]]
        cage.write(first)
        first.CageMode = "Editable"
        Forms.subdivide_faces(first, [0])
        self.doc.recompute()
        self.assertFalse(first.Shape.isNull(), first.ConversionStatus)
        self.assertTrue(first.Shape.isValid())
        self.assertEqual(len(first.Shape.Solids), 2)

    @unittest.skipUnless(App.GuiUp, "GUI cancellation requires FreeCADGui")
    def test_gui_cancel_weld_and_unweld(self):
        import FreeCADGui as Gui
        from Forms.edit import active_form_session
        obj, seam = self._split_form()
        gui = Gui.getDocument(self.doc.Name)
        gui.setEdit(obj, 0)
        session = active_form_session(obj)
        session.start_unweld_tool()
        session.unweld_segment_edges = seam
        session.unweld_separate_forms.setChecked(True)
        self.assertTrue(session._commit_unweld_preview())
        self.assertEqual(len(self.doc.Objects), 2)
        session.stop_surface_tool()
        session.reject()
        self.assertEqual(len(self.doc.Objects), 1)
        self.assertTrue(ControlCage.from_object(obj).is_closed)
        first, second = Forms.unweld_segment(obj, seam)
        self.doc.recompute()
        other_name = second.Name
        gui.setEdit(first, 0)
        session = active_form_session(first)
        session.start_weld_tool()
        session.weld_other = second
        session.weld_first_edge = ControlCage.from_object(first).boundary_edges[0]
        session.weld_second_edge = ControlCage.from_object(second).boundary_edges[0]
        self.assertTrue(session.apply_weld_tool())
        self.assertIsNone(self.doc.getObject(other_name))
        session.reject()
        restored = self.doc.getObject(other_name)
        self.assertIsNotNone(restored)
        self.assertIsNotNone(restored.ViewObject.Proxy._cage_coordinates)
        self.assertTrue(restored.Shape.isValid())

    @unittest.skipUnless(App.GuiUp, "Task panels require FreeCADGui")
    def test_task_panel_bindings_follow_the_primitive_type(self):
        from Forms.taskpanels import bind_edit_panel

        session = SimpleNamespace(obj=SimpleNamespace())
        panel = Mock()
        dynamic_widgets = {"Radius": object()}
        dynamic_labels = {"Radius": object()}
        table = object()
        with patch("Forms.taskpanels.load_panel", return_value=panel), patch(
            "Forms.taskpanels._dynamic_primitive_page",
            return_value=(object(), dynamic_widgets, dynamic_labels, table),
        ):
            for form_type in ("Forms::Sphere", "Forms::Box", "Forms::Pipe", "Forms::Face", "Forms::Form"):
                with self.subTest(form_type=form_type):
                    session.obj.FormType = form_type
                    self.assertIs(bind_edit_panel(session), panel)
                    if form_type in ("Forms::Box", "Forms::Face"):
                        prefix = "box" if form_type == "Forms::Box" else "face"
                        self.assertIs(session.parameter_widgets["Length"], getattr(panel, prefix + "Length"))
                        self.assertIs(session.parameter_labels["Length"], getattr(panel, prefix + "XLabel"))
                        self.assertIsNone(session.pipe_segment_table)
                        self.assertIs(session.segment_header, getattr(panel, prefix + "SegmentHeader"))
                    else:
                        self.assertIs(session.parameter_widgets, dynamic_widgets)
                        self.assertIs(session.parameter_labels, dynamic_labels)
                        self.assertIs(session.pipe_segment_table, table)
                        self.assertIsNone(session.segment_header)

    @unittest.skipUnless(App.GuiUp, "Edit sessions require FreeCADGui")
    def test_history_refresh_reloads_the_pipe_segment_table(self):
        # The override spin boxes write their value on every focus-out. After
        # Undo/Redo they must show the restored overrides, or leaving one would
        # silently re-apply the undone value.
        from PySide import QtCore
        from Forms.edit import FormEditSession

        def control(**methods):
            widget = QtCore.QObject()
            for name, method in methods.items():
                setattr(widget, name, method)
            return widget

        session = object.__new__(FormEditSession)
        session.cleaned = False
        session.active_tool = None
        session.obj = SimpleNamespace(
            FormType="Forms::Pipe", CageMode="Parametric", Symmetric=False, SymmetryPlane="YZ"
        )
        session.parameter_widgets = {}
        session.parameter_kinds = {}
        session.symmetric = control(setChecked=Mock())
        session.symmetry_plane = control(
            setCurrentIndex=Mock(), findData=Mock(return_value=0), setEnabled=Mock()
        )
        session.surface_tangent = None
        session.view = Mock()
        for name in (
            "_clear_editor_selection",
            "_reset_surface_tool_cache",
            "_set_parametric_state",
            "_populate_pipe_segment_table",
            "_configure_symmetry",
            "_sync_dimension_properties",
            "_update_dimension_gizmos",
        ):
            setattr(session, name, Mock())
        with patch("Forms.edit.Gui"):
            session._refresh_after_history_change()
        session._populate_pipe_segment_table.assert_called_once_with()

    @unittest.skipUnless(App.GuiUp, "Edit sessions require FreeCADGui")
    def test_pipe_segment_focus_out_without_change_keeps_the_history(self):
        from PySide import QtWidgets
        from Forms.edit import FormEditSession
        from Forms.pipe_parameters import set_segment_diameter

        self.doc.UndoMode = 1
        path = self.doc.addObject("Part::Feature", "Path")
        path.Shape = Part.makePolygon(
            [App.Vector(0, 0, 0), App.Vector(30, 0, 0), App.Vector(30, 30, 0)]
        )
        pipe = Forms.create_pipe(self.doc, path)
        self.doc.recompute()
        key = str(pipe.PipeSegmentKeys[0])
        session = object.__new__(FormEditSession)
        session.cleaned = False
        session.obj = pipe
        session.document_edit = True
        # The same widgets as the edit panel's segment table.
        diameter = QtWidgets.QDoubleSpinBox()
        diameter.setRange(0.0, 1000000.0)
        samples = QtWidgets.QSpinBox()
        samples.setRange(0, 100)

        diameter.setValue(7.0)
        session._pipe_diameter_changed(key, diameter)
        self.assertEqual(self.doc.UndoCount, 1)
        self.doc.undo()
        self.assertEqual(self.doc.RedoCount, 1)
        # editingFinished also fires on a plain focus-out of the refreshed boxes.
        diameter.setValue(0.0)
        session._pipe_diameter_changed(key, diameter)
        session._pipe_samples_changed(key, samples)
        self.assertEqual((self.doc.UndoCount, self.doc.RedoCount), (0, 1))

        # A scripted override finer than the box's decimals is kept as well.
        set_segment_diameter(pipe, key, 2.345)
        overrides = list(pipe.SegmentDiameters)
        diameter.setValue(2.345)
        session._pipe_diameter_changed(key, diameter)
        self.assertEqual(list(pipe.SegmentDiameters), overrides)

        samples.setValue(6)
        session._pipe_samples_changed(key, samples)
        self.assertIn('"samples": 6', pipe.SegmentSamples[0])

    def test_active_session_registry_filters_and_finishes_sessions(self):
        from Forms import sessions

        obj = object()
        session = SimpleNamespace(obj=obj, cleaned=False, document_edit=False, accept=Mock())
        with patch.object(sessions, "_active_session", None):
            self.assertFalse(sessions.finish_active_form_session())
            sessions.set_active_form_session(session)
            self.assertIs(sessions.active_form_session(obj), session)
            self.assertIsNone(sessions.active_form_session(object()))
            self.assertTrue(sessions.finish_active_form_session())
            session.accept.assert_called_once_with()
            session.cleaned = True
            self.assertIsNone(sessions.active_form_session())
            self.assertFalse(sessions.finish_active_form_session())
            sessions.set_active_form_session(None)
            self.assertIsNone(sessions.active_form_session())

    def test_whole_form_drag_preview_matches_the_committed_move(self):
        from Forms.edit import FormEditSession

        def field(*values):
            return SimpleNamespace(getValue=lambda: SimpleNamespace(getValue=lambda: values))

        placement = App.Placement(App.Vector(10, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))
        point = App.Vector(4, 5, 6)
        form_placement = App.Placement(App.Vector(1, 1, 0), App.Rotation(App.Vector(0, 1, 0), 30))
        dragger = SimpleNamespace(
            translation=field(1.0, 2.0, 8.0),
            rotation=field(*App.Rotation(App.Vector(1, 0, 0), 90).Q),
            planarScaleFactor=field(1.0, 1.0, 1.0),
        )
        for cage_mode in ("Editable", "Parametric"):
            with self.subTest(cage_mode=cage_mode):
                obj = SimpleNamespace(
                    Placement=placement.copy(),
                    CageMode=cage_mode,
                    PropertiesList=["FormPlacement"],
                    FormPlacement=form_placement.copy(),
                )
                session = object.__new__(FormEditSession)
                session.obj = obj
                session.syncing = False
                session.selected = [0]
                session.alt_extrude_face_indices = set()
                session.alt_extrude_boundary_edges = set()
                session.whole_form_selected = True
                session.base_center = App.Vector(1, 2, 3)
                session.base_dragger_rotation = App.Rotation()
                session.base_object_placement = placement.copy()
                session.base_form_placement = form_placement.copy()
                session.base_points = [App.Vector(point)]
                session.symmetric = SimpleNamespace(isChecked=lambda: False)
                session._transform_dimension_gizmos = lambda *_arguments: None
                session.view = SimpleNamespace(redraw=lambda: None)
                session.dragger_moved(dragger)
                if cage_mode == "Editable":
                    committed = placement.multVec(session.pending_control_points[0])
                    previewed = obj.Placement.multVec(point)
                else:
                    committed = placement.multiply(session.pending_form_placement).multVec(point)
                    previewed = obj.Placement.multiply(form_placement).multVec(point)
                self.assertLess(committed.sub(previewed).Length, 1.0e-9)

    def test_finishing_document_edit_session_accepts_it(self):
        from Forms import sessions

        # accept() flushes queued edits, applies the active tool and commits
        # a creation transaction; a bare resetEdit() would skip all three.
        session = SimpleNamespace(obj=object(), cleaned=False, document_edit=True, accept=Mock())
        with patch.object(sessions, "_active_session", session):
            self.assertTrue(sessions.finish_active_form_session())
        session.accept.assert_called_once_with()

    def test_topology_tool_picks_and_previews_in_the_cage_frame(self):
        # The Shape carries the Placement while the controls, the picked
        # Insert Point and the hover previews drawn under the Form's transform
        # are in the cage frame. Moving the Form must not change any of them.
        from Forms.cage import ControlElementMapper, control_surface_points
        from Forms.placement import global_placement

        try:
            from Forms.tool_topology import TopologyTool
        except ImportError as error:
            self.skipTest(f"Topology tools need PySide and Pivy: {error}")

        class Session:
            pass

        obj = Forms.create_box(self.doc)
        self.doc.recompute()
        Forms.make_editable(obj)
        self.doc.recompute()
        info = {}
        session = Session()
        session.obj = obj
        session.view = SimpleNamespace(getObjectInfo=lambda position: info)
        session._form_selection_subelement = (
            lambda document, name, raw: raw if name == obj.Name and raw else None
        )
        session._global_placement = global_placement
        session._control_surface_points = lambda: control_surface_points(obj)
        tool = TopologyTool(session)

        def hover():
            mapper = ControlElementMapper(obj)
            session._control_element_mapper = lambda: mapper
            tool._reset_surface_tool_cache()
            index, edge = next(
                (index, edge)
                for index, edge in enumerate(obj.Shape.Edges)
                if len(mapper.indices(edge)) == 2
            )
            # The Form is at the document root: its Shape is in world coordinates.
            first, last = edge.FirstParameter, edge.LastParameter
            picked = edge.valueAt(first + 0.3 * (last - first))
            info.clear()
            info.update(
                Document=self.doc.Name,
                Object=obj.Name,
                SubName=f"Edge{index + 1}",
                x=picked.x,
                y=picked.y,
                z=picked.z,
            )
            hovered = tool._hovered_insert_point((0, 0))
            cage_face = ControlCage.from_object(obj).faces[0]
            curve = tool._insert_curve_points(
                tool._shape_face_for_control_face(0, mapper),
                cage_face,
                tuple(sorted(cage_face[:2])),
                tool.surface_tool_control_points,
            )
            return hovered, curve

        (edge, fraction, point), curve = hover()
        self.assertGreater(abs(fraction - 0.5), 0.1)
        for placement in (
            App.Placement(App.Vector(0, 0, 50), App.Rotation()),
            App.Placement(App.Vector(30, -20, 5), App.Rotation(App.Vector(0, 0, 1), 90)),
        ):
            with self.subTest(placement=placement):
                obj.Placement = placement
                self.doc.recompute()
                (moved_edge, moved_fraction, moved_point), moved_curve = hover()
                self.assertEqual(moved_edge, edge)
                self.assertAlmostEqual(moved_fraction, fraction, places=6)
                self.assertLess(moved_point.sub(point).Length, 1.0e-6)
                self.assertEqual(len(moved_curve), len(curve))
                for moved, reference in zip(moved_curve, curve):
                    self.assertLess(moved.sub(reference).Length, 1.0e-6)

    def test_rejected_insert_point_chain_is_discarded(self):
        # Each consecutive pair is accepted while clicking, but the second
        # segment goes back across the face the first one has already split.
        from Forms.operations import insert_point_face_target

        try:
            from Forms.tool_topology import TopologyTool
        except ImportError as error:
            self.skipTest(f"Topology tools need PySide and Pivy: {error}")

        class Session:
            pass

        obj = Forms.create_box(self.doc)
        self.doc.recompute()
        Forms.make_editable(obj)
        self.doc.recompute()
        before = _content(obj)
        face = ControlCage.from_object(obj).faces[0]
        first = tuple(sorted(face[:2]))
        opposite = tuple(sorted(face[2:]))
        for pair in ((first, opposite), (opposite, first)):
            insert_point_face_target(ControlCage.from_object(obj), *pair)
        session = Session()
        session.obj = obj
        session.insert_point_tool_active = True
        session.view = SimpleNamespace(redraw=lambda: None)
        session._flush_pending_updates = lambda: None
        session._begin_action = lambda label: False
        session._finish_action = lambda transaction, commit=True: None
        tool = TopologyTool(session)
        tool.insert_point_chain = [
            (first, 0.5, App.Vector()),
            (opposite, 0.5, App.Vector()),
            (first, 0.25, App.Vector()),
        ]
        self.assertFalse(tool._commit_insert_point_chain())
        # The next right-click exits the tool instead of retrying the chain.
        self.assertEqual(tool.insert_point_chain, [])
        self.assertIsNone(tool.insert_point_hover)
        self.assertEqual(_content(obj), before)

    def test_pipe_optional_metadata_preserves_geometry(self):
        from Forms.pipe import path_segments, swept_segment_cage

        shape = Part.makePolygon([App.Vector(0, 0, 0), App.Vector(0, 0, 10)])
        segments, adjacency = path_segments(shape)
        detailed_segments, detailed_adjacency, edges = path_segments(shape, include_edges=True)
        self.assertEqual(segments, detailed_segments)
        self.assertEqual(adjacency, detailed_adjacency)
        self.assertEqual(len(edges), 1)
        for points, open_ends in (
            ([App.Vector(0, 0, 0), App.Vector(0, 0, 10)], False),
            ([App.Vector(0, 0, 0), App.Vector(0, 0, 10)], True),
            ([App.Vector(0, 0, 0), App.Vector(10, 0, 0), App.Vector(10, 10, 0),
              App.Vector(0, 10, 0), App.Vector(0, 0, 0)], False),
        ):
            with self.subTest(points=points, open_ends=open_ends):
                geometry = swept_segment_cage(points, 2, open_start=open_ends, open_end=open_ends)
                detailed = swept_segment_cage(
                    points, 2, open_start=open_ends, open_end=open_ends, include_boundaries=True
                )
                self.assertEqual(geometry, detailed[:2])
                self.assertEqual(len(detailed), 4)
                self.assertEqual(detailed[2] is not None, open_ends)
                self.assertEqual(detailed[3] is not None, open_ends)

    def test_motion_preview_does_not_fit_or_modify_the_brep(self):
        obj = Forms.create_box(self.doc)
        Forms.subdivide_faces(obj, [0])
        self.doc.recompute()
        before = _content(obj)
        with patch.object(brep, "_make_surface", side_effect=AssertionError("BRep fitting in preview")):
            vertices, faces = mesh_preview(obj)
        self.assertTrue(vertices and faces)
        self.assertEqual(before, _content(obj))

    def test_thicken_apply_never_commits_an_earlier_preview(self):
        from Forms.tool_thicken import ThickenTool

        self.doc.UndoMode = 1
        obj = Forms.create_face(self.doc)
        self.doc.recompute()
        original = ControlCage.from_object(obj)
        undo_count = self.doc.UndoCount

        def start(thickness):
            session = _ToolSession(obj, "thicken")
            tool = ThickenTool(session)
            tool.thicken_original_cage = ControlCage.from_object(obj)
            tool.thicken_original_mode = str(obj.CageMode)
            tool.thicken_transaction_open = session._begin_action("Thicken form")
            tool.thicken_distance = Mock()
            tool.thicken_distance.value.return_value = thickness
            tool.thicken_apply_button = Mock()
            self.assertTrue(tool._apply_thicken_preview())
            return session, tool

        # The panel shows 0 after a 2 mm preview: Apply must not commit 2 mm.
        session, tool = start(2.0)
        tool.thicken_distance.value.return_value = 0.0
        self.assertFalse(tool.stop_thicken_tool(apply=True))
        self.assertEqual(session.active_tool, "thicken")
        self.assertNotEqual(self.doc.getBookedTransactionID(), 0)
        tool.stop_thicken_tool(apply=False)
        self.assertIsNone(session.active_tool)
        self.assertEqual(self.doc.UndoCount, undo_count)
        restored = ControlCage.from_object(obj)
        self.assertEqual(restored.vertices, original.vertices)
        self.assertEqual(restored.faces, original.faces)

        session, tool = start(2.0)
        self.assertTrue(tool.stop_thicken_tool(apply=True))
        self.assertIsNone(session.active_tool)
        self.assertEqual(self.doc.UndoCount, undo_count + 1)
        self.assertTrue(ControlCage.from_object(obj).is_closed)

    def test_flatten_and_straighten_report_missing_references_on_apply(self):
        from Forms.tool_flatten import FlattenTool
        from Forms.tool_straighten import StraightenTool

        self.doc.UndoMode = 1
        obj = Forms.create_face(self.doc)
        self.doc.recompute()
        points = list(obj.ControlPoints)
        undo_count = self.doc.UndoCount

        def combo(value):
            widget = Mock()
            widget.currentData.return_value = value
            return widget

        session = _ToolSession(obj, "flatten")
        flatten = FlattenTool(session)
        flatten.flatten_indices = [0, 1, 2]
        flatten.flatten_mode = combo("Reference")
        flatten.flatten_preview_status = Mock()
        # The tools only hold weak references: keep each session alive.
        cases = [(session, flatten.apply_flatten_tool, flatten.flatten_preview_status,
                  "Select a reference face or plane")]
        for mode, use_range, indices, message in (
            ("Line", False, [0, 1], "Select one straight edge or axis"),
            ("TwoPoints", False, [0, 1], "Select two reference points"),
            ("Fit", True, [0, 1, 2], "exactly two selected control points"),
        ):
            session = _ToolSession(obj, "straighten")
            straighten = StraightenTool(session)
            straighten.straighten_indices = indices
            straighten.straighten_mode = combo(mode)
            straighten.straighten_type = combo("ControlPoints")
            straighten.straighten_range = Mock()
            straighten.straighten_range.isChecked.return_value = use_range
            straighten.straighten_preview_status = Mock()
            cases.append((session, straighten.apply_straighten_tool,
                          straighten.straighten_preview_status, message))
        for session, apply, status, message in cases:
            with self.subTest(session.active_tool, message=message):
                # Task panel OK applies the active tool whatever its state.
                self.assertFalse(apply())
                self.assertIn(message, status.setText.call_args.args[0])
                self.assertEqual(self.doc.getBookedTransactionID(), 0)
                self.assertEqual(self.doc.UndoCount, undo_count)
                self.assertEqual(list(obj.ControlPoints), points)

    def test_switching_to_a_reference_mode_clears_the_previous_preview(self):
        from Forms.tool_flatten import FlattenTool
        from Forms.tool_straighten import StraightenTool

        obj = Forms.create_face(self.doc)
        self.doc.recompute()
        flatten_session = _ToolSession(obj, "flatten")
        flatten = FlattenTool(flatten_session)
        flatten.flatten_indices = [0, 1, 2]
        straighten_session = _ToolSession(obj, "straighten")
        straighten = StraightenTool(straighten_session)
        straighten.straighten_indices = [0, 1, 2]
        straighten.straighten_type = Mock()
        straighten.straighten_type.currentData.return_value = "ControlPoints"
        straighten.straighten_range = Mock()
        straighten.straighten_range.isChecked.return_value = False
        cases = (
            (flatten_session, flatten, "flatten_", "Reference", flatten._flatten_mode_changed),
            (straighten_session, straighten, "straighten_", "Line", straighten._straighten_mode_changed),
            (straighten_session, straighten, "straighten_", "TwoPoints", straighten._straighten_mode_changed),
        )
        for session, tool, prefix, mode, changed in cases:
            with self.subTest(mode=mode):
                # The previous mode left a preview and an enabled Apply button.
                preview = object()
                for name in ("mode", "reference_widget", "reference_button", "reference_name",
                             "preview_status", "apply_button"):
                    setattr(tool, prefix + name, Mock())
                getattr(tool, prefix + "mode").currentData.return_value = mode
                setattr(tool, prefix + "preview_root", preview)
                changed()
                session.panel._remove_shape_preview.assert_called_with(preview)
                self.assertIsNone(getattr(tool, prefix + "preview_root"))
                getattr(tool, prefix + "apply_button").setEnabled.assert_called_with(False)
                getattr(tool, prefix + "reference_button").setChecked.assert_called_with(True)

    def test_reference_picking_enables_3d_selection_while_picking(self):
        from Forms.edit import FormEditSession
        from Forms.tool_flatten import FlattenTool
        from Forms.tool_straighten import StraightenTool

        obj = Forms.create_face(self.doc)
        for tool_type, name in ((FlattenTool, "flatten"), (StraightenTool, "straighten")):
            with self.subTest(name):
                session = _ToolSession(obj, name)
                session.viewer = Mock()
                session.viewer.isSelectionEnabled.return_value = True
                session.selection_filter = Mock()
                session.dragger_switch = None
                session.selection_gate_added = False
                for method in (
                    "_suspend_selection_for_tool",
                    "_enable_tool_picking",
                    "_resume_selection_after_tool",
                ):
                    setattr(session, method, getattr(FormEditSession, method).__get__(session))
                tool = tool_type(session)
                for widget in ("mode", "reference_name", "preview_status"):
                    setattr(tool, f"{name}_{widget}", Mock())
                toggle = getattr(tool, f"_toggle_{name}_reference_selection")
                session._suspend_selection_for_tool()
                toggle(True)
                session.viewer.setSelectionEnabled.assert_called_with(True)
                toggle(False)
                session.viewer.setSelectionEnabled.assert_called_with(False)
                session._resume_selection_after_tool()
                self.assertEqual(
                    [call.args[0] for call in session.viewer.setSelectionEnabled.call_args_list],
                    [False, True, False, True],
                )

    def test_flatten_and_straighten_use_infinite_datum_references(self):
        from Forms.tool_flatten import FlattenTool
        from Forms.tool_straighten import StraightenTool

        obj = Forms.create_face(self.doc)
        obj.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation(App.Vector(1, 1, 1), 30))
        part = self.doc.addObject("App::Part", "Part")
        box = self.doc.addObject("Part::Box", "Box")
        box.Placement.Base = App.Vector(0, 0, 4)
        self.doc.recompute()
        origin = {feature.Role: feature for feature in part.Origin.OriginFeatures}
        points = [(point.x, point.y, point.z) for point in obj.ControlPoints]
        indices = list(range(len(points)))

        def session(tool):
            return _reference_tool_session(obj, tool)

        def placed(local_points):
            return [obj.Placement.multVec(App.Vector(*point)) for point in local_points]

        flatten_session = session("flatten")
        flatten = FlattenTool(flatten_session)
        flatten.flatten_mode = Mock()
        flatten.flatten_mode.currentData.return_value = "Reference"
        # Origin planes are infinite faces; the Box face is a bounded one.
        for source, subelement, axis, value in (
            (origin["XY_Plane"], "", 2, 0.0),
            (origin["XZ_Plane"], "", 1, 0.0),
            (origin["YZ_Plane"], "", 0, 0.0),
            (box, "Face6", 2, 14.0),
        ):
            with self.subTest(flatten=source.Name):
                flatten.flatten_reference = flatten._flatten_reference_from_event(
                    self.doc, source.Name, subelement
                )
                result = placed(topology.flatten_points(points, indices, flatten._flatten_plane()))
                for point in result:
                    self.assertAlmostEqual(point[axis], value, places=6)

        straighten_session = session("straighten")
        straighten = StraightenTool(straighten_session)
        straighten.straighten_mode = Mock()
        straighten.straighten_mode.currentData.return_value = "Line"
        # Origin axes are infinite edges; the Box edge lies on the Z axis.
        for source, subelement, axis in (
            (origin["X_Axis"], "", 0),
            (origin["Y_Axis"], "", 1),
            (origin["Z_Axis"], "", 2),
            (box, "Edge1", 2),
        ):
            with self.subTest(straighten=source.Name):
                straighten.straighten_references = [(source, subelement)]
                line = straighten._straighten_reference_line()
                result = placed(topology.straighten_points(points, [0, 1, 2], line)[:3])
                for point in result:
                    for other in {0, 1, 2} - {axis}:
                        self.assertAlmostEqual(point[other], 0.0, places=6)

    def test_flatten_and_straighten_resolve_references_picked_in_containers(self):
        from Forms.placement import global_placement
        from Forms.tool_flatten import FlattenTool
        from Forms.tool_straighten import StraightenTool

        doc = self.doc
        obj = Forms.create_face(doc)
        holder = doc.addObject("App::Part", "FormPart")
        holder.addObject(obj)
        holder.Placement = App.Placement(
            App.Vector(1, 2, 3), App.Rotation(App.Vector(1, 1, 1), 30)
        )
        # Part > Body > Box, twice: the picked body is moved and rotated, so a
        # pick resolved one level only lands on the other body's geometry.
        part = doc.addObject("App::Part", "Part")
        part.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90))
        for name in ("B1", "B2"):
            body = doc.addObject("PartDesign::Body", name)
            part.addObject(body)
            body.addObject(doc.addObject("PartDesign::AdditiveBox", name + "Box"))
        b1, b2 = doc.getObject("B1"), doc.getObject("B2")
        b1.Placement.Base = App.Vector(0, 0, 100)
        b2.Placement = App.Placement(App.Vector(0, -10, 0), App.Rotation(App.Vector(1, 0, 0), 90))
        b2_origin = {feature.Role: feature.Name for feature in b2.Origin.OriginFeatures}
        datum = doc.addObject("PartDesign::Plane", "DatumPlane")
        b2.addObject(datum)
        datum.AttachmentSupport = [(b2.Origin.getObject(b2_origin["XY_Plane"]), "")]
        datum.MapMode = "FlatFace"
        datum.AttachmentOffset = App.Placement(App.Vector(0, 0, 3), App.Rotation())
        b3 = doc.addObject("PartDesign::Body", "B3")
        b3.Placement.Base = App.Vector(0, 0, 7)
        box = doc.addObject("Part::Box", "Box")
        box.Placement.Base = App.Vector(0, 0, 50)
        link = doc.addObject("App::Link", "Link")
        link.LinkedObject = box
        link.Placement.Base = App.Vector(200, 0, 0)
        body_link = doc.addObject("App::Link", "BodyLink")
        body_link.LinkedObject = b2
        body_link.Placement.Base = App.Vector(0, 300, 0)
        doc.recompute()
        part_origin = {feature.Role: feature.Name for feature in part.Origin.OriginFeatures}
        b3_origin = {feature.Role: feature.Name for feature in b3.Origin.OriginFeatures}
        on_b2_origin = f"B2.{b2.Origin.Name}."
        on_part_origin = f"{part.Origin.Name}."
        points = [(point.x, point.y, point.z) for point in obj.ControlPoints]
        indices = list(range(len(points)))

        def placed(local_points):
            placement = global_placement(obj)
            return [placement.multVec(App.Vector(*point)) for point in local_points]

        flatten_session = _reference_tool_session(obj, "flatten")
        flatten = FlattenTool(flatten_session)
        flatten.flatten_mode = Mock()
        flatten.flatten_mode.currentData.return_value = "Reference"
        # (root, subname) as the selection reports them; global plane axis = value.
        for root, subname, axis, value in (
            (part, "B2.B2Box.Face6", 0, 25.0),
            (part, "B2.Face6", 0, 25.0),
            (part, on_b2_origin + b2_origin["XY_Plane"] + ".", 0, 15.0),
            (part, "B2.DatumPlane.", 0, 18.0),
            (part, on_part_origin + part_origin["XZ_Plane"] + ".", 0, 5.0),
            (b3, f"{b3.Origin.Name}.{b3_origin['XY_Plane']}.", 2, 7.0),
            (link, "Face6", 2, 10.0),
            (body_link, "B2Box.Face6", 2, 10.0),
        ):
            with self.subTest(flatten=f"{root.Name}.{subname}"):
                flatten.flatten_reference = flatten._flatten_reference_from_event(
                    doc.Name, root.Name, subname
                )
                result = placed(topology.flatten_points(points, indices, flatten._flatten_plane()))
                for point in result:
                    self.assertAlmostEqual(point[axis], value, places=6)
        self.assertEqual(
            flatten_session._reference_label((part, "B2.B2Box.Face6")), "B2Box [Face6]"
        )
        with self.assertRaisesRegex(ValueError, "other than the edited Form"):
            flatten._flatten_reference_from_event(doc.Name, holder.Name, f"{obj.Name}.Face1")

        straighten_session = _reference_tool_session(obj, "straighten")
        straighten = StraightenTool(straighten_session)
        straighten.straighten_mode = Mock()
        # Global coordinates every straightened point must have.
        for mode, picks, expected in (
            ("Line", [(part, "B2.B2Box.Edge1")], {1: 0.0, 2: 0.0}),
            ("Line", [(part, on_b2_origin + b2_origin["Y_Axis"] + ".")], {0: 15.0, 1: 0.0}),
            ("Line", [(part, on_part_origin + part_origin["X_Axis"] + ".")], {0: 5.0, 2: 0.0}),
            ("Line", [(link, "Edge1")], {0: 200.0, 1: 0.0}),
            ("TwoPoints", [(part, "B2.B2Box.Vertex1"), (part, "B2.Vertex2")], {1: 0.0, 2: 0.0}),
        ):
            with self.subTest(straighten=str([f"{root.Name}.{sub}" for root, sub in picks])):
                straighten.straighten_mode.currentData.return_value = mode
                straighten.straighten_references = [
                    straighten._straighten_reference_element(doc.Name, root.Name, subname)
                    for root, subname in picks
                ]
                line = straighten._straighten_reference_line()
                result = placed(topology.straighten_points(points, [0, 1, 2], line)[:3])
                for point in result:
                    for index, value in expected.items():
                        self.assertAlmostEqual(point[index], value, places=6)
        with self.assertRaisesRegex(ValueError, "other than the edited Form"):
            straighten_session._reference_edge((holder, f"{obj.Name}.Edge1"))


def suite():
    return unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTest)
