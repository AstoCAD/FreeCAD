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

"""Simulation-local event task, using the same suspend/resume workflow as loads."""
import json

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

import Dynamics
import SimulationEvents as Events

translate = App.Qt.translate


def edit(study, event=None):
    import CommandCreateSimulation as Simulation
    task = Simulation.activeSimulationTask()
    if task:
        task.suspendForChildTask()
    elif Gui.Control.activeTaskDialog():
        Gui.Control.activeTaskDialog().reject()
    Gui.ActiveDocument.openCommand("Edit Event" if event else "Add Event")
    if event is None:
        event = Events.create(study)
        ViewProvider(event.ViewObject)
    panel = Task(study, event)
    dialog = Gui.Control.showDialog(panel)
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(study.Document.Name)


class ViewProvider:
    def __init__(self, view):
        view.addExtension("Gui::ViewProviderSuppressibleExtensionPython")
        view.Proxy = self

    def getIcon(self):
        return ":/icons/Assembly_CreateSimulation.svg"

    def doubleClicked(self, view):
        study = Dynamics.input_owner(view.Object)
        if not Dynamics.is_study(study):
            return False
        QtCore.QTimer.singleShot(0, lambda: edit(study, view.Object))
        return True

    def dumps(self):
        return None

    def loads(self, state):
        pass


def combo(values, selected=None):
    widget = QtWidgets.QComboBox()
    for label, data in values:
        widget.addItem(label, data)
    widget.setCurrentIndex(max(0, widget.findData(selected)))
    return widget


def spin(value, minimum=-1e12):
    widget = QtWidgets.QDoubleSpinBox()
    widget.setRange(minimum, 1e12)
    widget.setDecimals(6)
    widget.setValue(float(value))
    return widget


