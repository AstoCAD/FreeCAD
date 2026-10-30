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
