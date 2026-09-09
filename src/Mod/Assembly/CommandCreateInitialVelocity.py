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

"""Create and edit simulation-owned initial component velocities."""

import math

import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin
from PySide import QtCore, QtGui, QtWidgets
from PySide.QtCore import QT_TRANSLATE_NOOP

import CommandCreateSimulation
import Dynamics
import UtilsAssembly

translate = App.Qt.translate


def _available_types(simulation, component, excluding=None):
    children = (
        Dynamics.inputs_for_study(simulation)
        if Dynamics.is_study(simulation)
        else getattr(simulation, "Group", [])
    )
    occupied = {
        child.InitialVelocityType
        for child in children
        if child != excluding
        and not getattr(child, "Suppressed", False)
        and hasattr(child, "InitialVelocityType")
        and child.Component == component
    }
    current_type = (
        excluding.InitialVelocityType
        if excluding is not None and excluding.Component == component
        else None
    )
    return [kind for kind in Dynamics.InitialVelocity.TYPES if kind not in occupied or kind == current_type]


def _eligible_components(simulation, excluding=None):
    assembly = Dynamics.assembly_for_owner(simulation)
    return [
        component
        for component in assembly.getComponents()
        if (component == getattr(excluding, "Component", None) or not assembly.isPartGrounded(component))
        and _available_types(simulation, component, excluding)
    ]


def _show_task(initial, owner, resume_simulation=None):
    panel = TaskAssemblyCreateInitialVelocity(initial, owner, resume_simulation)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(initial.Document.Name)


