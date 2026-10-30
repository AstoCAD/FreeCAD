# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""GUI tests for the BIM_Setup command."""

import FreeCAD as App
import FreeCADGui as Gui
from bimcommands import BimSetup
from bimtests import TestArchBaseGui

DOC_PARAMS = "User parameter:BaseApp/Preferences/Document"


class TestBimSetupGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        # remember the license preferences, the tests change them
        param = App.ParamGet(DOC_PARAMS)
        self.savedType = (
            param.GetInt("prefLicenseType") if "prefLicenseType" in param.GetInts() else None
        )
        self.savedUrl = (
            param.GetString("prefLicenseUrl") if "prefLicenseUrl" in param.GetStrings() else None
        )
        self.cmd = BimSetup.BIM_Setup()
        self.cmd.form = Gui.PySideUic.loadUi(":/ui/dialogSetup.ui")
        self.cmd.fillLicenses()

    def tearDown(self):
        self.cmd.form.deleteLater()
        del self.cmd.form
        param = App.ParamGet(DOC_PARAMS)
        if self.savedType is None:
            param.RemInt("prefLicenseType")
        else:
            param.SetInt("prefLicenseType", self.savedType)
        if self.savedUrl is None:
            param.RemString("prefLicenseUrl")
        else:
            param.SetString("prefLicenseUrl", self.savedUrl)
        super().tearDown()

    def test_license_list_matches_preferences(self):
        """BIM_Setup offers the licenses of the preferences, and new documents get them.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/22995
        """
        self.printTestMessage("BIM_Setup license list matches the preferences...")
        combo = self.cmd.form.settingLicense
        self.assertEqual(combo.count(), len(BimSetup.LICENSES))
        param = App.ParamGet(DOC_PARAMS)
        # the last item is "Other", without a predefined license
        for index, (name, url) in enumerate(BimSetup.LICENSES[:-1]):
            self.cmd.saveLicense(index)
            self.assertEqual(param.GetInt("prefLicenseType"), index)
            self.assertEqual(param.GetString("prefLicenseUrl"), url)
            # a new document takes the license at the same index
            doc = App.newDocument("TestBimSetupLicense")
            try:
                self.assertEqual(doc.License, name)
                self.assertEqual(doc.LicenseURL, url)
            finally:
                App.closeDocument(doc.Name)

    def test_license_round_trip(self):
        """Every license reads back as itself in the BIM_Setup dialog.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/22995
        """
        self.printTestMessage("BIM_Setup license round trip...")
        combo = self.cmd.form.settingLicense
        for index in range(len(BimSetup.LICENSES)):
            App.ParamGet(DOC_PARAMS).SetInt("prefLicenseType", index)
            self.cmd.setPreset(None)
            self.assertEqual(combo.currentIndex(), index)
            self.cmd.saveLicense(combo.currentIndex())
            self.assertEqual(App.ParamGet(DOC_PARAMS).GetInt("prefLicenseType"), index)

    def test_other_license_keeps_url(self):
        """Choosing "Other" keeps the custom license URL of the preferences."""
        self.printTestMessage("BIM_Setup keeps a custom license URL...")
        param = App.ParamGet(DOC_PARAMS)
        param.SetString("prefLicenseUrl", "https://example.org/my-license")
        self.cmd.saveLicense(len(BimSetup.LICENSES) - 1)
        self.assertEqual(param.GetInt("prefLicenseType"), len(BimSetup.LICENSES) - 1)
        self.assertEqual(param.GetString("prefLicenseUrl"), "https://example.org/my-license")
