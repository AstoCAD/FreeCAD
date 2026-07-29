import FreeCAD
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate
from PySide import QtCore

class DrawViewSectionTest(unittest.TestCase):
    def setUp(self):
        """Creates a page and a view"""
        FreeCAD.newDocument("TDSection")
        FreeCAD.setActiveDocument("TDSection")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDSection")

        self.box = FreeCAD.ActiveDocument.addObject("Part::Box", "Box")

        self.page = createPageWithSVGTemplate()
        self.page.Scale = 5.0
        # page.ViewObject.show()    # unit tests run in console mode
        print("DrawViewSection test: page created")

        self.view = FreeCAD.ActiveDocument.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.box]
        self.view.Direction = (0.0, 0.0, 1.0)
        self.view.Rotation = 0.0
        self.view.X = 30.0
        self.view.Y = 150.0
        FreeCAD.ActiveDocument.recompute()

        #wait for threads to complete before checking result
        loop = QtCore.QEventLoop()

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        timer.start(2000)   #2 second delay
        loop.exec_()

        print("DrawViewSection test: view created")

    def tearDown(self):
        print("DrawViewSection test: finished")
        FreeCAD.closeDocument("TDSection")

    def testMakeDrawViewSection(self):
        """Tests if a DrawViewSection can be added to page"""
        section = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewSection", "Section"
        )
        self.page.addView(section)
        section.Source = [self.box]
        section.BaseView = self.view
        section.Direction = (0.0, 1.0, 0.0)
        section.SectionNormal = (0.0, 1.0, 0.0)
        section.SectionOrigin = (5.0, 5.0, 5.0)
        print("DrawViewSection test: section created")
        FreeCAD.ActiveDocument.recompute()

        #wait for threads to complete before checking result
        loop = QtCore.QEventLoop()

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        timer.start(2000)   #2 second delay
        loop.exec_()

        edges = section.getVisibleEdges()
        self.assertEqual(len(edges), 4, "DrawViewSection has wrong number of edges")
        self.assertTrue("Up-to-date" in section.State)

    def testGeneratedProfileOwnership(self):
        """Generated section profiles are owned by their complex section."""
        section = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawComplexSection", "ComplexSection"
        )
        generated_profile = FreeCAD.ActiveDocument.addObject(
            "Part::Feature", "SectionProfile"
        )
        section.CuttingToolWireObject = generated_profile
        generated_profile_name = generated_profile.Name

        FreeCAD.ActiveDocument.removeObject(section.Name)
        self.assertIsNone(FreeCAD.ActiveDocument.getObject(generated_profile_name))

        custom_section = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawComplexSection", "CustomComplexSection"
        )
        custom_profile = FreeCAD.ActiveDocument.addObject(
            "Part::Feature", "CustomProfile"
        )
        custom_section.CuttingToolWireObject = custom_profile
        custom_profile_name = custom_profile.Name

        FreeCAD.ActiveDocument.removeObject(custom_section.Name)
        self.assertIsNotNone(FreeCAD.ActiveDocument.getObject(custom_profile_name))


if __name__ == "__main__":
    unittest.main()
