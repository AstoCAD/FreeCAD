# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI tests: BIM preference pages show the value the code uses for an unset parameter.

A preference widget shows its .ui state while its parameter is not set, and
OK/Apply stores what it shows, so the .ui state must match the code default.
"""

import unittest

import FreeCAD

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtWidgets


@unittest.skipUnless(FreeCAD.GuiUp, "Requires the FreeCAD GUI")
class TestBimPreferencesGui(unittest.TestCase):

    def _page(self, path):
        import Arch_rc  # noqa: F401  (registers the :/ui resources)

        page = FreeCADGui.PySideUic.loadUi(path)
        self.addCleanup(page.deleteLater)
        return page

    @staticmethod
    def _entry(widget):
        value = widget.property("prefEntry")
        if hasattr(value, "data"):  # QByteArray
            value = value.data()
        if isinstance(value, str):
            value = value.encode()
        return value or b""

    def _check_box(self, page, entry):
        boxes = [
            box for box in page.findChildren(QtWidgets.QCheckBox) if self._entry(box) == entry
        ]
        self.assertEqual(len(boxes), 1, entry)
        return boxes[0]

    def test_native_ifc_switch_wb_default(self):
        # nativeifc.ifc_import.get_options() reads SwitchWB with default True
        page = self._page(":/ui/preferencesNativeIFC.ui")
        self.assertTrue(self._check_box(page, b"SwitchWB").isChecked())
