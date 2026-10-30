# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import unittest

import FreeCAD
from pivy import coin

App = FreeCAD


class TestBoolean(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestBoolean")

    def testBooleanFuseCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()
        self.Body001 = self.Doc.addObject("PartDesign::Body", "Body001")
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "Box001")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Box001.Placement.Base = App.Vector(-5, 0, 0)
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()
        self.BooleanFuse = self.Doc.addObject("PartDesign::Boolean", "BooleanFuse")
        self.Body001.addObject(self.BooleanFuse)
        self.Doc.recompute()
        self.BooleanFuse.setObjects(
            [
                self.Body,
            ]
        )
        self.BooleanFuse.Type = 0
        self.Doc.recompute()
        self.assertAlmostEqual(self.BooleanFuse.Shape.Volume, 1500)

    def testBooleanCutCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()
        self.Body001 = self.Doc.addObject("PartDesign::Body", "Body001")
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "Box001")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Box001.Placement.Base = App.Vector(-5, 0, 0)
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()
        self.BooleanCut = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.Body001.addObject(self.BooleanCut)
        self.Doc.recompute()
        self.BooleanCut.setObjects(
            [
                self.Body,
            ]
        )
        self.BooleanCut.Type = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.BooleanCut.Shape.Volume, 500)

    def testBooleanCommonCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()
        self.Body001 = self.Doc.addObject("PartDesign::Body", "Body001")
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "Box001")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Box001.Placement.Base = App.Vector(-5, 0, 0)
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()
        self.BooleanCommon = self.Doc.addObject("PartDesign::Boolean", "BooleanCommon")
        self.Body001.addObject(self.BooleanCommon)
        self.Doc.recompute()
        self.BooleanCommon.setObjects(
            [
                self.Body,
            ]
        )
        self.BooleanCommon.Type = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.BooleanCommon.Shape.Volume, 500)

    def testBooleanCutUsesActiveBodyPlacement(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "ToolBody")
        self.Body.Placement.Base = App.Vector(25, 0, 0)
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "ToolBox")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()

        self.Body001 = self.Doc.addObject("PartDesign::Body", "ActiveBody")
        self.Body001.Placement.Base = App.Vector(20, 0, 0)
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "BaseBox")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()

        self.BooleanCut = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.Body001.addObject(self.BooleanCut)
        self.BooleanCut.setObjects([self.Body])
        self.BooleanCut.Type = 1
        self.Doc.recompute()

        self.assertAlmostEqual(self.BooleanCut.Shape.Volume, 500)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMin, 0)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMax, 5)

    def testBooleanCutUsesActiveBodyGlobalPlacement(self):
        container = self.Doc.addObject("App::Part", "Part")
        container.Placement.Base = App.Vector(100, 0, 0)

        self.Body = self.Doc.addObject("PartDesign::Body", "ToolBody")
        container.addObject(self.Body)
        self.Body.Placement.Base = App.Vector(25, 0, 0)
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "ToolBox")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()

        self.Body001 = self.Doc.addObject("PartDesign::Body", "ActiveBody")
        container.addObject(self.Body001)
        self.Body001.Placement.Base = App.Vector(20, 0, 0)
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "BaseBox")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()

        self.BooleanCut = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.Body001.addObject(self.BooleanCut)
        self.BooleanCut.setObjects([self.Body])
        self.assertIn(self.Body, container.Group)
        self.BooleanCut.Type = 1
        self.Doc.recompute()

        self.assertAlmostEqual(self.BooleanCut.Shape.Volume, 500)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMin, 0)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMax, 5)

    def testBooleanCutUsesNestedContainerGlobalPlacement(self):
        outer = self.Doc.addObject("App::Part", "OuterPart")
        outer.Placement.Base = App.Vector(100, 0, 0)
        inner = self.Doc.addObject("App::Part", "InnerPart")
        outer.addObject(inner)
        inner.Placement.Base = App.Vector(10, 0, 0)

        self.Body = self.Doc.addObject("PartDesign::Body", "ToolBody")
        inner.addObject(self.Body)
        self.Body.Placement.Base = App.Vector(25, 0, 0)
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "ToolBox")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()

        self.Body001 = self.Doc.addObject("PartDesign::Body", "ActiveBody")
        inner.addObject(self.Body001)
        self.Body001.Placement.Base = App.Vector(20, 0, 0)
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "BaseBox")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()

        self.BooleanCut = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.Body001.addObject(self.BooleanCut)
        self.BooleanCut.setObjects([self.Body])
        self.assertIn(self.Body, inner.Group)
        self.BooleanCut.Type = 1
        self.Doc.recompute()

        self.assertAlmostEqual(self.BooleanCut.Shape.Volume, 500)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMin, 0)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMax, 5)

    def testBooleanCutUsesDifferentContainerGlobalPlacements(self):
        tool_container = self.Doc.addObject("App::Part", "ToolContainer")
        tool_container.Placement.Base = App.Vector(100, 0, 0)
        active_container = self.Doc.addObject("App::Part", "ActiveContainer")
        active_container.Placement.Base = App.Vector(200, 0, 0)

        self.Body = self.Doc.addObject("PartDesign::Body", "ToolBody")
        tool_container.addObject(self.Body)
        self.Body.Placement.Base = App.Vector(25, 0, 0)
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "ToolBox")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()

        self.Body001 = self.Doc.addObject("PartDesign::Body", "ActiveBody")
        active_container.addObject(self.Body001)
        self.Body001.Placement.Base = App.Vector(-80, 0, 0)
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "BaseBox")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Body001.addObject(self.Box001)
        self.Doc.recompute()

        self.BooleanCut = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        self.Body001.addObject(self.BooleanCut)
        self.BooleanCut.setObjects([self.Body])
        self.assertIn(self.Body, tool_container.Group)
        self.BooleanCut.Type = 1
        self.Doc.recompute()

        self.assertAlmostEqual(self.BooleanCut.Shape.Volume, 500)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMin, 0)
        self.assertAlmostEqual(self.BooleanCut.Shape.BoundBox.XMax, 5)

    def testBooleanFirstFeatureUsesSourcePlacement(self):
        box = self.Doc.addObject("Part::Box", "Box")
        box.Length = 10
        box.Width = 10
        box.Height = 10
        box.Placement.Base = App.Vector(20, 0, 0)

        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.BooleanFuse = self.Doc.addObject("PartDesign::Boolean", "BooleanFuse")
        self.Body.addObject(self.BooleanFuse)
        self.assertFalse(self.BooleanFuse.UseLegacyBodyPlacement)
        self.BooleanFuse.setObjects([box])
        self.BooleanFuse.Type = 0
        self.Doc.recompute()

        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMin, 20)
        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMax, 30)

    def testBooleanFirstFeatureUsesSubShapeBinderPlacement(self):
        box = self.Doc.addObject("Part::Box", "Box")
        box.Length = 10
        box.Width = 10
        box.Height = 10
        box.Placement.Base = App.Vector(20, 0, 0)

        binder = self.Doc.addObject("PartDesign::SubShapeBinder", "Binder")
        binder.Support = [box]
        self.Doc.recompute()

        self.assertAlmostEqual(binder.Shape.BoundBox.XMin, 20)
        self.assertAlmostEqual(binder.Shape.BoundBox.XMax, 30)

        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.BooleanFuse = self.Doc.addObject("PartDesign::Boolean", "BooleanFuse")
        self.Body.addObject(self.BooleanFuse)
        self.assertFalse(self.BooleanFuse.UseLegacyBodyPlacement)
        self.BooleanFuse.setObjects([binder])
        self.BooleanFuse.Type = 0
        self.Doc.recompute()

        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMin, 20)
        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMax, 30)

    def testBooleanLegacyPlacementKeepsOldFirstFeatureBehavior(self):
        box = self.Doc.addObject("Part::Box", "Box")
        box.Length = 10
        box.Width = 10
        box.Height = 10
        box.Placement.Base = App.Vector(20, 0, 0)

        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.BooleanFuse = self.Doc.addObject("PartDesign::Boolean", "BooleanFuse")
        self.Body.addObject(self.BooleanFuse)
        self.BooleanFuse.UseLegacyBodyPlacement = True
        self.BooleanFuse.setObjects([box])
        self.BooleanFuse.Type = 0
        self.Doc.recompute()

        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMin, 20)
        self.assertAlmostEqual(self.Body.Shape.BoundBox.XMax, 30)

    def testBooleanSelectUI(self):
        if not App.GuiUp:
            return
        # Arrange
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Box.Length = 10
        self.Box.Width = 10
        self.Box.Height = 10
        self.Body.addObject(self.Box)
        self.Doc.recompute()
        self.Body001 = self.Doc.addObject("PartDesign::Body", "Body001")
        self.Box001 = self.Doc.addObject("PartDesign::AdditiveBox", "Box001")
        self.Box001.Length = 10
        self.Box001.Width = 10
        self.Box001.Height = 10
        self.Box001.Placement.Base = App.Vector(-5, 0, 0)
        self.Body001.addObject(self.Box001)
        self.Body002 = self.Doc.addObject("PartDesign::Body", "Body002")
        self.BooleanFuse = self.Doc.addObject("PartDesign::Boolean", "BooleanFuse")
        self.BooleanFuse.Group = [self.Body, self.Body001]
        self.BooleanFuse.ViewObject.Display = (
            "Result"  # TODO:  This is a required redundancy or it doesn't init right
        )
        self.Body002.addObject(self.BooleanFuse)
        self.Doc.recompute()
        # Act
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face2")
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face6")
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face10")
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face3")
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face7")
        App.Gui.Selection.addSelection("", self.Body002.Name, "Face11")
        App.Gui.Selection.addSelection("", "Body002", "Face14")
        App.Gui.updateGui()
        # Assert
        self.assertEqual(len(App.Gui.Selection.getSelectionEx("", 0)[0].SubElementNames), 7)
        self.assertEqual(
            App.Gui.Selection.getSelectionEx("", 0)[0].SubElementNames[0][-8:],
            ",F.Face2",
        )
        # Ideally we would be able to check and see the selection color set, but there is currently no way to
        # see this either from python of c++ without either tapping into the coin GL renderer or writing a new
        # test renderer.  Prototypes of code moving in this direction would be:
        # compSel = App.Gui.Selection.getCompleteSelection()
        # selection0 = compSel[0]
        # selection00Object = selection0.Object.ViewObject
        # path = coin.SoPath()
        # foundCount = App.Gui.ActiveDocument.Box.getDetailPath("Face14.",path,False)
        # pathLength = path.getLength()
        # # path.getHead()  or path.getTail()  or path.getNode(n)
        # childCount = path.getHead().getNumChildren()
        # children = path.getHead().getChildren() # Some pivy objects support this.
        # child = children.get(0)
        # childOpt2 = path.getHead().getChild(0)  # And others support this.  And some support both.
        # rgb = App.Gui.ActiveDocument.Body002.RootNode.getChild(2).getChild(1).getChild(1).getChild(0).diffuseColor.getValues()[0].getValue()
        # # Assert the rgb color value.

    def testPartBooleanKeepsFeatureInBody(self):
        # https://github.com/FreeCAD/FreeCAD/issues/20735
        # A Part boolean made from a feature of a Body must not take the
        # feature out of the Body.
        from BOPTools import BOPFeatures

        part = self.Doc.addObject("App::Part", "Part")
        body = self.Doc.addObject("PartDesign::Body", "Body")
        part.addObject(body)
        box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        body.addObject(box)
        cube = self.Doc.addObject("Part::Box", "Cube")
        cube.Placement.Base = App.Vector(5, 5, 5)
        part.addObject(cube)
        self.Doc.recompute()

        common = BOPFeatures.BOPFeatures(self.Doc).make_multi_common([box.Name, cube.Name])
        self.Doc.recompute()

        self.assertIn(box, body.Group)
        self.assertEqual(body.Tip, box)
        self.assertEqual(body.getParent(), part)
        self.assertEqual(cube.getParent(), part)
        self.assertIsNone(common.getParent())
        self.assertAlmostEqual(common.Shape.Volume, 125)

    def testBooleanExportUsesBooleanShape(self):
        # https://github.com/FreeCAD/FreeCAD/issues/20641
        # Exporting a Boolean must write its result, not its tool bodies.
        import os
        import tempfile

        import Import
        import Mesh
        import Part

        tool = self.Doc.addObject("PartDesign::Body", "Body")
        toolBox = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        toolBox.Length = 10
        toolBox.Width = 10
        toolBox.Height = 10
        tool.addObject(toolBox)
        body = self.Doc.addObject("PartDesign::Body", "Body001")
        box = self.Doc.addObject("PartDesign::AdditiveBox", "Box001")
        box.Length = 10
        box.Width = 10
        box.Height = 10
        box.Placement.Base = App.Vector(-5, 0, 0)
        body.addObject(box)
        boolean = self.Doc.addObject("PartDesign::Boolean", "BooleanCut")
        body.addObject(boolean)
        boolean.setObjects([tool])
        boolean.Type = 1
        tool.Visibility = False
        self.Doc.recompute()
        self.assertAlmostEqual(boolean.Shape.Volume, 500)
        self.assertEqual(len(boolean.getSubObjects()), 0)

        with tempfile.TemporaryDirectory() as tmp:
            step = os.path.join(tmp, "boolean.step")
            Import.export([boolean], step)
            self.assertAlmostEqual(Part.read(step).Volume, 500, places=3)

            stl = os.path.join(tmp, "boolean.stl")
            Mesh.export([boolean], stl)
            self.assertAlmostEqual(Mesh.Mesh(stl).Volume, 500, places=3)

    def tearDown(self):
        if hasattr(App, "KeepTestDoc") and App.KeepTestDoc:
            return
        # closing doc.
        FreeCAD.closeDocument("PartDesignTestBoolean")
