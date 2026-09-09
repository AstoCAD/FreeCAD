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

import unittest
import os
import tempfile
from unittest.mock import patch

import FreeCAD as App
import Part
import AssemblyApp
import Dynamics
import PointMeasurement as PM


class TestPointMeasurement(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PointMeasurementTest")
        self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def assertVector(self, actual, expected):
        self.assertLess((actual - App.Vector(*expected)).Length, 1e-8)

    @staticmethod
    def body(p=(0, 0, 0), q=(0, 0, 0, 1), v=(0, 0, 0), a=(0, 0, 0), w=(0, 0, 0), alpha=(0, 0, 0)):
        return {"Placements": [list(p) + list(q)], "Velocity": [v], "Acceleration": [a],
                "AngularVelocity": [w], "AngularAcceleration": [alpha]}

    def test_rotating_offset_point(self):
        data = {"Times": [0], "Bodies": {"Rotor": self.body(w=(0, 0, 2), alpha=(0, 0, 3))}}
        result = PM.evaluate(data, "Rotor", App.Vector(4, 0, 0))
        self.assertVector(result["Position"][0], (4, 0, 0))
        self.assertVector(result["Velocity"][0], (0, 8, 0))
        self.assertVector(result["Acceleration"][0], (-16, 12, 0))

    def test_comoving_reference(self):
        body = self.body(p=(7, 8, 9), v=(1, 2, 3), a=(4, 5, 6), w=(0, 0, 2), alpha=(0, 0, 3))
        data = {"Times": [0], "Bodies": {"Rotor": body}}
        result = PM.evaluate(data, "Rotor", App.Vector(4, 0, 0), "Rotor",
                             App.Placement(App.Vector(1, 0, 0), App.Rotation(App.Vector(0, 0, 1), 90)))
        self.assertVector(result["Position"][0], (0, -3, 0))
        self.assertVector(result["Velocity"][0], (0, 0, 0))
        self.assertVector(result["Acceleration"][0], (0, 0, 0))

    def test_rotating_frame_coriolis(self):
        data = {"Times": [0], "Bodies": {"Point": self.body(p=(3, 0, 0), v=(1, 0, 0)),
                                               "Frame": self.body(w=(0, 0, 2), alpha=(0, 0, 1))}}
        result = PM.evaluate(data, "Point", App.Vector(), "Frame")
        self.assertVector(result["Velocity"][0], (1, -6, 0))
        self.assertVector(result["Acceleration"][0], (-12, -7, 0))

    def test_occurrences_and_nested_vertex(self):
        body = self.assembly.newObject("Part::Feature", "Body")
        body.Shape = Part.makeBox(2, 3, 4)
        body.Placement.Base = App.Vector(10, 0, 0)
        link = self.assembly.newObject("App::Link", "LinkToBody")
        link.setLink(body)
        link.Placement.Base = App.Vector(30, 0, 0)
        self.doc.recompute()
        for component in (body, link):
            resolved, sub = PM.resolve_reference(self.assembly, self.assembly, component.Name + ".Vertex2")
            self.assertEqual(resolved, component)
            self.assertEqual(sub, "Vertex2")
            direct, _ = PM.resolve_reference(self.assembly, component, "Vertex2")
            self.assertEqual(direct, component)
        self.assertVector(PM.local_frame((link, ["Vertex2"]), True).Base,
                          tuple(PM.local_frame((body, ["Vertex2"]), True).Base))
        part = self.assembly.newObject("App::Part", "Component")
        child = part.newObject("Part::Feature", "Child")
        child.Shape = Part.makeBox(2, 3, 4)
        child.Placement.Base = App.Vector(5, 0, 0)
        part.Placement.Base = App.Vector(100, 0, 0)
        self.doc.recompute()
        local = PM.local_frame((part, ["Child.Vertex2"]), True).Base
        self.assertVector(local, tuple(child.Shape.Vertexes[1].Point))

    def test_measurement_does_not_invalidate_results(self):
        study = Dynamics.create_study(self.assembly)
        study.ResultData = '{"SchemaVersion":2,"Times":[0],"Bodies":{}}'
        study.Status = "Complete"
        saved = study.ResultData
        obj = PM.create(study)
        self.assertEqual(study.ResultData, saved)
        self.assertEqual(study.Status, "Complete")
        obj.Quantity = "Acceleration"
        study.removeObject(obj)
        self.assertEqual(study.ResultData, saved)
        study.addObject(self.doc.addObject("App::FeaturePython", "Input"))
        self.assertEqual(study.Status, "NotRun")

    def test_missing_component_rejected(self):
        with self.assertRaises(ValueError):
            PM.evaluate({"Times": [0], "Bodies": {}}, "Missing", App.Vector())

    def test_datums_and_scaled_link(self):
        part = self.assembly.newObject("App::Part", "Component")
        datum = part.newObject("App::LocalCoordinateSystem", "LCS")
        datum.Placement = App.Placement(App.Vector(2, 3, 4), App.Rotation(App.Vector(0, 0, 1), 90))
        point = part.newObject("PartDesign::Point", "Point")
        point.Placement.Base = App.Vector(5, 6, 7)
        solid = part.newObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(2, 3, 4)
        link = self.assembly.newObject("App::Link", "Link")
        link.setLink(part)
        link.Scale = 2
        link.Placement.Base = App.Vector(50, 0, 0)
        self.doc.recompute()
        self.assertVector(PM.local_frame((part, ["LCS."]), True).Base, (2, 3, 4))
        self.assertVector(PM.local_frame((part, ["LCS."])).Rotation.multVec(App.Vector(1, 0, 0)), (0, 1, 0))
        self.assertVector(PM.local_frame((part, ["Point."]), True).Base, (5, 6, 7))
        expected = PM.local_frame((part, ["Solid.Vertex2"]), True).Base * 2
        self.assertVector(PM.local_frame((link, ["Solid.Vertex2"]), True).Base, tuple(expected))
        selected, sub = PM.resolve_reference(self.assembly, datum, "")
        self.assertEqual(selected, part)
        self.assertEqual(sub, "LCS.")

    def test_save_reopen_measurement(self):
        solid = self.assembly.newObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(2, 3, 4)
        study = Dynamics.create_study(self.assembly)
        obj = PM.create(study)
        obj.Point = (solid, ["Vertex2"])
        data = {"SchemaVersion": 2, "Times": [0], "Bodies": {solid.Name: self.body(w=(0, 0, 2))}}
        Dynamics.save_results(study, data)
        expected = PM.measure(obj)["Velocity"][0]
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "measurement.FCStd")
            self.doc.recompute()
            self.doc.saveAs(path)
            App.closeDocument(self.doc.Name)
            self.doc = App.openDocument(path)
            self.assertVector(PM.measure(self.doc.getObject("PointMeasurement"))["Velocity"][0], tuple(expected))

    @unittest.skipUnless(App.GuiUp, "Requires GUI")
    def test_task_playback_and_cancel(self):
        import FreeCADGui as Gui
        import CommandPointMeasurement as Command
        import CommandCreateSimulation as Simulation
        from PySide import QtWidgets

        solid = self.assembly.newObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(2, 3, 4)
        solid.Placement.Base = App.Vector(10, 0, 0)
        study = Dynamics.create_study(self.assembly)
        body = self.body(p=(10, 0, 0))
        for key in body:
            body[key].append(body[key][0])
        body["Placements"][1] = [20, 0, 0, 0, 0, 0, 1]
        data = {"SchemaVersion": 2, "Times": [0, 1], "Bodies": {solid.Name: body}}
        Dynamics.save_results(study, data)
        saved = study.ResultData
        self.doc.openTransaction("Measurement")
        obj = PM.create(study)
        obj.Point = (solid, ["Vertex2"])
        panel = Command.TaskPointMeasurement(study, obj)
        with patch.object(Simulation.TaskAssemblyCreateSimulation, "reopen"):
            try:
                Gui.Control.showDialog(panel)
                self.assertIsNotNone(panel.samples)
                self.assertTrue(panel.showPath.isChecked())
                self.assertEqual(panel.table.rowCount(), 2)
                panel.slider.setValue(1)
                self.assertVector(solid.Placement.Base, (20, 0, 0))
                panel.showPath.setChecked(False)
                self.assertEqual(panel.root.getNumChildren(), 0)
            finally:
                panel.reject()
                QtWidgets.QApplication.processEvents()
        self.assertVector(solid.Placement.Base, (10, 0, 0))
        self.assertEqual(study.ResultData, saved)
        self.assertIsNone(self.doc.getObject("PointMeasurement"))

    @unittest.skipUnless(App.GuiUp, "Requires GUI")
    def test_simulation_child_workflow(self):
        import FreeCADGui as Gui
        import CommandPointMeasurement as Command
        import CommandCreateSimulation as Simulation
        from PySide import QtWidgets

        solid = self.assembly.newObject("Part::Feature", "Solid")
        solid.Shape = Part.makeBox(2, 3, 4)
        self.doc.recompute()
        captured = []
        original = Command.TaskPointMeasurement

        def capture(*args):
            panel = original(*args)
            captured.append(panel)
            return panel

        with patch.object(Simulation.UtilsAssembly, "activeAssembly", return_value=self.assembly):
            sim_panel = Simulation.TaskAssemblyCreateSimulation()
            Gui.Control.showDialog(sim_panel)
            study = sim_panel.simFeaturePy
            data = {"SchemaVersion": 2, "Times": [0], "Bodies": {solid.Name: self.body()}}
            Dynamics.save_results(study, data)
            sim_panel.resultData = data
            sim_panel.refreshResults()
            self.assertTrue(sim_panel.pointMeasurementButton.isEnabled())
            try:
                with patch.object(Command, "TaskPointMeasurement", side_effect=capture):
                    sim_panel.addPointMeasurement()
                panel = captured[-1]
                self.assertTrue(panel.referenceButton.isHidden())
                self.assertTrue(panel.referenceLabel.isHidden())
                panel.frameMode.setCurrentIndex(1)
                self.assertFalse(panel.referenceButton.isHidden())
                self.assertFalse(panel.referenceLabel.isHidden())
                panel.frameMode.setCurrentIndex(0)
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(self.assembly, "Solid.Vertex2")
                panel.useSelection(True)
                self.assertEqual(panel.measurement.Point[0], solid)
                self.assertIsNotNone(panel.samples)
                self.assertTrue(panel.accept())
                QtWidgets.QApplication.processEvents()
                reopened = Simulation.activeSimulationTask()
                self.assertIsNotNone(reopened)
                self.assertEqual(reopened.measurementList.count(), 1)
                self.assertEqual(study.Status, "Complete")
                with patch.object(Command, "TaskPointMeasurement", side_effect=capture):
                    reopened.editPointMeasurement(reopened.measurementList.item(0))
                self.assertIsNotNone(captured[-1].samples)
                captured[-1].reject()
                QtWidgets.QApplication.processEvents()
            finally:
                panel = Simulation.activeSimulationTask()
                if panel:
                    panel.reject()
                elif Gui.Control.activeDialog():
                    Gui.Control.closeDialog()
