# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2024 FreeCAD Project Association                        *
# *                                                                         *
# *   This file is part of FreeCAD.                                         *
# *                                                                         *
# *   FreeCAD is free software: you can redistribute it and/or modify it    *
# *   under the terms of the GNU Lesser General Public License as           *
# *   published by the Free Software Foundation, either version 2.1 of the  *
# *   License, or (at your option) any later version.                       *
# *                                                                         *
# *   FreeCAD is distributed in the hope that it will be useful, but        *
# *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
# *   Lesser General Public License for more details.                       *
# *                                                                         *
# *   You should have received a copy of the GNU Lesser General Public      *
# *   License along with FreeCAD. If not, see                               *
# *   <https://www.gnu.org/licenses/>.                                      *
# *                                                                         *
# ***************************************************************************

import unittest
import FreeCAD
import Materials


class DocumentTestCases(unittest.TestCase):
    """
    Test class for FreeCAD material tests that need a document
    """

    def setUp(self):
        self.doc = FreeCAD.newDocument()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testApplyDiffuseColorCheckShapeAppearance(self):
        """ Test that applying a DiffuseColor with transparency results in a correct ShapeAppearance """
        if "BUILD_PART" in FreeCAD.__cmake__ and FreeCAD.GuiUp:
            dif_col_1 = (1.0, 1.0, 0.0, 1.0)  # yellow 0% transparent
            dif_col_2 = (1.0, 0.0, 0.0, 0.5)  # red 50% transparent
            dif_col = [dif_col_1] + [dif_col_2] + 4 * [dif_col_1]

            obj = self.doc.addObject("Part::Box")
            vobj = obj.ViewObject
            vobj.DiffuseColor = dif_col

            self.assertEqual(
                [m.DiffuseColor[:3] + (1.0 - m.Transparency, ) for m in vobj.ShapeAppearance],
                vobj.DiffuseColor
            )

    def testApplyShapeAppearanceCheckDiffuseColor(self):
        """ Test that applying a ShapeAppearance with transparency results in a correct DiffuseColor """
        if "BUILD_PART" in FreeCAD.__cmake__ and FreeCAD.GuiUp:
            sapp_1 = FreeCAD.Material()
            sapp_1.DiffuseColor = (0.0, 1.0, 1.0, 0.0)  # cyan
            sapp_1.Transparency = 0.0                   # 0% transparent
            sapp_2 = FreeCAD.Material()
            sapp_2.DiffuseColor = (0.0, 1.0, 0.0, 0.0)  # green
            sapp_2.Transparency = 0.3                   # 30% transparent
            sapp = [sapp_1] + [sapp_2] + 4 * [sapp_1]

            obj = self.doc.addObject("Part::Box")
            vobj = obj.ViewObject
            vobj.ShapeAppearance = sapp

            self.assertEqual(
                [m.DiffuseColor[:3] + (1.0 - m.Transparency, ) for m in vobj.ShapeAppearance],
                vobj.DiffuseColor
            )

    def testApplyNoAppearanceThenAppearanceMaterial(self):
        """Applying a material with no appearance then one with appearance must update ShapeAppearance.

        Regression test for https://github.com/FreeCAD/FreeCAD/issues/25793 — applying Air
        (no appearance properties) followed by Wood-Generic must still apply Wood's colors.
        """
        if "BUILD_PART" not in FreeCAD.__cmake__ or not FreeCAD.GuiUp:
            return

        manager = Materials.MaterialManager()

        # Air: physical-only material, no appearance properties
        air_uuid = "94370b96-c97e-4a3f-83b2-11d7461f7da7"
        # Wood-Generic inherits Wood appearance: DiffuseColor ~ (0.898, 0.730, 0.391)
        wood_uuid = "b588224e-e8d6-47ad-ba1f-a058333fd1c6"

        obj = self.doc.addObject("Part::Box")
        self.doc.recompute()
        vobj = obj.ViewObject

        default_color = vobj.ShapeAppearance[0].DiffuseColor

        obj.ShapeMaterial = manager.getMaterial(air_uuid)
        self.assertEqual(
            vobj.ShapeAppearance[0].DiffuseColor,
            default_color,
            "Applying Air (no appearance) must not change ShapeAppearance",
        )

        obj.ShapeMaterial = manager.getMaterial(wood_uuid)
        wood_color = vobj.ShapeAppearance[0].DiffuseColor
        self.assertNotEqual(
            wood_color,
            default_color,
            "Applying Wood after Air must update ShapeAppearance to Wood's color",
        )

    def testLinkLegacyShapeMaterial(self):
        """Links must keep the legacy ShapeMaterial view attribute (issue #30978)."""
        if "BUILD_PART" not in FreeCAD.__cmake__ or not FreeCAD.GuiUp:
            return

        box = self.doc.addObject("Part::Box")
        link = self.doc.addObject("App::Link")
        link.setLink(box)
        self.doc.recompute()
        vobj = link.ViewObject

        self.assertTrue(hasattr(box.ViewObject, "ShapeMaterial"))
        self.assertTrue(hasattr(vobj, "ShapeMaterial"))
        self.assertEqual(
            vobj.ShapeMaterial.DiffuseColor, vobj.ShapeAppearance[0].DiffuseColor
        )

        mat = FreeCAD.Material()
        mat.DiffuseColor = (1.0, 0.0, 0.0, 0.0)
        mat.Transparency = 0.25
        vobj.ShapeMaterial = mat
        self.assertEqual(vobj.ShapeAppearance[0].DiffuseColor[:3], (1.0, 0.0, 0.0))
        self.assertAlmostEqual(vobj.ShapeAppearance[0].Transparency, 0.25, places=6)
        self.assertEqual(vobj.ShapeMaterial.DiffuseColor[:3], (1.0, 0.0, 0.0))


