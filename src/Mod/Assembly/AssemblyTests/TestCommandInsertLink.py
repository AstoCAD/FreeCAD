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


def _msg(text, end="\n"):
    """Write messages to the console including the line ending."""
    App.Console.PrintMessage(text + end)


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestCommandInsertLink(AssemblyTestBase):
    """Unit tests for CommandInsertLink module."""

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
