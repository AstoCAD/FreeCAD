# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI regression test for the tab title of Python files opened in the editor.

Opening a macro through Macro > Macros... > Edit shows only the file name on
the tab, but opening the same file through File > Open, drag and drop or the
Start page showed its full path (issue #16237).

To run tests:
    FreeCAD -t TestPythonEditorTitleGui
"""

import os
import tempfile
import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtWidgets


@unittest.skipUnless(FreeCAD.GuiUp, "Requires the FreeCAD GUI")
class TestPythonEditorTitleGui(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="python_editor_title_")
        self.addCleanup(self.temporary.cleanup)
        self.path = os.path.join(self.temporary.name, "editor_title_macro.FCMacro")
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("# empty test macro\n")
        areas = FreeCADGui.getMainWindow().findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]

    def _editor_windows(self):
        return [
            window
            for window in self.area.subWindowList()
            if window.widget() is not None and window.widget().inherits("Gui::PythonEditorView")
        ]

    def test_opened_file_tab_shows_file_name_only(self):
        before = self._editor_windows()
        FreeCADGui.open(self.path)
        QtWidgets.QApplication.processEvents()
        created = [window for window in self._editor_windows() if window not in before]
        self.assertEqual(len(created), 1)
        window = created[0]
        try:
            title = window.widget().windowTitle()
            self.assertTrue(title.startswith("editor_title_macro.FCMacro[*]"), title)
            self.assertNotIn(self.temporary.name, title)
        finally:
            window.close()
            QtWidgets.QApplication.processEvents()
        self.assertEqual(self._editor_windows(), before)