class CommandCreateInitialVelocity:
    def GetResources(self):
        return {
            "Pixmap": "button_right",
            "MenuText": QT_TRANSLATE_NOOP("Assembly", "Add Initial Velocity"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly", "Creates an initial velocity. While editing a simulation it is "
                "local to that simulation; otherwise it is global and used by every simulation."
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        task = CommandCreateSimulation.activeSimulationTask()
        if task is None and not UtilsAssembly.isAssemblyCommandActive():
            return False
        assembly = task.assembly if task else UtilsAssembly.activeAssembly()
        global_owner = next(
            (obj for obj in assembly.Group if obj.TypeId == "Assembly::SimulationGroup"),
            assembly,
        )
        owner = task.simFeaturePy if task else global_owner
        return bool((not Gui.Control.activeDialog() or task) and _eligible_components(owner))

    def Activated(self):
        task = CommandCreateSimulation.activeSimulationTask()
        simulation = task.simFeaturePy if task else None
        owner = simulation or UtilsAssembly.getSimulationGroup(UtilsAssembly.activeAssembly())
        components = _eligible_components(owner)
        if not components:
            return
        selected = [obj for obj in Gui.Selection.getSelection() if obj in components]
        component = selected[0] if selected else components[0]
        velocity_type = _available_types(owner, component)[0]
        resume = task.suspendForChildTask() if task else None
        Gui.ActiveDocument.openCommand("Add Initial Velocity")
        initial = Dynamics.create_initial_velocity(
            owner, velocity_type, component
        )
        ViewProviderInitialVelocity(initial.ViewObject)
        _show_task(initial, Dynamics.input_owner(initial), resume)


def editInitialVelocity(initial):
    owner = Dynamics.input_owner(initial)
    assembly = Dynamics.assembly_for_owner(owner)
    if owner is None or assembly is None:
        return False
    simulation_task = CommandCreateSimulation.activeSimulationTask()
    if simulation_task is not None:
        resume = simulation_task.suspendForChildTask()
    else:
        resume = None
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()
    if CommandCreateSimulation.UtilsAssembly.activeAssembly() != assembly:
        Gui.ActiveDocument.setEdit(assembly)
    if initial.Document.getBookedTransactionID() == 0:
        Gui.ActiveDocument.openCommand("Edit " + initial.Label)
    _show_task(initial, owner, resume)
    return True


class ViewProviderInitialVelocity:
    def __init__(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        if not hasattr(view_object, "GlyphSize"):
            view_object.addProperty(
                "App::PropertyLength",
                "GlyphSize",
                "Initial Velocity",
                QT_TRANSLATE_NOOP("App::Property", "Length of the velocity glyph."),
            )
            view_object.GlyphSize = 20
        view_object.Proxy = self
        self.updateLabel(view_object.Object)

    def attach(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        self.object = view_object.Object
        self.root = coin.SoSeparator()
        color = coin.SoBaseColor()
        color.rgb = (0.15, 0.45, 0.95)
        style = coin.SoDrawStyle()
        style.lineWidth = 3
        self.root.addChild(color)
        self.root.addChild(style)
        self.visualSwitch = coin.SoSwitch()

        linear = coin.SoSeparator()
        self.linearTransform = coin.SoTransform()
        self.linearScale = coin.SoScale()
        coordinates = coin.SoCoordinate3()
        coordinates.point.setValues(
            0,
            6,
            [
                (0, 0, 0),
                (0, 0, 0.72),
                (-0.16, -0.16, 0.72),
                (0.16, -0.16, 0.72),
                (0.16, 0.16, 0.72),
                (-0.16, 0.16, 0.72),
            ],
        )
        shaft = coin.SoLineSet()
        shaft.numVertices = 2
        tip = coin.SoCoordinate3()
        tip.point.setValues(
            0,
            5,
            [
                (-0.16, -0.16, 0.72),
                (0.16, -0.16, 0.72),
                (0.16, 0.16, 0.72),
                (-0.16, 0.16, 0.72),
                (0, 0, 1),
            ],
        )
        faces = coin.SoIndexedFaceSet()
        faces.coordIndex.setValues(
            0,
            20,
            [0, 1, 4, -1, 1, 2, 4, -1, 2, 3, 4, -1, 3, 0, 4, -1, 3, 2, 1, 0],
        )
        for node in (self.linearTransform, self.linearScale, coordinates, shaft, tip, faces):
            linear.addChild(node)
        self.visualSwitch.addChild(linear)

        angular = coin.SoSeparator()
        self.angularTransform = coin.SoTransform()
        self.angularScale = coin.SoScale()
        self.angularArcCoordinates = coin.SoCoordinate3()
        self.angularArc = coin.SoLineSet()
        self.angularHeadTransform = coin.SoTransform()
        head = coin.SoCone()
        head.bottomRadius = 0.11
        head.height = 0.25
        for node in (
            self.angularTransform,
            self.angularScale,
            self.angularArcCoordinates,
            self.angularArc,
            self.angularHeadTransform,
            head,
        ):
            angular.addChild(node)
        axis = coin.SoSeparator()
        axis_style = coin.SoDrawStyle()
        axis_style.lineWidth = 2
        axis_style.linePattern = 0x0F0F
        axis_coordinates = coin.SoCoordinate3()
        axis_coordinates.point.setValues(0, 2, [(0, 0, -0.75), (0, 0, 0.75)])
        axis_line = coin.SoLineSet()
        axis_line.numVertices = 2
        for node in (axis_style, axis_coordinates, axis_line):
            axis.addChild(node)
        angular.addChild(axis)
        self.visualSwitch.addChild(angular)

        self.root.addChild(self.visualSwitch)
        view_object.addDisplayMode(self.root, "Initial Velocity")
        self.updateVisual(view_object.Object)

    def center(self, obj):
        if not obj.Component:
            return App.Vector()
        placement = Dynamics.component_placement(obj.Component)
        try:
            local = obj.Component.Document.getObject(obj.Component.Name)
            mass = Dynamics.assembly_for_owner(Dynamics.input_owner(obj)).getMassProperties(local)
            return placement.multVec(App.Vector(*mass["CenterOfMass"]))
        except (RuntimeError, ValueError):
            return placement.Base

    def updateData(self, obj, prop):
        if prop in (
            "InitialVelocityType",
            "Component",
            "Direction",
            "LinearVelocity",
            "AngularVelocity",
        ):
            self.updateLabel(obj)
            self.updateVisual(obj)

    def updateVisual(self, obj):
        if not hasattr(self, "visualSwitch"):
            return
        point = self.center(obj)
        direction = App.Vector(obj.Direction)
        if direction.Length < 1e-12:
            direction = App.Vector(1, 0, 0)
        size = max(float(obj.ViewObject.GlyphSize), 1.0)
        if obj.InitialVelocityType == "Linear":
            self.visualSwitch.whichChild = 0
            signed_direction = direction
            if obj.LinearVelocity.Value < 0:
                signed_direction = -signed_direction
            self.linearTransform.translation.setValue(tuple(point))
            self.linearTransform.rotation.setValue(
                App.Rotation(App.Vector(0, 0, 1), signed_direction).Q
            )
            self.linearScale.scaleFactor = (size, size, size)
            return

        self.visualSwitch.whichChild = 1
        self.angularTransform.translation.setValue(tuple(point))
        self.angularTransform.rotation.setValue(
            App.Rotation(App.Vector(0, 0, 1), direction).Q
        )
        self.angularScale.scaleFactor = (size, size, size)
        positive = obj.AngularVelocity.Value >= 0
        start = math.radians(30 if positive else 330)
        sweep = math.radians(300 if positive else -300)
        radius = 0.5
        segments = 32
        points = [
            (
                radius * math.cos(start + sweep * index / segments),
                radius * math.sin(start + sweep * index / segments),
                0,
            )
            for index in range(segments + 1)
        ]
        self.angularArcCoordinates.point.setValues(0, len(points), points)
        self.angularArc.numVertices = len(points)
        end = start + sweep
        sign = 1 if positive else -1
        arrow_tip = App.Vector(radius * math.cos(end), radius * math.sin(end), 0)
        tangent = App.Vector(-math.sin(end) * sign, math.cos(end) * sign, 0)
        self.angularHeadTransform.translation.setValue(tuple(arrow_tip - tangent * 0.125))
        self.angularHeadTransform.rotation.setValue(
            App.Rotation(App.Vector(0, 1, 0), tangent).Q
        )

    def updateLabel(self, obj=None):
        obj = obj or self.object
        if not obj.Component:
            return
        kind = translate("Assembly", obj.InitialVelocityType.lower())
        obj.Label = translate("Assembly", "{component} ({kind} velocity)").format(
            component=obj.Component.Label, kind=kind
        )

    def onChanged(self, view_object, prop):
        if prop == "GlyphSize":
            self.updateVisual(view_object.Object)

    def getDisplayModes(self, _view_object):
        return ["Initial Velocity"]

    def getDefaultDisplayMode(self):
        return "Initial Velocity"

    def getIcon(self):
        return (
            ":/icons/button_rotate.svg"
            if self.object.InitialVelocityType == "Angular"
            else ":/icons/button_right.svg"
        )

    def doubleClicked(self, view_object):
        initial = view_object.Object
        QtCore.QTimer.singleShot(0, lambda: editInitialVelocity(initial))
        return True

    def dumps(self):
        return None

    def loads(self, _state):
        return None


class TaskAssemblyCreateInitialVelocity:
    def __init__(self, initial, simulation, resume_simulation=None):
        self.initial = initial
        self.owner = simulation
        self.simulation = simulation if Dynamics.is_study(simulation) else None
        self.resume_simulation = resume_simulation
        self._updating = False
        self.form = Gui.PySideUic.loadUi(
            ":/panels/TaskAssemblyCreateInitialVelocity.ui"
        )
        self.form.setWindowIcon(Gui.getIcon("button_right"))
        self.form.DirectionEdit.setProperty("label", translate("Assembly", "Direction"))
        self.components = _eligible_components(simulation, initial)
        for component in self.components:
            self.form.ComponentComboBox.addItem(component.Label, component)
        index = self.components.index(initial.Component) if initial.Component in self.components else 0
        self.form.ComponentComboBox.setCurrentIndex(index)
        self.rebuildTypes(initial.InitialVelocityType)
        direction = initial.Direction
        for axis, value in zip(("vectorX", "vectorY", "vectorZ"), direction):
            self.form.DirectionEdit.setProperty(axis, value)
        self.updateVelocityUi()
        self.form.ComponentComboBox.currentIndexChanged.connect(self.onComponentChanged)
        self.form.TypeComboBox.currentIndexChanged.connect(self.onTypeChanged)
        self.form.VelocitySpinBox.valueChanged.connect(self.onVelocityChanged)
        self.form.DirectionEdit.vectorChanged.connect(self.onDirectionChanged)
        Dynamics.purge_touched(simulation, initial)

    def currentComponent(self):
        return self.form.ComponentComboBox.currentData()

    def rebuildTypes(self, preferred=None):
        kinds = _available_types(self.owner, self.currentComponent(), self.initial)
        self.form.TypeComboBox.blockSignals(True)
        self.form.TypeComboBox.clear()
        for kind in kinds:
            self.form.TypeComboBox.addItem(translate("Assembly", kind), kind)
        index = self.form.TypeComboBox.findData(preferred)
        self.form.TypeComboBox.setCurrentIndex(max(index, 0))
        self.form.TypeComboBox.blockSignals(False)

    def updateVelocityUi(self):
        self._updating = True
        angular = self.initial.InitialVelocityType == "Angular"
        self.form.VelocityLabel.setText(
            translate("Assembly", "Angular velocity" if angular else "Velocity")
        )
        value = self.initial.AngularVelocity if angular else self.initial.LinearVelocity
        self.form.VelocitySpinBox.setProperty("value", value)
        QtCore.QTimer.singleShot(0, self.finishUpdate)

    def finishUpdate(self):
        self._updating = False

    def onComponentChanged(self, _index):
        component = self.currentComponent()
        if component:
            self.initial.Component = component
            self.rebuildTypes(self.initial.InitialVelocityType)
            self.onTypeChanged(self.form.TypeComboBox.currentIndex())

    def onTypeChanged(self, _index):
        velocity_type = self.form.TypeComboBox.currentData()
        if not velocity_type:
            return
        self.initial.InitialVelocityType = velocity_type
        self.initial.ViewObject.Proxy.updateLabel(self.initial)
        self.updateVelocityUi()
        self.invalidateResult()

    def onVelocityChanged(self, _value):
        if self._updating:
            return
        value = self.form.VelocitySpinBox.property("value")
        if self.initial.InitialVelocityType == "Angular":
            self.initial.AngularVelocity = value
        else:
            self.initial.LinearVelocity = value
        self.initial.ViewObject.Proxy.updateVisual(self.initial)
        self.invalidateResult()

    def onDirectionChanged(self):
        self.initial.Direction = App.Vector(
            *(self.form.DirectionEdit.property(axis) for axis in ("vectorX", "vectorY", "vectorZ"))
        )
        self.initial.ViewObject.Proxy.updateVisual(self.initial)
        self.invalidateResult()

    def invalidateResult(self):
        Dynamics.invalidate_results(self.initial)

    def accept(self):
        if self.initial.Direction.Length < 1e-12:
            QtWidgets.QMessageBox.warning(
                self.form,
                translate("Assembly", "Invalid initial velocity"),
                translate("Assembly", "Direction must be a nonzero vector."),
            )
            return False
        Dynamics.purge_touched(self.owner, self.initial)
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
                    self.resume_simulation, "initialTab"
                ),
            )


Gui.addCommand("Assembly_CreateInitialVelocity", CommandCreateInitialVelocity())
