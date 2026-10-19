# SPDX-License-Identifier: LGPL-2.1-or-later
# /****************************************************************************
#                                                                           *
#    Copyright (c) 2025 Weston Schmidt <weston_schmidt@alumni.purdue.edu>   *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# ***************************************************************************/

"""
Unit tests for CommandInsertLink module.

This module contains unit tests to verify the proper handling of null
LinkedObject references in the TaskAssemblyInsertLink.accept() method.
Tests ensure that invalid objects are gracefully skipped without causing
AttributeError crashes.
"""

from AssemblyTests.TestCore import AssemblyTestBase
from contextlib import contextmanager
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import FreeCAD as App

# Only import CommandInsertLink if GUI is available
if App.GuiUp:
    import CommandInsertLink
    from PySide import QtCore, QtWidgets


def _msg(text, end="\n"):
    """Write messages to the console including the line ending."""
    App.Console.PrintMessage(text + end)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestCommandInsertLink(AssemblyTestBase):
    """Unit tests for CommandInsertLink module."""

    @contextmanager
    def _live_insertion_task(self):
        pref = CommandInsertLink.Preferences.preferences()
        saved_preferences = {
            key: pref.GetBool(key) if key in pref.GetBools() else None
            for key in ("InsertShowOnlyParts", "InsertRigidSubAssemblies")
        }
        task = None
        try:
            pref.SetBool("InsertShowOnlyParts", False)
            source = self.doc.addObject("Part::Box", "InsertionSource")
            self.doc.recompute()
            task = CommandInsertLink.TaskAssemblyInsertLink(
                self.assembly, CommandInsertLink.Gui.activeDocument().activeView()
            )
            yield task, source
        finally:
            try:
                if task is not None:
                    try:
                        task.reject()
                    finally:
                        task.form.deleteLater()
                        task.deleteLater()
                        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
                        QtWidgets.QApplication.processEvents()
            finally:
                for key, value in saved_preferences.items():
                    if value is None:
                        pref.RemBool(key)
                    else:
                        pref.SetBool(key, value)

    def _find_source_item(self, task, source):
        iterator = QtWidgets.QTreeWidgetItemIterator(task.form.partList)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == source:
                return item
            iterator += 1
        return None

    def _insert_occurrence(self, task, source):
        item = self._find_source_item(task, source)
        self.assertIsNotNone(item)
        # Suppress the first-component grounding question; keep the actual insertion.
        with patch.object(task, "handleFirstInsertion"):
            task.onItemClicked(item)
        return task.insertionStack[-1]

    def test_delete_occurrence_without_rebuilding_list(self):
        with self._live_insertion_task() as (task, source):
            inserted = self._insert_occurrence(task, source)
            self.doc.removeObject(inserted["addedObject"].Name)
            self.assertEqual(task.insertionStack, [])
            self.assertAlmostEqual(task.totalTranslation.Length, 0, places=9)
            self.assertEqual(self._find_source_item(task, source).text(0), source.Label)

    def test_rebuild_rebinds_occurrences_and_restores_counters(self):
        with self._live_insertion_task() as (task, source):
            first = self._insert_occurrence(task, source)
            second = self._insert_occurrence(task, source)
            task.buildPartList()
            task.buildPartList()
            item = self._find_source_item(task, source)
            self.assertIs(first["item"], item)
            self.assertIs(second["item"], item)
            self.assertEqual(item.text(0), f"{source.Label} : 2 inserted")

            self.doc.removeObject(second["addedObject"].Name)
            self.assertEqual(task.insertionStack, [first])
            self.assertEqual(item.text(0), f"{source.Label} : 1 inserted")
            self.doc.removeObject(first["addedObject"].Name)
            self.assertEqual(task.insertionStack, [])
            self.assertAlmostEqual(task.totalTranslation.Length, 0, places=9)
            self.assertEqual(item.text(0), source.Label)

    def test_delete_occurrences_while_source_is_filtered_out(self):
        with self._live_insertion_task() as (task, source):
            first = self._insert_occurrence(task, source)
            second = self._insert_occurrence(task, source)
            task.form.CheckBox_ShowOnlyParts.setChecked(True)
            self.assertIsNone(self._find_source_item(task, source))
            self.assertIsNone(first["item"])
            self.assertIsNone(second["item"])

            self.doc.removeObject(second["addedObject"].Name)
            self.doc.removeObject(first["addedObject"].Name)
            self.assertEqual(task.insertionStack, [])
            self.assertAlmostEqual(task.totalTranslation.Length, 0, places=9)

    def test_showing_filtered_source_restores_remaining_counter(self):
        with self._live_insertion_task() as (task, source):
            first = self._insert_occurrence(task, source)
            second = self._insert_occurrence(task, source)
            task.form.CheckBox_ShowOnlyParts.setChecked(True)
            self.doc.removeObject(second["addedObject"].Name)
            task.form.CheckBox_ShowOnlyParts.setChecked(False)

            item = self._find_source_item(task, source)
            self.assertIsNotNone(item)
            self.assertIs(first["item"], item)
            self.assertEqual(item.text(0), f"{source.Label} : 1 inserted")
            self.doc.removeObject(first["addedObject"].Name)
            self.assertEqual(task.insertionStack, [])
            self.assertAlmostEqual(task.totalTranslation.Length, 0, places=9)
            self.assertEqual(item.text(0), source.Label)

    def _check_macro_occurrence_state(
        self, count=1, rigid=None, displaced=False, final_placement=None
    ):
        replay_doc = None
        with self._live_insertion_task() as (task, source):
            if rigid is not None:
                source = self.doc.addObject("Assembly::AssemblyObject", "SubassemblySource")
                source.newObject("Part::Box", "SubassemblyBox")
                self.doc.recompute()
                task.buildPartList()
                task.form.CheckBox_RigidSubAsm.setChecked(rigid)

            view = CommandInsertLink.Gui.activeDocument().activeView()
            view.fitAll()
            CommandInsertLink.Gui.updateGui()
            if displaced:
                camera = view.getCameraNode()
                position = camera.position.getValue()
                camera.position.setValue(position[0] + 10000, position[1], position[2])
                CommandInsertLink.Gui.updateGui()
                origin_x, origin_y = view.getPointOnViewport(App.Vector())
                width, height = view.getSize()
                self.assertFalse(0 < origin_x < width and 0 < origin_y < height)

            occurrences = [
                self._insert_occurrence(task, source)["addedObject"] for _ in range(count)
            ]
            if final_placement is not None:
                occurrences[-1].Placement = final_placement
            expected = [(obj.Name, App.Placement(obj.Placement)) for obj in occurrences]
            child_placements = {}
            if rigid is not None:
                for occurrence in occurrences:
                    self.assertEqual(occurrence.Rigid, rigid)
                    child_placements[occurrence.Name] = {
                        child.LinkedObject.Name: occurrence.Placement * child.Placement
                        for child in occurrence.Group
                        if hasattr(child, "LinkedObject") and child.LinkedObject is not None
                    }
                    self.assertTrue(child_placements[occurrence.Name])
                if displaced:
                    self.assertTrue(
                        any(
                            placement.Base.Length > 100
                            for placements in child_placements.values()
                            for placement in placements.values()
                        )
                    )

            recorded = []
            with patch.object(CommandInsertLink.Gui, "doCommandSkip", side_effect=recorded.append):
                self.assertTrue(task.accept())
            self.assertEqual(len(recorded), 1)
            try:
                replay_doc = App.newDocument("InsertMacroOccurrenceReplay")
                replay_assembly = replay_doc.addObject("Assembly::AssemblyObject", "Assembly")
                if rigid is None:
                    replay_doc.addObject("Part::Box", source.Name)
                else:
                    replay_source = replay_doc.addObject("Assembly::AssemblyObject", source.Name)
                    replay_source.newObject("Part::Box", "SubassemblyBox")
                replay_doc.recompute()
                namespace = {"App": App, "UtilsAssembly": CommandInsertLink.UtilsAssembly}
                with patch.object(
                    CommandInsertLink.UtilsAssembly, "activeAssembly", return_value=replay_assembly
                ):
                    exec(compile(recorded[0], "<Insert Component macro>", "exec"), namespace)
                replay_doc.recompute()

                for name, placement in expected:
                    replayed = replay_doc.getObject(name)
                    self.assertIsNotNone(replayed)
                    if rigid is None:
                        with self.subTest(occurrence=name):
                            self.assertTrue(replayed.Placement.isSame(placement, 1e-9))
                        continue
                    with self.subTest(occurrence=name, property="Rigid"):
                        self.assertEqual(replayed.Rigid, rigid)
                    actual_children = {
                        child.LinkedObject.Name: replayed.Placement * child.Placement
                        for child in replayed.Group
                        if hasattr(child, "LinkedObject") and child.LinkedObject is not None
                    }
                    self.assertEqual(set(actual_children), set(child_placements[name]))
                    for child_name, expected_child in child_placements[name].items():
                        with self.subTest(occurrence=name, child=child_name):
                            self.assertTrue(actual_children[child_name].isSame(expected_child, 1e-9))
            finally:
                if replay_doc is not None:
                    App.closeDocument(replay_doc.Name)
                App.setActiveDocument(self.doc.Name)

    def test_macro_preserves_single_occurrence_placement(self):
        self._check_macro_occurrence_state()

    def test_macro_preserves_three_occurrence_placements(self):
        self._check_macro_occurrence_state(count=3)

    def test_macro_preserves_final_occurrence_placement(self):
        self._check_macro_occurrence_state(
            final_placement=App.Placement(
                App.Vector(1.23456789123, -9.87654321987, 3.45678912345),
                App.Rotation(App.Vector(1, 2, 3), 37.123456789),
            )
        )

    def test_macro_preserves_rigid_subassembly_at_origin(self):
        self._check_macro_occurrence_state(rigid=True)

    def test_macro_preserves_displaced_rigid_subassembly(self):
        self._check_macro_occurrence_state(rigid=True, displaced=True)

    def test_macro_preserves_displaced_flexible_subassembly(self):
        self._check_macro_occurrence_state(rigid=False, displaced=True)

    def _check_macro_label_round_trip(self, label):
        source = self.doc.addObject("Part::Box", "MacroSource")
        link = self.assembly.newObject("App::Link", "MacroOccurrence")
        link.setLink(source)
        link.Label = label
        self.doc.recompute()
        task = SimpleNamespace(
            deactivated=MagicMock(),
            groundedObj=None,
            insertionStack=[{"addedObject": link, "translation": App.Vector()}],
        )
        captured = []
        self.doc.openTransaction("Insert Component")
        with patch.object(CommandInsertLink.Gui, "doCommandSkip", side_effect=captured.append):
            self.assertTrue(CommandInsertLink.TaskAssemblyInsertLink.accept(task))
        self.assertEqual(len(captured), 1)

        replay_doc = App.newDocument("InsertComponentMacroReplay")
        try:
            replay_source = replay_doc.addObject("Part::Box", source.Name)
            replay_assembly = replay_doc.addObject("Assembly::AssemblyObject", "Assembly")
            namespace = {"App": App, "UtilsAssembly": CommandInsertLink.UtilsAssembly}
            with patch.object(
                CommandInsertLink.UtilsAssembly, "activeAssembly", return_value=replay_assembly
            ):
                exec(compile(captured[0], "<Insert Component macro>", "exec"), namespace)
            replayed = namespace["item"]
            self.assertEqual(replayed.Document, replay_doc)
            self.assertEqual(replayed.LinkedObject, replay_source)
            self.assertEqual(replayed.Label, label)
        finally:
            App.closeDocument(replay_doc.Name)
            App.setActiveDocument(self.doc.Name)

    def test_macro_preserves_ascii_label(self):
        self._check_macro_label_round_trip("Ordinary component")

    def test_macro_preserves_unicode_label(self):
        self._check_macro_label_round_trip("Café α 测量")

    def test_macro_preserves_quoted_label(self):
        self._check_macro_label_round_trip('Part "quoted"')

    def test_macro_preserves_literal_backslash_label(self):
        self._check_macro_label_round_trip("C:\\new\\tool")

    def test_macro_preserves_multiline_label(self):
        self._check_macro_label_round_trip("First line\nSecond line")

    def _check_macro_source_document(self, external, collision, close_source=False):
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        directory = Path(storage.name)
        source_document = self.doc
        replay_doc = None
        try:
            self.doc.saveAs(str(directory / "Assembly.FCStd"))
            if external:
                source_document = App.newDocument("InsertMacroExternalSource")
            source = source_document.addObject("Part::Box", "MacroSource")
            source_document.recompute()
            if external:
                source_document.saveAs(str(directory / "Component.FCStd"))
            App.setActiveDocument(self.doc.Name)
            link = self.assembly.newObject("App::Link", "MacroOccurrence")
            link.setLink(source)
            self.doc.recompute()
            task = SimpleNamespace(
                deactivated=MagicMock(),
                groundedObj=None,
                insertionStack=[{"addedObject": link, "translation": App.Vector()}],
            )
            captured = []
            self.doc.openTransaction("Insert Component")
            with patch.object(CommandInsertLink.Gui, "doCommandSkip", side_effect=captured.append):
                self.assertTrue(CommandInsertLink.TaskAssemblyInsertLink.accept(task))
            self.assertEqual(len(captured), 1)

            replay_doc = App.newDocument("InsertMacroSourceDocumentReplay")
            replay_assembly = replay_doc.addObject("Assembly::AssemblyObject", "Assembly")
            local_source = None
            if not external or collision:
                local_source = replay_doc.addObject("Part::Box", source.Name)
            replay_doc.saveAs(str(directory / "Replay.FCStd"))
            if close_source:
                App.closeDocument(source_document.Name)
                source_document = None
                App.setActiveDocument(replay_doc.Name)
            namespace = {"App": App, "UtilsAssembly": CommandInsertLink.UtilsAssembly}
            with patch.object(
                CommandInsertLink.UtilsAssembly, "activeAssembly", return_value=replay_assembly
            ):
                command = compile(captured[0], "<Insert Component macro>", "exec")
                if close_source:
                    with self.assertRaisesRegex(NameError, "Unknown document"):
                        exec(command, namespace)
                    self.assertIsNone(namespace["item"].LinkedObject)
                else:
                    exec(command, namespace)
                    self.assertEqual(
                        namespace["item"].LinkedObject, source if external else local_source
                    )
        finally:
            if replay_doc is not None:
                App.closeDocument(replay_doc.Name)
            if source_document is not None and source_document != self.doc:
                App.closeDocument(source_document.Name)
            App.setActiveDocument(self.doc.Name)

    def test_macro_replays_same_document_source_in_new_document(self):
        self._check_macro_source_document(external=False, collision=False)

    def test_macro_preserves_external_source_without_local_namesake(self):
        self._check_macro_source_document(external=True, collision=False)

    def test_macro_preserves_external_source_with_local_namesake(self):
        self._check_macro_source_document(external=True, collision=True)

    def test_macro_does_not_replace_closed_external_source_with_local_namesake(self):
        self._check_macro_source_document(external=True, collision=True, close_source=True)

    def test_open_files_with_same_basename_in_different_directories(self):
        """Distinct component files must both be available for insertion."""
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / folder / "Part.FCStd" for folder in ("First", "Second")]
            for index, path in enumerate(paths):
                path.parent.mkdir()
                source = App.newDocument(f"InsertComponentSource{index}")
                source.addObject("Part::Box", f"Box{index}")
                source.recompute()
                source.saveAs(str(path))
                App.closeDocument(source.Name)

            try:
                App.openDocument(str(paths[0]), True)
                App.setActiveDocument(self.doc.Name)
                task = SimpleNamespace(doc=self.doc, buildPartList=MagicMock())
                with patch(
                    "CommandInsertLink.QtGui.QFileDialog.getOpenFileNames",
                    return_value=([str(paths[1])], ""),
                ):
                    CommandInsertLink.TaskAssemblyInsertLink.openFiles(task)

                opened_paths = {
                    os.path.normcase(os.path.realpath(doc.FileName))
                    for doc in App.listDocuments().values()
                    if doc.FileName
                }
                for path in paths:
                    self.assertIn(os.path.normcase(os.path.realpath(path)), opened_paths)
                self.assertEqual(App.ActiveDocument, self.doc)
                task.buildPartList.assert_called_once_with()
            finally:
                for doc in list(App.listDocuments().values()):
                    if doc != self.doc and Path(doc.FileName) in paths:
                        App.closeDocument(doc.Name)
                App.setActiveDocument(self.doc.Name)

    def test_open_files_does_not_reopen_existing_component(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Part.FCStd"
            source = App.newDocument("InsertComponentExistingSource")
            source.addObject("Part::Box", "Box")
            source.recompute()
            source.saveAs(str(path))
            App.setActiveDocument(self.doc.Name)
            try:
                task = SimpleNamespace(doc=self.doc, buildPartList=MagicMock())
                # A different path spelling that resolves to the same file.
                selection = str(path.parent / ".." / path.parent.name / path.name)
                with (
                    patch(
                        "CommandInsertLink.QtGui.QFileDialog.getOpenFileNames",
                        return_value=([selection], ""),
                    ),
                    patch("CommandInsertLink.App.openDocument") as open_document,
                ):
                    CommandInsertLink.TaskAssemblyInsertLink.openFiles(task)
                open_document.assert_not_called()
                task.buildPartList.assert_not_called()
            finally:
                App.closeDocument(source.Name)
                App.setActiveDocument(self.doc.Name)

    @patch("FreeCADGui.PySideUic.loadUi")
    @patch("CommandInsertLink.TaskAssemblyInsertLink.adjustTreeWidgetSize")
    def test_mixed_valid_and_invalid_objects(self, _mock_adjustTreeSize, _mock_loadUi):
        """Test that accept() handles a mix of valid and invalid objects correctly."""
        operation = "Handle mixed valid/invalid objects"
        _msg(f"  Test '{operation}'")

        mock_view = MagicMock()
        mock_view.getSize = MagicMock(return_value=(800, 600))
        task = CommandInsertLink.TaskAssemblyInsertLink(self.assembly, mock_view)

        # Create a mix of valid and invalid objects
        test_objects = [
            # Valid object (would work in real scenario)
            {
                "addedObject": type(
                    "ValidObject",
                    (),
                    {
                        "Name": "ValidObject",
                        "Label": "Valid Object",
                        "LinkedObject": type(
                            "ValidLinkedObject", (), {"Name": "ValidLinkedObjectName"}
                        )(),
                    },
                )(),
                "translation": App.Vector(1, 1, 1),
            },
            # Invalid: LinkedObject is None
            {
                "addedObject": type(
                    "InvalidObject1",
                    (),
                    {"Name": "InvalidObject1", "Label": "Invalid Object 1", "LinkedObject": None},
                )(),
                "translation": App.Vector(2, 2, 2),
            },
            # Invalid: No LinkedObject attribute
            {
                "addedObject": type(
                    "InvalidObject2", (), {"Name": "InvalidObject2", "Label": "Invalid Object 2"}
                )(),
                "translation": App.Vector(3, 3, 3),
            },
            # Invalid: LinkedObject.Name is None
            {
                "addedObject": type(
                    "InvalidObject3",
                    (),
                    {
                        "Name": "InvalidObject3",
                        "Label": "Invalid Object 3",
                        "LinkedObject": type("LinkedObjectWithNoneName", (), {"Name": None})(),
                    },
                )(),
                "translation": App.Vector(4, 4, 4),
            },
            # Invalid: No Name attribute
            {
                "addedObject": type(
                    "InvalidObject4",
                    (),
                    {
                        "Label": "Invalid Object 4",
                        "LinkedObject": type("LinkedObject", (), {"Name": "Something"})(),
                    },
                )(),
                "translation": App.Vector(5, 5, 5),
            },
        ]

        # Add all objects to insertion stack
        for obj_data in test_objects:
            # All real document objects provide this method, independently of
            # whether their linked target is valid.
            obj_data["addedObject"].isDerivedFrom = lambda type_name: False
            obj_data["addedObject"].Document = self.doc
            obj_data["addedObject"].Placement = App.Placement(
                obj_data["translation"], App.Rotation()
            )
            linked = getattr(obj_data["addedObject"], "LinkedObject", None)
            if linked is not None:
                linked.Document = self.doc
            task.insertionStack.append(obj_data)

        # Should handle the mix gracefully - invalid objects skipped, valid ones processed
        result = task.accept()
        self.assertTrue(result, "accept() should return True even with mixed valid/invalid objects")
        _msg("  Successfully handled mixed valid/invalid objects")

    @patch("FreeCADGui.PySideUic.loadUi")
    @patch("CommandInsertLink.TaskAssemblyInsertLink.adjustTreeWidgetSize")
    def test_empty_insertion_stack(self, _mock_adjustTreeSize, _mock_ui):
        """Test that accept() handles empty insertion stack correctly."""
        operation = "Handle empty insertion stack"
        _msg(f"  Test '{operation}'")

        mock_view = MagicMock()
        mock_view.getSize = MagicMock(return_value=(800, 600))
        task = CommandInsertLink.TaskAssemblyInsertLink(self.assembly, mock_view)

        # Don't add anything to insertion stack - it should remain empty
        self.assertEqual(len(task.insertionStack), 0, "Insertion stack should be empty")

        result = task.accept()
        self.assertTrue(result, "accept() should return True even with empty insertion stack")
        _msg("  Successfully handled empty insertion stack")
