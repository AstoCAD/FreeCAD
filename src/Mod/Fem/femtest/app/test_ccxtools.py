# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2015 Przemo Firszt <przemo@firszt.eu>                   *
# *   Copyright (c) 2015 Bernd Hahnebach <bernd@bimstatik.org>              *
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

__title__ = "CcxTools FEM unit tests"
__author__ = "Bernd Hahnebach"
__url__ = "https://www.freecad.org"

import unittest
from os.path import join

import FreeCAD

from . import support_utils as testtools
from .support_utils import fcc_print
from .support_utils import get_namefromdef
from femtools import ccxtools


class TestCcxTools(unittest.TestCase):
    fcc_print("import TestCcxTools")

    # ********************************************************************************************
    def setUp(self):
        # setUp is executed before every test

        # new document
        self.document = FreeCAD.newDocument(self.__class__.__name__)

        # directory pre face in name
        self.pre_dir_name = "ccxtools_"

        # more inits
        self.mesh_name = "Mesh"
        self.test_file_dir = join(
            testtools.get_fem_test_home_dir(),
            "calculix",  # TODO rename directory to "ccxtools" or rename the solver to calculix
        )

    # ********************************************************************************************
    def tearDown(self):
        # tearDown is executed after every test
        FreeCAD.closeDocument(self.document.Name)

    # ********************************************************************************************
    def test_00print(self):
        # since method name starts with 00 this will be run first
        # this test just prints a line with stars

        fcc_print(
            "\n{0}\n{1} run FEM TestCcxTools tests {2}\n{0}".format(100 * "*", 10 * "*", 62 * "*")
        )

    # ********************************************************************************************
    def test_calculixtools_missing_prerequisites(self):
        # https://github.com/FreeCAD/FreeCAD/issues/23085
        # the CalculiX solver tool must report analysis setup errors and not write the input file
        try:
            from femsolver.calculix import calculixtools
        except ImportError as e:
            self.skipTest(f"CalculiX solver tool not available: {e}")
        from femtools.objecttools import PrerequisiteError
        import ObjectsFem

        analysis = ObjectsFem.makeAnalysis(self.document, "Analysis")
        solver = ObjectsFem.makeSolverCalculiX(self.document, "SolverCalculiX")
        analysis.addObject(solver)
        # an empty mesh and no material
        analysis.addObject(self.document.addObject("Fem::FemMeshObject", self.mesh_name))
        solver.WorkingDirectory = testtools.get_fem_test_tmp_dir(
            self.pre_dir_name + "missing_prerequisites"
        )
        self.document.recompute()

        tool = calculixtools.CalculiXTools(solver)
        with self.assertRaises(PrerequisiteError) as cm:
            tool.prepare()
        self.assertIn("No material object defined in the analysis.", str(cm.exception))
        self.assertEqual(tool.model_file, "")

    # ********************************************************************************************
    def test_prerequisites_density(self):
        # the input file writer needs the density for a centrifugal load and for a transient
        # thermomechanical analysis, the prerequisites must report a material without it
        from femexamples.ccx_cantilever_faceload import setup
        import ObjectsFem

        setup(self.document, "ccxtools")
        solver = self.document.CalculiXCcxTools

        def density_message():
            fea = ccxtools.FemToolsCcx(self.document.Analysis, solver, test_mode=True)
            fea.update_objects()
            return "No Density defined" in fea.check_prerequisites()

        self.assertFalse(density_message())

        centrif = ObjectsFem.makeConstraintCentrif(self.document)
        centrif.RotationAxis = [(self.document.Box, "Edge1")]
        self.document.Analysis.addObject(centrif)
        self.assertTrue(density_message())
        self.document.removeObject(centrif.Name)
        self.assertFalse(density_message())

        mat_obj = self.document.FemMaterial
        mat = mat_obj.Material
        mat["ThermalConductivity"] = "43 W/m/K"
        mat["ThermalExpansionCoefficient"] = "12 um/m/K"
        mat["SpecificHeat"] = "590 J/kg/K"
        mat_obj.Material = mat
        solver.AnalysisType = "thermomech"
        solver.ThermoMechSteadyState = True
        self.assertFalse(density_message())
        solver.ThermoMechSteadyState = False
        self.assertTrue(density_message())

    # ********************************************************************************************
    def test_prerequisites_displacement_empty_references(self):
        # a displacement constraint whose geometry was deleted has no references left,
        # the prerequisites must name it (and not fail when there is no fixed constraint)
        from femexamples.ccx_cantilever_faceload import setup
        import ObjectsFem

        setup(self.document, "ccxtools")
        for obj in self.document.Analysis.Group:
            if obj.isDerivedFrom("Fem::ConstraintFixed"):
                self.document.removeObject(obj.Name)
        displacement = ObjectsFem.makeConstraintDisplacement(self.document, "EmptyDisplacement")
        self.document.Analysis.addObject(displacement)

        fea = ccxtools.FemToolsCcx(
            self.document.Analysis, self.document.CalculiXCcxTools, test_mode=True
        )
        fea.update_objects()
        self.assertIn("EmptyDisplacement has empty references.", fea.check_prerequisites())

    # ********************************************************************************************
    def test_fluid_section_liquid_pump(self):
        # CalculiX reads an unused first entry, then the pairs flow rate, total head,
        # with at most 16 entries per line
        from femsolver.calculix.write_femelement_geometry import liquid_section_def
        import ObjectsFem

        fluid = ObjectsFem.makeElementFluid1D(self.document)
        fluid.LiquidSectionType = "LIQUID PUMP"
        fluid.PumpFlowRate = [0, 1.04e-04, 2.08e-4]
        fluid.PumpHeadLoss = [30, 29.17, 26.67]
        self.assertEqual(
            liquid_section_def(fluid, "LIQUID PUMP"),
            "0,0,30,0.000104,29.17,0.000208,26.67\n",
        )

        fluid.PumpFlowRate = [float(i) for i in range(9)]
        fluid.PumpHeadLoss = [float(20 - i) for i in range(9)]
        self.assertEqual(
            liquid_section_def(fluid, "LIQUID PUMP"),
            "0,0,20,1,19,2,18,3,17,4,16,5,15,6,14\n7,13,8,12\n",
        )

    # ********************************************************************************************
    def test_fluid_section_pipe_white_colebrook(self):
        # CalculiX reads area, hydraulic diameter, length (nonpositive: from the end nodes),
        # grain diameter and form factor
        from femsolver.calculix.write_femelement_geometry import liquid_section_def
        import ObjectsFem

        fluid = ObjectsFem.makeElementFluid1D(self.document)
        fluid.LiquidSectionType = "PIPE WHITE-COLEBROOK"
        fluid.ColebrookeArea = "12.5 mm^2"
        fluid.ColebrookeRadius = "2 mm"
        fluid.ColebrookeGrainDiameter = "0.1 mm"
        fluid.ColebrookeFormFactor = 1.0
        self.assertEqual(
            liquid_section_def(fluid, "PIPE WHITE-COLEBROOK"),
            "12.5,4,-1,0.1,1\n",
        )

    # ********************************************************************************************
    def test_box_frequency(self):
        # set up
        from femexamples.boxanalysis_frequency import setup

        setup(self.document, "ccxtools", test_mode=True)
        base_name = get_namefromdef("test_")
        res_obj_name = "CCX_EigenMode_1_Results"
        analysis_dir = testtools.get_fem_test_tmp_dir(self.pre_dir_name + base_name)

        # test input file writing
        fea = self.input_file_writing_test(
            base_name,
            analysis_dir=analysis_dir,
            test_end=True,
        )

        # test result reading
        self.result_reading_test(
            base_name,
            analysis_dir=analysis_dir,
            fea=fea,
            res_obj_name=res_obj_name,
        )

    def test_box_static(self):
        # set up
        from femexamples.boxanalysis_static import setup

        setup(self.document, "ccxtools", test_mode=True)
        base_name = get_namefromdef("test_")
        res_obj_name = "CCX_Results"
        analysis_dir = testtools.get_fem_test_tmp_dir(self.pre_dir_name + base_name)

        # test input file writing
        fea = self.input_file_writing_test(
            base_name,
            analysis_dir=analysis_dir,
            test_end=True,
        )

        # test result reading
        self.result_reading_test(
            base_name,
            analysis_dir=analysis_dir,
            fea=fea,
            res_obj_name=res_obj_name,
        )

    # ********************************************************************************************
    def test_ccx_buckling_flexuralbuckling(self):
        from femexamples.ccx_buckling_flexuralbuckling import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_beam_circle(self):
        from femexamples.ccx_cantilever_beam_circle import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_beam_pipe(self):
        from femexamples.ccx_cantilever_beam_pipe import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_beam_rect(self):
        from femexamples.ccx_cantilever_beam_rect import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_hexa20(self):
        from femexamples.ccx_cantilever_ele_hexa20 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_quad4(self):
        from femexamples.ccx_cantilever_ele_quad4 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_quad8(self):
        from femexamples.ccx_cantilever_ele_quad8 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_seg2(self):
        from femexamples.ccx_cantilever_ele_seg2 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_seg3(self):
        from femexamples.ccx_cantilever_ele_seg3 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_tria3(self):
        from femexamples.ccx_cantilever_ele_tria3 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_tria6(self):
        from femexamples.ccx_cantilever_ele_tria6 import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_faceload(self):
        from femexamples.ccx_cantilever_faceload import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_nodeload(self):
        from femexamples.ccx_cantilever_nodeload import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_prescribeddisplacement(self):
        from femexamples.ccx_cantilever_prescribeddisplacement import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_centrif(self):
        # TODO does pass on my local machine, but not on ci
        return

        from femexamples.constraint_centrif import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_contact_shell_shell(self):
        from femexamples.constraint_contact_shell_shell import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_contact_solid_solid(self):
        # TODO does pass on my local machine, but not on ci
        return

        from femexamples.constraint_contact_solid_solid import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_sectionprint(self):
        from femexamples.constraint_section_print import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_selfweight_cantilever(self):
        from femexamples.constraint_selfweight_cantilever import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_tie(self):
        from femexamples.constraint_tie import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_transform_beam_hinged(self):
        from femexamples.constraint_transform_beam_hinged import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_constraint_transform_torque(self):
        from femexamples.constraint_transform_torque import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_frequency_beamsimple(self):
        from femexamples.frequency_beamsimple import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_material_multiple_bendingbeam_fiveboxes(self):
        from femexamples.material_multiple_bendingbeam_fiveboxes import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_material_multiple_bendingbeam_fivefaces(self):
        from femexamples.material_multiple_bendingbeam_fivefaces import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_material_multiple_tensionrod_twoboxes(self):
        from femexamples.material_multiple_tensionrod_twoboxes import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_material_nonlinear(self):
        from femexamples.material_nl_platewithhole import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_square_pipe_end_twisted_edgeforces(self):
        from femexamples.square_pipe_end_twisted_edgeforces import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_square_pipe_end_twisted_nodeforces(self):
        from femexamples.square_pipe_end_twisted_nodeforces import setup

        setup(self.document, "ccxtools")
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_thermomech_bimetal(self):
        from femexamples.thermomech_bimetal import setup

        setup(self.document, "ccxtools", test_mode=True)
        self.input_file_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def input_file_writing_test(
        self,
        base_name,
        analysis_dir=None,
        test_end=False,
    ):
        fcc_print(f"\n--------------- Start of FEM ccxtools {base_name} test---------------")

        if analysis_dir is None:
            analysis_dir = testtools.get_fem_test_tmp_dir(self.pre_dir_name + base_name)
        analysis = self.document.Analysis
        solver_object = self.document.CalculiXCcxTools
        fea = ccxtools.FemToolsCcx(analysis, solver_object, test_mode=True)
        fea.update_objects()

        fcc_print(f"Setting up working directory {analysis_dir}")
        fea.setup_working_dir(analysis_dir)
        self.assertTrue(
            True if fea.working_dir == analysis_dir else False,
            f"Setting working directory {analysis_dir} failed",
        )

        fcc_print(f"Checking FEM inp file prerequisites for {base_name} ...")
        error = fea.check_prerequisites()
        self.assertFalse(
            error,
            f"ccxtools check_prerequisites returned error message: {error}",
        )

        inpfile_given = join(self.test_file_dir, (base_name + ".inp"))
        inpfile_totest = join(analysis_dir, (self.mesh_name + ".inp"))
        fcc_print("Checking FEM inp file write...")
        fcc_print(f"Writing {inpfile_totest} for {base_name}")
        error = fea.write_inp_file()
        self.assertFalse(error, "Writing failed")

        fcc_print(f"Comparing {inpfile_given} to {inpfile_totest}")
        ret = testtools.compare_inp_files(inpfile_given, inpfile_totest)
        self.assertFalse(ret, f"ccxtools write_inp_file test failed.\n{ret}")

        if test_end is True:
            # do not save and print End of tests
            return fea

        save_fc_file = join(analysis_dir, base_name + ".FCStd")
        fcc_print(f"Save FreeCAD file for {base_name} to {save_fc_file}...")
        self.document.saveAs(save_fc_file)

        fcc_print(f"\n--------------- End of FEM ccxtools {base_name}---------------")

    # ********************************************************************************************
    def result_reading_test(
        self,
        base_name,
        analysis_dir,
        fea,
        res_obj_name,
    ):
        inpfile_given = join(self.test_file_dir, (base_name + ".inp"))

        fcc_print(
            "Setting up working directory to {} in order to read simulated calculations".format(
                self.test_file_dir
            )
        )
        fea.setup_working_dir(self.test_file_dir)
        self.assertTrue(
            True if fea.working_dir == self.test_file_dir else False,
            f"Setting working directory {self.test_file_dir} failed",
        )

        fcc_print(f"Setting base name to read test {base_name}.frd file...")
        fea.set_base_name(base_name)
        self.assertTrue(
            True if fea.base_name == base_name else False,
            f"Setting base name to {base_name} failed",
        )

        fcc_print(f"Setting inp file name to read test {base_name}.frd file...")
        fea.set_inp_file_name()
        self.assertTrue(
            True if fea.inp_file_name == inpfile_given else False,
            f"Setting inp file name to {inpfile_given} failed",
        )

        fcc_print(f"Checking FEM frd file read from {base_name}...")
        fea.load_results()
        self.assertTrue(
            fea.results_present,
            f"Cannot read results from {fea.base_name}.frd frd file",
        )

        fcc_print(f"Reading stats from result object for {base_name}...")
        expected_values = join(self.test_file_dir, base_name + "_expected_values")
        ret = testtools.compare_stats(fea, expected_values, res_obj_name)
        self.assertFalse(ret, "Invalid results read from .frd file")

        save_fc_file = join(analysis_dir, base_name + ".FCStd")
        fcc_print(f"Save FreeCAD file for {base_name} to {save_fc_file}...")
        self.document.saveAs(save_fc_file)

        fcc_print(f"--------------- End of {base_name} -------------------")


