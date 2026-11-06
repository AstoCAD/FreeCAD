# SPDX-License-Identifier: LGPL-2.1-or-later
"""Numeric tolerances of an area dimension use the unit of the nominal area.

An adaptive unit schema picks the unit of each value on its own: a 900 mm²
area with a 5 mm² tolerance was shown as "9 ± 5 mm²" (nominal in cm²,
tolerance and unit in mm²). Linear tolerances already share the nominal unit.
"""

import time
import unittest

import FreeCAD as App
import Part
import TechDraw  # noqa: F401
from PySide import QtCore

from .TechDrawTestUtilities import createPageWithSVGTemplate


class DrawDimensionAreaToleranceTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("DimensionAreaTolerance")
        self.addCleanup(lambda: App.closeDocument(self.doc.Name))
        self.source = self.doc.addObject("Part::Feature", "Source")
        self.source.Shape = Part.makeBox(30, 30, 5)
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.doc.recompute()
        deadline = time.monotonic() + 20
        while not self.view.getVisibleEdges() or "Up-to-date" not in self.view.State:
            self.assertLess(time.monotonic(), deadline, self.view.State)
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

    def _area_dimension(self, tolerance):
        dimension = self.doc.addObject("TechDraw::DrawViewDimension", "AreaTolerance")
        self.page.addView(dimension)
        dimension.Type = "Area"
        dimension.References2D = [(self.view, "Face0")]
        dimension.FormatSpec = "%.6w"
        dimension.FormatSpecOverTolerance = "%+.6w"
        dimension.OverTolerance = tolerance
        dimension.EqualTolerance = True
        self.doc.recompute()
        self.assertAlmostEqual(dimension.getRawValue(), 900.0)
        return dimension

    def _texts(self, dimension, schemas):
        previous_schema = App.Units.getSchema()
        previous_document_schema = self.doc.UnitSystem
        previous_locale = QtCore.QLocale()
        result = {}
        try:
            QtCore.QLocale.setDefault(QtCore.QLocale.c())
            for schema in schemas:
                self.doc.UnitSystem = schema
                App.Units.setSchema(schema)
                result[schema] = dimension.getText()
        finally:
            self.doc.UnitSystem = previous_document_schema
            App.Units.setSchema(previous_schema)
            QtCore.QLocale.setDefault(previous_locale)
        return result

    def testAdaptiveSchemaToleranceUsesNominalUnit(self):
        dimension = self._area_dimension(5)
        # Standard (adaptive) shows this area in cm²
        self.assertEqual(self._texts(dimension, [0])[0], "9 ± 0.05 cm²")

    def testFixedSchemaUnchanged(self):
        dimension = self._area_dimension(5)
        # Metric small parts (fixed mm²)
        self.assertEqual(self._texts(dimension, [6])[6], "900 ± 5 mm²")


if __name__ == "__main__":
    unittest.main()
