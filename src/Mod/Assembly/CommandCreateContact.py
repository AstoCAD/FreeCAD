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

"""Create and edit assembly-wide or simulation-local contact pairs."""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from PySide.QtCore import QT_TRANSLATE_NOOP

import CommandCreateSimulation
import Dynamics
import UtilsAssembly


translate = App.Qt.translate


def _contact_owner(contact):
    return Dynamics.input_owner(contact)


def _assembly_for_owner(owner):
    return Dynamics.assembly_for_owner(owner)


def _show_task(contact, owner, resume_simulation=None):
    panel = TaskAssemblyCreateContact(contact, owner, resume_simulation)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(contact.Document.Name)


def editContact(contact):
    owner = _contact_owner(contact)
    assembly = _assembly_for_owner(owner)
    if owner is None or assembly is None:
        return False

    simulation_task = CommandCreateSimulation.activeSimulationTask()
    resume_simulation = None
    if simulation_task is not None:
        resume_simulation = simulation_task.suspendForChildTask()
    elif Gui.Control.activeTaskDialog():
        Gui.Control.activeTaskDialog().reject()

    if UtilsAssembly.activeAssembly() != assembly:
        Gui.ActiveDocument.setEdit(assembly)
    if contact.Document.getBookedTransactionID() == 0:
        Gui.ActiveDocument.openCommand("Edit " + contact.Label)
    _show_task(contact, owner, resume_simulation)
    return True


class CommandCreateContact:
    def GetResources(self):
        return {
            "Pixmap": "Assembly_CreateContact",
            "MenuText": QT_TRANSLATE_NOOP("Assembly", "Add Contact"),
            "ToolTip": QT_TRANSLATE_NOOP(
                "Assembly",
                "Creates shape contact between components, component sets, or across the assembly. "
                "Contacts created while "
                "editing a simulation apply only to that simulation; otherwise they apply "
                "to assembly dragging and every simulation.",
            ),
            "CmdType": "ForEdit",
        }

    def IsActive(self):
        simulation_task = CommandCreateSimulation.activeSimulationTask()
        if simulation_task is None and not UtilsAssembly.isAssemblyCommandActive():
            return False
        assembly = simulation_task.assembly if simulation_task else UtilsAssembly.activeAssembly()
        if assembly is None or len(assembly.getComponents()) < 2:
            return False
        return not Gui.Control.activeDialog() or simulation_task is not None

    def Activated(self):
        assembly = UtilsAssembly.activeAssembly()
        if assembly is None:
            return
        components = list(assembly.getComponents())
        if len(components) < 2:
            return

        selected = [obj for obj in Gui.Selection.getSelection() if obj in components]
        first = selected[0] if selected else components[0]
        second = next((obj for obj in selected[1:] if obj != first), None)
        if second is None:
            second = next(obj for obj in components if obj != first)

        simulation_task = CommandCreateSimulation.activeSimulationTask()
        resume_simulation = None
        if simulation_task is not None:
            owner = simulation_task.suspendForChildTask()
            resume_simulation = owner
        else:
            owner = assembly

        Gui.ActiveDocument.openCommand("Add Contact")
        contact = Dynamics.create_contact(owner, first, second)
        owner = Dynamics.input_owner(contact)
        _show_task(contact, owner, resume_simulation)


class ViewProviderContact:
    def __init__(self, view_object):
        if not view_object.hasExtension("Gui::ViewProviderSuppressibleExtensionPython"):
            view_object.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        view_object.Proxy = self

    def getIcon(self):
        return ":/icons/Assembly_CreateContact.svg"

    def doubleClicked(self, view_object):
        contact = view_object.Object
        QtCore.QTimer.singleShot(0, lambda: editContact(contact))
        return True

    def onDelete(self, view_object, _subelements):
        Dynamics.invalidate_contact_results(view_object.Object)
        return True

    def dumps(self):
        return None

    def loads(self, _state):
        return None


