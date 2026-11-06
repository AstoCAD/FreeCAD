# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#                                                                         *
#   This file is part of the FreeCAD CAx development system.              *
#                                                                         *
#   This program is free software; you can redistribute it and/or modify  *
#   it under the terms of the GNU Lesser General Public License (LGPL)    *
#   as published by the Free Software Foundation; either version 2 of     *
#   the License, or (at your option) any later version.                   *
#   for detail see the LICENCE text file.                                 *
#                                                                         *
#   FreeCAD is distributed in the hope that it will be useful,            *
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#   GNU Library General Public License for more details.                  *
#                                                                         *
#   You should have received a copy of the GNU Library General Public     *
#   License along with FreeCAD; if not, write to the Free Software        *
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#   USA                                                                   *
# **************************************************************************

"""
Test module for loading the model and material libraries

Models are only loaded once per process, so the model cases run in a separate
FreeCADCmd process with its own user configuration.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

import FreeCAD
import Materials

UUIDCard = "5b0f8c7e-1d2a-4c3b-9e4f-6a7b8c9d0e10"
UUIDInvalidCard = "5b0f8c7e-1d2a-4c3b-9e4f-6a7b8c9d0e11"
UUIDInvalidCard2 = "5b0f8c7e-1d2a-4c3b-9e4f-6a7b8c9d0e12"
UUIDTestModel = "34d0583d-f999-49ba-99e6-aa40bd5c3a6b"
UUIDModel = "5b0f8c7e-1d2a-4c3b-9e4f-6a7b8c9d0e01"
UUIDMissingModel = "5b0f8c7e-1d2a-4c3b-9e4f-6a7b8c9d0eff"

MODEL_MISSING_PARENT = """\
Model:
  Name: 'MissingParent'
  UUID: '{}'
  Description: 'A model inheriting from a model that is not installed'
  Inherits:
    - Missing:
      UUID: '{}'
  Colour:
    Type: 'String'
    Units: ''
    URL: ''
    Description: 'A colour'
""".format(
    UUIDModel, UUIDMissingModel
)

LOAD_MODELS = """\
import os
import FreeCAD
here = os.path.dirname(os.path.abspath(__file__))
param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")
param.SetString("CustomMaterialsDir", os.path.join(here, "library"))
param.SetBool("UseMaterialsFromCustomDir", True)
param.SetBool("UseMaterialsFromConfigDir", False)
import Materials
models = Materials.ModelManager().Models
with open(os.path.join(here, "result.txt"), "w") as f:
    f.write("loaded {{}}".format("{}" in models))
