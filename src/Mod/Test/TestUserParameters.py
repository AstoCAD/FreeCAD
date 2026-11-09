# SPDX-License-Identifier: LGPL-2.1-or-later
"""User parameters (`myVar = 23 mm`): the App helper and its Python binding.

See App/UserParameters.h. Parameters are properties of the group 'UserParameters' of one variable
set of the document, 'UserParameters', created with the first parameter; their names are unique
in a document and references from other objects are stored qualified.
"""

import os
import tempfile
import unittest

import FreeCAD as App


class TestUserParameters(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("UserParameters")
        # The object in which the parameters are typed
        self.typed = self.doc.addObject("App::VarSet", "Typed")
        self.typed.addProperty("App::PropertyLength", "Length", "Base")
        self.typed.Length = 20
        self.other = self.doc.addObject("App::VarSet", "Other")
        self.other.addProperty("App::PropertyDistance", "Target", "Base")
        self.files = []

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        for path in self.files:
            if os.path.exists(path):
                os.remove(path)

    def holder(self):
        return self.doc.getObject("UserParameters")

    def test_create_and_find(self):
        self.assertIsNone(self.holder())
        name = self.doc.addUserParameter(self.typed, "myVar", "23 mm")
        self.assertEqual(name, "myVar")
        holder = self.holder()
        self.assertIsNotNone(holder, "Expected the first parameter to create the holder")
        self.assertEqual(holder.TypeId, "App::VarSet")
        self.assertEqual(holder.Label, "User Parameters")
        self.assertEqual(holder.getGroupOfProperty("myVar"), "UserParameters")
        self.assertEqual(holder.getTypeIdOfProperty("myVar"), "App::PropertyDistance")
        self.assertAlmostEqual(holder.myVar.Value, 23.0)
        self.assertEqual(holder.ExpressionEngine, [])
        # Not on the object in which it was typed
        self.assertNotIn("myVar", self.typed.PropertiesList)
        self.assertEqual(self.doc.findUserParameter("myVar"), (holder, "myVar"))
        self.assertIsNone(self.doc.findUserParameter("nothing"))
        self.assertEqual(self.doc.getUserParameters(), [(holder, "myVar")])

    def check_values(self, cases):
        for name, value, typeId, internal in cases:
            self.doc.addUserParameter(self.typed, name, value)
            holder = self.holder()
            self.assertEqual(holder.getTypeIdOfProperty(name), typeId, value)
            self.assertAlmostEqual(getattr(holder, name).Value, internal, msg=value)
        self.assertEqual(self.holder().ExpressionEngine, [])

    def test_time(self):
        # The type of a time is App::PropertyTime, not named after the unit type (TimeSpan)
        self.check_values(
            (
                ("seconds", "5 s", "App::PropertyTime", 5.0),
                ("minutes", "2 min", "App::PropertyTime", 120.0),
            )
        )

    def test_number_with_compound_unit_is_a_value(self):
        # Like `10 N`: a value, not an expression bound to the parameter
        self.check_values(
            (
                ("speed", "3 m/s", "App::PropertyVelocity", 3000.0),
                ("negative", "-3 m/s", "App::PropertyVelocity", -3000.0),
                ("area", "5 mm^2", "App::PropertyArea", 5.0),
                ("inverse", "2 m^-1", "App::PropertyInverseLength", 0.002),
                ("acceleration", "9.81 m/s^2", "App::PropertyAcceleration", 9810.0),
            )
        )
        # A computation stays an expression
        self.doc.addUserParameter(self.typed, "computed", "3 m/s * 2")
        self.assertEqual(
            [path for path, _ in self.holder().ExpressionEngine], ["computed"]
        )
        self.assertAlmostEqual(self.holder().computed.Value, 6000.0)

    def test_quantity_times_function_is_an_expression(self):
        # A function is not a unit: `10 mm / cos(Angle)` follows the angle
        self.typed.addProperty("App::PropertyAngle", "Angle", "Base")
        self.typed.Angle = 60
        self.doc.addUserParameter(self.typed, "slanted", "10 mm / cos(Angle)")
        self.doc.addUserParameter(self.typed, "sine", "10 mm * sin(30 deg)")
        holder = self.holder()
        expressions = dict(holder.ExpressionEngine)
        self.assertIn("slanted", expressions)
        self.assertIn("sine", expressions)
        self.doc.recompute()
        self.assertAlmostEqual(holder.slanted.Value, 20.0)
        self.assertAlmostEqual(holder.sine.Value, 5.0)
        self.typed.Angle = 0
        self.doc.recompute()
        self.assertAlmostEqual(holder.slanted.Value, 10.0)

    def test_text(self):
        # https://github.com/AstoCAD/FreeCAD/issues/171
        self.doc.addUserParameter(self.typed, "material", "<<Steel>>")
        holder = self.holder()
        self.assertEqual(holder.getTypeIdOfProperty("material"), "App::PropertyString")
        self.assertEqual(holder.getGroupOfProperty("material"), "UserParameters")
        self.assertEqual(holder.material, "Steel")
        self.assertEqual(holder.ExpressionEngine, [])
        # A computed text stays an expression
        self.doc.addUserParameter(self.typed, "grade", "material + <<-S235>>")
        self.assertEqual([path for path, _ in holder.ExpressionEngine], ["grade"])
        self.assertEqual(holder.grade, "Steel-S235")
        self.assertEqual(
            self.doc.getUserParameters(), [(holder, "material"), (holder, "grade")]
        )
        # What is neither a number nor a text is refused and leaves nothing behind
        with self.assertRaises(TypeError):
            self.doc.addUserParameter(self.typed, "items", "list(1, 2)")
        self.assertNotIn("items", holder.PropertiesList)

    def test_unit_without_property_type_is_refused(self):
        # No property type stores a concentration: refused before anything is created
        with self.assertRaises(TypeError):
            self.doc.addUserParameter(self.typed, "molar", "2 mol/m^3")
        self.assertIsNone(self.holder())
        self.assertEqual(self.doc.getUserParameters(), [])

    def test_parameters_share_one_holder(self):
        self.doc.addUserParameter(self.typed, "first", "1 mm")
        self.doc.addUserParameter(self.other, "second", "2 mm")
        holder = self.holder()
        self.assertEqual(len(self.doc.findObjects("App::VarSet")), 3)
        self.assertEqual(self.doc.getUserParameters(), [(holder, "first"), (holder, "second")])

    def test_names_are_unique(self):
        self.doc.addUserParameter(self.typed, "myVar", "1 mm")
        self.assertNotEqual(self.doc.checkUserParameterName("myVar", self.other), "")
        self.assertNotEqual(self.doc.checkUserParameterName("Other"), "")
        # A property of the object in which the name is typed means that property there
        self.assertNotEqual(self.doc.checkUserParameterName("Target", self.other), "")
        self.assertEqual(self.doc.checkUserParameterName("Target", self.typed), "")
        # A property of the holder
        self.assertNotEqual(self.doc.checkUserParameterName("Label"), "")
        self.assertNotEqual(self.doc.checkUserParameterName("mm"), "")
        self.assertEqual(self.doc.checkUserParameterName("free", self.other), "")
        self.assertIn("cell", self.doc.checkUserParameterName("B5"))
        self.assertEqual(self.doc.checkUserParameterName("b5"), "")
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.typed, "AA12", "1 mm")
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.other, "myVar", "2 mm")
        self.assertEqual(self.doc.getUserParameters(), [(self.holder(), "myVar")])

    def test_python_attribute_names_are_refused(self):
        # A property hides the Python attribute of the same name: obj.Name would be the parameter
        python = self.doc.addObject("App::FeaturePython", "Python")
        names = ("Name", "Document", "State", "InList", "ViewObject", "TypeId", "Content")
        methods = ("recompute", "touch", "addProperty", "setExpression")
        for typed in (self.typed, python, None):
            for name in names + methods:
                self.assertIn("Python", self.doc.checkUserParameterName(name, typed), name)
                if typed:
                    with self.assertRaises(Exception):
                        self.doc.addUserParameter(typed, name, "20 mm")
        # Refused before anything is created
        self.assertIsNone(self.holder())
        self.assertEqual(self.doc.getUserParameters(), [])

        self.doc.addUserParameter(self.typed, "myVar", "1 mm")
        holder = self.holder()
        with self.assertRaises(Exception):
            self.doc.renameUserParameter(holder, "myVar", "Name")
        self.assertIn("myVar", holder.PropertiesList)
        self.assertEqual(holder.Name, "UserParameters")
        self.assertEqual(holder.Document.Name, self.doc.Name)
        # Not attributes of the holder: a name that only differs in case, an attribute of types
        self.assertEqual(self.doc.checkUserParameterName("name", self.typed), "")
        self.assertEqual(self.doc.checkUserParameterName("mro", self.typed), "")

    def test_expression_parameter_and_reference(self):
        self.doc.addUserParameter(self.typed, "base", "10 mm")
        # "base" is resolved to the parameter wherever it is typed
        self.doc.addUserParameter(self.other, "twice", "2 * base")
        holder = self.holder()
        self.assertNotIn("twice", self.other.PropertiesList)
        self.assertEqual(dict(holder.ExpressionEngine)["twice"], "2 * base")
        self.other.setExpression("Target", "UserParameters.twice")
        self.assertIn(holder, self.other.OutList)
        self.doc.recompute()
        self.assertAlmostEqual(holder.twice.Value, 20.0)
        self.assertAlmostEqual(self.other.Target.Value, 20.0)
        holder.base = 4
        self.doc.recompute()
        self.assertAlmostEqual(holder.twice.Value, 8.0)
        self.assertAlmostEqual(self.other.Target.Value, 8.0)

    def test_value_from_the_object_it_is_typed_in(self):
        # `Length` means the Length of the object in which it is typed: on the holder it is
        # written with the name of that object, in both spellings.
        self.doc.addUserParameter(self.typed, "half", "Length / 2")
        self.doc.addUserParameter(self.typed, "third", ".Length / 4")
        holder = self.holder()
        expressions = dict(holder.ExpressionEngine)
        self.assertEqual(expressions["half"], "Typed.Length / 2")
        self.assertEqual(expressions["third"], "Typed.Length / 4")
        self.doc.recompute()
        self.assertAlmostEqual(holder.half.Value, 10.0)
        self.assertAlmostEqual(holder.third.Value, 5.0)
        self.typed.Length = 40
        self.doc.recompute()
        self.assertAlmostEqual(holder.half.Value, 20.0)
        # The holder now depends on that object, which therefore cannot use a parameter
        with self.assertRaises(Exception):
            self.typed.setExpression("Length", "UserParameters.half")
        # Another object can
        self.other.setExpression("Target", "UserParameters.half")
        self.doc.recompute()
        self.assertAlmostEqual(self.other.Target.Value, 20.0)

    def test_rename_updates_references(self):
        self.doc.addUserParameter(self.typed, "base", "10 mm")
        self.doc.addUserParameter(self.typed, "twice", "2 * base")
        holder = self.holder()
        self.other.setExpression("Target", "UserParameters.base * 3")
        # Any object of the document can be given, the parameter is found by its name
        self.doc.renameUserParameter(self.other, "base", "width")
        self.assertNotIn("base", holder.PropertiesList)
        self.assertIn("width", holder.PropertiesList)
        self.assertEqual(dict(self.other.ExpressionEngine)["Target"], "UserParameters.width * 3")
        self.doc.recompute()
        self.assertAlmostEqual(self.other.Target.Value, 30.0)
        self.assertAlmostEqual(holder.twice.Value, 20.0)
        holder.width = 1
        self.doc.recompute()
        self.assertAlmostEqual(holder.twice.Value, 2.0)

    def test_save_restore_keeps_qualified_reference(self):
        self.doc.addUserParameter(self.typed, "base", "10 mm")
        self.doc.addUserParameter(self.other, "twice", "2 * base")
        self.other.setExpression("Target", "UserParameters.twice")
        self.doc.recompute()
        path = os.path.join(tempfile.gettempdir(), "TestUserParameters.FCStd")
        self.files.append(path)
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        holder = self.holder()
        other = self.doc.getObject("Other")
        self.assertEqual(holder.getGroupOfProperty("base"), "UserParameters")
        self.assertEqual(dict(other.ExpressionEngine)["Target"], "UserParameters.twice")
        self.assertEqual(self.doc.findUserParameter("twice"), (holder, "twice"))
        holder.base = 1
        self.doc.recompute()
        self.assertAlmostEqual(other.Target.Value, 2.0)
        # A parameter added after reopening goes to the same holder
        self.doc.addUserParameter(other, "later", "3 mm")
        self.assertEqual(self.doc.findUserParameter("later"), (holder, "later"))
        self.assertEqual(len(self.doc.findObjects("App::VarSet")), 3)

    def test_undo_of_the_first_parameter_removes_the_holder(self):
        self.doc.UndoMode = 1
        self.doc.openTransaction("create")
        self.doc.addUserParameter(self.typed, "myVar", "1 mm")
        self.doc.commitTransaction()
        self.assertIsNotNone(self.holder())
        self.doc.undo()
        self.assertIsNone(self.holder())
        self.assertEqual(self.doc.getUserParameters(), [])
        self.doc.redo()
        self.assertAlmostEqual(self.holder().myVar.Value, 1.0)

    def test_refused_parameter_leaves_no_holder(self):
        for name, value in (("Label", "1 mm"), ("x", "nope + 1"), ("AA12", "1 mm"), ("mm", "1")):
            with self.assertRaises(Exception):
                self.doc.addUserParameter(self.typed, name, value)
            self.assertIsNone(self.holder(), name)
        # With a holder, a refused parameter leaves it as it was
        self.doc.addUserParameter(self.typed, "kept", "1 mm")
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.typed, "x", "nope + 1")
        self.assertEqual(self.doc.getUserParameters(), [(self.holder(), "kept")])

    def test_holder_name_taken_by_another_object(self):
        taken = App.newDocument("UserParametersTaken")
        obj = taken.addObject("App::FeaturePython", "UserParameters")
        with self.assertRaises(Exception):
            taken.addUserParameter(obj, "myVar", "1 mm")
        self.assertEqual(taken.getUserParameters(), [])
        self.assertEqual(len(taken.Objects), 1)

    def test_deleted_object_is_refused(self):
        # A deleted object kept for undo is no longer in the document: nothing can be typed in
        # it. The parameters typed in it before are on the holder and stay.
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
        self.assertEqual(self.doc.getUserParameters(), [(self.holder(), "goneVar")])

    def test_parameters_of_older_documents(self):
        # Before the holder existed, a parameter was a property of the object in which it was
        # typed. Such parameters are found, used and renamed as before; new ones go to the holder.
        old = self.doc.addObject("App::VarSet", "Old")
        old.addProperty("App::PropertyDistance", "legacy", "UserParameters")
        old.legacy = 5
        self.assertEqual(self.doc.getUserParameters(), [(old, "legacy")])
        self.assertEqual(self.doc.findUserParameter("legacy"), (old, "legacy"))
        self.assertNotEqual(self.doc.checkUserParameterName("legacy", self.other), "")
        self.assertIsNone(self.holder())

        self.doc.addUserParameter(self.other, "twice", "2 * legacy")
        holder = self.holder()
        self.assertEqual(dict(holder.ExpressionEngine)["twice"], "2 * Old.legacy")
        self.assertNotIn("twice", old.PropertiesList)
        self.doc.renameUserParameter(old, "legacy", "renamed")
        self.assertIn("renamed", old.PropertiesList)
        self.assertEqual(dict(holder.ExpressionEngine)["twice"], "2 * Old.renamed")
        self.doc.recompute()
        self.assertAlmostEqual(holder.twice.Value, 10.0)

    def test_copy_makes_name_ambiguous_without_breaking_references(self):
        self.doc.addUserParameter(self.typed, "base", "10 mm")
        self.other.setExpression("Target", "UserParameters.base")
        self.doc.copyObject(self.holder())
        self.assertIsNone(self.doc.findUserParameter("base"))
        self.doc.recompute()
        self.assertAlmostEqual(self.other.Target.Value, 10.0)
        with self.assertRaises(Exception):
            self.doc.addUserParameter(self.other, "again", "base")
