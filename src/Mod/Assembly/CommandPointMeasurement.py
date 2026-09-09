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

"""Point measurement task and saved-result playback; no solver calls."""

import csv

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets
from pivy import coin

import Dynamics
import PointMeasurement as PM
import UtilsAssembly

translate = App.Qt.translate


def edit(study, measurement=None):
    import CommandCreateSimulation as Simulation

    # Validate before closing the current task or opening a transaction.
    if not Dynamics.results(study).get("Times"):
        raise ValueError("The simulation has no recorded samples. Generate it first.")
    task = Simulation.activeSimulationTask()
    if task:
        task.suspendForChildTask()
    elif Gui.Control.activeDialog():
        return False
    study.Document.openTransaction(translate("Assembly", "Point measurement"))
    try:
        if measurement is None:
            measurement = PM.create(study)
            ViewProviderMeasurement(measurement.ViewObject)
        panel = TaskPointMeasurement(study, measurement)
        dialog = Gui.Control.showDialog(panel)
    except Exception:
        study.Document.abortTransaction()
        QtCore.QTimer.singleShot(0, lambda: Simulation.TaskAssemblyCreateSimulation.reopen(study, "resultsTab"))
        raise
    if dialog is not None:
        dialog.setAutoCloseOnDeletedDocument(True)
        dialog.setDocumentName(study.Document.Name)
    return True


class ViewProviderMeasurement:
    def __init__(self, obj):
        obj.Proxy = self

    def attach(self, obj):
        pass

    def getIcon(self):
        return ":/icons/Std_DependencyGraph.svg"

    def doubleClicked(self, obj):
        study = next((p for p in obj.Object.InList if Dynamics.is_study(p)), None)
        if study:
            try:
                return edit(study, obj.Object)
            except ValueError as error:
                QtWidgets.QMessageBox.warning(None, translate("Assembly", "Point measurement"), str(error))
        return False

    def dumps(self):
        return None

    def loads(self, state):
        pass