WOOD_UUID = "b588224e-e8d6-47ad-ba1f-a058333fd1c6"  # Wood-Generic, look of Appearance/Wood
ALUMINIUM_UUID = "9bf060e9-1663-44a2-88e2-2ff6ee858efe"  # Aluminum-Generic
WOOD_COLOR = (0.8984, 0.7305, 0.3906)
ALUMINIUM_COLOR = (0.3, 0.3, 0.3)
RED = (1.0, 0.0, 0.0)


class MaterialLookTestCases(unittest.TestCase):
    """The look follows the physical material unless an appearance overrides it."""

    def setUp(self):
        if "BUILD_PART" not in FreeCAD.__cmake__ or not FreeCAD.GuiUp:
            self.skipTest("needs Part and the GUI")
        self.manager = Materials.MaterialManager()
        self.doc = FreeCAD.newDocument("MaterialLook")
        self.tempdir = None

    def tearDown(self):
        if self.doc and self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        if self.tempdir:
            import shutil

            shutil.rmtree(self.tempdir, ignore_errors=True)

    def setMaterial(self, obj, uuid):
        obj.ShapeMaterial = self.manager.getMaterial(uuid)

    @staticmethod
    def appearance(color):
        mat = FreeCAD.Material()
        mat.DiffuseColor = color + (0.0,)
        return mat

    def assertColor(self, material, color):
        for actual, expected in zip(material.DiffuseColor[:3], color):
            self.assertAlmostEqual(actual, expected, places=3)

    def newBox(self, uuid=WOOD_UUID):
        box = self.doc.addObject("Part::Box")
        self.doc.recompute()
        self.setMaterial(box, uuid)
        return box

    def saveAndReload(self, edit=None):
        import os
        import tempfile

        self.tempdir = self.tempdir or tempfile.mkdtemp()
        path = os.path.join(self.tempdir, "look.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = None
        if edit:
            edit(path)
        self.doc = FreeCAD.openDocument(path)

    def testLookFollowsMaterialUntilOverridden(self):
        box = self.newBox()
        vobj = box.ViewObject
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertTrue(vobj.isLookFromMaterial())

        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)

        vobj.ShapeAppearance = [self.appearance(RED)]
        self.assertEqual(vobj.AppearanceOverrides, ["Object"])
        self.assertFalse(vobj.isLookFromMaterial())

        # The override wins over a new material
        self.setMaterial(box, WOOD_UUID)
        self.assertColor(vobj.ShapeAppearance[0], RED)

        vobj.resetToMaterial()
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)
        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)

    def testFaceOverrideSurvivesMaterialChange(self):
        box = self.newBox()
        vobj = box.ViewObject
        faces = [vobj.ShapeAppearance[0]] * 6
        faces[1] = self.appearance(RED)
        vobj.ShapeAppearance = faces
        self.assertEqual(vobj.AppearanceOverrides, ["Face2"])
        self.assertFalse(vobj.isLookFromMaterial("Face2"))
        self.assertTrue(vobj.isLookFromMaterial("Face1"))

        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertEqual(len(vobj.ShapeAppearance), 6)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)
        self.assertColor(vobj.ShapeAppearance[1], RED)
        self.assertColor(vobj.ShapeAppearance[5], ALUMINIUM_COLOR)

        vobj.resetToMaterial(["Face2"])
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertEqual(len(vobj.ShapeAppearance), 1)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)

    def testOverridesSurviveSaveAndReload(self):
        painted = self.newBox()
        painted.ViewObject.ShapeAppearance = [self.appearance(RED)]
        plain = self.newBox()
        names = (painted.Name, plain.Name)

        self.saveAndReload()
        painted, plain = (self.doc.getObject(name) for name in names)
        self.assertEqual(painted.ViewObject.AppearanceOverrides, ["Object"])
        self.assertEqual(plain.ViewObject.AppearanceOverrides, [])
        self.assertColor(plain.ViewObject.ShapeAppearance[0], WOOD_COLOR)

        self.setMaterial(painted, ALUMINIUM_UUID)
        self.setMaterial(plain, ALUMINIUM_UUID)
        self.assertColor(painted.ViewObject.ShapeAppearance[0], RED)
        self.assertColor(plain.ViewObject.ShapeAppearance[0], ALUMINIUM_COLOR)

    def testOldFileWithoutOverrides(self):
        """A file without the saved overrides (older version or upstream FreeCAD) is guessed."""
        import re
        import zipfile

        painted = self.newBox()
        painted.ViewObject.ShapeAppearance = [self.appearance(RED)]
        plain = self.newBox()
        names = (painted.Name, plain.Name)

        def dropOverrides(path):
            with zipfile.ZipFile(path) as archive:
                entries = {info: archive.read(info.filename) for info in archive.infolist()}
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                for info, data in entries.items():
                    if info.filename == "GuiDocument.xml":
                        text = data.decode("utf-8")
                        text = re.sub(
                            r'<Property name="AppearanceOverrides".*?</Property>',
                            "",
                            text,
                            flags=re.DOTALL,
                        )
                        self.assertNotIn("AppearanceOverrides", text)
                        data = text.encode("utf-8")
                    archive.writestr(info, data)

        self.saveAndReload(dropOverrides)
        painted, plain = (self.doc.getObject(name) for name in names)
        # Loading changes nothing
        self.assertColor(painted.ViewObject.ShapeAppearance[0], RED)
        self.assertColor(plain.ViewObject.ShapeAppearance[0], WOOD_COLOR)
        self.assertEqual(painted.ViewObject.AppearanceOverrides, ["Object"])
        self.assertEqual(plain.ViewObject.AppearanceOverrides, [])

        self.setMaterial(painted, ALUMINIUM_UUID)
        self.setMaterial(plain, ALUMINIUM_UUID)
        self.assertColor(painted.ViewObject.ShapeAppearance[0], RED)
        self.assertColor(plain.ViewObject.ShapeAppearance[0], ALUMINIUM_COLOR)

    def testUndoRestoresLookAndOverrides(self):
        box = self.newBox()
        vobj = box.ViewObject
        self.doc.UndoMode = 1

        self.doc.openTransaction("Paint")
        vobj.ShapeAppearance = [self.appearance(RED)]
        self.doc.commitTransaction()
        self.doc.openTransaction("Material")
        self.setMaterial(box, ALUMINIUM_UUID)
        self.doc.commitTransaction()
        self.assertColor(vobj.ShapeAppearance[0], RED)

        self.doc.undo()  # material
        self.assertEqual(box.ShapeMaterial.UUID, WOOD_UUID)
        self.assertColor(vobj.ShapeAppearance[0], RED)
        self.doc.undo()  # paint
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)
        self.assertEqual(vobj.AppearanceOverrides, [])

        self.doc.redo()
        self.assertEqual(vobj.AppearanceOverrides, ["Object"])
        self.assertColor(vobj.ShapeAppearance[0], RED)

    def testTransparencyIsNoOverride(self):
        box = self.newBox()
        vobj = box.ViewObject
        vobj.Transparency = 60
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertTrue(vobj.isLookFromMaterial())

        # The material changes the look and keeps the transparency
        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)
        self.assertAlmostEqual(vobj.ShapeAppearance[0].Transparency, 0.6, places=3)
        self.assertEqual(vobj.Transparency, 60)

    def testTransparencyOfALookFromAnotherMaterialIsNoOverride(self):
        """Air has no look: the box keeps the wood look, which still follows the material."""
        box = self.newBox()
        vobj = box.ViewObject
        self.setMaterial(box, "94370b96-c97e-4a3f-83b2-11d7461f7da7")  # Air
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)
        vobj.Transparency = 60
        self.assertEqual(vobj.AppearanceOverrides, [])

        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)
        self.assertEqual(vobj.Transparency, 60)

    def testFaceTransparencyIsNoOverride(self):
        box = self.newBox()
        vobj = box.ViewObject
        faces = [vobj.ShapeAppearance[0]] * 6
        seeThrough = vobj.ShapeAppearance[0]
        seeThrough.Transparency = 0.5
        faces[1] = seeThrough
        vobj.ShapeAppearance = faces
        self.assertEqual(vobj.AppearanceOverrides, [])

        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertEqual(len(vobj.ShapeAppearance), 6)
        self.assertColor(vobj.ShapeAppearance[1], ALUMINIUM_COLOR)
        self.assertAlmostEqual(vobj.ShapeAppearance[1].Transparency, 0.5, places=3)
        self.assertAlmostEqual(vobj.ShapeAppearance[0].Transparency, 0.0, places=3)

    def testTemporaryAppearanceIsNoOverride(self):
        box = self.newBox()
        vobj = box.ViewObject
        vobj.beginTemporaryAppearance()
        try:
            vobj.ShapeColor = (1.0, 0.0, 1.0)
        finally:
            vobj.endTemporaryAppearance()
        self.assertEqual(vobj.AppearanceOverrides, [])

        # A later change is recorded again
        vobj.ShapeAppearance = [self.appearance(RED)]
        self.assertEqual(vobj.AppearanceOverrides, ["Object"])

    def testFemSolidHighlightIsNoOverride(self):
        """The highlight while picking a solid of a compound (FEM) is temporary."""
        try:
            from femguiutils.disambiguate_solid_selection import HighlightContext
        except ImportError:
            self.skipTest("needs FEM")

        box = self.newBox()
        vobj = box.ViewObject
        with HighlightContext(box):
            self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)

        # The look still follows the material
        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(vobj.ShapeAppearance[0], ALUMINIUM_COLOR)

    def testRandomColorIsAnOverride(self):
        import FreeCADGui

        box = self.newBox()
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(box)
        try:
            FreeCADGui.runCommand("Std_RandomColor")
        finally:
            FreeCADGui.Selection.clearSelection()
        self.assertEqual(box.ShapeMaterial.UUID, WOOD_UUID)
        self.assertEqual(box.ViewObject.AppearanceOverrides, ["Object"])

    def testLinkColorOverrideIsKept(self):
        box = self.newBox()
        link = self.doc.addObject("App::Link")
        link.setLink(box)
        self.doc.recompute()
        link.ViewObject.OverrideMaterial = True
        link.ViewObject.ShapeAppearance = [self.appearance(RED)]

        self.setMaterial(box, ALUMINIUM_UUID)
        self.assertColor(box.ViewObject.ShapeAppearance[0], ALUMINIUM_COLOR)
        self.assertTrue(link.ViewObject.OverrideMaterial)
        self.assertColor(link.ViewObject.ShapeAppearance[0], RED)

    def testSetFaceAppearance(self):
        box = self.newBox()
        vobj = box.ViewObject
        vobj.setFaceAppearance(["Face3"], self.appearance(RED))
        self.assertEqual(len(vobj.ShapeAppearance), 6)
        self.assertEqual(vobj.AppearanceOverrides, ["Face3"])
        self.assertColor(vobj.ShapeAppearance[2], RED)
        self.assertColor(vobj.ShapeAppearance[0], WOOD_COLOR)