# ************************************************************************************************
def create_test_results():
    import os
    import shutil
    import unittest

    import FemGui
    from femresult import resulttools
    from femtools import ccxtools

    temp_dir = testtools.get_fem_test_tmp_dir()
    test_class = "femtest.app.test_ccxtools.TestCcxTools"  # unit test class
    stat_types = [
        "U1",
        "U2",
        "U3",
        "Uabs",
        "Sabs",
        "MaxPrin",
        "MidPrin",
        "MinPrin",
        "MaxShear",
        "Peeq",
        "Temp",
        "MFlow",
        "NPress",
    ]

    # ****************************************************************************
    # static cube
    print("create static result files")
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromName(test_class + ".test_static_analysis")
    )
    static_analysis_dir = join(temp_dir, "FEM_ccx_static")
    doc_static_cube = FreeCAD.open(join(static_analysis_dir, "cube_static.FCStd"))
    FemGui.setActiveAnalysis(doc_static_cube.Analysis)
    fea = ccxtools.FemToolsCcx()
    fea.update_objects()

    fea.reset_all()
    fea.run()
    fea.load_results()
    stats_static = []
    res_obj_static = doc_static_cube.getObject("CCX_Results")
    for s in stat_types:
        statval = resulttools.get_stats(res_obj_static, s)
        stats_static.append(f"{s}: ({statval[0]:.14g}, {statval[1]:.14g}, )\n")
    static_expected_values_file = join(static_analysis_dir, "cube_static_expected_values")
    f = open(static_expected_values_file, "w")
    for s in stats_static:
        f.write(s)
    f.close()
    frd_result_file = os.path.splitext(fea.inp_file_name)[0] + ".frd"
    dat_result_file = os.path.splitext(fea.inp_file_name)[0] + ".dat"
    frd_static_test_result_file = join(static_analysis_dir, "cube_static.frd")
    dat_static_test_result_file = join(static_analysis_dir, "cube_static.dat")
    shutil.copyfile(frd_result_file, frd_static_test_result_file)
    shutil.copyfile(dat_result_file, dat_static_test_result_file)
    print("Results copied to the appropriate FEM test dirs in: " + temp_dir)

    # ****************************************************************************
    # frequency cube
    print("create frequency result files")
    unittest.TextTestRunner().run(
        unittest.TestLoader().loadTestsFromName(test_class + ".test_freq_analysis")
    )
    frequency_analysis_dir = join(temp_dir, "FEM_ccx_frequency")
    doc_frequency_cube = FreeCAD.open(join(frequency_analysis_dir, "cube_frequency.FCStd"))
    FemGui.setActiveAnalysis(doc_frequency_cube.Analysis)
    fea = ccxtools.FemToolsCcx()
    fea.update_objects()
    fea.reset_all()
    # we should only have one result object 1 to 6 will be less than 0.01 and ignored
    fea.solver.EigenmodesCount = 7
    doc_frequency_cube.recompute()
    fea.run()
    fea.load_results()
    stats_frequency = []
    res_obj_freq = doc_frequency_cube.getObject("CCX_Mode7_Results")
    for s in stat_types:
        statval = resulttools.get_stats(res_obj_freq, s)
        stats_frequency.append(f"{s}: ({statval[0]:.14g}, {statval[1]:.14g})\n")
    frequency_expected_values_file = join(frequency_analysis_dir, "cube_frequency_expected_values")
    f = open(frequency_expected_values_file, "w")
    for s in stats_frequency:
        f.write(s)
    f.close()
    frd_result_file = os.path.splitext(fea.inp_file_name)[0] + ".frd"
    dat_result_file = os.path.splitext(fea.inp_file_name)[0] + ".dat"
    frd_frequency_test_result_file = join(frequency_analysis_dir, "cube_frequency.frd")
    dat_frequency_test_result_file = join(frequency_analysis_dir, "cube_frequency.dat")
    shutil.copyfile(frd_result_file, frd_frequency_test_result_file)
    shutil.copyfile(dat_result_file, dat_frequency_test_result_file)
    print("Results copied to the appropriate FEM test dirs in: " + temp_dir)


"""
update the results of FEM ccxtools unit tests:

from femtest.app.test_ccxtools import create_test_results
create_test_results()

copy result files
from unit_test_temp_directory/FEM_unittests/specific_test into the src directory
compare the results with git difftool
run make
start FreeCAD and run FEM unit test
if FEM unit test is fine --> commit new FEM unit test results

TODO compare the inp file of the helper with the inp file of FEM unit tests
TODO the better way: move the result creation inside the TestFem
and add some preference to deactivate this because it needs ccx
"""