class TaskPointMeasurement:
    def __init__(self, study, measurement):
        self.study, self.measurement = study, measurement
        self.assembly = study.Assembly
        self.data = Dynamics.results(study)
        self.initial = UtilsAssembly.saveAssemblyPartsPlacements(self.assembly)
        self.view = Gui.getDocument(study.Document.Name).activeView()
        self.samples = None
        self.closed = False
        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(translate("Assembly", "Point measurement"))
        self.form.setWindowIcon(Gui.getIcon("Assembly_CreateSimulation"))
        self.form.setMinimumWidth(400)
        layout = QtWidgets.QVBoxLayout(self.form)
        fields = QtWidgets.QFormLayout()
        layout.addLayout(fields)
        self.pointButton = QtWidgets.QPushButton()
        self.pointButton.setToolTip(translate("Assembly", "Select a vertex, datum point or coordinate system in the viewport or tree, then click here. The selected component occurrence is preserved."))
        self.pointButton.clicked.connect(lambda: self.useSelection(True))
        fields.addRow(translate("Assembly", "Point"), self.pointButton)
        self.frameMode = QtWidgets.QComboBox()
        self.frameMode.addItems([translate("Assembly", "Assembly"), translate("Assembly", "Component / coordinate system")])
        self.frameMode.setCurrentIndex(1 if measurement.Reference else 0)
        fields.addRow(translate("Assembly", "Relative to"), self.frameMode)
        self.referenceButton = QtWidgets.QPushButton()
        self.referenceButton.setToolTip(translate("Assembly", "Select a component or coordinate system, then click here. Velocities and accelerations include the motion and rotation of this reference frame."))
        fields.addRow(translate("Assembly", "Reference"), self.referenceButton)
        self.referenceLabel = fields.labelForField(self.referenceButton)
        self.referenceButton.clicked.connect(lambda: self.useSelection(False))
        self.frameMode.currentIndexChanged.connect(self.frameChanged)
        self.quantity = QtWidgets.QComboBox()
        for name in ("Position", "Velocity", "Acceleration"):
            self.quantity.addItem(translate("Assembly", name), name)
        self.quantity.setCurrentIndex(self.quantity.findData(str(measurement.Quantity)))
        fields.addRow(translate("Assembly", "Quantity"), self.quantity)
        self.axis = QtWidgets.QComboBox()
        for name in ("X", "Y", "Z", "Magnitude"):
            self.axis.addItem(translate("Assembly", name), name)
        self.axis.setCurrentIndex(self.axis.findData(str(measurement.Axis)))
        fields.addRow(translate("Assembly", "Axis"), self.axis)
        self.quantity.currentIndexChanged.connect(self.refreshTable)
        self.axis.currentIndexChanged.connect(self.refreshTable)
        self.showPath = QtWidgets.QCheckBox(translate("Assembly", "Show trajectory"))
        self.showPath.setChecked(True)
        self.showPath.setToolTip(translate("Assembly", "Show the recorded path and current point. For a moving reference, the whole path is displayed in that frame at the current playback time."))
        layout.addWidget(self.showPath)
        self.showPath.toggled.connect(self.draw)
        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        self.plotButton = QtWidgets.QPushButton(translate("Assembly", "Plot"))
        self.exportButton = QtWidgets.QPushButton(translate("Assembly", "Export CSV"))
        buttons.addWidget(self.plotButton)
        buttons.addWidget(self.exportButton)
        self.plotButton.clicked.connect(self.plot)
        self.exportButton.clicked.connect(self.export)
        player = QtWidgets.QGroupBox(translate("Assembly", "Playback"))
        layout.addWidget(player)
        playerLayout = QtWidgets.QVBoxLayout(player)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, max(0, len(self.data["Times"]) - 1))
        playerLayout.addWidget(self.slider)
        self.timeLabel = QtWidgets.QLabel()
        playerLayout.addWidget(self.timeLabel)
        controls = QtWidgets.QHBoxLayout()
        playerLayout.addLayout(controls)
        self.timer = QtCore.QTimer(self.form)
        self.timer.setInterval(max(1, round(1000 / getattr(study, "jFramesPerSecond", 30))))
        self.direction = 1
        self.timer.timeout.connect(self.advance)
        for icon, tooltip, callback in (
            ("media-playback-step-back", "Step backward", lambda: self.step(-1)),
            ("media-playback-start-back", "Play backward", lambda: self.play(-1)),
            ("media-playback-stop", "Stop", self.timer.stop),
            ("media-playback-start", "Play forward", lambda: self.play(1)),
            ("media-playback-step", "Step forward", lambda: self.step(1)),
        ):
            button = QtWidgets.QToolButton()
            button.setIcon(Gui.getIcon(icon))
            button.setToolTip(translate("Assembly", tooltip))
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.slider.valueChanged.connect(self.playback)
        self.root = coin.SoSeparator()
        self.view.getSceneGraph().addChild(self.root)
        try:
            self.refresh()
        except Exception:
            self.view.getSceneGraph().removeChild(self.root)
            UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initial)
            raise

    def useSelection(self, point):
        selections = Gui.Selection.getSelectionEx("*", 0)
        try:
            if len(selections) != 1 or len(selections[0].SubElementNames) > 1:
                raise ValueError("Select exactly one reference, then click the selection button.")
            selection = selections[0]
            subname = selection.SubElementNames[0] if selection.SubElementNames else ""
            component, subname = PM.resolve_reference(self.assembly, selection.Object, subname)
            reference = (component, [subname])
            PM.local_frame(reference, point=point)
            setattr(self.measurement, "Point" if point else "Reference", reference)
            Gui.Selection.clearSelection()
            self.refresh()
        except (ValueError, RuntimeError, AttributeError) as error:
            self.message.setText(str(error))

    def frameChanged(self):
        if self.frameMode.currentIndex() == 0:
            self.measurement.Reference = None
        self.refresh()

    @staticmethod
    def label(reference):
        if not reference:
            return translate("Assembly", "Use selection")
        obj, names = reference
        return (obj.Label + ("." + names[0] if names and names[0] else "")) if obj else translate("Assembly", "Use selection")

    def refresh(self):
        self.pointButton.setText(self.label(self.measurement.Point))
        self.referenceButton.setText(self.label(self.measurement.Reference))
        self.referenceButton.setVisible(self.frameMode.currentIndex() == 1)
        self.referenceLabel.setVisible(self.frameMode.currentIndex() == 1)
        try:
            if not self.measurement.Point or not self.measurement.Point[0]:
                raise ValueError("Select a vertex, datum point or coordinate system, then click Point's selection button.")
            if self.frameMode.currentIndex() == 1 and not self.measurement.Reference:
                raise ValueError("Select the reference component or coordinate system.")
            self.samples = PM.measure(self.measurement, self.data)
            self.message.clear()
        except (ValueError, RuntimeError, AttributeError) as error:
            self.samples = None
            self.message.setText(str(error))
        self.refreshTable()
        self.playback()

    def series(self):
        if not self.samples:
            return [], ""
        quantity, axis = self.quantity.currentData(), self.axis.currentData()
        vectors = self.samples[quantity]
        values = [v.Length if axis == "Magnitude" else v["XYZ".index(axis)] for v in vectors]
        return values, {"Position": "mm", "Velocity": "mm/s", "Acceleration": "mm/s^2"}[quantity]

    def refreshTable(self, *_args):
        self.measurement.Quantity = self.quantity.currentData()
        self.measurement.Axis = self.axis.currentData()
        values, unit = self.series()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([translate("Assembly", "Time (s)"), f"{self.quantity.currentText()} {self.axis.currentText()} ({unit})"])
        self.table.setRowCount(len(values))
        for i, (time, value) in enumerate(zip(self.data["Times"], values)):
            for j, number in enumerate((time, value)):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(f"{number:.9g}"))
        self.plotButton.setEnabled(bool(values))
        self.exportButton.setEnabled(bool(values))

    def playback(self, *_args):
        index = self.slider.value()
        # Saved placements are assembly-local. Restore through the occurrence's
        # parent frame, also supporting components under organizational groups.
        for name, body in self.data["Bodies"].items():
            component = self.study.Document.getObject(name)
            if component is not None and hasattr(component, "Placement"):
                parent = Dynamics.component_placement(component) * component.Placement.inverse()
                component.Placement = parent.inverse() * PM.placement(body["Placements"][index])
        for obj in Dynamics.inputs_for_study(self.study):
            if hasattr(obj, "LoadType") or hasattr(obj, "InitialVelocityType"):
                provider = obj.ViewObject.Proxy
                if provider:
                    provider.updateVisual(obj)
        self.timeLabel.setText(f"{self.data['Times'][index]:.6g} s")
        self.table.selectRow(index)
        self.draw()

    def draw(self, *_args):
        self.root.removeAllChildren()
        if not self.samples or not self.showPath.isChecked():
            return
        index = self.slider.value()
        world = UtilsAssembly.getGlobalPlacement((self.assembly, [""]))
        frame = world * self.samples["Frames"][index]
        points = [tuple(frame.multVec(p)) for p in self.samples["Position"]]
        color = coin.SoBaseColor()
        color.rgb = (0.1, 0.7, 0.95)
        style = coin.SoDrawStyle()
        style.lineWidth = 2
        style.pointSize = 9
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(points), points)
        line = coin.SoLineSet()
        line.numVertices.setValue(len(points))
        marker = coin.SoPointSet()
        marker.startIndex = index
        marker.numPoints = 1
        for node in (color, style, coords, line, marker):
            self.root.addChild(node)

    def play(self, direction):
        self.direction = direction
        self.timer.start()

    def advance(self):
        self.slider.setValue((self.slider.value() + self.direction) % (self.slider.maximum() + 1))

    def step(self, direction):
        self.timer.stop()
        self.direction = direction
        self.advance()

    def plot(self):
        try:
            import Plot
            values, unit = self.series()
            figure = Plot.figure(self.measurement.Label)
            if figure is not None:
                figure.plot(self.data["Times"], values, self.axis.currentText())
                figure.axes.set_xlabel(translate("Assembly", "Time (s)"))
                figure.axes.set_ylabel(f"{self.quantity.currentText()} ({unit})")
                figure.axes.grid(True)
                figure.update()
        except ImportError as error:
            self.message.setText(str(error))

    def export(self):
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(self.form, translate("Assembly", "Export point measurement"), "", "CSV (*.csv)")
        if filename:
            if not filename.lower().endswith(".csv"):
                filename += ".csv"
            values, _ = self.series()
            with open(filename, "w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow([self.table.horizontalHeaderItem(i).text() for i in range(2)])
                writer.writerows(zip(self.data["Times"], values))

    def accept(self):
        if not self.samples:
            return False
        self.finish(True)
        return True

    def reject(self):
        self.finish(False)
        return True

    def finish(self, accepted):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.view.getSceneGraph().removeChild(self.root)
        UtilsAssembly.restoreAssemblyPartsPlacements(self.assembly, self.initial)
        if accepted:
            Dynamics.purge_touched(self.measurement, self.study)
            self.study.Document.commitTransaction()
        else:
            self.study.Document.abortTransaction()
        Gui.Control.closeDialog()
        import CommandCreateSimulation as Simulation
        QtCore.QTimer.singleShot(0, lambda: Simulation.TaskAssemblyCreateSimulation.reopen(self.study, "resultsTab"))
