# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2025 Furgo
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

import os
import tempfile

import FreeCAD
import Arch
from bimtests import TestArchBase


class TestArchReference(TestArchBase.TestArchBase):

    def test_makeReference(self):
        """Test the makeReference function."""
        operation = "Testing makeReference..."
        self.printTestMessage(operation)

        obj = Arch.makeReference()
        self.assertIsNotNone(obj, "makeReference failed to create an object")
        self.assertEqual(obj.Label, "External Reference", "Incorrect default label for Reference")

    def test_wholeObjectSkipsBodyFeatures(self):
        """Test that a whole-object reference does not duplicate the features of a Body.

        See https://github.com/FreeCAD/FreeCAD/issues/27170
        """
        operation = "Testing whole-object reference of a PartDesign Body..."
        self.printTestMessage(operation)

        import Part
        import PartDesign
        import Sketcher

        # Build the referenced file: a Body containing a sketch, plus a standalone box
        srcdoc = FreeCAD.newDocument("TestArchReferenceSource")
        try:
            body = srcdoc.addObject("PartDesign::Body", "Body")
            sketch = body.newObject("Sketcher::SketchObject", "Sketch")
            sketch.addGeometry(Part.Circle(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 5))
            box = srcdoc.addObject("Part::Box", "Box")
            box.Placement.Base = FreeCAD.Vector(100, 0, 0)
            srcdoc.recompute()
            self.assertEqual(len(sketch.Shape.Edges), 1)
            filename = os.path.join(tempfile.mkdtemp(), "TestArchReferenceSource.FCStd")
            srcdoc.saveAs(filename)
        finally:
            FreeCAD.closeDocument(srcdoc.Name)
            FreeCAD.setActiveDocument(self.document.Name)

        try:
            ref = Arch.makeReference(filename)
            self.document.recompute()

            parts = ref.Proxy.parts
            self.assertIn("Body", parts)
            self.assertIn("Sketch", parts)
            self.assertIn("Box", parts)
            # the Body and the standalone box are used, the sketch inside the Body is not
            self.assertFalse(parts["Body"][3])
            self.assertTrue(parts["Sketch"][3])
            self.assertFalse(parts["Box"][3])
            self.assertEqual(len(ref.Shape.Solids), 1)
            self.assertEqual(len(ref.Shape.Edges), 12)
        finally:
            os.remove(filename)
            os.rmdir(os.path.dirname(filename))

    def test_wholeFileSkipsHiddenObjects(self):
        """A whole-file reference must not include hidden objects such as boolean inputs.

        https://github.com/FreeCAD/FreeCAD/issues/23142
        """
        source = FreeCAD.newDocument("TestArchReferenceHidden")
        try:
            box = source.addObject("Part::Box", "Box")
            box.Length = box.Width = box.Height = 10
            cyl = source.addObject("Part::Cylinder", "Cylinder")
            cyl.Radius = 3
            cyl.Height = 20
            common = source.addObject("Part::MultiCommon", "Common")
            common.Shapes = [box, cyl]
            source.recompute()
            # what the GUI does when it creates the boolean
            box.Visibility = False
            cyl.Visibility = False
            expected = common.Shape.Volume
            filename = os.path.join(tempfile.mkdtemp(), "TestArchReferenceHidden.FCStd")
            source.saveAs(filename)
        finally:
            FreeCAD.closeDocument(source.Name)
            FreeCAD.setActiveDocument(self.document.Name)

        try:
            ref = Arch.makeReference(filename)
            self.document.recompute()
            self.assertEqual(len(ref.Shape.Solids), 1)
            self.assertAlmostEqual(ref.Shape.Volume, expected, places=3)
        finally:
            try:
                os.remove(filename)
                os.rmdir(os.path.dirname(filename))
            except OSError:
                pass

    def test_ifcReferenceFollowsFileChanges(self):
        """An IFC reference must read the new file when its File changes, and the
        file again when it changed on disk; the first file read used to stay cached."""
        try:
            import ifcopenshell
            import ifcopenshell.api
        except ImportError:
            self.skipTest("ifcopenshell not available")

        def write_wall_file(path, length):
            run = ifcopenshell.api.run
            model = run("project.create_file", version="IFC4")
            project = run("root.create_entity", model, ifc_class="IfcProject", name="Project")
            run("unit.assign_unit", model)
            ctx = run("context.add_context", model, context_type="Model")
            body = run(
                "context.add_context",
                model,
                context_type="Model",
                context_identifier="Body",
                target_view="MODEL_VIEW",
                parent=ctx,
            )
            site = run("root.create_entity", model, ifc_class="IfcSite")
            run("aggregate.assign_object", model, relating_object=project, products=[site])
            wall = run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
            rep = run(
                "geometry.add_wall_representation",
                model,
                context=body,
                length=length,
                height=3,
                thickness=0.2,
            )
            run("geometry.assign_representation", model, product=wall, representation=rep)
            run("spatial.assign_container", model, relating_structure=site, products=[wall])
            model.write(path)

        folder = tempfile.mkdtemp()
        file1 = os.path.join(folder, "wall1.ifc")
        file2 = os.path.join(folder, "wall2.ifc")
        write_wall_file(file1, 1)
        write_wall_file(file2, 2)
        try:
            ref = Arch.makeReference(file1)
            self.document.recompute()
            self.assertAlmostEqual(ref.Shape.Volume, 1000 * 3000 * 200, delta=1)

            # another file
            ref.File = file2
            self.document.recompute()
            self.assertAlmostEqual(ref.Shape.Volume, 2000 * 3000 * 200, delta=1)

            # the same file, changed on disk (what the reload command does)
            write_wall_file(file2, 4)
            os.utime(file2, (1e9, 1e9))
            ref.Proxy.reload = True
            ref.touch()
            self.document.recompute()
            self.assertAlmostEqual(ref.Shape.Volume, 4000 * 3000 * 200, delta=1)
        finally:
            for path in (file1, file2):
                try:
                    os.remove(path)
                except OSError:
                    pass
            try:
                os.rmdir(folder)
            except OSError:
                pass
