# SPDX-License-Identifier: LGPL-2.1-or-later
"""A cosmetic edge's Qt style must select its rendered line number.

The line drawn on the page comes from LineFormat's line number, not from its
Qt style. The cosmetic edge creation methods and CosmeticEdge.Format accept an
optional line number; when it was omitted, the line number was reset to 1
(continuous) and a requested dashed style was silently drawn as a solid line.
See https://github.com/FreeCAD/FreeCAD/issues/33075 and #24092.
"""

import unittest

import FreeCAD
import Part  # noqa: F401
import TechDraw  # noqa: F401

from .TechDrawTestUtilities import createPageWithSVGTemplate

QT_SOLID_LINE = 1
QT_DASH_LINE = 2
# Qt::DashLine maps to line number 2 in the ISO, ANSI and ASME line standards.
DASHED_LINE_NUMBER = 2
EXPLICIT_LINE_NUMBER = 8
COLOR = (1.0, 0.0, 0.0, 1.0)


class DrawCosmeticEdgeLineNumberTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TDCosmeticEdgeLineNumber")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = FreeCAD.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertEqual(len(self.view.getVisibleEdges()), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _makers(self):
        vector = FreeCAD.Vector
        return {
            "makeCosmeticLine": (vector(-5, 10, 0), vector(5, 10, 0)),
            "makeCosmeticLine3D": (vector(-5, 0, 0), vector(5, 0, 0)),
            "makeCosmeticCircle": (vector(0, 15, 0), 2.0),
            "makeCosmeticCircleArc": (vector(0, 20, 0), 2.0, 0.0, 180.0),
            "makeCosmeticCircle3d": (vector(5, 10, 5), 2.0),
            "makeCosmeticCircleArc3d": (vector(10, 10, 5), 2.0, 0.0, 180.0),
        }

    def _lineNumber(self, tag):
        return self.view.getCosmeticEdge(tag).Format["lineNumber"]

    def testCreationStyleSelectsLineNumber(self):
        for name, arguments in self._makers().items():
            with self.subTest(method=name):
                maker = getattr(self.view, name)
                tag = maker(*arguments, QT_DASH_LINE, 0.5, COLOR)
                self.assertEqual(self._lineNumber(tag), DASHED_LINE_NUMBER)
                tag = maker(*arguments, QT_SOLID_LINE, 0.5, COLOR)
                self.assertEqual(self._lineNumber(tag), 1)

    def testCreationExplicitLineNumberWins(self):
        for name, arguments in self._makers().items():
            with self.subTest(method=name):
                maker = getattr(self.view, name)
                tag = maker(*arguments, QT_DASH_LINE, 0.5, COLOR, EXPLICIT_LINE_NUMBER)
                self.assertEqual(self._lineNumber(tag), EXPLICIT_LINE_NUMBER)
                tag = maker(*arguments, QT_SOLID_LINE, 0.5, COLOR, EXPLICIT_LINE_NUMBER)
                self.assertEqual(self._lineNumber(tag), EXPLICIT_LINE_NUMBER)

    def testFormatStyleSelectsLineNumber(self):
        vector = FreeCAD.Vector
        tag = self.view.makeCosmeticLine(vector(-5, 10, 0), vector(5, 10, 0))
        edge = self.view.getCosmeticEdge(tag)
        for style, expected in (
            (QT_DASH_LINE, DASHED_LINE_NUMBER),
            (QT_SOLID_LINE, 1),
            (QT_DASH_LINE, DASHED_LINE_NUMBER),
        ):
            with self.subTest(style=style):
                edge.Format = {"style": style, "weight": 0.5, "color": COLOR, "visible": True}
                self.assertEqual(edge.Format["style"], style)
                self.assertEqual(edge.Format["lineNumber"], expected)

    def testFormatExplicitLineNumberWins(self):
        vector = FreeCAD.Vector
        tag = self.view.makeCosmeticLine(vector(-5, 10, 0), vector(5, 10, 0))
        edge = self.view.getCosmeticEdge(tag)
        edge.Format = {"style": QT_SOLID_LINE, "lineNumber": EXPLICIT_LINE_NUMBER}
        self.assertEqual(edge.Format["lineNumber"], EXPLICIT_LINE_NUMBER)
        edge.Format = {"style": QT_DASH_LINE, "lineNumber": 1}
        self.assertEqual(edge.Format["lineNumber"], 1)


if __name__ == "__main__":
    unittest.main()
