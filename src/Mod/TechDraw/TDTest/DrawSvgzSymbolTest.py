# SPDX-License-Identifier: LGPL-2.1-or-later
"""SVG insertion accepts gzip SVGZ while retaining plain-text compatibility."""

import gzip
from pathlib import Path
import unittest

from PySide import QtCore, QtSvg

from . import DrawImportFilenameTest as import_fixture


class DrawSvgzSymbolTest(unittest.TestCase):
    def setUp(self):
        # Reuse the real-page, preference-restoring fixture without inheriting its tests.
        import_fixture.DrawImportFilenameTest.setUp(self)

    def closeConsoleReader(self, path):
        import __main__

        # A failed native command can stop before its recorded f.close(). Close
        # only that command's exact fixture file before Windows temp cleanup.
        reader = vars(__main__).get("f")
        name = getattr(reader, "name", None)
        if isinstance(name, str) and Path(name).resolve() == path.resolve():
            reader.close()

    def checkSymbol(self, kind, command):
        suffix = ".svg" if kind == "plain_svg" else ".svgz"
        path = Path(self.directory.name) / (kind + suffix)
        source = ('<svg xmlns="http://www.w3.org/2000/svg" width="20mm" height="10mm" '
                  'viewBox="0 0 20 10">\r\n<rect id="asset-' + kind
                  + '" width="20" height="10" fill="#0000ff"/>\r\n</svg>')
        content = source.encode("utf-8")
        if kind == "gzip_svgz":
            path.write_bytes(gzip.compress(content))
            self.assertTrue(path.read_bytes().startswith(b"\x1f\x8b"))
            self.assertEqual(gzip.decompress(path.read_bytes()), content)
        else:
            path.write_bytes(content)
        self.addCleanup(self.closeConsoleReader, path)
        before = tuple(obj.Name for obj in self.doc.Objects)
        import_fixture.DrawImportFilenameTest.runCommandWithFile(self, command, path)
        symbols = [obj for obj in self.doc.Objects if obj.TypeId == "TechDraw::DrawViewSymbol"]
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0].findParentPage(), self.page)
        # Existing text-mode imports normalize CRLF; compressed imports must do the same.
        self.assertEqual(symbols[0].Symbol, source.replace("\r\n", "\n"))
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(symbols[0].Symbol.encode("utf-8")))
        self.assertTrue(renderer.isValid())
        import_fixture.DrawImportFilenameTest.assertOnlyImportedObject(self, symbols[0], before)

    def testSymbolPlainSvg(self):
        self.checkSymbol("plain_svg", "TechDraw_Symbol")

    def testSymbolPlainXmlSvgz(self):
        self.checkSymbol("plain_svgz", "TechDraw_Symbol")

    def testSymbolGzipSvgz(self):
        self.checkSymbol("gzip_svgz", "TechDraw_Symbol")

    def testGenericSymbolPlainSvg(self):
        self.checkSymbol("plain_svg", "TechDraw_View")

    def testGenericSymbolPlainXmlSvgz(self):
        self.checkSymbol("plain_svgz", "TechDraw_View")

    def testGenericSymbolGzipSvgz(self):
        self.checkSymbol("gzip_svgz", "TechDraw_View")
