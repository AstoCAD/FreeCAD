# SPDX-License-Identifier: LGPL-2.1-or-later
"""Regression tests for complex-section sketch placement and profile compatibility."""

import math
from pathlib import Path
import re
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import PartDesign
    import Sketcher
    import TechDraw
    import TechDrawGui
    from PySide import QtCore


@unittest.skipUnless(App.GuiUp, "GUI tests require FreeCAD GUI mode")
class TestComplexSectionPlacementGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        self.previous_document = App.ActiveDocument.Name if App.ActiveDocument else None
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.addCleanup(self._cleanup)
        self.assertIn("TechDrawWorkbench", Gui.listWorkbenches())
        Gui.activateWorkbench("TechDrawWorkbench")
        self.doc = App.newDocument("ComplexSectionBodyPlacement")
        self.directory = tempfile.TemporaryDirectory(prefix="complex-section-body-")
        self.addCleanup(self.directory.cleanup)

    def _pump(self, milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _cleanup(self):
        if self.doc is not None and self.doc.Name in App.listDocuments():
            Gui.Selection.clearSelection()
            App.closeDocument(self.doc.Name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._pump()
        if self.previous_document and self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    @staticmethod
    def _vector_tuple(vector):
        return tuple(round(value, 6) for value in (vector.x, vector.y, vector.z))

    def _geometry(self, view):
        result = []
        for edge in view.getVisibleEdges():
            points = tuple(self._vector_tuple(point) for point in edge.discretize(Number=9))
            self.assertTrue(all(math.isfinite(value) for point in points for value in point))
            result.append((round(edge.Length, 6), min(points, tuple(reversed(points)))))
        return tuple(sorted(result))

    def _wait_geometry(self, view, require_nonempty=True):
        deadline = time.monotonic() + 12.0
        previous = None
        stable = 0
        latest = ()
        while time.monotonic() < deadline:
            self._pump()
            latest = self._geometry(view)
            finished = "Up-to-date" in view.State
            if latest == previous and finished:
                stable += 1
            else:
                stable = 0
            if stable >= 3:
                if require_nonempty:
                    self.assertTrue(
                        latest, "Completed TechDraw projection must contain visible geometry"
                    )
                return latest
            previous = latest
        self.fail(
            "TechDraw projection did not finish: "
            + view.Name
            + " state="
            + repr(list(view.State))
            + " edges="
            + str(len(latest))
        )

    def _page(self, name):
        page = self.doc.addObject("TechDraw::DrawPage", name)
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", name + "Template")
        template_file = Path(__file__).with_name("TestTemplate.svg")
        self.assertTrue(template_file.is_file())
        template.Template = str(template_file)
        page.Template = template
        page.Scale = 1.0
        return page

    def _base_view(self, page, source, placement, name):
        view = self.doc.addObject("TechDraw::DrawViewPart", name)
        page.addView(view)
        view.Source = [source]
        view.Direction = placement.Rotation.multVec(App.Vector(0, 0, 1))
        view.XDirection = placement.Rotation.multVec(App.Vector(1, 0, 0))
        view.ScaleType = "Custom"
        view.Scale = 1.0
        view.X = 100.0
        view.Y = 150.0
        view.ViewObject.ShowSectionLine = True
        view.ViewObject.IncludeCutLine = True
        view.ViewObject.SectionLineColor = (1.0, 0.0, 0.0)
        return view

    def _section(self, page, source, base, profile, placement, name):
        section = self.doc.addObject("TechDraw::DrawComplexSection", name)
        section.SectionSymbol = "A"
        page.addView(section)
        section.Source = [source]
        section.BaseView = base
        section.CuttingToolWireObject = profile
        section.ProjectionStrategy = self.projection_strategy
        section.Direction = placement.Rotation.multVec(App.Vector(0, 1, 0))
        section.SectionNormal = placement.Rotation.multVec(App.Vector(0, 1, 0))
        section.XDirection = placement.Rotation.multVec(App.Vector(1, 0, 0))
        section.SectionOrigin = placement.multVec(App.Vector(20, 15, 10))
        section.ScaleType = "Custom"
        section.Scale = 1.0
        section.X = 100.0
        section.Y = 75.0
        return section

    @staticmethod
    def _canonical_svg_value(value):
        number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
        return re.sub(number, lambda match: str(round(float(match.group()), 6)), value)

    def _section_line_svg(self, page):
        Gui.getDocument(self.doc.Name).getObject(page.Name).show()
        self._pump(100)
        path = Path(self.directory.name) / (page.Name + ".svg")
        TechDrawGui.exportPageAsSvg(page, str(path))
        self.assertTrue(path.is_file())
        result = []
        geometry_tags = {"path", "line", "polyline", "polygon", "circle", "ellipse"}
        geometry_attributes = {"d", "points", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry"}

        def collect(element, inherited_stroke="", transforms=()):
            style = {}
            for item in element.get("style", "").split(";"):
                if ":" in item:
                    key, value = item.split(":", 1)
                    style[key.strip()] = value.strip()
            stroke = element.get("stroke", style.get("stroke", inherited_stroke))
            transform = element.get("transform", "")
            current_transforms = transforms + (
                (self._canonical_svg_value(transform),) if transform else ()
            )
            tag = element.tag.rsplit("}", 1)[-1]
            if stroke.lower() == "#ff0000" and tag in geometry_tags:
                attributes = tuple(
                    sorted(
                        (key, self._canonical_svg_value(value))
                        for key, value in element.attrib.items()
                        if key in geometry_attributes
                    )
                )
                result.append((tag, attributes, current_transforms))
            for child in element:
                collect(child, stroke, current_transforms)

        collect(ET.parse(path).getroot())
        return tuple(sorted(result))

    def _compare(self, placement, contained=True, strategy="Offset", linked=False, nested=False):
        self.projection_strategy = strategy
        body = self.doc.addObject("PartDesign::Body", "Body")
        base = body.newObject("PartDesign::Feature", "Base")
        base.Shape = Part.makeBox(40, 30, 10).cut(Part.makeCylinder(3, 10, App.Vector(12, 15, 0)))
        body.Placement = placement
        global_placement = placement
        if nested:
            outer = self.doc.addObject("App::Part", "OuterPart")
            outer.Placement = App.Placement(
                App.Vector(8, 12, 4), App.Rotation(App.Vector(1, 0, 0), 25)
            )
            outer.addObject(body)
            global_placement = outer.Placement.multiply(placement)
            self.assertIn(body, outer.Group)
        first = (
            body.newObject("Sketcher::SketchObject", "BodyCutProfile")
            if contained
            else self.doc.addObject("Sketcher::SketchObject", "FreeCutProfile")
        )
        first.addGeometry(Part.LineSegment(App.Vector(-5, 15, 0), App.Vector(45, 15, 0)), False)
        local_profile = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        first.Placement = local_profile if contained else global_placement.multiply(local_profile)
        body.Tip = base
        self.doc.recompute()
        self.assertTrue(base.Shape.isValid())
        self.assertEqual(len(base.Shape.Solids), 1)
        self.assertAlmostEqual(base.Shape.Volume, 12000.0 - math.pi * 90.0, places=6)

        expected_source = self.doc.addObject("Part::Feature", "GlobalSource")
        expected_source.Shape = base.Shape.copy()
        expected_source.Placement = base.getGlobalPlacement()
        expected_profile = self.doc.addObject("Sketcher::SketchObject", "GlobalCutProfile")
        expected_profile.addGeometry(
            Part.LineSegment(App.Vector(-5, 15, 0), App.Vector(45, 15, 0)), False
        )
        expected_profile.Placement = global_placement.multiply(local_profile)
        self.doc.recompute()
        expected_placement = expected_profile.getGlobalPlacement()
        actual_placement = first.getGlobalPlacement()
        for point in (App.Vector(), App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)):
            self.assertLess(
                (actual_placement.multVec(point) - expected_placement.multVec(point)).Length,
                1e-8,
                "The two public sketch placements must describe the identical global plane",
            )
        if contained:
            self.assertIn(first, body.Group)
        else:
            self.assertNotIn(first, body.Group)

        if linked:
            self.assertFalse(contained)
            occurrence = self.doc.addObject("App::Link", "ProfileOccurrence")
            occurrence.setLink(first)
            occurrence.LinkTransform = False
            occurrence.Placement = first.Placement
            self.doc.recompute()
            located = Part.getShape(occurrence, retType=2)[0]
            self.assertFalse(located.isNull())
            self.assertTrue(located.isValid())
            self.assertEqual(
                self._shape_geometry(located),
                self._shape_geometry(expected_profile.Shape),
                "Real Link profile must resolve to the same independent global wire before section comparison",
            )
            first = occurrence

        actual_page = self._page("ContainedPage")
        expected_page = self._page("EquivalentPage")
        actual_view = self._base_view(actual_page, base, global_placement, "ContainedView")
        expected_view = self._base_view(
            expected_page, expected_source, global_placement, "EquivalentView"
        )
        self.doc.recompute()
        expected_base = self._wait_geometry(expected_view)
        actual_base = self._wait_geometry(actual_view)
        self.assertTrue(
            expected_base, "Standalone reference source must render before section comparison"
        )
        self.assertEqual(
            actual_base, expected_base, "Both source views must use the same global geometry"
        )

        expected_section = self._section(
            expected_page,
            expected_source,
            expected_view,
            expected_profile,
            global_placement,
            "EquivalentSection",
        )
        actual_section = self._section(
            actual_page, base, actual_view, first, global_placement, "ContainedSection"
        )
        self.doc.recompute()
        expected_edges = self._wait_geometry(expected_section)
        self.assertTrue(
            expected_edges,
            "Standalone global section must complete before judging contained profile",
        )
        self.assertNotIn("Invalid", expected_section.State)
        actual_edges = self._wait_geometry(actual_section)
        expected_line = self._section_line_svg(expected_page)
        actual_line = self._section_line_svg(actual_page)
        self.assertTrue(expected_line, "Standalone global section must export a real red cut line")
        with self.subTest(oracle="section_geometry_matches_global_equivalent"):
            self.assertNotIn("Invalid", actual_section.State)
            self.assertEqual(actual_edges, expected_edges)
        with self.subTest(oracle="rendered_cut_line_matches_global_equivalent"):
            self.assertTrue(actual_line)
            self.assertEqual(actual_line, expected_line)

        return {
            "actual_section": actual_section.Name,
            "expected_section": expected_section.Name,
            "actual_page": actual_page.Name,
            "expected_page": expected_page.Name,
            "section_geometry": expected_edges,
            "section_line": expected_line,
        }

    def _shape_geometry(self, shape):
        result = []
        for edge in shape.Edges:
            points = tuple(self._vector_tuple(point) for point in edge.discretize(Number=9))
            self.assertTrue(all(math.isfinite(value) for point in points for value in point))
            result.append((round(edge.Length, 6), min(points, tuple(reversed(points)))))
        return tuple(sorted(result))

    def test_aligned_identity_body_control(self):
        self._compare(App.Placement(), strategy="Aligned")

    def test_aligned_uncontained_global_profile_control(self):
        self._compare(
            App.Placement(App.Vector(8, 12, 4), App.Rotation(App.Vector(1, 0, 0), 25)),
            contained=False,
            strategy="Aligned",
        )

    def test_offset_real_link_identity_profile_control(self):
        self._compare(App.Placement(), contained=False, linked=True)

    def test_nested_part_body_profile_matches_global_equivalent(self):
        self._compare(App.Placement(), nested=True)

    def test_identity_body_save_reopen_preserves_geometry_and_cut_line(self):
        expected = self._compare(App.Placement())
        model = Path(self.directory.name) / "ComplexSectionIdentity.FCStd"
        self.doc.saveAs(str(model))
        old_name = self.doc.Name
        Gui.Selection.clearSelection()
        App.closeDocument(old_name)
        self.doc = None
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        self._pump()
        self.assertNotIn(old_name, App.listDocuments())
        self.doc = App.openDocument(str(model))
        self.doc.recompute()
        for name in (expected["actual_section"], expected["expected_section"]):
            section = self.doc.getObject(name)
            self.assertIsNotNone(section)
            self.assertEqual(section.CuttingToolWireObject.TypeId, "Sketcher::SketchObject")
            self.assertNotIn("Invalid", section.State)
            self.assertEqual(self._wait_geometry(section), expected["section_geometry"])
        for name in (expected["actual_page"], expected["expected_page"]):
            page = self.doc.getObject(name)
            self.assertIsNotNone(page)
            self.assertEqual(self._section_line_svg(page), expected["section_line"])

    def test_identity_body_control(self):
        self._compare(App.Placement())

    def test_translated_body_matches_global_equivalent(self):
        self._compare(App.Placement(App.Vector(0, 10, 0), App.Rotation()))

    def test_rotated_body_matches_global_equivalent(self):
        self._compare(App.Placement(App.Vector(8, 12, 4), App.Rotation(App.Vector(1, 0, 0), 25)))

    def test_uncontained_global_profile_control(self):
        self._compare(
            App.Placement(App.Vector(8, 12, 4), App.Rotation(App.Vector(1, 0, 0), 25)),
            contained=False,
        )
