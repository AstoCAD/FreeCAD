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

"""Create and edit force/torque loads owned by an Assembly simulation."""

import math

import FreeCAD as App
import FreeCADGui as Gui
import PartGui
from pivy import coin
from PySide import QtCore, QtWidgets
from PySide.QtCore import QT_TRANSLATE_NOOP

import CommandCreateSimulation
import Dynamics
import UtilsAssembly

translate = App.Qt.translate


def validateBushingMatrix(values):
    """Match the solver's diagonally scaled semidefinite check (tolerance 1e-10)."""
    if len(values) != 36 or not all(math.isfinite(value) for value in values):
        raise ValueError(translate("Assembly", "Enter 36 finite numbers."))
    if any(values[6*i+i] < 0 for i in range(6)):
        raise ValueError(translate("Assembly", "Diagonal entries must be nonnegative."))
    scaled = [[0.0] * 6 for _ in range(6)]
    for i in range(6):
        for j in range(6):
            value = values[6*i+j]
            if value != values[6*j+i]:
                raise ValueError(translate("Assembly", "The matrix must be symmetric."))
            scale = math.sqrt(values[6*i+i]) * math.sqrt(values[6*j+j])
            if scale:
                scaled[i][j] = value / scale
            elif value:
                raise ValueError(translate("Assembly", "A zero diagonal requires a zero row and column."))
    for i in range(6):
        if scaled[i][i] < -1e-10 or (
            scaled[i][i] <= 1e-10
            and any(abs(scaled[j][i]) > 1e-10 for j in range(i+1, 6))
        ):
            raise ValueError(translate("Assembly", "The matrix must be positive semidefinite. Reduce coupling or increase the corresponding diagonal entries."))
        if scaled[i][i] > 1e-10:
            for j in range(i+1, 6):
                for k in range(j, 6):
                    scaled[k][j] -= scaled[j][i] * scaled[k][i] / scaled[i][i]
                    scaled[j][k] = scaled[k][j]


def _showLoadTask(load, owner, resume_simulation=None, new_load=False):
    panel = TaskAssemblyCreateLoad(load, owner, resume_simulation, new_load=new_load)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(load.Document.Name)


def editLoad(load):
    owner = Dynamics.input_owner(load)
    assembly = Dynamics.assembly_for_owner(owner)
    if owner is None or assembly is None:
        return False

    simulation_task = CommandCreateSimulation.activeSimulationTask()
    if simulation_task is not None:
        resume_simulation = simulation_task.suspendForChildTask()
    else:
        resume_simulation = None
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()

    if CommandCreateSimulation.UtilsAssembly.activeAssembly() != assembly:
        Gui.ActiveDocument.setEdit(assembly)
    if load.Document.getBookedTransactionID() == 0:
        Gui.ActiveDocument.openCommand("Edit " + load.Label)
    _showLoadTask(load, owner, resume_simulation)
    return True


