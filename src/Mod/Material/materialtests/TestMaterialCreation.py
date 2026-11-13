# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2023 David Carter
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

    def testEmptyStringClearsQuantity(self):
        """An empty string removes the value of a quantity"""
        uuids = Materials.UUIDs()
        material = Materials.Material()
        material.addPhysicalModel(uuids.Density)
        material.setPhysicalValue("Density", "7850 kg/m^3")
        self.assertTrue(material.isPhysicalModelComplete(uuids.Density))

        material.setPhysicalValue("Density", "")
        self.assertFalse(material.isPhysicalModelComplete(uuids.Density))
        self.assertTrue(material.PropertyObjects["Density"].Empty)

    def testUnknownPropertyRaises(self):
        """Setting a property that no model of the material has raises, physical or appearance"""
        uuids = Materials.UUIDs()
        material = Materials.Material()
        material.addPhysicalModel(uuids.Density)
        material.addAppearanceModel(uuids.BasicRendering)
        with self.assertRaises(FreeCAD.Base.FreeCADError):
            material.setPhysicalValue("DiffuseColor", "(0.1, 0.2, 0.3, 1.0)")
        with self.assertRaises(FreeCAD.Base.FreeCADError):
            material.setAppearanceValue("Density", "7850 kg/m^3")
        self.assertIsNone(material.getAppearanceValue("Density"))


