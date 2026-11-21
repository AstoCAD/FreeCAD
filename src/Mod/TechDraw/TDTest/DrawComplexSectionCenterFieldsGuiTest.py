# SPDX-License-Identifier: LGPL-2.1-or-later

"""The Section View task shows the path center of a generated complex section.

The task writes the model origin to SectionOrigin of a section whose cutting
profile it generated, and keeps the path center in the profile state. When such
a section is edited, the center fields must show that path center.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")

# Version 5 state: center (50, 50, 5), on-page direction (0, 1, 0), path from
# -300 to 300 scene units along the line with one sharp 100 unit offset at its
# middle, no arcs.
INITIAL_STATE = (
    "5 50 50 5 0 1 0 -300 300 0 0 0 0 0 "
    "0 0 0 2 1 0 100 0 0 0 1 0 "
    "0"
)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawComplexSectionCenterFieldsGuiTest(unittest.TestCase):
    def setUp(self):
        import Part
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDComplexSectionCenterFields")
        box = self.doc.addObject("Part::Box", "Box")
        box.Length, box.Width, box.Height = 100, 100, 10
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.base = self.doc.addObject("TechDraw::DrawViewPart", "BaseView")
        self.page.addView(self.base)
        self.base.Source = [box]
        self.base.Direction = App.Vector(0, 0, 1)
        self.base.XDirection = App.Vector(1, 0, 0)
        self.base.ScaleType = "Custom"
        self.base.Scale = 1.0
        self.base.X, self.base.Y = 100, 150

        self.profile = self.doc.addObject("Part::Feature", "SectionProfile")
        self.profile.Shape = Part.makePolygon([App.Vector(-20, 50, 5), App.Vector(120, 50, 5)])
        self.profile.addProperty("App::PropertyString", "ModernSectionData", "Section")
        self.profile.ModernSectionData = INITIAL_STATE

        self.section = self.doc.addObject("TechDraw::DrawComplexSection", "ComplexSection")
        self.page.addView(self.section)
        self.section.SectionSymbol = "A"
        self.section.Source = [box]
        self.section.BaseView = self.base
        self.section.CuttingToolWireObject = self.profile
        self.section.SectionDirection = "Aligned"
        self.section.Direction = App.Vector(0, -1, 0)
        self.section.SectionNormal = App.Vector(0, -1, 0)
        self.section.XDirection = App.Vector(1, 0, 0)
        self.section.SectionOrigin = App.Vector(50, 50, 5)
        self.section.ScaleType = "Custom"
        self.section.Scale = 1.0
        self.section.X, self.section.Y = 250, 150
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self._wait_base()

    def tearDown(self):
        Gui.Selection.clearSelection()
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
            self._pump(100)
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        self._pump(100)
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    @staticmethod
    def _pump(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=20):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() > deadline:
                return False
            self._pump()
        return True

    def _wait_base(self):
        self.assertTrue(
            self._wait(lambda: len(self.base.getVisibleEdges()) >= 4),
            "The base view was not projected",
        )
        self._pump(300)

    def test_center_fields_show_the_profile_center(self):
        # The task writes the model origin to SectionOrigin of a generated
        # profile section; the path center is in the profile state.
        self.section.SectionOrigin = App.Vector(0, 0, 0)
        self.doc.recompute()
        self._wait_base()
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self._pump(300)
        marker = Gui.getMainWindow().findChild(QtWidgets.QCheckBox, "cbShowOutsidePartialBoundaries")
        self.assertIsNotNone(marker, "No section task panel")
        panel = marker.parentWidget()
        center_x = panel.findChild(QtWidgets.QAbstractSpinBox, "sbCenterX")
        center_y = panel.findChild(QtWidgets.QAbstractSpinBox, "sbCenterY")
        self.assertIsNotNone(center_x)
        self.assertIsNotNone(center_y)
        # The stored center (50, 50, 5) is the base view centroid: the view center.
        self.assertAlmostEqual(float(center_x.property("rawValue")), 0.0, places=4)
        self.assertAlmostEqual(float(center_y.property("rawValue")), 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
