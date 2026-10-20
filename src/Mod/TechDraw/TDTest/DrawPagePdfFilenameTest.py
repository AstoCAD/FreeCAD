# SPDX-License-Identifier: LGPL-2.1-or-later

import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import TechDraw
import TechDrawGui

from .TechDrawTestUtilities import createPageWithSVGTemplate


_SYMBOL = """<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"
viewBox="0 0 10 10"><path d="M1 1 L9 1 L5 9 Z" fill="black"/></svg>"""


class DrawPagePdfFilenameTest(unittest.TestCase):
    def setUp(self):
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.directory = tempfile.TemporaryDirectory(prefix="FreeCADPdfFilename-")
        self.root = Path(self.directory.name)
        self.doc = App.newDocument("DrawPagePdfFilenameTest")
        self.addCleanup(self._cleanup)
        self.page = createPageWithSVGTemplate(self.doc)
        self.page.Label = "PDF filename page"
        self.symbol = self.doc.addObject("TechDraw::DrawViewSymbol", "Symbol")
        self.symbol.Symbol = _SYMBOL
        self.symbol.Label = "PDF filename symbol"
        self.symbol.X = 50
        self.symbol.Y = 50
        self.page.addView(self.symbol)
        self.doc.recompute()
        Gui.getDocument(self.doc.Name).getObject(self.page.Name).show()
        Gui.updateGui()
        Gui.updateGui()
        self.assertEqual(self.page.Template.TypeId, "TechDraw::DrawSVGTemplate")
        self.assertIn(self.symbol, self.page.Views)
        self.assertIn("<svg", self.symbol.Symbol)

    def _cleanup(self):
        try:
            if self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
            if self.previous in App.listDocuments():
                App.setActiveDocument(self.previous)
            Gui.updateGui()
        finally:
            self.directory.cleanup()

    def assertPdf(self, path):
        data = path.read_bytes()
        self.assertGreater(len(data), 100)
        self.assertEqual(data[:5], b"%PDF-")
        self.assertRegex(data.splitlines()[0], rb"^%PDF-[12][.][0-9]$")
        self.assertIn(b"%%EOF", data[-1024:])

    def checkExport(self, path, stray=None):
        self.assertTrue(path.parent.is_dir())
        self.assertFalse(path.exists())
        if stray is not None:
            self.assertFalse(stray.exists())
        source_svg = self.symbol.Symbol
        page_label, symbol_label = self.page.Label, self.symbol.Label

        TechDrawGui.exportPageAsPdf(self.page, path.as_posix())

        self.assertEqual(self.symbol.Symbol, source_svg)
        self.assertEqual(self.page.Label, page_label)
        self.assertEqual(self.symbol.Label, symbol_label)
        if stray is not None and stray.is_file():
            self.assertPdf(stray)
        self.assertTrue(path.is_file(), f"Requested PDF path was not written: {path}")
        self.assertPdf(path)
        if stray is not None:
            self.assertFalse(stray.exists(), f"Export wrote an unintended path: {stray}")

    def testOrdinaryFilename(self):
        self.checkExport(self.root / "ordinary.pdf")

    def testUnicodeFilename(self):
        self.checkExport(self.root / "plan-é-測試.pdf")

    def testQuotedPageAndSymbolLabelsWithOrdinaryFilename(self):
        self.page.Label = 'Page: O\'Brien "quoted"'
        self.symbol.Label = 'Symbol: O\'Brien "quoted"'
        self.checkExport(self.root / "ordinary-with-quoted-labels.pdf")

    def testApostropheFilenameWithoutAccidentalDirectory(self):
        target = self.root / "O'Brien.pdf"
        stray = self.root / "O" / "'Brien.pdf"
        self.assertFalse(stray.parent.exists())
        self.checkExport(target, stray)

    def testApostropheFilenameWithAccidentalDirectory(self):
        target = self.root / "O'Brien.pdf"
        stray = self.root / "O" / "'Brien.pdf"
        stray.parent.mkdir()
        self.checkExport(target, stray)

    def testApostropheDirectoryWithAccidentalDirectory(self):
        target = self.root / "O'Brien" / "page.pdf"
        stray = self.root / "O" / "'Brien" / "page.pdf"
        target.parent.mkdir()
        stray.parent.mkdir(parents=True)
        self.checkExport(target, stray)
