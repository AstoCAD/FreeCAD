# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for scripted point-measurement entries in Simulation Results.

Uses valid recorded-pose snapshots without running a dynamics simulation.
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import AssemblyApp
    import CommandCreateSimulation as Simulation
    import CommandPointMeasurement as MeasurementCommand
    import Dynamics
    import PointMeasurement as PM
    import UtilsAssembly
    from PySide import QtCore, QtWidgets


@unittest.skipUnless(App.GuiUp, "Requires the native FreeCAD GUI")
class TestPointMeasurementListGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        workbench = Gui.activeWorkbench()
        self.previous_workbench = workbench.name() if workbench else None
        self.preferences = App.ParamGet("User parameter:BaseApp/Preferences/Mod/Assembly")
        self.previous_solve_present = any(
            entry[1] == "SolveOnRecompute" for entry in (self.preferences.GetContents() or ())
        )
        self.previous_solve = self.preferences.GetBool("SolveOnRecompute", True)
        self.addCleanup(self._cleanup)
        self.preferences.SetBool("SolveOnRecompute", False)
        self.assertFalse(Gui.Control.activeDialog())
        Gui.activateWorkbench("AssemblyWorkbench")
        self.doc = App.newDocument("PointMeasurementListAudit")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
        self.solid = self.assembly.newObject("Part::Feature", "Solid")
        self.solid.Shape = Part.makeBox(2, 3, 4)
        self.solid.Placement.Base = App.Vector(10, 0, 0)
        # Mirror TaskAssemblyCreateSimulation.createSimulationObject exactly:
        # its GUI consumes the Simulation subclass and legacy property aliases.
        simulation_group = UtilsAssembly.getSimulationGroup(self.assembly)
        self.study = simulation_group.newObject("App::FeaturePython", "Simulation")
        Simulation.Simulation(self.study)
        Simulation.ViewProviderSimulation(self.study.ViewObject)
        # The real GUI sets this existing owner backlink in setUiInitialValues.
        self.study.Assembly = self.assembly
        self.assertEqual(self.study.Assembly, self.assembly)
        self.assertIsInstance(self.study.Proxy, Simulation.Simulation)
        self.assertTrue(callable(self.study.Proxy.setMotionsChangedCallback))
        for name in (
            "aTimeStart",
            "bTimeEnd",
            "cTimeStepOutput",
            "fGlobalErrorTolerance",
            "jFramesPerSecond",
        ):
            self.assertIn(name, self.study.PropertiesList)
        self.measurement = PM.create(self.study)
        self.measurement.Point = (self.solid, ["Vertex2"])
        body = {
            "Placements": [[10, 0, 0, 0, 0, 0, 1], [20, 0, 0, 0, 0, 0, 1]],
            "Velocity": [[10, 0, 0], [10, 0, 0]],
            "Acceleration": [[0, 0, 0], [0, 0, 0]],
            "AngularVelocity": [[0, 0, 0], [0, 0, 0]],
            "AngularAcceleration": [[0, 0, 0], [0, 0, 0]],
        }
        self.data = {
            "SchemaVersion": 2,
            "Times": [0, 1],
            "Bodies": {self.solid.Name: body},
        }
        Dynamics.save_results(self.study, self.data)
        self.doc.recompute()
        self.assertEqual(self.study.Status, "Complete")
        self.assertEqual(PM.measure(self.measurement)["Times"], [0, 1])
        self.saved_results = self.study.ResultData
        self.original_placement = self.solid.Placement
        self.assertFalse(self.solid.Shape.isNull())
        self.assertTrue(self.solid.Shape.isValid())
        self.assertEqual(len(self.solid.Shape.Solids), 1)
        Gui.activeDocument().setEdit(self.assembly)
        self.assertEqual(UtilsAssembly.activeAssembly(), self.assembly)

    @staticmethod
    def _pump():
        QtWidgets.QApplication.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        QtWidgets.QApplication.processEvents()
        Gui.updateGui()

    def _cancel_task(self):
        self.assertTrue(Gui.Control.activeDialog())
        elapsed = QtCore.QElapsedTimer()
        elapsed.start()

        def visible_owned_cancel():
            task = Gui.Control.activeTaskDialog()
            owner = task.getDocumentName() if task is not None else None
            own_task = owner == self.doc.Name
            buttons = []
            for box in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox):
                button = box.button(QtWidgets.QDialogButtonBox.Cancel)
                if button is None:
                    continue
                ancestor = box.parentWidget()
                retained = []
                task_control = False
                while ancestor is not None:
                    retained.append(ancestor)
                    if ancestor.inherits("Gui::TaskView::TaskEditControl"):
                        task_control = True
                        break
                    ancestor = ancestor.parentWidget()
                ready = (
                    own_task
                    and task_control
                    and box.isVisible()
                    and button.isVisible()
                    and button.isEnabled()
                )
                if ready:
                    buttons.append(button)
            return buttons

        buttons = visible_owned_cancel()
        while not buttons and elapsed.elapsed() < 5000:
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()
            buttons = visible_owned_cancel()
        buttons = visible_owned_cancel()
        self.assertTrue(buttons, "The native task must expose its Cancel button")
        buttons[-1].click()
        self._pump()

    def _cleanup(self):
        try:
            if self.doc is not None and self.doc.Name in App.listDocuments():
                for unused in range(4):
                    if not Gui.Control.activeDialog():
                        break
                    self._cancel_task()
                self.assertFalse(Gui.Control.activeDialog())
                Gui.Selection.clearSelection()
                Gui.getDocument(self.doc.Name).resetEdit()
                self._pump()
                App.closeDocument(self.doc.Name)
                self._pump()
        finally:
            if self.previous_solve_present:
                self.preferences.SetBool("SolveOnRecompute", self.previous_solve)
            else:
                self.preferences.RemBool("SolveOnRecompute")
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _open_from_results(self):
        panel = Simulation.TaskAssemblyCreateSimulation(self.study)
        dialog = Gui.Control.showDialog(panel)
        if dialog is not None:
            dialog.setAutoCloseOnDeletedDocument(True)
            dialog.setDocumentName(self.doc.Name)
        self._pump()
        self.assertIs(Simulation.activeSimulationTask(), panel)
        self.assertEqual(panel.measurementList.count(), 1)
        item = panel.measurementList.item(0)
        self.assertEqual(item.data(QtCore.Qt.UserRole), self.measurement.Name)
        error = None
        try:
            panel.editPointMeasurement(item)
        except (AttributeError, RuntimeError, ValueError) as caught:
            error = (type(caught).__name__, str(caught))
        self.assertIsNone(error, "An existing Results entry must open its point measurement")
        self._pump()
        self.assertTrue(Gui.Control.activeDialog())
        self.assertIsNone(Simulation.activeSimulationTask())
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertEqual(self.study.ResultData, self.saved_results)
        self._cancel_task()
        self.assertIsNotNone(Simulation.activeSimulationTask())
        self.assertEqual(self.study.ResultData, self.saved_results)
        self.assertLess((self.solid.Placement.Base - self.original_placement.Base).Length, 1e-8)
        self.assertIsNotNone(self.doc.getObject(self.measurement.Name))

    def test_explicit_provider_results_entry_control(self):
        MeasurementCommand.ViewProviderMeasurement(self.measurement.ViewObject)
        self.assertIsInstance(
            self.measurement.ViewObject.Proxy, MeasurementCommand.ViewProviderMeasurement
        )
        self._open_from_results()

    def test_scripted_results_entry_opens(self):
        self.assertIsNone(
            self.measurement.ViewObject.Proxy,
            "The scripted Results entry must exercise the missing GUI-provider path",
        )
        self._open_from_results()
        self.assertIsInstance(
            self.measurement.ViewObject.Proxy, MeasurementCommand.ViewProviderMeasurement
        )

    def test_existing_custom_provider_results_entry_control(self):
        class CustomProvider(MeasurementCommand.ViewProviderMeasurement):
            def __init__(self, view_object):
                self.calls = []
                super().__init__(view_object)

            def doubleClicked(self, view_object):
                self.calls.append(view_object.Object.Name)
                return super().doubleClicked(view_object)

        provider = CustomProvider(self.measurement.ViewObject)
        self.assertIs(self.measurement.ViewObject.Proxy, provider)
        self._open_from_results()
        self.assertEqual(provider.calls, [self.measurement.Name])
        self.assertIs(self.measurement.ViewObject.Proxy, provider)
