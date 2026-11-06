# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI tests for the Start page."""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

DRAFT_PARAMS = "User parameter:BaseApp/Preferences/Mod/Draft"
START_PARAMS = "User parameter:BaseApp/Preferences/Mod/Start"


class TestStartDraftButton(unittest.TestCase):
    """The "2D Draft" button must honour the Draft default working plane (issue #16224)."""

    def setUp(self):
        self.draftParams = FreeCAD.ParamGet(DRAFT_PARAMS)
        self.startParams = FreeCAD.ParamGet(START_PARAMS)
        self.hadDefaultWP = "defaultWP" in self.draftParams.GetInts()
        self.oldDefaultWP = self.draftParams.GetInt("defaultWP", 1)
        self.hadCloseStart = "closeStart" in self.startParams.GetBools()
        self.oldCloseStart = self.startParams.GetBool("closeStart", False)
        self.startParams.SetBool("closeStart", False)
        self.oldWorkbench = FreeCADGui.activeWorkbench().name()
        self.newDocs = []

    def tearDown(self):
        for name in self.newDocs:
            if name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(name)
        if self.hadDefaultWP:
            self.draftParams.SetInt("defaultWP", self.oldDefaultWP)
        else:
            self.draftParams.RemInt("defaultWP")
        if self.hadCloseStart:
            self.startParams.SetBool("closeStart", self.oldCloseStart)
        else:
            self.startParams.RemBool("closeStart")
        FreeCADGui.activateWorkbench(self.oldWorkbench)

    def _draftButton(self):
        FreeCADGui.runCommand("Start_Start")
        QtWidgets.QApplication.processEvents()
        view = FreeCADGui.getMainWindow().findChild(QtWidgets.QWidget, "StartView")
        self.assertIsNotNone(view, "Start page not found")
        heading = QtCore.QCoreApplication.translate("StartGui::StartView", "2D Draft")
        for button in view.findChildren(QtWidgets.QPushButton):
            for label in button.findChildren(QtWidgets.QLabel):
                if label.text() == heading:
                    return button
        self.fail("2D Draft button not found on the Start page")

    def _viewDirectionAfterClick(self, defaultWP, expected):
        self.draftParams.SetInt("defaultWP", defaultWP)
        button = self._draftButton()
        before = set(FreeCAD.listDocuments())
        button.click()
        self.newDocs = [name for name in FreeCAD.listDocuments() if name not in before]
        self.assertEqual(len(self.newDocs), 1, "2D Draft button did not create a document")

        view = FreeCADGui.getDocument(self.newDocs[0]).ActiveView
        # wait for a possible camera animation to finish
        deadline = time.time() + 5.0
        direction = view.getViewDirection()
        while not direction.isEqual(expected, 1e-6) and time.time() < deadline:
            QtWidgets.QApplication.processEvents()
            time.sleep(0.05)
            direction = view.getViewDirection()
        return direction

    def testDefaultWPTop(self):
        expected = FreeCAD.Vector(0, 0, -1)
        direction = self._viewDirectionAfterClick(1, expected)
        self.assertTrue(direction.isEqual(expected, 1e-6), "view direction {}".format(direction))

    def testDefaultWPFront(self):
        expected = FreeCAD.Vector(0, 1, 0)
        direction = self._viewDirectionAfterClick(2, expected)
        self.assertTrue(direction.isEqual(expected, 1e-6), "view direction {}".format(direction))

    def testDefaultWPSide(self):
        expected = FreeCAD.Vector(-1, 0, 0)
        direction = self._viewDirectionAfterClick(3, expected)
        self.assertTrue(direction.isEqual(expected, 1e-6), "view direction {}".format(direction))


class TestStartMigrator2024(unittest.TestCase):
    """The 2024 migration must keep "Close Start after opening a file" (read as closeStart)."""

    GROUP = "StartMigratorTest"

    def setUp(self):
        from StartMigrator import StartMigrator2024

        self.migrator = StartMigrator2024()
        # work on a scratch group, never on the user's Start preferences
        self.prefs = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/" + self.GROUP)
        self.migrator.start_prefs = self.prefs
        self.addCleanup(
            lambda: FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod").RemGroup(self.GROUP)
        )

    def testCloseStartIsKept(self):
        self.prefs.SetBool("closeStart", True)
        self.migrator._remove_deprecated_parameters()
        # StartView.cpp and DlgStartPreferences.ui use "closeStart"
        self.assertTrue(self.prefs.GetBool("closeStart", False))
