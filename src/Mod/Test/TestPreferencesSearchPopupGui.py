# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test for the preferences search results popup position."""

import time
import unittest

import FreeCADGui as Gui
from PySide import QtCore, QtWidgets


class TestPreferencesSearchPopupGui(unittest.TestCase):
    """Issue #22289: the search results popup must follow the preferences
    dialog when the dialog is moved."""

    def setUp(self):
        self.results = {}
        self.errors = []

    @staticmethod
    def processEvents(milliseconds=50):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def waitFor(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self.processEvents()
        return True

    @staticmethod
    def visiblePopup(dialog):
        for widget in dialog.findChildren(QtWidgets.QListWidget):
            if widget.isWindow() and widget.isVisible():
                return widget
        return None

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            search = dialog.findChild(QtWidgets.QLineEdit, "searchBox")
            if search is None:
                self.errors.append("search box not found")
                return
            search.setFocus()
            search.setText("color")
            if not self.waitFor(lambda: self.visiblePopup(dialog) is not None):
                self.errors.append("search results popup not shown")
                return
            popup = self.visiblePopup(dialog)
            before = popup.pos() - search.mapToGlobal(QtCore.QPoint(0, 0))
            dialog.move(dialog.pos() + QtCore.QPoint(40, 30))
            self.waitFor(lambda: dialog.pos() != QtCore.QPoint(0, 0))
            self.processEvents(300)
            after = popup.pos() - search.mapToGlobal(QtCore.QPoint(0, 0))
            self.results["offsets"] = ((before.x(), before.y()), (after.x(), after.y()))
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testPopupFollowsMovedDialog(self):
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.showPreferences()
        self.assertEqual(self.errors, [])
        before, after = self.results["offsets"]
        # allow for rounding of fractional display scaling
        self.assertLessEqual(abs(after[0] - before[0]), 2, (before, after))
        self.assertLessEqual(abs(after[1] - before[1]), 2, (before, after))
