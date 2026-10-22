# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for associated constraints selected through sketch vertices."""

import json
import unittest
from xml.etree import ElementTree
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import Sketcher
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the native Sketcher task panel")
class TestAssociatedConstraintPointFilter28516Gui(unittest.TestCase):
    def setUp(self):
        self.doc_name = None
        self.saved_parameters = []
        self.previous_workbench = None
        self.addCleanup(self._cleanup)
        self.assertEqual(App.listDocuments(), {}, "Use an isolated GUI process")
        self.assertFalse(Gui.Control.activeDialog())
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.general = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher/General")
        self.sketcher = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Sketcher")
        for group, key, kind in (
            (self.general, "ConstraintFilterEnabled", "Bool"),
            (self.general, "SelectedConstraintFilters", "Int"),
            (self.sketcher, "VisualisationTrackingFilter", "Bool"),
        ):
            self._save_parameter(group, key, kind)
        self.general.SetBool("ConstraintFilterEnabled", True)
        self.general.RemInt("SelectedConstraintFilters")
        self.sketcher.SetBool("VisualisationTrackingFilter", False)
        Gui.activateWorkbench("SketcherWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("AssociatedPoint28516_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(
            [
                Part.LineSegment(App.Vector(2, 3, 0), App.Vector(12, 3, 0)),
                Part.LineSegment(App.Vector(20, 5, 0), App.Vector(20, 13, 0)),
            ],
            False,
        )
        self.sketch.addConstraint(
            [
                Sketcher.Constraint("Horizontal", 0),
                Sketcher.Constraint("DistanceX", 0, 1, 2.0),
                Sketcher.Constraint("DistanceY", 0, 1, 3.0),
                Sketcher.Constraint("Vertical", 1),
            ]
        )
        self.names = ("FirstHorizontal", "FirstStartX", "FirstStartY", "SecondVertical")
        for index, name in enumerate(self.names):
            self.sketch.renameConstraint(index, name)
        self.doc.recompute()
        self.assertEqual(self.sketch.solve(), 0)
        self.assertEqual((self.sketch.GeometryCount, self.sketch.ConstraintCount), (2, 4))
        self.assertEqual(self.sketch.getPoint(0, 1), App.Vector(2, 3, 0))
        self.assertEqual(self.sketch.getPoint(0, 2), App.Vector(12, 3, 0))
        self.assertTrue(Gui.activeDocument().setEdit(self.sketch.Name))
        self._events()
        self.assertIsNotNone(Gui.activeDocument().getInEdit())
        main = Gui.getMainWindow()
        listings = main.findChildren(QtWidgets.QListWidget, "listWidgetConstraints")
        self.assertEqual(len(listings), 1)
        self.listing = listings[0]
        self.form = self.listing.parentWidget()
        self.assertEqual(self.form.objectName(), "SketcherGui__TaskSketcherConstraints")
        self.assertEqual(
            self.form.findChild(QtWidgets.QListWidget, "listWidgetConstraints"), self.listing
        )
        ready = QtCore.QElapsedTimer()
        ready.start()
        while not self.listing.isVisible() and ready.elapsed() < 3000:
            self._events(50)
        self.assertTrue(self.listing.isVisible())
        self.assertEqual(self.listing.count(), 4)
        self.assertEqual(
            tuple(self.listing.item(row).data(QtCore.Qt.EditRole) for row in range(4)), self.names
        )
        checkboxes = self.form.findChildren(QtWidgets.QCheckBox, "filterBox")
        buttons = self.form.findChildren(QtWidgets.QToolButton, "filterButton")
        self.assertEqual(len(checkboxes), 1)
        self.assertEqual(len(buttons), 1)
        self.assertTrue(checkboxes[0].isChecked())
        self.assertTrue(buttons[0].isEnabled())
        actions = [
            action for action in buttons[0].actions() if isinstance(action, QtWidgets.QWidgetAction)
        ]
        self.assertEqual(len(actions), 1)
        self.filters = actions[0].defaultWidget()
        self.assertIsInstance(self.filters, QtWidgets.QListWidget)
        self.assertGreater(self.filters.count(), 2)
        # Source defines the last two rows as Selected, then Associated.
        self.selected_filter = self.filters.item(self.filters.count() - 2)
        self.associated_filter = self.filters.item(self.filters.count() - 1)
        self.assertEqual(self.selected_filter.checkState(), QtCore.Qt.Unchecked)
        self.assertEqual(self.associated_filter.checkState(), QtCore.Qt.Unchecked)
        self.assertEqual(self._visible_names(), set(self.names))

    def _save_parameter(self, group, key, kind):
        matches = [
            (entry_kind, value)
            for entry_kind, name, value in (group.GetContents() or [])
            if name == key
        ]
        self.assertLessEqual(len(matches), 1)
        if matches:
            self.assertEqual(matches[0][0], {"Bool": "Boolean", "Int": "Integer"}[kind])
        self.saved_parameters.append(
            (group, key, kind, bool(matches), matches[0][1] if matches else None)
        )

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _snapshot(self):
        return (
            tuple(geometry.Content for geometry in self.sketch.Geometry),
            tuple(
                (
                    constraint.Name,
                    constraint.Type,
                    constraint.First,
                    constraint.FirstPos,
                    constraint.Second,
                    constraint.SecondPos,
                    constraint.Third,
                    constraint.ThirdPos,
                    constraint.Value,
                )
                for constraint in self.sketch.Constraints
            ),
            tuple(self.doc.UndoNames),
            tuple(self.doc.RedoNames),
            self.doc.HasPendingTransaction,
        )

    def _visible_names(self):
        return {
            self.listing.item(row).data(QtCore.Qt.EditRole)
            for row in range(self.listing.count())
            if not self.listing.item(row).isHidden()
        }

    def _select(self, subname):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc_name, self.sketch.Name, subname)
        self._events()
        selected = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].Object.Name, self.sketch.Name)
        self.assertEqual(tuple(selected[0].SubElementNames), (subname,))

    def _command_point_names(self):
        self._select("Vertex1")
        command = Gui.Command.get("Sketcher_SelectConstraints")
        self.assertIsNotNone(command)
        self.assertTrue(command.isActive())
        Gui.runCommand("Sketcher_SelectConstraints")
        self._events()
        selected = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].Object.Name, self.sketch.Name)
        subnames = tuple(selected[0].SubElementNames)
        self.assertEqual(set(subnames), {"Constraint2", "Constraint3"})
        return {
            self.sketch.Constraints[int(name[len("Constraint") :]) - 1].Name for name in subnames
        }

    def _associated(self, subname, expected):
        before = self._snapshot()
        self._select(subname)
        # Public Qt check state emits the actual itemChanged/filter route.
        self.associated_filter.setCheckState(QtCore.Qt.Checked)
        self._events()
        actual = self._visible_names()
        print(
            "ASSOCIATED28516",
            json.dumps(
                {"selection": subname, "expected": sorted(expected), "visible": sorted(actual)},
                sort_keys=True,
            ),
        )
        self.assertEqual(self._snapshot(), before, "Filtering must not change geometry or history")
        self.assertEqual(actual, expected)

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name is not None and self.doc_name in App.listDocuments():
            Gui.getDocument(self.doc_name).resetEdit()
            self._events()
            App.closeDocument(self.doc_name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._events()
        for group, key, kind, present, value in reversed(self.saved_parameters):
            if present:
                getattr(group, "Set" + kind)(key, value)
            else:
                getattr(group, "Rem" + kind)(key)
            matches = [
                (entry_kind, saved)
                for entry_kind, name, saved in (group.GetContents() or [])
                if name == key
            ]
            stored_kind = {"Bool": "Boolean", "Int": "Integer"}[kind]
            self.assertEqual(matches, [(stored_kind, value)] if present else [])
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def test_unfiltered_named_constraints_remain_visible(self):
        before = self._snapshot()
        self._select("Vertex1")
        self.assertEqual(self._visible_names(), set(self.names))
        self.assertEqual(self._snapshot(), before)

    def test_edge_associated_filter_keeps_existing_geometry_scope(self):
        self._associated("Edge1", set(self.names[:3]))

    def test_existing_select_constraints_command_accepts_point(self):
        before = self._snapshot()
        self.assertEqual(self._command_point_names(), {"FirstStartX", "FirstStartY"})
        self.assertEqual(self._snapshot(), before)

    def test_vertex_associated_filter_matches_named_point_constraints(self):
        before = self._snapshot()
        self.assertEqual(self._command_point_names(), {"FirstStartX", "FirstStartY"})
        self.assertEqual(self._snapshot(), before)
        self._associated("Vertex1", {"FirstStartX", "FirstStartY"})

    def test_active_associated_filter_refreshes_on_point_selection(self):
        before = self._snapshot()
        self.assertEqual(self._command_point_names(), {"FirstStartX", "FirstStartY"})
        self._associated("Edge1", set(self.names[:3]))
        self._select("Vertex1")
        actual = self._visible_names()
        print(
            "ASSOCIATED28516_ACTIVE",
            json.dumps({"selection": "Vertex1", "visible": sorted(actual)}),
        )
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(actual, {"FirstStartX", "FirstStartY"})

    def _constraint_visibility(self):
        flags = []
        for index, constraint in enumerate(self.sketch.Constraints):
            node = ElementTree.fromstring(constraint.Content)
            self.assertEqual(node.tag, "Constrain")
            self.assertEqual(node.attrib["Name"], self.names[index])
            self.assertIn("IsVisible", node.attrib)
            self.assertIn(node.attrib["IsVisible"], ("0", "1"))
            flags.append(node.attrib["IsVisible"] == "1")
        return tuple(flags)

    def test_tracking_filter_applies_existing_visibility_policy_to_vertex(self):
        self.sketcher.SetBool("VisualisationTrackingFilter", True)
        self._select("Edge1")
        self.associated_filter.setCheckState(QtCore.Qt.Checked)
        self._events()
        self.assertEqual(self._visible_names(), set(self.names[:3]))
        self.assertEqual(self._constraint_visibility(), (True, True, True, False))
        self._select("Vertex1")
        actual_rows = self._visible_names()
        actual_visibility = self._constraint_visibility()
        print(
            "ASSOCIATED28516_TRACKING",
            json.dumps(
                {
                    "selection": "Vertex1",
                    "visible": sorted(actual_rows),
                    "IsVisible": actual_visibility,
                },
                sort_keys=True,
            ),
        )
        # Tracking intentionally changes visibility flags; do not demand unchanged history.
        with self.subTest(output="task_rows"):
            self.assertEqual(actual_rows, {"FirstStartX", "FirstStartY"})
        with self.subTest(output="constraint_visibility"):
            self.assertEqual(actual_visibility, (False, True, True, False))
