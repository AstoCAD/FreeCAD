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

    def test_remove_property_keeps_valueless_properties(self):
        """Removing a property must not delete the property set while it still holds
        properties that get_psets() leaves out because they have no value."""
        from nativeifc import ifc_psets
        from nativeifc import ifc_tools

        model, wall = _make_wall_file()
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="Pset_Custom")
        single = model.createIfcPropertySingleValue("Single", None, model.createIfcLabel("one"))
        empty = model.createIfcPropertySingleValue("Empty", None, None)
        pset.HasProperties = [single, empty]
        path = os.path.join(tempfile.mkdtemp(), "remove_property.ifc")
        model.write(path)

        ifc_tools.create_document(self.document, path, shapemode=1, strategy=2, silent=True)
        self.document.recompute()
        obj = [o for o in self.document.Objects if getattr(o, "IfcClass", "") == "IfcWall"][0]
        ifcfile = ifc_tools.get_ifcfile(obj)

        # what ifc_observer does when the user deletes the dynamic property
        ifc_psets.remove_property(obj, "Single")
        psets = [p for p in ifcfile.by_type("IfcPropertySet") if p.Name == "Pset_Custom"]
        self.assertEqual(len(psets), 1, "the property set was deleted with its valueless property")
        self.assertEqual([p.Name for p in psets[0].HasProperties], ["Empty"])

        # removing the last property still removes the property set
        ifcopenshell.api.run("pset.edit_pset", ifcfile, pset=psets[0], properties={"Empty": "x"})
        ifc_psets.remove_property(obj, "Empty")
        psets = [p for p in ifcfile.by_type("IfcPropertySet") if p.Name == "Pset_Custom"]
        self.assertEqual(psets, [])

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
        importIFC.insert(path, self.document.Name, preferences=prefs)
        self._check_imported_wall()

    def test_legacy_import_singlecore(self):
        """Same as above, through the single-core code path of importIFC.insert.
        https://github.com/FreeCAD/FreeCAD/issues/33854"""
        from importers import importIFC, importIFCHelper

        model, _ = _make_wall_file()
        prefs = importIFCHelper.getPreferences()
        importIFC.insert(model, self.document.Name, preferences=prefs)
        self._check_imported_wall()