class Task:
    def __init__(self, study, event):
        self.study, self.event = study, event
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(translate("Assembly", "Event"))
        self.form.setWindowIcon(Gui.getIcon("Assembly_CreateSimulation"))
        self.form.setMinimumWidth(460)
        layout = QtWidgets.QVBoxLayout(self.form)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.name = QtWidgets.QLineEdit(event.Label)
        form.addRow(translate("Assembly", "Name"), self.name)
        self.trigger = combo([(translate("Assembly", v), v) for v in Events.Event.TRIGGERS], event.Trigger)
        form.addRow(translate("Assembly", "When"), self.trigger)
        self.time = spin(event.Time)
        self.time.setSuffix(" s")
        form.addRow(translate("Assembly", "Time"), self.time)
        self.previous = combo([(v.Label, v) for v in Events.events(study) if v != event and not v.Suppressed], event.PreviousEvent)
        form.addRow(translate("Assembly", "After event"), self.previous)
        self.delay = spin(event.Delay, 0)
        self.delay.setSuffix(" s")
        form.addRow(translate("Assembly", "Delay"), self.delay)
        self.measurement = QtWidgets.QGroupBox(translate("Assembly", "Measurement"))
        mf = QtWidgets.QFormLayout(self.measurement)
        layout.addWidget(self.measurement)
        components = [(obj.Label, obj) for obj in study.Assembly.getComponents()]
        self.component = combo(components, event.Component)
        self.reference = combo([(translate("Assembly", "Assembly frame"), None)] + components, event.ReferenceComponent)
        self.filterReferences()
        self.component.currentIndexChanged.connect(self.filterReferences)
        self.quantity = combo([(translate("Assembly", v), v) for v in Events.Event.QUANTITIES], event.Quantity)
        mf.addRow(translate("Assembly", "Component"), self.component)
        mf.addRow(translate("Assembly", "Relative to"), self.reference)
        self.point = App.Vector(event.Point)
        self.pointButton = QtWidgets.QPushButton()
        self.updatePoint()
        self.pointButton.setToolTip(translate("Assembly", "Select a vertex, datum point or coordinate system in the 3D view, then click to use it. With no selection, use the component origin. The selected link occurrence is preserved."))
        self.pointButton.clicked.connect(self.selectPoint)
        self.component.currentIndexChanged.connect(self.resetPoint)
        mf.addRow(translate("Assembly", "Point"), self.pointButton)
        mf.addRow(translate("Assembly", "Quantity"), self.quantity)
        self.threshold = spin(event.Threshold)
        self.rising = combo([(translate("Assembly", "Crosses above"), True), (translate("Assembly", "Crosses below"), False)], event.Rising)
        mf.addRow(self.rising, self.threshold)
        self.advanced = QtWidgets.QGroupBox(translate("Assembly", "Repeat / initial condition"))
        af = QtWidgets.QFormLayout(self.advanced)
        layout.addWidget(self.advanced)
        self.repeat = QtWidgets.QCheckBox(translate("Assembly", "Repeat after rearming"))
        self.repeat.setChecked(event.Repeat)
        af.addRow(self.repeat)
        self.hysteresis = spin(event.Hysteresis, 0)
        self.hysteresis.setToolTip(translate("Assembly", "Before a repeated crossing can fire, the measurement must return to the opposite side by this amount. Use a nonzero value to avoid chatter near the threshold."))
        af.addRow(translate("Assembly", "Hysteresis"), self.hysteresis)
        self.initial = QtWidgets.QCheckBox(translate("Assembly", "Fire if already satisfied at start"))
        self.initial.setChecked(event.FireInitially)
        af.addRow(self.initial)
        layout.addWidget(QtWidgets.QLabel(translate("Assembly", "Then perform these actions:")))
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([translate("Assembly", v) for v in ("Action", "Target", "Value", "Ramp (s)")])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        for text, callback in (("Add action", self.addAction), ("Remove action", self.removeAction)):
            button = QtWidgets.QPushButton(translate("Assembly", text))
            button.clicked.connect(callback)
            buttons.addWidget(button)
        self.hint = QtWidgets.QLabel(translate("Assembly", "Actions affect this run only. Deactivating a motion releases its axis; it does not stop the component. Ramp changes motor velocity (mm/s or rad/s), or load magnitude (N or N mm). Start profile restarts the target's saved profile at the event time, preserving the current motor position."))
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        for target, action in zip(event.Targets, json.loads(event.Actions)):
            self.addAction(action=action, target=target)
        self.trigger.currentIndexChanged.connect(self.updateUi)
        self.quantity.currentIndexChanged.connect(self.updateUi)
        self._formLayout = form
        self.updateUi()
        self.initialValues = self.values()

    def updatePoint(self):
        self.pointButton.setText("({:.4g}, {:.4g}, {:.4g}) mm — ".format(*self.point) + translate("Assembly", "Use selection"))

    def filterReferences(self):
        selected = self.reference.currentData()
        self.reference.clear()
        self.reference.addItem(translate("Assembly", "Assembly frame"), None)
        for component in self.study.Assembly.getComponents():
            if component != self.component.currentData():
                self.reference.addItem(component.Label, component)
        self.reference.setCurrentIndex(max(0, self.reference.findData(selected)))

    def resetPoint(self):
        self.point = App.Vector()
        self.updatePoint()

    def selectPoint(self):
        import PointMeasurement
        try:
            selected = Gui.Selection.getSelectionEx()
            if not selected:
                self.resetPoint()
                return
            selection = selected[0]
            component, subname = PointMeasurement.resolve_reference(self.study.Assembly, selection.Object, selection.SubElementNames[0] if selection.SubElementNames else "")
            point = PointMeasurement.local_frame((component, [subname]), point=True).Base
            self.component.setCurrentIndex(self.component.findData(component))
            self.point = point
            self.updatePoint()
            self.message.clear()
        except ValueError as error:
            self.message.setText(str(error))

    def updateUi(self):
        trigger = self.trigger.currentData()
        for widget, visible in ((self.time, trigger == "Time"), (self.previous, trigger == "After event"), (self.delay, trigger == "After event")):
            widget.setVisible(visible)
            self._formLayout.labelForField(widget).setVisible(visible)
        self.measurement.setVisible(trigger == "Measurement")
        self.advanced.setVisible(trigger != "Time")
        self.hysteresis.setVisible(trigger == "Measurement")
        self.advanced.layout().labelForField(self.hysteresis).setVisible(trigger == "Measurement")
        self.initial.setVisible(trigger == "Measurement")
        self.advanced.setTitle(translate("Assembly", "Repeat" if trigger == "After event" else "Repeat / initial condition"))
        self.repeat.setText(translate("Assembly", "Repeat for each occurrence" if trigger == "After event" else "Repeat after rearming"))
        unit = " mm/s" if self.quantity.currentData() == "Speed" else " mm"
        self.threshold.setSuffix(unit)
        self.hysteresis.setSuffix(unit)

    def addAction(self, checked=False, action=None, target=None):
        action = action or {"kind": "Activate", "value": 0, "duration": 0.1}
        row = self.table.rowCount()
        self.table.insertRow(row)
        kind = combo([(translate("Assembly", v), v) for v in Events.Event.ACTIONS], action["kind"])
        objects = QtWidgets.QComboBox()
        objects.setPlaceholderText(translate("Assembly", "Select a target"))
        selected_target = target
        value, duration = spin(action.get("value", 0)), spin(action.get("duration", 0.1), 0.000001)
        for col, widget in enumerate((kind, objects, value, duration)):
            self.table.setCellWidget(row, col, widget)
        def refresh():
            ramp = kind.currentData() == "Ramp"
            value.setEnabled(ramp)
            duration.setEnabled(ramp)
            obj = objects.currentData()
            unit = ("rad/s" if obj.MotionType == "Angular" else "mm/s") if obj and hasattr(obj, "MotionType") else ("N mm" if obj and obj.LoadType == "Torque" else "N")
            value.setSuffix(" " + unit)
        def filterTargets():
            nonlocal selected_target
            if objects.currentData() is not None:
                selected_target = objects.currentData()
            objects.blockSignals(True)
            objects.clear()
            for obj in Dynamics.inputs_for_study(self.study):
                if not (hasattr(obj, "MotionType") or hasattr(obj, "LoadType")):
                    continue
                action_kind = kind.currentData()
                if action_kind in ("Ramp", "Start profile"):
                    if hasattr(obj, "LoadType") and obj.LoadType not in ("Force", "Torque"):
                        continue
                if action_kind == "Start profile" and not getattr(obj, "ProfileData", ""):
                    continue
                label = obj.Label + (translate("Assembly", " (global)") if Dynamics.is_global_input(obj) else "")
                objects.addItem(label, obj)
            objects.setCurrentIndex(objects.findData(selected_target))
            objects.blockSignals(False)
            objects.setToolTip(translate("Assembly", "Select an eligible target. Start profile requires a saved motion, force or torque profile; unavailable targets are not replaced automatically.") if objects.currentIndex() < 0 else "")
            refresh()
        kind.currentIndexChanged.connect(filterTargets)
        objects.currentIndexChanged.connect(refresh)
        filterTargets()

    def removeAction(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def values(self):
        trigger = self.trigger.currentData()
        values = dict(Label=self.name.text(), Trigger=trigger)
        if trigger == "Time":
            values["Time"] = self.time.value()
        else:
            values["Repeat"] = self.repeat.isChecked()
        if trigger == "After event":
            values.update(PreviousEvent=self.previous.currentData(), Delay=self.delay.value())
        elif trigger == "Measurement":
            values.update(Component=self.component.currentData(), ReferenceComponent=self.reference.currentData(),
                          Point=App.Vector(self.point), Quantity=self.quantity.currentData(),
                          Threshold=self.threshold.value(), Rising=self.rising.currentData(),
                          Hysteresis=self.hysteresis.value(), FireInitially=self.initial.isChecked())
        targets, actions = [], []
        for row in range(self.table.rowCount()):
            targets.append(self.table.cellWidget(row, 1).currentData())
            actions.append(dict(kind=self.table.cellWidget(row, 0).currentData(), value=self.table.cellWidget(row, 2).value(), duration=self.table.cellWidget(row, 3).value()))
        values.update(Targets=targets, Actions=json.dumps(actions, allow_nan=False))
        return values

    def accept(self):
        obj = self.event
        values = self.values()
        if any(target is None for target in values["Targets"]):
            self.message.setText(translate("Assembly", "Select a motion or load for each action."))
            return False
        if values["Trigger"] == "After event" and values["PreviousEvent"] is None:
            self.message.setText(translate("Assembly", "Select an unsuppressed preceding event."))
            return False
        # Compare with the initial widget values, not rounded floats against
        # full-precision document properties. Unedited fields stay untouched.
        previous_values = {}
        previous_guard = getattr(obj.Proxy, "_validating_edit", False)
        obj.Proxy._validating_edit = True
        try:
            for prop, value in values.items():
                if prop not in self.initialValues or value != self.initialValues[prop]:
                    previous_values[prop] = getattr(obj, prop)
                    setattr(obj, prop, value)
            Events.describe(self.study)
        except (ValueError, TypeError) as error:
            for prop, value in previous_values.items():
                setattr(obj, prop, value)
            self.message.setText(str(error))
            return False
        finally:
            obj.Proxy._validating_edit = previous_guard
        # Failed candidates are restored above without discarding the saved
        # run. Only a successfully validated physical edit invalidates results.
        if any(prop != "Label" for prop in previous_values):
            Dynamics.invalidate_results(obj)
        Dynamics.purge_touched(obj, self.study)
        Gui.ActiveDocument.commitCommand()
        self.finish()
        return True

    def reject(self):
        Gui.ActiveDocument.abortCommand()
        self.finish()
        return True

    def finish(self):
        Gui.Control.closeDialog()
        import CommandCreateSimulation as Simulation
        QtCore.QTimer.singleShot(0, lambda: Simulation.TaskAssemblyCreateSimulation.reopen(self.study, "eventsTab"))


def add_tab(task):
    page = QtWidgets.QWidget()
    task.form.eventsTab = page
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    task.eventList = QtWidgets.QListWidget()
    layout.addWidget(task.eventList)
    row = QtWidgets.QHBoxLayout()
    layout.addLayout(row)
    add = QtWidgets.QPushButton(Gui.getIcon("list-add"), translate("Assembly", "Add event"))
    remove = QtWidgets.QPushButton(Gui.getIcon("list-remove"), translate("Assembly", "Remove"))
    row.addWidget(add)
    row.addWidget(remove)
    task.form.tabWidget.insertTab(task.form.tabWidget.indexOf(task.form.resultsTab), page, Gui.getIcon("Assembly_CreateSimulation"), translate("Assembly", "Events"))
    add.clicked.connect(lambda: edit(task.simFeaturePy))
    task.eventList.itemDoubleClicked.connect(lambda item: edit(task.simFeaturePy, task.simFeaturePy.Document.getObject(item.data(QtCore.Qt.UserRole))))
    def erase():
        item = task.eventList.currentItem()
        if item:
            task.simFeaturePy.Document.removeObject(item.data(QtCore.Qt.UserRole))
            task.invalidateResult()
            refresh_tab(task)
    remove.clicked.connect(erase)
    def seek(item):
        time = item.data(QtCore.Qt.UserRole + 1)
        if time is not None and task.resultData:
            index = min(range(len(task.resultData["Times"])), key=lambda i: abs(task.resultData["Times"][i]-time))
            task.setFrameValue(index+1)
    task.eventList.itemClicked.connect(seek)


def refresh_tab(task):
    task.eventList.clear()
    data = getattr(task, "resultData", None)
    log = data.get("EventLog", []) if data else []
    for obj in Events.events(task.simFeaturePy):
        times = [entry["Time"] for entry in log if entry["Event"] == obj.Name]
        status = translate("Assembly", "Suppressed") if obj.Suppressed else (
            ", ".join(f"{time:.6g} s" for time in times) if times else translate("Assembly", "Not triggered" if data else "Not generated")
        )
        item = QtWidgets.QListWidgetItem(f"{obj.Label} — {status}")
        item.setData(QtCore.Qt.UserRole, obj.Name)
        item.setData(QtCore.Qt.UserRole + 1, times[0] if times else None)
        task.eventList.addItem(item)
