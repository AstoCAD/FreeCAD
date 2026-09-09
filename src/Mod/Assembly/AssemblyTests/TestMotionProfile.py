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

import copy
import math
import unittest

import MotionProfile as MP


class TestMotionProfile(unittest.TestCase):
    def test_quintic_endpoints_and_derivatives(self):
        profile = MP.Profile(MP.defaults())
        self.assertAlmostEqual(profile.sample(.5), .5)
        self.assertAlmostEqual(profile.sample(.5, 1), 1.875)
        for t, position in ((0, 0), (1, 1)):
            self.assertAlmostEqual(profile.sample(t), position)
            self.assertAlmostEqual(profile.sample(t, 1), 0)
            self.assertAlmostEqual(profile.sample(t, 2), 0)
        h = 1e-5
        for t in (.1, .35, .8):
            self.assertAlmostEqual(profile.sample(t, 1), (profile.sample(t+h)-profile.sample(t-h))/(2*h), places=7)
            self.assertAlmostEqual(profile.sample(t, 2), (profile.sample(t+h,1)-profile.sample(t-h,1))/(2*h), places=6)

    def test_integrated_velocity_and_acceleration(self):
        spec = MP.defaults()
        spec.update(quantity="Velocity", initial_position=3)
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(1), 3.5)
        self.assertAlmostEqual(profile.sample(2), 4.5)
        spec.update(quantity="Acceleration", initial_velocity=2)
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(1), 3+2+1/7)
        self.assertAlmostEqual(profile.sample(1, 1), 2.5)
        self.assertAlmostEqual(profile.sample(1, 2), 1)

    def test_spline_interpolation_and_continuity(self):
        spec = MP.defaults(mode="Data points")
        spec["points"] = [[0, 0], [.3, .8], [1, -.2], [2, 1]]
        profile = MP.Profile(spec)
        for t, y in spec["points"]: self.assertAlmostEqual(profile.sample(t), y)
        for t in (.3, 1):
            for order in (0, 1, 2):
                self.assertAlmostEqual(profile.sample(t-1e-9, order), profile.sample(t+1e-9, order), places=6)

    def test_repeat_and_coverage(self):
        spec = MP.defaults()
        spec["segments"] = [[1, 1, "Smooth"], [1, 0, "Smooth"]]
        spec["outside"] = "Repeat"
        profile = MP.Profile(spec, -2, 7)
        for t in (-1.5, .5, 2.5, 6.5): self.assertAlmostEqual(profile.sample(t), .5, places=6)
        spec["outside"] = "Require coverage"
        with self.assertRaises(ValueError): MP.Profile(spec, 0, 3)

    def test_repeated_velocity_accumulates_travel(self):
        spec = MP.defaults()
        spec.update(quantity="Velocity", initial_position=3, outside="Repeat")
        spec["segments"] = [[1, 1, "Smooth"], [1, 0, "Smooth"]]
        profile = MP.Profile(spec, 0, 6)
        for time, position in ((0, 3), (2, 4), (4, 5), (5, 5.5), (6, 6)):
            self.assertAlmostEqual(profile.sample(time), position, places=8)

    def test_polynomial_expression_and_explicit_initial_value(self):
        spec = MP.defaults(mode="Expression")
        spec.update(expression="t*t", quantity="Acceleration", initial_position=3, initial_velocity=2)
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(.5), 3+2*.5+.5**4/12)
        spec.update(quantity="Position", expression="initialValue+t")
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(-1), 3)
        self.assertAlmostEqual(profile.sample(1), 4)
        self.assertNotIn("initialValue", profile.formula())

    def test_expression_derivatives_and_integrals(self):
        spec = MP.defaults(mode="Expression")
        spec.update(expression="sin(2*t)", quantity="Velocity", initial_position=3)
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(.4), 3+(1-math.cos(.8))/2)
        self.assertAlmostEqual(profile.sample(.4, 1), math.sin(.8))
        self.assertAlmostEqual(profile.sample(.4, 2), 2*math.cos(.8))
        spec.update(expression="2", quantity="Acceleration", initial_velocity=4)
        profile = MP.Profile(spec)
        self.assertAlmostEqual(profile.sample(.4), 3+4*.4+.4**2)

    def test_units_and_invalid_data(self):
        spec = MP.defaults("deg")
        spec["segments"] = [[1, 180, "Smooth"]]
        self.assertAlmostEqual(MP.Profile(spec).sample(1), math.pi)
        for rows in ([[0, 1, "Smooth"]], [[-1, 1, "Linear"]], [[1, 1, "Hold"]]):
            spec["segments"] = rows
            with self.assertRaises(ValueError): MP.Profile(spec)
        spec = MP.defaults(mode="Data points")
        spec["points"] = [[0, 1], [0, 2]]
        with self.assertRaises(ValueError): MP.Profile(spec)
        for expr in ("__import__('os')", "t.__class__", "[1,2]", "2**1000000"):
            with self.assertRaises(ValueError): MP.expression(expr)

    def test_dialog_preview_import_and_cancel(self):
        import FreeCAD as App
        if not App.GuiUp: self.skipTest("Requires GUI")
        from ProfileEditor import ProfileDialog
        spec = MP.defaults()
        original = copy.deepcopy(spec)
        dialog = ProfileDialog(spec, ["mm", "m"], True)
        self.assertFalse(dialog.quantity.isHidden())
        self.assertIsNotNone(dialog.profile)
        dialog.table.item(0, 1).setText("5")
        self.assertAlmostEqual(dialog.profile.sample(1), 5)
        dialog.mode.setCurrentIndex(dialog.mode.findData("Data points"))
        dialog.importText("Time,Value\n0,0\n1,2\n2,0", False)
        self.assertEqual(dialog.table.rowCount(), 3)
        self.assertAlmostEqual(dialog.profile.sample(1), 2)
        dialog.reject()
        self.assertEqual(spec, original)
        force_spec = MP.defaults("N")
        force_spec["quantity"] = "Magnitude"
        force_dialog = ProfileDialog(force_spec, ["N"], False)
        self.assertTrue(force_dialog.quantity.isHidden())
        self.assertTrue(force_dialog.layout().itemAt(0).layout().labelForField(force_dialog.quantity).isHidden())
        force_dialog.reject()

    def test_dialog_unit_conversion(self):
        import FreeCAD as App
        if not App.GuiUp: self.skipTest("Requires GUI")
        from ProfileEditor import ProfileDialog
        spec = MP.defaults("deg", "Expression")
        spec.update(expression="initialValue+90*t", initial_position=30)
        dialog = ProfileDialog(spec, ["deg", "rad"], True)
        before = dialog.profile.sample(.5)
        dialog.unit.setCurrentIndex(dialog.unit.findData("rad"))
        self.assertAlmostEqual(dialog.profile.sample(.5), before)
        dialog.reject()

    def test_profile_field_outer_transaction(self):
        import FreeCAD as App
        if not App.GuiUp: self.skipTest("Requires GUI")
        import Dynamics
        from ProfileEditor import ProfileField
        from PySide import QtWidgets
        from AssemblyTests.TestDynamics import TestDynamics
        fixture = TestDynamics()
        fixture.setUp()
        try:
            body = fixture.box()
            study = fixture.study(False)
            load = Dynamics.create_load(study, "Force", body)
            study.ResultData = "saved result"
            study.Status = "Complete"
            fixture.doc.openTransaction("Edit profile")
            container = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(container)
            magnitude = QtWidgets.QDoubleSpinBox()
            layout.addRow("Magnitude", magnitude)
            label = layout.labelForField(magnitude)
            field = ProfileField(load, QtWidgets.QLineEdit(), container, magnitude)
            self.assertFalse(magnitude.isHidden())
            self.assertFalse(label.isHidden())
            spec = MP.defaults("N")
            spec["quantity"] = "Magnitude"
            field.apply(spec)
            self.assertTrue(load.ProfileData)
            self.assertEqual(study.Status, "NotRun")
            self.assertEqual(field.mode.currentData(), "Segments")
            self.assertTrue(magnitude.isHidden())
            self.assertTrue(label.isHidden())
            field.apply(MP.defaults("N", "Constant") | {"quantity": "Magnitude"})
            self.assertTrue(magnitude.isHidden())
            self.assertTrue(label.isHidden())
            self.assertFalse(field.constant.isHidden())
            fixture.doc.abortTransaction()
            self.assertFalse(load.ProfileData)
            self.assertEqual(study.ResultData, "saved result")
            field.deleteLater()
            container.deleteLater()
        finally:
            fixture.tearDown()

    def test_solver_motor_matches_preview(self):
        import Dynamics
        from CommandCreateSimulation import Motion
        from AssemblyTests.TestDynamics import TestDynamics
        fixture = TestDynamics()
        fixture.setUp()
        try:
            ground = fixture.box("Ground", density=None)
            ground.setPropertyStatus("Placement", "ReadOnly")
            body = fixture.box()
            joint = fixture.joint("Revolute", ground, body)
            study = fixture.study(False)
            study.EndTime = "0.2 s"
            study.Tolerance = 1e-11
            study.MaximumStep = "0.001 s"
            motion = fixture.doc.addObject("App::FeaturePython", "Motion")
            Motion(motion, "Angular", joint, "")
            study.addObject(motion)
            spec = MP.defaults("deg")
            spec["segments"] = [[.1, 5, "Smooth"], [.1, 0, "Smooth"]]
            spec["outside"] = "Repeat"
            for quantity in ("Position", "Velocity", "Acceleration"):
                for mode in ("Kinematics", "Dynamics"):
                    spec["quantity"] = quantity
                    MP.assign(motion, spec)
                    study.AnalysisType = mode
                    data = Dynamics.run(study)
                    profile = MP.Profile(spec)
                    peak_acceleration = max(abs(profile.sample(i*.2/200, 2)) for i in range(201))
                    # Kinematics solves the derivatives directly; forward
                    # dynamics integrates them. Allow 0.1% of peak acceleration
                    # for the latter at joins where quintic jerk changes.
                    acceleration_tolerance = max(1e-6, peak_acceleration*1e-3) if mode == "Dynamics" else 1e-6
                    for i, time in enumerate(data["Times"]):
                        self.assertAlmostEqual(data["Bodies"][body.Name]["AngularVelocity"][i][2], profile.sample(time, 1), delta=1e-5)
                        self.assertAlmostEqual(data["Bodies"][body.Name]["AngularAcceleration"][i][2], profile.sample(time, 2), delta=acceleration_tolerance, msg=f"{quantity} {mode} t={time}")
                    self.assertTrue(motion.ProfileData)
        finally:
            fixture.tearDown()

    def test_solver_load_profile_and_persistence(self):
        import os
        import tempfile
        import FreeCAD as App
        import Dynamics
        from AssemblyTests.TestDynamics import TestDynamics
        fixture = TestDynamics()
        fixture.setUp()
        try:
            body = fixture.box()
            study = fixture.study(False)
            study.Tolerance = 1e-11
            study.MaximumStep = "0.0005 s"
            load = Dynamics.create_load(study, "Force", body)
            load.Direction = App.Vector(1, 0, 0)
            load.AttachmentI.Base = App.Vector(5, 10, 15)
            spec = MP.defaults("N", "Data points")
            spec.update(quantity="Magnitude", points=[[0,0], [.05,.003], [.1,.006]], interpolation="Linear")
            MP.assign(load, spec)
            data = Dynamics.run(study)
            self.assertAlmostEqual(data["Loads"][load.Name]["ForceX"][-1], .006, delta=1e-9)
            # At the hold boundary the force slope changes. Check a smooth
            # interior sample and the integrated impulse independently.
            index = min(range(len(data["Times"])), key=lambda i: abs(data["Times"][i]-.05))
            self.assertAlmostEqual(data["Bodies"][body.Name]["Acceleration"][index][0], 10000*data["Times"][index], delta=.02)
            self.assertAlmostEqual(data["Bodies"][body.Name]["Velocity"][-1][0], 50, delta=.02)
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "profile.FCStd")
                fixture.doc.saveAs(path)
                name, saved = load.Name, load.ProfileData
                App.closeDocument(fixture.doc.Name)
                fixture.doc = App.openDocument(path)
                self.assertEqual(fixture.doc.getObject(name).ProfileData, saved)
        finally:
            fixture.tearDown()
