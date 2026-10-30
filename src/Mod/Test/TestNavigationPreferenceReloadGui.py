# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test for reloading the navigation preference page."""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets


class TestNavigationPreferenceReloadGui(unittest.TestCase):
    """Issue #23304: the preferences dialog reloads all pages after a theme
    change; the navigation page must not connect its signals or fill its
    lists once more on every reload."""

    def setUp(self):
        self.results = {}
        self.errors = []

    @staticmethod
    def findPage(dialog):
        for widget in dialog.findChildren(QtWidgets.QWidget):
            if widget.metaObject().className() == "Gui::Dialog::DlgSettingsNavigation":
                return widget
        return None

    def inspect(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            page = self.findPage(dialog)
            if page is None:
                self.errors.append("navigation preference page not found")
                return
            views = page.findChild(QtWidgets.QComboBox, "comboNewDocView")
            fonts = page.findChild(QtWidgets.QComboBox, "naviCubeFontName")
            self.results["before"] = (views.count(), fonts.count())

            # what DlgPreferencesImp::reload() does after a theme change
            for _ in range(2):
                QtCore.QMetaObject.invokeMethod(page, "loadSettings")
            self.results["after"] = (views.count(), fonts.count())

            # count how often the mouse buttons dialog is shown for one click
            shown = []

            def closeDialogs():
                for child in page.findChildren(QtWidgets.QDialog):
                    if child.isVisible():
                        shown.append(child)
                        child.reject()

            timer = QtCore.QTimer()
            timer.timeout.connect(closeDialogs)
            timer.start(50)
            page.findChild(QtWidgets.QPushButton, "mouseButton").click()
            timer.stop()
            self.results["dialogs"] = len(shown)
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testReloadDoesNotDuplicate(self):
        QtCore.QTimer.singleShot(500, self.inspect)
        Gui.showPreferences("Display")
        self.assertEqual(self.errors, [])
        self.assertEqual(self.results["after"], self.results["before"])
        self.assertEqual(self.results["dialogs"], 1)

    def inspectFont(self):
        dialog = QtWidgets.QApplication.activeModalWidget()
        try:
            page = self.findPage(dialog)
            if page is None:
                self.errors.append("navigation preference page not found")
                return
            fonts = page.findChild(QtWidgets.QComboBox, "naviCubeFontName")
            self.results["loaded"] = (fonts.currentIndex(), fonts.currentText())
            QtCore.QMetaObject.invokeMethod(page, "loadSettings")
            self.results["reloaded"] = (fonts.currentIndex(), fonts.currentText())
            # what OK/Apply does
            QtCore.QMetaObject.invokeMethod(page, "saveSettings")
        except Exception as e:
            self.errors.append(repr(e))
        finally:
            if dialog is not None:
                dialog.reject()

    def testFontNameKeepsDefaultEntry(self):
        """The navigation cube font list starts with a "Default" entry: loading
        the page must show the stored font, and saving it must not change it."""
        families = QtGui.QFontDatabase.families()
        self.assertGreater(len(families), 2)
        font = families[1]
        group = App.ParamGet("User parameter:BaseApp/Preferences/NaviCube")
        had = "FontString" in group.GetStrings()
        old = group.GetString("FontString")
        try:
            group.SetString("FontString", font)
            QtCore.QTimer.singleShot(500, self.inspectFont)
            Gui.showPreferences("Display")
            self.assertEqual(self.errors, [])
            self.assertEqual(self.results["loaded"][1], font)
            self.assertEqual(self.results["reloaded"][1], font)
            self.assertEqual(group.GetString("FontString"), font)

            group.RemString("FontString")
            QtCore.QTimer.singleShot(500, self.inspectFont)
            Gui.showPreferences("Display")
            self.assertEqual(self.errors, [])
            self.assertEqual(self.results["loaded"][0], 0)
            self.assertEqual(self.results["reloaded"][0], 0)
            self.assertNotIn("FontString", group.GetStrings())
        finally:
            if had:
                group.SetString("FontString", old)
            else:
                group.RemString("FontString")