class MaterialAppearanceDialogTestCases(unittest.TestCase):
    """One command and dialog sets the physical material and the appearance."""

    def setUp(self):
        if "BUILD_PART" not in FreeCAD.__cmake__ or not FreeCAD.GuiUp:
            self.skipTest("needs Part and the GUI")
        import FreeCADGui

        self.gui = FreeCADGui
        self.doc = FreeCAD.newDocument("MaterialDialog")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.box.ShapeMaterial = Materials.MaterialManager().getMaterial(WOOD_UUID)
        self.gui.Selection.clearSelection()

    def tearDown(self):
        self.gui.Control.closeDialog()
        self.gui.Selection.clearSelection()
        FreeCAD.closeDocument(self.doc.Name)

    def findWidget(self, cls, name):
        from PySide import QtWidgets

        widget = self.gui.getMainWindow().findChild(getattr(QtWidgets, cls), name)
        self.assertIsNotNone(widget, name)
        return widget

    def testCommands(self):
        info = self.gui.Command.get("Std_SetAppearance").getInfo()
        self.assertIn("Material and", info["menuText"].replace("&", ""))
        # Kept for user toolbars and macros
        self.assertIsNotNone(self.gui.Command.get("Std_SetMaterial"))
        self.assertIsNotNone(self.gui.Command.get("Part_ColorPerFace"))
        self.assertNotIn("MaterialWorkbench", self.gui.listWorkbenches())

    def testSetMaterialOpensTheUnifiedDialog(self):
        self.gui.Selection.addSelection(self.doc.Name, self.box.Name)
        self.gui.runCommand("Std_SetMaterial")
        self.assertIsNotNone(self.gui.Control.activeDialog())
        self.findWidget("QWidget", "widgetPhysicalMaterial")
        self.findWidget("QRadioButton", "radioScopeFaces")

    def testLookSourceAndReset(self):
        vobj = self.box.ViewObject
        self.gui.Selection.addSelection(self.doc.Name, self.box.Name)
        self.gui.runCommand("Std_SetAppearance")
        label = self.findWidget("QLabel", "labelLookSource")
        reset = self.findWidget("QPushButton", "buttonResetToMaterial")
        self.assertTrue(label.text().startswith("From material"), label.text())
        self.assertFalse(reset.isEnabled())

        red = FreeCAD.Material()
        red.DiffuseColor = (1.0, 0.0, 0.0, 0.0)
        vobj.ShapeAppearance = [red]
        self.assertEqual(label.text(), "Override")
        self.assertTrue(reset.isEnabled())

        reset.click()
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertTrue(label.text().startswith("From material"), label.text())

    def testColorPerFaceUsesTheFaceScope(self):
        vobj = self.box.ViewObject
        red = FreeCAD.Material()
        red.DiffuseColor = (1.0, 0.0, 0.0, 0.0)
        vobj.setFaceAppearance(["Face2"], red)
        self.gui.Selection.addSelection(self.doc.Name, self.box.Name, "Face2")
        self.gui.runCommand("Part_ColorPerFace")
        self.assertTrue(self.findWidget("QRadioButton", "radioScopeFaces").isChecked())
        label = self.findWidget("QLabel", "labelLookSource")
        self.assertEqual(label.text(), "Override")

        # Resetting the selected face leaves the other faces alone
        self.findWidget("QPushButton", "buttonResetToMaterial").click()
        self.assertEqual(vobj.AppearanceOverrides, [])
        self.assertEqual(len(vobj.ShapeAppearance), 1)
