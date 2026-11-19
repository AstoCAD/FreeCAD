# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exporting several pages to one PDF file from a script."""

import re
import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import TechDraw  # noqa: F401
import TechDrawGui

_TEMPLATE = Path(__file__).with_name("TestTemplate.svg")

_SYMBOL ="""<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"
viewBox="0 0 10 10"><path d="M1 1 L9 1 L5 9 Z" fill="black"/></svg>"""


def _sheets(path):
    """Return the sizes of the sheets of a PDF file, in points."""

    return [
        tuple(round(float(value)) for value in box.split()[2:])
        for box in re.findall(rb"/MediaBox\s*\[([^\]]*)\]", path.read_bytes())
    ]


class DrawPagesPdfExportTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="FreeCADPagesExport-")
        self.root = Path(self.directory.name)
        self.doc = App.newDocument("DrawPagesPdfExportTest")
        self.addCleanup(self._cleanup)
        self.pages = []
        for index in range(3):
            page = self.doc.addObject("TechDraw::DrawPage", "Page")
            template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
            template.Template = _TEMPLATE.as_posix()
            page.Template = template
            symbol = self.doc.addObject("TechDraw::DrawViewSymbol", "Symbol")
            symbol.Symbol = _SYMBOL
            symbol.X = 50 + 20 * index
            symbol.Y = 50
            page.addView(symbol)
            self.pages.append(page)
        self.doc.recompute()
        Gui.updateGui()
        # the pages are deliberately never shown in a window

    def _cleanup(self):
        try:
            if self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
            Gui.updateGui()
        finally:
            self.directory.cleanup()

    def testPagesGoToOneFileASheetEach(self):
        """Several pages are written to one PDF, a sheet each."""
        path = self.root / "pages.pdf"
        modified = Gui.getDocument(self.doc.Name).Modified
        TechDrawGui.exportPagesAsPdf(self.pages, path.as_posix())
        data = path.read_bytes()
        self.assertEqual(data[:5], b"%PDF-")
        self.assertIn(b"%%EOF", data[-1024:])
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", data)), len(self.pages))
        # exporting is not a change to the document
        self.assertEqual(Gui.getDocument(self.doc.Name).Modified, modified)

    def testSheetsTakeTheirPageSize(self):
        """Each sheet has the size of its own page, and one page gives the single-page file."""
        single = self.root / "single.pdf"
        TechDrawGui.exportPageAsPdf(self.pages[0], single.as_posix())
        size = _sheets(single)
        self.assertEqual(len(size), 1)

        one = self.root / "one.pdf"
        TechDrawGui.exportPagesAsPdf(self.pages[:1], one.as_posix())
        self.assertEqual(_sheets(one), size)

        several = self.root / "several.pdf"
        TechDrawGui.exportPagesAsPdf(tuple(self.pages), several.as_posix())
        self.assertEqual(_sheets(several), size * len(self.pages))

    def testOnlyPagesAreAccepted(self):
        """Nothing is written for a list that is empty or holds something else than pages."""
        path = self.root / "none.pdf"
        with self.assertRaises(ValueError):
            TechDrawGui.exportPagesAsPdf([], path.as_posix())
        with self.assertRaises(TypeError):
            TechDrawGui.exportPagesAsPdf([self.pages[0], self.pages[0].Views[0]], path.as_posix())
        with self.assertRaises(TypeError):
            TechDrawGui.exportPagesAsPdf([self.pages[0], "Page"], path.as_posix())
        with self.assertRaises(TypeError):
            TechDrawGui.exportPagesAsPdf(self.pages[0], path.as_posix())
        self.assertFalse(path.exists())
