# ***************************************************************************
# *   Copyright (c) 2003 Juergen Riegel <juergen.riegel@web.de>             *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful,            *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with FreeCAD; if not, write to the Free Software        *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************/

import FreeCAD, os, unittest, tempfile, zipfile
from FreeCAD import Base
import math
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# define the functions to test the FreeCAD Document code
# ---------------------------------------------------------------------------


class Proxy:
    def __init__(self, obj):
        self.Dictionary = {}
        self.obj = obj
        obj.Proxy = self

    def dumps(self):
        return self.Dictionary

    def loads(self, data):
        self.Dictionary = data


class MyFeature:
    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLinkList", "propLink")

    def onDocumentRestored(self, obj):
        if hasattr(obj, "propLink"):
            obj.removeProperty("propLink")


class DocumentBasicCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("CreateTest")

    def saveAndRestore(self):
        # saving and restoring
        SaveName = tempfile.gettempdir() + os.sep + "CreateTest.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument("CreateTest")
        self.Doc = FreeCAD.open(SaveName)
        return self.Doc

    def testIssue18601(self):
        lnk = self.Doc.addObject("App::FeaturePython", "MyLink")
        obj = self.Doc.addObject("App::FeaturePython", "MyFeature")
        fea = MyFeature(obj)
        obj.propLink = [lnk]
        doc = self.saveAndRestore()
        FreeCAD.closeDocument(doc.Name)
        self.Doc = FreeCAD.newDocument("CreateTest")

    def testIssue24571(self):
        obj = self.Doc.addObject("App::FeatureTest", "Object")
        obj.ConstraintInt = (50, 0, 100, 1)
        obj.ConstraintFloat = (50.0, 0.0, 100.0, 1.0)
        self.Doc = self.saveAndRestore()
        obj = self.Doc.getObject("Object")
        # int
        obj.ConstraintInt = -1
        self.assertEqual(obj.ConstraintInt, 0)
        obj.ConstraintInt = 101
        self.assertEqual(obj.ConstraintInt, 100)
        # float
        obj.ConstraintFloat = -1.0
        self.assertEqual(obj.ConstraintFloat, 0.0)
        obj.ConstraintFloat = 101.0
        self.assertEqual(obj.ConstraintFloat, 100.0)

    def testAccessByNameOrID(self):
        obj = self.Doc.addObject("App::DocumentObject", "MyName")

        with self.assertRaises(TypeError):
            self.Doc.getObject([1])

        self.assertEqual(self.Doc.getObject(obj.Name), obj)
        self.assertEqual(self.Doc.getObject("Unknown"), None)
        self.assertEqual(self.Doc.getObject(obj.ID), obj)
        self.assertEqual(self.Doc.getObject(obj.ID + 1), None)

    def testCreateDestroy(self):
        # FIXME: Causes somehow a ref count error but it's _not_ FreeCAD.getDocument()!!!
        # If we remove the whole method no error appears.
        self.assertTrue(FreeCAD.getDocument("CreateTest") is not None, "Creating Document failed")

    def testAddition(self):
        # Cannot write a real test case for that but when debugging the
        # C-code there shouldn't be a memory leak (see rev. 1814)
        self.Doc.openTransaction("Add")
        L1 = self.Doc.addObject("App::FeatureTest", "Label")
        self.Doc.commitTransaction()
        self.Doc.undo()

    def testAddRemoveUndo(self):
        # Bug #0000525
        self.Doc.openTransaction("Add")
        obj = self.Doc.addObject("App::FeatureTest", "Label")
        self.Doc.commitTransaction()
        self.Doc.removeObject(obj.Name)
        self.Doc.undo()
        self.Doc.undo()

    def testNoRecompute(self):
        L1 = self.Doc.addObject("App::FeatureTest", "Label")
        self.Doc.recompute()
        L1.TypeNoRecompute = 2
        execcount = L1.ExecCount
        objectcount = self.Doc.recompute()
        self.assertEqual(objectcount, 0)
        self.assertEqual(L1.ExecCount, execcount)

    def testNoRecomputeParent(self):
        L1 = self.Doc.addObject("App::FeatureTest", "Child")
        L2 = self.Doc.addObject("App::FeatureTest", "Parent")
        L2.Source1 = L1
        self.Doc.recompute()
        L1.TypeNoRecompute = 2
        countChild = L1.ExecCount
        countParent = L2.ExecCount
        objectcount = self.Doc.recompute()
        self.assertEqual(objectcount, 1)
        self.assertEqual(L1.ExecCount, countChild)
        self.assertEqual(L2.ExecCount, countParent + 1)

        L1.touch("")
        countChild = L1.ExecCount
        countParent = L2.ExecCount
        objectcount = self.Doc.recompute()
        self.assertEqual(objectcount, 1)
        self.assertEqual(L1.ExecCount, countChild)
        self.assertEqual(L2.ExecCount, countParent + 1)

        L1.enforceRecompute()
        countChild = L1.ExecCount
        countParent = L2.ExecCount
        objectcount = self.Doc.recompute()
        self.assertEqual(objectcount, 2)
        self.assertEqual(L1.ExecCount, countChild + 1)
        self.assertEqual(L2.ExecCount, countParent + 1)

    def testAbortTransaction(self):
        self.Doc.openTransaction("Add")
        obj = self.Doc.addObject("App::FeatureTest", "Label")
        self.Doc.abortTransaction()
        TempPath = tempfile.gettempdir()
        SaveName = TempPath + os.sep + "SaveRestoreTests.FCStd"
        self.Doc.saveAs(SaveName)

    def testRemoval(self):
        # Cannot write a real test case for that but when debugging the
        # C-code there shouldn't be a memory leak (see rev. 1814)
        self.Doc.openTransaction("Add")
        L1 = self.Doc.addObject("App::FeatureTest", "Label")
        self.Doc.commitTransaction()
        self.Doc.openTransaction("Rem")
        L1 = self.Doc.removeObject("Label")
        self.Doc.commitTransaction()

    def testObjects(self):
        L1 = self.Doc.addObject("App::FeatureTest", "Label_1")
        # call members to check for errors in ref counting
        self.Doc.ActiveObject
        self.Doc.Objects
        self.Doc.UndoRedoMemSize
        self.Doc.UndoCount
        # test read only mechanismus
        try:
            self.Doc.UndoCount = 3
        except Exception:
            FreeCAD.Console.PrintLog("   exception thrown, OK\n")
        else:
            self.fail("no exception thrown")
        self.Doc.RedoCount
        self.Doc.UndoNames
        self.Doc.RedoNames
        self.Doc.recompute()
        self.assertTrue(L1.Integer == 4711)
        self.assertTrue(L1.Float - 47.11 < 0.001)
        self.assertTrue(L1.Bool == True)
        self.assertTrue(L1.String == "4711")
        self.assertTrue(float(L1.Angle) - 3.0 < 0.001)
        self.assertTrue(float(L1.Distance) - 47.11 < 0.001)

        # test basic property stuff
        self.assertTrue(not L1.getDocumentationOfProperty("Source1") == "")
        self.assertTrue(L1.getGroupOfProperty("Source1") == "Feature Test")
        self.assertTrue(L1.getTypeOfProperty("Source1") == [])
        self.assertTrue(L1.getEnumerationsOfProperty("Source1") is None)

        # test the constraint types ( both are constraint to percent range)
        self.assertTrue(L1.ConstraintInt == 5)
        self.assertTrue(L1.ConstraintFloat - 5.0 < 0.001)
        L1.ConstraintInt = 500
        L1.ConstraintFloat = 500.0
        self.assertTrue(L1.ConstraintInt == 100)
        self.assertTrue(L1.ConstraintFloat - 100.0 < 0.001)
        L1.ConstraintInt = -500
        L1.ConstraintFloat = -500.0
        self.assertTrue(L1.ConstraintInt == 0)
        self.assertTrue(L1.ConstraintFloat - 0.0 < 0.001)

        # test enum property
        # in App::FeatureTest the current value is set to 4
        self.assertTrue(L1.Enum == "Four")
        L1.Enum = "Three"
        self.assertTrue(L1.Enum == "Three", "Different value to 'Three'")
        L1.Enum = 2
        self.assertTrue(L1.Enum == "Two", "Different value to 'Two'")
        try:
            L1.Enum = "SurelyNotInThere!"
        except Exception:
            FreeCAD.Console.PrintLog("   exception thrown, OK\n")
        else:
            self.fail("no exception thrown")
        self.assertTrue(
            sorted(L1.getEnumerationsOfProperty("Enum"))
            == sorted(["Zero", "One", "Two", "Three", "Four"])
        )

        # self.assertTrue(L1.IntegerList  == [4711]   )
        # f = L1.FloatList
        # self.assertTrue(f -47.11<0.001    )
        # self.assertTrue(L1.Matrix  == [1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0,13.0,14.0,15.0,16.0] )
        # self.assertTrue(L1.Vector  == [1.0,2.0,3.0])

        self.assertTrue(L1.Label == "Label_1", "Invalid object name")
        L1.Label = "Label_2"
        self.Doc.recompute()
        self.assertTrue(L1.Label == "Label_2", "Invalid object name")
        self.Doc.removeObject("Label_1")

    def testEnum(self):
        enumeration_choices = ["one", "two"]
        obj = self.Doc.addObject("App::FeaturePython", "Label_2")
        obj.addProperty("App::PropertyEnumeration", "myEnumeration", "Enum", "mytest")
        with self.assertRaises(ValueError):
            obj.myEnumeration = enumeration_choices[0]

        obj.myEnumeration = enumeration_choices
        obj.myEnumeration = 0
        self.Doc.openTransaction("Modify enum")
        obj.myEnumeration = 1
        self.assertTrue(obj.myEnumeration, enumeration_choices[1])
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.assertTrue(obj.myEnumeration, enumeration_choices[0])

    def testWrongTypes(self):
        with self.assertRaises(TypeError):
            self.Doc.addObject("App::DocumentObjectExtension")

        class Feature:
            pass

        with self.assertRaises(TypeError):
            self.Doc.addObject(type="App::DocumentObjectExtension", objProxy=Feature(), attach=True)

        ext = FreeCAD.Base.TypeId.fromName("App::DocumentObjectExtension")
        self.assertEqual(ext.createInstance(), None)

        obj = self.Doc.addObject("App::FeaturePython", "Object")
        with self.assertRaises(TypeError):
            obj.addProperty("App::DocumentObjectExtension", "Property")

        with self.assertRaises(TypeError):
            self.Doc.findObjects(Type="App::DocumentObjectExtension")

        e = FreeCAD.Base.TypeId.fromName("App::LinkExtensionPython")
        self.assertIsNone(e.createInstance())

        if FreeCAD.GuiUp:
            obj = self.Doc.addObject("App::DocumentObject", viewType="App::Extension")
            self.assertIsNone(obj.ViewObject)

    def testFindObjectsInvalidRegex(self):
        # An invalid regular expression was silently ignored: findObjects() then
        # returned every object of the type instead of raising.
        first = self.Doc.addObject("App::FeaturePython", "First")
        first.Label = "Alpha"
        self.Doc.addObject("App::FeaturePython", "Second")
        self.assertEqual(self.Doc.findObjects(Label="^Alp"), [first])
        self.assertEqual(self.Doc.findObjects(Name="^First$"), [first])
        for pattern in ("(", "[", "*", "\\"):
            with self.assertRaises(RuntimeError, msg=pattern):
                self.Doc.findObjects(Label=pattern)
            with self.assertRaises(RuntimeError, msg=pattern):
                self.Doc.findObjects(Name=pattern)

    def testMem(self):
        self.Doc.MemSize

    def testViewObjectWithFreeCADGuiImportedInConsoleMode(self):
        if FreeCAD.GuiUp:
            self.skipTest("Console-mode regression test")

        import FreeCADGui

        obj = self.Doc.addObject("App::FeatureTest", "HeadlessViewObject")
        self.assertIsNotNone(FreeCADGui)
        self.assertFalse(hasattr(FreeCADGui, "getDocument"))
        self.assertIsNone(obj.ViewObject)

    def testDuplicateLinks(self):
        obj = self.Doc.addObject("App::FeatureTest", "obj")
        grp = self.Doc.addObject("App::DocumentObjectGroup", "group")
        grp.Group = [obj, obj]
        self.Doc.removeObject(obj.Name)
        self.assertListEqual(grp.Group, [])

    def testPlacementList(self):
        obj = self.Doc.addObject("App::FeaturePython", "Label")
        obj.addProperty("App::PropertyPlacementList", "PlmList")
        plm = FreeCAD.Placement()
        plm.Base = (1, 2, 3)
        plm.Rotation = (0, 0, 1, 0)
        obj.PlmList = [plm]
        cpy = self.Doc.copyObject(obj)
        self.assertListEqual(obj.PlmList, cpy.PlmList)

    def testRawAxis(self):
        obj = self.Doc.addObject("App::FeaturePython", "Label")
        obj.addProperty("App::PropertyPlacement", "Plm")
        obj.addProperty("App::PropertyRotation", "Rot")
        obj.Plm.Rotation.Axis = (1, 2, 3)
        obj.Rot.Axis = (3, 2, 1)

        # saving and restoring
        SaveName = tempfile.gettempdir() + os.sep + "CreateTest.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument("CreateTest")
        self.Doc = FreeCAD.open(SaveName)
        obj = self.Doc.ActiveObject

        self.assertEqual(obj.Plm.Rotation.RawAxis.x, 1)
        self.assertEqual(obj.Plm.Rotation.RawAxis.y, 2)
        self.assertEqual(obj.Plm.Rotation.RawAxis.z, 3)

        self.assertEqual(obj.Rot.RawAxis.x, 3)
        self.assertEqual(obj.Rot.RawAxis.y, 2)
        self.assertEqual(obj.Rot.RawAxis.z, 1)

    def testAddRemove(self):
        L1 = self.Doc.addObject("App::FeatureTest", "Label_1")
        # must delete object
        self.Doc.removeObject(L1.Name)
        try:
            L1.Name
        except Exception:
            self.assertTrue(True)
        else:
            self.assertTrue(False)
        del L1

        # What do we expect here?
        self.Doc.openTransaction("AddRemove")
        L2 = self.Doc.addObject("App::FeatureTest", "Label_2")
        self.Doc.removeObject(L2.Name)
        self.Doc.commitTransaction()
        self.Doc.undo()
        try:
            L2.Name
        except Exception:
            self.assertTrue(True)
        else:
            self.assertTrue(False)
        del L2

    def testSubObjectOfNestedLCS(self):
        # https://github.com/FreeCAD/FreeCAD/issues/22618
        # The placement of an LCS must apply to its axes and planes.
        part = self.Doc.addObject("App::Part", "Part")
        part.Placement.Base = FreeCAD.Vector(100, 0, 0)
        lcs = self.Doc.addObject("App::LocalCoordinateSystem", "LCS")
        part.addObject(lcs)
        lcs.Placement = FreeCAD.Placement(
            FreeCAD.Vector(0, 50, 7), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        )
        self.Doc.recompute()
        axis = [o for o in lcs.OriginFeatures if o.Role == "X_Axis"][0]

        expected = part.Placement * lcs.Placement * axis.Placement
        res = part.getSubObject("{}.{}.".format(lcs.Name, axis.Name), retType=3)
        self.assertTrue(res.isSame(expected, 1e-9), str(res))

        expected = lcs.Placement * axis.Placement
        res = lcs.getSubObject(axis.Name + ".", retType=3)
        self.assertTrue(res.isSame(expected, 1e-9), str(res))
        res = lcs.getSubObject(axis.Name + ".", retType=3, transform=False)
        self.assertTrue(res.isSame(axis.Placement, 1e-9), str(res))

    def testSubObject(self):
        obj = self.Doc.addObject("App::Origin", "Origin")
        self.Doc.recompute()

        res = obj.getSubObject("X_Axis", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(1, 0, 0)).getAngle(FreeCAD.Vector(1, 0, 0)), 0.0
        )

        res = obj.getSubObject("Y_Axis", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(1, 0, 0)).getAngle(FreeCAD.Vector(0, 1, 0)), 0.0
        )

        res = obj.getSubObject("Z_Axis", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(1, 0, 0)).getAngle(FreeCAD.Vector(0, 0, 1)), 0.0
        )

        res = obj.getSubObject("XY_Plane", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(0, 0, 1)).getAngle(FreeCAD.Vector(0, 0, 1)), 0.0
        )

        res = obj.getSubObject("XZ_Plane", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(0, 0, 1)).getAngle(FreeCAD.Vector(0, -1, 0)), 0.0
        )

        res = obj.getSubObject("YZ_Plane", retType=2)
        self.assertEqual(
            res[1].multVec(FreeCAD.Vector(0, 0, 1)).getAngle(FreeCAD.Vector(1, 0, 0)), 0.0
        )

        res = obj.getSubObject("YZ_Plane", retType=3)
        self.assertEqual(
            res.multVec(FreeCAD.Vector(0, 0, 1)).getAngle(FreeCAD.Vector(1, 0, 0)), 0.0
        )

        res = obj.getSubObject("YZ_Plane", retType=4)
        self.assertEqual(
            res.multVec(FreeCAD.Vector(0, 0, 1)).getAngle(FreeCAD.Vector(1, 0, 0)), 0.0
        )

        self.assertEqual(
            obj.getSubObject(("XY_Plane", "YZ_Plane"), retType=4)[0],
            obj.getSubObject("XY_Plane", retType=4),
        )
        self.assertEqual(
            obj.getSubObject(("XY_Plane", "YZ_Plane"), retType=4)[1],
            obj.getSubObject("YZ_Plane", retType=4),
        )

        # Create a second origin object
        obj2 = self.Doc.addObject("App::Origin", "Origin2")
        self.Doc.recompute()

        # Use the names of the origin's out-list
        for i in obj2.OutList:
            self.assertEqual(obj2.getSubObject(i.Name, retType=1).Name, i.Name)
        # Add a '.' to the names
        for i in obj2.OutList:
            self.assertEqual(obj2.getSubObject(i.Name + ".", retType=1).Name, i.Name)

    def testExtensions(self):
        # we try to create a normal python object and add an extension to it
        obj = self.Doc.addObject("App::DocumentObject", "Extension_1")
        grp = self.Doc.addObject("App::DocumentObject", "Extension_2")
        # we should have all methods we need to handle extensions
        try:
            self.assertTrue(not grp.hasExtension("App::GroupExtensionPython"))
            grp.addExtension("App::GroupExtensionPython")
            self.assertTrue(grp.hasExtension("App::GroupExtension"))
            self.assertTrue(grp.hasExtension("App::GroupExtensionPython"))
            grp.addObject(obj)
            self.assertTrue(len(grp.Group) == 1)
            self.assertTrue(grp.Group[0] == obj)
        except Exception:
            self.assertTrue(False)

        # test if the method override works
        class SpecialGroup:
            def allowObject(self, ext, obj):
                return False

        callback = SpecialGroup()
        grp2 = self.Doc.addObject("App::FeaturePython", "Extension_3")
        grp2.addExtension("App::GroupExtensionPython")
        grp2.Proxy = callback

        try:
            self.assertTrue(grp2.hasExtension("App::GroupExtension"))
            grp2.addObject(obj)
            self.assertTrue(len(grp2.Group) == 0)
        except Exception:
            self.assertTrue(False)

        self.Doc.removeObject(grp.Name)
        self.Doc.removeObject(grp2.Name)
        self.Doc.removeObject(obj.Name)
        del obj
        del grp
        del grp2

    def testExtensionBug0002785(self):
        class MyExtension:
            def __init__(self, obj):
                obj.addExtension("App::GroupExtensionPython")

        obj = self.Doc.addObject("App::DocumentObject", "myObj")
        MyExtension(obj)
        self.assertTrue(obj.hasExtension("App::GroupExtension"))
        self.assertTrue(obj.hasExtension("App::GroupExtensionPython"))
        self.Doc.removeObject(obj.Name)
        del obj

    def testExtensionGroup(self):
        obj = self.Doc.addObject("App::DocumentObject", "Obj")
        grp = self.Doc.addObject("App::FeaturePython", "Extension_2")
        grp.addExtension("App::GroupExtensionPython")
        grp.Group = [obj]
        self.assertTrue(obj in grp.Group)

    def testExtensionBugViewProvider(self):
        class Layer:
            def __init__(self, obj):
                obj.addExtension("App::GroupExtensionPython")

        class LayerViewProvider:
            def __init__(self, obj):
                obj.addExtension("Gui::ViewProviderGroupExtensionPython")
                obj.Proxy = self

        obj = self.Doc.addObject("App::FeaturePython", "Layer")
        Layer(obj)
        self.assertTrue(obj.hasExtension("App::GroupExtension"))

        if FreeCAD.GuiUp:
            LayerViewProvider(obj.ViewObject)
            self.assertTrue(obj.ViewObject.hasExtension("Gui::ViewProviderGroupExtension"))
            self.assertTrue(obj.ViewObject.hasExtension("Gui::ViewProviderGroupExtensionPython"))

        self.Doc.removeObject(obj.Name)
        del obj

    def testHasSelection(self):
        if FreeCAD.GuiUp:
            import FreeCADGui

            self.assertFalse(FreeCADGui.Selection.hasSelection("", 1))

    def testPropertyLink_Issue2902Part1(self):
        o1 = self.Doc.addObject("App::FeatureTest", "test1")
        o2 = self.Doc.addObject("App::FeatureTest", "test2")
        o3 = self.Doc.addObject("App::FeatureTest", "test3")

        o1.Link = o2
        self.assertEqual(o1.Link, o2)
        o1.Link = o3
        self.assertEqual(o1.Link, o3)
        o2.Placement = FreeCAD.Placement()
        self.assertEqual(o1.Link, o3)

    def testProp_NonePropertyLink(self):
        obj1 = self.Doc.addObject("App::FeaturePython", "Obj1")
        obj2 = self.Doc.addObject("App::FeaturePython", "Obj2")
        obj1.addProperty(
            "App::PropertyLink",
            "Link",
            "Base",
            "Link to another feature",
            FreeCAD.PropertyType.Prop_None,
            False,
            False,
        )
        obj1.Link = obj2
        self.assertEqual(obj1.MustExecute, True)

    def testNullLinkSubPythonRoundTrip(self):
        obj = self.Doc.addObject("App::FeaturePython", "Reference")
        obj.addProperty("App::PropertyLinkSub", "Axis")
        self.assertIsNone(obj.Axis)
        for subnames in ("X_Axis", ["Y_Axis"], ("Z_Axis", "X_Axis")):
            with self.subTest(subnames=subnames):
                obj.Axis = (None, subnames)
                expected = [subnames] if isinstance(subnames, str) else list(subnames)
                self.assertEqual(obj.Axis, (None, expected))
        with self.assertRaises(TypeError):
            obj.Axis = (None, [1])
        with self.assertRaises(TypeError):
            obj.Axis = (1, ["X_Axis"])
        obj.Axis = None
        self.assertIsNone(obj.Axis)
        obj.Axis = (None, [])
        self.assertIsNone(obj.Axis)

    def testNullLinkSubSaveRestore(self):
        obj = self.Doc.addObject("App::FeaturePython", "Reference")
        obj.addProperty("App::PropertyLinkSub", "Axis")
        obj.Axis = (None, ["Y_Axis"])
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "CreateTest.FCStd")
            self.Doc.saveAs(filename)
            FreeCAD.closeDocument(self.Doc.Name)
            self.Doc = FreeCAD.openDocument(filename)
            self.assertEqual(self.Doc.Reference.Axis, (None, ["Y_Axis"]))

    def testProp_OutputPropertyLink(self):
        obj1 = self.Doc.addObject("App::FeaturePython", "Obj1")
        obj2 = self.Doc.addObject("App::FeaturePython", "Obj2")
        obj1.addProperty(
            "App::PropertyLink",
            "Link",
            "Base",
            "Link to another feature",
            FreeCAD.PropertyType.Prop_Output,
            False,
            False,
        )
        obj1.Link = obj2
        self.assertEqual(obj1.MustExecute, False)

    def testAttributeOfDynamicProperty(self):
        obj = self.Doc.addObject("App::FeaturePython", "Obj")
        # Prop_NoPersist is the enum with the highest value
        max_value = FreeCAD.PropertyType.Prop_NoPersist
        list_of_types = []
        for i in range(0, max_value + 1):
            obj.addProperty("App::PropertyString", "String" + str(i), "", "", i)
            list_of_types.append(obj.getTypeOfProperty("String" + str(i)))

        # saving and restoring
        SaveName = tempfile.gettempdir() + os.sep + "CreateTest.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument("CreateTest")
        self.Doc = FreeCAD.open(SaveName)

        obj = self.Doc.ActiveObject
        for i in range(0, max_value):
            types = obj.getTypeOfProperty("String" + str(i))
            self.assertEqual(list_of_types[i], types)

        # A property with flag Prop_NoPersist won't be saved to the file
        with self.assertRaises(AttributeError):
            obj.getTypeOfProperty("String" + str(max_value))

    def testNotification_Issue2902Part2(self):
        o = self.Doc.addObject("App::FeatureTest", "test")

        plm = o.Placement
        o.Placement = FreeCAD.Placement()
        plm.Base.x = 5
        self.assertEqual(o.Placement.Base.x, 0)
        o.Placement.Base.x = 5
        self.assertEqual(o.Placement.Base.x, 5)

    def testNotification_Issue2996(self):
        if not FreeCAD.GuiUp:
            return

        # works only if Gui is shown
        class ViewProvider:
            def __init__(self, vobj):
                vobj.Proxy = self

            def attach(self, vobj):
                self.ViewObject = vobj
                self.Object = vobj.Object

            def claimChildren(self):
                children = [self.Object.Link]
                return children

        obj = self.Doc.addObject("App::FeaturePython", "Sketch")
        obj.addProperty("App::PropertyLink", "Link")
        ViewProvider(obj.ViewObject)

        ext = self.Doc.addObject("App::FeatureTest", "Extrude")
        ext.Link = obj

        sli = self.Doc.addObject("App::FeaturePython", "Slice")
        sli.addProperty("App::PropertyLink", "Link").Link = ext
        ViewProvider(sli.ViewObject)

        com = self.Doc.addObject("App::FeaturePython", "CompoundFilter")
        com.addProperty("App::PropertyLink", "Link").Link = sli
        ViewProvider(com.ViewObject)

        ext.Label = "test"

        self.assertEqual(ext.Link, obj)
        self.assertNotEqual(ext.Link, sli)

    def testIssue4823(self):
        # https://forum.freecad.org/viewtopic.php?f=3&t=52775
        # The issue was only visible in GUI mode and it crashed in the tree view
        obj = self.Doc.addObject("App::Origin")
        self.Doc.removeObject(obj.Name)

    def testSamePropertyOfLinkAndLinkedObject(self):
        # See also https://github.com/FreeCAD/FreeCAD/pull/6787
        test = self.Doc.addObject("App::FeaturePython", "Python")
        link = self.Doc.addObject("App::Link", "Link")
        test.addProperty("App::PropertyFloat", "Test")
        link.addProperty("App::PropertyFloat", "Test")
        link.LinkedObject = test
        # saving and restoring
        SaveName = tempfile.gettempdir() + os.sep + "CreateTest.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument("CreateTest")
        self.Doc = FreeCAD.open(SaveName)
        self.assertIn("Test", self.Doc.Python.PropertiesList)
        self.assertIn("Test", self.Doc.Link.PropertiesList)

    def testRelabelLinkReferencingItself(self):
        # A link that references itself through another link property is in its own
        # in-list. Relabeling it (and so restoring its Label from a file) used to notify
        # the link that its "parent" was relabeled, the link relabeled itself again and
        # FreeCAD crashed with a stack overflow.
        link = self.Doc.addObject("App::Link", "Link")
        link.addProperty("App::PropertyLinkList", "Refs")
        link.Refs = [link]
        link.Label = "Renamed"
        self.assertEqual(link.Label, "Renamed")

        doc = self.saveAndRestore()
        # The link instance-label migration may append " <n>" on restore; only the
        # base label matters here.
        self.assertTrue(doc.Link.Label.startswith("Renamed"))
        self.assertEqual(doc.Link.Refs, [doc.Link])

    def testUnencodableStringPropertyValues(self):
        # A str with an unpaired surrogate cannot be converted to UTF-8; the
        # nullptr from PyUnicode_AsUTF8() was assigned to std::string (crash).
        bad = "\ud800"
        obj = self.Doc.addObject("App::FeaturePython", "Strings")
        for typ, name, value in (
            ("App::PropertyString", "S", bad),
            ("App::PropertyStringList", "SL", ["ok", bad]),
            ("App::PropertyMap", "MK", {bad: "v"}),
            ("App::PropertyMap", "MV", {"k": bad}),
            ("App::PropertyPath", "P", bad),
            ("App::PropertyUUID", "U", bad),
            ("App::PropertyEnumeration", "E", bad),
            ("App::PropertyBoolList", "BL", bad),
            ("App::PropertyLength", "L", bad),
            ("App::PropertyFileIncluded", "FI", bad),
            ("App::PropertyFileIncluded", "FT", (bad, "name")),
        ):
            obj.addProperty(typ, name)
            with self.assertRaises(UnicodeError, msg=typ):
                setattr(obj, name, value)
        obj.SL = ["ok", "é"]
        self.assertEqual(obj.SL, ["ok", "é"])

    def testPropertyMapRejectsSequences(self):
        # A list or str passes PyMapping_Check() but has no keys(): assigning one
        # used to clear the map and return with the Python error still set
        # (SystemError).
        obj = self.Doc.addObject("App::FeaturePython", "MapHolder")
        obj.addProperty("App::PropertyMap", "Map")
        for value in (["a"], "abc", b"xy", (1, 2), range(3)):
            obj.Map = {"keep": "me"}
            with self.assertRaises((TypeError, AttributeError), msg=repr(value)):
                obj.Map = value
            self.assertEqual(obj.Map, {"keep": "me"}, msg=repr(value))
        obj.Map = {"a": "b"}
        self.assertEqual(obj.Map, {"a": "b"})

    def testEnumerationItemsWithBadIndex(self):
        # Assigning (items, index) with an index out of range raised ValueError
        # only after the new items had been set.
        obj = self.Doc.addObject("App::FeaturePython", "EnumHolder")
        obj.addProperty("App::PropertyEnumeration", "Choice")
        obj.Choice = ["a", "b"]
        obj.Choice = "b"
        with self.assertRaises(ValueError):
            obj.Choice = (["p", "q"], 5)
        self.assertEqual(obj.getEnumerationsOfProperty("Choice"), ["a", "b"])
        self.assertEqual(obj.Choice, "b")
        obj.Choice = (["p", "q", "r"], 2)
        self.assertEqual(obj.getEnumerationsOfProperty("Choice"), ["p", "q", "r"])
        self.assertEqual(obj.Choice, "r")

    def testEnumerationItemByNameWithIndexOutOfRange(self):
        # An expression can leave the index of an enumeration out of range; an
        # item could then no longer be selected by name ("not part of the enumeration").
        obj = self.Doc.addObject("App::FeaturePython", "EnumIndex")
        obj.addProperty("App::PropertyEnumeration", "Mode")
        obj.Mode = ["a", "b", "c"]
        obj.setExpression("Mode", "5")
        self.Doc.recompute()
        obj.setExpression("Mode", None)
        obj.Mode = "b"
        self.assertEqual(obj.Mode, "b")
        with self.assertRaises(ValueError):
            obj.Mode = "z"

    def testExpressionPathWithComputedIndex(self):
        # A non-literal index such as [-1] is not part of an expression path; it was
        # dropped, so the expression was bound to the whole list and replaced it.
        obj = self.Doc.addObject("App::FeaturePython", "ListHolder")
        obj.addProperty("App::PropertyFloatList", "Values")
        obj.Values = [1.0, 2.0, 3.0]
        for path in (".Values[-1]", ".Values[1 + 1]"):
            with self.assertRaises(RuntimeError, msg=path):
                obj.setExpression(path, "7")
            with self.assertRaises(RuntimeError, msg=path):
                obj.clearExpression(path)
        self.assertEqual(obj.ExpressionEngine, [])
        self.Doc.recompute()
        self.assertEqual(obj.Values, [1.0, 2.0, 3.0])
        # the same index still works inside an expression
        self.assertEqual(obj.evalExpression("Values[-1]"), 3.0)

    def testUnencodableStringArguments(self):
        # Same as testUnencodableStringPropertyValues for method arguments.
        bad = "\ud800"
        obj = self.Doc.addObject("App::FeatureTest", "Args")
        link = self.Doc.addObject("App::Link", "ArgsLink")
        with self.assertRaises(UnicodeError):
            obj.setExpression("Integer", bad)
        with self.assertRaises(UnicodeError):
            obj.getSubObject(bad)
        with self.assertRaises(UnicodeError):
            obj.getSubObject([bad])
        with self.assertRaises(UnicodeError):
            self.Doc.openTransaction(bad)
        self.Doc.abortTransaction()
        with self.assertRaises(UnicodeError):
            self.Doc.getTempFileName(bad)
        with self.assertRaises(UnicodeError):
            link.configLinkProperty(bad)
        with self.assertRaises(UnicodeError):
            link.configLinkProperty(LinkedObject=bad)
        with self.assertRaises(UnicodeError):
            FreeCAD.setLogLevel("Document", bad)

    def testUnencodableAttributeNames(self):
        # getattr()/setattr() with a name that cannot be converted to UTF-8 passed
        # the nullptr from PyUnicode_AsUTF8() on as the attribute name (crash).
        bad = "\ud800"
        obj = self.Doc.addObject("App::FeaturePython", "AttrNames")
        for target in (obj, self.Doc, FreeCAD.Vector(1, 2, 3), FreeCAD.Placement()):
            with self.assertRaises(UnicodeError, msg=type(target).__name__):
                getattr(target, bad)
            with self.assertRaises(UnicodeError, msg=type(target).__name__):
                setattr(target, bad, 1)
        self.assertFalse(hasattr(obj, "NoSuchAttribute"))
        self.assertEqual(getattr(FreeCAD.Vector(1, 2, 3), "y"), 2)

    def testPropertyStatusOutOfRangeNumber(self):
        # a number that does not fit a C long became -1 (clear status bit 1,
        # Immutable) and the call returned with an OverflowError still set
        obj = self.Doc.addObject("App::FeaturePython", "StatusNumbers")
        obj.addProperty("App::PropertyFloat", "Flags")
        obj.setPropertyStatus("Flags", "Immutable")
        before = obj.getPropertyStatus("Flags")
        self.assertIn("Immutable", before)
        for value in (2**70, -(2**70), 2**40 + 1, 2**63, -(2**63), 32, -32, 0):
            with self.subTest(value=value):
                with self.assertRaises((OverflowError, ValueError)):
                    obj.setPropertyStatus("Flags", value)
                self.assertEqual(obj.getPropertyStatus("Flags"), before)
            obj.setPropertyStatus("Flags", "Immutable")
        obj.setPropertyStatus("Flags", -1)
        self.assertNotIn("Immutable", obj.getPropertyStatus("Flags"))
        obj.setPropertyStatus("Flags", [1])
        self.assertIn("Immutable", obj.getPropertyStatus("Flags"))

    def testPropertyOutOfRangeIntegerItems(self):
        # ints that do not fit a C long (or a negative packed colour) were stored
        # as garbage and the call returned with an OverflowError still set
        obj = self.Doc.addObject("App::FeaturePython", "RangeNumbers")
        obj.addProperty("App::PropertyColor", "Color")
        obj.addProperty("App::PropertyColorList", "Colors")
        obj.addProperty("App::PropertyIntegerSet", "Set")
        obj.addProperty("App::PropertyBoolList", "Bools")
        obj.addProperty("App::PropertyFloatList", "Floats")
        obj.Color = (255, 0, 0)
        before = obj.Color
        for value in ((2**70, 0, 0), (0, 0, 2**70), (0, 0, 0, -(2**70)), -1, 2**70):
            with self.subTest(value=value):
                with self.assertRaises(OverflowError):
                    obj.Color = value
                self.assertEqual(obj.Color, before)
        with self.assertRaises(OverflowError):
            obj.Colors = [(0, 0, 0), (2**70, 0, 0)]
        with self.assertRaises(OverflowError):
            obj.Set = [1, 2**70]
        with self.assertRaises(OverflowError):
            obj.Set = 2**70
        with self.assertRaises(OverflowError):
            obj.Bools = [2**70]
        with self.assertRaises(OverflowError):
            obj.Floats = [10**400]
        # in range values are unchanged
        obj.Color = (0, 255, 0)
        self.assertEqual(obj.Color[:3], (0.0, 1.0, 0.0))
        obj.Color = 0x0000FFFF
        self.assertEqual(obj.Color[:3], (0.0, 0.0, 1.0))
        obj.Set = [3, 1]
        self.assertEqual(set(obj.Set), {1, 3})
        obj.Bools = [0, 2]
        self.assertEqual(obj.Bools, (False, True))
        obj.Floats = [2, 10**12]
        self.assertEqual(obj.Floats, [2.0, 1e12])

    def testMaterialColorOutOfRangeInteger(self):
        # App.Material colours: same unchecked int conversion as PropertyColor
        mat = FreeCAD.Material()
        mat.DiffuseColor = (255, 0, 0)
        before = mat.DiffuseColor
        for value in ((2**70, 0, 0), (0, 0, 0, 2**70), -1, 2**70):
            with self.subTest(value=value):
                with self.assertRaises(OverflowError):
                    mat.DiffuseColor = value
                self.assertEqual(mat.DiffuseColor, before)
        with self.assertRaises(OverflowError):
            FreeCAD.Material(AmbientColor=(2**70, 0, 0))
        mat.SpecularColor = (0, 255, 0)
        self.assertEqual(mat.SpecularColor[:3], (0.0, 1.0, 0.0))

    def testLinksLinkingEachOther(self):
        # Two links linking each other: setting the second link's LinkedObject rebuilt
        # its label from the other link, which rebuilt its own label in turn, and so
        # on until FreeCAD crashed with a stack overflow.
        a = self.Doc.addObject("App::Link", "A")
        b = self.Doc.addObject("App::Link", "B")
        a.LinkedObject = b
        b.LinkedObject = a
        self.assertEqual(b.LinkedObject, a)
        a.Label = "Renamed"
        self.Doc.recompute()
        doc = self.saveAndRestore()
        self.assertEqual(doc.B.LinkedObject, doc.A)

    def testLinkPropertyInfoByIndexAndName(self):
        # The index and name overloads ran after a failed PyArg_ParseTuple() without
        # clearing its error, so a valid call raised SystemError.
        link = self.Doc.addObject("App::Link", "Link")
        infos = link.getLinkPropertyInfo()
        self.assertEqual(link.getLinkPropertyInfo(0), infos[0])
        self.assertEqual(link.getLinkPropertyInfo(infos[0][0]), infos[0][1:])
        with self.assertRaises(ValueError):
            link.getLinkPropertyInfo(len(infos))
        with self.assertRaises(ValueError):
            link.getLinkPropertyInfo("NoSuchProperty")

    def testNoProxy(self):
        test = self.Doc.addObject("App::DocumentObject", "Object")
        test.addProperty("App::PropertyPythonObject", "Dictionary")
        test.Dictionary = {"Stored data": [3, 5, 7]}

        doc = self.saveAndRestore()
        obj = doc.Object

        self.assertEqual(obj.Dictionary, {"Stored data": [3, 5, 7]})

    def testWithProxy(self):
        test = self.Doc.addObject("App::FeaturePython", "Python")
        proxy = Proxy(test)
        proxy.Dictionary["Stored data"] = [3, 5, 7]

        doc = self.saveAndRestore()
        obj = doc.Python.Proxy

        self.assertEqual(obj.Dictionary, {"Stored data": [3, 5, 7]})

    def testContent(self):
        test = self.Doc.addObject("App::FeaturePython", "Python")
        types = Base.TypeId.getAllDerivedFrom("App::Property")
        for type in types:
            try:
                test.addProperty(type.Name, type.Name.replace(":", "_"))
                print("Add property type: {}".format(type.Name))
            except Exception as e:
                pass
        root = ET.fromstring(test.Content)
        self.assertEqual(root.tag, "Properties")

    def testValidateXml(self):
        self.Doc.openTransaction("Add")
        obj = self.Doc.addObject("App::FeatureTest", "Label")
        obj.Label = "abc\x01ef"
        TempPath = tempfile.gettempdir()
        SaveName = TempPath + os.sep + "CreateTest.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument(self.Doc.Name)
        self.Doc = FreeCAD.open(SaveName)
        self.assertEqual(self.Doc.ActiveObject.Label, "abc_ef")

    def testExpressionOnListItem(self):
        # An expression bound to one item of a list (".Values[1]") or to a value inside
        # an item (".Points[1].y") was evaluated but set on a temporary copy of the list.
        self.Doc.UndoMode = 1
        obj = self.Doc.addObject("App::FeaturePython", "ListItems")
        obj.addProperty("App::PropertyFloat", "Source")
        obj.addProperty("App::PropertyFloatList", "Values")
        obj.addProperty("App::PropertyIntegerList", "Counts")
        obj.addProperty("App::PropertyVectorList", "Points")
        obj.addProperty("App::PropertyPlacementList", "Placements")
        obj.Source = 7.5
        obj.Values = [1.0, 2.0, 3.0]
        obj.Counts = [1, 2, 3]
        obj.Points = [FreeCAD.Vector(1, 2, 3), FreeCAD.Vector(4, 5, 6)]
        obj.Placements = [FreeCAD.Placement(), FreeCAD.Placement()]
        obj.setExpression(".Values[1]", "Source * 2")
        obj.setExpression(".Counts[0]", "4")
        obj.setExpression(".Points[1].y", "Source")
        obj.setExpression(".Placements[1].Base.z", "Source + 1")
        self.Doc.recompute()

        def check(source):
            self.assertEqual(obj.Values, [1.0, source * 2, 3.0])
            self.assertEqual(obj.Counts, [4, 2, 3])
            self.assertEqual(obj.Points, [FreeCAD.Vector(1, 2, 3), FreeCAD.Vector(4, source, 6)])
            self.assertEqual(obj.Placements[0].Base, FreeCAD.Vector(0, 0, 0))
            self.assertEqual(obj.Placements[1].Base, FreeCAD.Vector(0, 0, source + 1))

        check(7.5)
        self.assertEqual(obj.evalExpression("Values[1]"), 15.0)

        # the items follow their expression, and undo restores them
        self.Doc.openTransaction("Change source")
        obj.Source = 1.5
        self.Doc.recompute()
        self.Doc.commitTransaction()
        check(1.5)
        self.Doc.undo()
        check(7.5)

        # the bindings and the values survive save and reload
        obj = self.saveAndRestore().getObject("ListItems")
        check(7.5)
        obj.Source = 2.5
        self.Doc.recompute()
        check(2.5)
        paths = [path for path, _ in obj.ExpressionEngine]
        self.assertEqual(
            sorted(paths), [".Counts[0]", ".Placements[1].Base.z", ".Points[1].y", ".Values[1]"]
        )

        # an index out of range is refused, or is an error of the binding when the list shrinks
        with self.assertRaises(IndexError):
            obj.setExpression(".Values[3]", "9")
        obj.Values = [1.0]
        self.Doc.recompute()
        self.assertFalse(obj.isValid())
        self.assertIn("out of range", obj.getStatusString())
        self.assertEqual(obj.Values, [1.0])

    def testExpressionOnListItemTakesNumbersLikeScalars(self):
        # A list item takes the number of its expression as the scalar property of its type
        # does: a quantity (e.g. a length) gives its value, an integer item rounds a float.
        obj = self.Doc.addObject("App::FeaturePython", "ListItemNumbers")
        obj.addProperty("App::PropertyLength", "Size")
        obj.addProperty("App::PropertyFloat", "Ratio")
        obj.addProperty("App::PropertyFloatList", "Values")
        obj.addProperty("App::PropertyIntegerList", "Counts")
        obj.Size = 12.5
        obj.Ratio = 2.6
        obj.Values = [1.0, 2.0, 3.0]
        obj.Counts = [1, 2, 3]
        obj.setExpression(".Values[0]", "Size")
        obj.setExpression(".Values[2]", "Ratio * 2")
        obj.setExpression(".Counts[0]", "Ratio * 2")
        obj.setExpression(".Counts[1]", "Size")
        obj.setExpression(".Counts[2]", "7")
        self.Doc.recompute()
        self.assertTrue(obj.isValid(), obj.getStatusString())
        self.assertEqual(obj.Values, [12.5, 2.0, 5.2])
        self.assertEqual(obj.Counts, [5, 13, 7])

    def testGetLicenses(self):
        """FreeCAD.getLicenses() lists the licenses in the order of the
        prefLicenseType preference that new documents use."""
        licenses = FreeCAD.getLicenses()
        self.assertGreater(len(licenses), 0)
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        storedType = "prefLicenseType" in param.GetInts()
        storedUrl = "prefLicenseUrl" in param.GetStrings()
        oldType = param.GetInt("prefLicenseType", 0)
        oldUrl = param.GetString("prefLicenseUrl", "")
        try:
            param.RemString("prefLicenseUrl")
            for index, (identifier, name, url) in enumerate(licenses):
                self.assertTrue(identifier and name and url)
                param.SetInt("prefLicenseType", index)
                doc = FreeCAD.newDocument("LicenseTest")
                try:
                    self.assertEqual(doc.License, name)
                    self.assertEqual(doc.LicenseURL, url)
                finally:
                    FreeCAD.closeDocument(doc.Name)
        finally:
            if storedType:
                param.SetInt("prefLicenseType", oldType)
            else:
                param.RemInt("prefLicenseType")
            if storedUrl:
                param.SetString("prefLicenseUrl", oldUrl)
            else:
                param.RemString("prefLicenseUrl")

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("CreateTest")


