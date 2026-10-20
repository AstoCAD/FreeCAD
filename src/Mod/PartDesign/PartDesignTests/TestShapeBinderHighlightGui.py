# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual legacy ShapeBinder reference highlighting and ordinary task closure."""

import io
import struct
import unittest
import xml.etree.ElementTree as ET
import zipfile

import FreeCAD as App
import FreeCADGui as Gui
import Part
import PartDesign
import PartDesignGui
from PySide import QtCore, QtWidgets


class TestShapeBinderHighlightGui(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        Gui.activateWorkbench("PartDesignWorkbench")
        self.doc = App.newDocument("ShapeBinderHighlightCleanup")
        self.gui_doc = Gui.getDocument(self.doc.Name)

    def tearDown(self):
        try:
            Gui.Selection.clearSelection()
            if self.doc.Name in App.listDocuments():
                if self.gui_doc.getInEdit():
                    self.gui_doc.resetEdit()
                if Gui.Control.activeDialog(self.gui_doc):
                    Gui.Control.closeDialog(self.gui_doc)
                if self.doc.HasPendingTransaction:
                    self.doc.abortTransaction()
                App.closeDocument(self.doc.Name)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def pump(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(100, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def snapshot(self, source):
        view = source.ViewObject
        return (tuple(tuple(color) for color in view.LineColorArray),
                tuple(view.ShapeAppearance))

    def makeSource(self, name="Source", sketch=False):
        if sketch:
            source = self.doc.addObject("Sketcher::SketchObject", name)
            source.addGeometry(Part.LineSegment(App.Vector(0, 0, 0),
                                                App.Vector(5, 0, 0)), False)
            source.addGeometry(Part.LineSegment(App.Vector(5, 0, 0),
                                                App.Vector(5, 4, 0)), False)
        else:
            source = self.doc.addObject("Part::Feature", name)
            source.Shape = Part.makeBox(5, 4, 3)
        self.doc.recompute()
        self.assertFalse(source.Shape.isNull())
        # Nonempty independent arrays avoid conflating teardown with the separate
        # empty-array sentinel behavior in highlightReferences(false).
        source.ViewObject.LineColorArray = [
            (0.1 + 0.02 * index, 0.35, 0.6, 1.0)
            for index in range(len(source.Shape.Edges))
        ]
        appearances = []
        for index in range(max(1, len(source.Shape.Faces))):
            material = App.Material()
            material.DiffuseColor = (0.2, 0.45 + 0.02 * index, 0.3, 1.0)
            material.SpecularColor = (0.15, 0.2, 0.25, 1.0)
            material.Shininess = 0.4
            material.Transparency = 0.1
            appearances.append(material)
        source.ViewObject.ShapeAppearance = appearances
        source.ViewObject.Visibility = True
        return source

    def openTask(self, source, face=False):
        binder = self.doc.addObject("PartDesign::ShapeBinder", "Binder")
        binder.Support = [(source, ["Face1" if face else "Edge1"])]
        self.doc.recompute()
        self.assertFalse(binder.Shape.isNull())
        self.doc.openTransaction("Edit ShapeBinder")
        self.assertTrue(self.gui_doc.setEdit(binder.Name))
        self.pump()
        self.assertIsNotNone(Gui.Control.activeTaskDialog())
        return binder

    def clickButton(self, name):
        button = Gui.getMainWindow().findChild(QtWidgets.QToolButton, name)
        self.assertIsNotNone(button)
        self.assertTrue(button.isEnabled())
        button.click()
        self.pump()
        self.assertTrue(button.isChecked())

    def closeTask(self, accept):
        task = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(task)
        if accept:
            task.accept()
        else:
            task.reject()
        self.pump()
        self.assertIsNone(self.gui_doc.getInEdit())
        self.assertFalse(Gui.Control.activeDialog(self.gui_doc))

    def checkClose(self, accept, face=False, sketch=False, highlight=True):
        source = self.makeSource(sketch=sketch)
        before = self.snapshot(source)
        binder = self.openTask(source, face)
        reference = binder.Support
        self.assertEqual(self.snapshot(source), before)
        if highlight:
            self.clickButton("buttonRefAdd")
            during = self.snapshot(source)
            self.assertNotEqual(during, before, "The actual task must highlight its source")
            if face:
                self.assertEqual(tuple(source.ViewObject.ShapeAppearance[0].DiffuseColor)[:3],
                                 (1.0, 0.0, 1.0))
            else:
                self.assertEqual(tuple(source.ViewObject.LineColorArray[0])[:3],
                                 (1.0, 0.0, 1.0))
        self.closeTask(accept)
        self.assertEqual(binder.Support, reference)
        self.assertEqual(self.snapshot(source), before,
                         "Leaving the reference task must restore the source's original appearance")

    def testAcceptSketchEdgeHighlight(self):
        self.checkClose(True, sketch=True)

    def testRejectSketchEdgeHighlight(self):
        self.checkClose(False, sketch=True)

    def testAcceptFaceHighlight(self):
        self.checkClose(True, face=True)

    def testRejectFaceHighlight(self):
        self.checkClose(False, face=True)

    def testAcceptWithoutHighlightControl(self):
        self.checkClose(True, highlight=False)

    def testRejectWithoutHighlightControl(self):
        self.checkClose(False, highlight=False)

    def testReplacingSourceRestoresOldAppearance(self):
        source = self.makeSource()
        replacement = self.makeSource("Replacement")
        before = self.snapshot(source)
        replacement_before = self.snapshot(replacement)
        binder = self.openTask(source)
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before)
        self.clickButton("buttonBase")
        Gui.Selection.addSelection(self.doc.Name, replacement.Name)
        self.pump()
        self.assertEqual(binder.Support[0][0], replacement)
        self.closeTask(True)
        self.assertEqual(self.snapshot(replacement), replacement_before,
                         "Switching references must not copy old colors onto the new source")
        self.assertEqual(self.snapshot(source), before,
                         "Switching the source must restore the previously highlighted object")

    def testDeletingSourceDuringHighlightLifetimeControl(self):
        source = self.makeSource()
        replacement = self.makeSource("Unrelated")
        replacement_before = self.snapshot(replacement)
        self.openTask(source)
        self.clickButton("buttonRefAdd")
        source_name = source.Name
        self.doc.removeObject(source_name)
        self.pump()
        self.assertIsNone(self.doc.getObject(source_name))
        if self.gui_doc.getInEdit():
            self.closeTask(False)
        self.assertEqual(self.snapshot(replacement), replacement_before)
        self.assertIsNone(self.gui_doc.getInEdit())

    def checkEmptyLineArray(self, accept):
        source = self.makeSource()
        source.ViewObject.LineColorArray = []
        self.assertEqual(len(source.ViewObject.LineColorArray), 0)
        before = self.snapshot(source)
        self.openTask(source)
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before)
        self.closeTask(accept)
        self.assertEqual(self.snapshot(source), before,
                         "The originally empty line array must be restored exactly")


    def testDefaultEmptyLineArrayAccept(self):
        self.checkEmptyLineArray(True)


    def testDefaultEmptyLineArrayRejectControl(self):
        self.checkEmptyLineArray(False)


    def testRepeatedHighlightAfterReject(self):
        source = self.makeSource()
        before = self.snapshot(source)
        binder = self.openTask(source)
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before)
        self.closeTask(False)
        self.assertEqual(self.snapshot(source), before)
        self.doc.openTransaction("Edit ShapeBinder again")
        self.assertTrue(self.gui_doc.setEdit(binder.Name))
        self.pump()
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before,
                            "A cancelled earlier edit must not suppress the next highlight")
        self.closeTask(False)
        self.assertEqual(self.snapshot(source), before)


    def testClearingSupportRestoresOldSource(self):
        source = self.makeSource()
        before = self.snapshot(source)
        binder = self.openTask(source)
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before)
        field = Gui.getMainWindow().findChild(QtWidgets.QLineEdit, "baseEdit")
        self.assertIsNotNone(field)
        self.assertTrue(field.text())
        field.clear()
        self.pump()
        self.assertFalse(binder.Support)
        self.assertEqual(self.snapshot(source), before,
                         "Clearing the source field must restore the old highlighted object")


    def testRemovingLastReferenceRestoresSource(self):
        source = self.makeSource()
        before = self.snapshot(source)
        binder = self.openTask(source)
        self.clickButton("buttonRefRemove")
        self.assertNotEqual(self.snapshot(source), before)
        Gui.Selection.addSelection(self.doc.Name, source.Name, "Edge1")
        self.pump()
        self.assertFalse(any(sub for obj, subs in binder.Support for sub in subs))
        self.assertEqual(self.snapshot(source), before,
                         "Removing the last subreference must restore the source appearance")


    def testExternalSupportReplacementKeepsNewSourceAppearance(self):
        source = self.makeSource()
        replacement = self.makeSource("Replacement")
        before = self.snapshot(source)
        replacement_before = self.snapshot(replacement)
        binder = self.openTask(source)
        self.clickButton("buttonRefAdd")
        self.assertNotEqual(self.snapshot(source), before)
        # An ordinary public Support assignment can occur while the task is open.
        # Restoration must use its original owner, not whichever object is now linked.
        binder.Support = [(replacement, ["Edge1"])]
        self.doc.recompute()
        self.assertEqual(binder.Support[0][0], replacement)
        self.closeTask(True)
        self.assertEqual(self.snapshot(replacement), replacement_before,
                         "Old cached colors must never be written to a replacement source")
        self.assertEqual(self.snapshot(source), before)

    def materialContent(self, source):
        payload = bytes(source.ViewObject.dumpPropertyContent("ShapeAppearance"))
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        root = ET.fromstring(files["Persistence.xml"])
        material_list = root.find("MaterialList")
        self.assertIsNotNone(material_list)
        self.assertEqual(material_list.get("version"), "3")
        name = material_list.get("file")
        self.assertTrue(name)
        data = files[name]
        count = struct.unpack_from("<I", data)[0]
        offset = 4 + count * 24
        self.assertLessEqual(offset, len(data))
        metadata = []
        for index in range(count):
            fields = []
            for field in range(3):
                self.assertLessEqual(offset + 4, len(data))
                size = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                self.assertLessEqual(offset + size, len(data))
                fields.append(data[offset:offset + size])
                offset += size
            metadata.append(fields)
        self.assertEqual(offset, len(data))
        return files, name, data[:4 + count * 24], metadata


    def seedMaterialUUID(self, source, uuid):
        # App.Material's public Python wrapper does not expose UUID. Use the
        # ordinary property persistence API and its documented v3 list payload
        # to seed the same material identity that the appearance task writes.
        files, name, prefix, metadata = self.materialContent(source)
        material_uuid = uuid.encode("ascii")
        body = bytearray(prefix)
        for image, image_path, previous_uuid in metadata:
            for value in (image, image_path, material_uuid):
                body.extend(struct.pack("<I", len(value)))
                body.extend(value)
        files[name] = bytes(body)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry, content in files.items():
                archive.writestr(entry, content)
        source.ViewObject.restorePropertyContent("ShapeAppearance", output.getvalue())
        self.pump()
        self.assertTrue(metadata)
        self.assertEqual([fields[2] for fields in self.materialContent(source)[3]],
                         [material_uuid] * len(metadata))


    def appearanceChannels(self, source):
        # Do not compare App.Material objects: C++ identity equality may ignore
        # changed diffuse colors, and Base.Color equality packs to 8-bit RGBA.
        return tuple((tuple(material.AmbientColor), tuple(material.DiffuseColor),
                      tuple(material.SpecularColor), tuple(material.EmissiveColor),
                      material.Shininess, material.Transparency)
                     for material in source.ViewObject.ShapeAppearance)


    def checkMaterialUUID(self, accept):
        source = self.makeSource()
        # The current highlighting map contains both edges and faces. Matching
        # its size prevents a vector-size mismatch from masking UUID equality.
        count = len(source.Shape.Edges) + len(source.Shape.Faces)
        appearances = []
        for index in range(count):
            material = App.Material()
            material.DiffuseColor = (0.2, 0.35 + index * 0.01, 0.6, 1.0)
            material.SpecularColor = (0.15, 0.2, 0.25, 1.0)
            material.Shininess = 0.4
            appearances.append(material)
        source.ViewObject.ShapeAppearance = appearances
        material_uuid = "8fa3f5ad-231e-42aa-aeda-734200000001"
        self.seedMaterialUUID(source, material_uuid)
        before = self.appearanceChannels(source)
        line_before = tuple(tuple(color) for color in source.ViewObject.LineColorArray)
        self.openTask(source, face=True)
        self.clickButton("buttonRefAdd")
        during = self.appearanceChannels(source)
        self.assertEqual(len(during), len(before))
        self.assertEqual(during[0][1][:3], (1.0, 0.0, 1.0))
        self.assertNotEqual(during[0][1], before[0][1])
        self.assertEqual([fields[2] for fields in self.materialContent(source)[3]],
                         [material_uuid.encode("ascii")] * count)
        self.closeTask(accept)
        self.assertEqual(self.appearanceChannels(source), before,
                         "Restoration must compare actual material channels, not UUID identity")
        self.assertEqual(tuple(tuple(color) for color in source.ViewObject.LineColorArray),
                         line_before)
        self.assertEqual([fields[2] for fields in self.materialContent(source)[3]],
                         [material_uuid.encode("ascii")] * count)


    def testAcceptFaceHighlightWithMaterialUUID(self):
        self.checkMaterialUUID(True)


    def testRejectFaceHighlightWithMaterialUUIDControl(self):
        self.checkMaterialUUID(False)


    def testAcceptEdgeHighlightRestoresPreciseChannels(self):
        source = self.makeSource()
        # These values pack to the same 8-bit RGBA as magenta. They remain
        # distinguishable in the actual float channels returned by the property.
        source.ViewObject.LineColorArray = [
            (0.99991, 0.00009, 0.99993, 1.0)
            for edge in source.Shape.Edges
        ]
        before = tuple(tuple(color) for color in source.ViewObject.LineColorArray)
        self.assertNotEqual(before[0][:3], (1.0, 0.0, 1.0))
        self.assertEqual(tuple(round(value * 255) for value in before[0]),
                         (255, 0, 255, 255))
        self.openTask(source)
        self.clickButton("buttonRefAdd")
        during = tuple(tuple(color) for color in source.ViewObject.LineColorArray)
        self.assertEqual(during[0][:3], (1.0, 0.0, 1.0))
        self.assertEqual(len(during), len(before))
        self.assertNotEqual(during, before)
        self.closeTask(True)
        self.assertEqual(tuple(tuple(color) for color in source.ViewObject.LineColorArray),
                         before, "Restoration must preserve float channels, not only packed RGBA")
