# SPDX-License-Identifier: LGPL-2.1-or-later
"""Exporting a page that was never opened in a window (#33798)."""

import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
import FreeCADGui as Gui
import TechDraw  # noqa: F401
import TechDrawGui

from .TechDrawTestUtilities import createPageWithSVGTemplate


_SYMBOL = """<svg xmlns="http://www.w3.org/2000/svg" width="10mm" height="10mm"
viewBox="0 0 10 10"><path d="M1 1 L9 1 L5 9 Z" fill="black"/></svg>"""


class DrawPageUnshownExportTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="FreeCADUnshownExport-")
        self.root = Path(self.directory.name)
        self.doc = App.newDocument("DrawPageUnshownExportTest")
        self.addCleanup(self._cleanup)
        self.page = createPageWithSVGTemplate(self.doc)
        self.symbol = self.doc.addObject("TechDraw::DrawViewSymbol", "Symbol")
        self.symbol.Symbol = _SYMBOL
        self.symbol.X = 50
        self.symbol.Y = 50
        self.page.addView(self.symbol)
        self.doc.recompute()
        Gui.updateGui()
        # the page is deliberately never shown in a window

    def _cleanup(self):
        try:
            if self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
            Gui.updateGui()
        finally:
            self.directory.cleanup()

    def testPdfOfUnshownPage(self):
        """Exporting an unshown page as PDF writes a file instead of crashing."""
        path = self.root / "unshown.pdf"
        TechDrawGui.exportPageAsPdf(self.page, path.as_posix())
        self.assertTrue(path.is_file())
        data = path.read_bytes()
        self.assertEqual(data[:5], b"%PDF-")
        self.assertIn(b"%%EOF", data[-1024:])

    def testSvgOfUnshownPageIncludesTemplate(self):
        """An unshown page exports the same drawing (with its template) as a shown one."""
        unshown = self.root / "unshown.svg"
        TechDrawGui.exportPageAsSvg(self.page, unshown.as_posix())
        Gui.getDocument(self.doc.Name).getObject(self.page.Name).show()
        Gui.updateGui()
        shown = self.root / "shown.svg"
        TechDrawGui.exportPageAsSvg(self.page, shown.as_posix())

        unshownSize = len(unshown.read_bytes())
        shownSize = len(shown.read_bytes())
        self.assertGreater(shownSize, 0)
        # without the template, the export is only a small fraction of the full drawing
        self.assertGreater(unshownSize, 0.8 * shownSize, (unshownSize, shownSize))