""".format(
    UUIDModel
)


def _freecadcmd():
    bindir = os.path.join(FreeCAD.getHomePath(), "bin")
    for name in ("FreeCADCmd.exe", "FreeCADCmd", "freecadcmd"):
        path = os.path.join(bindir, name)
        if os.path.isfile(path):
            return path
    return None


class ModelLibraryTestCases(unittest.TestCase):
    """
    Loading model files from a library
    """

    def setUp(self):
        self.exe = _freecadcmd()
        if not self.exe:
            self.skipTest("FreeCADCmd executable not found")
        self.tmpdir = tempfile.mkdtemp(prefix="fc_material_models_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        os.mkdir(os.path.join(self.tmpdir, "library"))

    def loadModels(self, files):
        """Load the model files as the custom library of a new FreeCADCmd process"""
        for fileName, text in files.items():
            with open(os.path.join(self.tmpdir, "library", fileName), "w", encoding="utf-8") as f:
                f.write(text)
        script = os.path.join(self.tmpdir, "load_models.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(LOAD_MODELS)
        cmd = [self.exe, "--user-cfg", os.path.join(self.tmpdir, "user.cfg"), script]
        subprocess.run(cmd, cwd=self.tmpdir, capture_output=True, timeout=300)
        result = os.path.join(self.tmpdir, "result.txt")
        if not os.path.exists(result):
            return None
        with open(result, encoding="utf-8") as f:
            return f.read()

    def testModelWithMissingParent(self):
        """A model inheriting from a model that is not installed is loaded, without a crash"""
        self.assertEqual(self.loadModels({"MissingParent.yml": MODEL_MISSING_PARENT}), "loaded True")


class MaterialLibraryTestCases(unittest.TestCase):
    """
    Refreshing the material libraries after cards or libraries changed
    """

    ModuleLibrary = "MaterialLibraryTestModule"

    def setUp(self):
        self.MaterialManager = Materials.MaterialManager()

        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")
        self.customDir = param.GetString("CustomMaterialsDir", "")
        self.useBuiltInDir = param.GetBool("UseBuiltInMaterials", True)
        self.useWorkbenchDir = param.GetBool("UseMaterialsFromWorkbenches", True)
        self.useUserDir = param.GetBool("UseMaterialsFromConfigDir", True)
        self.useCustomDir = param.GetBool("UseMaterialsFromCustomDir", False)
        paramExternal = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/ExternalInterface"
        )
        self.useExternal = paramExternal.GetBool("UseExternal", False)

        # The card lives in the custom library; a second (empty) library stays loaded
        self.testDir = tempfile.mkdtemp(prefix="fc_material_libraries_")
        customDir = os.path.join(self.testDir, "custom")
        moduleDir = os.path.join(self.testDir, "module")
        os.mkdir(customDir)
        os.mkdir(moduleDir)
        param.SetString("CustomMaterialsDir", customDir)
        param.SetBool("UseBuiltInMaterials", False)
        param.SetBool("UseMaterialsFromWorkbenches", True)
        param.SetBool("UseMaterialsFromConfigDir", False)
        param.SetBool("UseMaterialsFromCustomDir", True)
        paramExternal.SetBool("UseExternal", False)
        module = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/Resources/Modules/"
            + self.ModuleLibrary
        )
        module.SetString("ModuleDir", moduleDir)

        self.cardPath = os.path.join(customDir, "Card.FCMat")
        with open(self.cardPath, "w", encoding="utf-8") as f:
            f.write('---\nGeneral:\n  UUID: "{}"\n  Name: "Card"\n'.format(UUIDCard))
        self.MaterialManager.refresh()

    def tearDown(self):
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")
        param.SetString("CustomMaterialsDir", self.customDir)
        param.SetBool("UseBuiltInMaterials", self.useBuiltInDir)
        param.SetBool("UseMaterialsFromWorkbenches", self.useWorkbenchDir)
        param.SetBool("UseMaterialsFromConfigDir", self.useUserDir)
        param.SetBool("UseMaterialsFromCustomDir", self.useCustomDir)
        FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/Resources/Modules"
        ).RemGroup(self.ModuleLibrary)
        FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/ExternalInterface"
        ).SetBool("UseExternal", self.useExternal)

        self.MaterialManager.refresh()
        shutil.rmtree(self.testDir, ignore_errors=True)

    def testRefreshDropsDeletedCard(self):
        """A card deleted from the disk is gone after a refresh"""
        self.assertIn(UUIDCard, self.MaterialManager.Materials)
        os.remove(self.cardPath)
        self.MaterialManager.refresh()
        self.assertFalse(UUIDCard in self.MaterialManager.Materials)

    def testRefreshDropsCardsOfDisabledLibrary(self):
        """The cards of a library that is no longer used are gone after a refresh"""
        self.assertIn(UUIDCard, self.MaterialManager.Materials)
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")
        param.SetBool("UseMaterialsFromCustomDir", False)
        self.MaterialManager.refresh()
        self.assertFalse(UUIDCard in self.MaterialManager.Materials)

    def testInvalidCardIsSkipped(self):
        """A card with invalid contents is skipped; the other cards are still loaded"""
        cards = {
            # A model without its UUID
            "NoModelUUID.FCMat": '---\nGeneral:\n  UUID: "{}"\n  Name: "NoModelUUID"\n'
            'Models:\n  Density:\n    Density: "1 kg/m^3"\n'.format(UUIDInvalidCard),
            # A boolean that is not one
            "BadBoolean.FCMat": '---\nGeneral:\n  UUID: "{}"\n  Name: "BadBoolean"\n'
            'Models:\n  Test:\n    UUID: "{}"\n    TestBoolean: "yes"\n'.format(
                UUIDInvalidCard2, UUIDTestModel
            ),
        }
        for fileName, text in cards.items():
            path = os.path.join(os.path.dirname(self.cardPath), fileName)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        self.MaterialManager.refresh()
        materials = self.MaterialManager.Materials
        self.assertIn(UUIDCard, materials)
        self.assertFalse(UUIDInvalidCard in materials)
        self.assertFalse(UUIDInvalidCard2 in materials)
