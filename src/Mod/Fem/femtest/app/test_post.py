# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 The FreeCAD project association AISBL
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

__title__ = "FEM App post-processing object unit tests"

import unittest

import FreeCAD
import Fem  # noqa: F401 (registers the FEM document object types)

from .support_utils import fcc_print


class TestPostGroups(unittest.TestCase):
    fcc_print("import TestPostGroups")

    def setUp(self):
        self.document = FreeCAD.newDocument(self.__class__.__name__)
        if "Fem::FemPostBranchFilter" not in self.document.supportedTypes():
            FreeCAD.closeDocument(self.document.Name)
            self.skipTest("FEM was built without VTK post-processing")

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def test_00print(self):
        fcc_print(
            "\n{0}\n{1} run FEM TestPostGroups tests {2}\n{0}".format(
                100 * "*", 10 * "*", 55 * "*"
            )
        )

    def test_branch_filter_with_non_filter_child(self):
        # The Group property of a branch filter can hold any object when it is set from
        # Python. Setting up the VTK pipeline used to treat every child as a post filter,
        # which crashed (access violation) as soon as a non-filter object was in the group.
        branch = self.document.addObject("Fem::FemPostBranchFilter", "Branch")
        other = self.document.addObject("App::DocumentObjectGroup", "Other")
        clip = self.document.addObject("Fem::FemPostScalarClipFilter", "Clip")

        branch.Group = [other]
        self.document.recompute()
        self.assertEqual(branch.Group, [other])

        branch.Group = [other, clip]
        branch.Mode = "Parallel"
        branch.Mode = "Serial"
        self.document.recompute()
        self.assertIn(clip, branch.Group)
        self.assertIn(other, branch.Group)

    def test_write_vtk_without_data(self):
        # writeVTK of a post object that holds no data yet (a new pipeline) crashed
        import os
        import tempfile

        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline")
        self.document.recompute()
        path = os.path.join(tempfile.gettempdir(), "fem_post_write_without_data.vtu")
        with self.assertRaises(ValueError):
            pipeline.writeVTK(path)
        self.assertFalse(os.path.exists(path))

    def test_import_vtk_result_pipeline(self):
        # importing a VTK file as result pipeline set the view display mode unconditionally
        # and failed without GUI, leaving a pipeline that was never recomputed
        import os
        import tempfile
        from feminout import importVTKResults

        mesh = Fem.FemMesh()
        for i, point in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]):
            mesh.addNode(*point, i + 1)
        mesh.addVolume([1, 2, 3, 4], 1)
        path = os.path.join(tempfile.gettempdir(), "fem_post_import_result.vtu")
        mesh.write(path)
        try:
            FreeCAD.setActiveDocument(self.document.Name)
            pipeline = importVTKResults.importVtkVtkResult(path, "ImportedResult")
        finally:
            os.remove(path)
        self.assertEqual(pipeline.TypeId, "Fem::FemPostPipeline")
        self.assertTrue(pipeline.isValid())

    def test_multistep_without_data(self):
        # a multistep pipeline from a file VTK can't read or from results without a mesh crashed
        import os
        import tempfile

        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline")
        bad = os.path.join(tempfile.gettempdir(), "fem_post_multistep_unreadable.vtk")
        with open(bad, "w") as f:
            f.write("not a vtk file\n")
        try:
            with self.assertRaisesRegex(OSError, "could not be read"):
                pipeline.read([bad, bad], [1.0, 2.0], FreeCAD.Units.Unit(), "Time")
        finally:
            os.remove(bad)

        results = [
            self.document.addObject("Fem::FemResultObject", "Result1"),
            self.document.addObject("Fem::FemResultObject", "Result2"),
        ]
        with self.assertRaisesRegex(ValueError, "Result mesh object"):
            pipeline.load(results, [1.0, 2.0], FreeCAD.Units.Unit(), "Time")

    def test_group_cannot_contain_itself(self):
        # A pipeline or branch filter holding itself (directly or through another group)
        # used to crash: a branch on recompute (VTK pipeline loop), a pipeline on reopen
        # (endless recomputeChildren recursion).
        import os
        import tempfile

        pipeline = self.document.addObject("Fem::FemPostPipeline", "Pipeline")
        branch = self.document.addObject("Fem::FemPostBranchFilter", "Branch")
        branch2 = self.document.addObject("Fem::FemPostBranchFilter", "Branch2")
        clip = self.document.addObject("Fem::FemPostScalarClipFilter", "Clip")

        with self.assertRaises(RuntimeError):
            pipeline.Group = [pipeline]
        self.assertEqual(pipeline.Group, [])
        with self.assertRaises(RuntimeError):
            branch.Group = [clip, branch]
        self.assertEqual(branch.Group, [clip])

        branch2.Group = [branch]
        with self.assertRaises(RuntimeError):
            branch.Group = [clip, branch2]
        self.assertEqual(branch.Group, [clip])

        pipeline.Group = [branch2]
        with self.assertRaises(RuntimeError):
            branch.Group = [clip, pipeline]
        self.assertEqual(branch.Group, [clip])
        self.document.recompute()

        # valid nesting is kept, also after reopening
        self.assertEqual(pipeline.Group, [branch2])
        self.assertEqual(branch2.Group, [branch])
        path = os.path.join(tempfile.mkdtemp(), "post_group_cycle.FCStd")
        self.document.saveAs(path)
        name = self.document.Name
        FreeCAD.closeDocument(name)
        self.document = FreeCAD.openDocument(path)
        self.document.recompute()
        pipeline = self.document.getObject("Pipeline")
        self.assertEqual([o.Name for o in pipeline.Group], ["Branch2"])
        os.remove(path)
        os.rmdir(os.path.dirname(path))
