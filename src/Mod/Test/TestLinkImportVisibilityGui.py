# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regression tests for the visibility of objects imported by Std_LinkImport."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import FreeCADGui as Gui


class TestLinkImportVisibilityGui(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.src = App.newDocument("LinkImportSource")
        self.dst = App.newDocument("LinkImportTarget")

    def tearDown(self):
        Gui.Selection.clearSelection()
        for name in (self.dst.Name, self.src.Name):
            if name in App.listDocuments():
                App.closeDocument(name)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def makeLinkedContainer(self):
        part = self.src.addObject("App::Part", "Container")
        shown = self.src.addObject("Part::Box", "Shown")
        shown.Label = "ShownChild"
        hidden = self.src.addObject("Part::Box", "Hidden")
        hidden.Label = "HiddenChild"
        part.addObject(shown)
        part.addObject(hidden)
        hidden.Visibility = False
        self.src.recompute()
        self.src.saveAs(os.path.join(self.tmpdir, "LinkImportSource.FCStd"))
        self.dst.saveAs(os.path.join(self.tmpdir, "LinkImportTarget.FCStd"))

        link = self.dst.addObject("App::Link", "Link")
        link.setLink(part)
        self.dst.recompute()
        return link

    def importLink(self, link, command):
        App.setActiveDocument(self.dst.Name)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(link)
        Gui.runCommand(command)
        Gui.Selection.clearSelection()
        imported = link.LinkedObject
        self.assertIsNotNone(imported)
        self.assertEqual(imported.Document, self.dst)
        return imported

    def checkImported(self, imported):
        # issue #28656: only the imported object that the link displays is hidden,
        # its children keep their visibility, otherwise the link shows nothing
        self.assertFalse(imported.Visibility)
        children = {obj.Label: obj for obj in imported.Group}
        self.assertIn("ShownChild", children)
        self.assertIn("HiddenChild", children)
        self.assertTrue(children["ShownChild"].Visibility)
        self.assertFalse(children["HiddenChild"].Visibility)

    def testLinkImportKeepsChildVisibility(self):
        link = self.makeLinkedContainer()
        self.checkImported(self.importLink(link, "Std_LinkImport"))

    def testLinkImportAllKeepsChildVisibility(self):
        link = self.makeLinkedContainer()
        self.checkImported(self.importLink(link, "Std_LinkImportAll"))