class DocumentDuplicateLabelCases(unittest.TestCase):
    """Tests for the DuplicateLabels document preference (issue #25519)."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("DuplicateLabelTest")
        self.Params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        self.OldDuplicateLabels = self.Params.GetBool("DuplicateLabels", False)

    def tearDown(self):
        self.Params.SetBool("DuplicateLabels", self.OldDuplicateLabels)
        FreeCAD.closeDocument("DuplicateLabelTest")

    def testNewObjectKeepsRequestedLabel(self):
        # With duplicate labels allowed, the label of a new object must be the
        # requested name, not the numbered internal name generated from it
        self.Params.SetBool("DuplicateLabels", True)
        first = self.Doc.addObject("App::FeatureTest", "Label")
        second = self.Doc.addObject("App::FeatureTest", "Label")
        self.assertEqual(first.Name, "Label")
        self.assertEqual(second.Name, "Label001")
        self.assertEqual(first.Label, "Label")
        self.assertEqual(second.Label, "Label")

    def testNewObjectLabelIsSanitized(self):
        # The requested name is sanitized the same way as the internal name
        self.Params.SetBool("DuplicateLabels", True)
        first = self.Doc.addObject("App::FeatureTest", "My Label")
        second = self.Doc.addObject("App::FeatureTest", "My Label")
        self.assertEqual(first.Name, "My_Label")
        self.assertEqual(second.Name, "My_Label001")
        self.assertEqual(first.Label, "My_Label")
        self.assertEqual(second.Label, "My_Label")

    def testNewObjectWithoutNameUsesInternalName(self):
        # Without a requested name the internal name is the only choice
        self.Params.SetBool("DuplicateLabels", True)
        first = self.Doc.addObject("App::FeatureTest")
        second = self.Doc.addObject("App::FeatureTest")
        self.assertEqual(first.Label, first.Name)
        self.assertEqual(second.Label, second.Name)

    def testNewObjectGetsUniqueLabelWhenDisabled(self):
        # With duplicate labels disallowed (default), the label of the second
        # object is made unique
        self.Params.SetBool("DuplicateLabels", False)
        first = self.Doc.addObject("App::FeatureTest", "Label")
        second = self.Doc.addObject("App::FeatureTest", "Label")
        self.assertEqual(first.Label, "Label")
        self.assertEqual(second.Label, "Label001")

    def testCopyObjectPreservesDuplicateLabel(self):
        # With duplicate labels allowed, copying an object must not rename the
        # label of the copy
        self.Params.SetBool("DuplicateLabels", True)
        obj = self.Doc.addObject("App::FeatureTest", "Label")
        copy = self.Doc.copyObject(obj)
        self.assertEqual(copy.Label, "Label")

    def testCopyObjectGetsUniqueLabelWhenDisabled(self):
        # With duplicate labels disallowed (default), the copy gets a unique label
        self.Params.SetBool("DuplicateLabels", False)
        obj = self.Doc.addObject("App::FeatureTest", "Label")
        copy = self.Doc.copyObject(obj)
        self.assertEqual(copy.Label, "Label001")

    def testEmptyLabelResetsToName(self):
        # An empty label is replaced by the object name (issue #26323)
        for duplicates in (False, True):
            with self.subTest(DuplicateLabels=duplicates):
                self.Params.SetBool("DuplicateLabels", duplicates)
                obj = self.Doc.addObject("App::FeatureTest", "Feature")
                obj.Label = "Renamed"
                obj.Label = ""
                self.assertEqual(obj.Label, obj.Name)
                # Clearing a label already equal to the name keeps it unchanged
                obj.Label = ""
                self.assertEqual(obj.Label, obj.Name)

    def testEmptyLabelResetsToUniqueNameWhenDisabled(self):
        # When the name is already used as another object's label, the reset
        # label is made unique if duplicate labels are disallowed
        self.Params.SetBool("DuplicateLabels", False)
        obj = self.Doc.addObject("App::FeatureTest", "Feature")
        other = self.Doc.addObject("App::FeatureTest", "Other")
        obj.Label = "Renamed"
        other.Label = obj.Name
        obj.Label = ""
        self.assertNotEqual(obj.Label, "")
        self.assertNotEqual(obj.Label, other.Label)
        self.assertTrue(obj.Label.startswith(obj.Name))


class DocumentLinkLabelCases(unittest.TestCase):
    """Link instance labels when the link loses its linked object."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("LinkLabelTest")

    def tearDown(self):
        FreeCAD.closeDocument("LinkLabelTest")

    def testUnlinkKeepsLabel(self):
        # Without a linked object getLinkedObject() returns the link itself, the
        # label must not be rebuilt from it ("Cube <1>" -> "Cube <1> <1>")
        cube = self.Doc.addObject("App::FeatureTest", "Cube")
        link = self.Doc.addObject("App::Link", "Link")
        link.setLink(cube)
        label = link.Label
        link.LinkedObject = None
        self.assertEqual(link.Label, label)
        link.setLink(cube)
        self.Doc.removeObject("Cube")
        self.assertEqual(link.Label, label)

    def testUnlinkLinkInDependencyCycle(self):
        # A link that is in its own InList (here through another link property)
        # recursed through onParentLabelChanged() until the stack overflowed
        # when its linked object was cleared
        cube = self.Doc.addObject("App::FeatureTest", "Cube")
        link = self.Doc.addObject("App::Link", "Link")
        link.setLink(cube)
        link.addProperty("App::PropertyLink", "Other")
        link.Other = link
        label = link.Label
        link.LinkedObject = None
        self.assertIsNone(link.LinkedObject)
        self.assertEqual(link.Label, label)

    def testUndoTargetDeletionKeepsLabel(self):
        # Undoing the deletion of the linked object restores the link's LinkedObject.
        # The label must not be rebuilt from the linked object during undo/redo
        # ("Custom" became "Child <1>").
        self.Doc.UndoMode = 1
        child = self.Doc.addObject("App::FeatureTest", "Child")
        link = self.Doc.addObject("App::Link", "Link")
        link.setLink(child)
        link.Label = "Custom"
        self.Doc.clearUndos()
        self.Doc.openTransaction("Delete child")
        self.Doc.removeObject("Child")
        self.Doc.commitTransaction()
        for _ in range(2):
            self.Doc.undo()
            self.assertEqual(link.LinkedObject, self.Doc.getObject("Child"))
            self.assertEqual(link.Label, "Custom")
            self.Doc.redo()
            self.assertIsNone(link.LinkedObject)
            self.assertEqual(link.Label, "Custom")

    def testUndoTargetRelabelRestoresInstanceLabel(self):
        # Relabeling the linked object updates the instance label; undo and redo
        # restore both labels
        self.Doc.UndoMode = 1
        child = self.Doc.addObject("App::FeatureTest", "Child")
        link = self.Doc.addObject("App::Link", "Link")
        link.setLink(child)
        label = link.Label
        self.assertEqual(label, "Child <1>")
        self.Doc.clearUndos()
        self.Doc.openTransaction("Relabel child")
        child.Label = "Renamed"
        self.Doc.commitTransaction()
        self.assertEqual(link.Label, "Renamed <1>")
        self.Doc.undo()
        self.assertEqual(child.Label, "Child")
        self.assertEqual(link.Label, label)
        self.Doc.redo()
        self.assertEqual(child.Label, "Renamed")
        self.assertEqual(link.Label, "Renamed <1>")

    def testRestoreMigratedLabelKeepsLabelReferences(self):
        # A link label that is not "<linked label> <instance>" (custom label, or a file
        # from FreeCAD) is migrated when the document is restored. The expressions that
        # refer to the link by its label must follow the new label.
        child = self.Doc.addObject("App::VarSet", "Child")
        child.addProperty("App::PropertyLength", "Outer")
        child.Outer = 7
        link = self.Doc.addObject("App::Link", "Link")
        link.setLink(child)
        link.Label = "Custom"
        user = self.Doc.addObject("App::VarSet", "User")
        user.addProperty("App::PropertyLength", "Length")
        user.setExpression("Length", "<<Custom>>.Outer")
        self.Doc.recompute()
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "LinkLabelTest.FCStd")
            self.Doc.saveAs(filename)
            FreeCAD.closeDocument(self.Doc.Name)
            self.Doc = FreeCAD.openDocument(filename)
            link = self.Doc.getObject("Link")
            user = self.Doc.getObject("User")
            self.assertEqual(link.Label, "Child <Custom>")
            self.assertEqual(user.ExpressionEngine, [("Length", "<<Child <Custom\\>>>.Outer")])
            self.Doc.getObject("Child").Outer = 9
            self.Doc.recompute()
            self.assertNotIn("Invalid", user.State)
            self.assertEqual(user.Length, 9)
            # The new label contains '>', which is escaped in the saved expression
            self.Doc.save()
            FreeCAD.closeDocument(self.Doc.Name)
            self.Doc = FreeCAD.openDocument(filename)
            user = self.Doc.getObject("User")
            self.assertEqual(self.Doc.getObject("Link").Label, "Child <Custom>")
            self.assertEqual(user.ExpressionEngine, [("Length", "<<Child <Custom\\>>>.Outer")])
            self.Doc.getObject("Child").Outer = 11
            self.Doc.recompute()
            self.assertNotIn("Invalid", user.State)
            self.assertEqual(user.Length, 11)

    def testRestoreMigratedExternalLinkLabelKeepsLabelReferences(self):
        # A link to an object of another document gets its linked object only when that
        # document is loaded, while the link's document is still restoring. The label
        # migrated then must also update the expressions referring to the link by label,
        # instead of leaving them broken (https://github.com/AstoCAD/FreeCAD/issues/131).
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "LinkLabelTest.FCStd")
            resname = os.path.join(directory, "LinkLabelTestRes.FCStd")
            res = FreeCAD.newDocument("LinkLabelTestRes")
            try:
                varset = res.addObject("App::VarSet", "VarSet")
                varset.addProperty("App::PropertyLength", "Outer")
                varset.Outer = 7
                res.saveAs(resname)
                self.Doc.saveAs(filename)
                link = self.Doc.addObject("App::Link", "Link")
                link.setLink(varset)
                # A link labeled like its linked object, as in a file from FreeCAD
                link.Label = "VarSet"
                user = self.Doc.addObject("App::VarSet", "User")
                user.addProperty("App::PropertyLength", "Length")
                user.setExpression("Length", "<<VarSet>>.Outer")
                self.Doc.recompute()
                self.assertEqual(user.Length, 7)
                res.save()
                self.Doc.save()
                FreeCAD.closeDocument(self.Doc.Name)
                FreeCAD.closeDocument(res.Name)
                self.Doc = FreeCAD.openDocument(filename)
                res = FreeCAD.getDocument("LinkLabelTestRes")
                user = self.Doc.getObject("User")
                self.assertEqual(self.Doc.getObject("Link").Label, "VarSet <1>")
                self.assertEqual(user.ExpressionEngine, [("Length", "<<VarSet <1\\>>>.Outer")])
                res.getObject("VarSet").Outer = 9
                user.touch()
                self.Doc.recompute()
                self.assertNotIn("Invalid", user.State)
                self.assertEqual(user.Length, 9)
            finally:
                if "LinkLabelTestRes" in FreeCAD.listDocuments():
                    FreeCAD.closeDocument("LinkLabelTestRes")

    def testLabelWithGreaterThanInExpression(self):
        # quote() escapes '>' in a <<label>>, the parser must read it back
        child = self.Doc.addObject("App::VarSet", "Child")
        child.addProperty("App::PropertyLength", "Outer")
        child.Outer = 7
        child.Label = "Child <1>"
        user = self.Doc.addObject("App::VarSet", "User")
        user.addProperty("App::PropertyLength", "Length")
        user.setExpression("Length", "<<Child <1\\>>>.Outer")
        self.Doc.recompute()
        self.assertEqual(user.ExpressionEngine, [("Length", "<<Child <1\\>>>.Outer")])
        self.assertNotIn("Invalid", user.State)
        self.assertEqual(user.Length, 7)

    def testDuplicateInstanceLabelTakesNextInstanceNumber(self):
        # A copied link, or any label set to an instance label already in use, takes the next
        # instance number ("Cube <2>"), not a padded one ("Cube <001>")
        params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        oldDuplicateLabels = params.GetBool("DuplicateLabels", False)
        params.SetBool("DuplicateLabels", False)
        try:
            cube = self.Doc.addObject("App::FeatureTest", "Cube")
            link = self.Doc.addObject("App::Link", "Link")
            link.setLink(cube)
            self.assertEqual(link.Label, "Cube <1>")
            copy = self.Doc.copyObject(link)
            self.assertEqual(copy.Label, "Cube <2>")
            other = self.Doc.addObject("App::FeatureTest", "Other")
            other.Label = "Cube <1>"
            self.assertEqual(other.Label, "Cube <3>")
            # Other labels keep the padded numbers
            other.Label = "Cube"
            self.assertEqual(other.Label, "Cube001")
        finally:
            params.SetBool("DuplicateLabels", oldDuplicateLabels)

    def testDuplicateLabelEndingWithGreaterThan(self):
        # Only an instance label "Name <instance>" is numbered inside its brackets. Other
        # labels ending with '>' take the digits at the end, like any other label.
        params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        oldDuplicateLabels = params.GetBool("DuplicateLabels", False)
        params.SetBool("DuplicateLabels", False)
        try:
            for label, unique in (
                ("Foo>", "Foo>001"),
                ("<Tag>", "<Tag>001"),
                ("Box<a>", "Box<a>001"),
                ("x->y>", "x->y>001"),
                ("Box <a>", "Box <a001>"),
                ("Box <2>", "Box <3>"),
            ):
                first = self.Doc.addObject("App::FeatureTest", "First")
                first.Label = label
                self.assertEqual(first.Label, label)
                second = self.Doc.addObject("App::FeatureTest", "Second")
                second.Label = label
                self.assertEqual(second.Label, unique)
        finally:
            params.SetBool("DuplicateLabels", oldDuplicateLabels)


class DocumentSettingsCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("DocumentSettingsTests")

    def tearDown(self):
        if FreeCAD.getDocument(self.Doc.Name) is not None:
            FreeCAD.closeDocument(self.Doc.Name)

    def testStringSettingUpdatesOnlyNamespacedMetaKey(self):
        self.Doc.Meta = {
            "Unrelated": "keep",
            "Draft.Other": "old",
            "BIM.GridSpacing": "1 m",
        }

        settings = self.Doc.settings("Draft")
        settings.setString("GridSpacing", "0.1 m")

        self.assertEqual(settings.getString("GridSpacing", ""), "0.1 m")
        self.assertEqual(self.Doc.Meta["Draft.GridSpacing"], "0.1 m")
        self.assertEqual(self.Doc.Meta["Unrelated"], "keep")
        self.assertEqual(self.Doc.Meta["Draft.Other"], "old")
        self.assertEqual(self.Doc.Meta["BIM.GridSpacing"], "1 m")

    def testTypedGettersParseValidValuesAndDefaultInvalidValues(self):
        self.Doc.Meta = {
            "Draft.GridMainlines": "10",
            "Draft.GridSize": "12.5",
            "Draft.ShowGrid": "true",
            "Draft.InvalidInt": "10 lines",
            "Draft.InvalidFloat": "12,5",
            "Draft.InvalidBool": "sometimes",
        }

        settings = self.Doc.settings("Draft")

        self.assertEqual(settings.getInt("GridMainlines", 1), 10)
        self.assertAlmostEqual(settings.getFloat("GridSize", 1.0), 12.5)
        self.assertTrue(settings.getBool("ShowGrid", False))
        self.assertEqual(settings.getInt("InvalidInt", 7), 7)
        self.assertAlmostEqual(settings.getFloat("InvalidFloat", 2.5), 2.5)
        self.assertTrue(settings.getBool("InvalidBool", True))
        self.assertEqual(settings.getString("Missing", "fallback"), "fallback")
        self.assertEqual(settings.getInt("Missing", 3), 3)
        self.assertAlmostEqual(settings.getFloat("Missing", 4.5), 4.5)
        self.assertTrue(settings.getBool("Missing", True))

    def testTypedSettersStoreStringBackedCanonicalValues(self):
        settings = self.Doc.settings("Draft")

        settings.setInt("GridMainlines", 10)
        settings.setFloat("GridSize", 12.5)
        settings.setFloat("FineStep", 0.1)
        settings.setBool("ShowGrid", True)

        self.assertEqual(self.Doc.Meta["Draft.GridMainlines"], "10")
        self.assertEqual(self.Doc.Meta["Draft.GridSize"], "12.5")
        self.assertEqual(self.Doc.Meta["Draft.FineStep"], "0.1")
        self.assertEqual(self.Doc.Meta["Draft.ShowGrid"], "true")

    def testKeysAreScopedAndRemoveDeletesOnlySelectedKey(self):
        self.Doc.Meta = {
            "Draft.GridSpacing": "0.1 m",
            "Draft.GridSize": "100",
            "Draft.Bad.Key": "hidden",
            "BIM.GridSpacing": "1 m",
            "Draft_Style_Default": "{}",
        }

        settings = self.Doc.settings("Draft")

        self.assertEqual(settings.keys(), ["GridSize", "GridSpacing"])
        settings.remove("GridSize")

        self.assertNotIn("Draft.GridSize", self.Doc.Meta)
        self.assertEqual(self.Doc.Meta["Draft.GridSpacing"], "0.1 m")
        self.assertEqual(self.Doc.Meta["BIM.GridSpacing"], "1 m")
        self.assertEqual(self.Doc.Meta["Draft_Style_Default"], "{}")

    def testDottedNamespacesAreScoped(self):
        self.Doc.Meta = {
            "Draft.Grid.Spacing": "0.1 m",
            "Draft.Grid.Mainlines": "10",
            "Draft.Grid.Nested.Key": "hidden",
            "Draft.GridSize": "100",
            "Draft.Other": "keep",
            "BIM.Grid.Spacing": "1 m",
        }

        draftSettings = self.Doc.settings("Draft")
        gridSettings = self.Doc.settings("Draft.Grid")

        self.assertEqual(draftSettings.keys(), ["GridSize", "Other"])
        self.assertEqual(gridSettings.keys(), ["Mainlines", "Spacing"])
        self.assertEqual(gridSettings.getString("Spacing", ""), "0.1 m")

        gridSettings.setFloat("Size", 100.0)
        gridSettings.remove("Spacing")

        self.assertEqual(self.Doc.Meta["Draft.Grid.Size"], "100")
        self.assertNotIn("Draft.Grid.Spacing", self.Doc.Meta)
        self.assertEqual(self.Doc.Meta["Draft.Grid.Mainlines"], "10")
        self.assertEqual(self.Doc.Meta["Draft.Other"], "keep")
        self.assertEqual(self.Doc.Meta["BIM.Grid.Spacing"], "1 m")

    def testNamespaceAndKeyValidation(self):
        for namespace in ("", ".Draft", "Draft.", "Draft..Grid", "Draft-Grid"):
            with self.subTest(namespace=namespace):
                with self.assertRaises(ValueError):
                    self.Doc.settings(namespace)

        settings = self.Doc.settings("Draft.Grid")
        for key in ("", "Grid.Spacing", "Grid-Spacing"):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    settings.setString(key, "0.1 m")

    def testBoolArgumentsRequireBoolValues(self):
        settings = self.Doc.settings("Draft")

        with self.assertRaises(TypeError):
            settings.getBool("ShowGrid", "false")

        with self.assertRaises(TypeError):
            settings.setBool("ShowGrid", "false")


# class must be defined in global scope to allow it to be reloaded on document open
class SaveRestoreSpecialGroup:
    def __init__(self, obj):
        obj.addExtension("App::GroupExtensionPython")
        obj.Proxy = self

    def allowObject(self, ext, obj):
        return False


# class must be defined in global scope to allow it to be reloaded on document open
class SaveRestoreSpecialGroupViewProvider:
    def __init__(self, obj):
        obj.addExtension("Gui::ViewProviderGroupExtensionPython")
        obj.Proxy = self

    def testFunction(self):
        pass


# class must be defined in global scope to allow it to be reloaded on document open
class SaveRestoreRecomputeRequest:
    def __init__(self, obj):
        obj.Proxy = self

    def onDocumentRestored(self, obj):
        obj.Document.addRecomputeObject(obj)


class DocumentSaveRestoreCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("SaveRestoreTests")
        L1 = self.Doc.addObject("App::FeatureTest", "Label_1")
        L2 = self.Doc.addObject("App::FeatureTest", "Label_2")
        L3 = self.Doc.addObject("App::FeatureTest", "Label_3")
        self.TempPath = tempfile.gettempdir()
        FreeCAD.Console.PrintLog("  Using temp path: " + self.TempPath + "\n")

    def testSaveAndRestore(self):
        # saving and restoring
        SaveName = self.TempPath + os.sep + "SaveRestoreTests.FCStd"
        self.assertTrue(self.Doc.Label_1.TypeTransient == 4711)
        self.Doc.Label_1.TypeTransient = 4712
        # setup Linking
        self.Doc.Label_1.Link = self.Doc.Label_2
        self.Doc.Label_2.Link = self.Doc.Label_3
        self.Doc.Label_1.LinkSub = (self.Doc.Label_2, ["Sub1", "Sub2"])
        self.Doc.Label_2.LinkSub = (self.Doc.Label_3, ["Sub3", "Sub4"])
        # save the document
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument("SaveRestoreTests")
        self.Doc = FreeCAD.open(SaveName)
        self.assertTrue(self.Doc.Label_1.Integer == 4711)
        self.assertTrue(self.Doc.Label_2.Integer == 4711)
        # test Linkage
        self.assertTrue(self.Doc.Label_1.Link == self.Doc.Label_2)
        self.assertTrue(self.Doc.Label_2.Link == self.Doc.Label_3)
        self.assertTrue(self.Doc.Label_1.LinkSub == (self.Doc.Label_2, ["Sub1", "Sub2"]))
        self.assertTrue(self.Doc.Label_2.LinkSub == (self.Doc.Label_3, ["Sub3", "Sub4"]))
        # do NOT save transient properties
        self.assertTrue(self.Doc.Label_1.TypeTransient == 4711)
        self.assertTrue(self.Doc == FreeCAD.getDocument(self.Doc.Name))

    def testRestore(self):
        Doc = FreeCAD.newDocument("RestoreTests")
        Doc.addObject("App::FeatureTest", "Label_1")
        # saving and restoring
        FileName = self.TempPath + os.sep + "Test2.FCStd"
        Doc.saveAs(FileName)
        # restore must first clear the current content
        Doc.restore()
        self.assertTrue(len(Doc.Objects) == 1)
        FreeCAD.closeDocument("RestoreTests")

    def testFailedSaveAsKeepsDocumentName(self):
        # https://github.com/FreeCAD/FreeCAD/issues/32482
        with tempfile.TemporaryDirectory() as temp_dir:
            blocker = os.path.join(temp_dir, "blocker")
            with open(blocker, "w") as f:
                f.write("not a directory")
            label = self.Doc.Label
            transient = self.Doc.TransientDir
            self.assertEqual(self.Doc.FileName, "")
            with self.assertRaises(Exception):
                self.Doc.saveAs(os.path.join(blocker, "sub", "Failed.FCStd"))
            self.assertEqual(self.Doc.FileName, "")
            self.assertEqual(self.Doc.Label, label)
            self.assertEqual(self.Doc.TransientDir, transient)
            self.assertTrue(os.path.isdir(self.Doc.TransientDir))

            # a later saveAs to a valid path still works
            good = os.path.join(temp_dir, "Saved.FCStd")
            self.Doc.saveAs(good)
            self.assertEqual(os.path.normcase(self.Doc.FileName), os.path.normcase(good))
            self.assertEqual(self.Doc.Label, "Saved")
            self.assertTrue(os.path.isfile(good))

            # a failing saveAs of a saved document keeps its previous file
            with self.assertRaises(Exception):
                self.Doc.saveAs(os.path.join(blocker, "sub", "Other.FCStd"))
            self.assertEqual(os.path.normcase(self.Doc.FileName), os.path.normcase(good))
            self.assertEqual(self.Doc.Label, "Saved")

    def testActiveDocument(self):
        # open 2nd doc
        Second = FreeCAD.newDocument("Active")
        FreeCAD.closeDocument("Active")
        try:
            # There might be no active document anymore
            # This also checks for dangling pointers
            Active = FreeCAD.activeDocument()
            # Second is still a valid object
            self.assertTrue(Second != Active)
        except Exception:
            # Okay, no document open
            self.assertTrue(True)

    def testExtensionSaveRestore(self):
        # saving and restoring
        SaveName = self.TempPath + os.sep + "SaveRestoreExtensions.FCStd"
        Doc = FreeCAD.newDocument("SaveRestoreExtensions")
        # we try to create a normal python object and add an extension to it
        obj = Doc.addObject("App::DocumentObject", "Obj")
        grp1 = Doc.addObject("App::DocumentObject", "Extension_1")
        grp2 = Doc.addObject("App::FeaturePython", "Extension_2")

        grp1.addExtension("App::GroupExtensionPython")
        SaveRestoreSpecialGroup(grp2)
        if FreeCAD.GuiUp:
            SaveRestoreSpecialGroupViewProvider(grp2.ViewObject)
        grp2.Group = [obj]

        Doc.saveAs(SaveName)
        FreeCAD.closeDocument("SaveRestoreExtensions")
        Doc = FreeCAD.open(SaveName)

        self.assertTrue(Doc.Extension_1.hasExtension("App::GroupExtension"))
        self.assertTrue(Doc.Extension_2.hasExtension("App::GroupExtension"))
        self.assertTrue(Doc.Extension_2.Group[0] is Doc.Obj)
        self.assertTrue(hasattr(Doc.Extension_2.Proxy, "allowObject"))

        if FreeCAD.GuiUp:
            self.assertTrue(
                Doc.Extension_2.ViewObject.hasExtension("Gui::ViewProviderGroupExtensionPython")
            )
            self.assertTrue(hasattr(Doc.Extension_2.ViewObject.Proxy, "testFunction"))

        FreeCAD.closeDocument("SaveRestoreExtensions")

    def testAddRecomputeObjectOnRestore(self):
        SaveName = self.TempPath + os.sep + "SaveRestoreRecompute.FCStd"
        Doc = FreeCAD.newDocument("SaveRestoreRecompute")
        obj = Doc.addObject("App::FeaturePython", "Requested")
        SaveRestoreRecomputeRequest(obj)
        Proxy(Doc.addObject("App::FeaturePython", "Other"))
        Doc.recompute()
        # Outside a restore the request has no effect
        Doc.addRecomputeObject(obj)
        self.assertFalse(Doc.isTouched())
        with self.assertRaises(ValueError):
            Doc.addRecomputeObject(self.Doc.Label_1)

        Doc.saveAs(SaveName)
        FreeCAD.closeDocument("SaveRestoreRecompute")
        Doc = FreeCAD.open(SaveName)
        try:
            # Touch flags set in onDocumentRestored() are normally purged
            self.assertIn("Touched", Doc.Requested.State)
            self.assertNotIn("Touched", Doc.Other.State)
            self.assertEqual(Doc.recompute(), 1)
            self.assertFalse(Doc.isTouched())
        finally:
            FreeCAD.closeDocument(Doc.Name)

    def testPersistenceContentDump(self):
        # test smallest level... property
        self.Doc.Label_1.Vector = (1, 2, 3)
        dump = self.Doc.Label_1.dumpPropertyContent("Vector", Compression=9)
        self.Doc.Label_2.restorePropertyContent("Vector", dump)
        self.assertEqual(self.Doc.Label_1.Vector, self.Doc.Label_2.Vector)

        # next higher: object
        self.Doc.Label_1.Distance = 12
        self.Doc.Label_1.String = "test"
        dump = self.Doc.Label_1.dumpContent()
        self.Doc.Label_3.restoreContent(dump)
        self.assertEqual(self.Doc.Label_1.Distance, self.Doc.Label_3.Distance)
        self.assertEqual(self.Doc.Label_1.String, self.Doc.Label_3.String)

        # highest level: document
        dump = self.Doc.dumpContent(9)
        Doc = FreeCAD.newDocument("DumpTest")
        Doc.restoreContent(dump)
        self.assertEqual(len(self.Doc.Objects), len(Doc.Objects))
        self.assertEqual(self.Doc.Label_1.Distance, Doc.Label_1.Distance)
        self.assertEqual(self.Doc.Label_1.String, Doc.Label_1.String)
        self.assertEqual(self.Doc.Label_1.Vector, Doc.Label_1.Vector)
        FreeCAD.closeDocument("DumpTest")

    def testPersistenceContentDumpInvalidCompression(self):
        # a compression level that zlib rejects used to abort the whole process
        self.Doc.Label_1.Vector = (1, 2, 3)
        self.Doc.Label_1.Distance = 12
        for level in (10, 1000000, -2):
            with self.assertRaises(ValueError):
                self.Doc.Label_1.dumpContent(level)
            with self.assertRaises(ValueError):
                self.Doc.Label_1.dumpPropertyContent("Vector", Compression=level)

        # zlib's default (-1) and the levels from 0 to 9 are valid
        for level in (-1, 0, 9):
            dump = self.Doc.Label_1.dumpContent(level)
            self.Doc.Label_3.restoreContent(dump)
            self.assertEqual(self.Doc.Label_1.Distance, self.Doc.Label_3.Distance)

            dump = self.Doc.Label_1.dumpPropertyContent("Vector", Compression=level)
            self.Doc.Label_2.restorePropertyContent("Vector", dump)
            self.assertEqual(self.Doc.Label_1.Vector, self.Doc.Label_2.Vector)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("SaveRestoreTests")


class DocumentBackupDirectoryCases(unittest.TestCase):
    """The Document/BackupDirectory preference stores backup files in a directory.
    https://github.com/FreeCAD/FreeCAD/issues/6697"""

    PARAMS = (
        ("Bool", "BackupPolicy", True),
        ("Bool", "CreateBackupFiles", True),
        ("Int", "CountBackupFiles", 1),
        ("Bool", "UseFCBakExtension", False),
    )

    def setUp(self):
        self.grp = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        self.saved = []
        for kind, name, value in self.PARAMS + (("String", "BackupDirectory", ""),):
            stored = name in getattr(self.grp, "Get" + kind + "s")()
            old = getattr(self.grp, "Get" + kind)(name)
            self.saved.append((kind, name, stored, old))
        for kind, name, value in self.PARAMS:
            getattr(self.grp, "Set" + kind)(name, value)
        self.dir = tempfile.mkdtemp(prefix="fc_backup_dir_")
        self.path = os.path.join(self.dir, "BackupDirectory.FCStd")
        self.doc = FreeCAD.newDocument("BackupDirectoryTests")

    def tearDown(self):
        import shutil

        FreeCAD.closeDocument(self.doc.Name)
        shutil.rmtree(self.dir, ignore_errors=True)
        for kind, name, stored, old in self.saved:
            if stored:
                getattr(self.grp, "Set" + kind)(name, old)
            else:
                getattr(self.grp, "Rem" + kind)(name)

    def _save_twice(self):
        self.doc.saveAs(self.path)
        self.doc.addObject("App::FeatureTest", "Feature")
        self.doc.save()

    def testBackupNextToDocumentByDefault(self):
        self.grp.RemString("BackupDirectory")
        self._save_twice()
        self.assertTrue(os.path.exists(self.path + "1"))

    def testBackupInRelativeDirectory(self):
        self.grp.SetString("BackupDirectory", "bak")
        self._save_twice()
        self.assertTrue(os.path.exists(os.path.join(self.dir, "bak", "BackupDirectory.FCStd1")))
        self.assertFalse(os.path.exists(self.path + "1"))
        self.assertTrue(os.path.exists(self.path))


class DocumentRecoveryCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("RecoveryTests")
        self.Obj = self.Doc.addObject("App::FeatureTest", "RecoveryObject")
        self.savedFileName = None

    def tearDown(self):
        if FreeCAD.getDocument("RecoveryTests") is not None:
            FreeCAD.closeDocument("RecoveryTests")
        if self.savedFileName and os.path.exists(self.savedFileName):
            os.remove(self.savedFileName)

    def testWriteCompressedRecoverySnapshot(self):
        self.assertTrue(self.Doc.canWriteRecoverySnapshot())
        self.assertTrue(FreeCAD.writeRecoverySnapshotToTransientDir(self.Doc))

        metadata = os.path.join(self.Doc.TransientDir, "fc_recovery_file.xml")
        archive = os.path.join(self.Doc.TransientDir, "fc_recovery_file.fcstd")

        self.assertTrue(os.path.isfile(metadata))
        self.assertTrue(os.path.isfile(archive))

        root = ET.parse(metadata).getroot()
        self.assertEqual(root.tag, "AutoRecovery")

        with zipfile.ZipFile(archive) as recovery:
            self.assertIn("Document.xml", recovery.namelist())

    def testWriteUncompressedRecoverySnapshot(self):
        self.assertTrue(FreeCAD.writeRecoverySnapshotToTransientDir(self.Doc, compressed=False))

        metadata = os.path.join(self.Doc.TransientDir, "fc_recovery_file.xml")
        document_xml = os.path.join(self.Doc.TransientDir, "fc_recovery_files", "Document.xml")

        self.assertTrue(os.path.isfile(metadata))
        self.assertTrue(os.path.isfile(document_xml))

    def testRecoveryMetadataEscapesXml(self):
        self.Doc.Label = 'Recovery <Label> & "Name"'
        self.savedFileName = os.path.join(tempfile.gettempdir(), "Recovery&Name.FCStd")
        self.Doc.saveAs(self.savedFileName)

        self.assertTrue(FreeCAD.writeRecoverySnapshotToTransientDir(self.Doc))

        metadata = os.path.join(self.Doc.TransientDir, "fc_recovery_file.xml")
        root = ET.parse(metadata).getroot()

        self.assertEqual(root.findtext("Label"), self.Doc.Label)
        self.assertEqual(root.findtext("FileName"), self.savedFileName)

    def testRejectRecoverySnapshotDuringTransaction(self):
        self.Doc.openTransaction("RecoveryWrite")
        try:
            self.assertFalse(self.Doc.canWriteRecoverySnapshot())
            with self.assertRaises(RuntimeError):
                FreeCAD.writeRecoverySnapshotToTransientDir(self.Doc)
        finally:
            self.Doc.abortTransaction()


class DocumentRecomputeCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("RecomputeTests")
        self.L1 = self.Doc.addObject("App::FeatureTest", "Label_1")
        self.L2 = self.Doc.addObject("App::FeatureTest", "Label_2")
        self.L3 = self.Doc.addObject("App::FeatureTest", "Label_3")

    def testDescent(self):
        # testing the up and downstream stuff
        FreeCAD.Console.PrintLog("def testDescent(self):Testcase not implemented\n")
        self.L1.Link = self.L2
        self.L2.Link = self.L3

    def testRecompute(self):

        # sequence to test recompute behaviour
        #       L1---\    L7
        #      /  \   \    |
        #    L2   L3   \  L8
        #   /  \ /  \  /
        #  L4   L5   L6

        L1 = self.Doc.addObject("App::FeatureTest", "Label_1")
        L2 = self.Doc.addObject("App::FeatureTest", "Label_2")
        L3 = self.Doc.addObject("App::FeatureTest", "Label_3")
        L4 = self.Doc.addObject("App::FeatureTest", "Label_4")
        L5 = self.Doc.addObject("App::FeatureTest", "Label_5")
        L6 = self.Doc.addObject("App::FeatureTest", "Label_6")
        L7 = self.Doc.addObject("App::FeatureTest", "Label_7")
        L8 = self.Doc.addObject("App::FeatureTest", "Label_8")
        L1.LinkList = [L2, L3, L6]
        L2.Link = L4
        L2.LinkList = [L5]
        L3.LinkList = [L5, L6]
        L7.Link = L8  # make second root

        self.assertTrue(L7 in self.Doc.RootObjects)
        self.assertTrue(L1 in self.Doc.RootObjects)

        self.assertTrue(len(self.Doc.Objects) == len(self.Doc.TopologicalSortedObjects))

        seqDic = {}
        i = 0
        for obj in self.Doc.TopologicalSortedObjects:
            seqDic[obj] = i
            print(obj)
            i += 1

        self.assertTrue(seqDic[L2] > seqDic[L1])
        self.assertTrue(seqDic[L3] > seqDic[L1])
        self.assertTrue(seqDic[L5] > seqDic[L2])
        self.assertTrue(seqDic[L5] > seqDic[L3])
        self.assertTrue(seqDic[L5] > seqDic[L1])

        self.assertTrue(
            (0, 0, 0, 0, 0, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        self.assertTrue(self.Doc.recompute() == 4)
        self.assertTrue(
            (1, 1, 1, 0, 0, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L5.enforceRecompute()
        self.assertTrue(
            (1, 1, 1, 0, 0, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        self.assertTrue(self.Doc.recompute() == 4)
        self.assertTrue(
            (2, 2, 2, 0, 1, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L4.enforceRecompute()
        self.assertTrue(self.Doc.recompute() == 3)
        self.assertTrue(
            (3, 3, 2, 1, 1, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L5.enforceRecompute()
        self.assertTrue(self.Doc.recompute() == 4)
        self.assertTrue(
            (4, 4, 3, 1, 2, 0)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L6.enforceRecompute()
        self.assertTrue(self.Doc.recompute() == 3)
        self.assertTrue(
            (5, 4, 4, 1, 2, 1)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L2.enforceRecompute()
        self.assertTrue(self.Doc.recompute() == 2)
        self.assertTrue(
            (6, 5, 4, 1, 2, 1)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )
        L1.enforceRecompute()
        self.assertTrue(self.Doc.recompute() == 1)
        self.assertTrue(
            (7, 5, 4, 1, 2, 1)
            == (L1.ExecCount, L2.ExecCount, L3.ExecCount, L4.ExecCount, L5.ExecCount, L6.ExecCount)
        )

        self.Doc.removeObject(L1.Name)
        self.Doc.removeObject(L2.Name)
        self.Doc.removeObject(L3.Name)
        self.Doc.removeObject(L4.Name)
        self.Doc.removeObject(L5.Name)
        self.Doc.removeObject(L6.Name)
        self.Doc.removeObject(L7.Name)
        self.Doc.removeObject(L8.Name)

    def testRemoveObjectInRecomputedObserver(self):
        # https://github.com/FreeCAD/FreeCAD/issues/27781
        # An observer of the recomputed signal deletes an object that was just
        # recomputed. The object list of the signal is still delivered to the
        # other observers (e.g. the tree view) and read by recompute itself,
        # so the object must stay alive until recompute is finished.
        doc = self.Doc
        doc.UndoMode = 0
        victim = self.L1
        doc.recompute()
        victim.touch()

        class Remover:
            def slotRecomputedDocument(self, d):
                if d == doc and doc.getObject("Label_1"):
                    doc.removeObject("Label_1")

        class Reader:
            result = None

            def slotRecomputedDocument(self, d):
                if d == doc:
                    try:
                        self.result = victim.TypeId
                    except ReferenceError as e:
                        self.result = str(e)

        remover = Remover()
        reader = Reader()
        FreeCAD.addDocumentObserver(remover)
        FreeCAD.addDocumentObserver(reader)
        try:
            doc.recompute()
        finally:
            FreeCAD.removeDocumentObserver(remover)
            FreeCAD.removeDocumentObserver(reader)

        self.assertEqual(reader.result, "App::FeatureTest")
        self.assertIsNone(doc.getObject("Label_1"))
        with self.assertRaises(ReferenceError):
            victim.TypeId

    def testCloseDocumentFromExecuteIsRefused(self):
        # Closing the document from a feature's execute() destroyed it while
        # Document::recompute() was still running on it (access violation).
        doc = self.Doc

        class Closer:
            error = None

            def __init__(self, obj):
                obj.Proxy = self

            def execute(self, obj):
                try:
                    FreeCAD.closeDocument(doc.Name)
                except RuntimeError as e:
                    Closer.error = e

        Closer(doc.addObject("App::FeaturePython", "Closer"))
        doc.recompute()
        self.assertIsInstance(Closer.error, RuntimeError)
        self.assertIn(doc.Name, FreeCAD.listDocuments())
        self.assertIsNotNone(doc.getObject("Closer"))

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("RecomputeTests")


class UndoRedoCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("UndoTest")
        self.Doc.addObject("App::FeatureTest", "Base")
        self.Doc.addObject("App::FeatureTest", "Del")
        self.Doc.getObject("Del").Integer = 2

    def testUndoProperties(self):
        # first transaction
        self.Doc.openTransaction("Transaction1")
        self.Doc.addObject("App::FeatureTest", "test1")
        self.Doc.getObject("test1").Integer = 1
        self.Doc.getObject("test1").String = "test1"
        self.Doc.getObject("test1").Float = 1.0
        self.Doc.getObject("test1").Bool = 1

        # self.Doc.getObject("test1").IntegerList  = 1
        # self.Doc.getObject("test1").FloatList  = 1.0

        # self.Doc.getObject("test1").Matrix  = (1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0)
        # self.Doc.getObject("test1").Vector  = (1.0,1.0,1.0)

        # second transaction
        self.Doc.openTransaction("Transaction2")
        self.Doc.getObject("test1").Integer = 2
        self.Doc.getObject("test1").String = "test2"
        self.Doc.getObject("test1").Float = 2.0
        self.Doc.getObject("test1").Bool = 0

    def testUndoClear(self):
        # switch on the Undo
        self.assertEqual(self.Doc.UndoNames, [])
        self.assertEqual(self.Doc.UndoCount, 0)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        self.Doc.openTransaction("Transaction1")
        # becomes the active object
        self.Doc.addObject("App::FeatureTest", "test1")
        self.Doc.commitTransaction()
        # removes the active object
        self.Doc.undo()
        self.assertEqual(self.Doc.ActiveObject, None)
        # deletes the active object
        self.Doc.clearUndos()
        self.assertEqual(self.Doc.ActiveObject, None)

    def testUndo(self):
        # switch on the Undo
        self.assertEqual(self.Doc.UndoNames, [])
        self.assertEqual(self.Doc.UndoCount, 0)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # first transaction
        self.Doc.openTransaction("Transaction1")
        self.Doc.addObject("App::FeatureTest", "test1")
        self.Doc.getObject("test1").Integer = 1
        self.Doc.getObject("Del").Integer = 1
        self.Doc.removeObject("Del")
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # second transaction
        self.Doc.openTransaction("Transaction2")
        # new behavior: no change, no transaction
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        self.Doc.getObject("test1").Integer = 2
        self.assertEqual(self.Doc.UndoNames, ["Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # abort second transaction
        self.Doc.abortTransaction()
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)
        self.assertEqual(self.Doc.getObject("test1").Integer, 1)

        # again second transaction
        self.Doc.openTransaction("Transaction2")
        self.Doc.getObject("test1").Integer = 2
        self.assertEqual(self.Doc.UndoNames, ["Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # third transaction
        self.Doc.openTransaction("Transaction3")
        self.Doc.getObject("test1").Integer = 3
        self.assertEqual(self.Doc.UndoNames, ["Transaction3", "Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 3)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # fourth transaction
        self.Doc.openTransaction("Transaction4")
        self.Doc.getObject("test1").Integer = 4
        self.assertEqual(
            self.Doc.UndoNames, ["Transaction4", "Transaction3", "Transaction2", "Transaction1"]
        )
        self.assertEqual(self.Doc.UndoCount, 4)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # undo the fourth transaction
        self.Doc.undo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 3)
        self.assertEqual(self.Doc.UndoNames, ["Transaction3", "Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 3)
        self.assertEqual(self.Doc.RedoNames, ["Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 1)

        # undo the third transaction
        self.Doc.undo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 2)
        self.assertEqual(self.Doc.UndoNames, ["Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, ["Transaction3", "Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 2)

        # undo the second transaction
        self.Doc.undo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 1)
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, ["Transaction2", "Transaction3", "Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 3)

        # undo the first transaction
        self.Doc.undo()
        self.assertTrue(self.Doc.getObject("test1") is None)
        self.assertTrue(self.Doc.getObject("Del").Integer == 2)
        self.assertEqual(self.Doc.UndoNames, [])
        self.assertEqual(self.Doc.UndoCount, 0)
        self.assertEqual(
            self.Doc.RedoNames, ["Transaction1", "Transaction2", "Transaction3", "Transaction4"]
        )
        self.assertEqual(self.Doc.RedoCount, 4)

        # redo the first transaction
        self.Doc.redo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 1)
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, ["Transaction2", "Transaction3", "Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 3)

        # redo the second transaction
        self.Doc.redo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 2)
        self.assertEqual(self.Doc.UndoNames, ["Transaction2", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, ["Transaction3", "Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 2)

        # undo the second transaction
        self.Doc.undo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 1)
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, ["Transaction2", "Transaction3", "Transaction4"])
        self.assertEqual(self.Doc.RedoCount, 3)

        # new transaction eight
        self.Doc.openTransaction("Transaction8")
        self.Doc.getObject("test1").Integer = 8
        self.assertEqual(self.Doc.UndoNames, ["Transaction8", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)
        self.Doc.abortTransaction()
        self.assertEqual(self.Doc.UndoNames, ["Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 1)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # again new transaction eight
        self.Doc.openTransaction("Transaction8")
        self.Doc.getObject("test1").Integer = 8
        self.assertEqual(self.Doc.UndoNames, ["Transaction8", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)

        # again new transaction nine
        self.Doc.openTransaction("Transaction9")
        self.Doc.getObject("test1").Integer = 9
        self.assertEqual(self.Doc.UndoNames, ["Transaction9", "Transaction8", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 3)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)
        self.Doc.commitTransaction()
        self.assertEqual(self.Doc.UndoNames, ["Transaction9", "Transaction8", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 3)
        self.assertEqual(self.Doc.RedoNames, [])
        self.assertEqual(self.Doc.RedoCount, 0)
        self.assertEqual(self.Doc.getObject("test1").Integer, 9)

        # undo the ninth transaction
        self.Doc.undo()
        self.assertEqual(self.Doc.getObject("test1").Integer, 8)
        self.assertEqual(self.Doc.UndoNames, ["Transaction8", "Transaction1"])
        self.assertEqual(self.Doc.UndoCount, 2)
        self.assertEqual(self.Doc.RedoNames, ["Transaction9"])
        self.assertEqual(self.Doc.RedoCount, 1)

    def testUndoInList(self):
        self.Doc.openTransaction("Box")
        self.Box = self.Doc.addObject("App::FeatureTest")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Cylinder")
        self.Cylinder = self.Doc.addObject("App::FeatureTest")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Fuse")
        self.Fuse1 = self.Doc.addObject("App::FeatureTest", "Fuse")
        self.Fuse1.LinkList = [self.Box, self.Cylinder]
        self.Doc.commitTransaction()

        self.Doc.undo()
        self.assertTrue(len(self.Box.InList) == 0)
        self.assertTrue(len(self.Cylinder.InList) == 0)

        self.Doc.redo()
        self.assertTrue(len(self.Box.InList) == 1)
        self.assertTrue(self.Box.InList[0] == self.Doc.Fuse)
        self.assertTrue(len(self.Cylinder.InList) == 1)
        self.assertTrue(self.Cylinder.InList[0] == self.Doc.Fuse)

    def testUndoIssue0003150Part1(self):
        self.Doc.openTransaction("Box")
        self.Box = self.Doc.addObject("App::FeatureTest")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Cylinder")
        self.Cylinder = self.Doc.addObject("App::FeatureTest")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Fuse")
        self.Fuse1 = self.Doc.addObject("App::FeatureTest")
        self.Fuse1.LinkList = [self.Box, self.Cylinder]
        self.Doc.commitTransaction()
        self.Doc.recompute()

        self.Doc.openTransaction("Sphere")
        self.Sphere = self.Doc.addObject("App::FeatureTest")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Fuse")
        self.Fuse2 = self.Doc.addObject("App::FeatureTest")
        self.Fuse2.LinkList = [self.Fuse1, self.Sphere]
        self.Doc.commitTransaction()
        self.Doc.recompute()

        self.Doc.openTransaction("Part")
        self.Part = self.Doc.addObject("App::Part")
        self.Doc.commitTransaction()

        self.Doc.openTransaction("Drag")
        self.Part.addObject(self.Fuse2)
        self.Doc.commitTransaction()

        # 3 undos show the problem of failing recompute
        self.Doc.undo()
        self.Doc.undo()
        self.Doc.undo()
        self.assertTrue(self.Doc.recompute() >= 0)

    def testUndoRedoLinkCopyOnChange(self):
        """Undo/redo of a change that made a link's private copy restores the recorded state."""
        src = self.Doc.addObject("App::FeaturePython", "Src")
        src.addProperty("App::PropertyFloat", "Size")
        src.Size = 1
        src.setPropertyStatus("Size", "CopyOnChange")
        link = self.Doc.addObject("App::Link", "Lnk")
        link.LinkedObject = src
        link.LinkCopyOnChange = "Enabled"
        self.Doc.recompute()

        def copies():
            return [o for o in self.Doc.Objects if o.Name.startswith("Src") and o != src]

        self.Doc.openTransaction("Change")
        link.Size = 5
        self.Doc.commitTransaction()
        self.assertEqual(len(copies()), 1)
        self.assertEqual(link.LinkedObject, copies()[0])
        self.assertEqual(link.LinkCopyOnChange, "Owned")

        self.Doc.undo()
        self.assertEqual(copies(), [])
        self.assertIsNone(link.LinkCopyOnChangeGroup)
        self.assertEqual(link.LinkedObject, src)
        self.assertEqual(link.LinkCopyOnChangeSource, src)
        self.assertEqual(link.LinkCopyOnChange, "Enabled")
        self.assertEqual(link.Size, 1)

        self.Doc.redo()
        self.assertEqual(len(copies()), 1)
        copy = copies()[0]
        self.assertEqual(link.LinkedObject, copy)
        self.assertEqual(link.LinkCopyOnChangeSource, src)
        self.assertEqual(link.LinkCopyOnChange, "Owned")
        self.assertEqual(link.LinkCopyOnChangeGroup.ElementList, [copy])
        self.assertEqual(copy.Size, 5)
        self.assertEqual(src.Size, 1)

        self.Doc.undo()
        self.assertEqual(copies(), [])
        self.assertEqual(link.LinkedObject, src)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("UndoTest")


class DocumentGroupCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("GroupTests")

    def testGroup(self):
        # Add an object to the group
        L2 = self.Doc.addObject("App::FeatureTest", "Label_2")
        G1 = self.Doc.addObject("App::DocumentObjectGroup", "Group")
        G1.addObject(L2)
        self.assertTrue(G1.hasObject(L2))

        # Adding the group to itself must fail
        try:
            G1.addObject(G1)
        except Exception:
            FreeCAD.Console.PrintLog("Cannot add group to itself, OK\n")
        else:
            self.fail("Adding the group to itself must not be possible")

        # Remove object from group
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Label_2")
        self.Doc.commitTransaction()
        self.assertTrue(G1.getObject("Label_2") is None)
        self.Doc.undo()
        self.assertTrue(G1.getObject("Label_2") is not None)

        # Remove first group and then the object
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Group")
        self.Doc.removeObject("Label_2")
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.assertTrue(G1.getObject("Label_2") is not None)

        # Remove first object and then the group in two transactions
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Label_2")
        self.Doc.commitTransaction()
        self.assertTrue(G1.getObject("Label_2") is None)
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Group")
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.Doc.undo()
        self.assertTrue(G1.getObject("Label_2") is not None)

        # Remove first object and then the group in one transaction
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Label_2")
        self.assertTrue(G1.getObject("Label_2") is None)
        self.Doc.removeObject("Group")
        self.Doc.commitTransaction()
        self.Doc.undo()
        # FIXME: See bug #1820554
        self.assertTrue(G1.getObject("Label_2") is not None)

        # Add a second object to the group
        L3 = self.Doc.addObject("App::FeatureTest", "Label_3")
        G1.addObject(L3)
        self.Doc.openTransaction("Remove")
        self.Doc.removeObject("Label_2")
        self.assertTrue(G1.getObject("Label_2") is None)
        self.Doc.removeObject("Label_3")
        self.assertTrue(G1.getObject("Label_3") is None)
        self.Doc.removeObject("Group")
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.assertTrue(G1.getObject("Label_3") is not None)
        self.assertTrue(G1.getObject("Label_2") is not None)

        # Cleanup
        self.Doc.removeObject("Group")
        self.Doc.removeObject("Label_2")
        self.Doc.removeObject("Label_3")

    def testGroupAndGeoFeatureGroup(self):

        # an object can only be in one group at once, that must be enforced
        obj1 = self.Doc.addObject("App::FeatureTest", "obj1")
        grp1 = self.Doc.addObject("App::DocumentObjectGroup", "Group1")
        grp2 = self.Doc.addObject("App::DocumentObjectGroup", "Group2")
        grp1.addObject(obj1)
        self.assertTrue(obj1.getParentGroup() == grp1)
        self.assertTrue(obj1.getParentGeoFeatureGroup() is None)
        self.assertTrue(grp1.hasObject(obj1))
        grp2.addObject(obj1)
        self.assertTrue(grp1.hasObject(obj1) == False)
        self.assertTrue(grp2.hasObject(obj1))

        # an object is allowed to be in a group and a geofeaturegroup
        prt1 = self.Doc.addObject("App::Part", "Part1")
        prt2 = self.Doc.addObject("App::Part", "Part2")

        prt1.addObject(grp2)
        self.assertTrue(grp2.getParentGeoFeatureGroup() == prt1)
        self.assertTrue(grp2.getParentGroup() is None)
        self.assertTrue(grp2.hasObject(obj1))
        self.assertTrue(prt1.hasObject(grp2))
        self.assertTrue(prt1.hasObject(obj1))

        # it is not allowed to be in 2 geofeaturegroups
        prt2.addObject(grp2)
        self.assertTrue(grp2.hasObject(obj1))
        self.assertTrue(prt1.hasObject(grp2) == False)
        self.assertTrue(prt1.hasObject(obj1) == False)
        self.assertTrue(prt2.hasObject(grp2))
        self.assertTrue(prt2.hasObject(obj1))
        try:
            grp = prt1.Group
            grp.append(obj1)
            prt1.Group = grp
        except Exception:
            grp.remove(obj1)
            self.assertTrue(prt1.Group == grp)
        else:
            self.fail("No exception thrown when object is in multiple Groups")

        # it is not allowed to be in 2 Groups
        prt2.addObject(grp1)
        grp = grp1.Group
        grp.append(obj1)
        try:
            grp1.Group = grp
        except Exception:
            pass
        else:
            self.fail("No exception thrown when object is in multiple Groups")

        # cross linking between GeoFeatureGroups is not allowed
        self.Doc.recompute()
        box = self.Doc.addObject("App::FeatureTest", "Box")
        cyl = self.Doc.addObject("App::FeatureTest", "Cylinder")
        fus = self.Doc.addObject("App::FeatureTest", "Fusion")
        fus.LinkList = [cyl, box]
        self.Doc.recompute()
        self.assertTrue(fus.State[0] == "Up-to-date")
        fus.LinkList = (
            []
        )  # remove all links as addObject would otherwise transfer all linked objects
        prt1.addObject(cyl)
        fus.LinkList = [cyl, box]
        self.Doc.recompute()
        # self.assertTrue(fus.State[0] == 'Invalid')
        fus.LinkList = []
        prt1.addObject(box)
        fus.LinkList = [cyl, box]
        self.Doc.recompute()
        # self.assertTrue(fus.State[0] == 'Invalid')
        fus.LinkList = []
        prt1.addObject(fus)
        fus.LinkList = [cyl, box]
        self.Doc.recompute()
        self.assertTrue(fus.State[0] == "Up-to-date")
        prt2.addObject(box)  # this time addObject should move all dependencies to the new part
        self.Doc.recompute()
        self.assertTrue(fus.State[0] == "Up-to-date")

        # grouping must be resilient against cyclic links and not crash: #issue 0002567
        # (a cycle is refused and the Group keeps its valid members)
        prt1.addObject(prt2)
        grp = prt2.Group
        old = prt2.Group
        grp.append(prt1)
        with self.assertRaises(RuntimeError):
            prt2.Group = grp
        self.assertEqual(prt2.Group, old)
        self.Doc.recompute()
        prt2.Group = []
        try:
            prt2.Group = [prt2]
        except Exception:
            pass
        else:
            self.fail("Exception is expected")

        self.Doc.recompute()

    def testContainerChainGroupInPart(self):
        # ContainerChain must not raise when a plain group is nested inside a GeoFeatureGroup
        from Show.Containers import ContainerChain

        part = self.Doc.addObject("App::Part", "Part")
        group = self.Doc.addObject("App::DocumentObjectGroup", "Group")
        obj = self.Doc.addObject("App::FeatureTest", "Obj")
        part.addObject(group)
        group.addObject(obj)
        self.Doc.recompute()

        chain = ContainerChain(obj)
        objects_in_chain = [c for c in chain if not c.isDerivedFrom("App::Document")]
        self.assertIn(part, objects_in_chain)
        self.assertIn(group, objects_in_chain)

    def testGetParentPrefersGroupInsidePart(self):
        # https://github.com/FreeCAD/FreeCAD/issues/19600
        # getParent must return the innermost group regardless of the InList order
        part = self.Doc.addObject("App::Part", "Part")
        group = self.Doc.addObject("App::DocumentObjectGroup", "Group")
        obj = self.Doc.addObject("App::FeatureTest", "Obj")
        part.addObject(group)
        group.addObject(obj)
        self.assertEqual(obj.getParent(), group)
        part.removeObject(group)
        self.assertEqual(obj.getParent(), group)
        part.addObject(group)
        self.assertEqual(obj.getParent(), group)
        # an object directly in the Part still reports the Part
        other = self.Doc.addObject("App::FeatureTest", "Other")
        part.addObject(other)
        self.assertEqual(other.getParent(), part)
        self.assertEqual(group.getParent(), part)

    def testIssue0003150Part2(self):
        self.box = self.Doc.addObject("App::FeatureTest")
        self.cyl = self.Doc.addObject("App::FeatureTest")
        self.sph = self.Doc.addObject("App::FeatureTest")

        self.fus1 = self.Doc.addObject("App::FeatureTest")
        self.fus2 = self.Doc.addObject("App::FeatureTest")

        self.fus1.LinkList = [self.box, self.cyl]
        self.fus2.LinkList = [self.sph, self.cyl]

        self.prt = self.Doc.addObject("App::Part")
        self.prt.addObject(self.fus1)
        self.assertTrue(len(self.prt.Group) == 5)
        self.assertTrue(self.fus2.getParentGeoFeatureGroup() == self.prt)
        self.assertTrue(self.prt.hasObject(self.sph))

        self.prt.removeObject(self.fus1)
        self.assertTrue(len(self.prt.Group) == 0)

    def _reopenWithGroupLinksReplaced(self, replacements):
        # Group refuses cycles when it is set, so a cyclic group can only come from a
        # file (e.g. one written before cycles were refused): save, point the given
        # links at other objects in Document.xml and reopen.
        tempdir = tempfile.mkdtemp()
        path = os.path.join(tempdir, "GroupTests.FCStd")
        self.addCleanup(os.rmdir, tempdir)
        self.addCleanup(os.remove, path)
        self.Doc.saveAs(path)
        FreeCAD.closeDocument(self.Doc.Name)
        with zipfile.ZipFile(path) as zin:
            entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
        with zipfile.ZipFile(path, "w") as zout:
            for info, data in entries:
                if info.filename == "Document.xml":
                    text = data.decode("utf-8")
                    for old, new in replacements.items():
                        link = '<Link value="{}"/>'
                        self.assertEqual(text.count(link.format(old)), 1)
                        text = text.replace(link.format(old), link.format(new))
                    data = text.encode("utf-8")
                zout.writestr(info, data)
        self.Doc = FreeCAD.openDocument(path)
        self.assertEqual(self.Doc.Name, "GroupTests")

    def testGroupCannotContainItself(self):
        A = self.Doc.addObject("App::DocumentObjectGroup", "A")
        B = self.Doc.addObject("App::DocumentObjectGroup", "B")
        C = self.Doc.addObject("App::DocumentObjectGroup", "C")
        L = self.Doc.addObject("App::FeatureTest", "L")

        # directly, the invalid member is dropped and the valid ones are kept
        with self.assertRaises(RuntimeError):
            A.Group = [L, A]
        self.assertEqual(A.Group, [L])

        # through sub-groups
        A.Group = [B]
        B.Group = [C]
        with self.assertRaises(RuntimeError):
            C.Group = [A]
        self.assertEqual(C.Group, [])
        with self.assertRaises(RuntimeError):
            B.Group = [C, A]
        self.assertEqual(B.Group, [C])
        self.assertEqual(A.Group, [B])
        self.assertIsNone(A.getParentGroup())

        # addObject() raises, addObjects()/setObjects() skip the cycle without
        # taking the group out of its parent
        with self.assertRaises(Exception):
            C.addObject(A)
        with self.assertRaises(Exception):
            C.addObject(B)
        self.assertEqual(C.addObjects([A, L]), [L])
        self.assertEqual(C.Group, [L])
        self.assertEqual(C.setObjects([B]), [])
        self.assertEqual(C.Group, [])
        self.assertEqual(A.Group, [B])
        self.assertEqual(B.Group, [C])
        self.assertEqual(A.addObjects([A]), [])

        # moving a group to another branch is still allowed
        D = self.Doc.addObject("App::DocumentObjectGroup", "D")
        A.addObject(D)
        C.addObject(D)
        self.assertEqual(A.Group, [B])
        self.assertEqual(C.Group, [D])
        self.Doc.recompute()

    def testGeoFeatureGroupCannotContainItself(self):
        P1 = self.Doc.addObject("App::Part", "P1")
        P2 = self.Doc.addObject("App::Part", "P2")
        G = self.Doc.addObject("App::DocumentObjectGroup", "G")
        with self.assertRaises(RuntimeError):
            P1.Group = [P1]
        self.assertEqual(P1.Group, [])

        P1.addObject(P2)
        with self.assertRaises(RuntimeError):
            P2.Group = [P1]
        self.assertEqual(P2.Group, [])
        with self.assertRaises(Exception):
            P2.addObject(P1)
        self.assertEqual(P2.Group, [])
        self.assertEqual(P1.Group, [P2])

        # through a plain group, both ways
        P2.addObject(G)
        with self.assertRaises(RuntimeError):
            G.Group = [P1]
        self.assertEqual(G.Group, [])
        self.assertEqual(G.addObjects([P2]), [])
        self.assertEqual(P1.Group, [P2])
        self.assertEqual(P2.Group, [G])
        self.Doc.recompute()

    def testAddObjectsAddsEachObjectOnce(self):
        # addObjects() checked membership against Group, which it only updates at the
        # end, so an object listed twice, or a base shared by two added objects (moved
        # along into a Part), ended up twice in Group.
        G = self.Doc.addObject("App::DocumentObjectGroup", "G")
        f = self.Doc.addObject("App::FeaturePython", "f")
        self.assertEqual(G.addObjects([f, f]), [f])
        self.assertEqual(G.Group, [f])
        self.assertEqual(G.setObjects([f, f]), [f])
        self.assertEqual(G.Group, [f])

        P = self.Doc.addObject("App::Part", "P")
        base = self.Doc.addObject("App::FeaturePython", "Base")
        users = []
        for name in ("User1", "User2"):
            user = self.Doc.addObject("App::FeaturePython", name)
            user.addProperty("App::PropertyLink", "Source")
            user.Source = base
            users.append(user)
        P.addObjects(users + [users[0]])
        self.assertEqual(sorted(o.Name for o in P.Group), ["Base", "User1", "User2"])
        self.Doc.recompute()

    def testRestoreCyclicGroup(self):
        # an old file with a cyclic group still opens with its Group as saved
        A = self.Doc.addObject("App::DocumentObjectGroup", "A")
        B = self.Doc.addObject("App::DocumentObjectGroup", "B")
        L = self.Doc.addObject("App::FeatureTest", "L")
        S = self.Doc.addObject("App::FeatureTest", "S")
        A.Group = [B]
        B.Group = [S, L]
        self._reopenWithGroupLinksReplaced({"S": "A"})
        A = self.Doc.getObject("A")
        B = self.Doc.getObject("B")
        L = self.Doc.getObject("L")
        self.assertEqual(A.Group, [B])
        self.assertEqual(B.Group, [A, L])

        # its members can still be changed and removed, but the cycle cannot be made again
        X = self.Doc.addObject("App::FeatureTest", "X")
        B.Group = B.Group + [X]
        self.assertEqual(B.Group, [A, L, X])
        B.Group = [X, A, L]
        self.Doc.removeObject("L")
        self.assertEqual(B.Group, [X, A])
        B.removeObject(X)
        self.assertEqual(B.Group, [A])
        B.removeObject(A)
        self.assertEqual(B.Group, [])
        with self.assertRaises(RuntimeError):
            B.Group = [A]
        self.assertEqual(B.Group, [])
        self.assertEqual(A.Group, [B])
        self.Doc.recompute()

    def testRemoveObjectsFromDocumentCyclicGroup(self):
        # A group that contains itself (from a file) made removing its content recurse
        # until the stack overflowed
        G1 = self.Doc.addObject("App::DocumentObjectGroup", "G1")
        S1 = self.Doc.addObject("App::FeatureTest", "S1")
        G1.Group = [S1]
        G2 = self.Doc.addObject("App::DocumentObjectGroup", "G2")
        G3 = self.Doc.addObject("App::DocumentObjectGroup", "G3")
        L = self.Doc.addObject("App::FeatureTest", "L")
        S2 = self.Doc.addObject("App::FeatureTest", "S2")
        G2.Group = [G3]
        G3.Group = [S2, L]
        self._reopenWithGroupLinksReplaced({"S1": "G1", "S2": "G2"})

        G1 = self.Doc.getObject("G1")
        self.assertEqual(G1.Group, [G1])
        G1.removeObjectsFromDocument()
        self.assertEqual(G1.Group, [])
        self.assertIsNotNone(self.Doc.getObject("G1"))

        G2 = self.Doc.getObject("G2")
        self.assertEqual(self.Doc.getObject("G3").Group, [G2, self.Doc.getObject("L")])
        G2.removeObjectsFromDocument()
        self.assertEqual(G2.Group, [])
        self.assertIsNone(self.Doc.getObject("G3"))
        self.assertIsNone(self.Doc.getObject("L"))
        self.assertIsNotNone(self.Doc.getObject("G2"))

    def testRemoveObjectsFromDocumentNested(self):
        G1 = self.Doc.addObject("App::DocumentObjectGroup", "G1")
        G2 = G1.newObject("App::DocumentObjectGroup", "G2")
        G2.newObject("App::FeatureTest", "L1")
        G1.newObject("App::FeatureTest", "L2")
        G1.removeObjectsFromDocument()
        self.assertEqual(G1.Group, [])
        for name in ("G2", "L1", "L2"):
            self.assertIsNone(self.Doc.getObject(name))

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("GroupTests")


class DocumentPlatformCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PlatformTests")
        self.Doc.addObject("App::FeatureTest", "Test")
        self.TempPath = tempfile.gettempdir()
        self.DocName = self.TempPath + os.sep + "PlatformTests.FCStd"

    def testFloatList(self):
        self.Doc.Test.FloatList = [-0.05, 2.5, 5.2]

        # saving and restoring
        self.Doc.saveAs(self.DocName)
        FreeCAD.closeDocument("PlatformTests")
        self.Doc = FreeCAD.open(self.DocName)

        self.assertTrue(abs(self.Doc.Test.FloatList[0] + 0.05) < 0.01)
        self.assertTrue(abs(self.Doc.Test.FloatList[1] - 2.5) < 0.01)
        self.assertTrue(abs(self.Doc.Test.FloatList[2] - 5.2) < 0.01)

    def testColorList(self):
        self.Doc.Test.ColourList = [(1.0, 0.5, 0.0), (0.0, 0.5, 1.0)]

        # saving and restoring
        self.Doc.saveAs(self.DocName)
        FreeCAD.closeDocument("PlatformTests")
        self.Doc = FreeCAD.open(self.DocName)

        self.assertTrue(abs(self.Doc.Test.ColourList[0][0] - 1.0) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[0][1] - 0.5) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[0][2] - 0.0) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[0][3] - 1.0) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[1][0] - 0.0) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[1][1] - 0.5) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[1][2] - 1.0) < 0.01)
        self.assertTrue(abs(self.Doc.Test.ColourList[1][3] - 1.0) < 0.01)

    def testVectorList(self):
        self.Doc.Test.VectorList = [(-0.05, 2.5, 5.2), (-0.05, 2.5, 5.2)]

        # saving and restoring
        self.Doc.saveAs(self.DocName)
        FreeCAD.closeDocument("PlatformTests")
        self.Doc = FreeCAD.open(self.DocName)

        self.assertTrue(len(self.Doc.Test.VectorList) == 2)

    def testPoints(self):
        try:
            self.Doc.addObject("Points::Feature", "Points")

            # saving and restoring
            self.Doc.saveAs(self.DocName)
            FreeCAD.closeDocument("PlatformTests")
            self.Doc = FreeCAD.open(self.DocName)

            self.assertTrue(self.Doc.Points.Points.count() == 0)
        except Exception:
            pass

    def testNativePathSeparators(self):
        # https://github.com/FreeCAD/FreeCAD/issues/18027
        if os.sep != "\\":
            self.skipTest("Only relevant where the native separator is not '/'")
        for path in (
            self.Doc.TransientDir,
            FreeCAD.getUserCachePath(),
            FreeCAD.getTempPath(),
            FreeCAD.getUserAppDataDir(),
            FreeCAD.getUserConfigDir(),
        ):
            self.assertNotIn("/", path)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PlatformTests")


class DocumentBacklinks(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("BackLinks")

    def testIssue0003323(self):
        self.Doc.openTransaction("Create object")
        obj1 = self.Doc.addObject("App::FeatureTest", "Test1")
        obj2 = self.Doc.addObject("App::FeatureTest", "Test2")
        obj2.Link = obj1
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.Doc.openTransaction("Create object")

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("BackLinks")


class DocumentFileIncludeCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("FileIncludeTests")

    def testApplyFiles(self):
        self.Doc.openTransaction("Transaction0")
        self.L1 = self.Doc.addObject("App::DocumentObjectFileIncluded", "FileObject1")
        self.assertTrue(self.L1.File == "")
        self.Filename = self.L1.File

        self.Doc.openTransaction("Transaction1")
        self.TempPath = tempfile.gettempdir()
        # creating a file in the Transient directory of the document
        file = open(self.Doc.getTempFileName("test"), "w")
        file.write("test No1")
        file.close()
        # applying the file
        self.L1.File = (file.name, "Test.txt")
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        # read again
        file = open(self.L1.File, "r")
        self.assertTrue(file.read() == "test No1")
        file.close()
        file = open(self.TempPath + "/testNest.txt", "w")
        file.write("test No2")
        file.close()
        # applying the file
        self.Doc.openTransaction("Transaction2")
        self.L1.File = file.name
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        # read again
        file = open(self.L1.File, "r")
        self.assertTrue(file.read() == "test No2")
        file.close()
        self.Doc.undo()
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        # read again
        file = open(self.L1.File, "r")
        self.assertTrue(file.read() == "test No1")
        file.close()
        self.Doc.undo()
        # read again
        self.assertTrue(self.L1.File == "")
        self.Doc.redo()
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        # read again
        file = open(self.L1.File, "r")
        self.assertTrue(file.read() == "test No1")
        file.close()
        self.Doc.redo()
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        # read again
        file = open(self.L1.File, "r")
        self.assertTrue(file.read() == "test No2")
        file.close()
        # Save restore test
        FileName = self.TempPath + "/FileIncludeTests.fcstd"
        self.Doc.saveAs(FileName)
        FreeCAD.closeDocument("FileIncludeTests")
        self.Doc = FreeCAD.open(self.TempPath + "/FileIncludeTests.fcstd")
        # check if the file is still there
        self.L1 = self.Doc.getObject("FileObject1")
        file = open(self.L1.File, "r")
        res = file.read()
        FreeCAD.Console.PrintLog(res + "\n")
        self.assertTrue(res == "test No2")
        self.assertTrue(self.L1.File.split("/")[-1] == "Test.txt")
        file.close()

        # test for bug #94 (File overlap in PropertyFileIncluded)
        L2 = self.Doc.addObject("App::DocumentObjectFileIncluded", "FileObject2")
        L3 = self.Doc.addObject("App::DocumentObjectFileIncluded", "FileObject3")

        # creating two files in the Transient directory of the document
        file1 = open(self.Doc.getTempFileName("test"), "w")
        file1.write("test No1")
        file1.close()
        file2 = open(self.Doc.getTempFileName("test"), "w")
        file2.write("test No2")
        file2.close()

        # applying the file with the same base name
        L2.File = (file1.name, "Test.txt")
        L3.File = (file2.name, "Test.txt")

        file = open(L2.File, "r")
        self.assertTrue(file.read() == "test No1")
        file.close()
        file = open(L3.File, "r")
        self.assertTrue(file.read() == "test No2")
        file.close()

        # create a second document, copy a file and close the document
        # the test is about to put the file to the correct transient dir
        doc2 = FreeCAD.newDocument("Doc2")
        L4 = doc2.addObject("App::DocumentObjectFileIncluded", "FileObject")
        L5 = doc2.addObject("App::DocumentObjectFileIncluded", "FileObject")
        L6 = doc2.addObject("App::DocumentObjectFileIncluded", "FileObject")
        L4.File = (L3.File, "Test.txt")
        L5.File = L3.File
        L6.File = L3.File
        FreeCAD.closeDocument("FileIncludeTests")
        self.Doc = FreeCAD.open(self.TempPath + "/FileIncludeTests.fcstd")
        self.assertTrue(os.path.exists(L4.File))
        self.assertTrue(os.path.exists(L5.File))
        self.assertTrue(os.path.exists(L6.File))
        self.assertTrue(L5.File != L6.File)
        # copy file from L5 which is in the same directory
        L7 = doc2.addObject("App::DocumentObjectFileIncluded", "FileObject3")
        L7.File = (L5.File, "Copy.txt")
        self.assertTrue(os.path.exists(L7.File))
        FreeCAD.closeDocument("Doc2")

    def testBinarySaveRestore(self):
        payload = bytes((i % 251 for i in range(150000))) + b"\x00FreeCAD\x00restore\x00"
        source_path = os.path.join(tempfile.gettempdir(), "FileIncludeBinarySource.bin")
        doc_path = os.path.join(tempfile.gettempdir(), "FileIncludeTests.FCStd")

        with open(source_path, "wb") as file:
            file.write(payload)

        obj = self.Doc.addObject("App::DocumentObjectFileIncluded", "BinaryFile")
        obj.File = (source_path, "BinaryPayload.bin")
        self.Doc.saveAs(doc_path)

        FreeCAD.closeDocument("FileIncludeTests")
        self.Doc = FreeCAD.open(doc_path)
        obj = self.Doc.getObject("BinaryFile")

        with open(obj.File, "rb") as file:
            self.assertEqual(file.read(), payload)
        self.assertEqual(obj.File.split("/")[-1], "BinaryPayload.bin")

    def testCopyInSameDocumentDoesNotShareFile(self):
        # https://github.com/FreeCAD/FreeCAD/issues/11151
        source_path = os.path.join(tempfile.gettempdir(), "FileIncludeCopySource.svg")
        with open(source_path, "w") as file:
            file.write("original content")

        # without undo, removeObject() destroys the copy and its property
        self.Doc.UndoMode = 0
        obj = self.Doc.addObject("App::DocumentObjectFileIncluded", "Original")
        obj.File = source_path
        copy = self.Doc.copyObject(obj)

        self.assertNotEqual(copy.File, obj.File)
        self.assertTrue(copy.File.endswith(".svg"))
        with open(copy.File, "r") as file:
            self.assertEqual(file.read(), "original content")

        # deleting the copy must not delete the file of the original
        self.Doc.removeObject(copy.Name)
        self.assertTrue(os.path.exists(obj.File))
        with open(obj.File, "r") as file:
            self.assertEqual(file.read(), "original content")

        doc_path = os.path.join(tempfile.gettempdir(), "FileIncludeTests.FCStd")
        self.Doc.saveAs(doc_path)
        FreeCAD.closeDocument("FileIncludeTests")
        self.Doc = FreeCAD.open(doc_path)
        obj = self.Doc.getObject("Original")
        with open(obj.File, "r") as file:
            self.assertEqual(file.read(), "original content")

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("FileIncludeTests")


class DocumentPropertyCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PropertyTests")
        self.Obj = self.Doc.addObject("App::FeaturePython", "Test")

    def testDescent(self):
        # testing the up and downstream stuff
        props = self.Obj.supportedProperties()
        for i in props:
            self.Obj.addProperty(i, i.replace(":", "_"))
        tempPath = tempfile.gettempdir()
        tempFile = tempPath + os.sep + "PropertyTests.FCStd"
        self.Doc.saveAs(tempFile)
        FreeCAD.closeDocument("PropertyTests")
        self.Doc = FreeCAD.open(tempFile)

    def testRemoveProperty(self):
        prop = "Something"
        self.Obj.addProperty("App::PropertyFloat", prop)
        self.Obj.Something = 0.01
        self.Doc.recompute()
        self.Doc.openTransaction("modify and remove property")
        self.Obj.Something = 0.00
        self.Obj.removeProperty(prop)
        self.Obj.recompute()
        self.Doc.abortTransaction()

    def testRemovePropertyExpression(self):
        p1 = self.Doc.addObject("App::FeaturePython", "params1")
        p2 = self.Doc.addObject("App::FeaturePython", "params2")
        p1.addProperty("App::PropertyFloat", "a")
        p1.a = 42
        p2.addProperty("App::PropertyFloat", "b")
        p2.setExpression("b", "params1.a")
        self.Doc.recompute()
        p2.removeProperty("b")
        p1.touch()
        self.Doc.recompute()
        self.assertTrue(not p2 in p1.InList)

    def testRemovePropertyOnChange(self):
        class Feature:
            def __init__(self, fp):
                fp.Proxy = self
                fp.addProperty("App::PropertyString", "Test")

            def onBeforeChange(self, fp, prop):
                if prop == "Test":
                    fp.removeProperty("Test")

            def onChanged(self, fp, prop):
                getattr(fp, prop)

        obj = self.Doc.addObject("App::FeaturePython")
        fea = Feature(obj)
        obj.Test = "test"

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PropertyTests")


class DocumentExpressionCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument()

    def assertAlmostEqual(self, v1, v2):
        if math.fabs(v2 - v1) > 1e-12:
            self.assertEqual(v1, v2)

    def testExpression(self):
        self.Obj1 = self.Doc.addObject("App::FeatureTest", "Test")
        self.Obj2 = self.Doc.addObject("App::FeatureTest", "Test")
        # set the object twice to test that the backlinks are removed when overwriting the expression
        self.Obj2.setExpression(
            "Placement.Rotation.Angle", "%s.Placement.Rotation.Angle" % self.Obj1.Name
        )
        self.Obj2.setExpression(
            "Placement.Rotation.Angle", "%s.Placement.Rotation.Angle" % self.Obj1.Name
        )
        self.Obj1.Placement = FreeCAD.Placement(
            FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 10)
        )
        self.Doc.recompute()
        self.assertAlmostEqual(
            self.Obj1.Placement.Rotation.Angle, self.Obj2.Placement.Rotation.Angle
        )

        # clear the expression
        self.Obj2.setExpression("Placement.Rotation.Angle", None)
        self.assertAlmostEqual(
            self.Obj1.Placement.Rotation.Angle, self.Obj2.Placement.Rotation.Angle
        )
        self.Doc.recompute()
        self.assertAlmostEqual(
            self.Obj1.Placement.Rotation.Angle, self.Obj2.Placement.Rotation.Angle
        )
        # touch the objects to perform a recompute
        self.Obj1.Placement = self.Obj1.Placement
        self.Obj2.Placement = self.Obj2.Placement
        # must not raise a topological error
        self.assertEqual(self.Doc.recompute(), 2)

        # add test for issue #6948
        self.Obj3 = self.Doc.addObject("App::FeatureTest", "Test")
        self.Obj3.setExpression("Float", "2*(5%3)")
        self.Doc.recompute()
        self.assertEqual(self.Obj3.Float, 4)
        self.assertEqual(self.Obj3.evalExpression(self.Obj3.ExpressionEngine[0][1]), 4)

    def testYawRollExpressionOutsideHalfTurn(self):
        # issue #12193: yaw and roll are periodic, an expression result beyond
        # +-180 degrees must give the equivalent rotation instead of an error
        obj = self.Doc.addObject("App::FeatureTest", "YawRoll")
        obj.setExpression(".Placement.Rotation.Yaw", "45 deg + 180 deg")
        self.Doc.recompute()
        self.assertNotIn("Invalid", obj.State)
        ypr = obj.Placement.Rotation.toEulerAngles("YawPitchRoll")
        self.assertAlmostEqual(round(ypr[0], 9), -135.0)
        obj.setExpression(".Placement.Rotation.Yaw", None)

        obj.setExpression(".Placement.Rotation.Roll", "-200 deg")
        self.Doc.recompute()
        self.assertNotIn("Invalid", obj.State)
        ypr = obj.Placement.Rotation.toEulerAngles("YawPitchRoll")
        self.assertAlmostEqual(round(ypr[2], 9), 160.0)

    def testIntegerResultBeyondCLong(self):
        # An integer result of Python arithmetic that does not fit in a C long
        # (32 bits on Windows) gave -1 and a pending OverflowError
        obj = self.Doc.addObject("App::FeatureTest", "BigInteger")
        obj.setExpression("Float", "2^40")
        self.Doc.recompute()
        self.assertNotIn("Invalid", obj.State)
        self.assertEqual(obj.Float, 2**40)
        self.assertEqual(obj.evalExpression("2^40 + 1"), 2**40 + 1)
        self.assertEqual(obj.evalExpression("-(2^70)"), -float(2**70))

    def testIntegerPropertyOutOfRange(self):
        # A value outside the C long range must not be stored as an arbitrary integer.
        # PropertyInteger holds a C long: 64 bits on Linux and macOS, 32 bits on Windows.
        import ctypes

        expressions = ["2^70", "1e30", "-1e30"]
        if ctypes.sizeof(ctypes.c_long) == 4:
            expressions += ["2^40", "1e12"]
        for expression in expressions:
            with self.subTest(expression=expression):
                obj = self.Doc.addObject("App::FeatureTest", "OutOfRange")
                obj.Integer = 7
                obj.setExpression("Integer", expression)
                self.Doc.recompute()
                self.assertIn("Invalid", obj.State)
                self.assertEqual(obj.Integer, 7)
                obj.setExpression("Integer", "2^30")
                self.Doc.recompute()
                self.assertNotIn("Invalid", obj.State)
                self.assertEqual(obj.Integer, 2**30)
                self.Doc.removeObject(obj.Name)

    def testIssue4649(self):
        class Cls:
            def __init__(self, obj):
                self.MonitorChanges = False
                obj.Proxy = self
                obj.addProperty("App::PropertyFloat", "propA", "group")
                obj.addProperty("App::PropertyFloat", "propB", "group")
                self.MonitorChanges = True
                obj.setExpression("propB", "6*9")

            def onChanged(self, obj, prop):
                print("onChanged", self, obj, prop)
                if self.MonitorChanges and prop == "propA":
                    print("Removing expression...")
                    obj.setExpression("propB", None)

        obj = self.Doc.addObject("App::DocumentObjectGroupPython", "Obj")
        Cls(obj)
        self.Doc.openTransaction("Expression")
        obj.setExpression("propA", "42")
        self.Doc.recompute()
        self.Doc.commitTransaction()
        self.assertTrue(("propB", None) in obj.ExpressionEngine)
        self.assertTrue(("propA", "42") in obj.ExpressionEngine)

        self.Doc.undo()
        self.assertFalse(("propB", None) in obj.ExpressionEngine)
        self.assertFalse(("propA", "42") in obj.ExpressionEngine)

        self.Doc.redo()
        self.assertTrue(("propB", None) in obj.ExpressionEngine)
        self.assertTrue(("propA", "42") in obj.ExpressionEngine)

        self.Doc.recompute()
        obj.ExpressionEngine

        TempPath = tempfile.gettempdir()
        SaveName = TempPath + os.sep + "ExpressionTests.FCStd"
        self.Doc.saveAs(SaveName)
        FreeCAD.closeDocument(self.Doc.Name)
        self.Doc = FreeCAD.openDocument(SaveName)

    def testMergeProjectRelabelsLabelReferences(self):
        # issue #6284: merging a project whose objects get new unique labels
        # must update the label references (<<label>>) in the merged expressions
        params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Document")
        hadDuplicateLabels = "DuplicateLabels" in params.GetBools()
        oldDuplicateLabels = params.GetBool("DuplicateLabels", False)
        params.SetBool("DuplicateLabels", False)
        fileName = os.path.join(tempfile.gettempdir(), "MergeLabelReferences.FCStd")
        try:
            src = FreeCAD.newDocument("MergeLabelSource")
            box = src.addObject("App::FeatureTest", "Box")
            box.Label = "Cube"
            box.Float = 3.0
            other = src.addObject("App::FeatureTest", "Other")
            other.Float = 5.0
            user = src.addObject("App::FeatureTest", "User")
            user.setExpression("Float", "<<Cube>>.Float")
            user.setExpression("Integer", "Other.Float")
            src.saveAs(fileName)
            FreeCAD.closeDocument(src.Name)

            self.Doc.mergeProject(fileName)
            self.Doc.mergeProject(fileName)
            self.Doc.recompute()
            self.assertEqual(self.Doc.getObject("Box001").Label, "Cube001")
            first = self.Doc.getObject("User")
            second = self.Doc.getObject("User001")
            self.assertIn(("Float", "<<Cube>>.Float"), first.ExpressionEngine)
            self.assertIn(("Float", "<<Cube001>>.Float"), second.ExpressionEngine)
            self.assertIn(("Integer", "Other001.Float"), second.ExpressionEngine)

            # the merged expression follows the merged object, not the first copy
            self.Doc.getObject("Box001").Float = 7.0
            self.Doc.recompute()
            self.assertEqual(first.Float, 3.0)
            self.assertEqual(second.Float, 7.0)

            # copying objects within the document keeps working as before:
            # a copied reference follows the copied object, an uncopied one
            # keeps pointing to the original object
            copiedBox, copiedUser = self.Doc.copyObject([self.Doc.getObject("Box"), first])
            self.assertNotEqual(copiedBox.Label, "Cube")
            self.assertIn(("Float", "<<%s>>.Float" % copiedBox.Label), copiedUser.ExpressionEngine)
            alone = self.Doc.copyObject(second)
            self.assertIn(("Float", "<<Cube001>>.Float"), alone.ExpressionEngine)
        finally:
            if hadDuplicateLabels:
                params.SetBool("DuplicateLabels", oldDuplicateLabels)
            else:
                params.RemBool("DuplicateLabels")
            if os.path.exists(fileName):
                os.remove(fileName)

    def testCyclicDependencyOnPlacement(self):
        obj = self.Doc.addObject("App::FeaturePython", "Python")
        obj.addProperty("App::PropertyPlacement", "Placement")
        obj.setExpression(".Placement.Base.x", ".Placement.Base.y + 10mm")
        with self.assertRaises(RuntimeError):
            obj.setExpression(".Placement.Base.y", ".Placement.Base.x + 10mm")

    def testConstructorFunctionsWithInvalidArguments(self):
        # vector(), placement(), matrix() and create() ignored a failing
        # constructor and returned the default object with a Python error
        # still pending (a SystemError, or a stray TypeError later on)
        obj = self.Doc.addObject("App::FeaturePython", "Python")
        for expression in (
            "vector(1; 2; <<a>>)",
            "placement(<<x>>)",
            "matrix(<<a>>)",
            "create(<<vector>>; 1; <<a>>)",
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(Exception) as context:
                    obj.evalExpression(expression)
                self.assertNotIsInstance(context.exception, SystemError)
        self.assertEqual(obj.evalExpression("vector(1; 2; 3)"), FreeCAD.Vector(1, 2, 3))
        self.assertEqual(
            obj.evalExpression("create(<<vector>>; 1; 2; 3)"), FreeCAD.Vector(1, 2, 3)
        )
        self.assertTrue(
            obj.evalExpression("placement(vector(1; 2; 3); rotation(vector(0; 0; 1); 90))").isSame(
                FreeCAD.Placement(FreeCAD.Vector(1, 2, 3), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90))
            )
        )
        self.assertEqual(
            obj.evalExpression("matrix(1; 2; 3; 4; 5; 6; 7; 8; 9; 10; 11; 12; 13; 14; 15; 16)"),
            FreeCAD.Matrix(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
        )

    def _addValueObject(self, name):
        obj = self.Doc.addObject("App::FeaturePython", name)
        obj.addProperty("App::PropertyFloat", "Value")
        return obj

    def testUndoDeleteRestoresExpressionDependencies(self):
        # undoing the deletion of an object holding an expression restored its
        # property back links only: its OutList and the InList of the referenced
        # object stayed empty
        self.Doc.UndoMode = 1
        source = self._addValueObject("Source")
        dependent = self._addValueObject("Dependent")
        dependent.setExpression("Value", "Source.Value")
        self.Doc.recompute()
        # the expression engine is listed twice in OutList (as a link property
        # and as the expression engine), so compare with the state before deletion
        outList = [o.Name for o in dependent.OutList]
        self.assertIn("Source", outList)
        self.assertEqual([o.Name for o in source.InList], ["Dependent"])
        self.assertEqual(len(source.InListProp), 1)
        self.Doc.openTransaction("Delete dependent")
        self.Doc.removeObject("Dependent")
        self.Doc.commitTransaction()
        self.assertEqual(source.InList, [])

        for redo in (True, False):
            self.Doc.undo()
            dependent = self.Doc.getObject("Dependent")
            self.assertEqual([o.Name for o in dependent.OutList], outList)
            self.assertEqual([o.Name for o in source.InList], ["Dependent"])
            self.assertEqual(len(source.InListProp), 1)
            if redo:
                self.Doc.redo()
                self.assertIsNone(self.Doc.getObject("Dependent"))
                self.assertEqual(source.InList, [])
                self.assertEqual(source.InListProp, [])

        source.Value = 3.5
        self.Doc.recompute()
        self.assertEqual(dependent.Value, 3.5)

    def testUndoDeleteThenClearExpressionLeavesNoBackLink(self):
        # undo registered the back links of the restored object twice (from a
        # stale out-list and again from the restored expression); removing the
        # expression dropped only one, and destroying the object left dangling
        # pointers in the InList of the referenced object (access violation)
        self.Doc.UndoMode = 1
        source = self._addValueObject("Source")
        dependent = self._addValueObject("Dependent")
        dependent.setExpression("Value", "Source.Value * 2")
        self.Doc.recompute()
        self.Doc.openTransaction("Delete dependent")
        self.Doc.removeObject("Dependent")
        self.Doc.commitTransaction()
        self.Doc.undo()
        dependent = self.Doc.getObject("Dependent")
        self.assertEqual([o.Name for o in source.InList], ["Dependent"])
        self.assertEqual(len(source.InListProp), 1)

        dependent.setExpression("Value", None)
        self.Doc.recompute()
        self.assertEqual(source.InList, [])
        self.assertEqual(source.InListProp, [])

        self.Doc.UndoMode = 0
        self.Doc.removeObject("Dependent")
        self.assertEqual(source.InList, [])
        self.assertEqual(source.InListProp, [])

    def testUndoDeleteAfterExpressionDependencyDestroyed(self):
        # the deleted object kept pointers to the objects its expression used:
        # once such an object was destroyed outside any transaction, undoing the
        # deletion accessed the destroyed object (access violation)
        self.Doc.UndoMode = 1
        self._addValueObject("Source")
        dependent = self._addValueObject("Dependent")
        dependent.setExpression("Value", "Source.Value")
        self.Doc.recompute()
        self.Doc.openTransaction("Delete dependent")
        self.Doc.removeObject("Dependent")
        self.Doc.commitTransaction()
        # no transaction is open: the object is destroyed at once
        self.Doc.removeObject("Source")
        # reuse the freed memory
        names = [self._addValueObject("Other%d" % i).Name for i in range(300)]
        for name in names:
            self.Doc.removeObject(name)

        self.Doc.undo()
        dependent = self.Doc.getObject("Dependent")
        self.assertEqual(dependent.OutList, [])
        self.assertEqual(dependent.OutListProp, [])
        self.assertIn(("Value", "Source.Value"), dependent.ExpressionEngine)

    def testSliceOfProperty(self):
        # A literal slice of a property was turned into an identifier range that
        # lost a missing end ([1:] became [1:0], an empty list) and a slice with
        # only a step ([::2]) lost the step.
        obj = self.Doc.addObject("App::FeaturePython", "Obj")
        obj.addProperty("App::PropertyStringList", "SL").SL = ["a", "b", "c", "d"]
        obj.addProperty("App::PropertyFloatList", "FL").FL = [1, 2, 3, 4]
        obj.addProperty("App::PropertyFloat", "Value")
        lst = ["a", "b", "c", "d"]
        for expr, expected in (
            ("SL[1:]", lst[1:]),
            ("SL[3:]", lst[3:]),
            ("SL[-1:]", lst[-1:]),
            ("SL[:2]", lst[:2]),
            ("SL[1:3]", lst[1:3]),
            ("SL[::2]", lst[::2]),
            ("SL[::-1]", lst[::-1]),
            ("SL[::1]", lst[::1]),
            ("SL[1::2]", lst[1::2]),
            ("SL[2:0:-1]", lst[2:0:-1]),
            ("Obj.SL[1:]", lst[1:]),
        ):
            self.assertEqual(obj.evalExpression(expr), expected, expr)
        with self.assertRaises(Exception):
            obj.evalExpression("SL[::0]")

        obj.setExpression("Value", "FL[1:][0]")
        self.assertEqual(obj.ExpressionEngine, [("Value", "FL[1:][0]")])
        self.Doc.recompute()
        self.assertEqual(obj.Value, 2)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument(self.Doc.Name)


class DocumentObserverCases(unittest.TestCase):
    class Observer:
        def __init__(self):
            self.clear()

        def clear(self):
            self.signal = []
            self.parameter = []
            self.parameter2 = []

        def slotCreatedDocument(self, doc):
            self.signal.append("DocCreated")
            self.parameter.append(doc)

        def slotDeletedDocument(self, doc):
            self.signal.append("DocDeleted")
            self.parameter.append(doc)

        def slotRelabelDocument(self, doc):
            self.signal.append("DocRelabled")
            self.parameter.append(doc)

        def slotActivateDocument(self, doc):
            self.signal.append("DocActivated")
            self.parameter.append(doc)

        def slotRecomputedDocument(self, doc):
            self.signal.append("DocRecomputed")
            self.parameter.append(doc)

        def slotUndoDocument(self, doc):
            self.signal.append("DocUndo")
            self.parameter.append(doc)

        def slotRedoDocument(self, doc):
            self.signal.append("DocRedo")
            self.parameter.append(doc)

        def slotOpenTransaction(self, doc, name):
            self.signal.append("DocOpenTransaction")
            self.parameter.append(doc)
            self.parameter2.append(name)

        def slotCommitTransaction(self, doc):
            self.signal.append("DocCommitTransaction")
            self.parameter.append(doc)

        def slotAbortTransaction(self, doc):
            self.signal.append("DocAbortTransaction")
            self.parameter.append(doc)

        def slotBeforeChangeDocument(self, doc, prop):
            self.signal.append("DocBeforeChange")
            self.parameter.append(doc)
            self.parameter2.append(prop)

        def slotChangedDocument(self, doc, prop):
            self.signal.append("DocChanged")
            self.parameter.append(doc)
            self.parameter2.append(prop)

        def slotCreatedObject(self, obj):
            self.signal.append("ObjCreated")
            self.parameter.append(obj)

        def slotDeletedObject(self, obj):
            self.signal.append("ObjDeleted")
            self.parameter.append(obj)

        def slotChangedObject(self, obj, prop):
            self.signal.append("ObjChanged")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotBeforeChangeObject(self, obj, prop):
            self.signal.append("ObjBeforeChange")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotRecomputedObject(self, obj):
            self.signal.append("ObjRecomputed")
            self.parameter.append(obj)

        def slotAppendDynamicProperty(self, obj, prop):
            self.signal.append("ObjAddDynProp")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotRemoveDynamicProperty(self, obj, prop):
            self.signal.append("ObjRemoveDynProp")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotChangePropertyEditor(self, obj, prop):
            self.signal.append("ObjChangePropEdit")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotStartSaveDocument(self, obj, name):
            self.signal.append("DocStartSave")
            self.parameter.append(obj)
            self.parameter2.append(name)

        def slotFinishSaveDocument(self, obj, name):
            self.signal.append("DocFinishSave")
            self.parameter.append(obj)
            self.parameter2.append(name)

        def slotBeforeAddingDynamicExtension(self, obj, extension):
            self.signal.append("ObjBeforeDynExt")
            self.parameter.append(obj)
            self.parameter2.append(extension)

        def slotAddedDynamicExtension(self, obj, extension):
            self.signal.append("ObjDynExt")
            self.parameter.append(obj)
            self.parameter2.append(extension)

    class GuiObserver:
        def __init__(self):
            self.clear()

        def clear(self):
            self.signal = []
            self.parameter = []
            self.parameter2 = []

        def slotCreatedDocument(self, doc):
            self.signal.append("DocCreated")
            self.parameter.append(doc)

        def slotDeletedDocument(self, doc):
            self.signal.append("DocDeleted")
            self.parameter.append(doc)

        def slotRelabelDocument(self, doc):
            self.signal.append("DocRelabled")
            self.parameter.append(doc)

        def slotRenameDocument(self, doc):
            self.signal.append("DocRenamed")
            self.parameter.append(doc)

        def slotActivateDocument(self, doc):
            self.signal.append("DocActivated")
            self.parameter.append(doc)

        def slotCreatedObject(self, obj):
            self.signal.append("ObjCreated")
            self.parameter.append(obj)

        def slotDeletedObject(self, obj):
            self.signal.append("ObjDeleted")
            self.parameter.append(obj)

        def slotChangedObject(self, obj, prop):
            self.signal.append("ObjChanged")
            self.parameter.append(obj)
            self.parameter2.append(prop)

        def slotInEdit(self, obj):
            self.signal.append("ObjInEdit")
            self.parameter.append(obj)

        def slotResetEdit(self, obj):
            self.signal.append("ObjResetEdit")
            self.parameter.append(obj)

    def setUp(self):
        self.Obs = self.Observer()
        FreeCAD.addDocumentObserver(self.Obs)

    def testRemoveObserver(self):
        FreeCAD.removeDocumentObserver(self.Obs)
        self.Obs.clear()
        self.Doc1 = FreeCAD.newDocument("Observer")
        FreeCAD.closeDocument(self.Doc1.Name)
        self.assertEqual(len(self.Obs.signal), 0)
        self.assertEqual(len(self.Obs.parameter2), 0)
        self.assertEqual(len(self.Obs.signal), 0)
        FreeCAD.addDocumentObserver(self.Obs)

    def testSave(self):
        TempPath = tempfile.gettempdir()
        SaveName = TempPath + os.sep + "SaveRestoreTests.FCStd"
        self.Doc1 = FreeCAD.newDocument("Observer1")
        self.Doc1.saveAs(SaveName)
        self.assertEqual(self.Obs.signal.pop(), "DocFinishSave")
        self.assertEqual(self.Obs.parameter2.pop(), self.Doc1.FileName)
        self.assertEqual(self.Obs.signal.pop(), "DocStartSave")
        self.assertEqual(self.Obs.parameter2.pop(), self.Doc1.FileName)
        FreeCAD.closeDocument(self.Doc1.Name)

    def testDefaultLabelIsAnnounced(self):
        # https://github.com/FreeCAD/FreeCAD/issues/14862
        # A new document whose label equals the default label ("Unnamed") must be announced
        # like any other, otherwise the GUI never marks it modified on document property changes.
        self.Doc1 = FreeCAD.newDocument("ObserverDefaultLabel", "Unnamed")
        try:
            self.assertEqual(self.Doc1.Label, "Unnamed")
            self.assertIn("DocRelabled", self.Obs.signal)
            self.assertIs(self.Obs.parameter[self.Obs.signal.index("DocRelabled")], self.Doc1)
            if FreeCAD.GuiUp:
                guiDoc = FreeCAD.Gui.getDocument(self.Doc1.Name)
                guiDoc.Modified = False
                self.Doc1.Comment = "Issue 14862"
                self.assertTrue(guiDoc.Modified)
        finally:
            FreeCAD.closeDocument(self.Doc1.Name)

    def testDocument(self):
        # in case another document already exists then the tests cannot
        # be done reliably
        if FreeCAD.GuiUp and FreeCAD.activeDocument():
            return

        # testing document level signals
        self.Doc1 = FreeCAD.newDocument("Observer1")
        if FreeCAD.GuiUp:
            self.assertEqual(self.Obs.signal.pop(0), "DocActivated")
            self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.signal.pop(0), "DocCreated")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.signal.pop(0), "DocBeforeChange")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.parameter2.pop(0), "Label")
        self.assertEqual(self.Obs.signal.pop(0), "DocChanged")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.parameter2.pop(0), "Label")
        self.assertEqual(self.Obs.signal.pop(0), "DocRelabled")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        self.Doc2 = FreeCAD.newDocument("Observer2")
        if FreeCAD.GuiUp:
            self.assertEqual(self.Obs.signal.pop(0), "DocActivated")
            self.assertTrue(self.Obs.parameter.pop(0) is self.Doc2)
        self.assertEqual(self.Obs.signal.pop(0), "DocCreated")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc2)
        self.assertEqual(self.Obs.signal.pop(0), "DocBeforeChange")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc2)
        self.assertEqual(self.Obs.parameter2.pop(0), "Label")
        self.assertEqual(self.Obs.signal.pop(0), "DocChanged")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc2)
        self.assertEqual(self.Obs.parameter2.pop(0), "Label")
        self.assertEqual(self.Obs.signal.pop(0), "DocRelabled")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc2)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        FreeCAD.setActiveDocument("Observer1")
        self.assertEqual(self.Obs.signal.pop(), "DocActivated")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        # Must set Doc2 as active document before start transaction test. If not,
        # then a transaction will be auto created inside the active document if a
        # new transaction is triggered from a non active document
        FreeCAD.setActiveDocument("Observer2")
        self.assertEqual(self.Obs.signal.pop(), "DocActivated")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        self.Doc2.openTransaction("test")
        # openTransaction() now only setup pending transaction, which will only be
        # created when there is actual change
        self.Doc2.addObject("App::FeatureTest", "test")
        self.assertEqual(self.Obs.signal[0], "DocOpenTransaction")
        self.assertEqual(self.Obs.signal.count("DocOpenTransaction"), 1)
        self.assertTrue(self.Obs.parameter[0] is self.Doc2)
        self.assertEqual(self.Obs.parameter2[0], "test")
        self.Obs.clear()

        self.Doc2.commitTransaction()
        self.assertEqual(self.Obs.signal.pop(), "DocCommitTransaction")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        self.Doc2.openTransaction("test2")
        # openTransaction() now only setup pending transaction, which will only be
        # created when there is actual change
        self.Doc2.addObject("App::FeatureTest", "test")
        self.assertEqual(self.Obs.signal[0], "DocOpenTransaction")
        self.assertEqual(self.Obs.signal.count("DocOpenTransaction"), 1)
        self.assertTrue(self.Obs.parameter[0] is self.Doc2)
        self.assertEqual(self.Obs.parameter2[0], "test2")
        # there will be other signals because of the addObject()
        self.Obs.clear()

        self.Doc2.abortTransaction()
        self.assertEqual(self.Obs.signal.pop(), "DocAbortTransaction")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        # there will be other signals because of aborting the above addObject()
        self.Obs.clear()

        self.Doc2.undo()
        self.assertEqual(self.Obs.signal.pop(), "DocUndo")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        # there will be other signals because undoing the above addObject()
        self.Obs.clear()

        self.Doc2.redo()
        self.assertEqual(self.Obs.signal.pop(), "DocRedo")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        # there will be other signals because redoing the above addObject()
        self.Obs.clear()

        self.Doc1.Comment = "test comment"
        self.assertEqual(self.Obs.signal.pop(0), "DocBeforeChange")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.parameter2.pop(0), "Comment")
        self.assertEqual(self.Obs.signal.pop(0), "DocChanged")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertEqual(self.Obs.parameter2.pop(0), "Comment")

        FreeCAD.closeDocument(self.Doc2.Name)
        self.assertEqual(self.Obs.signal.pop(), "DocDeleted")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc2)
        if FreeCAD.GuiUp and not FreeCAD.Gui.HasQtBug_129596:
            # only has document activated signal when running in GUI mode
            self.assertEqual(self.Obs.signal.pop(), "DocActivated")
            self.assertTrue(self.Obs.parameter.pop() is self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        FreeCAD.closeDocument(self.Doc1.Name)
        self.assertEqual(self.Obs.signal.pop(), "DocDeleted")
        self.assertEqual(self.Obs.parameter.pop(), self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

    def testObject(self):
        # testing signal on object changes

        self.Doc1 = FreeCAD.newDocument("Observer1")
        self.Obs.clear()

        obj = self.Doc1.addObject("App::DocumentObject", "obj")
        self.assertTrue(self.Obs.signal.pop() == "ObjCreated")
        self.assertTrue(self.Obs.parameter.pop() is obj)
        # there are multiple object change signals
        self.Obs.clear()

        obj.Label = "myobj"
        self.assertTrue(self.Obs.signal.pop(0) == "ObjBeforeChange")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(self.Obs.parameter2.pop(0) == "Label")
        self.assertTrue(self.Obs.signal.pop(0) == "ObjChanged")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(self.Obs.parameter2.pop(0) == "Label")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        obj.enforceRecompute()
        obj.recompute()
        self.assertTrue(self.Obs.signal.pop(0) == "ObjRecomputed")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        obj.enforceRecompute()
        self.Doc1.recompute()
        self.assertTrue(self.Obs.signal.pop(0) == "ObjRecomputed")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(self.Obs.signal.pop(0) == "DocRecomputed")
        self.assertTrue(self.Obs.parameter.pop(0) is self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        FreeCAD.ActiveDocument.removeObject(obj.Name)
        self.assertTrue(self.Obs.signal.pop(0) == "ObjDeleted")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        pyobj = self.Doc1.addObject("App::FeaturePython", "pyobj")
        self.Obs.clear()
        pyobj.addProperty("App::PropertyLength", "Prop", "Group", "test property")
        self.assertTrue(self.Obs.signal.pop() == "ObjAddDynProp")
        self.assertTrue(self.Obs.parameter.pop() is pyobj)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        pyobj.setEditorMode("Prop", ["ReadOnly"])
        self.assertTrue(self.Obs.signal.pop() == "ObjChangePropEdit")
        self.assertTrue(self.Obs.parameter.pop() is pyobj)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        pyobj.removeProperty("Prop")
        self.assertTrue(self.Obs.signal.pop() == "ObjRemoveDynProp")
        self.assertTrue(self.Obs.parameter.pop() is pyobj)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        pyobj.addExtension("App::GroupExtensionPython")
        self.assertTrue(self.Obs.signal.pop() == "ObjDynExt")
        self.assertTrue(self.Obs.parameter.pop() is pyobj)
        self.assertTrue(self.Obs.parameter2.pop() == "App::GroupExtensionPython")
        self.assertTrue(self.Obs.signal.pop(0) == "ObjBeforeDynExt")
        self.assertTrue(self.Obs.parameter.pop(0) is pyobj)
        self.assertTrue(self.Obs.parameter2.pop(0) == "App::GroupExtensionPython")
        # a proxy property was changed, hence those events are also in the signal list
        self.Obs.clear()

        FreeCAD.closeDocument(self.Doc1.Name)
        self.Obs.clear()

    def testUndoDisabledDocument(self):

        # testing document level signals
        self.Doc1 = FreeCAD.newDocument("Observer1")
        self.Obs.clear()

        self.Doc1.openTransaction("test")
        self.Doc1.commitTransaction()
        self.Doc1.undo()
        self.Doc1.redo()
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)

        FreeCAD.closeDocument(self.Doc1.Name)
        self.Obs.clear()

    def testGuiObserver(self):

        if not FreeCAD.GuiUp:
            return

        # in case another document already exists then the tests cannot
        # be done reliably
        if FreeCAD.activeDocument():
            return

        self.GuiObs = self.GuiObserver()
        FreeCAD.Gui.addDocumentObserver(self.GuiObs)
        self.Doc1 = FreeCAD.newDocument("Observer1")
        self.GuiDoc1 = FreeCAD.Gui.getDocument(self.Doc1.Name)
        self.Obs.clear()
        self.assertTrue(self.GuiObs.signal.pop(0) == "DocCreated")
        self.assertTrue(self.GuiObs.parameter.pop(0) is self.GuiDoc1)
        self.assertTrue(self.GuiObs.signal.pop(0) == "DocActivated")
        self.assertTrue(self.GuiObs.parameter.pop(0) is self.GuiDoc1)
        self.assertTrue(self.GuiObs.signal.pop(0) == "DocRelabled")
        self.assertTrue(self.GuiObs.parameter.pop(0) is self.GuiDoc1)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        self.Doc1.Label = "test"
        self.assertTrue(self.Obs.signal.pop() == "DocRelabled")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc1)
        # not interested in the change signals
        self.Obs.clear()
        self.assertTrue(self.GuiObs.signal.pop(0) == "DocRelabled")
        self.assertTrue(self.GuiObs.parameter.pop(0) is self.GuiDoc1)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        FreeCAD.setActiveDocument(self.Doc1.Name)
        self.assertTrue(self.Obs.signal.pop() == "DocActivated")
        self.assertTrue(self.Obs.parameter.pop() is self.Doc1)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(self.GuiObs.signal.pop() == "DocActivated")
        self.assertTrue(self.GuiObs.parameter.pop() is self.GuiDoc1)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        obj = self.Doc1.addObject("App::FeaturePython", "obj")
        self.assertTrue(self.Obs.signal.pop() == "ObjCreated")
        self.assertTrue(self.Obs.parameter.pop() is obj)
        # there are multiple object change signals
        self.Obs.clear()
        self.assertTrue(self.GuiObs.signal.pop() == "ObjCreated")
        self.assertTrue(self.GuiObs.parameter.pop() is obj.ViewObject)

        # There are object change signals, caused by sync of obj.Visibility. Same below.
        self.GuiObs.clear()

        obj.ViewObject.Visibility = False
        self.assertTrue(self.Obs.signal.pop() == "ObjChanged")
        self.assertTrue(self.Obs.parameter.pop() is obj)
        self.assertTrue(self.Obs.parameter2.pop() == "Visibility")
        self.assertTrue(self.Obs.signal.pop() == "ObjBeforeChange")
        self.assertTrue(self.Obs.parameter.pop() is obj)
        self.assertTrue(self.Obs.parameter2.pop() == "Visibility")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(self.GuiObs.signal.pop(0) == "ObjChanged")
        self.assertTrue(self.GuiObs.parameter.pop(0) is obj.ViewObject)
        self.assertTrue(self.GuiObs.parameter2.pop(0) == "Visibility")
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        obj.ViewObject.addProperty("App::PropertyLength", "Prop", "Group", "test property")
        self.assertTrue(self.Obs.signal.pop() == "ObjAddDynProp")
        self.assertTrue(self.Obs.parameter.pop() is obj.ViewObject)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        obj.ViewObject.setEditorMode("Prop", ["ReadOnly"])
        self.assertTrue(self.Obs.signal.pop() == "ObjChangePropEdit")
        self.assertTrue(self.Obs.parameter.pop() is obj.ViewObject)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        obj.ViewObject.removeProperty("Prop")
        self.assertTrue(self.Obs.signal.pop() == "ObjRemoveDynProp")
        self.assertTrue(self.Obs.parameter.pop() is obj.ViewObject)
        self.assertTrue(self.Obs.parameter2.pop() == "Prop")
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        self.GuiDoc1.setEdit("obj", 0)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(self.GuiObs.signal.pop(0) == "ObjInEdit")
        self.assertTrue(self.GuiObs.parameter.pop(0) is obj.ViewObject)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        self.GuiDoc1.resetEdit()
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(self.GuiObs.signal.pop(0) == "ObjResetEdit")
        self.assertTrue(self.GuiObs.parameter.pop(0) is obj.ViewObject)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        obj.ViewObject.addExtension("Gui::ViewProviderGroupExtensionPython")
        self.assertTrue(self.Obs.signal.pop() == "ObjDynExt")
        self.assertTrue(self.Obs.parameter.pop() is obj.ViewObject)
        self.assertTrue(self.Obs.parameter2.pop() == "Gui::ViewProviderGroupExtensionPython")
        self.assertTrue(self.Obs.signal.pop() == "ObjBeforeDynExt")
        self.assertTrue(self.Obs.parameter.pop() is obj.ViewObject)
        self.assertTrue(self.Obs.parameter2.pop() == "Gui::ViewProviderGroupExtensionPython")
        # a proxy property was changed, hence those events are also in the signal list (but of GUI observer)
        self.GuiObs.clear()

        vo = obj.ViewObject
        FreeCAD.ActiveDocument.removeObject(obj.Name)
        self.assertTrue(self.Obs.signal.pop(0) == "ObjDeleted")
        self.assertTrue(self.Obs.parameter.pop(0) is obj)
        self.assertTrue(not self.Obs.signal and not self.Obs.parameter and not self.Obs.parameter2)
        self.assertTrue(self.GuiObs.signal.pop() == "ObjDeleted")
        self.assertTrue(self.GuiObs.parameter.pop() is vo)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        FreeCAD.closeDocument(self.Doc1.Name)
        self.Obs.clear()
        self.assertTrue(self.GuiObs.signal.pop() == "DocDeleted")
        self.assertTrue(self.GuiObs.parameter.pop() is self.GuiDoc1)
        self.assertTrue(
            not self.GuiObs.signal and not self.GuiObs.parameter and not self.GuiObs.parameter2
        )

        FreeCAD.Gui.removeDocumentObserver(self.GuiObs)
        self.GuiObs.clear()

    def tearDown(self):
        # closing doc
        FreeCAD.removeDocumentObserver(self.Obs)
        self.Obs.clear()
        self.Obs = None


class FeatureTestColumn(unittest.TestCase):
    def setUp(self):
        doc = FreeCAD.newDocument("TestColumn")
        self.obj = doc.addObject("App::FeatureTestColumn", "Column")

    def testEmpty(self):
        value = self.obj.Value
        self.obj.Column = ""
        self.assertFalse(self.obj.recompute())
        self.assertEqual(self.obj.Value, value)

    def testA(self):
        self.obj.Column = "A"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 0)

    def testZ(self):
        self.obj.Column = "Z"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 25)

    def testAA(self):
        self.obj.Column = "AA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 26)

    def testAB(self):
        self.obj.Column = "AB"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 27)

    def testAZ(self):
        self.obj.Column = "AZ"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 51)

    def testBA(self):
        self.obj.Column = "BA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 52)

    def testCB(self):
        self.obj.Column = "CB"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 79)

    def testZA(self):
        self.obj.Column = "ZA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 676)

    def testZZ(self):
        self.obj.Column = "ZZ"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 701)

    def testAAA(self):
        self.obj.Column = "AAA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 702)

    def testAAZ(self):
        self.obj.Column = "AAZ"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 727)

    def testCBA(self):
        self.obj.Column = "CBA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 2080)

    def testAZA(self):
        self.obj.Column = "AZA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 1352)

    def testZZA(self):
        self.obj.Column = "ZZA"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 18252)

    def testZZZ(self):
        self.obj.Column = "ZZZ"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 18277)

    def testALL(self):
        self.obj.Column = "ALL"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 999)

    def testAb(self):
        value = self.obj.Value
        self.obj.Column = "Ab"
        self.assertFalse(self.obj.recompute())
        self.assertEqual(self.obj.Value, value)

    def testABCD(self):
        value = self.obj.Value
        self.obj.Column = "ABCD"
        self.assertFalse(self.obj.recompute())
        self.assertEqual(self.obj.Value, value)

    def testEmptySilent(self):
        self.obj.Column = ""
        self.obj.Silent = True
        self.assertTrue(self.obj.recompute())
        self.assertEqual(self.obj.Value, -1)

    def testAbSilent(self):
        self.obj.Column = "Ab"
        self.obj.Silent = True
        self.assertTrue(self.obj.recompute())
        self.assertEqual(self.obj.Value, -1)

    def testABCDSilent(self):
        self.obj.Column = "ABCD"
        self.obj.Silent = True
        self.assertTrue(self.obj.recompute())
        self.assertEqual(self.obj.Value, -1)

    def tearDown(self):
        FreeCAD.closeDocument("TestColumn")


class FeatureTestRow(unittest.TestCase):
    def setUp(self):
        doc = FreeCAD.newDocument("TestRow")
        self.obj = doc.addObject("App::FeatureTestRow", "Row")

    def testEmpty(self):
        self.obj.Silent = True
        self.obj.Row = ""
        self.obj.recompute()
        self.assertEqual(self.obj.Value, -1)

    def testA(self):
        self.obj.Silent = True
        self.obj.Row = "A"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, -1)

    def testException(self):
        value = self.obj.Value
        self.obj.Row = "A"
        self.assertFalse(self.obj.recompute())
        self.assertEqual(self.obj.Value, value)

    def test0(self):
        self.obj.Silent = True
        self.obj.Row = "0"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, -1)

    def test1(self):
        self.obj.Silent = True
        self.obj.Row = "1"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 0)

    def test16384(self):
        self.obj.Silent = True
        self.obj.Row = "16384"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, 16383)

    def test16385(self):
        self.obj.Silent = True
        self.obj.Row = "16385"
        self.obj.recompute()
        self.assertEqual(self.obj.Value, -1)

    def tearDown(self):
        FreeCAD.closeDocument("TestRow")


