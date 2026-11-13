# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2018 Bernd Hahnebach <bernd@bimstatik.org>              *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

__title__ = "Results FEM unit tests"
__author__ = "Bernd Hahnebach"
__url__ = "https://www.freecad.org"

import unittest
from os.path import join

import FreeCAD

from . import support_utils as testtools
from .support_utils import fcc_print


class TestResult(unittest.TestCase):
    fcc_print("import TestResult")

    # ********************************************************************************************
    def setUp(self):
        # setUp is executed before every test

        # new document
        self.document = FreeCAD.newDocument(self.__class__.__name__)

    # ********************************************************************************************
    def tearDown(self):
        # tearDown is executed after every test
        FreeCAD.closeDocument(self.document.Name)

    # ********************************************************************************************
    def test_00print(self):
        # since method name starts with 00 this will be run first
        # this test just prints a line with stars
        fcc_print(
            "\n{0}\n{1} run FEM TestResult tests {2}\n{0}".format(100 * "*", 10 * "*", 64 * "*")
        )

    # ********************************************************************************************
    def get_stress_values(self):
        # stress at node 4 of CalculiX cantilever face load
        stress = (
            -4.52840e02,  # Sxx
            -1.94075e02,  # Syy
            -1.94075e02,  # Szz
            6.11223e01,  # Sxy
            -2.60754e01,  # Sxz
            6.92759e-05,  # Syz
        )
        return stress

    # ********************************************************************************************
    def test_stress_von_mises(self):
        expected_mises = 283.2082
        from femresult.resulttools import calculate_von_mises as vm

        mises = vm(self.get_stress_values())
        # fcc_print(round(mises, 4))
        self.assertEqual(
            round(mises, 4),
            expected_mises,
            "Calculated von Mises stress is not the expected value.",
        )

    # ********************************************************************************************
    def test_stress_principal_std(self):
        expected_principal = (-178.0076, -194.0749, -468.9075, 145.4499)
        from femresult.resulttools import calculate_principal_stress_std as pr

        prin = pr(self.get_stress_values())
        rounded_prin = (round(prin[0], 4), round(prin[1], 4), round(prin[2], 4), round(prin[3], 4))
        # fcc_print(rounded_prin)
        self.assertEqual(
            rounded_prin,
            expected_principal,
            "Calculated principal stresses are not the expected values.",
        )

    # ********************************************************************************************
    def test_stress_principal_reinforced(self):
        expected_principal = (-178.0076, -194.0749, -468.9075, 145.4499)
        from femresult.resulttools import calculate_principal_stress_reinforced as prrc

        prin = prrc(self.get_stress_values())
        rounded_prin = (round(prin[0], 4), round(prin[1], 4), round(prin[2], 4), round(prin[3], 4))
        # fcc_print(rounded_prin)
        self.assertEqual(
            rounded_prin,
            expected_principal,
            "Calculated principal reinforced stresses are not the expected values.",
        )

    # ********************************************************************************************
    def test_rho(self):
        data = (
            (
                # Case1: Governing Eq.14
                (2.000, -2.000, 5.000, 6.000, -4.000, 2.000),
                (0.02400, 0.00400, 0.01400),
            ),
            (
                # Case2: Governing Eq.10+
                (-3.000, -7.000, 0.000, 6.000, -4.000, 2.000),
                (0.00886, 0.00000, 0.00571),
            ),
            (
                # Case3: Governing Eq.5
                (-1.000, -7.000, 10.000, 0.000, 0.000, 5.000),
                (0.00000, 0.00000, 0.02714),
            ),
            (
                # Case4: Governing Eq.13
                (3.000, 0.000, 10.000, 0.000, 5.000, 0.000),
                (0.01600, 0.00000, 0.03000),
            ),
            (
                # Case5: Governing Eq.11-
                (10.000, 7.000, -3.000, 3.000, 1.000, -2.000),
                (0.02533, 0.02133, 0.00000),
            ),
            (
                # Case6: Governing Eq.14
                (4.000, -7.000, 3.000, 7.000, 0.000, -5.000),
                (0.02200, 0.01000, 0.01600),
            ),
            (
                # Case7: Governing Eq.14
                (8.000, -14.000, 6.000, 14.000, 0.000, -10.000),
                (0.04400, 0.02000, 0.03200),
            ),
            (
                # Case8: Governing Eq.17
                (1.000, 0.000, 3.000, 10.000, -8.000, 7.000),
                (0.02486, 0.01750, 0.01720),
            ),
            (
                # Case9: Governing Eq.13
                (0.000, 0.000, 0.000, 10.000, 8.000, 7.000),
                (0.03600, 0.03400, 0.03000),
            ),
            (
                # Case10: Governing Eq.13
                (15.000, 0.000, 0.000, 0.000, 0.000, 0.000),
                (0.03000, 0.00000, 0.00000),
            ),
            (
                # Case11: Governing Eq.13
                (0.000, 0.000, 0.000, 5.000, 0.000, 0.000),
                (0.01000, 0.01000, 0.00000),
            ),
        )

        from femresult.resulttools import calculate_rho as calrho

        for i, case in enumerate(data):
            res = calrho(case[0], 500)
            rhores = (round(res[0], 5), round(res[1], 5), round(res[2], 5))
            # fcc_print("Case{}: {}".format(i + 1 , rhores))
            self.assertEqual(rhores, case[1], f"Calculated rho are not the expected Case{i + 1}.")

    # ********************************************************************************************
    def test_disp_abs(self):
        expected_dispabs = 87.302986
        # x, y, z at node 4 of CalculiX cantilever face load
        disp_xyz = [FreeCAD.Vector(8.12900e00, 3.38889e-02, -8.69237e01)]
        from femresult.resulttools import calculate_disp_abs as dp

        disp_abs = round(dp(disp_xyz)[0], 6)
        # fcc_print(disp_abs)
        self.assertEqual(
            disp_abs, expected_dispabs, "Calculated displacement abs are not the expected values."
        )

    # ********************************************************************************************
    def test_show_result_types(self):
        # show_result passes the values of the requested result type to the coloring helper,
        # and for "None" resets the colors of the result object
        from unittest import mock
        import ObjectsFem
        from femresult import resulttools

        res = ObjectsFem.makeResultMechanical(self.document, "Result")
        res.DisplacementVectors = [FreeCAD.Vector(1, 2, 3), FreeCAD.Vector(4, 5, 6)]
        with mock.patch.object(resulttools, "show_color_by_scalar_with_cutoff") as show:
            for result_type, expected in (("U1", [1, 4]), ("U2", [2, 5]), ("U3", [3, 6])):
                resulttools.show_result(res, result_type)
                self.assertEqual(show.call_args.args[0], res)
                self.assertEqual(list(show.call_args.args[1]), expected, result_type)
        with mock.patch.object(resulttools, "reset_mesh_color") as reset:
            resulttools.show_result(res, "None")
            reset.assert_called_once_with(res)

    # ********************************************************************************************
    def test_z88_disp_import_directory_with_o2(self):
        # the mesh file z88i1.txt is read next to z88o2.txt, also when "o2" is in the directory
        import shutil
        import Fem
        from feminout import importZ88Mesh
        from feminout import importZ88O2Results

        work_dir = testtools.get_fem_test_tmp_dir("z88_o2_import")
        self.addCleanup(shutil.rmtree, work_dir, True)
        mesh = Fem.FemMesh()
        for i, p in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], 1):
            mesh.addNode(*p, i)
        mesh.addVolume([1, 2, 3, 4], 1)
        importZ88Mesh.write(mesh, join(work_dir, "z88i1.txt"))
        disp_file = join(work_dir, "z88o2.txt")
        with open(disp_file, "w") as f:
            f.write("header\n" * 5)
            for node in range(1, 5):
                f.write(f"{node} 0.0 0.0 {node * 0.25}\n")

        res = importZ88O2Results.import_z88_disp(disp_file)
        self.assertIsNotNone(res)
        self.assertEqual(res.Mesh.FemMesh.NodeCount, 4)
        self.assertAlmostEqual(max(res.DisplacementLengths), 1.0)

    # ********************************************************************************************
    def test_frd_import_close_eigenfrequencies(self):
        # https://github.com/FreeCAD/FreeCAD/issues/23083
        # frequencies of the rigid body modes of an unconstrained model differ only after the second
        # decimal, rounding them made the pipeline frame values equal: "Values need to be unique"
        if "BUILD_FEM_VTK" not in FreeCAD.__cmake__:
            self.skipTest("FEM was built without VTK, there is no result pipeline")
        import ObjectsFem
        from feminout import importCcxFrdResults

        frd_file = join(testtools.get_fem_test_home_dir(), "calculix", "box_frequency.frd")
        with open(frd_file) as f:
            lines = f.read().splitlines()
        # mesh, then the result blocks of eigenmode 1 (starting at the first PSTEP) up to 9999
        first_step = next(i for i, ln in enumerate(lines) if ln[4:10] == "1PSTEP")
        mesh_part = lines[:first_step]
        mode_part = lines[first_step:-1]
        frd_lines = list(mesh_part)
        for mode, freq in ((1, "1.00000E-03"), (2, "2.00000E-03")):
            for ln in mode_part:
                if ln[5:10] == "PMODE":
                    ln = ln[:30] + f"{mode:6d}" + ln[36:]
                elif ln[2:7] == "100CL":
                    ln = ln[:13] + freq + ln[24:]
                frd_lines.append(ln)
        frd_lines.append(lines[-1])
        test_frd = join(testtools.get_fem_test_tmp_dir("result_frd_freq"), "box_frequency.frd")
        with open(test_frd, "w") as f:
            f.write("\n".join(frd_lines) + "\n")

        analysis = ObjectsFem.makeAnalysis(self.document, "Analysis")
        importCcxFrdResults.importFrd(test_frd, analysis, "", "frequency")

        pipelines = analysis.getObjectsOfType("Fem::FemPostPipeline")
        self.assertEqual(len(pipelines), 1)
        frames = pipelines[0].getEnumerationsOfProperty("Frame")
        self.assertEqual(len(frames), 2, f"unexpected frames: {frames}")

    # ********************************************************************************************
    def test_frd_import_small_time_increments(self):
        # https://github.com/FreeCAD/FreeCAD/issues/13887
        # the result object names were made from the increment time rounded to two decimals,
        # all increments of a transient analysis with small time steps were named "Time_0.0"
        import ObjectsFem
        from feminout import importCcxFrdResults

        frd_file = join(testtools.get_fem_test_home_dir(), "calculix", "box_static.frd")
        with open(frd_file) as f:
            lines = f.read().splitlines()
        # mesh, then the result blocks of the only increment (from the first PSTEP) up to 9999
        first_step = next(i for i, ln in enumerate(lines) if ln[4:10] == "1PSTEP")
        mesh_part = lines[:first_step]
        step_part = lines[first_step:-1]
        frd_lines = list(mesh_part)
        for step_time in ("1.00000E-04", "2.50000E-04"):
            for ln in step_part:
                if ln[2:7] == "100CL":
                    ln = ln[:13] + step_time + ln[24:]
                frd_lines.append(ln)
        frd_lines.append(lines[-1])
        test_frd = join(testtools.get_fem_test_tmp_dir("result_frd_time"), "box_transient.frd")
        with open(test_frd, "w") as f:
            f.write("\n".join(frd_lines) + "\n")

        analysis = ObjectsFem.makeAnalysis(self.document, "Analysis")
        importCcxFrdResults.importFrd(test_frd, analysis, "CCX_", "thermomech")

        labels = sorted(
            obj.Label for obj in analysis.Group if obj.isDerivedFrom("Fem::FemResultObject")
        )
        self.assertEqual(labels, ["CCX_Time_0_0001_Results", "CCX_Time_0_00025_Results"])

    # ********************************************************************************************
    def test_fill_result_keeps_exact_time(self):
        # https://github.com/FreeCAD/FreeCAD/issues/13887
        # the Time property of a result object was rounded to two decimals
        import ObjectsFem
        from feminout import importToolsFem

        res_obj = ObjectsFem.makeResultMechanical(self.document, "Result")
        result_set = {"time": 2.5e-4, "temp": {1: 293.15, 2: 300.0}}
        importToolsFem.fill_femresult_mechanical(res_obj, result_set)
        self.assertEqual(res_obj.Temperature, [293.15, 300.0])
        self.assertEqual(res_obj.Time, 2.5e-4)

    # ********************************************************************************************
    def test_frd_import_multistep_node_number_gap(self):
        # the result mesh of the first result set was compacted (node numbers from 1 without
        # gaps), the meshes of the next result sets were not, but got the compacted NodeNumbers
        import ObjectsFem
        from feminout import importCcxFrdResults

        frd_file = join(testtools.get_fem_test_home_dir(), "calculix", "box_frequency.frd")
        with open(frd_file) as f:
            lines = f.read().splitlines()
        first_step = next(i for i, ln in enumerate(lines) if ln[4:10] == "1PSTEP")
        mesh_part = lines[:first_step]
        mode_part = lines[first_step:-1]

        # node numbers from 100 on get an offset of 1000: a gap in the node numbers
        def renumber(node):
            return node + 1000 if node >= 100 else node

        block = None

        def with_gap(ln):
            nonlocal block
            if ln.startswith("    2C"):
                block = "nodes"
            elif ln.startswith("    3C"):
                block = "elements"
            elif ln.startswith("  100C"):
                block = "results"
            elif ln.startswith(" -3"):
                block = None
            elif ln.startswith(" -1") and block in ("nodes", "results"):
                return ln[:3] + f"{renumber(int(ln[3:13])):10d}" + ln[13:]
            elif ln.startswith(" -2") and block == "elements":
                nodes = [int(ln[i : i + 10]) for i in range(3, len(ln), 10)]
                return " -2" + "".join(f"{renumber(n):10d}" for n in nodes)
            return ln

        frd_lines = [with_gap(ln) for ln in mesh_part]
        for mode, freq in ((1, "1.00000E-03"), (2, "2.00000E-03")):
            for ln in mode_part:
                if ln[5:10] == "PMODE":
                    ln = ln[:30] + f"{mode:6d}" + ln[36:]
                elif ln[2:7] == "100CL":
                    ln = ln[:13] + freq + ln[24:]
                frd_lines.append(with_gap(ln))
        frd_lines.append(lines[-1])
        test_frd = join(testtools.get_fem_test_tmp_dir("result_frd_gap"), "box_frequency.frd")
        with open(test_frd, "w") as f:
            f.write("\n".join(frd_lines) + "\n")

        analysis = ObjectsFem.makeAnalysis(self.document, "Analysis")
        importCcxFrdResults.importFrd(test_frd, analysis, "", "frequency")
        results = [o for o in analysis.Group if o.isDerivedFrom("Fem::FemResultObject")]
        self.assertEqual(len(results), 2)
        for res in results:
            mesh_nodes = res.Mesh.FemMesh.Nodes
            self.assertEqual(max(mesh_nodes), len(mesh_nodes), res.Name)
            self.assertTrue(all(n in mesh_nodes for n in res.NodeNumbers), res.Name)

    # ********************************************************************************************
    def test_vtk_result_read_write_bad_input(self):
        # Fem.readResult(file) without an object name, a file VTK could not read and
        # Fem.writeResult with an object without a FEM mesh crashed
        if "BUILD_FEM_VTK" not in FreeCAD.__cmake__:
            self.skipTest("FEM was built without VTK")
        import os
        import Fem

        tmp = testtools.get_fem_test_tmp_dir("result_vtk_bad_input")

        # writing: objects without a FEM mesh write nothing
        out = join(tmp, "nothing.vtu")
        Fem.writeResult(out, self.document.addObject("Fem::FemResultObject", "NoMesh"))
        Fem.writeResult(out, self.document.addObject("App::FeaturePython", "Other"))
        self.assertFalse(os.path.exists(out))

        # a result with a mesh is written and read back with the one argument form
        mesh = Fem.FemMesh()
        for i, p in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], 1):
            mesh.addNode(*p, i)
        mesh.addVolume([1, 2, 3, 4], 1)
        mesh_obj = self.document.addObject("Fem::FemMeshObject", "Mesh")
        mesh_obj.FemMesh = mesh
        result = self.document.addObject("Fem::FemResultObject", "Result")
        result.Mesh = mesh_obj
        good = join(tmp, "result.vtu")
        Fem.writeResult(good, result)
        self.assertTrue(os.path.exists(good))
        Fem.readResult(good)
        read_mesh = self.document.getObject("ResultMesh")
        self.assertIsNotNone(read_mesh)
        self.assertEqual(read_mesh.FemMesh.NodeCount, 4)
        self.document.removeObject(read_mesh.Name)

        # reading files VTK can't read creates nothing
        bad = join(tmp, "bad.vtk")
        with open(bad, "w") as f:
            f.write("hello\n")
        Fem.readResult(bad)
        Fem.readResult(bad, "NoSuchObject")
        Fem.readResult(join(tmp, "bad.xyz"), "NoSuchObject")
        self.assertIsNone(self.document.getObject("ResultMesh"))

    # ********************************************************************************************
    def test_result_files_non_ascii_path(self):
        # The frd converter and the pvd reader opened the file with a narrow std::ifstream, which
        # on Windows does not take the UTF-8 path: in a folder with non-ASCII characters the frd
        # results were silently lost and reading a pvd file failed
        if "BUILD_FEM_VTK" not in FreeCAD.__cmake__:
            self.skipTest("FEM was built without VTK")
        import os
        import Fem

        tmp = join(testtools.get_fem_test_tmp_dir("result_non_ascii_path"), "Pièce Ωμέγα 日本")
        os.makedirs(tmp)

        # frd: the static results become a block of their own next to the frd file
        frd_file = join(testtools.get_fem_test_home_dir(), "calculix", "box_static.frd")
        with open(frd_file) as f:
            lines = f.read().splitlines()
        test_frd = join(tmp, "box_static.frd")
        # LF line ends: the converter does not handle CR LF line ends
        with open(test_frd, "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        Fem.frdToVTK(test_frd, False)
        self.assertTrue(os.path.isfile(join(tmp, "box_staticStatic.vtm")), os.listdir(tmp))

        # pvd: a collection of two time steps
        mesh = Fem.FemMesh()
        for i, p in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], 1):
            mesh.addNode(*p, i)
        mesh.addVolume([1, 2, 3, 4], 1)
        mesh.write(join(tmp, "step0.vtu"))
        mesh.write(join(tmp, "step1.vtu"))
        pvd_file = join(tmp, "case.pvd")
        with open(pvd_file, "w", encoding="utf-8") as f:
            f.write(
                '<?xml version="1.0"?>\n'
                '<VTKFile type="Collection" version="0.1">\n'
                "<Collection>\n"
                '<DataSet timestep="0" group="" part="0" file="step0.vtu"/>\n'
                '<DataSet timestep="2.5" group="" part="0" file="step1.vtu"/>\n'
                "</Collection>\n"
                "</VTKFile>\n"
            )
        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline")
        pipeline.read(pvd_file)
        self.assertEqual(len(pipeline.getEnumerationsOfProperty("Frame")), 2)
