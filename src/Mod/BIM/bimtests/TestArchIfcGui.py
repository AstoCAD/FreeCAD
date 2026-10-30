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

"""GUI tests for NativeIFC (need ifcopenshell)."""

import os
import shutil
import tempfile
import unittest

import FreeCAD
import FreeCADGui
from bimtests import TestArchBaseGui

try:
    import ifcopenshell

    _HAS_IFCOPENSHELL = True
except ImportError:
    _HAS_IFCOPENSHELL = False


@unittest.skipUnless(_HAS_IFCOPENSHELL, "ifcopenshell not available")
class TestArchIfcGui(TestArchBaseGui.TestArchBaseGui):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/NativeIFC")
        self.ask = self.params.GetBool("AskBeforeSaving", True)
        self.params.SetBool("AskBeforeSaving", False)

    def tearDown(self):
        self.params.SetBool("AskBeforeSaving", self.ask)
        super().tearDown()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_hybrid_save_keeps_document_unmodified(self):
        """Saving the IFC projects of a hybrid document after the document
        itself was saved must not mark the document as modified again.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/16410
        """
        from nativeifc import ifc_observer
        from nativeifc import ifc_tools

        self.printTestMessage("NativeIFC hybrid save keeps document unmodified...")
        proj = ifc_tools.create_document_object(self.document, silent=True)
        ifcpath = os.path.join(self.tmpdir, "hybrid.ifc")
        proj.IfcFilePath = ifcpath
        proj.Modified = True
        self.document.recompute()
        gdoc = FreeCADGui.getDocument(self.document.Name)
        # the observer runs right after the FreeCAD document was saved
        gdoc.Modified = False
        obs = ifc_observer.ifc_observer()
        obs.docname = self.document.Name
        obs.save()
        self.assertTrue(os.path.exists(ifcpath))
        self.assertFalse(proj.Modified)
        self.assertFalse(gdoc.Modified, "the saved document is marked as modified")
