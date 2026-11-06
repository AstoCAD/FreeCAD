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
