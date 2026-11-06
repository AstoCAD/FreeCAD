# SPDX-License-Identifier: LGPL-2.1-or-later

#**************************************************************************
#   Copyright (c) 2023 David Carter <dcarter@davidcarter.ca>              *
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
#**************************************************************************

"""
Test module for FreeCAD material cards and APIs
"""

import unittest
import FreeCAD
import Materials

import os
import shutil
import tempfile

parseQuantity = FreeCAD.Units.parseQuantity

class MaterialCreationTestCases(unittest.TestCase):
    """
    Test class for FreeCAD material creation and APIs
    """

    def setUp(self):
        """ Setup function to initialize test data """
        self.ModelManager = Materials.ModelManager()
        self.MaterialManager = Materials.MaterialManager()
        self.uuids = Materials.UUIDs()

    def tearDown(self):
        try:
            material = self.MaterialManager.getMaterialByPath("Example/Frakenstein.FCMat", "User")
            os.remove(material.LibraryRoot + "/Example/Frakenstein.FCMat")
            try:
                os.rmdir(material.LibraryRoot + "/Example")
            except OSError:
                # Can't remove directories that aren't empty
                pass
        except LookupError:
            pass

    def checkNewMaterial(self, material):
        """ Check the state of a newly created material """
        self.assertEqual(len(material.UUID), 36)
        self.assertEqual(len(material.Name), 0)
        self.assertEqual(len(material.Author), 0)
        self.assertEqual(len(material.License), 0)
        self.assertEqual(len(material.Description), 0)
        self.assertEqual(len(material.URL), 0)
        self.assertEqual(len(material.Reference), 0)
        self.assertEqual(len(material.Parent), 0)
        self.assertEqual(len(material.Tags), 0)

    def getQuantity(self, value):
        quantity = parseQuantity(value)
        quantity.Format = { "NumberFormat" : "g",
                            "Precision" : 6 }
        return quantity

    def testCreateMaterial(self):
        """ Create a material with properties """
        material = Materials.Material()
        self.checkNewMaterial(material)

        material.Name = "Frankenstein"
        material.Author = "Mary Shelley"
        material.License = "CC-BY-3.0"
        material.Description = "The sad story of a boy afraid of fire"
        material.URL = "https://www.example.com"
        material.Reference = "ISBN 978-1673287882"

        # Ensure a valid UUID
        self.assertEqual(len(material.UUID), 36)
        uuid = material.UUID

        self.assertEqual(material.Name, "Frankenstein")
        self.assertEqual(material.Author, "Mary Shelley")
        self.assertEqual(material.License, "CC-BY-3.0")
        self.assertEqual(material.Description, "The sad story of a boy afraid of fire")
        self.assertEqual(material.URL, "https://www.example.com")
        self.assertEqual(material.Reference, "ISBN 978-1673287882")

        self.assertEqual(len(material.PhysicalModels), 0)
        self.assertEqual(len(material.AppearanceModels), 0)

        material.addAppearanceModel(self.uuids.TextureRendering)
        self.assertEqual(len(material.AppearanceModels), 1)
        # TextureRendering inherits BasicRendering
        self.assertTrue(material.hasAppearanceModel(self.uuids.BasicRendering))
        self.assertTrue(material.hasAppearanceModel(self.uuids.TextureRendering))

        # Colors are tuples of 3 (rgb) or 4 (rgba) values between 0 and 1
        # All values are set with strings
        material.setAppearanceValue("DiffuseColor", "(1.0, 1.0, 1.0)")
        material.setAppearanceValue("SpecularColor", "(0, 0, 0, 1.0)")

        self.assertEqual(material.AppearanceProperties["DiffuseColor"], "(1.0, 1.0, 1.0)")
        self.assertEqual(material.getAppearanceValue("DiffuseColor"), "(1.0, 1.0, 1.0)")

        self.assertEqual(material.AppearanceProperties["SpecularColor"], "(0, 0, 0, 1.0)")
        self.assertEqual(material.getAppearanceValue("SpecularColor"), "(0, 0, 0, 1.0)")

        # Properties without a value will return None
        self.assertIsNone(material.getAppearanceValue("AmbientColor"))
        self.assertIsNone(material.getAppearanceValue("EmissiveColor"))
        self.assertIsNone(material.getAppearanceValue("Shininess"))
        self.assertIsNone(material.getAppearanceValue("Transparency"))
        self.assertIsNone(material.getAppearanceValue("TexturePath"))
        self.assertIsNone(material.getAppearanceValue("TextureImage"))
        self.assertIsNone(material.getAppearanceValue("TextureScaling"))

        material.addPhysicalModel(self.uuids.Density)
        self.assertEqual(len(material.PhysicalModels), 1)
        self.assertTrue(material.hasPhysicalModel(self.uuids.Density))

        # Quantity properties require units
        with self.assertRaises(ValueError):
            # Units of mass not  density
            material.setPhysicalValue("Density", "99.9 kg")

        material.setPhysicalValue("Density", "99.9")
        self.assertEqual(material.getPhysicalValue("Density").Format["NumberFormat"], "g")
        self.assertEqual(material.getPhysicalValue("Density").UserString, self.getQuantity("99.90 kg/m^3").UserString)

        material.setPhysicalValue("Density", "99.9 kg/m^3")
        self.assertEqual(material.getPhysicalValue("Density").Format["NumberFormat"], "g")
        self.assertEqual(material.getPhysicalValue("Density").UserString, self.getQuantity("99.90 kg/m^3").UserString)

        # MaterialManager is unaware of the material until it is saved
        #
        # When initially creating the material, setting overwrite=True preserves the UUID. This should not
        # be used when saving after properties have been edited as this could adversely affect other
        # documents or parts using the same material. Setting overwrite=False, or omitting it, will change
        # the UUID. It will also fail if the material file already exists.
        #
        # Similarly, saveAsCopy=True preserves the UUID and should be used carefully. It will save an
        # identical copy of the original but in a different location.
        #
        # The third optional parameter is saveInherited. When set to true it will mark models and properties
        # as inherited without duplicating them. When false, they will be copied as uninherited. Avoid
        # self-inheritance as this creates an invalid model. It will have a different UUID than the original.
        #
        self.MaterialManager.save("User", material, "Example/Frakenstein.FCMat", overwrite=True)

        # Now the UUID is valid
        self.assertEqual(len(material.UUID), 36)
        self.assertEqual(material.UUID, uuid)
        self.assertIn(uuid, self.MaterialManager.Materials)
        self.assertIsNotNone(self.MaterialManager.getMaterialByPath("Example/Frakenstein.FCMat", "User"))
        self.assertIsNotNone(self.MaterialManager.getMaterial(uuid))