class FeatureTestAbsAddress(unittest.TestCase):
    def setUp(self):
        doc = FreeCAD.newDocument("TestAbsAddress")
        self.obj = doc.addObject("App::FeatureTestAbsAddress", "Cell")

    def testAbsoluteA12(self):
        self.obj.Address = "$A$12"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, True)

    def testAbsoluteA13(self):
        self.obj.Address = "A$13"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, True)

    def testAbsoluteAA13(self):
        self.obj.Address = "AA$13"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, True)

    def testAbsoluteZZ12(self):
        self.obj.Address = "$ZZ$12"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, True)

    def testAbsoluteABC1(self):
        self.obj.Address = "$ABC1"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, False)

    def testAbsoluteABC2(self):
        self.obj.Address = "ABC$2"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, False)

    def testRelative(self):
        self.obj.Address = "A1"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, False)

    def testInvalid(self):
        self.obj.Address = "A"
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, False)

    def testEmpty(self):
        self.obj.Address = ""
        self.obj.recompute()
        self.assertEqual(self.obj.Valid, False)

    def tearDown(self):
        FreeCAD.closeDocument("TestAbsAddress")


class FeatureTestAttribute(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestAttribute")

    def testValidAttribute(self):
        obj = self.doc.addObject("App::FeatureTestAttribute", "Attribute")
        obj.Object = obj
        obj.Attribute = "Name"
        self.doc.recompute()
        self.assertIn("Up-to-date", obj.State)

    def testInvalidAttribute(self):
        obj = self.doc.addObject("App::FeatureTestAttribute", "Attribute")
        obj.Object = obj
        obj.Attribute = "Name123"
        self.doc.recompute()
        self.assertIn("Invalid", obj.State)
        self.assertIn("Touched", obj.State)

    def testRemoval(self):
        obj = self.doc.addObject("App::FeatureTestAttribute", "Attribute")
        obj.Object = obj
        self.assertEqual(self.doc.removeObject("Attribute"), None)

    def tearDown(self):
        FreeCAD.closeDocument("TestAttribute")


class DocumentAutoCreatedCases(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestDoc")

    def tearDown(self):
        for doc_name in FreeCAD.listDocuments().keys():
            FreeCAD.closeDocument(doc_name)

    def test_set_get_auto_created(self):
        self.doc.setAutoCreated(True)
        self.assertTrue(self.doc.isAutoCreated(), "autoCreated flag should be True")

        self.doc.setAutoCreated(False)
        self.assertFalse(self.doc.isAutoCreated(), "autoCreated flag should be False")

    def test_auto_created_document_closes_on_opening_existing_document(self):
        self.doc.setAutoCreated(True)
        self.assertEqual(len(self.doc.Objects), 0)
        saved_doc = FreeCAD.newDocument("SavedDoc")
        file_path = tempfile.gettempdir() + os.sep + "SavedDoc.FCStd"
        saved_doc.saveAs(file_path)
        FreeCAD.closeDocument("SavedDoc")
        FreeCAD.setActiveDocument("TestDoc")
        FreeCAD.open(file_path)
        if self.doc.isAutoCreated() and len(self.doc.Objects) == 0:
            FreeCAD.closeDocument("TestDoc")
        self.assertNotIn("TestDoc", FreeCAD.listDocuments())

    def test_manual_document_does_not_close_on_opening_existing_document(self):
        self.assertFalse(self.doc.isAutoCreated())
        self.assertEqual(len(self.doc.Objects), 0)
        saved_doc = FreeCAD.newDocument("SavedDoc")
        file_path = tempfile.gettempdir() + os.sep + "SavedDoc.FCStd"
        saved_doc.saveAs(file_path)
        FreeCAD.closeDocument("SavedDoc")
        FreeCAD.setActiveDocument("TestDoc")
        FreeCAD.open(file_path)
        if self.doc.isAutoCreated() and len(self.doc.Objects) == 0:
            FreeCAD.closeDocument("TestDoc")
        self.assertIn("TestDoc", FreeCAD.listDocuments())
        self.assertIn("SavedDoc", FreeCAD.listDocuments())


# Test if actions done on two documents are undone together
# (working toward making this test pass)
class MultiDocumentUndo(unittest.TestCase):
    def setUp(self):
        self.Doc1 = FreeCAD.newDocument("Doc1")
        self.Doc2 = FreeCAD.newDocument("Doc2")

    def testAddObjects(self):
        self.Doc1.openTransaction("transact1")
        self.Doc2.openTransaction("transact2")

        obj1 = self.Doc1.addObject("App::DocumentObject", "Obj1Name")
        obj2 = self.Doc2.addObject("App::DocumentObject", "Obj2Name")

        self.assertNotEqual(self.Doc1.getBookedTransactionID(), self.Doc2.getBookedTransactionID())

        self.Doc1.commitTransaction()
        self.Doc2.commitTransaction()

        with self.assertRaises(TypeError):
            self.Doc1.getObject([1])
            self.Doc2.getObject([1])

        self.assertEqual(self.Doc1.getObject("Obj1Name"), obj1)
        self.assertEqual(self.Doc2.getObject("Obj2Name"), obj2)

        self.Doc1.undo()
        self.assertEqual(self.Doc1.getObject("Obj1Name"), None)
        self.assertEqual(self.Doc2.getObject("Obj2Name"), obj2)

        self.Doc2.undo()
        self.assertEqual(self.Doc1.getObject("Obj1Name"), None)
        self.assertEqual(self.Doc2.getObject("Obj2Name"), None)

        self.Doc1.redo()
        self.assertEqual(self.Doc1.getObject("Obj1Name"), obj1)
        self.assertEqual(self.Doc2.getObject("Obj2Name"), None)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("Doc1")
        FreeCAD.closeDocument("Doc2")


class DocumentPathCases(unittest.TestCase):
    """Relative document arguments must not corrupt saved external links."""

    def setUp(self):
        try:
            import Spreadsheet
        except ImportError:
            self.skipTest("Spreadsheet module is required")
        from pathlib import Path

        self.original_cwd = Path.cwd()
        self.previous_document = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        self.initial_documents = set(FreeCAD.listDocuments())
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.directory = Path(storage.name)

    def tearDown(self):
        for name in reversed(list(FreeCAD.listDocuments())):
            if name not in self.initial_documents:
                FreeCAD.closeDocument(name)
        os.chdir(self.original_cwd)
        if self.previous_document in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(self.previous_document)

    def _check_spreadsheet_link_paths(self, owner_relative, source_relative):
        from pathlib import Path

        model = self.directory / "project" / "model"
        model.mkdir(parents=True)
        source_file = model / "GlobalVars.FCStd"
        owner_file = model / "Owner.FCStd"
        source = FreeCAD.newDocument("ProjectVarsSource")
        sheet = source.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.Label = "GlobalVars"
        sheet.set("A1", "123")
        source.recompute()
        source.saveAs(str(source_file))
        FreeCAD.closeDocument(source.Name)
        owner = FreeCAD.newDocument("ProjectOwnerSource")
        owner.saveAs(str(owner_file))
        FreeCAD.closeDocument(owner.Name)

        os.chdir(self.directory)
        owner = FreeCAD.openDocument(
            str(owner_file.relative_to(self.directory)) if owner_relative else str(owner_file)
        )
        if owner_relative and source_relative:
            # The project path follows the owner's runtime FileName. normpath
            # alone must not leave an argument relative to the process cwd.
            project_path = os.path.join(os.path.dirname(owner.FileName), "FCProject")
            source_argument = os.path.normpath(os.path.join(
                os.path.dirname(project_path), "GlobalVars.FCStd"
            ))
        else:
            source_argument = (
                str(source_file.relative_to(self.directory)) if source_relative else str(source_file)
            )
        source = FreeCAD.openDocument(source_argument)
        FreeCAD.setActiveDocument(owner.Name)
        link = owner.addObject("App::Link", "GlobalVarsLink")
        link.LinkedObject = source.Spreadsheet
        self.assertEqual(link.LinkedObject, source.Spreadsheet)
        owner.recompute()
        owner.save()

        with zipfile.ZipFile(owner_file) as archive:
            xml = ET.fromstring(archive.read("Document.xml"))
        node = xml.find(
            ".//ObjectData/Object[@name='GlobalVarsLink']/Properties/"
            "Property[@name='LinkedObject']/XLink"
        )
        self.assertIsNotNone(node)
        self.assertEqual(
            (owner_file.parent / node.attrib["file"]).resolve(), source_file.resolve()
        )

        FreeCAD.closeDocument(owner.Name)
        FreeCAD.closeDocument(source.Name)
        os.chdir(self.original_cwd)
        reopened = FreeCAD.openDocument(str(owner_file))
        restored = reopened.GlobalVarsLink.LinkedObject
        self.assertIsNotNone(restored)
        self.assertEqual(restored.TypeId, "Spreadsheet::Sheet")
        self.assertEqual(restored.get("A1"), 123)
        self.assertEqual(Path(restored.Document.FileName), source_file)

    def test_absolute_owner_and_source_link_paths(self):
        self._check_spreadsheet_link_paths(False, False)

    def test_relative_owner_and_absolute_source_link_paths(self):
        self._check_spreadsheet_link_paths(True, False)

    def test_absolute_owner_and_relative_source_link_paths(self):
        self._check_spreadsheet_link_paths(False, True)

    def test_relative_owner_and_project_derived_source_link_paths(self):
        self._check_spreadsheet_link_paths(True, True)

    def test_link_created_during_first_save_is_relative_to_owner(self):
        # Issue #33468: a link made while the owner is saved for the first
        # time (slotStartSaveDocument) was stored relative to the process cwd.
        model = self.directory / "model"
        model.mkdir()
        source_file = model / "Source.FCStd"
        owner_file = model / "Owner.FCStd"
        source = FreeCAD.newDocument("FirstSaveLinkSource")
        target = source.addObject("App::FeaturePython", "Target")
        source.saveAs(str(source_file))
        owner = FreeCAD.newDocument("FirstSaveLinkOwner")

        class Observer:
            def slotStartSaveDocument(self, doc, filename):
                if doc == owner and not doc.getObject("FirstSaveLink"):
                    doc.addObject("App::Link", "FirstSaveLink").LinkedObject = target

        observer = Observer()
        FreeCAD.addDocumentObserver(observer)
        try:
            owner.saveAs(str(owner_file))
        finally:
            FreeCAD.removeDocumentObserver(observer)

        with zipfile.ZipFile(owner_file) as archive:
            xml = ET.fromstring(archive.read("Document.xml"))
        node = xml.find(
            ".//ObjectData/Object[@name='FirstSaveLink']/Properties/"
            "Property[@name='LinkedObject']/XLink"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.attrib["file"], "Source.FCStd")

    def test_link_to_saved_document_is_stored_relative_to_owner(self):
        # A link is saved relative to its owner, so that the files can be moved together.
        source_file = self.directory / "Source.FCStd"
        owner_file = self.directory / "Owner.FCStd"
        source = FreeCAD.newDocument("RelativeLinkSource")
        target = source.addObject("App::FeaturePython", "Target")
        source.saveAs(str(source_file))
        owner = FreeCAD.newDocument("RelativeLinkOwner")
        owner.saveAs(str(owner_file))
        owner.addObject("App::Link", "SavedLink").LinkedObject = target
        owner.save()

        with zipfile.ZipFile(owner_file) as archive:
            xml = ET.fromstring(archive.read("Document.xml"))
        node = xml.find(
            ".//ObjectData/Object[@name='SavedLink']/Properties/"
            "Property[@name='LinkedObject']/XLink"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.attrib["file"], "Source.FCStd")

    def test_link_follows_owner_saved_as_to_another_directory(self):
        # Save As of the owner to another directory must store the path relative to the new
        # location, otherwise the link is broken when the file is opened again.
        source_file = self.directory / "Source.FCStd"
        owner_file = self.directory / "Owner.FCStd"
        moved_file = self.directory / "other" / "sub" / "Owner.FCStd"
        moved_file.parent.mkdir(parents=True)
        source = FreeCAD.newDocument("MovedOwnerLinkSource")
        source.addObject("App::FeaturePython", "Target")
        source.saveAs(str(source_file))
        owner = FreeCAD.newDocument("MovedOwnerLinkOwner")
        owner.saveAs(str(owner_file))
        owner.addObject("App::Link", "SavedLink").LinkedObject = source.Target
        owner.save()
        owner.saveAs(str(moved_file))

        with zipfile.ZipFile(moved_file) as archive:
            xml = ET.fromstring(archive.read("Document.xml"))
        node = xml.find(
            ".//ObjectData/Object[@name='SavedLink']/Properties/"
            "Property[@name='LinkedObject']/XLink"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.attrib["file"], "../../Source.FCStd")

        FreeCAD.closeDocument(owner.Name)
        FreeCAD.closeDocument(source.Name)
        reopened = FreeCAD.openDocument(str(moved_file))
        restored = reopened.SavedLink.LinkedObject
        self.assertIsNotNone(restored)
        self.assertEqual(restored.Name, "Target")

    def test_owner_saved_as_relative_path_keeps_its_file(self):
        # A relative Save As path is resolved once: after the working directory changes,
        # saving again must update the same file, and links stay relative to it.
        from pathlib import Path

        source_file = self.directory / "Source.FCStd"
        owner_file = self.directory / "Owner.FCStd"
        other = self.directory / "other"
        other.mkdir()
        source = FreeCAD.newDocument("RelativeSaveAsSource")
        source.addObject("App::FeaturePython", "Target")
        source.saveAs(str(source_file))
        owner = FreeCAD.newDocument("RelativeSaveAsOwner")
        os.chdir(self.directory)
        owner.saveAs("Owner.FCStd")
        self.assertTrue(os.path.isabs(owner.FileName))
        self.assertEqual(Path(owner.FileName).resolve(), owner_file.resolve())

        os.chdir(other)
        owner.addObject("App::Link", "SavedLink").LinkedObject = source.Target
        owner.save()
        self.assertFalse((other / "Owner.FCStd").exists())

        with zipfile.ZipFile(owner_file) as archive:
            xml = ET.fromstring(archive.read("Document.xml"))
        node = xml.find(
            ".//ObjectData/Object[@name='SavedLink']/Properties/"
            "Property[@name='LinkedObject']/XLink"
        )
        self.assertIsNotNone(node)
        self.assertEqual(node.attrib["file"], "Source.FCStd")


class DocumentXLinkStampCases(unittest.TestCase):
    """External links must notice a linked document saved after them."""

    def setUp(self):
        from pathlib import Path

        self.previous_document = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
        self.initial_documents = set(FreeCAD.listDocuments())
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.directory = Path(storage.name)

    def tearDown(self):
        for name in reversed(list(FreeCAD.listDocuments())):
            if name not in self.initial_documents:
                FreeCAD.closeDocument(name)
        if self.previous_document in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(self.previous_document)

    def test_link_touched_when_open_linked_document_changed(self):
        # Issue #25295: when the linked document was opened, changed and saved
        # before the owner was opened, the link was not marked touched.
        import time

        source_file = self.directory / "Source.FCStd"
        owner_file = self.directory / "Owner.FCStd"
        source = FreeCAD.newDocument("StampLinkSource")
        target = source.addObject("App::FeaturePython", "Target")
        source.saveAs(str(source_file))
        owner = FreeCAD.newDocument("StampLinkOwner")
        owner.saveAs(str(owner_file))
        owner.addObject("App::Link", "Link").LinkedObject = target
        owner.recompute()
        owner.save()
        FreeCAD.closeDocument(owner.Name)

        # Unchanged linked document: the link stays up to date
        owner = FreeCAD.openDocument(str(owner_file))
        self.assertNotIn("Touched", owner.Link.State)
        FreeCAD.closeDocument(owner.Name)

        # The saved time stamp has a resolution of one second
        time.sleep(1.1)
        source.Target.Label = "ChangedTarget"
        source.save()

        owner = FreeCAD.openDocument(str(owner_file))
        self.assertEqual(owner.Link.LinkedObject, source.Target)
        self.assertIn("Touched", owner.Link.State)

    def test_recompute_after_closing_document_used_by_expression(self):
        # Closing a document used by an expression of another document left the
        # property dependencies of that expression pointing to the destroyed
        # objects; the next recompute of the other document read them (access
        # violation).
        source = FreeCAD.newDocument("CloseXLinkSource")
        source.saveAs(str(self.directory / "CloseXLinkSource.FCStd"))
        varset = source.addObject("App::VarSet", "VarSet")
        varset.addProperty("App::PropertyLength", "L")
        varset.L = 20
        source.save()
        owner = FreeCAD.newDocument("CloseXLinkOwner")
        owner.saveAs(str(self.directory / "CloseXLinkOwner.FCStd"))
        user = owner.addObject("App::VarSet", "User")
        user.addProperty("App::PropertyLength", "Length")
        user.setExpression("Length", "CloseXLinkSource#VarSet.L")
        owner.recompute()
        self.assertEqual(user.Length, 20)

        FreeCAD.closeDocument(source.Name)
        self.assertEqual(user.OutList, [])
        owner.recompute()

        # Reopening the document restores the dependency
        source = FreeCAD.openDocument(str(self.directory / "CloseXLinkSource.FCStd"))
        self.assertIn(source.VarSet, user.OutList)
        source.VarSet.L = 30
        source.recompute()
        user.touch()
        owner.recompute()
        self.assertEqual(user.Length, 30)
