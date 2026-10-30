# SPDX-License-Identifier: LGPL-2.1-or-later

"""Keyboard Tab order of the Section View task panel.

The compass and the vector editor are created in code after the .ui widgets,
so they used to come last in the focus chain, after "Live update", and the
section-line center Y field came before X. Tab must follow the visual
top-to-bottom order (https://github.com/FreeCAD/FreeCAD/issues/30833).
"""

from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    try:
        import shiboken6 as shiboken
    except ImportError:
        import shiboken2 as shiboken


TEMPLATE = Path(__file__).with_name("TestTemplate.svg")

# Visual top-to-bottom order of the main controls of the task panel.
EXPECTED_ORDER = (
    "tbSectionHorizontal",
    "pbResetSectionLine",
    "leSymbol",
    "cmbScaleType",
    "sbScale",
    "cbConnectionLine",
    "cbSectionCutOnly",
    "cbShowManualControls",
    "sbCenterX",
    "sbCenterY",
    "Compass",
    "VectorEdit",
    "cbLiveUpdate",
)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class DrawSectionTabOrderGuiTest(unittest.TestCase):
    def setUp(self):
        import Part  # noqa: F401
        import TechDraw  # noqa: F401
        import TechDrawGui  # noqa: F401

        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("TDSectionTabOrder")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TEMPLATE)
        self.page.Template = template
        self.base = self.doc.addObject("TechDraw::DrawViewPart", "BaseView")
        self.page.addView(self.base)
        self.base.Source = [self.box]
        self.base.Direction = App.Vector(0, 0, 1)
        self.base.X, self.base.Y = 80, 100
        self.section = self.doc.addObject("TechDraw::DrawViewSection", "Section")
        self.page.addView(self.section)
        self.section.BaseView = self.base
        self.section.Source = [self.box]
        self.section.SectionNormal = App.Vector(0, -1, 0)
        self.section.SectionOrigin = App.Vector(5, 5, 5)
        self.section.Direction = App.Vector(0, -1, 0)
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
        # A check box only the section task has; the .ui widgets are direct
        # children of the task panel widget.
        marker = Gui.getMainWindow().findChild(
            QtWidgets.QCheckBox, "cbShowOutsidePartialBoundaries"
        )
        return marker.parentWidget() if marker is not None else None

    def test_tab_order_follows_visual_order(self):
        Gui.ActiveDocument.setEdit(self.section.Name, 0)
        self.assertTrue(self._wait(Gui.Control.activeDialog), "The edit task did not open")
        self.assertTrue(self._wait(lambda: self._panel() is not None), "No section task panel")
        self._pump(200)
        panel = self._panel()

        targets = {}
        for name in EXPECTED_ORDER:
            widget = panel.findChild(QtWidgets.QWidget, name)
            self.assertIsNotNone(widget, name)
            targets[name] = widget

        # Walk the whole focus chain once, starting at the panel.
        chain = []
        start = shiboken.getCppPointer(panel)[0]
        widget = panel.nextInFocusChain()
        while widget is not None and shiboken.getCppPointer(widget)[0] != start:
            chain.append(widget)
            self.assertLess(len(chain), 20000, "The focus chain does not loop")
            widget = widget.nextInFocusChain()

        def position(target):
            pointer = shiboken.getCppPointer(target)[0]
            for index, item in enumerate(chain):
                if shiboken.getCppPointer(item)[0] == pointer or target.isAncestorOf(item):
                    return index
            self.fail("{} is not in the focus chain".format(target.objectName()))

        positions = [(position(targets[name]), name) for name in EXPECTED_ORDER]
        self.assertEqual(
            [name for _, name in sorted(positions)],
            list(EXPECTED_ORDER),
            "Tab order of the Section View task panel must follow the visual order",
        )


if __name__ == "__main__":
    unittest.main()
