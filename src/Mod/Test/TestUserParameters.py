# SPDX-License-Identifier: LGPL-2.1-or-later
"""User parameters (`myVar = 23 mm`): the App helper and its Python binding.

See App/UserParameters.h. Parameters are properties of the group 'UserParameters'; their names
are unique in a document and references from other objects are stored qualified.
"""

import os
import tempfile
import unittest

import FreeCAD as App


class TestUserParameters(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("UserParameters")
        self.holder = self.doc.addObject("App::VarSet", "Holder")
        self.other = self.doc.addObject("App::VarSet", "Other")
        self.other.addProperty("App::PropertyDistance", "Target", "Base")
        self.files = []

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        for path in self.files:
            if os.path.exists(path):
                os.remove(path)

    def test_create_and_find(self):
        name = self.doc.addUserParameter(self.holder, "myVar", "23 mm")
        self.assertEqual(name, "myVar")
        self.assertEqual(self.holder.getGroupOfProperty("myVar"), "UserParameters")
        self.assertEqual(self.holder.getTypeIdOfProperty("myVar"), "App::PropertyDistance")
        self.assertAlmostEqual(self.holder.myVar.Value, 23.0)
        self.assertEqual(self.holder.ExpressionEngine, [])
        self.assertEqual(self.doc.findUserParameter("myVar"), (self.holder, "myVar"))
        self.assertIsNone(self.doc.findUserParameter("nothing"))
        self.assertEqual(self.doc.getUserParameters(), [(self.holder, "myVar")])

    def test_names_are_unique(self):
        self.doc.addUserParameter(self.holder, "myVar", "1 mm")
        self.assertNotEqual(self.doc.checkUserParameterName("myVar", self.other), "")
        self.assertNotEqual(self.doc.checkUserParameterName("Other"), "")
        self.assertNotEqual(self.doc.checkUserParameterName("Target", self.other), "")
        self.assertNotEqual(self.doc.checkUserParameterName("mm"), "")
        self.assertEqual(self.doc.checkUserParameterName("free", self.other), "")
        self.assertIn("cell", self.doc.checkUserParameterName("B5"))
        self.assertEqual(self.doc.checkUserParameterName("b5"), "")
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.holder, "AA12", "1 mm")
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.other, "myVar", "2 mm")
        self.assertNotIn("myVar", self.other.PropertiesList)

    def test_expression_parameter_and_reference(self):
        self.doc.addUserParameter(self.holder, "base", "10 mm")
        # created on another object: "base" is resolved to Holder.base
        self.doc.addUserParameter(self.other, "twice", "2 * base")
        self.assertEqual(dict(self.other.ExpressionEngine)["twice"], "2 * Holder.base")
        self.assertIn(self.holder, self.other.OutList)
        self.doc.recompute()
        self.assertAlmostEqual(self.other.twice.Value, 20.0)
        self.holder.base = 4
        self.doc.recompute()
        self.assertAlmostEqual(self.other.twice.Value, 8.0)

    def test_rename_updates_references(self):
        self.doc.addUserParameter(self.holder, "base", "10 mm")
        self.other.setExpression("Target", "Holder.base * 3")
        self.doc.renameUserParameter(self.holder, "base", "width")
        self.assertNotIn("base", self.holder.PropertiesList)
        self.assertEqual(dict(self.other.ExpressionEngine)["Target"], "Holder.width * 3")
        self.doc.recompute()
        self.assertAlmostEqual(self.other.Target.Value, 30.0)

    def test_save_restore_keeps_qualified_reference(self):
        self.doc.addUserParameter(self.holder, "base", "10 mm")
        self.doc.addUserParameter(self.other, "twice", "2 * base")
        self.doc.recompute()
        path = os.path.join(tempfile.gettempdir(), "TestUserParameters.FCStd")
        self.files.append(path)
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        holder = self.doc.getObject("Holder")
        other = self.doc.getObject("Other")
        self.assertEqual(holder.getGroupOfProperty("base"), "UserParameters")
        self.assertEqual(dict(other.ExpressionEngine)["twice"], "2 * Holder.base")
        self.assertEqual(self.doc.findUserParameter("twice"), (other, "twice"))
        holder.base = 1
        self.doc.recompute()
        self.assertAlmostEqual(other.twice.Value, 2.0)

    def test_deleted_owner_is_refused(self):
        # A deleted object kept for undo is no longer in the document: it must not get or
        # rename parameters (rename used to fail halfway, after renaming the property).
        self.doc.UndoMode = 1
        self.doc.openTransaction("add")
        gone = self.doc.addObject("App::VarSet", "Gone")
        self.doc.addUserParameter(gone, "goneVar", "1 mm")
        self.doc.commitTransaction()
        self.doc.openTransaction("remove")
        self.doc.removeObject("Gone")
        self.doc.commitTransaction()
        with self.assertRaises(ValueError):
            self.doc.addUserParameter(gone, "another", "2 mm")
        with self.assertRaises(ValueError):
            self.doc.renameUserParameter(gone, "goneVar", "renamed")
        with self.assertRaises(ValueError):
            self.doc.checkUserParameterName("another", gone)
        self.assertEqual(self.doc.getUserParameters(), [])
        self.doc.undo()
        restored = self.doc.getObject("Gone")
        self.assertEqual(self.doc.getUserParameters(), [(restored, "goneVar")])

    def test_copy_makes_name_ambiguous_without_breaking_references(self):
        self.doc.addUserParameter(self.holder, "base", "10 mm")
        self.other.setExpression("Target", "Holder.base")
        self.doc.copyObject(self.holder)
        self.assertIsNone(self.doc.findUserParameter("base"))
        self.doc.recompute()
        self.assertAlmostEqual(self.other.Target.Value, 10.0)
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.other, "again", "base")
