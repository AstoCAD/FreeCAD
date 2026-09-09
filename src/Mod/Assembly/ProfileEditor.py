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

"""Shared modal motor/load profile editor and compact task-panel field."""

import copy
import csv
import io
import json
import math

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

import MotionProfile as MP

tr = App.Qt.translate


def combo(items, parent=None):
    widget = QtWidgets.QComboBox(parent)
    for item in items:
        widget.addItem(tr("Assembly", item), item)
    return widget


def spin(value=0.0):
    widget = QtWidgets.QDoubleSpinBox()
    widget.setRange(-1e12, 1e12)
    widget.setDecimals(9)
    widget.setValue(value)
    return widget


def units(obj):
    if hasattr(obj, "MotionType"):
        return ["rad", "deg"] if obj.MotionType == "Angular" else ["mm", "m"]
    return ["N"] if obj.LoadType == "Force" else ["N mm", "N m"]


class ProfilePlot(QtWidgets.QWidget):
    """Dependency-free preview of the actual compiled input, not solver output."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.profile = None
        self.order = 0
        self.cursor = None

    def setProfile(self, profile, order=0):
        self.profile, self.order = profile, order
        self.update()

    def mouseMoveEvent(self, event):
        self.cursor = event.position().x()
        self.update()

    def leaveEvent(self, event):
        self.cursor = None
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        rect = QtCore.QRectF(60, 15, max(1, self.width()-78), max(1, self.height()-50))
        painter.setPen(self.palette().text().color())
        painter.drawRect(rect)
        if not self.profile:
            painter.drawText(rect, QtCore.Qt.AlignCenter, tr("Assembly", "Enter a valid profile to preview"))
            return
        p = self.profile
        times = [p.start + (p.end-p.start)*i/300 for i in range(301)]
        values = [p.sample(t, self.order)/MP.scale(p.spec) for t in times]
        low, high = min(values), max(values)
        margin = max((high-low)*0.05, abs(high)*0.01, 1e-6)
        low, high = low-margin, high+margin
        painter.drawText(2, 22, f"{high:.4g}")
        painter.drawText(2, int(rect.bottom()), f"{low:.4g}")
        painter.drawText(int(rect.left()), self.height()-8, f"{p.start:.4g} s")
        painter.drawText(int(rect.right())-65, self.height()-8, f"{p.end:.4g} s")
        path = QtGui.QPainterPath()
        for i, v in enumerate(values):
            point = QtCore.QPointF(rect.left()+rect.width()*i/300, rect.bottom()-rect.height()*(v-low)/(high-low))
            if i: path.lineTo(point)
            else: path.moveTo(point)
        painter.setPen(QtGui.QPen(self.palette().highlight().color(), 2))
        painter.drawPath(path)
        if self.cursor is not None:
            fraction = min(1, max(0, (self.cursor-rect.left())/rect.width()))
            t = p.start + fraction*(p.end-p.start)
            x = rect.left()+fraction*rect.width()
            painter.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            painter.drawText(int(rect.left()+6), 30, f"t = {t:.6g} s, value = {p.sample(t,self.order)/MP.scale(p.spec):.6g}")


class ProfileDialog(QtWidgets.QDialog):
    def __init__(self, spec, allowed_units, motion, parent=None):
        super().__init__(parent)
        self.spec = copy.deepcopy(spec)
        self.motion = motion
        self.loading = True
        self.profile = None
        self.setWindowTitle(tr("Assembly", "Edit profile"))
        self.setWindowIcon(Gui.getIcon("Assembly_CreateSimulation"))
        self.setModal(True)
        self.resize(780, 740)
        self.setMinimumSize(620, 540)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.mode = combo(["Constant", "Segments", "Data points", "Expression"])
        self.mode.setCurrentIndex(self.mode.findData(spec["mode"]))
        form.addRow(tr("Assembly", "Definition"), self.mode)
        self.quantity = combo(["Position", "Velocity", "Acceleration"] if motion else ["Magnitude"])
        self.quantity.setCurrentIndex(self.quantity.findData(spec["quantity"]))
        form.addRow(tr("Assembly", "Prescribe"), self.quantity)
        self.quantity.setVisible(motion)
        form.labelForField(self.quantity).setVisible(motion)
        self.unit = combo(allowed_units)
        self.unit.setCurrentIndex(self.unit.findData(spec["unit"]))
        form.addRow(tr("Assembly", "Base unit (time in seconds)"), self.unit)
        self.start, self.end = spin(spec["start"]), spin(spec["end"])
        self.start.setSuffix(" s")
        self.end.setSuffix(" s")
        self.startLabel, self.endLabel = QtWidgets.QLabel(tr("Assembly", "Start time")), QtWidgets.QLabel(tr("Assembly", "End time"))
        form.addRow(self.startLabel, self.start)
        form.addRow(self.endLabel, self.end)
        self.initial = spin(spec["initial"])
        self.initialLabel = QtWidgets.QLabel(tr("Assembly", "Initial value"))
        form.addRow(self.initialLabel, self.initial)
        self.position, self.velocity = spin(spec["initial_position"]), spin(spec["initial_velocity"])
        self.positionLabel = QtWidgets.QLabel(tr("Assembly", "Initial position"))
        self.velocityLabel = QtWidgets.QLabel(tr("Assembly", "Initial velocity"))
        self.position.setToolTip(tr("Assembly", "Position at profile start. In this editor, initialValue means this explicit value, not a value reevaluated from the joint during each run."))
        self.velocity.setToolTip(tr("Assembly", "Velocity at profile start when prescribing acceleration."))
        form.addRow(self.positionLabel, self.position)
        form.addRow(self.velocityLabel, self.velocity)
        self.outside = combo(["Hold endpoint", "Repeat", "Require coverage"])
        self.outside.setCurrentIndex(self.outside.findData(spec["outside"]))
        self.outside.setToolTip(tr("Assembly", "Hold endpoint holds the prescribed quantity: holding velocity means continued travel. Repeat repeats the input cycle. Require coverage rejects simulations extending outside this profile."))
        form.addRow(tr("Assembly", "Outside time range"), self.outside)
        self.expression = QtWidgets.QLineEdit(spec["expression"])
        self.expression.setPlaceholderText("10*sin(2*pi*t)")
        self.expression.setToolTip(tr("Assembly", "Time t (or time) is in seconds. Use + - * / ^, sin, cos, exp and pi. Values use the selected units. Velocity/acceleration expressions must have an analytic integral supported by the editor."))
        layout.addWidget(self.expression)
        self.table = QtWidgets.QTableWidget()
        self.table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.contextMenu)
        layout.addWidget(self.table)
        self.tableButtons = QtWidgets.QWidget()
        buttons = QtWidgets.QHBoxLayout(self.tableButtons)
        buttons.setContentsMargins(0, 0, 0, 0)
        for title, callback in (("Add", self.addRow), ("Remove", self.removeRows),
                                ("Paste", self.paste), ("Import CSV…", self.importCsv)):
            button = QtWidgets.QPushButton(tr("Assembly", title))
            button.clicked.connect(callback)
            buttons.addWidget(button)
            if title == "Paste": self.pasteButton = button
            if title == "Import CSV…": self.importButton = button
        self.interpolation = combo(["Cubic spline", "Linear"])
        self.interpolation.setCurrentIndex(self.interpolation.findData(spec["interpolation"]))
        buttons.addWidget(self.interpolation)
        layout.addWidget(self.tableButtons)
        self.graphTabs = QtWidgets.QTabBar()
        for title in (["Position", "Velocity", "Acceleration", "Jerk"] if motion else ["Magnitude"]):
            self.graphTabs.addTab(tr("Assembly", title))
        layout.addWidget(self.graphTabs)
        self.graph = ProfilePlot()
        layout.addWidget(self.graph)
        self.graphUnits = QtWidgets.QLabel()
        layout.addWidget(self.graphUnits)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.mode.currentIndexChanged.connect(self.changeMode)
        self.unit.currentIndexChanged.connect(self.changeUnit)
        for widget in (self.quantity, self.outside, self.interpolation): widget.currentIndexChanged.connect(self.refresh)
        for widget in (self.start, self.end, self.initial, self.position, self.velocity): widget.valueChanged.connect(self.refresh)
        self.expression.textChanged.connect(self.refresh)
        self.table.itemChanged.connect(self.refresh)
        self.graphTabs.currentChanged.connect(self.updateGraph)
        self.fillTable()
        self.loading = False
        self.refresh()

    def fillTable(self):
        mode = self.mode.currentData()
        blocker = QtCore.QSignalBlocker(self.table)
        self.table.clear()
        segments = mode == "Segments"
        self.table.setColumnCount(4 if segments else 2)
        self.table.setHorizontalHeaderLabels([tr("Assembly", h) for h in (
            ["Duration (s)", "End value", "Transition", "End time (s)"] if segments else ["Time (s)", "Value"])])
        rows = self.spec["segments"] if segments else self.spec["points"]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j in range(2): self.table.setItem(i, j, QtWidgets.QTableWidgetItem(f"{row[j]:.12g}"))
            if segments:
                transition = combo(["Hold", "Linear", "Smooth"])
                transition.setCurrentIndex(transition.findData(row[2]))
                transition.setToolTip(tr("Assembly", "Smooth uses a quintic transition with zero slope and curvature at both ends. For position this means zero endpoint velocity and acceleration. Hold keeps the preceding value."))
                transition.currentIndexChanged.connect(self.refresh)
                self.table.setCellWidget(i, 2, transition)
                item = QtWidgets.QTableWidgetItem()
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table.setItem(i, 3, item)
        del blocker

    def readTable(self):
        rows = []
        for i in range(self.table.rowCount()):
            row = [MP.number(self.table.item(i, j).text()) for j in range(2)]
            if self.mode.currentData() == "Segments": row.append(self.table.cellWidget(i, 2).currentData())
            rows.append(row)
        return rows

    def collect(self):
        result = copy.deepcopy(self.spec)
        for key, widget in (("mode", self.mode), ("quantity", self.quantity), ("unit", self.unit),
                            ("outside", self.outside), ("interpolation", self.interpolation)):
            result[key] = widget.currentData()
        for key, widget in (("start", self.start), ("end", self.end), ("initial", self.initial),
                            ("initial_position", self.position), ("initial_velocity", self.velocity)):
            result[key] = widget.value()
        result["expression"] = self.expression.text()
        if result["mode"] in ("Segments", "Data points"):
            result["segments" if result["mode"] == "Segments" else "points"] = self.readTable()
        return result

    def changeMode(self):
        self.loading = True
        self.fillTable()
        self.loading = False
        self.refresh()

    def changeUnit(self):
        if self.loading: return
        old = MP.scale(self.spec)
        current = dict(self.spec, unit=self.unit.currentData())
        ratio = old / MP.scale(current)
        self.loading = True
        old_expression = self.expression.text().replace("initialValue", f"({self.position.value():.17g})")
        for widget in (self.initial, self.position, self.velocity): widget.setValue(widget.value()*ratio)
        for key in ("segments", "points"):
            for row in self.spec[key]: row[1] *= ratio
        self.expression.setText(f"({old_expression})*{ratio:.17g}")
        self.spec["unit"] = self.unit.currentData()
        self.fillTable()
        self.loading = False
        self.refresh()

    def refresh(self, *_args):
        if self.loading: return
        mode, quantity = self.mode.currentData(), self.quantity.currentData()
        table = mode in ("Segments", "Data points")
        self.table.setVisible(table)
        self.tableButtons.setVisible(table)
        self.pasteButton.setVisible(mode == "Data points")
        self.importButton.setVisible(mode == "Data points")
        self.interpolation.setVisible(mode == "Data points")
        self.expression.setVisible(mode == "Expression")
        for widget in (self.start, self.startLabel): widget.setVisible(mode != "Data points")
        for widget in (self.end, self.endLabel): widget.setVisible(mode in ("Constant", "Expression"))
        for widget in (self.initial, self.initialLabel): widget.setVisible(mode in ("Constant", "Segments"))
        for widget in (self.position, self.positionLabel): widget.setVisible(self.motion and (quantity != "Position" or mode == "Expression"))
        for widget in (self.velocity, self.velocityLabel): widget.setVisible(quantity == "Acceleration")
        self.initialLabel.setText(tr("Assembly", "Value" if mode == "Constant" else "Initial value"))
        power = {"Position": 0, "Velocity": 1, "Acceleration": 2, "Magnitude": 0}[quantity]
        unit = self.unit.currentData()
        suffix = unit + (f"/s^{power}" if power > 1 else "/s" if power else "")
        self.initial.setSuffix(" " + suffix)
        self.position.setSuffix(" " + unit)
        self.velocity.setSuffix(" " + unit + "/s")
        try:
            if mode == "Segments":
                blocker = QtCore.QSignalBlocker(self.table)
                previous = self.initial.value()
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, 1)
                    hold = self.table.cellWidget(row, 2).currentData() == "Hold"
                    if hold:
                        item.setText(f"{previous:.12g}")
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
                    previous = MP.number(item.text())
                del blocker
            spec = self.collect()
            profile = MP.Profile(spec)
            self.spec, self.profile = spec, profile
            self.message.setText("\n".join(profile.warnings))
            if mode == "Segments":
                blocker = QtCore.QSignalBlocker(self.table)
                time = self.start.value()
                for row, segment in enumerate(spec["segments"]):
                    time += segment[0]
                    self.table.item(row, 3).setText(f"{time:.9g}")
                del blocker
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
            self.profile = None
            self.message.setText(str(error))
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(self.profile is not None)
        self.updateGraph()

    def updateGraph(self, *_args):
        order = self.graphTabs.currentIndex()
        self.graph.setProfile(self.profile, order)
        unit = self.unit.currentData()
        self.graphUnits.setText(tr("Assembly", "Input preview — ") + unit + (f"/s^{order}" if order > 1 else "/s" if order else ""))

    def addRow(self, *_args, index=None):
        try: rows = self.readTable()
        except ValueError: return
        if index is None: index = len(rows)
        if self.mode.currentData() == "Segments":
            value = rows[index-1][1] if index else self.initial.value()
            rows.insert(index, [1.0, value, "Hold"])
            self.spec["segments"] = rows
        else:
            time = rows[index-1][0]+1 if index else 0
            if index < len(rows): time = (time-1+rows[index][0])/2
            rows.insert(index, [time, rows[index-1][1] if index else 0])
            self.spec["points"] = rows
        self.fillTable()
        self.refresh()

    def removeRows(self):
        selected = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in selected: self.table.removeRow(row)
        self.refresh()

    def contextMenu(self, point):
        menu = QtWidgets.QMenu(self)
        insert = menu.addAction(tr("Assembly", "Insert row above"))
        delete = menu.addAction(tr("Assembly", "Remove selected rows"))
        action = menu.exec(self.table.viewport().mapToGlobal(point))
        if action == insert: self.addRow(index=max(0, self.table.rowAt(point.y())))
        elif action == delete: self.removeRows()

    def paste(self):
        self.importText(QtWidgets.QApplication.clipboard().text(), False)

    def importCsv(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, tr("Assembly", "Import profile data"), "", "CSV (*.csv);;Text (*.txt);;All files (*)")
        if path:
            try:
                with open(path, encoding="utf-8-sig") as stream: data = stream.read(2_000_001)
                if len(data) > 2_000_000: raise ValueError("Profile import is limited to 2 MB.")
                self.importText(data, True)
            except (OSError, UnicodeError, ValueError) as error: self.message.setText(str(error))

    def importText(self, data, ask_units):
        try:
            if len(data) > 2_000_000: raise ValueError("Profile import is limited to 2 MB.")
            delimiter = "\t" if "\t" in data else ";" if ";" in data else ","
            rows = [row for row in csv.reader(io.StringIO(data), delimiter=delimiter) if row]
            time_factor, value_factor, time_col, value_col = 1.0, 1.0, 0, 1
            if ask_units:
                dialog = QtWidgets.QDialog(self)
                dialog.setWindowTitle(tr("Assembly", "Import columns and units"))
                form = QtWidgets.QFormLayout(dialog)
                time_column, value_column = QtWidgets.QSpinBox(), QtWidgets.QSpinBox()
                for widget in (time_column, value_column): widget.setRange(1, max(map(len, rows), default=2))
                value_column.setValue(2)
                time_unit = combo(["s", "ms"])
                value_unit = combo([self.unit.itemData(i) for i in range(self.unit.count())])
                value_unit.setCurrentText(self.unit.currentText())
                for label, widget in (("Time column", time_column), ("Value column", value_column),
                                      ("Time unit", time_unit), ("Value base unit", value_unit)):
                    form.addRow(tr("Assembly", label), widget)
                info = QtWidgets.QLabel(tr("Assembly", "Optional first header row is skipped. Numbers use a decimal point; rate values use seconds (for example deg/s)."))
                info.setWordWrap(True)
                form.addRow(info)
                buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
                buttons.accepted.connect(dialog.accept)
                buttons.rejected.connect(dialog.reject)
                form.addRow(buttons)
                if not dialog.exec(): return
                time_factor = 0.001 if time_unit.currentData() == "ms" else 1.0
                value_factor = MP.scale(dict(self.spec, unit=value_unit.currentData()))/MP.scale(self.spec)
                time_col, value_col = time_column.value()-1, value_column.value()-1
            points = []
            for index, row in enumerate(rows):
                try: x, y = float(row[time_col]), float(row[value_col])
                except ValueError:
                    # Only skip a genuine textual header; reject partially
                    # numeric first rows and non-finite numerical data.
                    if index == 0:
                        numeric = []
                        for column in (time_col, value_col):
                            try:
                                float(row[column])
                                numeric.append(True)
                            except ValueError:
                                numeric.append(False)
                        if not any(numeric):
                            continue
                    raise ValueError(f"Invalid number on row {index+1}.")
                point = [MP.number(x)*time_factor, MP.number(y)*value_factor]
                points.append(point)
            candidate = dict(self.spec, mode="Data points", points=points)
            MP.Profile(candidate)
            self.spec = candidate
            self.fillTable()
            self.refresh()
        except (ValueError, IndexError) as error: self.message.setText(str(error))


class ProfileField(QtWidgets.QWidget):
    """Uses existing scalar/formula controls for backwards-compatible editing."""
    def __init__(self, obj, formula_edit, parent=None, magnitude=None):
        super().__init__(parent)
        self.obj, self.formula_edit, self.magnitude = obj, formula_edit, magnitude
        self.motion = hasattr(obj, "MotionType")
        self.loading = True
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(tr("Assembly", "Profile")))
        self.mode = combo(["Constant", "Segments", "Data points", "Expression"])
        row.addWidget(self.mode, 1)
        self.editButton = QtWidgets.QPushButton(tr("Assembly", "Edit profile…"))
        row.addWidget(self.editButton)
        layout.addLayout(row)
        self.constant = spin()
        layout.addWidget(self.constant)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.preview = ProfilePlot()
        self.preview.setMinimumHeight(70)
        self.preview.setMaximumHeight(80)
        layout.addWidget(self.preview)
        self.mode.currentIndexChanged.connect(self.modeChanged)
        self.editButton.clicked.connect(self.edit)
        self.constant.valueChanged.connect(self.constantChanged)
        formula_edit.textChanged.connect(self.sync)
        self.loading = False
        self.sync()

    def definition(self):
        if getattr(self.obj, "ProfileData", ""):
            return json.loads(self.obj.ProfileData)
        spec = MP.defaults(units(self.obj)[0], "Expression" if self.obj.Formula else "Constant")
        if self.motion and self.obj.Joint:
            import UtilsAssembly
            joint = self.obj.Joint[0]
            first = UtilsAssembly.getGlobalPlacement(joint.Reference1) * joint.Placement1
            second = UtilsAssembly.getGlobalPlacement(joint.Reference2) * joint.Placement2
            relative = first.inverse() * second
            if self.obj.MotionType == "Angular":
                axis = relative.Rotation.multVec(App.Vector(1, 0, 0))
                initial = math.atan2(axis.y, axis.x)
            else:
                initial = (first.Base-second.Base).Length * (-1 if relative.Base.z < 0 else 1)
            spec["initial_position"] = initial
            spec["initial"] = initial
        elif not self.motion:
            spec["quantity"] = "Magnitude"
            prop = self.obj.Force if self.obj.LoadType == "Force" else self.obj.Torque
            spec["initial"] = prop.getValueAs("N" if self.obj.LoadType == "Force" else "N*mm").Value
        spec["expression"] = self.obj.Formula or "0"
        return spec

    def sync(self, *_args):
        if self.loading: return
        self.loading = True
        try:
            spec = self.definition()
            self.mode.setCurrentIndex(self.mode.findData(spec["mode"]))
            self.constant.setValue(spec["initial"])
            power = {"Position": 0, "Magnitude": 0, "Velocity": 1, "Acceleration": 2}[spec["quantity"]]
            suffix = "/s^2" if power == 2 else "/s" if power else ""
            self.constant.setSuffix(" " + spec["unit"] + suffix)
            saved_constant = spec["mode"] == "Constant" and bool(getattr(self.obj, "ProfileData", ""))
            self.constant.setVisible(spec["mode"] == "Constant" and (self.motion or saved_constant))
            self.formula_edit.setVisible(spec["mode"] == "Expression" and not getattr(self.obj, "ProfileData", ""))
            self.editButton.setVisible(spec["mode"] != "Constant" or self.motion)
            if self.magnitude:
                scalar = spec["mode"] == "Constant" and not saved_constant
                self.magnitude.setVisible(scalar)
                self.magnitude.setEnabled(scalar)
                label = self.magnitude.parentWidget().layout().labelForField(self.magnitude)
                if label:
                    label.setVisible(scalar)
            profile = MP.Profile(spec)
            self.preview.setProfile(profile)
            self.preview.setVisible(spec["mode"] != "Constant")
            self.summary.setText(tr("Assembly", spec["quantity"]) + f" — {spec['unit']}{suffix}, {profile.start:g}–{profile.end:g} s")
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as error:
            self.preview.setProfile(None)
            self.summary.setText(str(error))
        finally:
            self.loading = False

    def modeChanged(self):
        if self.loading: return
        mode = self.mode.currentData()
        if mode == "Constant":
            spec = self.definition()
            spec["mode"] = mode
            self.apply(spec)
        else:
            self.edit(mode)

    def contextChanged(self):
        if not self.motion and self.obj.LoadType not in ("Force", "Torque"):
            return
        spec = self.definition()
        if spec["unit"] not in units(self.obj):
            # Like an existing scalar/formula, retain the numerical definition
            # when the user changes the physical motion/load type.
            spec["unit"] = units(self.obj)[0]
            self.apply(spec)
        else:
            self.sync()

    def constantChanged(self):
        if self.loading: return
        spec = self.definition()
        spec["initial"] = self.constant.value()
        self.apply(spec)

    def apply(self, spec):
        MP.assign(self.obj, spec)
        blocker = QtCore.QSignalBlocker(self.formula_edit)
        self.formula_edit.setText(self.obj.Formula)
        del blocker
        self.sync()

    def edit(self, mode=None):
        spec = self.definition()
        if isinstance(mode, str): spec["mode"] = mode
        dialog = ProfileDialog(spec, units(self.obj), self.motion, self)
        if dialog.exec(): self.apply(dialog.spec)
        else: self.sync()