class CommandCreateLoad:
    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateLoad",
            "MenuText": QT_TRANSLATE_NOOP("Assembly", "Add Load"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly", "Creates a load. While editing a simulation it is local to that "
                "simulation; otherwise it is global and used by every simulation."
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        task = CommandCreateSimulation.activeSimulationTask()
        if task is None and not UtilsAssembly.isAssemblyCommandActive():
            return False
        assembly = task.assembly if task else UtilsAssembly.activeAssembly()
        return bool(assembly and assembly.getComponents() and (not Gui.Control.activeDialog() or task))

    def Activated(self):
        simulation_task = CommandCreateSimulation.activeSimulationTask()
        selected = Gui.Selection.getSelection()
        simulation = simulation_task.suspendForChildTask() if simulation_task else None
        assembly = UtilsAssembly.activeAssembly()
        components = list(assembly.getComponents())
        if not components:
            if simulation:
                CommandCreateSimulation.TaskAssemblyCreateSimulation.reopen(simulation)
            return

        selected_components = [obj for obj in selected if obj in components]
        component = selected_components[0] if selected_components else components[0]
        reaction_component = selected_components[1] if len(selected_components) > 1 else None
        Gui.ActiveDocument.openCommand("Add Load")
        load = Dynamics.create_load(
            simulation or assembly, "Force", component, body_j=reaction_component
        )
        ViewProviderLoad(load.ViewObject)
        _showLoadTask(load, Dynamics.input_owner(load), simulation, new_load=True)


class ViewProviderLoad:
    def __init__(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        view_object.addExtension("PartGui::ViewProviderAttachExtensionPython")
        view_object.setIgnoreOverlayIcon(True, "PartGui::ViewProviderAttachExtensionPython")
        if not hasattr(view_object, "ArrowSize"):
            view_object.addProperty(
                "App::PropertyLength",
                "ArrowSize",
                "Load",
                QT_TRANSLATE_NOOP("App::Property", "Length of the load arrow."),
            )
            view_object.ArrowSize = 20
        # Assigning Proxy invokes attach(), so all view properties used by the
        # scene graph must exist first.
        view_object.Proxy = self

    def attach(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        self.root = coin.SoSeparator()
        color = coin.SoBaseColor()
        color.rgb = (0.9, 0.1, 0.1)
        style = coin.SoDrawStyle()
        style.lineWidth = 3

        self.loadSwitch = coin.SoSwitch()
        arrow = coin.SoSeparator()
        self.transform = coin.SoTransform()
        self.scale = coin.SoScale()
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
        self.root.addChild(color)
        self.root.addChild(style)
        arrow.addChild(self.transform)
        arrow.addChild(self.scale)
        arrow.addChild(coordinates)
        arrow.addChild(shaft)
        arrow.addChild(tip)
        arrow.addChild(faces)
        self.loadSwitch.addChild(arrow)

        torque = coin.SoSeparator()
        self.torqueTransform = coin.SoTransform()
        self.torqueScale = coin.SoScale()
        self.torqueArcCoordinates = coin.SoCoordinate3()
        self.torqueArc = coin.SoLineSet()
        self.torqueHeadTransform = coin.SoTransform()
        torque_head = coin.SoCone()
        torque_head.bottomRadius = 0.11
        torque_head.height = 0.25
        torque.addChild(self.torqueTransform)
        torque.addChild(self.torqueScale)
        torque.addChild(self.torqueArcCoordinates)
        torque.addChild(self.torqueArc)
        torque.addChild(self.torqueHeadTransform)
        torque.addChild(torque_head)

        axis = coin.SoSeparator()
        self.torqueAxisStyle = coin.SoDrawStyle()
        self.torqueAxisStyle.lineWidth = 2
        self.torqueAxisStyle.linePattern = 0x0F0F
        axis_coordinates = coin.SoCoordinate3()
        axis_coordinates.point.setValues(0, 2, [(0, 0, -0.75), (0, 0, 0.75)])
        axis_line = coin.SoLineSet()
        axis_line.numVertices = 2
        axis.addChild(self.torqueAxisStyle)
        axis.addChild(axis_coordinates)
        axis.addChild(axis_line)
        torque.addChild(axis)
        self.loadSwitch.addChild(torque)

        spring = coin.SoSeparator()
        self.springCoordinates = coin.SoCoordinate3()
        self.springLine = coin.SoLineSet()
        spring.addChild(self.springCoordinates)
        spring.addChild(self.springLine)
        self.loadSwitch.addChild(spring)

        bushing = coin.SoSeparator()
        self.bushingTransform = coin.SoTransform()
        self.bushingScale = coin.SoScale()
        bushing.addChild(self.bushingTransform)
        bushing.addChild(self.bushingScale)
        for color_value, endpoint in (
            ((1.0, 0.2, 0.2), (1, 0, 0)),
            ((0.2, 1.0, 0.2), (0, 1, 0)),
            ((0.3, 0.5, 1.0), (0, 0, 1)),
        ):
            axis = coin.SoSeparator()
            axis_color = coin.SoBaseColor()
            axis_color.rgb = color_value
            axis_coordinates = coin.SoCoordinate3()
            axis_coordinates.point.setValues(0, 2, [(0, 0, 0), endpoint])
            axis_line = coin.SoLineSet()
            axis_line.numVertices = 2
            axis.addChild(axis_color)
            axis.addChild(axis_coordinates)
            axis.addChild(axis_line)
            bushing.addChild(axis)
        self.loadSwitch.addChild(bushing)
        self.root.addChild(self.loadSwitch)
        view_object.addDisplayMode(self.root, "Load")
        self.updateVisual(view_object.Object)

    def updateData(self, obj, prop):
        if prop in (
            "Placement",
            "LoadType",
            "BodyI",
            "BodyJ",
            "AttachmentI",
            "AttachmentJ",
            "Direction",
            "Follower",
            "Force",
            "Torque",
            "Formula",
            "ProfileData",
            "TorsionalStiffness",
            "TorsionalDamping",
            "FreeAngle",
        ):
            if hasattr(obj.Proxy, "update_attachment"):
                if prop == "Placement":
                    obj.Proxy.update_attachment(obj)
            self.updateVisual(obj)

    def updateVisual(self, obj):
        if not hasattr(self, "loadSwitch"):
            return
        if obj.LoadType == "SpringDamper":
            self.loadSwitch.whichChild = 2
            self.updateSpring(obj)
            return
        if obj.LoadType == "Bushing":
            self.loadSwitch.whichChild = 3
            placement = Dynamics.attachment_placement(obj, "I")
            self.bushingTransform.translation.setValue(tuple(placement.Base))
            self.bushingTransform.rotation.setValue(placement.Rotation.Q)
            size = max(float(obj.ViewObject.ArrowSize), 1.0) * 0.6
            self.bushingScale.scaleFactor = (size, size, size)
            return
        if obj.LoadType in ("Torque", "TorsionalSpringDamper"):
            self.loadSwitch.whichChild = 1
            self.updateTorque(obj)
            return
        self.loadSwitch.whichChild = 0
        point = Dynamics.attachment_placement(obj, "I").Base
        direction = Dynamics.load_visual_direction(obj)
        magnitude = Dynamics.constant_load_magnitude(obj)
        if magnitude is not None and magnitude < 0:
            direction = -direction
        if direction.Length < 1e-12:
            direction = App.Vector(0, 0, 1)
        self.transform.translation.setValue(tuple(point))
        self.transform.rotation.setValue(
            App.Rotation(App.Vector(0, 0, 1), direction).Q
        )
        size = max(float(obj.ViewObject.ArrowSize), 1.0)
        self.scale.scaleFactor = (size, size, size)

    def updateTorque(self, obj):
        point = Dynamics.attachment_placement(obj, "I").Base
        direction = Dynamics.load_visual_direction(obj)
        if direction.Length < 1e-12:
            direction = App.Vector(0, 0, 1)
        self.torqueTransform.translation.setValue(tuple(point))
        self.torqueTransform.rotation.setValue(
            App.Rotation(App.Vector(0, 0, 1), direction).Q
        )
        size = max(float(obj.ViewObject.ArrowSize), 1.0)
        self.torqueScale.scaleFactor = (size, size, size)

        # A time-varying profile can change sign during a run, so show its
        # positive convention. Constant torque and torsional deflection use
        # the curl direction to show the currently applied sign.
        if obj.LoadType == "TorsionalSpringDamper":
            positive = (
                Dynamics.torsional_angle(obj) - math.radians(obj.FreeAngle.Value)
            ) >= 0
        else:
            magnitude = Dynamics.constant_load_magnitude(obj)
            positive = magnitude is None or magnitude >= 0
        start = math.radians(30 if positive else 330)
        sweep = math.radians(300 if positive else -300)
        segments = 32
        radius = 0.5
        points = []
        for index in range(segments + 1):
            angle = start + sweep * index / segments
            points.append((radius * math.cos(angle), radius * math.sin(angle), 0))
        self.torqueArcCoordinates.point.setValues(0, len(points), points)
        self.torqueArc.numVertices = len(points)

        end = start + sweep
        sign = 1 if positive else -1
        tip = App.Vector(radius * math.cos(end), radius * math.sin(end), 0)
        tangent = App.Vector(-math.sin(end) * sign, math.cos(end) * sign, 0)
        head_height = 0.25
        self.torqueHeadTransform.translation.setValue(
            tuple(tip - tangent * (head_height / 2))
        )
        self.torqueHeadTransform.rotation.setValue(
            App.Rotation(App.Vector(0, 1, 0), tangent).Q
        )

    def updateSpring(self, obj):
        start = Dynamics.attachment_placement(obj, "I").Base
        end = Dynamics.attachment_placement(obj, "J").Base
        span = end - start
        length = span.Length
        if length < 1e-9:
            points = [tuple(start), tuple(end)]
        else:
            axis = span / length
            reference = App.Vector(0, 0, 1)
            if abs(axis.dot(reference)) > 0.9:
                reference = App.Vector(1, 0, 0)
            side = axis.cross(reference)
            side.normalize()
            amplitude = min(max(float(obj.ViewObject.ArrowSize), 1.0) * 0.18, length / 10)
            points = [tuple(start)]
            turns = 12
            for index in range(1, turns):
                center = start + span * (index / turns)
                offset = side * (amplitude if index % 2 else -amplitude)
                points.append(tuple(center + offset))
            points.append(tuple(end))
        self.springCoordinates.point.setValues(0, len(points), points)
        self.springLine.numVertices = len(points)

    def onChanged(self, view_object, prop):
        if prop == "ArrowSize":
            self.updateVisual(view_object.Object)

    def getDisplayModes(self, _view_object):
        return ["Load"]

    def getDefaultDisplayMode(self):
        return "Load"

    def getIcon(self):
        return ":/icons/Assembly_CreateLoad.svg"

    def doubleClicked(self, view_object):
        load = view_object.Object
        QtCore.QTimer.singleShot(0, lambda: editLoad(load))
        return True

    def dumps(self):
        return None

    def loads(self, _state):
        return None


class TaskAssemblyCreateLoad:
    LOAD_TYPES = ("Force", "Torque", "SpringDamper", "TorsionalSpringDamper", "Bushing")

    def __init__(self, load, simulation, resume_simulation=None, new_load=False):
        # Attachment and quantity widgets emit changes while populating their
        # controls. They are not user edits and must not discard saved runs.
        previous = getattr(load.Proxy, "_initializing_editor", False)
        load.Proxy._initializing_editor = True
        try:
            self.initialize(load, simulation, resume_simulation, new_load)
        finally:
            load.Proxy._initializing_editor = previous

    def initialize(self, load, simulation, resume_simulation, new_load):
        self.load = load
        self.owner = simulation
        self.simulation = simulation if Dynamics.is_study(simulation) else None
        self.resume_simulation = resume_simulation
        # Defaults are only for the first selection in a newly created load.
        # Zero is a valid user value, never a marker for an uninitialized input.
        self.initialized_types = {load.LoadType} if new_load else set(self.LOAD_TYPES)
        self._updating_ui = False
        self.automatic_label = load.Label in {
            load.Name,
            translate("Assembly", "Force"),
            translate("Assembly", "Torque"),
            translate("Assembly", "Spring-Damper"),
            translate("Assembly", "Torsional Spring-Damper"),
            translate("Assembly", "Bushing"),
        }
        self.form_load = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateLoad.ui")
        self.form_load.setWindowIcon(Gui.getIcon("Assembly_CreateLoad"))
        # The attachment widget temporarily changes Placement while initializing
        # its controls. Opening an editor must not redefine the reaction frame.
        reaction_frame = App.Placement(load.AttachmentJ)
        try:
            self.attachment = PartGui.createAttachmentTaskBox(load)
        finally:
            if not load.AttachmentJ.isSame(reaction_frame, 1e-12):
                load.AttachmentJ = reaction_frame
        self.form = [self.form_load, self.attachment]

        self.components = list(Dynamics.assembly_for_owner(simulation).getComponents())
        for component in self.components:
            self.form_load.ComponentComboBox.addItem(component.Label, component.Name)
        current = next(
            (index for index, component in enumerate(self.components) if component == load.BodyI),
            0,
        )
        self.form_load.ComponentComboBox.setCurrentIndex(current)
        self.form_load.TypeComboBox.addItems(
            [
                translate("Assembly", "Force"),
                translate("Assembly", "Torque"),
                translate("Assembly", "Linear Spring-Damper"),
                translate("Assembly", "Torsional Spring-Damper"),
                translate("Assembly", "Bushing"),
            ]
        )
        self.form_load.TypeComboBox.setCurrentIndex(self.LOAD_TYPES.index(load.LoadType))
        self.form_load.ReactionComponentComboBox.addItem(
            translate("Assembly", "Ground (assembly)"), None
        )
        self.form_load.BushingReactionComponentComboBox.addItem(
            translate("Assembly", "Ground (assembly)"), None
        )
        for component in self.components:
            self.form_load.ReactionComponentComboBox.addItem(
                component.Label, component.Name
            )
            self.form_load.BushingReactionComponentComboBox.addItem(
                component.Label, component.Name
            )
        reaction_index = next(
            (
                index + 1
                for index, component in enumerate(self.components)
                if component == load.BodyJ
            ),
            0,
        )
        self.form_load.ReactionComponentComboBox.setCurrentIndex(reaction_index)
        self.form_load.BushingReactionComponentComboBox.setCurrentIndex(reaction_index)
        self.form_load.ComponentComboBox.currentIndexChanged.connect(self.onComponentChanged)
        self.form_load.TypeComboBox.currentIndexChanged.connect(self.onTypeChanged)
        self.form_load.MagnitudeSpinBox.valueChanged.connect(self.onMagnitudeChanged)
        self.form_load.FormulaLineEdit.setText(load.Formula)
        self.form_load.MagnitudeSpinBox.setEnabled(not load.Formula.strip())
        self.form_load.FormulaLineEdit.textChanged.connect(self.onFormulaChanged)
        import ProfileEditor
        self.profileField = ProfileEditor.ProfileField(
            load, self.form_load.FormulaLineEdit, self.form_load.WrenchPage,
            self.form_load.MagnitudeSpinBox,
        )
        self.form_load.WrenchLayout.addRow(self.profileField)
        self.form_load.FormulaLabel.hide()
        self.followerCheckBox = QtWidgets.QCheckBox(translate("Assembly", "Follow component rotation"))
        self.followerCheckBox.setObjectName("FollowerCheckBox")
        self.followerCheckBox.setToolTip(translate("Assembly", "Rotate the force or torque direction with the component. Otherwise its direction stays fixed in assembly coordinates. The attachment point always follows the component."))
        self.followerCheckBox.setChecked(load.Follower)
        self.form_load.WrenchPage.layout().addRow(self.followerCheckBox)
        self.followerCheckBox.toggled.connect(lambda checked: setattr(self.load, "Follower", checked))
        self.setupBushingMatrices()
        self.form_load.ReactionComponentComboBox.currentIndexChanged.connect(
            self.onReactionComponentChanged
        )
        self.form_load.BushingReactionComponentComboBox.currentIndexChanged.connect(
            lambda index: self.onReactionComponentChanged(index, True)
        )
        for spinbox in self.endpointSpinboxes():
            spinbox.valueChanged.connect(self.onEndpointChanged)
        self.form_load.StiffnessSpinBox.editingFinished.connect(self.onStiffnessChanged)
        self.form_load.DampingSpinBox.editingFinished.connect(self.onDampingChanged)
        self.form_load.RestLengthSpinBox.editingFinished.connect(self.onRestLengthChanged)
        self.form_load.UseCurrentLengthButton.clicked.connect(self.useCurrentLength)
        self.form_load.UseCurrentPoseButton.clicked.connect(self.useCurrentPose)
        for name, spinbox, _unit in self.bushingSpinboxes():
            axis = name[-1]
            if "LinearStiffness" in name:
                description = translate(
                    "Assembly",
                    "Restoring force per unit displacement along the attachment's local %s axis",
                ) % axis
            elif "LinearDamping" in name:
                description = translate(
                    "Assembly",
                    "Force opposing relative velocity along the attachment's local %s axis",
                ) % axis
            elif "AngularStiffness" in name:
                description = translate(
                    "Assembly",
                    "Restoring torque per radian about the attachment's local %s axis",
                ) % axis
            else:
                description = translate(
                    "Assembly",
                    "Torque opposing relative angular velocity about the attachment's local %s axis",
                ) % axis
            spinbox.setToolTip(description)
            spinbox.editingFinished.connect(
                lambda name=name, spinbox=spinbox: self.onBushingValueChanged(name, spinbox)
            )
        self.updateTypeUi()
        Dynamics.purge_touched(self.owner, self.load)

    def setupBushingMatrices(self):
        self.coupledCheckBox = QtWidgets.QCheckBox(translate("Assembly", "Coupled 6×6 matrices"))
        self.coupledCheckBox.setObjectName("CoupledBushingCheckBox")
        self.coupledCheckBox.setToolTip(translate("Assembly", "Couple translation and rotation in attachment I's frame. Matrices must be symmetric and positive semidefinite: negative-energy springs and active damping are rejected by the solver. Edit the upper triangle; its mirror is filled automatically."))
        self.form_load.BushingPage.layout().addWidget(self.coupledCheckBox)
        self.matrixTabs = QtWidgets.QTabWidget()
        self.matrixTables = []
        for prop, title in (("BushingStiffnessMatrix", "Stiffness"), ("BushingDampingMatrix", "Damping")):
            table = QtWidgets.QTableWidget(6, 6)
            table.setObjectName(prop + "Table")
            table.setHorizontalHeaderLabels(["x", "y", "z", "rx", "ry", "rz"])
            table.setVerticalHeaderLabels(["Fx", "Fy", "Fz", "Mx", "My", "Mz"])
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
            values = getattr(self.load, prop)
            for row in range(6):
                for col in range(6):
                    item = QtWidgets.QTableWidgetItem(format(values[6 * row + col], ".12g"))
                    effort = "N" if row < 3 else "N mm"
                    strain = "mm" if col < 3 else "rad"
                    item.setToolTip(effort + (" s / " if title == "Damping" else " / ") + strain)
                    if col < row:
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                    table.setItem(row, col, item)
            table.cellChanged.connect(lambda row, col, table=table, prop=prop: self.onMatrixChanged(table, prop, row, col))
            self.matrixTables.append(table)
            self.matrixTabs.addTab(table, translate("Assembly", title))
        self.form_load.BushingPage.layout().addWidget(self.matrixTabs)
        self.matrixMessage = QtWidgets.QLabel()
        self.matrixMessage.setWordWrap(True)
        self.form_load.BushingPage.layout().addWidget(self.matrixMessage)
        self.coupledCheckBox.setChecked(self.load.CoupledBushing)
        self.coupledCheckBox.toggled.connect(self.onCoupledChanged)
        self.updateMatrixVisibility()

    def updateMatrixVisibility(self):
        coupled = self.coupledCheckBox.isChecked()
        self.matrixTabs.setVisible(coupled)
        self.matrixMessage.setVisible(coupled)
        self.form_load.BushingTranslationGroup.setVisible(not coupled)
        self.form_load.BushingRotationGroup.setVisible(not coupled)
        self.validateMatrices()

    def validateMatrices(self):
        errors = []
        for index, table in enumerate(self.matrixTables):
            try:
                values = [float(table.item(row, col).text()) for row in range(6) for col in range(6)]
            except ValueError:
                errors.append(self.matrixTabs.tabText(index) + ": " + translate("Assembly", "Enter a finite number in every cell."))
                continue
            try:
                validateBushingMatrix(values)
            except ValueError as error:
                errors.append(self.matrixTabs.tabText(index) + ": " + str(error))
        self.matrixMessage.setText("\n".join(errors))
        return not errors

    def onCoupledChanged(self, checked):
        self.load.CoupledBushing = checked
        self.updateMatrixVisibility()

    def onMatrixChanged(self, table, prop, row, col):
        try:
            value = float(table.item(row, col).text())
            if not math.isfinite(value):
                raise ValueError()
        except ValueError:
            self.validateMatrices()
            return
        blocker = QtCore.QSignalBlocker(table)
        table.item(row, col).setText(format(value, ".12g"))
        table.item(col, row).setText(format(value, ".12g"))
        del blocker
        values = list(getattr(self.load, prop))
        values[6 * row + col] = values[6 * col + row] = value
        setattr(self.load, prop, values)
        self.validateMatrices()

    def endpointSpinboxes(self):
        return (
            self.form_load.EndpointJX,
            self.form_load.EndpointJY,
            self.form_load.EndpointJZ,
        )

    def bushingSpinboxes(self):
        result = []
        for kind, unit in (
            ("LinearStiffness", "N/mm"),
            ("LinearDamping", "kg/s"),
            ("AngularStiffness", "N*mm"),
            ("AngularDamping", "N*mm*s"),
        ):
            for axis in "XYZ":
                name = "Bushing" + kind + axis
                result.append((name, getattr(self.form_load, name), unit))
        return result

    def updateTypeUi(self):
        spring = self.load.LoadType in ("SpringDamper", "TorsionalSpringDamper")
        torsional = self.load.LoadType == "TorsionalSpringDamper"
        bushing = self.load.LoadType == "Bushing"
        self.form_load.LoadTypeStack.setCurrentWidget(
            self.form_load.BushingPage
            if bushing
            else self.form_load.SpringPage
            if spring
            else self.form_load.WrenchPage
        )
        if bushing:
            self.updateBushingValues()
        elif spring:
            self.form_load.EndpointJLabel.setVisible(not torsional)
            for widget in self.endpointSpinboxes():
                widget.setVisible(not torsional)
            self.form_load.StiffnessLabel.setText(
                translate("Assembly", "Angular stiffness (per radian)")
                if torsional else translate("Assembly", "Stiffness")
            )
            self.form_load.DampingLabel.setText(
                translate("Assembly", "Angular damping (per radian)")
                if torsional else translate("Assembly", "Damping")
            )
            self.form_load.RestLengthLabel.setText(
                translate("Assembly", "Free angle")
                if torsional else translate("Assembly", "Free length")
            )
            self.form_load.UseCurrentLengthButton.setToolTip(
                translate("Assembly", "Use the current relative twist as the free angle")
                if torsional
                else translate(
                    "Assembly",
                    "Use the current distance between the attachment points as the free length",
                )
            )
            self.form_load.StiffnessSpinBox.setToolTip(
                translate("Assembly", "Restoring torque per radian of angular deflection")
                if torsional else ""
            )
            self.form_load.DampingSpinBox.setToolTip(
                translate(
                    "Assembly",
                    "Opposing torque per radian per second of relative angular velocity",
                )
                if torsional else ""
            )
            self.updateSpringValues()
        else:
            self.updateMagnitude()

    def updateMagnitude(self):
        value = self.load.Force if self.load.LoadType == "Force" else self.load.Torque
        self.form_load.MagnitudeSpinBox.setProperty("value", value)
        if hasattr(self, "profileField"):
            self.profileField.contextChanged()

    def updateSpringValues(self):
        self._updating_ui = True
        for spinbox, value in zip(self.endpointSpinboxes(), self.load.AttachmentJ.Base):
            spinbox.setProperty("value", App.Units.Quantity(value, App.Units.Length))
        torsional = self.load.LoadType == "TorsionalSpringDamper"
        values = (
            (
                (1000 * self.load.TorsionalStiffness.getValueAs("N*mm/rad"), "N*mm"),
                (1000 * self.load.TorsionalDamping.getValueAs("N*mm*s/rad"), "N*mm*s"),
                (self.load.FreeAngle.Value, "deg"),
            )
            if torsional
            else (
                (self.load.Stiffness.Value, "N/mm"),
                (self.load.Damping.Value, "kg/s"),
                (self.load.RestLength.Value, "mm"),
            )
        )
        for spinbox, (raw_value, unit) in zip(
            (
                self.form_load.StiffnessSpinBox,
                self.form_load.DampingSpinBox,
                self.form_load.RestLengthSpinBox,
            ),
            values,
        ):
            # PySide's generic Quantity property conversion loses compound
            # inverse-angle units. Set the schema and FreeCAD base value
            # independently so this reusable editor can change dimensions.
            # Compound unit expressions need an explicit scalar.
            spinbox.setProperty("unit", "1 " + unit)
            spinbox.setProperty("rawValue", raw_value)
        # QuantitySpinBox forwards an internal editor signal asynchronously.
        # Keep synchronization guarded until those notifications are drained.
        QtCore.QTimer.singleShot(0, self.finishUiUpdate)

    def updateBushingValues(self):
        self._updating_ui = True
        for name, spinbox, unit in self.bushingSpinboxes():
            value = getattr(self.load, name)
            raw_value = (
                1000 * value.getValueAs("N*mm/rad")
                if "AngularStiffness" in name
                else 1000 * value.getValueAs("N*mm*s/rad")
                if "AngularDamping" in name
                else value.Value
            )
            spinbox.setProperty("unit", "1 " + unit)
            spinbox.setProperty("rawValue", raw_value)
        QtCore.QTimer.singleShot(0, self.finishUiUpdate)

    def finishUiUpdate(self):
        self._updating_ui = False

    def onComponentChanged(self, index):
        if 0 <= index < len(self.components):
            self.load.BodyI = self.components[index]
            self.load.Proxy.update_attachment(self.load)
            self.invalidateResult()

    def onTypeChanged(self, index):
        load_type = self.LOAD_TYPES[index]
        if load_type in ("SpringDamper", "TorsionalSpringDamper", "Bushing"):
            self._updating_ui = True
        self.load.LoadType = load_type
        if self.automatic_label:
            self.load.Label = (
                translate(
                    "Assembly",
                    "Torsional Spring-Damper"
                    if load_type == "TorsionalSpringDamper"
                    else "Bushing"
                    if load_type == "Bushing"
                    else "Spring-Damper",
                )
                if load_type in ("SpringDamper", "TorsionalSpringDamper", "Bushing")
                else translate("Assembly", load_type)
            )
        if load_type not in self.initialized_types:
            self.ensureSpringDefaults()
            self.initialized_types.add(load_type)
        self.updateTypeUi()
        self.load.ViewObject.Proxy.updateVisual(self.load)
        self.invalidateResult()

    def ensureSpringDefaults(self):
        if self.load.LoadType not in ("SpringDamper", "TorsionalSpringDamper", "Bushing"):
            return
        if self.load.LoadType == "Bushing":
            # Only called on the first choice of this type for a new load.
            # Start stress-free, just like Dynamics.create_load('Bushing').
            Dynamics.align_bushing_reference(self.load)
            for axis in "XYZ":
                linear = "BushingLinearStiffness" + axis
                angular = "BushingAngularStiffness" + axis
                if getattr(self.load, linear).Value == 0:
                    setattr(self.load, linear, "1 N/mm")
                if getattr(self.load, angular).Value == 0:
                    setattr(self.load, angular, "100 N*mm/rad")
            return
        if self.load.LoadType == "TorsionalSpringDamper":
            if self.load.TorsionalStiffness.Value == 0:
                self.load.TorsionalStiffness = "100 N*mm/rad"
            return
        if Dynamics.spring_length(self.load) < 1e-9:
            point = Dynamics.attachment_placement(self.load, "I").Base + App.Vector(0, 0, -20)
            if self.load.BodyJ:
                point = Dynamics.component_placement(self.load.BodyJ).inverse().multVec(point)
            self.load.AttachmentJ = App.Placement(point, App.Rotation())
        if self.load.Stiffness.Value == 0:
            self.load.Stiffness = "1 N/mm"
        if self.load.RestLength.Value == 0:
            self.load.RestLength = App.Units.Quantity(
                Dynamics.spring_length(self.load), App.Units.Length
            )

    def onReactionComponentChanged(self, index, bushing=False):
        world = Dynamics.attachment_placement(self.load, "J")
        body = self.components[index - 1] if index > 0 else None
        self.load.BodyJ = body
        self.load.AttachmentJ = (
            Dynamics.component_placement(body).inverse() * world if body else world
        )
        for combo in (self.form_load.ReactionComponentComboBox, self.form_load.BushingReactionComponentComboBox):
            blocker = QtCore.QSignalBlocker(combo)
            combo.setCurrentIndex(index)
            del blocker
        if bushing or self.load.LoadType == "Bushing":
            self.updateBushingValues()
        else:
            self.updateSpringValues()
        self.load.ViewObject.Proxy.updateVisual(self.load)
        self.invalidateResult()

    def onEndpointChanged(self, _value):
        if self._updating_ui:
            return
        point = App.Vector(
            *(spinbox.property("value").Value for spinbox in self.endpointSpinboxes())
        )
        placement = self.load.AttachmentJ
        placement.Base = point
        self.load.AttachmentJ = placement
        self.load.ViewObject.Proxy.updateVisual(self.load)
        self.invalidateResult()

    def onStiffnessChanged(self):
        if self._updating_ui:
            return
        name = (
            "TorsionalStiffness"
            if self.load.LoadType == "TorsionalSpringDamper"
            else "Stiffness"
        )
        self.setSpringValue(name, self.form_load.StiffnessSpinBox)
        self.invalidateResult()

    def onDampingChanged(self):
        if self._updating_ui:
            return
        name = (
            "TorsionalDamping"
            if self.load.LoadType == "TorsionalSpringDamper"
            else "Damping"
        )
        self.setSpringValue(name, self.form_load.DampingSpinBox)
        self.invalidateResult()

    def onRestLengthChanged(self):
        if self._updating_ui:
            return
        name = "FreeAngle" if self.load.LoadType == "TorsionalSpringDamper" else "RestLength"
        self.setSpringValue(name, self.form_load.RestLengthSpinBox)
        self.invalidateResult()

    def setSpringValue(self, name, spinbox):
        raw_value = spinbox.property("rawValue")
        if name == "TorsionalStiffness":
            self.load.TorsionalStiffness = f"{raw_value / 1000} N*mm/rad"
        elif name == "TorsionalDamping":
            self.load.TorsionalDamping = f"{raw_value / 1000} N*mm*s/rad"
        else:
            setattr(self.load, name, raw_value)

    def useCurrentLength(self):
        if self.load.LoadType == "TorsionalSpringDamper":
            self.load.FreeAngle = math.degrees(Dynamics.torsional_angle(self.load))
        else:
            self.load.RestLength = App.Units.Quantity(
                Dynamics.spring_length(self.load), App.Units.Length
            )
        self.updateSpringValues()
        self.invalidateResult()

    def useCurrentPose(self):
        Dynamics.align_bushing_reference(self.load)
        self.load.ViewObject.Proxy.updateVisual(self.load)
        self.invalidateResult()

    def onBushingValueChanged(self, name, spinbox):
        if self._updating_ui:
            return
        raw_value = spinbox.property("rawValue")
        if "AngularStiffness" in name:
            setattr(self.load, name, f"{raw_value / 1000} N*mm/rad")
        elif "AngularDamping" in name:
            setattr(self.load, name, f"{raw_value / 1000} N*mm*s/rad")
        else:
            setattr(self.load, name, raw_value)
        self.invalidateResult()

    def onMagnitudeChanged(self, _value):
        if getattr(self.load.Proxy, "_initializing_editor", False):
            return
        value = self.form_load.MagnitudeSpinBox.property("value")
        current = self.load.Force if self.load.LoadType == "Force" else self.load.Torque
        if current == value:
            return
        if self.load.LoadType == "Force":
            self.load.Force = value
        else:
            self.load.Torque = value
        self.invalidateResult()

    def onFormulaChanged(self, formula):
        self.load.Formula = formula
        self.form_load.MagnitudeSpinBox.setEnabled(not formula.strip())
        self.invalidateResult()

    def invalidateResult(self):
        Dynamics.invalidate_results(self.load)

    def accept(self):
        if self.load.LoadType == "Bushing" and self.load.CoupledBushing and not self.validateMatrices():
            return False
        Dynamics.purge_touched(self.owner, self.load)
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
                    self.resume_simulation, "loadsTab"
                ),
            )


Gui.addCommand("Assembly_CreateLoad", CommandCreateLoad())
