# SPDX-License-Identifier: LGPL-2.1-or-later
"""Scrolling over preference fields must not change them unless they have focus.

https://github.com/FreeCAD/FreeCAD/issues/17684
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide6 import QtCore, QtGui, QtWidgets


def _wheel(widget):
    pos = QtCore.QPointF(5, 5)
    event = QtGui.QWheelEvent(
        pos,
        widget.mapToGlobal(pos),
        QtCore.QPoint(0, 0),
        QtCore.QPoint(0, -120),
        QtCore.Qt.MouseButton.NoButton,
        QtCore.Qt.KeyboardModifier.NoModifier,
        QtCore.Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QtWidgets.QApplication.sendEvent(widget, event)


@unittest.skipUnless(App.GuiUp, "Requires FreeCAD GUI mode")
class TestPrefWidgetsWheelGui(unittest.TestCase):
    def _check(self, class_name, plain_class):
        # a plain Qt widget of the same kind reacts to the wheel on this platform
        plain = plain_class()
        self.addCleanup(plain.deleteLater)
        if plain.count() < 2:
            self.skipTest("not enough items")
        plain.setCurrentIndex(0)
        _wheel(plain)
        if plain.currentIndex() == 0:
            self.skipTest("the style ignores wheel events on combo boxes")

        widget = Gui.UiLoader().createWidget(class_name)
        self.addCleanup(widget.deleteLater)
        self.assertIsNotNone(widget)
        if isinstance(widget, QtWidgets.QComboBox) and widget.count() < 2:
            widget.addItems(["first", "second", "third"])
        widget.setCurrentIndex(0)
        self.assertFalse(widget.hasFocus())
        _wheel(widget)
        self.assertEqual(widget.currentIndex(), 0)

    def testFontBoxIgnoresWheelWithoutFocus(self):
        self._check("Gui::PrefFontBox", QtWidgets.QFontComboBox)

    def testComboBoxIgnoresWheelWithoutFocus(self):
        def plain():
            box = QtWidgets.QComboBox()
            box.addItems(["first", "second", "third"])
            return box

        self._check("Gui::PrefComboBox", plain)
