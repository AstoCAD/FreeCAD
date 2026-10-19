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


if __name__ == "__main__":
    unittest.main()
