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

"""Initial-velocity command, task panel, and simulation-tab regressions."""

import unittest
from unittest.mock import patch

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import CommandCreateInitialVelocity as InitialCommand
    import CommandCreateSimulation as SimulationCommand
    import JointObject
    from PySide import QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires a GUI-enabled FreeCAD runtime")
class TestInitialVelocityUI(unittest.TestCase):
    def setUp(self):
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.doc = App.newDocument("InitialVelocityUiTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.first = self.assembly.newObject("Part::Feature", "First")
        self.second = self.assembly.newObject("Part::Feature", "Second")
        self.first.Shape = Part.makeBox(10, 10, 10)
        self.second.Shape = Part.makeBox(10, 10, 10)
        joints = self.assembly.newObject("Assembly::JointGroup", "Joints")
        grounded = joints.newObject("App::FeaturePython", "Grounded")
        JointObject.GroundedJoint(grounded, self.first)
        self.doc.recompute()
        self.active = patch.object(
            SimulationCommand.UtilsAssembly, "activeAssembly", return_value=self.assembly
        )
        self.active.start()
        self.panel = SimulationCommand.TaskAssemblyCreateSimulation()
        Gui.Control.showDialog(self.panel)
        QtWidgets.QApplication.processEvents()

    def tearDown(self):
        if Gui.Control.activeDialog():
            self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.active.stop()
        App.closeDocument(self.doc.Name)
        self.preferences.SetBool("SolveOnRecompute", self.solve)

    def clickTaskButton(self, button):
        boxes = Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
        candidates = [box for box in boxes if box.button(button)]
        self.assertTrue(candidates)
        candidates[-1].button(button).click()
        QtWidgets.QApplication.processEvents()

    def addInitial(self):
        self.panel.form.AddInitialVelocityButton.click()
        QtWidgets.QApplication.processEvents()
        return next(
            obj
            for obj in self.panel.simFeaturePy.Group
            if hasattr(obj, "InitialVelocityType")
        )

    def test_create_edit_and_remove_initial_velocity(self):
        self.assertTrue(InitialCommand.CommandCreateInitialVelocity().IsActive())
        initial = self.addInitial()
        content = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = content.findChild(
            QtWidgets.QWidget, "TaskAssemblyCreateInitialVelocity"
        )
        self.assertIsNotNone(form)
        self.assertEqual(form.ComponentComboBox.count(), 1)
        self.assertEqual(form.ComponentComboBox.currentData(), self.second)
        self.assertEqual(form.TypeComboBox.currentData(), "Linear")
        self.assertEqual(initial.Component, self.second)
        self.assertTrue(initial.hasExtension("App::SuppressibleExtensionPython"))
        self.assertTrue(
            initial.ViewObject.hasExtension("Gui::ViewProviderSuppressibleExtensionPython")
        )
        self.assertEqual(initial.ViewObject.Proxy.visualSwitch.whichChild.getValue(), 0)
        self.assertNotIn("Touched", initial.State)
        self.assertNotIn("Touched", self.panel.simFeaturePy.State)

        form.TypeComboBox.setCurrentIndex(form.TypeComboBox.findData("Angular"))
        QtWidgets.QApplication.processEvents()
        form.VelocitySpinBox.setProperty("value", App.Units.Quantity("2 rad/s"))
        form.DirectionEdit.setProperty("vectorX", 0.0)
        form.DirectionEdit.setProperty("vectorZ", 1.0)
        QtWidgets.QApplication.processEvents()
        self.assertEqual(initial.InitialVelocityType, "Angular")
        self.assertAlmostEqual(initial.AngularVelocity.getValueAs("rad/s"), 2, places=4)
        self.assertEqual(initial.Direction, App.Vector(0, 0, 1))
        self.assertEqual(initial.ViewObject.Proxy.visualSwitch.whichChild.getValue(), 1)

        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertEqual(self.panel.form.tabWidget.currentWidget().objectName(), "initialTab")
        self.assertEqual(self.panel.form.initialVelocityList.count(), 1)

        self.assertTrue(initial.ViewObject.Proxy.doubleClicked(initial.ViewObject))
        QtWidgets.QApplication.processEvents()
        content = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = content.findChild(
            QtWidgets.QWidget, "TaskAssemblyCreateInitialVelocity"
        )
        self.assertIsNotNone(form)
        form.VelocitySpinBox.setProperty("value", App.Units.Quantity("3 rad/s"))
        QtWidgets.QApplication.processEvents()
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Cancel)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertAlmostEqual(initial.AngularVelocity.getValueAs("rad/s"), 2, places=4)

        name = initial.Name
        self.panel.form.initialVelocityList.setCurrentRow(0)
        self.panel.form.RemoveInitialVelocityButton.click()
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual(self.panel.form.initialVelocityList.count(), 0)

    def test_one_linear_and_one_angular_velocity_per_component(self):
        first = self.addInitial()
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        second = self.addInitial()
        content = Gui.Control.activeTaskDialog().getDialogContent()[0]
        form = content.findChild(
            QtWidgets.QWidget, "TaskAssemblyCreateInitialVelocity"
        )
        self.assertIsNotNone(form)
        self.assertEqual(form.TypeComboBox.count(), 1)
        self.assertEqual(form.TypeComboBox.currentData(), "Angular")
        self.assertEqual(first.Component, second.Component)
        self.clickTaskButton(QtWidgets.QDialogButtonBox.Ok)
        self.panel = SimulationCommand.activeSimulationTask()
        self.assertFalse(InitialCommand.CommandCreateInitialVelocity().IsActive())
        self.assertFalse(self.panel.form.AddInitialVelocityButton.isEnabled())
