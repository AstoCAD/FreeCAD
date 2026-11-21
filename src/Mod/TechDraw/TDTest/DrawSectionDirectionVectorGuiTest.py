# SPDX-License-Identifier: LGPL-2.1-or-later

"""View direction typed in the vector editor of the Section View task.

The vector editor holds the view direction in BaseView coordinates, like the
compass angle. Typing a vector must turn the compass to that vector's angle,
also when the base view does not look along the global Z axis, and the
section view rotation derived from the compass must follow.
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawSectionDirectionVectorGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDSectionDirectionVector")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        # A front view: its BaseView Y axis is the global Z axis, so a
        # BaseView vector projected as a global vector loses its Y part.
        self.base = self.doc.addObject("TechDraw::DrawViewPart", "BaseView")
        self.page.addView(self.base)
        self.base.Source = [self.box]
        self.base.Direction = App.Vector(0, -1, 0)
        self.base.XDirection = App.Vector(1, 0, 0)
        self.base.X, self.base.Y = 80, 100
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        self.page.addView(self.section)
        self.section.BaseView = self.base
        self.section.Source = [self.box]
        self.section.SectionNormal = App.Vector(1, 0, 0)
        self.section.SectionOrigin = App.Vector(5, 5, 5)
        self.section.Direction = App.Vector(1, 0, 0)
        self.section.X, self.section.Y = 200, 100
        self.doc.recompute()
        App.setActiveDocument(self.doc.Name)
        self.page.ViewObject.show()
        self.assertTrue(
            self._wait(lambda: len(self.base.getVisibleEdges()) >= 4),
            "The base view was not projected",
        )

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

    @staticmethod
    def _panel():
        marker = Gui.getMainWindow().findChild(
            QtWidgets.QCheckBox, "cbShowOutsidePartialBoundaries"
        )
        return marker.parentWidget() if marker is not None else None

    def test_typed_vector_sets_compass_in_base_view_coordinates(self):
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self.assertTrue(self._wait(lambda: self._panel() is not None), "No section task panel")
        self._pump(200)
        panel = self._panel()
        vector_edit = panel.findChild(QtWidgets.QWidget, "VectorEdit")
        self.assertIsNotNone(vector_edit)
        x_box = vector_edit.findChild(QtWidgets.QDoubleSpinBox, "dsbX")
        y_box = vector_edit.findChild(QtWidgets.QDoubleSpinBox, "dsbY")
        angle_box = panel.findChild(QtWidgets.QAbstractSpinBox, "dsbAngle")
        self.assertIsNotNone(x_box)
        self.assertIsNotNone(y_box)
        self.assertIsNotNone(angle_box)

        # The view direction (-1, 0) of the opened section points to 180 degrees.
        self.assertAlmostEqual(float(angle_box.property("rawValue")) % 360.0, 180.0, places=6)

        # Type the BaseView vector (0, 1, 0): the view looks up the base view.
        y_box.setValue(1.0)
        self._pump()
        self.assertAlmostEqual(float(angle_box.property("rawValue")), 135.0, places=6)
        x_box.setValue(0.0)
        self._pump()
        self.assertAlmostEqual(float(angle_box.property("rawValue")), 90.0, places=6)

        Gui.Control.activeTaskDialog().accept()
        self.assertTrue(self._wait(lambda: not Gui.Control.activeDialog()), "The task did not close")
        self.doc.recompute()
        # A view direction of 90 degrees needs no rotation of the section view.
        self.assertAlmostEqual(self.section.Rotation.Value, 0.0, places=6)
        # The view looks along global +Z; the section normal points against it.
        normal = self.section.SectionNormal
        self.assertAlmostEqual(normal.x, 0.0, places=6)
        self.assertAlmostEqual(normal.y, 0.0, places=6)
        self.assertAlmostEqual(normal.z, -1.0, places=6)


if __name__ == "__main__":
    unittest.main()
