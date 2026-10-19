# SPDX-License-Identifier: LGPL-2.1-or-later

import FreeCAD
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate
from PySide import QtCore

class DrawViewDimensionTest(unittest.TestCase):
    def setUp(self):
        """Creates a page and 2 views"""
        print("DVDTest.setUp()")
        FreeCAD.newDocument("TDDimTest")
        FreeCAD.setActiveDocument("TDDimTest")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDDimTest")
        self.document = FreeCAD.ActiveDocument

        # make source feature
        self.document.addObject("Part::Box", "Box")
        self.document.addObject("Part::Sphere", "Sphere")

        # make a page
        self.page = createPageWithSVGTemplate(self.document)
        self.page.Scale = 5.0

        # make Views
        self.view = self.document.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.document.Box]
        self.view.X = 30
        self.view.Y = 150

        self.view1 = self.document.addObject("TechDraw::DrawViewPart", "View001")
        self.page.addView(self.view1)
        self.view1.Source = [self.document.Sphere]
        self.view1.X = 220
        self.view1.Y = 150

        self.document.recompute()

        #wait for threads to complete before checking result
        loop = QtCore.QEventLoop()

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        timer.start(5000)   #5 second delay
        loop.exec_()

    def tearDown(self):
        print("DVDTest.tearDown()")
        FreeCAD.closeDocument("TDDimTest")

    def testLengthDimension(self):
        """Tests if a length dimension can be added to view"""
        # make length dimension
        print("making length dimension")

        dimension = self.document.addObject("TechDraw::DrawViewDimension", "Dimension")
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.References2D = [(self.view, "Edge1")]
        print("finished length dimension")
        self.document.recompute()
        self.assertTrue("Up-to-date" in dimension.State)

    def testRadiusDimension(self):
        """Tests if a radius dimension can be added to view1"""
        print("making radius dimension")
        dimension = self.document.addObject("TechDraw::DrawViewDimension", "Dimension001")
        self.page.addView(dimension)
        dimension.Type = "Radius"
        dimension.MeasureType = "Projected"
        dimension.References2D = [(self.view1, "Edge0")]
        self.document.recompute()
        self.assertTrue("Up-to-date" in dimension.State)

    def testToleranceUsesNominalUnit(self):
        """Adaptive schemas must not change the unit of a numeric tolerance."""
        dimension = self.document.addObject("TechDraw::DrawViewDimension", "Tolerance")
        self.page.addView(dimension)
        dimension.Type = "Distance"
        dimension.MeasureType = "Projected"
        dimension.References2D = [(self.view, "Edge0")]
        dimension.FormatSpec = "%.6w"
        dimension.FormatSpecOverTolerance = "%+.6w"
        dimension.OverTolerance = 0.05
        dimension.EqualTolerance = True
        self.document.recompute()
        self.assertAlmostEqual(dimension.getRawValue(), 10.0)

        previous_schema = FreeCAD.Units.getSchema()
        previous_document_schema = self.document.UnitSystem
        previous_locale = QtCore.QLocale()
        try:
            QtCore.QLocale.setDefault(QtCore.QLocale.c())
            for schema, expected, unit in (
                (0, "10 ± 0.05", "mm"),  # Standard (adaptive)
                (1, "10 ± 0.05", "mm"),  # MKS (adaptive)
                (6, "10 ± 0.05", "mm"),  # Metric small parts (fixed)
                (3, "0.393701 ± 0.001969", "in"),  # Imperial decimal (fixed)
            ):
                with self.subTest(schema=schema):
                    self.document.UnitSystem = schema
                    FreeCAD.Units.setSchema(schema)
                    dimension.ShowUnits = False
                    self.assertEqual(dimension.getText(), expected)
                    dimension.ShowUnits = True
                    self.assertEqual(dimension.getText(), expected + " " + unit)
        finally:
            self.document.UnitSystem = previous_document_schema
            FreeCAD.Units.setSchema(previous_schema)
            QtCore.QLocale.setDefault(previous_locale)


if __name__ == "__main__":
    unittest.main()
