# SPDX-License-Identifier: LGPL-2.1-or-later
"""A spin box without buttons keeps its edit field under the Dark and Light stylesheets.

The Sketcher on-view parameters are quantity spin boxes without up/down buttons. With
Qt 6.11.3 their edit field collapsed to one pixel when the stylesheet positioned the
buttons that are not shown, so the typed value could not be seen.

https://github.com/AstoCAD/FreeCAD/issues/169
"""

import os
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide6 import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "requires GUI")
class TestSpinBoxNoButtonsStyleGui(unittest.TestCase):
    STYLESHEETS = ("FreeCAD Dark.qss", "FreeCAD Light.qss")
    WIDTH = 160
    HEIGHT = 30

    def _stylesheet(self, name):
        path = os.path.join(App.getResourceDir(), "Gui", "Stylesheets", name)
        with open(path, encoding="utf-8") as stream:
            return stream.read()

    def _edit_width(self, spin, symbols, stylesheet):
        self.addCleanup(spin.deleteLater)
        self.addCleanup(spin.close)
        spin.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen)
        spin.setButtonSymbols(symbols)
        spin.setStyleSheet(stylesheet)
        spin.resize(self.WIDTH, self.HEIGHT)
        spin.show()
        Gui.updateGui()
        edit = spin.findChild(QtWidgets.QLineEdit)
        self.assertIsNotNone(edit)
        return edit.width()

    def _makers(self):
        return (
            ("QDoubleSpinBox", QtWidgets.QDoubleSpinBox),
            ("Gui::QuantitySpinBox", lambda: Gui.UiLoader().createWidget("Gui::QuantitySpinBox")),
        )

    def test_edit_field_without_buttons_is_not_collapsed(self):
        symbols = QtWidgets.QAbstractSpinBox.ButtonSymbols
        for name in self.STYLESHEETS:
            stylesheet = self._stylesheet(name)
            for kind, make in self._makers():
                with self.subTest(stylesheet=name, widget=kind):
                    with_buttons = self._edit_width(make(), symbols.UpDownArrows, stylesheet)
                    without = self._edit_width(make(), symbols.NoButtons, stylesheet)
                    # without buttons the field takes the room of the button column too
                    self.assertGreater(with_buttons, self.WIDTH // 2)
                    self.assertGreaterEqual(without, with_buttons)
