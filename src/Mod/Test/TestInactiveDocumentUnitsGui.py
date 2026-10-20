# SPDX-License-Identifier: LGPL-2.1-or-later
"""Preserve the active document when another document's properties change."""

import tempfile
import unittest
from pathlib import Path

import FreeCAD as App
if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets


@unittest.skipIf(not App.GuiUp, "Requires native GUI document and schema callbacks")
class TestInactiveDocumentUnits(unittest.TestCase):
    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "Run in an isolated native GUI process")
        self.names = []
        self.retained = []
        self.previous_schema = App.Units.getSchema()
        self.parameters = App.ParamGet("User parameter:BaseApp/Preferences/Units")
        self.parameters_before = self.parameters.GetContents()
        self.addCleanup(self._cleanup)
        self.assertFalse(self.parameters.GetBool("IgnoreProjectSchema", False),
                         "Use the existing ordinary per-document unit mode")
        areas = Gui.getMainWindow().findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]
        self.retained.append(self.area)
        self.temporary = tempfile.TemporaryDirectory(prefix="fc14862_inactive_")

    def _cleanup(self):
        for name in reversed(self.names):
            if name in App.listDocuments():
                App.closeDocument(name)
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        Gui.updateGui()
        App.Units.setSchema(self.previous_schema)
        try:
            self.assertEqual(self.parameters.GetContents(), self.parameters_before,
                             "Unit preferences must remain exactly unchanged")
        finally:
            if hasattr(self, "temporary"):
                self.temporary.cleanup()

    def _new(self, name=None):
        before = list(self.area.subWindowList())
        doc = App.newDocument() if name is None else App.newDocument(name)
        self.names.append(doc.Name)
        Gui.updateGui()
        created = [window for window in self.area.subWindowList() if window not in before]
        self.assertEqual(len(created), 1)
        window = created[0]
        view = window.widget()
        self.retained.extend((window, view))
        self.assertTrue(view.inherits("Gui::View3DInventor"))
        self.assertIs(self.area.activeSubWindow(), window)
        self.assertEqual(App.activeDocument().Name, doc.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, doc.Name)
        self.assertFalse(Gui.getDocument(doc.Name).Modified)
        self.assertFalse(view.isWindowModified())
        return doc, view

    def _documents(self, default_owner):
        owner, owner_view = self._new(None if default_owner else "InactiveOwner14862")
        if default_owner:
            self.assertEqual(owner.Label, "Unnamed")
        else:
            self.assertEqual(owner.Label, "InactiveOwner14862")
        descriptions = owner.getEnumerationsOfProperty("UnitSystem")
        self.assertGreaterEqual(len(descriptions), 3)
        owner_schema = descriptions.index(str(owner.UnitSystem))
        peer, peer_view = self._new("ActivePeer14862")
        peer_schema = (owner_schema + 1) % len(descriptions)
        peer.UnitSystem = peer_schema
        self.assertEqual(str(peer.UnitSystem), descriptions[peer_schema])
        self.assertEqual(App.Units.getSchema(), peer_schema)
        self.assertTrue(Gui.getDocument(peer.Name).Modified)
        path = Path(self.temporary.name) / "active_peer.FCStd"
        peer.saveAs(str(path))
        self.assertTrue(path.is_file())
        self.assertTrue(Gui.getDocument(peer.Name).save())
        Gui.updateGui()
        self.assertFalse(Gui.getDocument(peer.Name).Modified)
        self.assertFalse(peer_view.isWindowModified())
        self.assertFalse(Gui.getDocument(owner.Name).Modified)
        self.assertFalse(owner_view.isWindowModified())
        self.assertEqual(App.activeDocument().Name, peer.Name)
        self.assertEqual(str(owner.UnitSystem), descriptions[owner_schema])
        self.assertEqual(App.Units.getSchema(), peer_schema)
        self.assertNotEqual(owner_schema, peer_schema)
        return owner, owner_view, peer, peer_view, descriptions, owner_schema, peer_schema

    def _inactive_change(self, default_owner, property_name):
        (owner, owner_view, peer, peer_view, descriptions,
         owner_schema, peer_schema) = self._documents(default_owner)
        peer_state = (peer.Label, peer.Comment, peer.Company, str(peer.UnitSystem))
        if property_name == "UnitSystem":
            new_owner_schema = (peer_schema + 1) % len(descriptions)
            self.assertNotEqual(new_owner_schema, owner_schema)
            self.assertNotEqual(new_owner_schema, peer_schema)
            target = descriptions[new_owner_schema]
            owner.UnitSystem = new_owner_schema
            self.assertEqual(str(owner.UnitSystem), target)
        else:
            target = getattr(owner, property_name) + " changed while inactive14862"
            setattr(owner, property_name, target)
            self.assertEqual(getattr(owner, property_name), target)
        Gui.updateGui()
        self.assertEqual(str(getattr(owner, property_name)), str(target))
        with self.subTest(oracle="active_document_identity"):
            self.assertEqual(App.activeDocument().Name, peer.Name)
            self.assertEqual(Gui.activeDocument().Document.Name, peer.Name)
        with self.subTest(oracle="active_document_properties_unchanged"):
            self.assertEqual((peer.Label, peer.Comment, peer.Company, str(peer.UnitSystem)),
                             peer_state,
                             "An inactive document edit must not alter the active document")
        with self.subTest(oracle="active_native_schema_unchanged"):
            self.assertEqual(App.Units.getSchema(), peer_schema)
        with self.subTest(oracle="active_document_stays_clean"):
            self.assertFalse(Gui.getDocument(peer.Name).Modified)
        with self.subTest(oracle="active_MDI_stays_clean"):
            self.assertFalse(peer_view.isWindowModified())
        with self.subTest(oracle="edited_owner_modified"):
            self.assertTrue(Gui.getDocument(owner.Name).Modified)
        with self.subTest(oracle="edited_owner_MDI_modified"):
            self.assertTrue(owner_view.isWindowModified())

    def test_named_inactive_comment_preserves_active_schema(self):
        self._inactive_change(False, "Comment")

    def test_named_inactive_company_preserves_active_schema(self):
        self._inactive_change(False, "Company")

    def test_named_inactive_units_preserves_active_schema(self):
        self._inactive_change(False, "UnitSystem")




    def test_active_document_units_updates_native_schema_control(self):
        (owner, owner_view, peer, peer_view, descriptions,
         owner_schema, peer_schema) = self._documents(False)
        target = (peer_schema + 1) % len(descriptions)
        peer.UnitSystem = target
        Gui.updateGui()
        self.assertEqual(str(peer.UnitSystem), descriptions[target])
        self.assertEqual(App.Units.getSchema(), target)
        self.assertTrue(Gui.getDocument(peer.Name).Modified)
        self.assertTrue(peer_view.isWindowModified())
        self.assertEqual(str(owner.UnitSystem), descriptions[owner_schema])
        self.assertFalse(Gui.getDocument(owner.Name).Modified)
        self.assertFalse(owner_view.isWindowModified())
