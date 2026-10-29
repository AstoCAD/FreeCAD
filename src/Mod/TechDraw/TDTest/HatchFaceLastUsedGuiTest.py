# SPDX-License-Identifier: LGPL-2.1-or-later
"""The face hatch task reuses the last used settings (#21115)."""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtWidgets

from .TechDrawTestUtilities import createPageWithSVGTemplate

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/TechDraw"
# GetContents() kinds and the matching Get/Set/Rem method suffixes
_SUFFIX = {
    "Integer": "Int",
    "Float": "Float",
    "Unsigned": "Unsigned",
    "String": "String",
    "Boolean": "Bool",
}


@unittest.skipIf(not App.GuiUp, "GUI tests require FreeCAD GUI mode")
class HatchFaceLastUsedGuiTest(unittest.TestCase):
    def setUp(self):
        self.params = App.ParamGet(PARAM_PATH)
        self.saved = [
            entry for entry in (self.params.GetContents() or []) if entry[1].startswith("Hatch")
        ]
        for kind, name, _ in self.saved:
            getattr(self.params, "Rem" + _SUFFIX[kind])(name)
        self.addCleanup(self._restore_params)

        # A modal message would block the test, record and dismiss it instead
        self.messages = []
        self.dismiss_timer = QtCore.QTimer()
        self.dismiss_timer.timeout.connect(self._dismiss_messages)
        self.dismiss_timer.start(50)
        self.addCleanup(self.dismiss_timer.stop)

        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("HatchFaceLastUsed21115")
        self.addCleanup(self._close)
        box = self.doc.addObject("Part::Box", "Box")
        self.page = createPageWithSVGTemplate(self.doc)
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [box]
        self.view.Direction = App.Vector(0, 0, 1)
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: len(self.view.getVisibleEdges()) == 4))

    def _dismiss_messages(self):
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if isinstance(widget, QtWidgets.QMessageBox) and widget.isVisible():
                self.messages.append(widget.text())
                widget.reject()

    def _restore_params(self):
        for name in [entry[1] for entry in (self.params.GetContents() or [])]:
            if name.startswith("HatchLastUsed"):
                for suffix in _SUFFIX.values():
                    getattr(self.params, "Rem" + suffix)(name)
        for kind, name, value in self.saved:
            setter = "Set" + _SUFFIX[kind]
            getattr(self.params, setter)(name, value)

    def _close(self):
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def _wait(self, predicate, ms=5000):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while timer.elapsed() < ms:
            QtWidgets.QApplication.processEvents()
            if predicate():
                return True
        return predicate()

    def _widget(self, cls, name):
        widget = Gui.getMainWindow().findChild(cls, name)
        self.assertIsNotNone(widget, name)
        return widget

    def _open_task(self):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.view.Name, "Face0")
        Gui.runCommand("TechDraw_HatchFace")
        self.assertTrue(
            self._wait(lambda: Gui.Control.activeTaskDialog() is not None), self.messages
        )

    def testSettingsAreReused(self):
        self._open_task()
        patterns = self._widget(QtWidgets.QComboBox, "patternComboBox")
        self.assertGreater(patterns.count(), 1)
        patterns.setCurrentIndex(patterns.count() - 1)
        chosen = patterns.currentText()
        self._widget(QtWidgets.QAbstractSpinBox, "scaleSpinBox").setProperty("rawValue", 2.5)
        self._widget(QtWidgets.QDoubleSpinBox, "rotationSpinBox").setValue(30)
        self._widget(QtWidgets.QDoubleSpinBox, "offsetXSpinBox").setValue(1.5)
        Gui.Control.activeTaskDialog().accept()
        self.assertTrue(self._wait(lambda: Gui.Control.activeTaskDialog() is None))

        self._open_task()
        self.assertEqual(self._widget(QtWidgets.QComboBox, "patternComboBox").currentText(), chosen)
        self.assertAlmostEqual(
            self._widget(QtWidgets.QAbstractSpinBox, "scaleSpinBox").property("rawValue"), 2.5
        )
        self.assertAlmostEqual(self._widget(QtWidgets.QDoubleSpinBox, "rotationSpinBox").value(), 30)
        self.assertAlmostEqual(self._widget(QtWidgets.QDoubleSpinBox, "offsetXSpinBox").value(), 1.5)
        Gui.Control.activeTaskDialog().reject()
