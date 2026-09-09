# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2024 Ondsel <development@ondsel.com>                     *
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

import re
import os
import csv
import time
import tempfile
from pathlib import Path

import FreeCAD as App

from pivy import coin
from Part import LineSegment, Compound

from PySide.QtCore import QT_TRANSLATE_NOOP

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets
    from PySide.QtWidgets import (
        QFileDialog,
        QProgressDialog,
    )
    from PySide.QtCore import Qt
    from PySide.QtGui import QIcon, QMessageBox

import UtilsAssembly
import Preferences
import Dynamics

translate = App.Qt.translate

__title__ = "Assembly Command Create Simulation"
__author__ = "Ondsel"
__url__ = "https://www.freecad.org"

_active_simulation_task = None


def activeSimulationTask():
    return _active_simulation_task


class CommandCreateSimulation:
    def __init__(self):
        pass

    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateSimulation",
            "MenuText": QT_TRANSLATE_NOOP("Assembly_CreateSimulation", "Simulation"),
            "Accel": "V",
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly_CreateSimulation",
                "Creates a new simulation of the current assembly",
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        if not UtilsAssembly.isAssemblyCommandActive():
            return False

        assembly = UtilsAssembly.activeAssembly()
        # Gravity can act on a free body without any joint or prescribed motion.
        return UtilsAssembly.number_of_components_in(assembly) > 0

    def Activated(self):
        assembly = UtilsAssembly.activeAssembly()
        if not assembly:
            return

        self.panel = TaskAssemblyCreateSimulation()
        dialog = Gui.Control.showDialog(self.panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)


