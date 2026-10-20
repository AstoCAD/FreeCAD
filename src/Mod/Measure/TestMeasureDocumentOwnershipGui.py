# SPDX-License-Identifier: LGPL-2.1-or-later
"""Measure callbacks retain the exact document owning their task dialog."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
import MeasureGui  # noqa: F401
try:
    import Sketcher
    import SketcherGui  # noqa: F401
except ModuleNotFoundError as error:
    if error.name not in {"Sketcher", "SketcherGui"}:
        raise
    Sketcher = None
from PySide import QtCore, QtWidgets
try:
    from PySide6 import QtTest
except ImportError:
    from PySide2 import QtTest


class _MeasureCreationLog:
    def __init__(self):
        self.events = []

    def slotCreatedObject(self, obj):
        if obj.isDerivedFrom("Measure::MeasureBase"):
            self.events.append((obj.Document.Name, obj.Name, obj.TypeId))


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
@unittest.skipIf(Sketcher is None, "Requires the Sketcher module")
class TestMeasureDocumentOwnershipGui(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_selection = []
        for item in Gui.Selection.getSelectionEx("*", 0):
            subnames = list(item.SubElementNames) or [""]
            points = list(item.PickedPoints)
            for index, subname in enumerate(subnames):
                point = points[index] if index < len(points) else App.Vector()
                self.previous_selection.append((item.Object.Document.Name, item.Object.Name,
                                                subname, point.x, point.y, point.z))
        self.docs = []
        self.strong_widgets = []
        self.settings = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Measure/TaskMeasure")
        keys = ("AutoSave", "GreedySelection", "ShowDelta")
        contents = self.settings.GetContents() or []
        self.preferences = {
            key: (any(kind == "Boolean" and name == key for kind, name, value in contents),
                  self.settings.GetBool(key, False)) for key in keys
        }
        self.addCleanup(self._cleanup)
        self.assertIsNone(Gui.Control.activeTaskDialog(), "Fixture requires no existing active task")
        self.settings.SetBool("AutoSave", False)
        self.settings.SetBool("GreedySelection", False)
        Gui.Selection.clearSelection()
        Gui.activateWorkbench("PartWorkbench")
        self.log = _MeasureCreationLog()
        App.addDocumentObserver(self.log)
        self.observer_attached = True

        self.a = App.newDocument("MeasureOwnerA")
        self.docs.append(self.a)
        self.a.UndoMode = 1
        self.box_a = self.a.addObject("Part::Box", "BoxA")
        self.box_a.Length, self.box_a.Width, self.box_a.Height = 2, 3, 4
        self.a.recompute()
        self.b = App.newDocument("MeasureForeignB")
        self.docs.append(self.b)
        self.b.UndoMode = 1
        self.box_b = self.b.addObject("Part::Box", "BoxB")
        self.box_b.Length, self.box_b.Width, self.box_b.Height = 5, 6, 7
        self.sketch_b = self.b.addObject("Sketcher::SketchObject", "SketchB")
        self.sketch_b.addGeometry(Part.LineSegment(App.Vector(20, 0, 0), App.Vector(30, 3, 0)), False)
        self.b.recompute()
        for box in (self.box_a, self.box_b):
            self.assertTrue(box.Shape.isValid())
            self.assertEqual(len(box.Shape.Edges), 12)
        self.assertEqual(self.sketch_b.GeometryCount, 1)
        self.assertEqual(self.sketch_b.ConstraintCount, 0)
        self._activate(self.a)
        self._select(self.a, self.box_a, "Edge1")
        Gui.runCommand("Std_Measure")
        self._wait(lambda: self._dialog(self.a) is not None, "Owner measurement task did not open")
        self.task_a = self._dialog(self.a)
        self.assertEqual(self.task_a.getDocumentName(), self.a.Name)
        self.stack, self.panel_a = self._panel(self.task_a)
        self.buttons_a = self.panel_a.findChild(QtWidgets.QDialogButtonBox)
        self.assertIsNotNone(self.buttons_a)
        self.strong_widgets.extend([self.buttons_a, *self.buttons_a.buttons()])
        self._wait(lambda: len(self._measurements(self.a)) == 1,
                   "Owner edge did not create a measurement")
        self.assertTrue(self.buttons_a.button(QtWidgets.QDialogButtonBox.Apply).isEnabled())
        measure = self._measurements(self.a)[0]
        self.assertEqual(measure.TypeId, "Measure::MeasureLength")
        self.assertAlmostEqual(measure.Length.Value, self.box_a.Shape.Edges[0].Length, places=9)
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(self.stack.currentWidget(), self.panel_a)
        self.owner_before = self._snapshot(self.a)
        self.log.events.clear()

    def _pump(self):
        Gui.updateGui()
        QtTest.QTest.qWait(80)
        Gui.updateGui()

    def _wait(self, predicate, message):
        clock = QtCore.QElapsedTimer()
        clock.start()
        while not predicate() and clock.elapsed() < 2500:
            self._pump()
        self.assertTrue(predicate(), message)

    def _activate(self, doc):
        App.setActiveDocument(doc.Name)
        self._pump()
        self.assertEqual(App.ActiveDocument.Name, doc.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, doc.Name)

    def _dialog(self, doc):
        return Gui.Control.activeTaskDialog(Gui.getDocument(doc.Name))

    def _panel(self, dialog):
        contents = dialog.getDialogContent()
        self.assertTrue(contents)
        self.strong_widgets.extend([dialog, *contents])
        panel = contents[0]
        while panel is not None:
            parent = panel.parentWidget()
            self.strong_widgets.append(parent)
            if isinstance(parent, QtWidgets.QStackedWidget):
                return parent, panel
            panel = parent
        self.fail("Task content has no native stacked task-panel ancestor")

    def _select(self, doc, obj, subname):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(doc.Name, obj.Name, subname)
        self._pump()
        selections = Gui.Selection.getSelectionEx(doc.Name, 0)
        self.assertEqual(len(selections), 1, "Native selection was unexpectedly cleared")
        self.assertEqual(selections[0].Object.Name, obj.Name)
        self.assertEqual(tuple(selections[0].SubElementNames), (subname,) if subname else ())
        if subname:
            self.assertEqual(len(selections[0].SubObjects), 1)
            selected = selections[0].SubObjects[0]
            self.assertEqual(selected.ShapeType, "Edge")
            self.assertGreater(selected.Length, 0)

    @staticmethod
    def _measurements(doc):
        return [obj for obj in doc.Objects if obj.isDerivedFrom("Measure::MeasureBase")]

    def _snapshot(self, doc):
        result = []
        for obj in self._measurements(doc):
            refs = []
            if "Elements" in obj.PropertiesList:
                refs = [(target.Document.Name, target.Name, tuple(subs))
                        for target, subs in obj.Elements]
            value = obj.Length.Value if "Length" in obj.PropertiesList else None
            result.append((obj.Name, obj.TypeId, refs, value))
        return result

    def _assert_isolated(self, stage):
        with self.subTest(stage=stage, invariant="no foreign creation"):
            self.assertEqual([event for event in self.log.events if event[0] == self.b.Name], [])
            self.assertEqual(self._measurements(self.b), [])
        with self.subTest(stage=stage, invariant="owner preview preserved"):
            self.assertEqual(self._snapshot(self.a), self.owner_before)
        with self.subTest(stage=stage, invariant="owner panel remains hidden"):
            self.assertNotEqual(self.stack.currentWidget(), self.panel_a)
        self.assertEqual(App.ActiveDocument.Name, self.b.Name)

    def _owner_update(self):
        first_length = self.box_a.Shape.Edges[0].Length
        index = next(i for i, edge in enumerate(self.box_a.Shape.Edges, 1)
                     if edge.Length != first_length)
        self._select(self.a, self.box_a, "Edge" + str(index))
        self.assertEqual(len(self._measurements(self.a)), 1)
        current = self._measurements(self.a)[0]
        self.assertEqual(current.TypeId, "Measure::MeasureLength")
        self.assertAlmostEqual(current.Length.Value, self.box_a.Shape.Edges[index - 1].Length, places=9)
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(self.stack.currentWidget(), self.panel_a)

    def test_owner_edge_selection_updates_own_preview_control(self):
        self._owner_update()

    def test_switch_without_foreign_selection_preserves_owner_and_hides_task(self):
        self._activate(self.b)
        self._assert_isolated("FOREIGN_ACTIVATE_ONLY")

    def test_foreign_edge_does_not_create_measurement_or_change_owner(self):
        self._activate(self.b)
        with self.subTest(invariant="foreign native edge selection persists"):
            self._select(self.b, self.box_b, "Edge1")
        self._assert_isolated("FOREIGN_EDGE_SELECTED")

    def test_foreign_sketch_does_not_create_measurement_or_change_owner(self):
        self._activate(self.b)
        with self.subTest(invariant="foreign native sketch selection persists"):
            self._select(self.b, self.sketch_b, "")
        self._assert_isolated("FOREIGN_SKETCH_SELECTED")

    def _foreign_sketch_edit(self, accept):
        self._activate(self.b)
        with self.subTest(invariant="foreign native sketch selection persists"):
            self._select(self.b, self.sketch_b, "")
        self._assert_isolated("BEFORE_FOREIGN_SKETCH_EDIT")
        gui_b = Gui.getDocument(self.b.Name)
        self.assertTrue(gui_b.setEdit(self.sketch_b.Name))
        self._pump()
        dialog_b = self._dialog(self.b)
        self.assertIsNotNone(dialog_b)
        stack_b, panel_b = self._panel(dialog_b)
        self.assertEqual(stack_b, self.stack)
        self.assertEqual(stack_b.currentWidget(), panel_b)
        self.assertIsNotNone(gui_b.getInEdit())
        if accept:
            dialog_b.accept()
        else:
            dialog_b.reject()
        self._pump()
        self.assertIsNone(gui_b.getInEdit())
        self.assertIsNone(self._dialog(self.b))
        self.assertEqual(self.sketch_b.GeometryCount, 1)
        self.assertEqual(self.sketch_b.ConstraintCount, 0)
        self.assertIsNotNone(self._dialog(self.a))
        self._assert_isolated("FOREIGN_SKETCH_ACCEPTED" if accept else "FOREIGN_SKETCH_CANCELLED")

    def test_foreign_sketch_accept_does_not_expose_owner_task(self):
        self._foreign_sketch_edit(True)

    def test_foreign_sketch_cancel_does_not_expose_owner_task(self):
        self._foreign_sketch_edit(False)

    def test_return_to_owner_updates_and_closes_normally_control(self):
        self._activate(self.b)
        self._activate(self.a)
        self._owner_update()
        self.task_a.reject()
        self._pump()
        self.assertIsNone(self._dialog(self.a))
        self.assertEqual(self._measurements(self.a), [])
        self.assertEqual(self._measurements(self.b), [])

    def _cleanup(self):
        for doc in self.docs:
            if doc.Name not in App.listDocuments():
                continue
            self._activate(doc)
            gui_doc = Gui.getDocument(doc.Name)
            if gui_doc.getInEdit():
                gui_doc.resetEdit()
                self._pump()
            dialog = self._dialog(doc)
            if dialog:
                dialog.reject()
                self._pump()
            if self._dialog(doc):
                Gui.Control.closeDialog(gui_doc)
                self._pump()
        if getattr(self, "observer_attached", False):
            App.removeDocumentObserver(self.log)
            self.observer_attached = False
        Gui.Selection.clearSelection()
        for doc in reversed(self.docs):
            if doc.Name in App.listDocuments():
                App.closeDocument(doc.Name)
                self._pump()
        for key, (present, value) in self.preferences.items():
            if present:
                self.settings.SetBool(key, value)
            else:
                self.settings.RemBool(key)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        elif self.previous_document is None:
            App.setActiveDocument("")
        for args in self.previous_selection:
            doc_name, obj_name = args[:2]
            doc = App.getDocument(doc_name) if doc_name in App.listDocuments() else None
            if doc and doc.getObject(obj_name):
                Gui.Selection.addSelection(*args)
        self._pump()

    def _enable_auto_save(self):
        candidates = []
        for button in self.panel_a.findChildren(QtWidgets.QToolButton):
            menu = button.menu()
            if menu is not None and len(menu.actions()) == 2:
                actions = menu.actions()
                if all(action.isCheckable() for action in actions):
                    candidates.append((button, menu, actions))
        self.assertEqual(len(candidates), 1, "Expected the native two-action Measure settings menu")
        button, menu, actions = candidates[0]
        self.strong_widgets.extend([button, menu, *actions])
        auto_save = actions[0]
        self.assertFalse(auto_save.isChecked())
        auto_save.trigger()
        self.assertTrue(auto_save.isChecked())
        self.assertTrue(self.settings.GetBool("AutoSave", False))
        self.assertEqual(self._snapshot(self.a), self.owner_before)
        self.assertIsNone(self.a.getObject("Measurements"))

    def test_auto_save_owner_selection_still_saves_previous_measure_control(self):
        self._enable_auto_save()
        initial = self._measurements(self.a)[0]
        initial_name = initial.Name
        first_length = initial.Length.Value
        index = next(i for i, edge in enumerate(self.box_a.Shape.Edges, 1)
                     if edge.Length != first_length)
        self._select(self.a, self.box_a, "Edge" + str(index))
        group = self.a.getObject("Measurements")
        self.assertIsNotNone(group)
        self.assertEqual([obj.Name for obj in group.Group], [initial_name])
        self.assertEqual(len(self._measurements(self.a)), 2)
        saved = self.a.getObject(initial_name)
        self.assertAlmostEqual(saved.Length.Value, first_length, places=9)
        preview = next(obj for obj in self._measurements(self.a) if obj.Name != initial_name)
        self.assertAlmostEqual(preview.Length.Value, self.box_a.Shape.Edges[index - 1].Length,
                               places=9)
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(self.stack.currentWidget(), self.panel_a)

    def test_auto_save_foreign_selection_does_not_save_or_replace_owner_preview(self):
        self._enable_auto_save()
        self._activate(self.b)
        with self.subTest(invariant="foreign native selection persists"):
            self._select(self.b, self.box_b, "Edge1")
        self._assert_isolated("AUTO_SAVE_FOREIGN_SELECTION")
        with self.subTest(invariant="foreign event must not save the owner preview"):
            self.assertIsNone(self.a.getObject("Measurements"))

    def _close_initial_task(self):
        self.assertEqual(App.ActiveDocument.Name, self.a.Name)
        self.task_a.reject()
        self._pump()
        self.assertIsNone(self._dialog(self.a))
        self.assertEqual(self._measurements(self.a), [])
        self.assertEqual(self._measurements(self.b), [])
        self.log.events.clear()

    def _open_owner_task_without_event_turn(self):
        self.assertEqual(App.ActiveDocument.Name, self.a.Name)
        Gui.runCommand("Std_Measure")
        self.task_a = self._dialog(self.a)
        self.assertIsNotNone(self.task_a)
        self.assertEqual(self.task_a.getDocumentName(), self.a.Name)
        self.stack, self.panel_a = self._panel(self.task_a)
        self.assertEqual(self._measurements(self.a), [],
                         "Fixture must reach the pending initialization timer before it fires")
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(self.log.events, [], "No synchronous selection update may create a preview")

    def test_queued_initialization_still_creates_owner_preview_control(self):
        self._close_initial_task()
        self._select(self.a, self.box_a, "Edge1")
        self._open_owner_task_without_event_turn()
        self._wait(lambda: len(self._measurements(self.a)) == 1,
                   "Active owner initialization must still create its preview")
        measure = self._measurements(self.a)[0]
        self.assertEqual(measure.TypeId, "Measure::MeasureLength")
        self.assertAlmostEqual(measure.Length.Value, self.box_a.Shape.Edges[0].Length, places=9)
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(self.stack.currentWidget(), self.panel_a)

    def test_queued_initialization_after_switch_does_not_measure_foreign_selection(self):
        self._close_initial_task()
        self._select(self.b, self.box_b, "Edge1")
        self.assertEqual(App.ActiveDocument.Name, self.a.Name,
                         "Public selection of a foreign object must not activate its document")
        self._open_owner_task_without_event_turn()
        App.setActiveDocument(self.b.Name)
        self.assertEqual(App.ActiveDocument.Name, self.b.Name)
        self.assertEqual(self._measurements(self.a), [])
        self.assertEqual(self._measurements(self.b), [],
                         "Document activation must not synchronously initialize the preview")
        self.assertEqual(self.log.events, [], "Only the pending timer may reach this boundary")
        self._pump()
        with self.subTest(invariant="delayed owner invoke creates no foreign measurement"):
            self.assertEqual(self._measurements(self.b), [])
            self.assertEqual(self.log.events, [])
        with self.subTest(invariant="inactive owner remains empty"):
            self.assertEqual(self._measurements(self.a), [])
        with self.subTest(invariant="inactive owner panel remains hidden"):
            self.assertNotEqual(self.stack.currentWidget(), self.panel_a)

    def test_two_independent_measure_tasks_update_only_their_active_owner(self):
        self._activate(self.b)
        Gui.runCommand("Std_Measure")
        self._wait(lambda: self._dialog(self.b) is not None, "Foreign-owned task did not open")
        task_b = self._dialog(self.b)
        self.assertEqual(task_b.getDocumentName(), self.b.Name)
        stack_b, panel_b = self._panel(task_b)
        self.assertEqual(stack_b, self.stack)
        self.assertEqual(self.stack.currentWidget(), panel_b)
        self._select(self.b, self.box_b, "Edge1")
        with self.subTest(invariant="B task still creates its own correct preview"):
            self.assertEqual(len(self._measurements(self.b)), 1)
            measure = self._measurements(self.b)[0]
            self.assertEqual(measure.TypeId, "Measure::MeasureLength")
            self.assertAlmostEqual(measure.Length.Value, self.box_b.Shape.Edges[0].Length,
                                   places=9)
        with self.subTest(invariant="inactive A preview remains unchanged"):
            self.assertEqual(self._snapshot(self.a), self.owner_before)
        self.assertEqual(self.stack.currentWidget(), panel_b)
        task_b.reject()
        self._pump()
        self.assertIsNone(self._dialog(self.b))
        self.assertIsNotNone(self._dialog(self.a))
        self.assertNotEqual(self.stack.currentWidget(), self.panel_a)
        self._activate(self.a)
        self._owner_update()

    def test_owner_document_close_destroys_task_before_later_foreign_selection_control(self):
        self._activate(self.b)
        owner_name = self.a.Name
        self.docs.remove(self.a)
        del self.stack
        App.closeDocument(owner_name)
        self._pump()
        self.assertNotIn(owner_name, App.listDocuments())
        self.assertIsNone(self._dialog(self.b))
        self.log.events.clear()
        self._select(self.b, self.box_b, "Edge1")
        self.assertEqual(self.log.events, [])
        self.assertEqual(self._measurements(self.b), [])
        self.assertEqual(App.ActiveDocument.Name, self.b.Name)
