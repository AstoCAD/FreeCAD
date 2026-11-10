# SPDX-License-Identifier: LGPL-2.1-or-later
"""Actual Part Mirror accepts real internal UTF8 source/document names.

The task caches the names as decoded UTF8 text. These tests exercise ordinary
XY mirroring with valid1800-volume geometry, separately from reference paths.
"""

import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtWidgets


class TestMirrorUnicodeNames(unittest.TestCase):
    def setUp(self):
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        Gui.activateWorkbench("PartWorkbench")
        self.doc = None
        self.retained = []
        self.messages = []
        self.modal_closer = QtCore.QTimer(Gui.getMainWindow())

        def closeUnexpectedModal():
            modal = QtWidgets.QApplication.activeModalWidget()
            if isinstance(modal, QtWidgets.QMessageBox):
                self.messages.append(modal.text())
                modal.reject()

        self.modal_closer.timeout.connect(closeUnexpectedModal)
        self.modal_closer.start(30)

    def tearDown(self):
        try:
            self.modal_closer.stop()
            self.modal_closer.deleteLater()
            if Gui.Control.activeDialog():
                Gui.Control.closeDialog()
            Gui.Selection.clearSelection()
            if self.doc is not None and self.doc.Name in App.listDocuments():
                App.closeDocument(self.doc.Name)
            self.retained.clear()
            if self.previous_document in App.listDocuments():
                App.setActiveDocument(self.previous_document)
        finally:
            if self.previous_workbench:
                Gui.activateWorkbench(self.previous_workbench)

    def _retain_ancestors(self, obj):
        while obj is not None:
            self.retained.append(obj)
            obj = obj.parent()

    def _check(self, document_name="MirrorNamesAudit", source_name="MirrorSource",
               source_label=None, document_label=None):
        self.doc = App.newDocument(document_name)
        self.assertEqual(self.doc.Name, document_name,
                         "The AstoCAD branch must preserve the actual requested internal name")
        if document_label is not None:
            self.doc.Label = document_label
        source = self.doc.addObject("Part::Box", source_name)
        self.assertEqual(source.Name, source_name,
                         "The AstoCAD branch must preserve the actual requested internal name")
        source.Length = 10
        source.Width = 12
        source.Height = 15
        if source_label is not None:
            source.Label = source_label
        self.doc.recompute()
        self.assertTrue(source.Shape.isValid())
        self.assertAlmostEqual(source.Shape.Volume, 1800)
        self.assertLess((source.Shape.CenterOfMass - App.Vector(5, 6, 7.5)).Length, 1e-8)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source)
        Gui.runCommand("Part_Mirror")
        dialog = Gui.Control.activeTaskDialog()
        self.assertIsNotNone(dialog)
        self.retained.append(dialog)
        content = dialog.getDialogContent()
        for widget in content:
            self._retain_ancestors(widget)
        shapes = next((widget.findChild(QtWidgets.QTreeWidget, "shapes")
                       for widget in content
                       if widget.findChild(QtWidgets.QTreeWidget, "shapes") is not None), None)
        self.assertIsNotNone(shapes)
        self._retain_ancestors(shapes)
        shapes_parent = shapes.parentWidget()
        self.retained.append(shapes_parent)
        combo = shapes_parent.findChild(QtWidgets.QComboBox, "comboBox")
        self.assertIsNotNone(combo)
        self.retained.append(combo)
        Gui.updateGui()
        selected = shapes.selectedItems()
        self.assertEqual(len(selected), 1,
                         "Normal constructor preselection must identify the original source")
        self.assertEqual(selected[0].text(0), source.Label)
        cached_name = selected[0].data(0, QtCore.Qt.UserRole)
        self.assertEqual(cached_name, source.Name,
                         "The task caches the internal name as decoded text")
        self.assertEqual(combo.currentIndex(), 0,
                         "The ordinary XY plane isolates source/document command identity")
        dialog.accept()
        Gui.updateGui()
        mirrors = [obj for obj in self.doc.Objects if obj.TypeId == "Part::Mirroring"]
        self.assertEqual(len(mirrors), 1)
        mirror = mirrors[0]
        self.assertEqual(mirror.Source, source)
        self.assertNotIn("Invalid", mirror.State)
        self.assertFalse(mirror.Shape.isNull())
        self.assertTrue(mirror.Shape.isValid())
        self.assertAlmostEqual(mirror.Shape.Volume, 1800, places=7)
        self.assertLess((mirror.Shape.CenterOfMass - App.Vector(5, 6, -7.5)).Length, 1e-8)
        self.assertEqual(mirror.Label, source.Label + " (Mirror #1)")

    def test_ascii_names_control(self):
        self._check()

    def test_unicode_source_label_control(self):
        self._check(source_label="源部件 Ω café")

    def test_unicode_document_label_control(self):
        self._check(document_label="镜像文档 Ω café")

    def test_unicode_source_internal_name(self):
        self._check(source_name="源形体")

    def test_unicode_document_internal_name(self):
        self._check(document_name="镜像文档")

    def test_unicode_source_and_document_internal_names(self):
        self._check(document_name="镜像文档", source_name="源形体")
