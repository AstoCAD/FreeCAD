# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression test: the Help dock window reopens with its saved size.

The dock size is saved with SetInt("dockWidgetWidth"/"dockWidgetHeight"), but it
was read back with GetBool (always True, i.e. 1 pixel) and with width and height
swapped.

To run tests:
    FreeCAD -t TestHelpGui
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest

    import Help

KEYS = (
    ("Int", "dockWidgetWidth", 450),
    ("Int", "dockWidgetHeight", 350),
    ("Bool", "dockWidgetFloat", True),
)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestHelpDockSizeGui(unittest.TestCase):
    def setUp(self):
        if not Help.get_qtwebwidgets():
            self.skipTest("Requires QtWebEngine")
        self.main = Gui.getMainWindow()
        if self.main.findChild(QtWidgets.QDockWidget, "HelpWidget"):
            self.skipTest("A Help dock window is already open")
        self.prefs = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Help")
        saved = []
        for typ, name, value in KEYS:
            had = name in getattr(self.prefs, "Get" + typ + "s")()
            old = getattr(self.prefs, "Get" + typ)(name) if had else None
            saved.append((typ, name, had, old))
            getattr(self.prefs, "Set" + typ)(name, value)

        def restore():
            dock = self.main.findChild(QtWidgets.QDockWidget, "HelpWidget")
            if dock:
                self.main.removeDockWidget(dock)
                dock.setParent(None)
                dock.deleteLater()
            for typ, name, had, old in saved:
                if had:
                    getattr(self.prefs, "Set" + typ)(name, old)
                else:
                    getattr(self.prefs, "Rem" + typ)(name)

        self.addCleanup(restore)

    def testDockOpensWithSavedSize(self):
        Help.openBrowserHTML("<p>dock size</p>", "", "Help: dock size", "", dialog=True)
        QtTest.QTest.qWait(50)
        dock = self.main.findChild(QtWidgets.QDockWidget, "HelpWidget")
        self.assertIsNotNone(dock)
        self.assertTrue(dock.isFloating())
        self.assertEqual((dock.width(), dock.height()), (450, 350))
