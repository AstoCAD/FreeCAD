# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2018 Bernd Hahnebach <bernd@bimstatik.org>              *
# *   Copyright (c) 2020 Sudhanshu Dubey <sudhanshu.thethunder@gmail.com>   *
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

__title__ = "Solver z88 FEM unit tests"
__author__ = "Bernd Hahnebach"
__url__ = "https://www.freecad.org"

import unittest
from os import listdir
from os.path import join
from os.path import isfile

import FreeCAD

from femsolver.z88 import z88tools
from . import support_utils as testtools
from .support_utils import fcc_print
from .support_utils import get_namefromdef


class TestSolverZ88(unittest.TestCase):
    fcc_print("import TestSolverZ88")

    # ********************************************************************************************
    def setUp(self):
        # setUp is executed before every test

        # new document
        self.document = FreeCAD.newDocument(self.__class__.__name__)

        # more inits
        self.mesh_name = "Mesh"

    # ********************************************************************************************
    def tearDown(self):
        # tearDown is executed after every test
        FreeCAD.closeDocument(self.document.Name)

    # ********************************************************************************************
    def test_00print(self):
        # since method name starts with 00 this will be run first
        # this test just prints a line with stars

        fcc_print(
            "\n{0}\n{1} run FEM TestSolverFrameWork tests {2}\n{0}".format(
                100 * "*", 10 * "*", 55 * "*"
            )
        )

    # ********************************************************************************************
    def test_ccx_cantilever_ele_hexa20(self):
        from femexamples.ccx_cantilever_ele_hexa20 import setup

        setup(self.document, "z88", test_mode=True)
        self.inputfile_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_ele_tria6(self):
        from femexamples.ccx_cantilever_ele_tria6 import setup

        setup(self.document, "z88")
        self.inputfile_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_faceload(self):
        from femexamples.ccx_cantilever_faceload import setup

        setup(self.document, "z88", test_mode=True)
        self.inputfile_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_ccx_cantilever_nodeload(self):
        from femexamples.ccx_cantilever_nodeload import setup

        setup(self.document, "z88", test_mode=True)
        self.inputfile_writing_test(get_namefromdef("test_"))

    # ********************************************************************************************
    def test_axisymmetric_pressure_radius(self):
        # The pressure on an axisymmetric edge is multiplied by 2*pi*R, R taken from the
        # mid node of the edge. Z88 renumbers the nodes, so the mesh node ids must not
        # be used: an unused node (id 1) shifts the numbering, ids from 101 leave a gap.
        import math
        import Fem
        import ObjectsFem
        import Part

        for first_id, unused_node in ((2, True), (101, False)):
            with self.subTest(first_id=first_id, unused_node=unused_node):
                doc = self.document
                for obj in doc.Objects:
                    doc.removeObject(obj.Name)
                face = doc.addObject("Part::Feature", "Face")
                # x is the radius: x from 10 to 20, y from 0 to 10
                face.Shape = Part.makePlane(10, 10, FreeCAD.Vector(10, 0, 0))
                analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
                solver = analysis.addObject(ObjectsFem.makeSolverZ88(doc, "SolverZ88"))[0]
                solver.ModelSpace = "axisymmetric"
                material = analysis.addObject(ObjectsFem.makeMaterialSolid(doc, "Material"))[0]
                mat = material.Material
                mat["Name"] = "Steel"
                mat["YoungsModulus"] = "210000 MPa"
                mat["PoissonRatio"] = "0.3"
                material.Material = mat
                fixed = analysis.addObject(ObjectsFem.makeConstraintFixed(doc, "Fixed"))[0]
                pressure = analysis.addObject(ObjectsFem.makeConstraintPressure(doc, "Pressure"))[0]
                pressure.Pressure = "1 MPa"
                for i, edge in enumerate(face.Shape.Edges, start=1):
                    bb = edge.BoundBox
                    if math.isclose(bb.XMin, 20) and math.isclose(bb.XMax, 20):
                        pressure.References = [(face, f"Edge{i}")]
                    elif math.isclose(bb.YMin, 0) and math.isclose(bb.YMax, 0):
                        fixed.References = [(face, f"Edge{i}")]

                # one quad8 element, corner nodes first, then mid nodes
                femmesh = Fem.FemMesh()
                if unused_node:
                    femmesh.addNode(0, 0, 0, 1)
                coords = (
                    (10, 0, 0),
                    (20, 0, 0),
                    (20, 10, 0),
                    (10, 10, 0),
                    (15, 0, 0),
                    (20, 5, 0),
                    (15, 10, 0),
                    (10, 5, 0),
                )
                node_ids = []
                for i, (x, y, z) in enumerate(coords):
                    femmesh.addNode(x, y, z, first_id + i)
                    node_ids.append(first_id + i)
                femmesh.addFace(node_ids, 1)
                mesh = analysis.addObject(ObjectsFem.makeMeshGmsh(doc, self.mesh_name))[0]
                mesh.FemMesh = femmesh
                mesh.Shape = face
                doc.recompute()

                working_dir = testtools.get_fem_test_tmp_dir("solver_z88_axisymmetric_pressure")
                solver.WorkingDirectory = working_dir
                z88tools.Z88Tools(solver).prepare()

                with open(join(working_dir, "z88i5.txt")) as f:
                    rows = f.read().split("\n")
                self.assertEqual(rows[0], "1")
                load = float(rows[1].split()[1])
                # 1 MPa * 2 * pi * 20 mm
                self.assertAlmostEqual(load, 2 * math.pi * 20, places=4)

    # ********************************************************************************************
    def inputfile_writing_test(self, base_name):
        self.document.recompute()

        # start
        fcc_print(f"\n------------- Start of FEM Z88 tests for {base_name} -------")

        # get analysis working directory and save FreeCAD file
        working_dir = testtools.get_fem_test_tmp_dir("solver_z88_" + base_name)
        save_fc_file = join(working_dir, base_name + ".FCStd")
        fcc_print(f"Save FreeCAD file to {save_fc_file} ...")
        self.document.saveAs(save_fc_file)

        # write input file
        self.document.SolverZ88.WorkingDirectory = working_dir
        tool = z88tools.Z88Tools(self.document.SolverZ88)
        tool.prepare()

        # compare created input files with the given input files
        test_path = join(testtools.get_fem_test_home_dir(), "z88", base_name)
        test_files = [f for f in listdir(test_path) if isfile(join(test_path, f))]
        # fcc_print(sorted(test_files))
        not_files = ["__init__.py"]
        test_files = [f for f in test_files if f not in not_files]
        fcc_print(test_files)
        for test_file in test_files:
            inpfile_given = join(test_path, test_file)
            inpfile_totest = join(working_dir, test_file)
            fcc_print(f"Comparing {inpfile_given}  to  {inpfile_totest}")
            ret = testtools.compare_inp_files(inpfile_given, inpfile_totest)
            self.assertFalse(ret, f"Z88 write_inp_file for {base_name} test failed.\n{ret}")

        # end
        fcc_print(f"--------------- End of FEM Z88 tests for {base_name} ---------")
