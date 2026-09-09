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

"""Create and edit global or simulation-local joint friction inputs."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide.QtCore import QT_TRANSLATE_NOOP

import CommandCreateSimulation
import Dynamics
import UtilsAssembly

translate = App.Qt.translate


def _eligible_joints(assembly):
    return UtilsAssembly.getJointsOfType(assembly, ["Revolute", "Slider"])


def _show_task(friction, owner, resume_simulation=None):
    panel = TaskAssemblyCreateFriction(friction, owner, resume_simulation)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(friction.Document.Name)


def editFriction(friction):
    owner = Dynamics.input_owner(friction)
    assembly = Dynamics.assembly_for_owner(owner)
    if not owner or not assembly:
        return False
    task = CommandCreateSimulation.activeSimulationTask()
    resume = task.suspendForChildTask() if task else None
    if not task and Gui.Control.activeTaskDialog():
        Gui.Control.activeTaskDialog().reject()
    if UtilsAssembly.activeAssembly() != assembly:
        Gui.ActiveDocument.setEdit(assembly)
    if friction.Document.getBookedTransactionID() == 0:
        Gui.ActiveDocument.openCommand("Edit " + friction.Label)
    _show_task(friction, owner, resume)
    return True


class CommandCreateFriction:
    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateFriction",
            "MenuText": QT_TRANSLATE_NOOP("Assembly", "Add Joint Friction"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly",
                "Creates joint friction. While editing a simulation it is local to that "
                "simulation; otherwise it is global and used by every simulation.",
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        task = CommandCreateSimulation.activeSimulationTask()
        if task is None and not UtilsAssembly.isAssemblyCommandActive():
            return False
        assembly = task.assembly if task else UtilsAssembly.activeAssembly()
        return bool(
            assembly and _eligible_joints(assembly)
            and (not Gui.Control.activeDialog() or task is not None)
        )

    def Activated(self):
        assembly = UtilsAssembly.activeAssembly()
        joints = _eligible_joints(assembly) if assembly else []
        if not joints:
            return
        selected = [obj for obj in Gui.Selection.getSelection() if obj in joints]
        task = CommandCreateSimulation.activeSimulationTask()
        resume = task.suspendForChildTask() if task else None
        owner = resume or assembly
        Gui.ActiveDocument.openCommand("Add Joint Friction")
        friction = Dynamics.create_friction(owner, selected[0] if selected else joints[0])
        ViewProviderFriction(friction.ViewObject)
        _show_task(friction, Dynamics.input_owner(friction), resume)


class ViewProviderFriction:
    def __init__(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        view_object.Proxy = self
        self.updateLabel(view_object.Object)

    def getIcon(self):
        return ":/icons/Assembly_CreateFriction.svg"

    def updateLabel(self, obj):
        if obj.Joint:
            obj.Label = translate("Assembly", "{joint} (friction)").format(joint=obj.Joint.Label)

    def doubleClicked(self, view_object):
        QtCore.QTimer.singleShot(0, lambda: editFriction(view_object.Object))
        return True

    def dumps(self):
        return None

    def loads(self, _state):
        return None


class TaskAssemblyCreateFriction:
    def __init__(self, friction, owner, resume_simulation=None):
        self.friction = friction
        self.owner = owner
        self.resume_simulation = resume_simulation
        self.assembly = Dynamics.assembly_for_owner(owner)
        self._updating = True
        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateFriction.ui")
        self.form.setWindowIcon(Gui.getIcon("Assembly_CreateFriction"))
        self.joints = _eligible_joints(self.assembly)
        for joint in self.joints:
            self.form.JointComboBox.addItem(joint.Label, joint)
        self.form.JointComboBox.setCurrentIndex(
            self.joints.index(friction.Joint) if friction.Joint in self.joints else 0
        )
        self.rebuildModels()
        fields = {
            "StaticSpinBox": "StaticTorque" if self.rotational() else "StaticForce",
            "DynamicSpinBox": "DynamicTorque" if self.rotational() else "DynamicForce",
            "TransitionSpinBox": "AngularTransitionVelocity" if self.rotational() else "LinearTransitionVelocity",
            "ViscousSpinBox": "AngularViscousDamping" if self.rotational() else "LinearViscousDamping",
            "RadiusSpinBox": "EffectiveRadius",
        }
        for widget, prop in fields.items():
            getattr(self.form, widget).setProperty("value", getattr(friction, prop))
        self.form.StaticCoefficientSpinBox.setValue(friction.StaticCoefficient)
        self.form.DynamicCoefficientSpinBox.setValue(friction.DynamicCoefficient)
        self.form.JointComboBox.currentIndexChanged.connect(self.onJointChanged)
        self.form.ModelComboBox.currentIndexChanged.connect(self.onModelChanged)
        for widget in fields:
            getattr(self.form, widget).valueChanged.connect(self.onValuesChanged)
        self.form.StaticCoefficientSpinBox.valueChanged.connect(self.onValuesChanged)
        self.form.DynamicCoefficientSpinBox.valueChanged.connect(self.onValuesChanged)
        self._updating = False
        self.updateUi()
        Dynamics.purge_touched(owner, friction)

    def rotational(self):
        joint = self.form.JointComboBox.currentData()
        return bool(joint and joint.JointType == "Revolute")

    def rebuildModels(self):
        combo = self.form.ModelComboBox
        preferred = self.friction.FrictionModel
        combo.blockSignals(True)
        combo.clear()
        for model in Dynamics.Friction.MODELS:
            if self.rotational() or model not in ("Rolling resistance", "Thrust bearing"):
                combo.addItem(translate("Assembly", model), model)
        combo.setCurrentIndex(max(0, combo.findData(preferred)))
        combo.blockSignals(False)
        if preferred != combo.currentData():
            self.friction.FrictionModel = combo.currentData()

    def onJointChanged(self, _index):
        self._updating = True
        self.friction.Joint = self.form.JointComboBox.currentData()
        self.rebuildModels()
        self.friction.ViewObject.Proxy.updateLabel(self.friction)
        rotational = self.rotational()
        self.form.StaticSpinBox.setProperty(
            "value", getattr(self.friction, "StaticTorque" if rotational else "StaticForce")
        )
        self.form.DynamicSpinBox.setProperty(
            "value", getattr(self.friction, "DynamicTorque" if rotational else "DynamicForce")
        )
        self.form.TransitionSpinBox.setProperty(
            "value", getattr(self.friction, "AngularTransitionVelocity" if rotational else "LinearTransitionVelocity")
        )
        self.form.ViscousSpinBox.setProperty(
            "value", getattr(self.friction, "AngularViscousDamping" if rotational else "LinearViscousDamping")
        )
        self._updating = False
        self.updateUi()
        Dynamics.invalidate_results(self.friction)

    def onModelChanged(self, _index):
        self.friction.FrictionModel = self.form.ModelComboBox.currentData()
        self.updateUi()
        self.onValuesChanged()

    def updateUi(self):
        reaction = self.form.ModelComboBox.currentData() != "Specified resistance"
        rotational = self.rotational()
        self.form.SpecifiedGroup.setVisible(not reaction)
        self.form.ReactionGroup.setVisible(reaction)
        self.form.RadiusRow.setVisible(reaction and rotational)
        self.form.StaticCoefficientSpinBox.setToolTip(translate("Assembly", "Low-speed coefficient multiplied by the selected radial or axial joint load. It must be at least the dynamic coefficient."))
        self.form.DynamicCoefficientSpinBox.setToolTip(translate("Assembly", "Moving friction coefficient multiplied by the selected radial or axial joint load."))
        self.form.RadiusSpinBox.setToolTip(translate("Assembly", "Effective bearing radius: torque = coefficient × selected joint load × radius. For rolling resistance, use the radius corresponding to the measured or manufacturer coefficient."))
        self.form.ModelComboBox.setToolTip(translate("Assembly", "Reaction based and rolling resistance use radial joint load; thrust bearings use axial joint load. Bearing torque is coefficient × load × effective radius, opposing rotation. Rolling resistance is an effective bearing model, not a simulation of individual rolling elements. Use bearing test data or manufacturer coefficients."))
        self.form.StaticLabel.setText(translate("Assembly", "Static torque" if rotational else "Static force"))
        self.form.DynamicLabel.setText(translate("Assembly", "Dynamic torque" if rotational else "Dynamic force"))
        self.form.TransitionLabel.setText(translate("Assembly", "Angular transition velocity" if rotational else "Transition velocity"))

    def onValuesChanged(self, *_args):
        if self._updating:
            return
        rotational = self.rotational()
        setattr(self.friction, "StaticTorque" if rotational else "StaticForce", self.form.StaticSpinBox.property("value"))
        setattr(self.friction, "DynamicTorque" if rotational else "DynamicForce", self.form.DynamicSpinBox.property("value"))
        setattr(self.friction, "AngularTransitionVelocity" if rotational else "LinearTransitionVelocity", self.form.TransitionSpinBox.property("value"))
        setattr(self.friction, "AngularViscousDamping" if rotational else "LinearViscousDamping", self.form.ViscousSpinBox.property("value"))
        self.friction.StaticCoefficient = self.form.StaticCoefficientSpinBox.value()
        self.friction.DynamicCoefficient = self.form.DynamicCoefficientSpinBox.value()
        self.friction.EffectiveRadius = self.form.RadiusSpinBox.property("value")
        Dynamics.invalidate_results(self.friction)

    def accept(self):
        reaction = self.friction.FrictionModel != "Specified resistance"
        rotational = self.rotational()
        if not rotational and self.friction.FrictionModel in ("Rolling resistance", "Thrust bearing"):
            QtWidgets.QMessageBox.warning(self.form, translate("Assembly", "Invalid friction"),
                translate("Assembly", "Rolling and thrust bearing friction require a revolute joint."))
            return False
        static_value = (
            self.friction.StaticCoefficient
            if reaction else getattr(self.friction, "StaticTorque" if rotational else "StaticForce").Value
        )
        dynamic_value = (
            self.friction.DynamicCoefficient
            if reaction else getattr(self.friction, "DynamicTorque" if rotational else "DynamicForce").Value
        )
        transition = getattr(
            self.friction,
            "AngularTransitionVelocity" if rotational else "LinearTransitionVelocity",
        ).Value
        if static_value < dynamic_value or dynamic_value < 0 or transition <= 0:
            QtWidgets.QMessageBox.warning(
                self.form,
                translate("Assembly", "Invalid friction"),
                translate("Assembly", "Static resistance must be at least the dynamic resistance, and the transition velocity must be positive."),
            )
            return False
        Dynamics.purge_touched(self.owner, self.friction)
        Gui.ActiveDocument.commitCommand()
        self.reopenSimulation()
        return True

    def reject(self):
        Gui.ActiveDocument.abortCommand()
        self.reopenSimulation()
        return True

    def reopenSimulation(self):
        if self.resume_simulation:
            QtCore.QTimer.singleShot(
                0,
                lambda: CommandCreateSimulation.TaskAssemblyCreateSimulation.reopen(
                    self.resume_simulation, "frictionTab"
                ),
            )


Gui.addCommand("Assembly_CreateFriction", CommandCreateFriction())