class CommandCreateMotion:
    def GetResources(self):
        return {
            "Pixmap": "button_right",
            "MenuText": QT_TRANSLATE_NOOP("Assembly", "Add Prescribed Motion"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly", "Creates a prescribed motion. While editing a simulation it is "
                "local to that simulation; otherwise it is global and used by every simulation."
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        task = activeSimulationTask()
        if task is None and not UtilsAssembly.isAssemblyCommandActive():
            return False
        assembly = task.assembly if task else UtilsAssembly.activeAssembly()
        return bool(
            UtilsAssembly.getJointsOfType(
                assembly, ["Revolute", "Slider", "Cylindrical"]
            )
            and (not Gui.Control.activeDialog() or task)
        )

    def Activated(self):
        task = activeSimulationTask()
        startCreateMotion(task)


######### Simulation Object ###########
class Simulation(Dynamics.Study):
    def __init__(self, feaPy):
        feaPy.Proxy = self
        feaPy.addExtension("App::GroupExtensionPython")

        if not hasattr(feaPy, "aTimeStart"):
            feaPy.addProperty(
                "App::PropertyTime",
                "aTimeStart",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation start time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "bTimeEnd"):
            feaPy.addProperty(
                "App::PropertyTime",
                "bTimeEnd",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation end time.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "cTimeStepOutput"):
            feaPy.addProperty(
                "App::PropertyTime",
                "cTimeStepOutput",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Simulation time step for output.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "fGlobalErrorTolerance"):
            feaPy.addProperty(
                "App::PropertyFloat",
                "fGlobalErrorTolerance",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Integration global error tolerance.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "jFramesPerSecond"):
            feaPy.addProperty(
                "App::PropertyInteger",
                "jFramesPerSecond",
                "Simulation",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "Frames Per Second.",
                ),
                locked=True,
            )

        feaPy.aTimeStart = 0.0
        feaPy.bTimeEnd = 1.0
        feaPy.cTimeStepOutput = 1.0e-2
        feaPy.fGlobalErrorTolerance = 1.0e-6
        feaPy.jFramesPerSecond = 30

        self.motionsChangedCallback = None
        self._properties(feaPy, legacy=True)

    def onDocumentRestored(self, feaPy):
        self._properties(feaPy, legacy=True)
        self.motionsChangedCallback = None
        if feaPy.Status == "Running":
            feaPy.Status = "Failed"
            feaPy.LastError = translate("Assembly", "The previous run did not finish.")
        Dynamics.purge_touched(feaPy)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        super().onChanged(feaPy, prop)
        if prop == "Group" and hasattr(self, "motionsChangedCallback"):
            if self.motionsChangedCallback is not None:
                self.motionsChangedCallback()

    def setMotionsChangedCallback(self, callback):
        self.motionsChangedCallback = callback

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getAssembly(self, feaPy):
        assert feaPy.isDerivedFrom("App::FeaturePython"), "Type error"
        return feaPy.Assembly


class ViewProviderSimulation:
    def __init__(self, vpDoc):
        vpDoc.Proxy = self
        self.Object = vpDoc.Object
        self.setProperties(vpDoc)

    def setProperties(self, vpDoc):
        if not hasattr(vpDoc, "Decimals"):
            vpDoc.addProperty(
                "App::PropertyInteger",
                "Decimals",
                "Space",
                QT_TRANSLATE_NOOP(
                    "App::Property", "The number of decimals to use for calculated texts"
                ),
                locked=True,
            )
            vpDoc.Decimals = 9

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        pass

    def getIcon(self):
        return ":/icons/Assembly_CreateSimulation.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def claimChildren(self):
        return self.app_obj.Group

    @staticmethod
    def isSimulationInput(obj):
        return any(
            hasattr(obj, name)
            for name in ("MotionType", "LoadType", "InitialVelocityType", "ContactType", "FrictionModel")
        )

    def canDragObjects(self):
        return True

    def canDropObjects(self):
        return True

    def canDragObject(self, obj):
        return self.isSimulationInput(obj)

    def canDropObject(self, obj):
        return self.isSimulationInput(obj) and Dynamics.assembly_for_owner(
            Dynamics.input_owner(obj)
        ) == self.app_obj.Assembly

    def canDragAndDropObject(self, obj):
        return self.canDropObject(obj)

    def dragObject(self, _view_object, obj):
        Dynamics.invalidate_results(obj)
        self.app_obj.removeObject(obj)

    def dropObject(self, _view_object, obj):
        old_owner = Dynamics.input_owner(obj)
        if old_owner and Dynamics.assembly_for_owner(old_owner) != self.app_obj.Assembly:
            raise ValueError("Simulation inputs cannot be moved between assemblies.")
        if old_owner and old_owner != self.app_obj:
            old_owner.removeObject(obj)
        self.app_obj.addObject(obj)
        Dynamics.invalidate_results(obj)

    def doubleClicked(self, vpDoc):
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()

        assembly = vpDoc.Object.Proxy.getAssembly(vpDoc.Object)

        if assembly is None:
            return False

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        panel = TaskAssemblyCreateSimulation(vpDoc.Object)
        dialog = Gui.Control.showDialog(panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(App.ActiveDocument.Name)

        return True

    def onDelete(self, vobj, subelements):
        for obj in self.claimChildren():
            obj.Document.removeObject(obj.Name)
        return True


########### Motion Object #############
MotionTypes = [
    "Angular",
    "Linear",
]


class Motion:
    def __init__(self, feaPy, motionType=MotionTypes[0], joint=None, formula=""):
        feaPy.Proxy = self

        self.createProperties(feaPy)

        feaPy.MotionType = MotionTypes  # sets the list
        feaPy.MotionType = motionType  # set the initial value
        feaPy.Joint = joint
        feaPy.Formula = formula

    def onDocumentRestored(self, feaPy):
        self.createProperties(feaPy)

    def createProperties(self, feaPy):
        import MotionProfile
        MotionProfile.ensure_properties(feaPy)
        if not feaPy.hasExtension("App::SuppressibleExtensionPython"):
            feaPy.addExtension("App::SuppressibleExtensionPython")
        if not hasattr(feaPy, "Joint"):
            feaPy.addProperty(
                "App::PropertyXLinkSubHidden",
                "Joint",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The joint that is moved by the motion"),
                locked=True,
            )

        if not hasattr(feaPy, "Formula"):
            feaPy.addProperty(
                "App::PropertyString",
                "Formula",
                "Motion",
                QT_TRANSLATE_NOOP(
                    "App::Property",
                    "This is the formula of the motion. For example '1.0*time'.",
                ),
                locked=True,
            )

        if not hasattr(feaPy, "MotionType"):
            feaPy.addProperty(
                "App::PropertyEnumeration",
                "MotionType",
                "Motion",
                QT_TRANSLATE_NOOP("App::Property", "The type of the motion"),
                locked=True,
            )

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def onChanged(self, feaPy, prop):
        if App.isRestoring():
            return
        if prop == "Formula" and getattr(self, "_updating_profile", False):
            return
        if prop == "Formula" and getattr(feaPy, "ProfileData", ""):
            feaPy.ProfileData = ""
        if prop in ("Joint", "Formula", "MotionType", "Suppressed", "ProfileData"):
            Dynamics.invalidate_results(feaPy)

    def execute(self, feaPy):
        """Do something when doing a recomputation, this method is mandatory"""
        pass

    def getSimulation(self, feaPy):
        for obj in feaPy.InList:
            if hasattr(obj, "Proxy"):
                if hasattr(obj.Proxy, "setMotionsChangedCallback"):
                    return obj
        return None

    def getAssembly(self, feaPy):
        return Dynamics.assembly_for_owner(Dynamics.input_owner(feaPy))


class ViewProviderMotion:
    def __init__(self, vp):
        if not vp.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            vp.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        vp.Proxy = self
        self.updateLabel()

    def attach(self, vpDoc):
        """Setup the scene sub-graph of the view provider, this method is mandatory"""
        if not vpDoc.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            vpDoc.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        self.app_obj = vpDoc.Object

        self.display_mode = coin.SoType.fromName("SoFCSelection").createInstance()

        vpDoc.addDisplayMode(self.display_mode, "Wireframe")

    def updateData(self, feaPy, prop):
        """If a property of the handled feature has changed we have the chance to handle this here"""
        pass

    def getDisplayModes(self, vpDoc):
        """Return a list of display modes."""
        return ["Wireframe"]

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in getDisplayModes."""
        return "Wireframe"

    def onChanged(self, vpDoc, prop):
        """Here we can do something when a single property got changed"""
        # App.Console.PrintMessage("Change property: " + str(prop) + "\n")
        pass

    def getIcon(self):
        if self.app_obj.MotionType == "Angular":
            return ":/icons/button_rotate.svg"

        return ":/icons/button_right.svg"

    def dumps(self):
        """When saving the document this object gets stored using Python's json module.\
                Since we have some un-serializable parts here -- the Coin stuff -- we must define this method\
                to return a tuple of all serializable objects or None."""
        return None

    def loads(self, state):
        """When restoring the serialized object from document we have the chance to set some internals here.\
                Since no data were serialized nothing needs to be done here."""
        return None

    def doubleClicked(self, vpDoc):
        motion = vpDoc.Object
        # Defer replacing the task dialog until the double-click event has
        # returned; GUIApplication::notify may still reference its widgets.
        QtCore.QTimer.singleShot(0, lambda: editMotion(motion))
        return True

    def openEditDialog(self):
        return editMotion(self.app_obj)

    def updateLabel(self):
        if self.app_obj.Joint is None:
            return

        typeStr = "Linear" if self.app_obj.MotionType == "Linear" else "Angular"

        self.app_obj.Label = "{label} ({type_})".format(
            label=self.app_obj.Joint[0].Label, type_=translate("Assembly", typeStr)
        )

    def getAssembly(self):
        assembly = self.app_obj.Proxy.getAssembly(self.app_obj)

        if assembly is None:
            return None

        if UtilsAssembly.activeAssembly() != assembly:
            Gui.ActiveDocument.setEdit(assembly)

        return assembly


def _motionTypesForJoint(joint):
    if joint is None:
        return []
    if joint.JointType == "Revolute":
        return ["Angular"]
    if joint.JointType == "Slider":
        return ["Linear"]
    return ["Angular", "Linear"]


def _showMotionTask(motion, owner, resume_simulation=None):
    panel = TaskAssemblyCreateMotion(motion, owner, resume_simulation)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(motion.Document.Name)


def _createMotion(simulation, joint):
    owner = Dynamics.normalize_input_owner(simulation)
    motion_type = _motionTypesForJoint(joint)[0]
    motion = owner.Document.addObject("App::FeaturePython", "Motion")
    Motion(motion, motion_type, joint, "initialValue + 5*time")
    ViewProviderMotion(motion.ViewObject)
    owner.addObject(motion)
    Dynamics.purge_touched(owner, motion)
    return motion


def startCreateMotion(simulation_task):
    simulation = simulation_task.simFeaturePy if simulation_task else None
    assembly = simulation_task.assembly if simulation_task else UtilsAssembly.activeAssembly()
    joints = UtilsAssembly.getJointsOfType(
        assembly, ["Revolute", "Slider", "Cylindrical"]
    )
    if not joints:
        return False
    resume = simulation_task.suspendForChildTask() if simulation_task else None
    Gui.ActiveDocument.openCommand("Add Prescribed Motion")
    motion = _createMotion(simulation or assembly, joints[0])
    _showMotionTask(motion, Dynamics.input_owner(motion), resume)
    return True


def editMotion(motion):
    owner = Dynamics.input_owner(motion)
    assembly = Dynamics.assembly_for_owner(owner)
    if owner is None or assembly is None:
        return False

    simulation_task = activeSimulationTask()
    if simulation_task is not None:
        resume = simulation_task.suspendForChildTask()
    else:
        resume = None
        task = Gui.Control.activeTaskDialog()
        if task:
            task.reject()

    if UtilsAssembly.activeAssembly() != assembly:
        Gui.ActiveDocument.setEdit(assembly)
    # A tree double-click may already own the generic Edit transaction. Keep
    # it alive until the task accepts or rejects; aborting it from inside the
    # event callback can invalidate GUI state still used by the tree.
    if motion.Document.getBookedTransactionID() == 0:
        Gui.ActiveDocument.openCommand("Edit " + motion.Label)
    _showMotionTask(motion, owner, resume)
    return True


class TaskAssemblyCreateMotion:
    def __init__(self, motion, simulation, resume_simulation=None):
        self.motion = motion
        self.owner = simulation
        self.simulation = simulation if Dynamics.is_study(simulation) else None
        self.resume_simulation = resume_simulation
        self.assembly = Dynamics.assembly_for_owner(simulation)
        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateMotion.ui")
        self.form.setWindowIcon(Gui.getIcon("button_right"))
        self.joints = UtilsAssembly.getJointsOfType(
            self.assembly, ["Revolute", "Slider", "Cylindrical"]
        )
        for joint in self.joints:
            self.form.JointComboBox.addItem(QIcon(joint.ViewObject.Icon), joint.Label, joint)

        current_joint = motion.Joint[0] if motion.Joint else None
        current_index = self.joints.index(current_joint) if current_joint in self.joints else 0
        self.form.JointComboBox.setCurrentIndex(current_index)
        self.updateMotionTypes()
        if motion.MotionType in [
            self.form.MotionTypeComboBox.itemText(i)
            for i in range(self.form.MotionTypeComboBox.count())
        ]:
            self.form.MotionTypeComboBox.setCurrentText(motion.MotionType)
        self.form.FormulaLineEdit.setText(motion.Formula)
        self.form.HelpButton.toggled.connect(self.form.HelpLabel.setVisible)
        self.form.JointComboBox.currentIndexChanged.connect(self.onJointChanged)
        self.form.MotionTypeComboBox.currentTextChanged.connect(self.onMotionTypeChanged)
        self.form.FormulaLineEdit.textChanged.connect(self.onFormulaChanged)
        import ProfileEditor
        self.profileField = ProfileEditor.ProfileField(motion, self.form.FormulaLineEdit, self.form)
        self.form.layout().insertWidget(1, self.profileField)
        self.form.FormulaLabel.hide()
        self.form.HelpButton.hide()
        Dynamics.purge_touched(self.owner, self.motion)

    def updateMotionTypes(self):
        joint = self.currentJoint()
        self.form.MotionTypeComboBox.blockSignals(True)
        self.form.MotionTypeComboBox.clear()
        self.form.MotionTypeComboBox.addItems(_motionTypesForJoint(joint))
        self.form.MotionTypeComboBox.blockSignals(False)

    def currentJoint(self):
        index = self.form.JointComboBox.currentIndex()
        return self.joints[index] if 0 <= index < len(self.joints) else None

    def onJointChanged(self, _index):
        joint = self.currentJoint()
        self.motion.Joint = joint
        self.updateMotionTypes()
        self.onMotionTypeChanged(self.form.MotionTypeComboBox.currentText())

    def onMotionTypeChanged(self, motion_type):
        if motion_type:
            self.motion.MotionType = motion_type
            if hasattr(self, "profileField"):
                self.profileField.contextChanged()
            self.motion.ViewObject.Proxy.updateLabel()
            self.invalidateResult()

    def onFormulaChanged(self, formula):
        self.motion.Formula = formula
        self.invalidateResult()

    def invalidateResult(self):
        Dynamics.invalidate_results(self.motion)

    def accept(self):
        Dynamics.purge_touched(self.owner, self.motion)
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
                lambda: TaskAssemblyCreateSimulation.reopen(
                    self.resume_simulation, "motionsTab"
                ),
            )


######### Create Simulation Task ###########
class TaskAssemblyCreateSimulation(QtCore.QObject):
    def __init__(self, simFeaturePy=None):
        super().__init__()
        global _active_simulation_task
        Gui.Selection.clearSelection()

        self.assembly = UtilsAssembly.activeAssembly()

        self.initialPlcs = UtilsAssembly.saveAssemblyPartsPlacements(self.assembly)
        self.frameTimes = {}

        self.doc = self.assembly.Document
        self.gui_doc = Gui.getDocument(self.doc)

        self.view = self.gui_doc.activeView()

        if not self.assembly or not self.view or not self.doc:
            return

        self.runKinematicsTimer = QtCore.QTimer()
        self.runKinematicsTimer.setSingleShot(True)
        self.runKinematicsTimer.timeout.connect(self.displayLastFrame)

        self.animationTimer = QtCore.QTimer()
        self.animationTimer.setInterval(50)  # ms
        self.animationTimer.timeout.connect(self.playAnimation)

        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateSimulation.ui")
        self.form.setWindowIcon(Gui.getIcon("Assembly_CreateSimulation"))
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.settingsTab),
            QIcon(":/icons/preferences-general.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.motionsTab),
            QIcon(":/icons/button_right.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.loadsTab),
            QIcon(":/icons/Assembly_CreateLoad.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.initialTab),
            QIcon(":/icons/button_right.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.contactsTab),
            QIcon(":/icons/Assembly_CreateContact.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.frictionTab),
            QIcon(":/icons/Assembly_CreateFriction.svg"),
        )
        self.form.tabWidget.setTabIcon(
            self.form.tabWidget.indexOf(self.form.resultsTab),
            QIcon(":/icons/Std_DependencyGraph.svg"),
        )
        self.form.motionList.installEventFilter(self)
        self.form.loadList.installEventFilter(self)
        self.form.initialVelocityList.installEventFilter(self)
        self.form.contactList.installEventFilter(self)
        self.form.frictionList.installEventFilter(self)
        self.setSpinboxPrecision(self.form.TimeStartSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeEndSpinBox, 9)
        self.setSpinboxPrecision(self.form.TimeStepOutputSpinBox, 9)
        self.setSpinboxPrecision(self.form.GravityMagnitudeSpinBox, 6, App.Units.Acceleration)
        self.form.GravityMagnitudeSpinBox.setProperty("minimum", 0.0)
        self.form.GravityDirectionEdit.setProperty("label", translate("Assembly", "Direction"))
        self.setSpinboxPrecision(self.form.GlobalErrorToleranceSpinBox, 9, App.Units.Length)
        self.form.motionList.itemDoubleClicked.connect(self.onMotionDoubleClicked)
        self.form.loadList.itemDoubleClicked.connect(self.onLoadDoubleClicked)
        self.form.initialVelocityList.itemDoubleClicked.connect(
            self.onInitialVelocityDoubleClicked
        )
        self.form.contactList.itemDoubleClicked.connect(self.onContactDoubleClicked)
        self.form.frictionList.itemDoubleClicked.connect(self.onFrictionDoubleClicked)
        self.form.RunKinematicsButton.clicked.connect(self.runKinematics)
        self.form.frameSlider.valueChanged.connect(self.onFrameChanged)
        self.form.PlayBackwardButton.clicked.connect(self.animationTimerStartBackward)
        self.form.PlayForwardButton.clicked.connect(self.animationTimerStartForward)
        self.form.StepBackwardButton.clicked.connect(self.stepBackward)
        self.form.StepForwardButton.clicked.connect(self.stepForward)
        self.form.StopButton.clicked.connect(self.stopAnimation)
        self.form.AddMotionButton.clicked.connect(self.addMotionClicked)
        self.form.RemoveMotionButton.clicked.connect(self.deleteSelectedMotions)
        self.form.AddLoadButton.clicked.connect(self.addLoadClicked)
        self.form.RemoveLoadButton.clicked.connect(self.deleteSelectedLoads)
        self.form.AddInitialVelocityButton.clicked.connect(
            self.addInitialVelocityClicked
        )
        self.form.RemoveInitialVelocityButton.clicked.connect(
            self.deleteSelectedInitialVelocities
        )
        self.form.AddContactButton.clicked.connect(self.addContactClicked)
        self.form.RemoveContactButton.clicked.connect(self.deleteSelectedContacts)
        self.form.AddFrictionButton.clicked.connect(self.addFrictionClicked)
        self.form.RemoveFrictionButton.clicked.connect(self.deleteSelectedFrictions)
        self.form.ResultCategoryComboBox.currentIndexChanged.connect(
            self.onResultCategoryChanged
        )
        self.form.ResultEntityComboBox.currentIndexChanged.connect(
            self.onResultSelectionChanged
        )
        self.form.ResultQuantityComboBox.currentIndexChanged.connect(
            self.onResultSelectionChanged
        )
        self.form.PlotResultButton.clicked.connect(self.plotResult)
        self.form.ExportResultButton.clicked.connect(self.exportResult)
        self.pointMeasurementButton = QtWidgets.QPushButton(translate("Assembly", "Point measurement…"))
        self.form.resultsTab.layout().addWidget(self.pointMeasurementButton)
        self.pointMeasurementButton.clicked.connect(self.addPointMeasurement)
        self.measurementList = QtWidgets.QListWidget()
        self.measurementList.setMaximumHeight(100)
        self.form.resultsTab.layout().addWidget(self.measurementList)
        self.measurementList.itemDoubleClicked.connect(self.editPointMeasurement)
        import CommandSimulationEvent
        CommandSimulationEvent.add_tab(self)
        self.form.groupBox_player.hide()
        self.form.SaveAnimationButton.clicked.connect(self.saveAnimation)
        self.form.SaveAnimationButton.hide()

        if simFeaturePy:
            self.simFeaturePy = simFeaturePy
            Gui.ActiveDocument.openCommand("Edit " + simFeaturePy.Label + " Simulation")
            self.onMotionsChanged()
        else:
            Gui.ActiveDocument.openCommand("Create Simulation")
            self.createSimulationObject()

        self.setUiInitialValues()
        self.form.AnalysisTypeComboBox.currentIndexChanged.connect(self.onAnalysisTypeChanged)
        self.form.TimeStartSpinBox.valueChanged.connect(self.onTimeStartChanged)
        self.form.TimeEndSpinBox.valueChanged.connect(self.onTimeEndChanged)
        self.form.TimeStepOutputSpinBox.valueChanged.connect(self.onTimeStepOutputChanged)
        self.form.GlobalErrorToleranceSpinBox.valueChanged.connect(
            self.onGlobalErrorToleranceChanged
        )
        self.form.FramesPerSecondSpinBox.valueChanged.connect(self.onFramesPerSecondChanged)
        self.form.groupBox_gravity.toggled.connect(self.onGravityChanged)
        self.form.GravityMagnitudeSpinBox.valueChanged.connect(self.onGravityChanged)
        self.form.GravityDirectionEdit.vectorChanged.connect(self.onGravityChanged)

        self.simFeaturePy.Proxy.setMotionsChangedCallback(self.onInputsChanged)
        _active_simulation_task = self
        self.onMotionsChanged()
        self.onLoadsChanged()
        self.onInitialVelocitiesChanged()
        self.onContactsChanged()
        self.onFrictionsChanged()
        self.resultData = None
        if self.simFeaturePy.Status == "Complete" and self.simFeaturePy.ResultData:
            try:
                self.resultData = Dynamics.results(self.simFeaturePy)
            except ValueError:
                pass
        self.refreshResults()
        self.configurePlayback()
        self.form.AddMotionButton.setEnabled(
            bool(UtilsAssembly.getJointsOfType(self.assembly, ["Revolute", "Slider", "Cylindrical"]))
        )
        self.form.AddLoadButton.setEnabled(bool(self.assembly.getComponents()))
        self.updateInitialVelocityButton()

        self.currentFrm = 1
        self.startFrm = 1
        self.endFrm = 100
        self.fps = 30
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = 0
        Dynamics.purge_touched(self.simFeaturePy)
        self.inputRefreshTimer = QtCore.QTimer(self.form)
        self.inputRefreshTimer.setSingleShot(True)
        self.inputRefreshTimer.timeout.connect(self.onInputsChanged)
        self.resultRefreshTimer = QtCore.QTimer(self.form)
        self.resultRefreshTimer.setSingleShot(True)
        self.resultRefreshTimer.timeout.connect(self.syncResults)
        App.addDocumentObserver(self)

    def slotChangedObject(self, obj, prop):
        if obj == self.simFeaturePy and prop in ("Status", "ResultData"):
            self.resultRefreshTimer.start(0)
        if prop in ("Suppressed", "Label") and obj.Document == self.doc:
            if obj in Dynamics.inputs_for_study(self.simFeaturePy):
                self.inputRefreshTimer.start(0)

    def setUiInitialValues(self):
        # Schema migration happens during restore. Avoid rewriting properties
        # merely because the user opened this task panel.
        if self.simFeaturePy.Assembly != self.assembly:
            self.simFeaturePy.Assembly = self.assembly
        for name, label in (
            ("Automatic", translate("Assembly", "Automatic")),
            ("Kinematics", translate("Assembly", "Kinematics")),
            ("Dynamics", translate("Assembly", "Dynamics")),
        ):
            self.form.AnalysisTypeComboBox.addItem(label, name)
        self.form.AnalysisTypeComboBox.setCurrentIndex(
            self.form.AnalysisTypeComboBox.findData(str(self.simFeaturePy.AnalysisType))
        )
        self.form.groupBox_gravity.setChecked(self.simFeaturePy.GravityEnabled)
        self.form.GravityMagnitudeSpinBox.setProperty("rawValue", self.simFeaturePy.GravityMagnitude.Value)
        direction = self.simFeaturePy.GravityDirection
        for axis, value in zip(("vectorX", "vectorY", "vectorZ"), direction):
            self.form.GravityDirectionEdit.setProperty(axis, value)
        self.form.TimeStartSpinBox.setProperty("rawValue", self.simFeaturePy.aTimeStart.Value)
        self.form.TimeEndSpinBox.setProperty("rawValue", self.simFeaturePy.bTimeEnd.Value)
        self.form.TimeStepOutputSpinBox.setProperty(
            "rawValue", self.simFeaturePy.cTimeStepOutput.Value
        )
        self.form.GlobalErrorToleranceSpinBox.setProperty(
            "rawValue", self.simFeaturePy.fGlobalErrorTolerance
        )
        self.form.FramesPerSecondSpinBox.setValue(self.simFeaturePy.jFramesPerSecond)

    def onAnalysisTypeChanged(self):
        self.animationTimer.stop()
        self.simFeaturePy.AnalysisType = self.form.AnalysisTypeComboBox.currentData()
        self.invalidateResult()
        self.form.groupBox_player.hide()
        self.form.SaveAnimationButton.hide()

    def setSpinboxPrecision(self, spinbox, precision, unit=App.Units.TimeSpan):
        q = App.Units.Quantity()
        q.Unit = unit
        q.Format = {"Precision": precision}
        spinbox.setProperty("value", q)

    def accept(self):
        self.deactivate()
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initialPlcs)
        Dynamics.purge_touched(self.simFeaturePy, *self.simFeaturePy.Group)
        Gui.ActiveDocument.commitCommand()
        return True

    def reject(self):
        self.deactivate()
        Gui.ActiveDocument.abortCommand()
        return True

    def deactivate(self):
        global _active_simulation_task
        App.removeDocumentObserver(self)
        self.inputRefreshTimer.stop()
        self.resultRefreshTimer.stop()
        self.animationTimer.stop()
        self.runKinematicsTimer.stop()
        self.simFeaturePy.Proxy.setMotionsChangedCallback(None)
        if _active_simulation_task is self:
            _active_simulation_task = None
        if Gui.Control.activeDialog():
            Gui.Control.closeDialog()

    def suspendForChildTask(self):
        """Commit the simulation edits and temporarily replace this task dialog."""
        self.animationTimer.stop()
        self.runKinematicsTimer.stop()
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initialPlcs)
        self.simFeaturePy.Proxy.setMotionsChangedCallback(None)
        Dynamics.purge_touched(self.simFeaturePy, *self.simFeaturePy.Group)
        Gui.ActiveDocument.commitCommand()
        self.deactivate()
        return self.simFeaturePy

    @staticmethod
    def reopen(simulation, tab=None):
        if not simulation or not simulation.Document:
            return
        panel = TaskAssemblyCreateSimulation(simulation)
        if tab and hasattr(panel.form, tab):
            panel.form.tabWidget.setCurrentWidget(getattr(panel.form, tab))
        dialog = Gui.Control.showDialog(panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(simulation.Document.Name)

    def onTimeStartChanged(self, quantity):
        self.simFeaturePy.aTimeStart = self.form.TimeStartSpinBox.property("rawValue")
        self.invalidateResult()

    def onTimeEndChanged(self, quantity):
        self.simFeaturePy.bTimeEnd = self.form.TimeEndSpinBox.property("rawValue")
        self.invalidateResult()

    def onTimeStepOutputChanged(self, quantity):
        self.simFeaturePy.cTimeStepOutput = self.form.TimeStepOutputSpinBox.property("rawValue")
        self.invalidateResult()

    def onGlobalErrorToleranceChanged(self, quantity):
        self.simFeaturePy.fGlobalErrorTolerance = self.form.GlobalErrorToleranceSpinBox.property(
            "rawValue"
        )
        self.invalidateResult()

    def onGravityChanged(self, *args):
        self.animationTimer.stop()
        self.simFeaturePy.GravityEnabled = self.form.groupBox_gravity.isChecked()
        self.simFeaturePy.GravityMagnitude = self.form.GravityMagnitudeSpinBox.property("rawValue")
        self.simFeaturePy.GravityDirection = App.Vector(
            *(self.form.GravityDirectionEdit.property(axis) for axis in ("vectorX", "vectorY", "vectorZ"))
        )
        self.invalidateResult()

    def onMotionDoubleClicked(self, item):
        motion = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if motion:
            motion.ViewObject.Proxy.doubleClicked(motion.ViewObject)

    def onLoadDoubleClicked(self, item):
        load = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if load:
            load.ViewObject.Proxy.doubleClicked(load.ViewObject)

    def onInitialVelocityDoubleClicked(self, item):
        initial = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if initial:
            initial.ViewObject.Proxy.doubleClicked(initial.ViewObject)

    def onContactDoubleClicked(self, item):
        contact = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if contact:
            contact.ViewObject.Proxy.doubleClicked(contact.ViewObject)

    def onFrictionDoubleClicked(self, item):
        friction = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if friction:
            friction.ViewObject.Proxy.doubleClicked(friction.ViewObject)

    def createSimulationObject(self):
        existing_group = next(
            (
                obj
                for obj in self.assembly.OutList
                if obj.TypeId == "Assembly::SimulationGroup"
            ),
            None,
        )
        group_was_touched = (
            existing_group is not None and "Touched" in existing_group.State
        )
        sim_group = UtilsAssembly.getSimulationGroup(self.assembly)
        self.simFeaturePy = sim_group.newObject("App::FeaturePython", "Simulation")
        Simulation(self.simFeaturePy)
        ViewProviderSimulation(self.simFeaturePy.ViewObject)
        Dynamics.purge_touched(self.simFeaturePy)
        if not group_was_touched:
            sim_group.purgeTouched()

    def onMotionsChanged(self):
        self.form.motionList.clear()
        for motion in Dynamics.inputs_for_study(self.simFeaturePy):
            if not hasattr(motion, "MotionType"):
                continue
            item = QtWidgets.QListWidgetItem(self.inputLabel(motion))
            item.setData(QtCore.Qt.UserRole, motion.Name)
            self.form.motionList.addItem(item)

    def onInputsChanged(self):
        self.onMotionsChanged()
        self.onLoadsChanged()
        self.onInitialVelocitiesChanged()
        self.onContactsChanged()
        self.onFrictionsChanged()
        import CommandSimulationEvent
        CommandSimulationEvent.refresh_tab(self)

    def onLoadsChanged(self):
        self.form.loadList.clear()
        for load in Dynamics.inputs_for_study(self.simFeaturePy):
            if not hasattr(load, "LoadType"):
                continue
            item = QtWidgets.QListWidgetItem(self.inputLabel(load))
            item.setData(QtCore.Qt.UserRole, load.Name)
            self.form.loadList.addItem(item)

    def onInitialVelocitiesChanged(self):
        self.form.initialVelocityList.clear()
        for initial in Dynamics.inputs_for_study(self.simFeaturePy):
            if not hasattr(initial, "InitialVelocityType"):
                continue
            item = QtWidgets.QListWidgetItem(self.inputLabel(initial))
            item.setData(QtCore.Qt.UserRole, initial.Name)
            self.form.initialVelocityList.addItem(item)
        self.updateInitialVelocityButton()

    def onContactsChanged(self):
        self.form.contactList.clear()
        for contact in Dynamics.inputs_for_study(self.simFeaturePy):
            if not hasattr(contact, "ContactType"):
                continue
            item = QtWidgets.QListWidgetItem(self.inputLabel(contact))
            item.setData(QtCore.Qt.UserRole, contact.Name)
            self.form.contactList.addItem(item)

    def onFrictionsChanged(self):
        self.form.frictionList.clear()
        for friction in Dynamics.inputs_for_study(self.simFeaturePy):
            if not hasattr(friction, "FrictionModel"):
                continue
            item = QtWidgets.QListWidgetItem(self.inputLabel(friction))
            item.setData(QtCore.Qt.UserRole, friction.Name)
            self.form.frictionList.addItem(item)

    @staticmethod
    def inputLabel(obj):
        suffix = translate("Assembly", " (global)") if Dynamics.is_global_input(obj) else ""
        if getattr(obj, "Suppressed", False):
            suffix += translate("Assembly", " (suppressed)")
        return obj.Label + suffix

    def updateInitialVelocityButton(self):
        if not hasattr(self.form, "AddInitialVelocityButton"):
            return
        import CommandCreateInitialVelocity

        self.form.AddInitialVelocityButton.setEnabled(
            bool(CommandCreateInitialVelocity._eligible_components(self.simFeaturePy))
        )

    RESULT_QUANTITIES = {
        "Bodies": (
            ("Position", "Placements", "mm"),
            ("Linear velocity", "Velocity", "mm/s"),
            ("Linear acceleration", "Acceleration", "mm/s²"),
            ("Angular velocity", "AngularVelocity", "rad/s"),
            ("Angular acceleration", "AngularAcceleration", "rad/s²"),
            ("Translational kinetic energy", "TranslationalKineticEnergy", "mJ"),
            ("Rotational kinetic energy", "RotationalKineticEnergy", "mJ"),
            ("Gravitational potential energy", "GravitationalPotentialEnergy", "mJ"),
            ("Mechanical energy", "MechanicalEnergy", "mJ"),
        ),
        "JointReactions": (
            ("Reaction force", "Force", "N"),
            ("Reaction moment", "Torque", "N mm"),
            ("Constraint or actuator power", "Power", "mW"),
            ("Constraint or actuator work", "Work", "mJ"),
        ),
        "Loads": (
            ("Force", "Force", "N"),
            ("Torque", "Torque", "N mm"),
            ("Power delivered", "Power", "mW"),
            ("Stored energy", "StoredEnergy", "mJ"),
            ("Dissipated power", "DissipatedPower", "mW"),
            ("Work delivered", "Work", "mJ"),
            ("Dissipated energy", "DissipatedEnergy", "mJ"),
        ),
        "Limits": (
            ("Power delivered", "Power", "mW"),
            ("Stored energy", "StoredEnergy", "mJ"),
            ("Dissipated power", "DissipatedPower", "mW"),
            ("Dissipated energy", "DissipatedEnergy", "mJ"),
        ),
        "Energy": (
            ("Translational kinetic energy", "TranslationalKineticEnergy", "mJ"),
            ("Rotational kinetic energy", "RotationalKineticEnergy", "mJ"),
            ("Total kinetic energy", "KineticEnergy", "mJ"),
            ("Gravitational potential energy", "GravitationalPotentialEnergy", "mJ"),
            ("Stored elastic energy", "StoredEnergy", "mJ"),
            ("Total mechanical energy", "MechanicalEnergy", "mJ"),
            ("External power", "ExternalPower", "mW"),
            ("Dissipated power", "DissipatedPower", "mW"),
            ("External work", "ExternalWork", "mJ"),
            ("Dissipated energy", "DissipatedEnergy", "mJ"),
            ("Energy balance residual", "EnergyBalanceResidual", "mJ"),
        ),
    }

    def addPointMeasurement(self):
        import CommandPointMeasurement
        CommandPointMeasurement.edit(self.simFeaturePy)

    def editPointMeasurement(self, item):
        obj = self.doc.getObject(item.data(QtCore.Qt.UserRole))
        if obj:
            obj.ViewObject.Proxy.doubleClicked(obj.ViewObject)

    def refreshResults(self):
        import CommandSimulationEvent
        CommandSimulationEvent.refresh_tab(self)
        self.pointMeasurementButton.setEnabled(bool(self.resultData))
        self.measurementList.clear()
        for obj in self.simFeaturePy.Group:
            if getattr(obj, "IsPointMeasurement", False):
                item = QtWidgets.QListWidgetItem(obj.Label)
                item.setData(QtCore.Qt.UserRole, obj.Name)
                self.measurementList.addItem(item)
        self.measurementList.setVisible(self.measurementList.count() > 0)
        category_combo = self.form.ResultCategoryComboBox
        previous = category_combo.currentData()
        category_combo.blockSignals(True)
        category_combo.clear()
        labels = {
            "Bodies": translate("Assembly", "Component motion"),
            "JointReactions": translate("Assembly", "Joint reactions"),
            "Loads": translate("Assembly", "Loads"),
            "Limits": translate("Assembly", "Contacts and compliant stops"),
            "Energy": translate("Assembly", "Energy and power"),
        }
        if self.resultData:
            for key in ("Bodies", "JointReactions", "Loads", "Limits", "Energy"):
                if self.resultData.get(key):
                    category_combo.addItem(labels[key], key)
        if previous:
            index = category_combo.findData(previous)
            if index >= 0:
                category_combo.setCurrentIndex(index)
        category_combo.blockSignals(False)
        available = category_combo.count() > 0
        self.form.NoResultsLabel.setVisible(not available)
        for widget in (
            self.form.ResultCategoryLabel,
            category_combo,
            self.form.ResultEntityLabel,
            self.form.ResultEntityComboBox,
            self.form.ResultQuantityLabel,
            self.form.ResultQuantityComboBox,
            self.form.ResultTable,
            self.form.PlotResultButton,
            self.form.ExportResultButton,
        ):
            widget.setVisible(available)
        if available:
            self.onResultCategoryChanged(category_combo.currentIndex())
        else:
            self.form.ResultTable.clear()
            self.form.ResultTable.setRowCount(0)

    def resultEntityLabel(self, key):
        candidates = (key, key.rsplit("#", 1)[-1], key.rsplit("/", 1)[-1])
        for name in candidates:
            obj = self.doc.getObject(name)
            if obj:
                return obj.Label
        return key

    def onResultCategoryChanged(self, _index):
        category = self.form.ResultCategoryComboBox.currentData()
        entity_combo = self.form.ResultEntityComboBox
        quantity_combo = self.form.ResultQuantityComboBox
        entity_combo.blockSignals(True)
        quantity_combo.blockSignals(True)
        entity_combo.clear()
        quantity_combo.clear()
        if category and self.resultData:
            for key in self.resultData.get(category, {}):
                entity_combo.addItem(self.resultEntityLabel(key), key)
            entities = self.resultData.get(category, {})
            first = next(iter(entities.values()), {})
            for label, key, unit in self.RESULT_QUANTITIES[category]:
                if key in first or key + "X" in first:
                    quantity_combo.addItem(translate("Assembly", label), (key, unit))
        entity_combo.blockSignals(False)
        quantity_combo.blockSignals(False)
        self.onResultSelectionChanged()

    def resultVectors(self):
        if not self.resultData:
            return [], [], "", ""
        category = self.form.ResultCategoryComboBox.currentData()
        entity = self.form.ResultEntityComboBox.currentData()
        quantity_data = self.form.ResultQuantityComboBox.currentData()
        if not category or not entity or not quantity_data:
            return [], [], "", ""
        quantity, unit = quantity_data
        data = self.resultData[category][entity]
        if category in ("Bodies", "Energy", "Limits") or quantity not in ("Force", "Torque"):
            vectors = data[quantity]
            if quantity == "Placements":
                vectors = [value[:3] for value in vectors]
            elif vectors and not isinstance(vectors[0], (list, tuple)):
                vectors = [(value,) for value in vectors]
        else:
            vectors = [
                tuple(values)
                for values in zip(
                    data[quantity + "X"],
                    data[quantity + "Y"],
                    data[quantity + "Z"],
                )
            ]
        return self.resultData["Times"], vectors, unit, entity

    def onResultSelectionChanged(self, *_args):
        times, vectors, unit, _entity = self.resultVectors()
        table = self.form.ResultTable
        headers = [translate("Assembly", "Time (s)")]
        scalar = bool(vectors) and len(vectors[0]) == 1
        if scalar:
            headers.append(f"{translate('Assembly', 'Value')} ({unit})")
        else:
            headers.extend(f"{axis} ({unit})" for axis in ("X", "Y", "Z"))
            headers.append(f"{translate('Assembly', 'Magnitude')} ({unit})")
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(times))
        for row, (sample_time, vector) in enumerate(zip(times, vectors)):
            values = (sample_time, *vector)
            if not scalar:
                values += (sum(component * component for component in vector) ** 0.5,)
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(f"{value:.9g}")
                item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        enabled = bool(times)
        self.form.PlotResultButton.setEnabled(enabled)
        self.form.ExportResultButton.setEnabled(enabled)

    def resultTableData(self):
        table = self.form.ResultTable
        headers = [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ]
        rows = [
            [table.item(row, column).text() for column in range(table.columnCount())]
            for row in range(table.rowCount())
        ]
        return headers, rows

    def plotResult(self):
        times, vectors, unit, entity = self.resultVectors()
        if not times:
            return
        try:
            import Plot
        except ImportError as error:
            QtWidgets.QMessageBox.warning(
                self.form, translate("Assembly", "Plot unavailable"), str(error)
            )
            return
        quantity = self.form.ResultQuantityComboBox.currentText()
        figure = Plot.figure(f"{self.resultEntityLabel(entity)} — {quantity}")
        if figure is None:
            return
        if len(vectors[0]) == 1:
            figure.plot(times, [value[0] for value in vectors], quantity)
        else:
            for axis, values in zip("XYZ", zip(*vectors)):
                figure.plot(times, values, axis)
            magnitudes = [sum(value * value for value in vector) ** 0.5 for vector in vectors]
            figure.plot(times, magnitudes, translate("Assembly", "Magnitude"))
        figure.axes.set_xlabel(translate("Assembly", "Time (s)"))
        for firing in (self.resultData or {}).get("EventLog", []):
            figure.axes.axvline(firing["Time"], color="0.5", linestyle="--", linewidth=0.8)
        figure.axes.set_ylabel(f"{quantity} ({unit})")
        figure.axes.grid(True)
        figure.legend = True
        figure.update()

    def exportResult(self):
        headers, rows = self.resultTableData()
        if not rows:
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self.form,
            translate("Assembly", "Export Simulation Result"),
            "",
            translate("Assembly", "CSV files (*.csv)"),
        )
        if not filename:
            return
        if not filename.lower().endswith(".csv"):
            filename += ".csv"
        with open(filename, "w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)

    def runKinematics(self):
        self.animationTimer.stop()
        self.form.groupBox_player.hide()
        self.form.SaveAnimationButton.hide()
        # Playback must never become the input pose of the next run.
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initialPlcs)
        try:
            self.resultData = Dynamics.run(self.simFeaturePy)
        except Exception as error:
            self.clearResultPreview()
            QtWidgets.QMessageBox.warning(self.form, translate("Assembly", "Simulation failed"), str(error))
            return
        self.configurePlayback()
        self.setFrameValue(self.form.frameSlider.maximum())
        self.refreshResults()

    def onFrameChanged(self, val):
        if not self.resultData or self.simFeaturePy.Status != "Complete":
            return
        index = val - 1
        if not 0 <= index < len(self.resultData.get("Times", [])):
            return
        # Play the study's saved snapshot, not the assembly's shared solver cache
        # (which may belong to another study or be absent after reopening a file).
        for name, body in self.resultData.get("Bodies", {}).items():
            component = self.doc.getObject(name)
            if component is not None and hasattr(component, "Placement"):
                pose = body["Placements"][index]
                parent = Dynamics.component_placement(component) * component.Placement.inverse()
                component.Placement = parent.inverse() * App.Placement(
                    App.Vector(*pose[:3]), App.Rotation(*pose[3:])
                )
        for child in Dynamics.inputs_for_study(self.simFeaturePy):
            if hasattr(child, "LoadType") and child.ViewObject.Proxy:
                child.ViewObject.Proxy.updateVisual(child)
            if hasattr(child, "InitialVelocityType") and child.ViewObject.Proxy:
                child.ViewObject.Proxy.updateVisual(child)
        self.form.FrameLabel.setText(translate("Assembly", "Frame" + " " + str(val)))
        sample_time = self.frameTimes[val]
        self.form.FrameTimeLabel.setText(f"{sample_time:.6g} s")

    def onFramesPerSecondChanged(self):
        self.simFeaturePy.jFramesPerSecond = self.form.FramesPerSecondSpinBox.value()
        Dynamics.purge_touched(self.simFeaturePy)

    def playBackward(self):
        pass

    def animationTimerStartForward(self):
        self.direction = 1
        self.animationTimerStart()

    def animationTimerStartBackward(self):
        self.direction = -1
        self.animationTimerStart()

    def animationTimerStart(self):
        self.animationTimer.stop()
        if not self.resultData or self.simFeaturePy.Status != "Complete":
            return
        self.currentFrm = self.form.frameSlider.value()
        self.startFrm = 1
        self.endFrm = self.form.frameSlider.maximum()
        if self.startFrm >= self.endFrm:
            return

        self.fps = self.simFeaturePy.jFramesPerSecond
        self.deltaTime = 1.0 / self.fps
        self.startTime = time.time()
        self.index = self.currentFrm
        self.animationTimer.setInterval(self.deltaTime * 1000)  # ms
        self.animationTimer.start()

    def playAnimation(self):
        range_ = self.endFrm - self.startFrm + 1
        offset = self.currentFrm - self.startFrm
        count = int((time.time() - self.startTime) / self.deltaTime)
        self.index = ((self.direction * count + offset) % range_) + self.startFrm
        self.setFrameValue(self.index)

    def displayLastFrame(self):
        self.setFrameValue(self.form.frameSlider.maximum())

    def stepBackward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() - 1
        if nextFrm < 1:
            nextFrm = self.form.frameSlider.maximum()  # wraparound
        self.setFrameValue(nextFrm)

    def stepForward(self):
        self.animationTimer.stop()

        nextFrm = self.form.frameSlider.value() + 1
        if nextFrm > self.form.frameSlider.maximum():
            nextFrm = 1  # wraparound
        self.setFrameValue(nextFrm)

    def setFrameValue(self, val):
        if val < 1:
            val = 1
        if val > self.form.frameSlider.maximum():
            val = self.form.frameSlider.maximum()

        if val == self.form.frameSlider.value():
            self.onFrameChanged(val)
        else:
            self.form.frameSlider.setValue(val)

    def stopAnimation(self):
        self.animationTimer.stop()

    def addMotionClicked(self):
        Gui.runCommand("Assembly_CreateMotion")

    def addLoadClicked(self):
        Gui.runCommand("Assembly_CreateLoad")

    def addInitialVelocityClicked(self):
        Gui.runCommand("Assembly_CreateInitialVelocity")

    def addContactClicked(self):
        Gui.runCommand("Assembly_CreateContact")

    def addFrictionClicked(self):
        Gui.runCommand("Assembly_CreateFriction")

    # Taskbox keyboard event handler
    def eventFilter(self, watched, event):
        if self.form is not None and watched in (
            self.form.motionList,
            self.form.loadList,
            self.form.initialVelocityList,
            self.form.contactList,
            self.form.frictionList,
        ):
            if event.type() == QtCore.QEvent.ShortcutOverride:
                if event.key() == QtCore.Qt.Key_Delete:
                    event.accept()
                    return True  # Indicate that the event has been handled
                return False

            elif event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Delete:
                    if watched == self.form.motionList:
                        self.deleteSelectedMotions()
                    elif watched == self.form.loadList:
                        self.deleteSelectedLoads()
                    elif watched == self.form.contactList:
                        self.deleteSelectedContacts()
                    elif watched == self.form.frictionList:
                        self.deleteSelectedFrictions()
                    else:
                        self.deleteSelectedInitialVelocities()
                    return True  # Consume the event

        return super().eventFilter(watched, event)

    def deleteSelectedMotions(self):
        if not self.confirmInputDeletion(self.form.motionList):
            return
        selected_indexes = self.form.motionList.selectedIndexes()
        sorted_indexes = sorted(selected_indexes, key=lambda x: x.row(), reverse=True)
        for index in sorted_indexes:
            row = index.row()
            item = self.form.motionList.item(row)
            motion = self.doc.getObject(item.data(QtCore.Qt.UserRole)) if item else None
            if motion:
                motion.Document.removeObject(motion.Name)
        self.onMotionsChanged()
        self.invalidateResult()

    def deleteSelectedLoads(self):
        if not self.confirmInputDeletion(self.form.loadList):
            return
        selected = [
            self.doc.getObject(item.data(QtCore.Qt.UserRole))
            for item in self.form.loadList.selectedItems()
        ]
        for load in selected:
            if load:
                load.Document.removeObject(load.Name)
        self.onLoadsChanged()
        self.invalidateResult()

    def deleteSelectedInitialVelocities(self):
        if not self.confirmInputDeletion(self.form.initialVelocityList):
            return
        selected = [
            self.doc.getObject(item.data(QtCore.Qt.UserRole))
            for item in self.form.initialVelocityList.selectedItems()
        ]
        for initial in selected:
            if initial:
                initial.Document.removeObject(initial.Name)
        self.onInitialVelocitiesChanged()
        self.invalidateResult()

    def deleteSelectedContacts(self):
        if not self.confirmInputDeletion(self.form.contactList):
            return
        selected = [
            self.doc.getObject(item.data(QtCore.Qt.UserRole))
            for item in self.form.contactList.selectedItems()
        ]
        for contact in selected:
            if contact:
                contact.Document.removeObject(contact.Name)
        self.onContactsChanged()
        self.invalidateResult()

    def deleteSelectedFrictions(self):
        if not self.confirmInputDeletion(self.form.frictionList):
            return
        selected = [
            self.doc.getObject(item.data(QtCore.Qt.UserRole))
            for item in self.form.frictionList.selectedItems()
        ]
        for friction in selected:
            if friction:
                friction.Document.removeObject(friction.Name)
        self.onFrictionsChanged()
        self.invalidateResult()

    def confirmInputDeletion(self, widget):
        global_inputs = [
            obj for item in widget.selectedItems()
            if (obj := self.doc.getObject(item.data(QtCore.Qt.UserRole)))
            and Dynamics.is_global_input(obj)
        ]
        if not global_inputs:
            return True
        answer = QtWidgets.QMessageBox.question(
            self.form,
            translate("Assembly", "Delete global simulation inputs?"),
            translate("Assembly", "These global inputs will be deleted from the assembly and every simulation that uses them, not just this simulation:\n\n")
            + "\n".join(obj.Label for obj in global_inputs),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return answer == QtWidgets.QMessageBox.Yes

    def invalidateResult(self):
        Dynamics.invalidate_study(self.simFeaturePy)
        self.clearResultPreview()
        Dynamics.purge_touched(self.simFeaturePy)

    def clearResultPreview(self):
        self.animationTimer.stop()
        self.runKinematicsTimer.stop()
        self.resultData = None
        self.configurePlayback()
        self.refreshResults()

    def syncResults(self):
        if self.simFeaturePy.Status != "Complete" or not self.simFeaturePy.ResultData:
            self.clearResultPreview()
            return
        try:
            self.resultData = Dynamics.results(self.simFeaturePy)
        except ValueError:
            self.clearResultPreview()
            return
        self.configurePlayback()
        self.refreshResults()

    def configurePlayback(self):
        times = self.resultData.get("Times", []) if self.resultData else []
        self.frameTimes = dict(enumerate(times, 1))
        blocker = QtCore.QSignalBlocker(self.form.frameSlider)
        self.form.frameSlider.setRange(1, max(1, len(times)))
        del blocker
        self.form.groupBox_player.setVisible(bool(times))
        self.form.SaveAnimationButton.setVisible(len(times) > 1)
        if times:
            frame = self.form.frameSlider.value()
            self.form.FrameLabel.setText(translate("Assembly", "Frame") + f" {frame}")
            self.form.FrameTimeLabel.setText(f"{self.frameTimes[frame]:.6g} s")

    def saveAnimation(self):
        self.animationTimer.stop()
        num_frames = len(self.resultData.get("Times", [])) if self.resultData and self.simFeaturePy.Status == "Complete" else 0
        if num_frames <= 1:
            QMessageBox.warning(
                self.form,
                translate("Assembly", "Animation"),
                translate("Assembly", "Not enough frames to create an animation."),
            )
            return

        formats = {
            "MP4 Video": ".mp4",
            "Animated GIF": ".gif",
            "AVI Video": ".avi",
        }

        try:
            import av

            # 05/26 libvpx has no Windows conda package
            if "libvpx-vp9" in av.codecs_available:
                formats["WebM Video"] = ".webm"
        except ImportError:
            pass  # Error out later

        # Prompt user for file location and type
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self.form,
            translate("Assembly", "Save Animation"),
            "",
            ";;".join(f"{k} (*{v})" for k, v in formats.items()),
        )

        if not file_path:
            return  # User cancelled

        # Get parameters
        view = Gui.ActiveDocument.ActiveView
        width, height = view.getSize()

        # Ensure dimensions are even, as required by many video codecs
        width -= width % 2
        height -= height % 2

        fps = self.form.FramesPerSecondSpinBox.value()

        # Fail early when PIL is not installed
        try:
            from PIL import Image
        except ImportError:
            errMsg = translate(
                "Assembly", "Pillow (PIL) is not installed. It is required for video export."
            )
            QMessageBox.critical(self.form, "Error", errMsg)
            return

        # Setup temporary directory and progress bar
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            progress = QProgressDialog(
                translate("Assembly", "Generating Frames…"),
                translate("Assembly", "Cancel"),
                0,
                num_frames,
                self.form,
            )
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            original_frame = self.form.frameSlider.value()

            try:
                # Generate and save all frames as temporary images
                frame_files = []
                for i in range(num_frames):
                    progress.setValue(i)
                    if progress.wasCanceled():
                        App.Console.PrintMessage("Animation save cancelled.\n")
                        return

                    self.setFrameValue(i + 1)
                    Gui.updateGui()  # Ensure the 3D view is redrawn

                    frame_filename = temp_path / f"frame_{i:05d}.png"
                    view.saveImage(str(frame_filename), width, height, "Current")
                    frame_files.append(str(frame_filename))

                # Assemble the final animation file
                progress.setLabelText(translate("Assembly", "Assembling animation…"))
                progress.setMaximum(0)  # Indeterminate progress

                success = False
                file_extension = Path(file_path).suffix.lower()
                if not file_extension:
                    file_extension = [
                        filter for filter in formats.values() if filter in selected_filter
                    ][0]
                    file_path += file_extension

                if file_extension == ".gif":
                    success = self.create_gif(file_path, frame_files, fps)
                elif file_extension in [".mp4", ".avi", ".webm"]:
                    success = self.create_video(file_path, frame_files, fps, (width, height))

                if success:
                    App.Console.PrintMessage(f"Animation successfully saved to {file_path}\n")

            except Exception as e:
                errMsg = (
                    translate("Assembly", "An error occurred while saving the animation")
                    + ": "
                    + str(e)
                )
                QMessageBox.critical(self.form, "Error", errMsg)
            finally:
                progress.close()
                # Restore original state
                self.setFrameValue(original_frame)
                self.form.frameSlider.setValue(original_frame)

    def create_gif(self, output_path, frame_files, fps):
        """Creates an animated GIF from a list of image files using Pillow."""
        from PIL import Image

        pil_images = [Image.open(f) for f in frame_files]
        duration_ms = int(1000 / fps)
        pil_images[0].save(
            output_path,
            save_all=True,
            append_images=pil_images[1:],
            optimize=True,
            duration=duration_ms,
            loop=0,  # 0 means loop forever
        )
        return True

    def create_video(
        self, output_path: str, frame_files: list[str], fps: int, size: tuple[int, int]
    ):
        """Creates a video file from a list of image files using PyAV."""
        try:
            import av
        except ImportError:
            errMsg = translate(
                "Assembly", "PyAv is not installed. It is required for video export."
            )
            QMessageBox.critical(self.form, "Error", errMsg)
            return False

        file_extension = Path(output_path).suffix.lower()

        # Select codec based on file type
        with av.open(output_path, "w") as output:
            stream = None
            if file_extension == ".mp4":
                try:
                    stream = output.add_stream("libx264", fps)
                except av.codec.codec.UnknownCodecError:
                    stream = output.add_stream("mpeg4", fps)
            elif file_extension == ".avi":
                stream = output.add_stream("mpeg4", fps)
            elif file_extension == ".webm":
                stream = output.add_stream("libvpx-vp9", fps)
            else:
                errMsg = translate("Assembly", "Unknown video export format")
                QMessageBox.critical(self.form, "Error", errMsg)
                return False

            stream.width, stream.height = size

            from PIL import Image
            import numpy as np

            for file in frame_files:
                img = Image.open(file).convert("RGB")
                frame = av.VideoFrame.from_ndarray(np.array(img), format="rgb24")
                packet = stream.encode(frame)
                output.mux(packet)

            # Flush & write
            packet = stream.encode(None)
            output.mux(packet)

        return True


if App.GuiUp:
    Gui.addCommand("Assembly_CreateSimulation", CommandCreateSimulation())
    Gui.addCommand("Assembly_CreateMotion", CommandCreateMotion())
