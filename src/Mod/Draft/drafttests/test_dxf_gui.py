# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public     *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

"""Unit tests for the Draft Workbench, DXF import tests that need the GUI."""

## @package test_dxf_gui
# \ingroup drafttests
# \brief Unit tests for the Draft Workbench, DXF import tests that need the GUI.

## \addtogroup drafttests
# @{

import os
import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui


def _override_cursor():
    return QtGui.QApplication.overrideCursor()


def _clear_override_cursors():
    # Do not leave a wait cursor behind if a test fails.
    if QtGui.QApplication.overrideCursor() is not None:
        Gui.suspendWaitCursor()
    while QtGui.QApplication.overrideCursor() is not None:
        QtGui.QApplication.restoreOverrideCursor()


class DraftGuiDXF(unittest.TestCase):
    """DXF import from Python must not leave the wait cursor on."""

    def setUp(self):
        # These tests only make sense when no wait cursor is active.
        self.assertIsNone(_override_cursor())

    def tearDown(self):
        _clear_override_cursors()

    def test_resume_wait_cursor_without_wait_cursor(self):
        """resumeWaitCursor() must not start a wait cursor that nothing will stop.

        https://github.com/FreeCAD/FreeCAD/issues/31637
        """
        Gui.suspendWaitCursor()
        Gui.resumeWaitCursor()
        self.assertIsNone(_override_cursor(), "wait cursor left on after resumeWaitCursor()")

    def test_insert_dxf_from_python_restores_cursor(self):
        """importDXF.insert() called from a macro leaves no busy cursor.

        https://github.com/FreeCAD/FreeCAD/issues/31637
        The bug shows when 'Allow aborting recomputation' is off.
        """
        import importDXF

        in_file = os.path.join(App.getHomePath(), "Mod/Draft/drafttests/Issue24314.dxf")
        self.assertTrue(os.path.exists(in_file), in_file)

        hDraft = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
        hDoc = App.ParamGet("User parameter:BaseApp/Preferences/Document")
        wasShowDialog = hDraft.GetBool("dxfShowDialog", True)
        wasUseLegacyImporter = hDraft.GetBool("dxfUseLegacyImporter", False)
        wasCanAbort = hDoc.GetBool("CanAbortRecompute", True)
        doc = App.newDocument("DraftGuiDXFCursor")
        try:
            hDraft.SetBool("dxfShowDialog", False)
            hDraft.SetBool("dxfUseLegacyImporter", False)
            hDoc.SetBool("CanAbortRecompute", False)
            importDXF.insert(in_file, doc.Name)
            self.assertTrue(doc.Objects, "nothing imported")
            self.assertIsNone(_override_cursor(), "wait cursor left on after DXF insert")
        finally:
            hDraft.SetBool("dxfShowDialog", wasShowDialog)
            hDraft.SetBool("dxfUseLegacyImporter", wasUseLegacyImporter)
            hDoc.SetBool("CanAbortRecompute", wasCanAbort)
            App.closeDocument(doc.Name)


## @}
