# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawViewAnnotationTest(unittest.TestCase):
    def setUp(self):
        """Creates a page"""
        FreeCAD.newDocument("TDAnno")
        FreeCAD.setActiveDocument("TDAnno")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDAnno")
        self.page = createPageWithSVGTemplate()

    def tearDown(self):
        FreeCAD.closeDocument("TDAnno")

    def testMakeAnnotation(self):
        """Tests if an annotation can be added to page"""
        anno = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewAnnotation", "TestAnno"
        )
        s = "Different Text"
        sl = list()
        sl.append(s)
        anno.Text = sl
        anno.TextStyle = "Bold"
        self.page.addView(anno)
        anno.X = 30.0
        anno.Y = 150.0
        FreeCAD.ActiveDocument.recompute()

        self.assertTrue("Up-to-date" in anno.State)

    def testFindParentPage(self):
        """Parent-page lookup safely represents a new or detached view."""
        annotation = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewAnnotation", "ParentPageAnnotation"
        )
        self.assertIsNone(annotation.findParentPage())
        self.page.addView(annotation)
        self.assertEqual(annotation.findParentPage(), self.page)
        self.page.removeView(annotation)
        self.assertIsNone(annotation.findParentPage())

    def testDxfExportWithEmptyAnnotation(self):
        """An empty annotation must not prevent other page text from exporting."""
        from pathlib import Path
        import tempfile
        import TechDraw

        document = FreeCAD.ActiveDocument
        annotation = document.addObject("TechDraw::DrawViewAnnotation", "DxfControl")
        annotation.Text = ["DXF annotation control"]
        self.page.addView(annotation)
        document.recompute()

        def exported_texts(path):
            TechDraw.writeDXFPage(self.page, str(path))
            lines = path.read_text(encoding="utf-8").splitlines()
            texts = []
            in_text = False
            for code, value in zip(lines[::2], lines[1::2]):
                if int(code.strip()) == 0:
                    in_text = value.strip() == "TEXT"
                elif in_text and int(code.strip()) == 1:
                    texts.append(value.strip())
            return texts

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "annotations.dxf"
            control = exported_texts(path)
            self.assertEqual(control, ["DXF annotation control"])
            empty = document.addObject("TechDraw::DrawViewAnnotation", "EmptyAnnotation")
            empty.Text = []
            self.page.addView(empty)
            document.recompute()
            self.assertEqual(empty.Text, [])
            self.assertNotIn("Invalid", empty.State)
            self.assertEqual(exported_texts(path), control)
            empty.Text = ["Recovered annotation"]
            document.recompute()
            self.assertCountEqual(exported_texts(path), control + ["Recovered annotation"])

    def testDxfExportNonAsciiText(self):
        """DXF text is written in the code page the file declares and reads back unchanged"""
        from pathlib import Path
        import tempfile
        import Import
        import TechDraw

        text = "Wände Ωμέγα 日本 ±45° ⌀ \U0001f600"
        document = FreeCAD.ActiveDocument
        annotation = document.addObject("TechDraw::DrawViewAnnotation", "NonAsciiText")
        annotation.Text = [text]
        self.page.addView(annotation)
        document.recompute()

        parent = "User parameter:BaseApp/Preferences/Mod/Import"
        options = FreeCAD.ParamGet(parent).GetGroup("TestTechDrawDxfText")
        self.addCleanup(FreeCAD.ParamGet(parent).RemGroup, "TestTechDrawDxfText")
        options.SetBool("dxftext", True)
        options.SetBool("dxfUseDraftVisGroups", False)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.dxf"
            TechDraw.writeDXFPage(self.page, str(path))
            data = path.read_bytes()
            # R12/R14 files have no UTF-8: Windows-1252, the others as \U+XXXX (UTF-16 units)
            self.assertIn(b"ANSI_1252", data)
            expected = (
                "Wände \\U+03A9\\U+03BC\\U+03AD\\U+03B3\\U+03B1 \\U+65E5\\U+672C"
                " ±45° \\U+2300 \\U+D83D\\U+DE00"
            )
            self.assertIn(expected.encode("cp1252"), data)

            imported = FreeCAD.newDocument("TDAnnoDxfImport")
            try:
                Import.readDXF(str(path), imported.Name, True, f"{parent}/TestTechDrawDxfText")
                texts = [list(o.Text) for o in imported.Objects if hasattr(o, "Text")]
            finally:
                FreeCAD.closeDocument(imported.Name)
                FreeCAD.setActiveDocument("TDAnno")
        self.assertIn([text], texts)


if __name__ == "__main__":
    unittest.main()