class TaskAssemblyCreateContact:
    def __init__(self, contact, owner, resume_simulation=None):
        self.contact = contact
        self.owner = owner
        self.resume_simulation = resume_simulation
        self.assembly = _assembly_for_owner(owner)
        self.components = list(self.assembly.getComponents())
        self._updating = True

        self.form = Gui.PySideUic.loadUi(":/panels/TaskAssemblyCreateContact.ui")
        self.form.setWindowIcon(Gui.getIcon("Assembly_CreateContact"))
        self.form.ModeComboBox.addItems(
            [translate("Assembly", mode) for mode in Dynamics.Contact.MODES]
        )
        mode_tip = translate("Assembly", "Check one pair, every assembly pair, all pairs between sets A and B, or all pairs within one set. Self-pairs and duplicate pairs are ignored. Set membership does not make components rigid.")
        self.form.ModeComboBox.setToolTip(mode_tip)
        self.form.ModeLabel.setToolTip(mode_tip)
        self.form.ModeComboBox.setCurrentIndex(
            Dynamics.Contact.MODES.index(contact.Mode)
        )
        for component in self.components:
            self.form.FirstComponentComboBox.addItem(component.Label, component.Name)
            self.form.SecondComponentComboBox.addItem(component.Label, component.Name)
        if contact.ComponentI in self.components:
            self.form.FirstComponentComboBox.setCurrentIndex(
                self.components.index(contact.ComponentI)
            )
        if contact.ComponentJ in self.components:
            self.form.SecondComponentComboBox.setCurrentIndex(
                self.components.index(contact.ComponentJ)
            )
        self.form.StiffnessSpinBox.setProperty("value", contact.Stiffness)
        self.form.DampingSpinBox.setProperty("value", contact.Damping)
        self.form.FrictionGroupBox.setChecked(contact.FrictionEnabled)
        self.form.StaticFrictionSpinBox.setValue(contact.StaticFriction)
        self.form.DynamicFrictionSpinBox.setValue(contact.DynamicFriction)
        self.form.TransitionVelocitySpinBox.setProperty(
            "value", contact.FrictionTransitionVelocity
        )
        self.form.ScopeValueLabel.setText(
            translate("Assembly", "This simulation")
            if isinstance(getattr(owner, "Proxy", None), Dynamics.Study)
            else translate("Assembly", "Assembly (dragging and all simulations)")
        )
        self.createGroupWidgets()
        self.updateModeWidgets()
        self._updating = False

        self.form.ModeComboBox.currentIndexChanged.connect(self.onModeChanged)
        self.form.FirstComponentComboBox.currentIndexChanged.connect(
            self.onFirstComponentChanged
        )
        self.form.SecondComponentComboBox.currentIndexChanged.connect(
            self.onSecondComponentChanged
        )
        self.form.StiffnessSpinBox.valueChanged.connect(self.onStiffnessChanged)
        self.form.DampingSpinBox.valueChanged.connect(self.onDampingChanged)
        self.form.FrictionGroupBox.toggled.connect(self.onFrictionToggled)
        self.form.StaticFrictionSpinBox.valueChanged.connect(self.onStaticFrictionChanged)
        self.form.DynamicFrictionSpinBox.valueChanged.connect(self.onDynamicFrictionChanged)
        self.form.TransitionVelocitySpinBox.valueChanged.connect(
            self.onTransitionVelocityChanged
        )
        Dynamics.purge_touched(owner, contact)

    def updateModeWidgets(self):
        general = self.contact.Mode == Dynamics.Contact.MODES[1]
        pair = self.contact.Mode == Dynamics.Contact.MODES[0]
        for widget in (
            self.form.FirstComponentLabel,
            self.form.FirstComponentComboBox,
            self.form.SecondComponentLabel,
            self.form.SecondComponentComboBox,
        ):
            widget.setEnabled(pair)
            widget.setVisible(pair)
        self.form.GeneralWarningLabel.setVisible(general)
        grouped = self.contact.Mode in Dynamics.Contact.MODES[2:]
        self.groupWidget.setVisible(grouped)
        self.exclusionWidget.setVisible(not pair)
        self.pairCount.setVisible(not pair)
        within = self.contact.Mode == Dynamics.Contact.MODES[3]
        self.members.setColumnHidden(2, within)
        self.addSelectionB.setVisible(not within)
        self.addSelectionA.setText(translate("Assembly", "Add selection" if within else "Add selection to A"))
        self.members.headerItem().setText(1, translate("Assembly", "Member" if within else "Set A"))
        self.refreshPairCount()

    def createGroupWidgets(self):
        self.groupWidget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.groupWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText(translate("Assembly", "Filter components"))
        layout.addWidget(self.filter)
        self.members = QtWidgets.QTreeWidget()
        self.members.setHeaderLabels([translate("Assembly", value) for value in ("Component", "Set A", "Set B")])
        self.members.setRootIsDecorated(False)
        self.members.setMaximumHeight(200)
        self.members.setMinimumHeight(100)
        layout.addWidget(self.members)
        for component in self.components:
            item = QtWidgets.QTreeWidgetItem([component.Label, "", ""])
            item.setData(0, QtCore.Qt.UserRole, component.Name)
            item.setToolTip(0, component.Name)
            for column, name in ((1, "ComponentsI"), (2, "ComponentsJ")):
                item.setCheckState(column, QtCore.Qt.Checked if component in getattr(self.contact, name) else QtCore.Qt.Unchecked)
            self.members.addTopLevelItem(item)
        self.members.header().setStretchLastSection(False)
        self.members.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.members.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.members.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.members.itemChanged.connect(self.onMembersChanged)
        self.filter.textChanged.connect(self.filterMembers)
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        self.addSelectionA = QtWidgets.QPushButton(translate("Assembly", "Add selection to A"))
        self.addSelectionB = QtWidgets.QPushButton(translate("Assembly", "Add selection to B"))
        buttons.addWidget(self.addSelectionA)
        buttons.addWidget(self.addSelectionB)
        self.addSelectionA.clicked.connect(lambda: self.useSelection(1))
        self.addSelectionB.clicked.connect(lambda: self.useSelection(2))
        self.form.formLayout.insertRow(5, self.groupWidget)
        self.pairCount = QtWidgets.QLabel()
        self.pairCount.setWordWrap(True)
        self.pairCount.setToolTip(translate("Assembly", "Candidate pairs after removing self-pairs, duplicates and this definition's exclusions. Fixed components and members of the same rigid group may reduce the solver count further. If definitions overlap, the first active contact supplies the response; forces are not added twice."))
        self.form.formLayout.insertRow(6, self.pairCount)
        self.exclusionWidget = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(self.exclusionWidget)
        outer.setContentsMargins(0, 0, 0, 0)
        self.exclusions = QtWidgets.QToolButton()
        self.exclusions.setText(translate("Assembly", "Excluded pairs"))
        self.exclusions.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.exclusions.setCheckable(True)
        self.exclusions.setChecked(bool(self.contact.ExcludedPairs))
        self.exclusions.setArrowType(QtCore.Qt.DownArrow if self.exclusions.isChecked() else QtCore.Qt.RightArrow)
        outer.addWidget(self.exclusions)
        self.exclusionContent = QtWidgets.QWidget()
        outer.addWidget(self.exclusionContent)
        el = QtWidgets.QVBoxLayout(self.exclusionContent)
        el.setContentsMargins(0, 0, 0, 0)
        hint = QtWidgets.QLabel(translate("Assembly", "Exclusions apply only to this contact definition. Another contact may still include the same pair."))
        hint.setWordWrap(True)
        el.addWidget(hint)
        self.exclusionList = QtWidgets.QListWidget()
        self.exclusionList.setMaximumHeight(90)
        el.addWidget(self.exclusionList)
        row = QtWidgets.QHBoxLayout()
        el.addLayout(row)
        self.excludeI, self.excludeJ = QtWidgets.QComboBox(), QtWidgets.QComboBox()
        for widget in (self.excludeI, self.excludeJ):
            for component in self.components:
                widget.addItem(component.Label, component.Name)
            row.addWidget(widget)
        self.excludeJ.setCurrentIndex(min(1, len(self.components)-1))
        row = QtWidgets.QHBoxLayout()
        el.addLayout(row)
        for title, callback in (("Exclude pair", self.addExclusion), ("Remove exclusion", self.removeExclusion)):
            button = QtWidgets.QPushButton(translate("Assembly", title))
            button.clicked.connect(callback)
            row.addWidget(button)
        self.exclusionContent.setVisible(self.exclusions.isChecked())
        self.exclusions.toggled.connect(self.exclusionContent.setVisible)
        self.exclusions.toggled.connect(lambda expanded: self.exclusions.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow))
        self.exclusions.setToolTip(translate("Assembly", "Expand or collapse the pair list. Collapsing does not disable exclusions."))
        self.form.formLayout.insertRow(7, self.exclusionWidget)
        self.refreshExclusions()

    def refreshPairCount(self):
        try:
            count = len(Dynamics.contact_pairs(self.contact))
            self.pairCount.setText(translate("Assembly", "Candidate pairs: {count}").format(count=count))
        except ValueError as error:
            self.pairCount.setText(str(error))

    def filterMembers(self, text):
        for row in range(self.members.topLevelItemCount()):
            item = self.members.topLevelItem(row)
            item.setHidden(text.casefold() not in (item.text(0) + " " + item.data(0, QtCore.Qt.UserRole)).casefold())

    def onMembersChanged(self, _item=None, _column=0):
        if self._updating:
            return
        for column, name in ((1, "ComponentsI"), (2, "ComponentsJ")):
            values = [self.contact.Document.getObject(self.members.topLevelItem(row).data(0, QtCore.Qt.UserRole))
                      for row in range(self.members.topLevelItemCount())
                      if self.members.topLevelItem(row).checkState(column) == QtCore.Qt.Checked]
            setattr(self.contact, name, values)
        self.invalidateResult()
        self.refreshPairCount()

    def useSelection(self, column):
        selected = set()
        for entry in Gui.Selection.getSelectionEx():
            if entry.Object in self.components:
                selected.add(entry.Object.Name)
            else:
                for path in entry.SubElementNames or [""]:
                    component, _ = UtilsAssembly.getComponentReference(self.assembly, entry.Object, path)
                    if component in self.components:
                        selected.add(component.Name)
        self._updating = True
        for row in range(self.members.topLevelItemCount()):
            item = self.members.topLevelItem(row)
            if item.data(0, QtCore.Qt.UserRole) in selected:
                item.setCheckState(column, QtCore.Qt.Checked)
        self._updating = False
        self.onMembersChanged()

    def refreshExclusions(self):
        self.exclusionList.clear()
        for a, b in Dynamics.contact_exclusions(self.contact):
            item = QtWidgets.QListWidgetItem(a.Label + " — " + b.Label)
            item.setData(QtCore.Qt.UserRole, (a.Name, b.Name))
            self.exclusionList.addItem(item)
        self.refreshPairCount()

    def addExclusion(self):
        a = self.contact.Document.getObject(self.excludeI.currentData())
        b = self.contact.Document.getObject(self.excludeJ.currentData())
        if a and b and a != b:
            Dynamics.set_contact_exclusions(self.contact, Dynamics.contact_exclusions(self.contact) + [(a, b)])
            self.refreshExclusions()

    def removeExclusion(self):
        row = self.exclusionList.currentRow()
        if row >= 0:
            pairs = Dynamics.contact_exclusions(self.contact)
            del pairs[row]
            Dynamics.set_contact_exclusions(self.contact, pairs)
            self.refreshExclusions()

    def onModeChanged(self, index):
        if self._updating or not 0 <= index < len(Dynamics.Contact.MODES):
            return
        self.contact.Mode = Dynamics.Contact.MODES[index]
        if index == 0:
            # Set-based contacts need not have pair links. Commit the displayed
            # selections when entering pair mode, choosing a distinct second
            # component when both selectors initially show the first item.
            first = self.form.FirstComponentComboBox.currentIndex()
            second = self.form.SecondComponentComboBox.currentIndex()
            if first == second and len(self.components) > 1:
                second = (first + 1) % len(self.components)
            self._updating = True
            try:
                self.form.SecondComponentComboBox.setCurrentIndex(second)
                self.contact.ComponentI = self.components[first] if first >= 0 else None
                self.contact.ComponentJ = self.components[second] if second >= 0 else None
            finally:
                self._updating = False
        self.updateModeWidgets()
        self.invalidateResult()

    def onFirstComponentChanged(self, index):
        if self._updating or not 0 <= index < len(self.components):
            return
        self.contact.ComponentI = self.components[index]
        if self.contact.ComponentI == self.contact.ComponentJ:
            self._updating = True
            other = (index + 1) % len(self.components)
            self.form.SecondComponentComboBox.setCurrentIndex(other)
            self.contact.ComponentJ = self.components[other]
            self._updating = False
        self.invalidateResult()
        self.refreshPairCount()

    def onSecondComponentChanged(self, index):
        if self._updating or not 0 <= index < len(self.components):
            return
        self.contact.ComponentJ = self.components[index]
        if self.contact.ComponentI == self.contact.ComponentJ:
            self._updating = True
            other = (index + 1) % len(self.components)
            self.form.FirstComponentComboBox.setCurrentIndex(other)
            self.contact.ComponentI = self.components[other]
            self._updating = False
        self.invalidateResult()
        self.refreshPairCount()

    def onStiffnessChanged(self, _value):
        if not self._updating:
            self.contact.Stiffness = self.form.StiffnessSpinBox.property("value")
            self.invalidateResult()

    def onDampingChanged(self, _value):
        if not self._updating:
            self.contact.Damping = self.form.DampingSpinBox.property("value")
            self.invalidateResult()

    def onFrictionToggled(self, enabled):
        if self._updating:
            return
        self.contact.FrictionEnabled = enabled
        self.invalidateResult()

    def onStaticFrictionChanged(self, value):
        if not self._updating:
            self.contact.StaticFriction = value
            if value < self.form.DynamicFrictionSpinBox.value():
                self._updating = True
                self.form.DynamicFrictionSpinBox.setValue(value)
                self.contact.DynamicFriction = value
                self._updating = False
            self.invalidateResult()

    def onDynamicFrictionChanged(self, value):
        if not self._updating:
            self.contact.DynamicFriction = value
            if value > self.form.StaticFrictionSpinBox.value():
                self._updating = True
                self.form.StaticFrictionSpinBox.setValue(value)
                self.contact.StaticFriction = value
                self._updating = False
            self.invalidateResult()

    def onTransitionVelocityChanged(self, _value):
        if not self._updating:
            self.contact.FrictionTransitionVelocity = (
                self.form.TransitionVelocitySpinBox.property("value")
            )
            self.invalidateResult()

    def invalidateResult(self):
        if isinstance(getattr(self.owner, "Proxy", None), Dynamics.Study):
            self.owner.ResultData = ""
            self.owner.Status = "NotRun"
            self.owner.LastError = ""
        Dynamics.purge_touched(self.owner, self.contact)

    def accept(self):
        try:
            Dynamics.contact_pairs(self.contact)
        except ValueError as error:
            QtWidgets.QMessageBox.warning(self.form, translate("Assembly", "Invalid contact"), str(error))
            return False
        Dynamics.purge_touched(self.owner, self.contact)
        Gui.ActiveDocument.commitCommand()
        self.reopenSimulation()
        return True

    def reject(self):
        Gui.ActiveDocument.abortCommand()
        self.reopenSimulation()
        return True

    def reopenSimulation(self):
        if self.resume_simulation:
            simulation = self.resume_simulation
            QtCore.QTimer.singleShot(
                0,
                lambda: CommandCreateSimulation.TaskAssemblyCreateSimulation.reopen(
                    simulation, "contactsTab"
                ),
            )


Gui.addCommand("Assembly_CreateContact", CommandCreateContact())
