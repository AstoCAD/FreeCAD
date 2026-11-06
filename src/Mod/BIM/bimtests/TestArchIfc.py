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

    def _export_hidden_objects_model(self, exclude_hidden):
        """Exports a site with visible and hidden boxes, directly in a level and in an App::Part.
        Returns the sorted names of the exported elements."""
        import Arch
        from importers import exportIFC

        def box(name, x, visible):
            obj = self.document.addObject("Part::Box", name)
            obj.Placement.Base = FreeCAD.Vector(x, 0, 0)
            obj.Visibility = visible
            return obj

        part = self.document.addObject("App::Part", "Part")
        part.addObject(box("PartVisible", 0, True))
        part.addObject(box("PartHidden", 100, False))
        level = Arch.makeFloor(
            [part, box("LevelVisible", 200, True), box("LevelHidden", 300, False)]
        )
        site = Arch.makeSite([Arch.makeBuilding([level])])
        self.document.recompute()

        preferences = exportIFC.getPreferences()
        preferences["EXCLUDE_HIDDEN"] = exclude_hidden
        path = os.path.join(tempfile.mkdtemp(), "hidden_objects.ifc")
        exportIFC.export([site], path, preferences=preferences)
        ifcfile = ifcopenshell.open(path)
        return sorted(e.Name for e in ifcfile.by_type("IfcElement"))

    def test_export_hidden_objects_by_default(self):
        """Hidden objects are exported unless the option asks otherwise.
        https://github.com/FreeCAD/FreeCAD/issues/16293"""
        self.assertEqual(
            self._export_hidden_objects_model(False),
            ["LevelHidden", "LevelVisible", "Part", "PartHidden", "PartVisible"],
        )

    def test_export_exclude_hidden_objects(self):
        """With the "Exclude hidden objects" option, hidden objects are not exported.
        https://github.com/FreeCAD/FreeCAD/issues/16293"""
        self.assertEqual(
            self._export_hidden_objects_model(True),
            ["LevelVisible", "Part", "PartVisible"],
        )

    def test_remove_hidden_objects_keeps_containers_and_selection(self):
        """Hidden containers and explicitly exported hidden objects are kept.
        https://github.com/FreeCAD/FreeCAD/issues/16293"""
        from importers import exportIFC

        group = self.document.addObject("App::DocumentObjectGroup", "EmptyGroup")
        group.Visibility = False
        hidden = self.document.addObject("Part::Box", "Hidden")
        hidden.Visibility = False
        selected = self.document.addObject("Part::Box", "Selected")
        selected.Visibility = False
        visible = self.document.addObject("Part::Box", "Visible")
        objects = [group, hidden, selected, visible]
        self.assertEqual(
            exportIFC._remove_hidden_objects(objects, [selected]), [group, selected, visible]
        )
        self.assertEqual(
            exportIFC._remove_hidden_objects(objects, selected), [group, selected, visible]
        )

    def test_export_exclude_hidden_preference(self):
        """The EXCLUDE_HIDDEN export preference follows Mod/Arch/IfcExportExcludeHidden,
        which is off by default. https://github.com/FreeCAD/FreeCAD/issues/16293"""
        from importers import exportIFC

        group = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Arch")
        stored = group.GetBools()
        old = group.GetBool("IfcExportExcludeHidden", False)
        try:
            if "IfcExportExcludeHidden" in stored:
                group.RemBool("IfcExportExcludeHidden")
            self.assertFalse(exportIFC.getPreferences()["EXCLUDE_HIDDEN"])
            group.SetBool("IfcExportExcludeHidden", True)
            self.assertTrue(exportIFC.getPreferences()["EXCLUDE_HIDDEN"])
        finally:
            if "IfcExportExcludeHidden" in stored:
                group.SetBool("IfcExportExcludeHidden", old)
            else:
                group.RemBool("IfcExportExcludeHidden")

    def test_export_nested_compound_placement(self):
        """Nested Part_Compounds are exported at their own placement.
        https://github.com/FreeCAD/FreeCAD/issues/9324"""
        import Arch
        import ifcopenshell.geom
        import ifcopenshell.util.shape
        from importers import exportIFC

        box1 = self.document.addObject("Part::Box", "Box1")
        box2 = self.document.addObject("Part::Box", "Box2")
        box2.Placement.Base = FreeCAD.Vector(100, 0, 0)
        inner = self.document.addObject("Part::Compound", "Inner")
        inner.Links = [box1, box2]
        inner.Placement.Base = FreeCAD.Vector(0, 500, 0)
        box3 = self.document.addObject("Part::Box", "Box3")
        box3.Placement.Base = FreeCAD.Vector(0, 0, 200)
        outer = self.document.addObject("Part::Compound", "Outer")
        outer.Links = [inner, box3]
        outer.Placement.Base = FreeCAD.Vector(1000, 0, 0)
        site = Arch.makeSite([Arch.makeBuilding([Arch.makeFloor([outer])])])
        self.document.recompute()

        path = os.path.join(tempfile.mkdtemp(), "nested_compound.ifc")
        exportIFC.export([site], path)
        ifcfile = ifcopenshell.open(path)
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        mins = []
        maxs = []
        for product in ifcfile.by_type("IfcProduct"):
            if product.Representation and not product.is_a("IfcSpatialStructureElement"):
                shape = ifcopenshell.geom.create_shape(settings, product)
                verts = ifcopenshell.util.shape.get_vertices(shape.geometry) * 1000
                mins.append(verts.min(axis=0))
                maxs.append(verts.max(axis=0))
        self.assertTrue(mins, "nothing was exported")
        expected = outer.Shape.BoundBox
        exported = [min(m[i] for m in mins) for i in range(3)]
        exported += [max(m[i] for m in maxs) for i in range(3)]
        for got, exp in zip(
            exported,
            [
                expected.XMin,
                expected.YMin,
                expected.ZMin,
                expected.XMax,
                expected.YMax,
                expected.ZMax,
            ],
        ):
            self.assertAlmostEqual(got, exp, delta=1e-3, msg=f"{exported} != {expected}")

    def _check_imported_wall(self):
        walls = [o for o in self.document.Objects if o.Label == "TestWall"]
        self.assertEqual(len(walls), 1, "the IFC wall was not imported")
        self.assertFalse(walls[0].Shape.isNull())
        self.assertAlmostEqual(walls[0].Shape.Volume, 5000 * 3000 * 200, delta=1)

    def test_export_wall_on_single_edge_base(self):
        """A wall whose base shape is a single edge (e.g. a Draft arc) must export its
        axis; scaling the read-only base shape used to raise ReferenceError."""
        import Arch
        import Draft
        from importers import exportIFC

        arc = Draft.make_circle(2000, startangle=0, endangle=90)
        wall = Arch.makeWall(arc, width=200, height=3000)
        site = Arch.makeSite([Arch.makeBuilding([Arch.makeFloor([wall])])])
        self.document.recompute()
        self.assertEqual(arc.Shape.ShapeType, "Edge")

        path = os.path.join(tempfile.mkdtemp(), "arc_wall.ifc")
        exportIFC.export([site], path)
        ifcfile = ifcopenshell.open(path)
        walls = ifcfile.by_type("IfcWall")
        self.assertEqual(len(walls), 1)
        reps = walls[0].Representation.Representations
        axes = [r for r in reps if r.RepresentationIdentifier == "Axis"]
        self.assertEqual(len(axes), 1)
        curve = axes[0].Items[0]
        self.assertTrue(curve.is_a("IfcCompositeCurve"))
        circle = curve.Segments[0].ParentCurve.BasisCurve
        self.assertTrue(circle.is_a("IfcCircle"))
        # the axis is scaled to meters, the base arc itself is untouched
        self.assertAlmostEqual(circle.Radius, 2.0, places=6)
        self.assertAlmostEqual(arc.Shape.Curve.Radius, 2000, places=6)

    def test_export_closed_wire_curve_is_closed(self):
        """The polyline curve of a closed wire ends at its first point, otherwise
        the closing segment is lost (e.g. in 2D annotations and closed profiles)."""
        import Arch
        import Draft
        from importers import exportIFC

        rect = Draft.make_rectangle(1000, 500)
        site = Arch.makeSite([Arch.makeBuilding([Arch.makeFloor([rect])])])
        self.document.recompute()

        preferences = exportIFC.getPreferences()
        preferences["EXPORT_2D"] = True
        path = os.path.join(tempfile.mkdtemp(), "closed_wire.ifc")
        exportIFC.export([site], path, preferences=preferences)
        ifcfile = ifcopenshell.open(path)
        curves = ifcfile.by_type("IfcIndexedPolyCurve")
        self.assertEqual(len(curves), 1)
        coords = curves[0].Points.CoordList
        self.assertEqual(len(coords), 5)
        self.assertEqual(coords[0], coords[-1])
        corners = sorted(set((round(c[0], 6), round(c[1], 6)) for c in coords))
        self.assertEqual(corners, [(0.0, 0.0), (0.0, 0.5), (1.0, 0.0), (1.0, 0.5)])

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

    def test_lock_document_keeps_empty_building_parts(self):
        """Converting to strict IFC mode keeps an empty building and its levels
        when there is no site.
        https://github.com/FreeCAD/FreeCAD/issues/24926"""
        import Arch
        from nativeifc import ifc_status

        level1 = Arch.makeFloor()
        level1.Label = "Level1"
        level2 = Arch.makeFloor()
        level2.Label = "Level2"
        building = Arch.makeBuilding([level1, level2])
        building.Label = "Building"
        self.document.recompute()

        ifc_status.lock_document()

        self.assertIn("IfcFilePath", self.document.PropertiesList)
        ifcfile = self.document.Proxy.ifcfile
        self.assertEqual(
            sorted(e.Name for e in ifcfile.by_type("IfcBuildingStorey")), ["Level1", "Level2"]
        )
        self.assertEqual([e.Name for e in ifcfile.by_type("IfcBuilding")], ["Building"])
        self.assertIn("IfcBuilding", [getattr(o, "IfcClass", None) for o in self.document.Objects])

    def test_can_expand_site_with_expanded_building(self):
        """A site whose only child (the building) is already loaded cannot be expanded.
        https://github.com/FreeCAD/FreeCAD/issues/21913"""
        import Arch
        from nativeifc import ifc_status
        from nativeifc import ifc_tools

        wall = Arch.makeWall(None, 2000, 200, 3000)
        level = Arch.makeFloor([wall])
        building = Arch.makeBuilding([level])
        Arch.makeSite([building])
        self.document.recompute()

        ifc_status.lock_document()
        ifcfile = self.document.Proxy.ifcfile
        objs = {getattr(o, "IfcClass", None): o for o in self.document.Objects}
        site = objs["IfcSite"]
        building = objs["IfcBuilding"]
        self.assertIn(building, site.Group)
        self.assertFalse(ifc_tools.can_expand(site, ifcfile))
        # the building's storey is not loaded yet
        self.assertNotIn("IfcBuildingStorey", objs)
        self.assertTrue(ifc_tools.can_expand(building, ifcfile))
