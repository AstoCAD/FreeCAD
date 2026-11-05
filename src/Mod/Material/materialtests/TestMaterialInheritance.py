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
Test module for material card inheritance
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD
import Materials

UUIDCycleA = "6c3d2e86-0f6a-4b38-9f49-1d6a4f1f0a01"
UUIDCycleB = "6c3d2e86-0f6a-4b38-9f49-1d6a4f1f0a02"
UUIDChild = "6c3d2e86-0f6a-4b38-9f49-1d6a4f1f0a03"
UUIDParent = "6c3d2e86-0f6a-4b38-9f49-1d6a4f1f0a04"
UUIDDensityModel = "454661e5-265b-4320-8e6f-fcf6223ac3af"


def _card(name, uuid, parent=None, density=None):
    text = '---\nGeneral:\n  UUID: "{}"\n  Name: "{}"\n'.format(uuid, name)
    if parent:
        text += 'Inherits:\n  Parent:\n    UUID: "{}"\n'.format(parent)
    if density:
        text += 'Models:\n  Density:\n    UUID: "{}"\n    Density: "{}"\n'.format(
            UUIDDensityModel, density
        )
    return text


class MaterialInheritanceTestCases(unittest.TestCase):
    """
    Test class for loading material cards that inherit from other cards
    """

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

        self.testDir = tempfile.mkdtemp(prefix="fc_material_inheritance_")

    def tearDown(self):
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")

        # Restore preferences
        param.SetString("CustomMaterialsDir", self.customDir)
        param.SetBool("UseBuiltInMaterials", self.useBuiltInDir)
        param.SetBool("UseMaterialsFromWorkbenches", self.useWorkbenchDir)
        param.SetBool("UseMaterialsFromConfigDir", self.useUserDir)
        param.SetBool("UseMaterialsFromCustomDir", self.useCustomDir)

        paramExternal = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/ExternalInterface"
        )
        paramExternal.SetBool("UseExternal", self.useExternal)

        self.MaterialManager.refresh()
        shutil.rmtree(self.testDir, ignore_errors=True)

    def loadCards(self, cards):
        """Write the cards to the test directory and load only that library"""
        for fileName, text in cards.items():
            with open(os.path.join(self.testDir, fileName), "w", encoding="utf-8") as f:
                f.write(text)

        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Material/Resources")
        param.SetString("CustomMaterialsDir", self.testDir)
        param.SetBool("UseBuiltInMaterials", False)
        param.SetBool("UseMaterialsFromWorkbenches", False)
        param.SetBool("UseMaterialsFromConfigDir", False)
        param.SetBool("UseMaterialsFromCustomDir", True)

        paramExternal = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/ExternalInterface"
        )
        paramExternal.SetBool("UseExternal", False)

        self.MaterialManager.refresh()

    def testInheritedValues(self):
        """A child card receives the values of its parent card"""
        self.loadCards(
            {
                "Parent.FCMat": _card("Parent", UUIDParent, density="2700 kg/m^3"),
                "Child.FCMat": _card("Child", UUIDChild, parent=UUIDParent),
            }
        )
        child = self.MaterialManager.getMaterial(UUIDChild)
        self.assertEqual(child.Parent, UUIDParent)
        self.assertTrue(child.hasPhysicalModel(UUIDDensityModel))
        self.assertAlmostEqual(
            child.getPhysicalValue("Density").getValueAs("kg/m^3").Value, 2700.0
        )

    def testSelfInheritance(self):
        """A card that inherits from itself must not recurse forever while loading"""
        self.loadCards({"CycleA.FCMat": _card("CycleA", UUIDCycleA, parent=UUIDCycleA)})
        material = self.MaterialManager.getMaterial(UUIDCycleA)
        self.assertEqual(material.Name, "CycleA")

    def testInheritanceCycle(self):
        """Two cards that inherit from each other must not recurse forever while loading"""
        self.loadCards(
            {
                "CycleA.FCMat": _card("CycleA", UUIDCycleA, parent=UUIDCycleB, density="1 kg/m^3"),
                "CycleB.FCMat": _card("CycleB", UUIDCycleB, parent=UUIDCycleA),
            }
        )
        self.assertEqual(self.MaterialManager.getMaterial(UUIDCycleA).Name, "CycleA")
        materialB = self.MaterialManager.getMaterial(UUIDCycleB)
        self.assertEqual(materialB.Name, "CycleB")
        self.assertTrue(materialB.hasPhysicalModel(UUIDDensityModel))
