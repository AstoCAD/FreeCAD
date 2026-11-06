# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI regression test for "Execute in Console" of the Python editor.

The selected code was passed to Gui::Command::doCommand() as its printf
format, so every '%' in it was taken as a conversion: "%%" became "%" and
"%d" or "%s" read arguments that were never passed.

To run tests:
    FreeCAD -t TestPythonEditorExecuteGui
"""

import os
import tempfile
import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtCore, QtWidgets

RESULT = "_test_python_editor_execute_result"


@unittest.skipUnless(FreeCAD.GuiUp, "Requires the FreeCAD GUI")
class TestPythonEditorExecuteGui(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="python_editor_execute_")
        self.addCleanup(self.temporary.cleanup)
        self.path = os.path.join(self.temporary.name, "editor_execute_macro.FCMacro")
        with open(self.path, "w", encoding="utf-8") as stream:
            # no "%s": with the old code it would read a missing argument
            stream.write(f'{RESULT} = "%d%% of %i" % (50, 8) + "%%"\n')
        areas = FreeCADGui.getMainWindow().findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]
        import __main__

        self.main = __main__
        if hasattr(self.main, RESULT):
            delattr(self.main, RESULT)
        self.addCleanup(self._remove_result)

    def _remove_result(self):
        if hasattr(self.main, RESULT):
            delattr(self.main, RESULT)

    def _editor_windows(self):
        return [
            window
            for window in self.area.subWindowList()
            if window.widget() is not None and window.widget().inherits("Gui::PythonEditorView")
        ]

    def test_execute_selection_keeps_percent_signs(self):
        before = self._editor_windows()
        FreeCADGui.open(self.path)
        QtWidgets.QApplication.processEvents()
        created = [window for window in self._editor_windows() if window not in before]
        self.assertEqual(len(created), 1)
        window = created[0]
        try:
            editors = [
                editor
                for editor in window.widget().findChildren(QtWidgets.QPlainTextEdit)
                if editor.inherits("Gui::PythonEditor")
            ]
            self.assertEqual(len(editors), 1)
            editor = editors[0]
            editor.selectAll()
            self.assertTrue(QtCore.QMetaObject.invokeMethod(editor, "onExecuteInConsole"))
            QtWidgets.QApplication.processEvents()
            self.assertEqual(getattr(self.main, RESULT, None), "50% of 8%%")
        finally:
            window.close()
            QtWidgets.QApplication.processEvents()
        self.assertEqual(self._editor_windows(), before)
