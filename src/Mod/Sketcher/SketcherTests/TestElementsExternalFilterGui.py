# SPDX-License-Identifier: LGPL-2.1-or-later
"""The "External" filter of the Elements panel covers all external geometry."""

import FreeCAD
import Part
from PySide import QtCore, QtGui

from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

GENERAL_PATH = "User parameter:BaseApp/Preferences/Mod/Sketcher/General"


class TestElementsExternalFilterGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.general = FreeCAD.ParamGet(GENERAL_PATH)
        self.hadState = "ElementFilterState" in self.general.GetInts()
        self.oldState = self.general.GetInt("ElementFilterState", 0)
        self.hadEnabled = "ElementFilterEnabled" in self.general.GetBools()
        self.oldEnabled = self.general.GetBool("ElementFilterEnabled", True)
        # Filtering enabled, every filter entry checked.
        self.general.RemInt("ElementFilterState")
        self.general.SetBool("ElementFilterEnabled", True)

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("ElementsExternalFilter")
        V = FreeCAD.Vector
        source = self.doc.addObject("Part::Feature", "Source")
        source.Shape = Part.Compound(
            [Part.makeLine(V(0, 20, 0), V(20, 20, 0)), Part.makeLine(V(0, 30, 0), V(20, 30, 0))]
        )
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(Part.LineSegment(V(0, 0, 0), V(20, 0, 0)))
        self.doc.recompute()
        self.sketch.addExternal(source.Name, "Edge1", True)  # defining, GeoId -3
        self.sketch.addExternal(source.Name, "Edge2")  # non-defining (construction), GeoId -4
        self.doc.recompute()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            if self.hadState:
                self.general.SetInt("ElementFilterState", self.oldState)
            else:
                self.general.RemInt("ElementFilterState")
            if self.hadEnabled:
                self.general.SetBool("ElementFilterEnabled", self.oldEnabled)
            else:
                self.general.RemBool("ElementFilterEnabled")

    def hiddenByGeoId(self, elements):
        result = {}
        for row in range(elements.count()):
            item = elements.item(row)
            result[int(item.data(QtCore.Qt.UserRole))] = item.isHidden()
        return result

    def testExternalFilterHidesDefiningAndConstructionExternals(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.flush_gui(100)
        mw = FreeCADGui.getMainWindow()
        elements = mw.findChild(QtGui.QListWidget, "listWidgetElements")
        self.assertIsNotNone(elements)
        # The filter list lives in the filter button's menu (a QWidgetAction), which has
        # no parent widget until the menu is shown for the first time.
        filters = [
            w
            for w in QtGui.QApplication.allWidgets()
            if w.metaObject().className().endswith("ElementFilterList")
        ]
        self.assertEqual(len(filters), 1)
        external = next(
            filters[0].item(row)
            for row in range(filters[0].count())
            if filters[0].item(row).text() == "External"
        )

        self.assertEqual(self.hiddenByGeoId(elements), {0: False, -3: False, -4: False})

        external.setCheckState(QtCore.Qt.Unchecked)
        self.flush_gui()
        self.assertEqual(self.hiddenByGeoId(elements), {0: False, -3: True, -4: True})

        external.setCheckState(QtCore.Qt.Checked)
        self.flush_gui()
        self.assertEqual(self.hiddenByGeoId(elements), {0: False, -3: False, -4: False})
