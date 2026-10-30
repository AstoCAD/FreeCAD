# SPDX-License-Identifier: LGPL-2.1-or-later
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

"""Unit tests for the IFC helpers of the BIM workbench (need ifcopenshell)."""

import os
import tempfile
import unittest

import FreeCAD
from bimtests import TestArchBase

try:
    import ifcopenshell
    import ifcopenshell.api

    _HAS_IFCOPENSHELL = True
except ImportError:
    _HAS_IFCOPENSHELL = False


def _make_wall_file():
    """Returns an in-memory IFC4 file containing one wall with a body representation"""

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
    building = run("root.create_entity", model, ifc_class="IfcBuilding")
    storey = run("root.create_entity", model, ifc_class="IfcBuildingStorey")
    run("aggregate.assign_object", model, relating_object=project, products=[site])
    run("aggregate.assign_object", model, relating_object=site, products=[building])
    run("aggregate.assign_object", model, relating_object=building, products=[storey])
    wall = run("root.create_entity", model, ifc_class="IfcWall", name="TestWall")
    rep = run(
        "geometry.add_wall_representation",
        model,
        context=body,
        length=5,
        height=3,
        thickness=0.2,
    )
    run("geometry.assign_representation", model, product=wall, representation=rep)
    run("spatial.assign_container", model, relating_structure=storey, products=[wall])
    return model, wall


@unittest.skipUnless(_HAS_IFCOPENSHELL, "ifcopenshell not available")
class TestArchIfc(TestArchBase.TestArchBase):

    def test_get_psets_enumerated_value(self):
        """IfcPropertyEnumeratedValue has no NominalValue and must not break get_psets.
        https://github.com/FreeCAD/FreeCAD/issues/31872"""
        from nativeifc import ifc_psets

        model, wall = _make_wall_file()
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_Custom")
        single = model.createIfcPropertySingleValue("Single", None, model.createIfcLabel("one"))
        empty = model.createIfcPropertySingleValue("Empty", None, None)
        enum1 = model.createIfcPropertyEnumeratedValue(
            "Condition", None, (model.createIfcLabel("btaHeated"),)
        )
        enum2 = model.createIfcPropertyEnumeratedValue(
            "Several", None, (model.createIfcLabel("a"), model.createIfcLabel("b"))
        )
        pset.HasProperties = [single, empty, enum1, enum2]

        psets = ifc_psets.get_psets(wall)
        self.assertEqual(
            psets["Pset_Custom"],
            {
                "Single": "IfcLabel('one')",
                "Condition": "IfcLabel('btaHeated')",
                "Several": "IfcLabel('a::b')",
            },
        )

    def test_export_app_part_skips_base_objects(self):
        """The base objects of BIM objects inside an App::Part must not be exported.
        https://github.com/FreeCAD/FreeCAD/issues/28368"""
        import Arch
        import Draft
        from importers import exportIFC

        rect = Draft.makeRectangle(1000, 500)
        ext = self.document.addObject("Part::Extrusion", "Extrusion")
        ext.Base = rect
        ext.DirMode = "Custom"
        ext.Dir = FreeCAD.Vector(0, 0, 1)
        ext.LengthFwd = 50
        ext.Solid = True
        equipment = Arch.makeEquipment(ext)
        part = self.document.addObject("App::Part", "Part")
        part.addObject(equipment)
        level = Arch.makeFloor([part])
        building = Arch.makeBuilding([level])
        site = Arch.makeSite([building])
        self.document.recompute()
        # the App::Part also holds the base objects of the equipment
        self.assertIn(ext, part.Group)
        self.assertEqual(Arch.pruneIncluded(part.Group, strict=True, silent=True), [equipment])

        path = os.path.join(tempfile.mkdtemp(), "app_part.ifc")
        exportIFC.export([site], path)
        ifcfile = ifcopenshell.open(path)
        # every element apart from the assembly itself
        elements = [
            e
            for e in ifcfile.by_type("IfcElement")
            if not e.is_a("IfcElementAssembly") and not e.is_a("IfcOpeningElement")
        ]
        names = sorted(e.Name for e in elements)
        self.assertEqual(names, [equipment.Label])

    def _check_imported_wall(self):
        walls = [o for o in self.document.Objects if o.Label == "TestWall"]
        self.assertEqual(len(walls), 1, "the IFC wall was not imported")
        self.assertFalse(walls[0].Shape.isNull())
        self.assertAlmostEqual(walls[0].Shape.Volume, 5000 * 3000 * 200, delta=1)

    def test_legacy_import_multicore(self):
        """The legacy (non-native) IFC importer must work with IfcOpenShell 0.8.
        https://github.com/FreeCAD/FreeCAD/issues/33854"""
        from importers import importIFC, importIFCHelper

        model, _ = _make_wall_file()
        path = os.path.join(tempfile.mkdtemp(), "legacy_import.ifc")
        model.write(path)
        prefs = importIFCHelper.getPreferences()
        importIFC.insert(path, self.document.Name, prefs)
        self._check_imported_wall()

    def test_legacy_import_singlecore(self):
        """Same as above, through the single-core code path of importIFC.insert.
        https://github.com/FreeCAD/FreeCAD/issues/33854"""
        from importers import importIFC, importIFCHelper

        model, _ = _make_wall_file()
        prefs = importIFCHelper.getPreferences()
        importIFC.insert(model, self.document.Name, prefs)
        self._check_imported_wall()