class MaterialModelTestCases(unittest.TestCase):
    """
    Models added to and removed from a material in memory (no library, no files)
    """

    def setUp(self):
        self.uuids = Materials.UUIDs()

    def testRemoveModelKeepsSharedPhysicalProperties(self):
        """Removing a model keeps the models and values another model of the material has too"""
        uuids = self.uuids
        for removed, kept in ((uuids.Fluid, uuids.LinearElastic),
                              (uuids.LinearElastic, uuids.Fluid)):
            with self.subTest(removed=removed):
                material = Materials.Material()
                material.addPhysicalModel(uuids.LinearElastic)
                material.addPhysicalModel(uuids.Fluid)
                material.setPhysicalValue("Density", "7850 kg/m^3")
                material.setPhysicalValue("YoungsModulus", "200 GPa")
                material.setPhysicalValue("KinematicViscosity", "1 m^2/s")

                material.removePhysicalModel(removed)

                self.assertEqual(material.PhysicalModels, [kept])
                self.assertFalse(material.hasPhysicalModel(removed))
                # Both models inherit Density
                self.assertTrue(material.hasPhysicalModel(uuids.Density))
                self.assertTrue(material.hasPhysicalProperty("Density"))
                density = material.getPhysicalValue("Density").getValueAs("kg/m^3").Value
                self.assertAlmostEqual(density, 7850.0)
                fluid = kept == uuids.Fluid
                self.assertEqual(material.hasPhysicalModel(uuids.IsotropicLinearElastic), not fluid)
                self.assertEqual(material.hasPhysicalProperty("YoungsModulus"), not fluid)
                self.assertEqual(material.hasPhysicalProperty("KinematicViscosity"), fluid)

    def testRemoveModelKeepsSharedAppearanceProperties(self):
        """Removing an appearance model keeps the properties of the models still inherited"""
        uuids = self.uuids
        material = Materials.Material()
        material.addAppearanceModel(uuids.AdvancedRendering)
        material.addAppearanceModel(uuids.TextureRendering)
        material.setAppearanceValue("DiffuseColor", "(0.1, 0.2, 0.3, 1.0)")
        material.setAppearanceValue("TexturePath", "texture.png")

        material.removeAppearanceModel(uuids.TextureRendering)

        self.assertEqual(material.AppearanceModels, [uuids.AdvancedRendering])
        self.assertTrue(material.hasAppearanceModel(uuids.BasicRendering))
        self.assertEqual(material.getAppearanceValue("DiffuseColor"), "(0.1, 0.2, 0.3, 1.0)")
        self.assertFalse(material.hasAppearanceProperty("TexturePath"))

    def testRemoveModelRemovesWhatOnlyItProvides(self):
        """The inherited models and properties no other model has go with the removed model"""
        uuids = self.uuids
        material = Materials.Material()
        material.addPhysicalModel(uuids.LinearElastic)
        material.addPhysicalModel(uuids.Thermal)
        material.setPhysicalValue("Density", "7850 kg/m^3")

        # An inherited model is not removed on its own
        material.removePhysicalModel(uuids.Density)
        self.assertTrue(material.hasPhysicalModel(uuids.Density))
        self.assertTrue(material.hasPhysicalProperty("Density"))

        material.removePhysicalModel(uuids.LinearElastic)
        self.assertEqual(material.PhysicalModels, [uuids.Thermal])
        for uuid in (uuids.LinearElastic, uuids.Density, uuids.IsotropicLinearElastic):
            self.assertFalse(material.hasPhysicalModel(uuid))
        self.assertFalse(material.hasPhysicalProperty("Density"))
        self.assertTrue(material.hasPhysicalProperty("ThermalConductivity"))


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

    def testSaveQuantitiesWithFullPrecision(self):
        """Saved quantities read back unrounded, whatever the unit schema"""
        uuids = Materials.UUIDs()
        schema = FreeCAD.Units.getSchema()
        self.addCleanup(FreeCAD.Units.setSchema, schema)
        for name in ("Internal", "Imperial"):
            with self.subTest(schema=name):
                material = Materials.Material()
                material.addPhysicalModel(uuids.Density)
                material.addPhysicalModel(uuids.TestModel)
                material.setPhysicalValue("Density", "7850.123456789 kg/m^3")
                material.setPhysicalValue("TestQuantity", "7850 kg/m^3")
                array = Materials.Array2D()
                array.Columns = 2
                array.Rows = 1
                array.setValue(0, 0, "293.123456789 K")
                array.setValue(0, 1, "7850.123456789 kg/m^3")
                material.setValue("TestArray2D", array)

                FreeCAD.Units.setSchema(FreeCAD.Units.listSchemas().index(name))
                self.MaterialManager.save("Custom", material, name + ".FCMat")
                self.MaterialManager.refresh()
                saved = self.MaterialManager.getMaterialByPath(name + ".FCMat", "Custom")

                density = saved.getPhysicalValue("Density").getValueAs("kg/m^3").Value
                self.assertAlmostEqual(density, 7850.123456789, places=9)
                quantity = saved.getPhysicalValue("TestQuantity").getValueAs("kg/m^3").Value
                self.assertAlmostEqual(quantity, 7850.0, places=9)
                savedArray = saved.getPhysicalValue("TestArray2D")
                temperature = savedArray.getValue(0, 0).getValueAs("K").Value
                self.assertAlmostEqual(temperature, 293.123456789, places=9)
                density = savedArray.getValue(0, 1).getValueAs("kg/m^3").Value
                self.assertAlmostEqual(density, 7850.123456789, places=9)

    def testSaveFloatsWithFullPrecision(self):
        """Float values are kept and saved in double precision"""
        uuids = Materials.UUIDs()
        material = Materials.Material()
        material.addPhysicalModel(uuids.TestModel)
        material.addPhysicalModel(uuids.IsotropicLinearElastic)
        material.setPhysicalValue("TestFloat", "0.123456789012345")
        material.setPhysicalValue("PoissonRatio", "0.3")
        self.assertEqual(material.getPhysicalValue("TestFloat"), 0.123456789012345)
        self.assertEqual(material.getPhysicalValue("PoissonRatio"), 0.3)

        self.MaterialManager.save("Custom", material, "Floats.FCMat")
        self.MaterialManager.refresh()
        saved = self.MaterialManager.getMaterialByPath("Floats.FCMat", "Custom")
        self.assertEqual(saved.getPhysicalValue("TestFloat"), 0.123456789012345)
        self.assertEqual(saved.getPhysicalValue("PoissonRatio"), 0.3)

    def testSaveChildOfParentWithSpecialName(self):
        """A card inheriting from a card named with YAML special characters can be read back"""
        uuids = Materials.UUIDs()
        parent = Materials.Material()
        parent.addPhysicalModel(uuids.Density)
        parent.setPhysicalValue("Density", "1000 kg/m^3")
        self.MaterialManager.save("Custom", parent, "Steel #1.FCMat", overwrite=True)
        self.MaterialManager.refresh()
        parent = self.MaterialManager.getMaterialByPath("Steel #1.FCMat", "Custom")

        child = self.MaterialManager.inheritMaterial(parent.UUID)
        child.addPhysicalModel(uuids.Thermal)
        child.setPhysicalValue("ThermalConductivity", "1 W/m/K")
        self.MaterialManager.save(
            "Custom", child, "Child.FCMat", overwrite=True, saveInherited=True
        )
        self.MaterialManager.refresh()

        child = self.MaterialManager.getMaterialByPath("Child.FCMat", "Custom")
        self.assertEqual(child.Parent, parent.UUID)
        self.assertAlmostEqual(
            child.getPhysicalValue("Density").getValueAs("kg/m^3").Value, 1000.0
        )

    def testSaveTagsWithQuotes(self):
        """Tags with quotes and backslashes are saved so that they can be read back"""
        uuid = "4a1d5c0e-7b2f-4e3a-9c8d-1f2e3d4c5b6a"
        with open(os.path.join(self.libDir, "Tagged.FCMat"), "w", encoding="utf-8") as f:
            f.write(
                '---\nGeneral:\n  UUID: "{}"\n  Name: "Tagged"\n'
                "  Tags:\n    - 'say \"hi\"'\n    - 'back\\slash'\n".format(uuid)
            )
        self.MaterialManager.refresh()
        material = self.MaterialManager.getMaterial(uuid)
        self.assertEqual(sorted(material.Tags), ["back\\slash", 'say "hi"'])

        self.MaterialManager.save(
            "Custom", material, "Copy.FCMat", overwrite=True, saveAsCopy=True
        )
        os.remove(os.path.join(self.libDir, "Tagged.FCMat"))
        self.MaterialManager.refresh()
        copy = self.MaterialManager.getMaterialByPath("Copy.FCMat", "Custom")
        self.assertEqual(sorted(copy.Tags), ["back\\slash", 'say "hi"'])

    def testSaveStringsWithLineBreaks(self):
        """Line breaks and control characters in the strings of a card are read back"""
        uuids = Materials.UUIDs()
        description = "First paragraph.\n\nSecond paragraph:\n---\n...\r\nend\x07"
        material = Materials.Material()
        material.Name = "Line breaks"
        material.Description = description
        material.addPhysicalModel(uuids.TestModel)
        material.setPhysicalValue("TestString", "one\ntwo")
        material.setValue("TestList", ["a\nb", "c"])
        self.MaterialManager.save("Custom", material, "LineBreaks.FCMat", overwrite=True)
        self.MaterialManager.refresh()

        saved = self.MaterialManager.getMaterialByPath("LineBreaks.FCMat", "Custom")
        self.assertEqual(saved.Description, description)
        self.assertEqual(saved.getPhysicalValue("TestString"), "one\ntwo")
        self.assertEqual(saved.getPhysicalValue("TestList"), ["a\nb", "c"])

    def testSaveMultiLineStringsWithEmptyLines(self):
        """Multi-line strings are read back with their empty lines and final line breaks"""
        uuids = Materials.UUIDs()
        values = (
            ("first\n\n  indented\n\nlast", "first\n\n  indented\n\nlast"),
            ("<svg>\n\n  <g/>\n</svg>\n", "<svg>\n\n  <g/>\n</svg>\n"),
            ("\nends with empty lines\n\n", "\nends with empty lines\n\n"),
            ("crlf\r\n\r\nlines", "crlf\n\nlines"),
        )
        for index, (value, expected) in enumerate(values):
            with self.subTest(value=value):
                material = Materials.Material()
                material.addPhysicalModel(uuids.TestModel)
                material.setPhysicalValue("TestMultiLineString", value)
                material.setPhysicalValue("TestSVG", value)
                path = "MultiLine{}.FCMat".format(index)
                self.MaterialManager.save("Custom", material, path)
                self.MaterialManager.refresh()

                saved = self.MaterialManager.getMaterialByPath(path, "Custom")
                self.assertEqual(saved.getPhysicalValue("TestMultiLineString"), expected)
                self.assertEqual(saved.getPhysicalValue("TestSVG"), expected)

    def testSaveAfterRemovingModel(self):
        """A material saves after removing a model whose inherited properties another model has"""
        uuids = Materials.UUIDs()
        material = Materials.Material()
        material.addPhysicalModel(uuids.LinearElastic)
        material.addPhysicalModel(uuids.Fluid)
        material.setPhysicalValue("Density", "7850 kg/m^3")
        material.removePhysicalModel(uuids.Fluid)

        self.MaterialManager.save("Custom", material, "Removed.FCMat")
        self.MaterialManager.refresh()
        saved = self.MaterialManager.getMaterialByPath("Removed.FCMat", "Custom")
        self.assertEqual(saved.PhysicalModels, [uuids.LinearElastic])
        density = saved.getPhysicalValue("Density").getValueAs("kg/m^3").Value
        self.assertAlmostEqual(density, 7850.0)

    def testSaveIntoReadOnlyLibraryRaises(self):
        """A read-only library (as the System one) does not accept saves"""
        with self.assertRaises(FreeCAD.Base.FreeCADError):
            self.MaterialManager.save(self.ReadOnlyLibrary, Materials.Material(), "Saved.FCMat")
        self.assertEqual(os.listdir(self.readOnlyDir), [])