class MaterialValueTestCases(unittest.TestCase):
    """
    Values set on a material in memory (no library, no files)
    """

    def testQuantityWithoutUnitsKeepsItsValue(self):
        """A value given without units gets the property units without being rounded"""
        uuids = Materials.UUIDs()
        material = Materials.Material()
        material.addPhysicalModel(uuids.Thermal)
        material.addPhysicalModel(uuids.Density)

        material.setPhysicalValue("ThermalExpansionCoefficient", "0.0000123")
        value = material.getPhysicalValue("ThermalExpansionCoefficient")
        self.assertAlmostEqual(value.getValueAs("1/K").Value, 1.23e-5, delta=1e-12)

        material.setPhysicalValue("Density", "7850.123")
        value = material.getPhysicalValue("Density")
        self.assertAlmostEqual(value.getValueAs("kg/m^3").Value, 7850.123, delta=1e-6)


class MaterialSaveTestCases(unittest.TestCase):
    """
    Saving into temporary libraries: a writable custom one and a read-only module one
    """

    ReadOnlyLibrary = "MaterialSaveTestReadOnly"

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

        self.testDir = tempfile.mkdtemp(prefix="fc_material_save_")
        self.libDir = os.path.join(self.testDir, "lib")
        self.readOnlyDir = os.path.join(self.testDir, "readonly")
        os.mkdir(self.libDir)
        os.mkdir(self.readOnlyDir)

        param.SetString("CustomMaterialsDir", self.libDir)
        param.SetBool("UseBuiltInMaterials", False)
        param.SetBool("UseMaterialsFromWorkbenches", True)
        param.SetBool("UseMaterialsFromConfigDir", False)
        param.SetBool("UseMaterialsFromCustomDir", True)
        paramExternal.SetBool("UseExternal", False)
        module = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/Resources/Modules/"
            + self.ReadOnlyLibrary
        )
        module.SetString("ModuleDir", self.readOnlyDir)
        module.SetBool("ModuleReadOnly", True)

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
        ).RemGroup(self.ReadOnlyLibrary)
        FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Material/ExternalInterface"
        ).SetBool("UseExternal", self.useExternal)

        self.MaterialManager.refresh()
        shutil.rmtree(self.testDir, ignore_errors=True)

    def testSaveOutsideLibraryRaises(self):
        """A path leading out of the library root must not be written"""
        for path in ("../Escape.FCMat", "sub/../../Escape.FCMat", "./../lib/../Escape.FCMat"):
            with self.subTest(path=path):
                with self.assertRaises(FreeCAD.Base.FreeCADError):
                    self.MaterialManager.save("Custom", Materials.Material(), path)
                self.assertFalse(os.path.exists(os.path.join(self.testDir, "Escape.FCMat")))

    def testSaveInsideLibrary(self):
        """Paths that stay inside the library after normalization are saved as before"""
        self.MaterialManager.save("Custom", Materials.Material(), "Example/Saved.FCMat")
        self.assertTrue(os.path.isfile(os.path.join(self.libDir, "Example", "Saved.FCMat")))
        self.MaterialManager.save("Custom", Materials.Material(), "sub/../Inside.FCMat")
        self.assertTrue(os.path.isfile(os.path.join(self.libDir, "Inside.FCMat")))
        self.MaterialManager.save("Custom", Materials.Material(), "/Custom/Prefixed.FCMat")
        self.assertTrue(os.path.isfile(os.path.join(self.libDir, "Prefixed.FCMat")))

    def testSaveIntoReadOnlyLibraryRaises(self):
        """A read-only library (as the System one) does not accept saves"""
        with self.assertRaises(FreeCAD.Base.FreeCADError):
            self.MaterialManager.save(self.ReadOnlyLibrary, Materials.Material(), "Saved.FCMat")
        self.assertEqual(os.listdir(self.readOnlyDir), [])
