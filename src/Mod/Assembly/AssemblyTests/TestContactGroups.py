# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2026 AstoCAD     <hello@astocad.com>                     *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

"""Contact-set selection, occurrence identity, and native response regressions."""
import os
import tempfile
import unittest
import FreeCAD as App
import Dynamics


class TestContactGroups(unittest.TestCase):
    def setUp(self):
        from AssemblyTests.TestContact import TestContact
        self.fixture = TestContact()
        self.fixture.setUp()
        self.a = self.fixture.sphere("A", -9)
        self.b = self.fixture.sphere("B", 9)
        self.c = self.fixture.linked_part_sphere("LinkedPart", 100)
        self.d = self.fixture.sphere("D", 200)
        self.contact = Dynamics.create_contact(self.fixture.assembly, mode="Between component sets")
        self.contact.ComponentsI = [self.a, self.b]
        self.contact.ComponentsJ = [self.c, self.d]

    def tearDown(self):
        self.fixture.tearDown()

    def native(self):
        study = self.fixture.study("0.000001 s")
        study.OutputStep = study.EndTime
        return study, Dynamics.run(study)

    def test_sets_exclusions_and_native_pair_count(self):
        self.assertEqual(len(Dynamics.contact_pairs(self.contact)), 4)
        Dynamics.set_contact_exclusions(self.contact, [(self.a, self.c), (self.c, self.a)])
        self.assertEqual(len(Dynamics.contact_pairs(self.contact)), 3)
        _, data = self.native()
        self.assertEqual(len(data["Loads"]), 3)

    def test_overlapping_sets_remove_self_and_reverse_pairs(self):
        self.contact.ComponentsI = [self.a, self.b, self.a]
        self.contact.ComponentsJ = [self.b, self.a, self.c]
        self.assertEqual(len(Dynamics.contact_pairs(self.contact)), 3)
        _, data = self.native()
        self.assertEqual(len(data["Loads"]), 3)

    def test_within_set_and_duplicate_definitions_do_not_double_force(self):
        self.contact.Mode = "Within a component set"
        self.contact.ComponentsI = [self.a, self.b]
        # The first definition supplies the parameters in both native paths.
        other = Dynamics.create_contact(self.fixture.assembly, self.b, self.a)
        other.Stiffness = "10 N/mm"
        _, data = self.native()
        self.assertEqual(len(data["Loads"]), 1)
        result = next(iter(data["Loads"].values()))
        self.assertAlmostEqual(abs(result["ForceX"][0]), 2, delta=1e-5)

    def test_general_mode_exclusions(self):
        self.contact.Mode = "General collision detection"
        Dynamics.set_contact_exclusions(self.contact, [(self.a, self.b), (self.a, self.c)])
        self.assertEqual(len(Dynamics.contact_pairs(self.contact)), 4)
        _, data = self.native()
        self.assertEqual(len(data["Loads"]), 4)

    def test_empty_or_foreign_members_rejected(self):
        self.contact.ComponentsI = []
        with self.assertRaises(ValueError): Dynamics.contact_pairs(self.contact)
        with self.assertRaises(RuntimeError): self.native()
        self.contact.ComponentsI = [self.c.LinkedObject]
        with self.assertRaises(ValueError): Dynamics.contact_pairs(self.contact)
        with self.assertRaises(RuntimeError): self.native()

    def test_exclusions_deleted_endpoint_and_name_reuse(self):
        Dynamics.set_contact_exclusions(self.contact, [(self.a, self.c)])
        old_name = self.c.Name
        self.fixture.doc.removeObject(old_name)
        replacement = self.fixture.sphere(old_name, 100)
        self.contact.ComponentsJ = [replacement, self.d]
        self.assertEqual(self.contact.ExcludedPairs, [])
        self.assertEqual(len(Dynamics.contact_pairs(self.contact)), 4)

    def test_scope_and_result_invalidation(self):
        study, _ = self.native()
        self.contact.ComponentsI = [self.a]
        self.assertEqual(study.Status, "NotRun")
        self.assertTrue(Dynamics.is_global_input(self.contact))
        local = Dynamics.create_contact(study, mode="Within a component set")
        local.ComponentsI = [self.a, self.b]
        other = self.fixture.study("0.000001 s")
        other.OutputStep = other.EndTime
        self.assertNotIn(local, Dynamics.inputs_for_study(other))
        self.assertEqual(len(Dynamics.run(other)["Loads"]), 2)
        self.assertEqual(len(Dynamics.run(study)["Loads"]), 3)

    def test_persistence_preserves_occurrences_and_exclusions(self):
        Dynamics.set_contact_exclusions(self.contact, [(self.a, self.c)])
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "ContactGroups.FCStd")
            self.fixture.doc.saveAs(filename)
            name = self.contact.Name
            member_names = [self.c.Name, self.d.Name]
            App.closeDocument(self.fixture.doc.Name)
            saved = App.openDocument(filename)
            self.fixture.doc = saved
            restored = saved.getObject(name)
            self.assertEqual(restored.Mode, "Between component sets")
            self.assertEqual([v.Name for v in restored.ComponentsJ], member_names)
            self.assertEqual(len(Dynamics.contact_pairs(restored)), 3)

    def test_task_set_membership_and_exclusions(self):
        if not App.GuiUp: self.skipTest("GUI required")
        from PySide import QtCore
        import CommandCreateContact
        panel = CommandCreateContact.TaskAssemblyCreateContact(self.contact, Dynamics.input_owner(self.contact))
        self.assertFalse(panel.groupWidget.isHidden())
        self.assertFalse(panel.exclusionWidget.isHidden())
        self.assertIn("4", panel.pairCount.text())
        panel.members.topLevelItem(0).setCheckState(2, QtCore.Qt.Checked)
        self.assertIn(self.a, self.contact.ComponentsJ)
        panel.excludeI.setCurrentIndex(panel.excludeI.findData(self.a.Name))
        panel.excludeJ.setCurrentIndex(panel.excludeJ.findData(self.c.Name))
        panel.addExclusion()
        self.assertEqual(len(Dynamics.contact_exclusions(self.contact)), 1)
        panel.exclusions.setChecked(False)
        self.assertEqual(len(Dynamics.contact_exclusions(self.contact)), 1)
        panel.form.deleteLater()

    def test_switch_to_pair_mode_initializes_displayed_components(self):
        if not App.GuiUp:
            self.skipTest("GUI required")
        import CommandCreateContact

        panel = CommandCreateContact.TaskAssemblyCreateContact(
            self.contact, Dynamics.input_owner(self.contact)
        )
        try:
            self.assertIsNone(self.contact.ComponentI)
            self.assertIsNone(self.contact.ComponentJ)
            panel.form.ModeComboBox.setCurrentIndex(0)
            self.assertEqual(Dynamics.contact_pairs(self.contact), [(self.a, self.b)])
            self.assertEqual(panel.form.FirstComponentComboBox.currentData(), self.a.Name)
            self.assertEqual(panel.form.SecondComponentComboBox.currentData(), self.b.Name)
            panel.form.SecondComponentComboBox.setCurrentIndex(2)
            selected = (self.contact.ComponentI, self.contact.ComponentJ)
            panel.form.ModeComboBox.setCurrentIndex(2)
            panel.form.ModeComboBox.setCurrentIndex(0)
            self.assertEqual(Dynamics.contact_pairs(self.contact), [selected])
            self.assertEqual(self.contact.ComponentsI, [self.a, self.b])
            self.assertEqual(self.contact.ComponentsJ, [self.c, self.d])
        finally:
            panel.form.deleteLater()

    def test_pair_mode_hides_exclusions_and_friction_is_a_group(self):
        if not App.GuiUp: self.skipTest("GUI required")
        import CommandCreateContact
        self.contact.Mode = "Between two components"
        self.contact.ComponentI, self.contact.ComponentJ = self.a, self.b
        Dynamics.set_contact_exclusions(self.contact, [(self.a, self.b)])
        self.assertEqual(Dynamics.contact_pairs(self.contact), [(self.a, self.b)])
        _, data = self.native()
        self.assertEqual(len(data["Loads"]), 1)
        panel = CommandCreateContact.TaskAssemblyCreateContact(self.contact, Dynamics.input_owner(self.contact))
        try:
            component_widgets = (
                panel.form.FirstComponentLabel,
                panel.form.FirstComponentComboBox,
                panel.form.SecondComponentLabel,
                panel.form.SecondComponentComboBox,
            )
            self.assertTrue(all(not widget.isHidden() for widget in component_widgets))
            self.assertTrue(panel.exclusionWidget.isHidden())
            self.assertTrue(panel.groupWidget.isHidden())
            self.assertTrue(panel.form.FrictionGroupBox.isCheckable())
            self.assertFalse(panel.form.StaticFrictionSpinBox.isEnabled())
            panel.form.FrictionGroupBox.setChecked(True)
            self.assertTrue(self.contact.FrictionEnabled)
            self.assertTrue(panel.form.StaticFrictionSpinBox.isEnabled())
            panel.form.ModeComboBox.setCurrentIndex(1)
            self.assertTrue(all(widget.isHidden() for widget in component_widgets))
            self.assertFalse(panel.exclusionWidget.isHidden())
            self.assertNotIn((self.a, self.b), Dynamics.contact_pairs(self.contact))
            panel.form.ModeComboBox.setCurrentIndex(0)
            self.assertTrue(all(not widget.isHidden() for widget in component_widgets))
        finally:
            panel.form.deleteLater()

    def test_native_double_click_before_and_after_reopen(self):
        if not App.GuiUp: self.skipTest("GUI required")
        import FreeCADGui as Gui
        from PySide import QtWidgets
        contact = self.contact
        name = contact.Name
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "ContactEdit.FCStd")
            for restored, missing_provider in ((False, False), (True, False), (True, True)):
                with self.subTest(restored=restored, missing_provider=missing_provider):
                    if restored:
                        if missing_provider:
                            contact.ViewObject.Proxy = None
                        self.fixture.doc.saveAs(filename)
                        App.closeDocument(self.fixture.doc.Name)
                        self.fixture.doc = App.openDocument(filename)
                        contact = self.fixture.doc.getObject(name)
                    self.assertTrue(contact.ViewObject.doubleClicked())
                    QtWidgets.QApplication.processEvents()
                    try:
                        self.assertTrue(Gui.Control.activeDialog())
                        task = Gui.Control.activeTaskDialog().getDialogContent()[0]
                        form = task.findChild(QtWidgets.QWidget, "TaskAssemblyCreateContact")
                        self.assertIsNotNone(form)
                    finally:
                        if Gui.Control.activeDialog():
                            Gui.Control.activeTaskDialog().reject()
                        QtWidgets.QApplication.processEvents()
