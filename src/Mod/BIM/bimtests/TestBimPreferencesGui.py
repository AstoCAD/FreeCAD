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

    def test_bim_text_uses_draft_text_height_default(self):
        # BIM_Text on a TechDraw page must use the Draft text height (3.5 mm by default)
        from draftutils import params

        if not hasattr(FreeCADGui, "draftToolBar"):
            import DraftGui  # noqa: F401  (creates the Draft tool bar used by finish())
        from bimcommands import BimText

        grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Draft")
        had = "textheight" in grp.GetFloats()
        old = grp.GetFloat("textheight") if had else None
        grp.RemFloat("textheight")
        self.addCleanup(
            lambda: grp.SetFloat("textheight", old) if had else grp.RemFloat("textheight")
        )
        doc = FreeCAD.newDocument("BimTextDefaults")
        self.addCleanup(FreeCAD.closeDocument, doc.Name)
        page = doc.addObject("TechDraw::DrawPage", "Page")

        class View:
            def getPage(self):
                return page

        cmd = BimText.BIM_Text()
        cmd.view = View()
        cmd.text = ["Text"]
        cmd.createObject()
        annos = [o for o in doc.Objects if o.isDerivedFrom("TechDraw::DrawViewAnnotation")]
        self.assertEqual(len(annos), 1)
        expected = params.get_param("textheight") * (page.Scale or 1)
        self.assertAlmostEqual(expected, 3.5 * (page.Scale or 1))
        self.assertAlmostEqual(annos[0].TextSize.Value, expected)
