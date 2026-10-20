# SPDX-License-Identifier: LGPL-2.1-or-later
"""Spreadsheet view labels must round-trip through their generated SVG."""

import unittest
import xml.etree.ElementTree as ET

import FreeCAD as App
import Spreadsheet
import TechDraw
from PySide import QtCore, QtSvg

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawSpreadsheetLabelXmlTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("SpreadsheetLabelXmlRegression")
        self.addCleanup(App.closeDocument, self.doc.Name)
        self.sheet = self.doc.addObject("Spreadsheet::Sheet", "Sheet")
        self.content = "Cell & <sample> \"quoted\" 'single' 測定"
        self.sheet.set("A1", self.content)
        page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewSpreadsheet", "SheetView")
        page.addView(self.view)
        self.view.Source = self.sheet
        self.view.CellStart = self.view.CellEnd = "A1"

    def _checkLabel(self, label):
        self.view.Label = label
        self.view.touch()
        self.doc.recompute()
        self.assertIn("Up-to-date", self.view.State)
        self.assertNotIn("Invalid", self.view.State)
        self.assertEqual(self.view.Label, label)
        self.assertEqual(self.sheet.get("A1"), self.content)
        symbol = self.view.Symbol
        try:
            root = ET.fromstring(symbol)
        except ET.ParseError as exc:
            self.fail(f"The spreadsheet view's label produced invalid SVG XML: {exc}")
        groups = [element.attrib.get("id") for element in root.iter()
                  if element.tag.split("}")[-1] == "g"]
        self.assertEqual(groups, [label, label + "_colA"])
        texts = ["".join(element.itertext()) for element in root.iter()
                 if element.tag.split("}")[-1] == "text"]
        self.assertEqual(texts, [self.content])
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(symbol.encode("utf-8")))
        self.assertTrue(renderer.isValid(), "Qt must render the generated spreadsheet SVG")

    def testOrdinaryLabel(self):
        self._checkLabel("DrawingTable")

    def testUnicodeLabel(self):
        self._checkLabel("Drawing_測定_é")

    def testApostropheLabel(self):
        self._checkLabel("Drawing'sTable")

    def testAmpersandLabel(self):
        self._checkLabel("R&D_Table")

    def testDoubleQuoteLabel(self):
        self._checkLabel('Drawing_"quoted"')

    def testAngleBracketLabel(self):
        self._checkLabel("Drawing_<section>")
