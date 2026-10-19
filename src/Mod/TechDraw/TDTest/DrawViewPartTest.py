# SPDX-License-Identifier: LGPL-2.1-or-later

# basic test script for TechDraw module
# creates a page and 1 view


import FreeCAD
import unittest
from .TechDrawTestUtilities import createPageWithSVGTemplate
from PySide import QtCore

class DrawViewPartTest(unittest.TestCase):
    def setUp(self):
        """Creates a page"""
        FreeCAD.newDocument("TDPart")
        FreeCAD.setActiveDocument("TDPart")
        FreeCAD.ActiveDocument = FreeCAD.getDocument("TDPart")

        FreeCAD.ActiveDocument.addObject("Part::Box", "Box")

        self.page = createPageWithSVGTemplate()
        self.page.Scale = 5.0
        # page.ViewObject.show()    # unit tests run in console mode
        print("DrawViewPart test: page created")

    def tearDown(self):
        print("DrawViewPart test finished")
        FreeCAD.closeDocument("TDPart")

    def _waitUntil(self, predicate, timeout_ms=5000):
        timer = QtCore.QElapsedTimer()
        timer.start()
        while not predicate():
            if timer.elapsed() >= timeout_ms:
                return False
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(20, loop.quit)
            loop.exec_()
        return True

    def testMakeDrawViewPart(self):
        """Tests if a view can be added to page"""
        print("testing DrawViewPart")
        view = FreeCAD.ActiveDocument.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(view)
        FreeCAD.ActiveDocument.View.Source = [FreeCAD.ActiveDocument.Box]
        FreeCAD.ActiveDocument.recompute()

        #wait for threads to complete before checking result
        loop = QtCore.QEventLoop()

        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        timer.start(2000)   #2 second delay
        loop.exec_()

        edges = view.getVisibleEdges()
        self.assertEqual(len(edges), 4, "DrawViewPart has wrong number of edges")
        self.assertTrue("Up-to-date" in view.State, "DrawViewPart is not Up-to-date")

    def testDisplayStyleControlsHardHidden(self):
        """DisplayStyle controls hard hidden edges without changing other HLR options."""
        view = FreeCAD.ActiveDocument.addObject("TechDraw::DrawViewPart", "StyleView")

        self.assertEqual(view.DisplayStyle, "Visible Edges")
        self.assertFalse(view.HardHidden)
        hard_hidden_status = view.getPropertyStatus("HardHidden")
        self.assertIn(24, hard_hidden_status)  # App::Property::PropReadOnly
        self.assertIn(26, hard_hidden_status)  # App::Property::PropHidden

        view.DisplayStyle = "All Edges"
        self.assertTrue(view.HardHidden)

        view.DisplayStyle = "Hidden Edges"
        self.assertTrue(view.HardHidden)

        view.DisplayStyle = "Shaded with Edges"
        self.assertFalse(view.HardHidden)

        view.SmoothHidden = True
        view.SeamHidden = True
        view.DisplayStyle = "Shaded"
        self.assertTrue(view.SmoothHidden)
        self.assertTrue(view.SeamHidden)

    def testFormatGeometricEdgeStyleUpdate(self):
        """Changing a formatted edge's Qt style changes its exported dash pattern."""
        import tempfile
        import time
        import xml.etree.ElementTree as ET
        from pathlib import Path
        import FreeCADGui
        import Part
        import TechDrawGui

        document = FreeCAD.ActiveDocument
        source = document.addObject("Part::Feature", "Line")
        source.Shape = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(30, 0, 0))
        view = document.addObject("TechDraw::DrawViewPart", "FormattedView")
        self.page.addView(view)
        view.Source = [source]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.X = 50
        view.Y = 50
        document.recompute()

        def process_events():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

        deadline = time.monotonic() + 10
        while not view.getVisibleEdges() and time.monotonic() < deadline:
            process_events()
        self.assertEqual(len(view.getVisibleEdges()), 1)
        FreeCADGui.activeDocument().getObject(self.page.Name).show()
        process_events()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "style.svg"
            for style, expect_dashed in ((1, False), (2, True), (1, False)):
                with self.subTest(style=style, expect_dashed=expect_dashed):
                    view.formatGeometricEdge(0, style, 0.5, (1.0, 0.0, 0.0, 1.0), True)
                    view.recompute()
                    view.requestPaint()
                    process_events()
                    TechDrawGui.exportPageAsSvg(self.page, str(path))
                    patterns = [
                        element.get("stroke-dasharray", "none")
                        for element in ET.parse(path).getroot().iter()
                        if element.get("stroke") == "#ff0000"
                    ]
                    self.assertTrue(patterns, "Formatted red edge is missing from SVG")
                    self.assertEqual(
                        all(pattern not in ("", "none") for pattern in patterns),
                        expect_dashed,
                    )

    def testCosmeticEdgeStyle(self):
        """Explicit creation and Format styles reach the rendered cosmetic edges."""
        import tempfile
        import time
        import xml.etree.ElementTree as ET
        from pathlib import Path
        import FreeCADGui
        import TechDrawGui

        preferences = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/TechDraw/Decorations"
        )
        previous_style = preferences.GetInt("CenterLineStyle", 2)
        self.addCleanup(preferences.SetInt, "CenterLineStyle", previous_style)
        preferences.SetInt("CenterLineStyle", 2)
        document = FreeCAD.ActiveDocument
        view = document.addObject("TechDraw::DrawViewPart", "CosmeticView")
        self.page.addView(view)
        view.Source = [document.Box]
        view.Direction = FreeCAD.Vector(0, 0, 1)
        view.ScaleType = "Custom"
        view.Scale = 1
        view.X = 50
        view.Y = 50
        document.recompute()

        def process_events():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(50, loop.quit)
            loop.exec_()

        deadline = time.monotonic() + 10
        while not view.getVisibleEdges() and time.monotonic() < deadline:
            process_events()
        self.assertTrue(view.getVisibleEdges())
        vector = FreeCAD.Vector
        colors = (
            ((1.0, 0.0, 0.0, 1.0), "#ff0000"),
            ((0.0, 1.0, 0.0, 1.0), "#00ff00"),
            ((0.0, 0.0, 1.0, 1.0), "#0000ff"),
            ((0.0, 1.0, 1.0, 1.0), "#00ffff"),
            ((1.0, 0.0, 1.0, 1.0), "#ff00ff"),
            ((1.0, 1.0, 0.0, 1.0), "#ffff00"),
        )
        makers = (
            ("makeCosmeticLine", (vector(-5, 10, 0), vector(5, 10, 0))),
            ("makeCosmeticLine3D", (vector(-5, 0, 0), vector(5, 0, 0))),
            ("makeCosmeticCircle", (vector(0, 15, 0), 2.0)),
            ("makeCosmeticCircleArc", (vector(0, 20, 0), 2.0, 0.0, 180.0)),
            ("makeCosmeticCircle3d", (vector(5, 10, 5), 2.0)),
            ("makeCosmeticCircleArc3d", (vector(10, 10, 5), 2.0, 0.0, 180.0)),
        )
        tags = [
            getattr(view, name)(*arguments, 1, 0.5, color)
            for (name, arguments), (color, stroke) in zip(makers, colors)
        ]
        self.assertTrue(all(tags))
        FreeCADGui.activeDocument().getObject(self.page.Name).show()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cosmetic-style.svg"
            for style, expected_dashed in ((None, False), (2, True), (1, False)):
                with self.subTest(style=style):
                    if style is not None:
                        for tag, (color, stroke) in zip(tags, colors):
                            edge = view.getCosmeticEdge(tag)
                            edge.Format = {
                                "style": style, "weight": 0.5,
                                "color": color, "visible": True,
                            }
                    view.requestPaint()
                    process_events()
                    TechDrawGui.exportPageAsSvg(self.page, str(path))
                    patterns = {stroke: [] for color, stroke in colors}

                    def collect_patterns(element, inherited):
                        effective = dict(inherited)
                        effective.update(element.attrib)
                        for declaration in element.get("style", "").split(";"):
                            if ":" in declaration:
                                key, value = declaration.split(":", 1)
                                effective[key.strip()] = value.strip()
                        kind = element.tag.rsplit("}", 1)[-1]
                        stroke = effective.get("stroke", "").lower()
                        if kind in ("path", "line", "polyline", "polygon", "circle", "ellipse"):
                            if stroke in patterns:
                                patterns[stroke].append(effective.get("stroke-dasharray", "none"))
                        for child in element:
                            collect_patterns(child, effective)

                    collect_patterns(ET.parse(path).getroot(), {})
                    for (name, arguments), (color, stroke) in zip(makers, colors):
                        with self.subTest(api=name):
                            self.assertTrue(patterns[stroke], "Cosmetic API missing from SVG")
                            self.assertTrue(all(
                                (pattern not in ("", "none")) == expected_dashed
                                for pattern in patterns[stroke]
                            ))

    def testUnattachedClipGroup(self):
        """A clip may collect views before it is attached to a page."""
        document = FreeCAD.ActiveDocument
        clip = document.addObject("TechDraw::DrawViewClip", "UnattachedClip")
        view = document.addObject("TechDraw::DrawViewAnnotation", "ClipAnnotation")
        view.Text = ["Clip child"]
        with self.assertRaises(TypeError):
            clip.addView(document.Box)
        self.assertEqual(clip.Views, [])
        clip.addView(view)
        self.assertEqual(clip.Views, [view])

        self.page.addView(clip)
        self.page.addView(view)
        document.recompute()
        clip.removeView(view)
        self.assertEqual(clip.Views, [])
        clip.addView(view)
        document.recompute()
        self.assertEqual(clip.Views, [view])
        self.assertIn(clip, self.page.Views)
        self.assertIn(view, self.page.Views)

    def testLeaderInputValidation(self):
        """Invalid leader inputs raise before creating document objects."""
        import TechDraw

        document = FreeCAD.ActiveDocument
        view = document.addObject("TechDraw::DrawViewPart", "LeaderView")
        view.Source = [document.Box]
        self.page.addView(view)
        unattached = document.addObject("TechDraw::DrawViewPart", "UnattachedLeaderView")
        points = [FreeCAD.Vector(10, 10, 0), FreeCAD.Vector(20, 20, 0)]
        previous_objects = [obj.Name for obj in document.Objects]
        for parent in (None, document.Box, self.page):
            with self.subTest(parent=parent):
                with self.assertRaises(TypeError):
                    TechDraw.makeLeader(parent, points)
        with self.assertRaises(ValueError):
            TechDraw.makeLeader(unattached, points)
        for invalid_points in ([], points[:1]):
            with self.subTest(points=invalid_points):
                with self.assertRaises(ValueError):
                    TechDraw.makeLeader(view, invalid_points)
        with self.assertRaises(TypeError):
            TechDraw.makeLeader(view, [points[0], "not a vector"])
        self.assertEqual([obj.Name for obj in document.Objects], previous_objects)

        leader = TechDraw.makeLeader(view, points)
        self.assertEqual(leader.LeaderParent, view)
        self.assertEqual(leader.LeaderParent.findParentPage(), self.page)
        self.assertEqual(len(leader.WayPoints), 2)

    def testBreakDocumentObject(self):
        """A view owns editable, suppressible break document objects."""
        view = FreeCAD.ActiveDocument.addObject("TechDraw::DrawViewPart", "BreakableView")
        self.page.addView(view)
        view.Source = [FreeCAD.ActiveDocument.Box]

        view_break = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewBreak", "ViewBreak"
        )
        view_break.StartPoint = FreeCAD.Vector(3.0, 0.0, 0.0)
        view_break.EndPoint = FreeCAD.Vector(7.0, 0.0, 0.0)
        view_break.Direction = FreeCAD.Vector(1.0, 0.0, 0.0)
        view_break.Gap = 1.0
        view_break.BreakType = "ZigZag"
        view.Breaks = [view_break]
        FreeCAD.ActiveDocument.recompute()

        self.assertEqual(view.Breaks, [view_break])
        self.assertTrue(view_break.hasExtension("App::SuppressibleExtension"))
        self.assertFalse(view_break.Suppressed)
        self.assertTrue(self._waitUntil(lambda: bool(view.getVisibleEdges())))

        view_break.Suppressed = True
        self.assertIn("Touched", view.State)
        FreeCAD.ActiveDocument.recompute()
        self.assertEqual(view.Breaks, [view_break])

        FreeCAD.ActiveDocument.removeObject(view_break.Name)
        FreeCAD.ActiveDocument.recompute()
        self.assertEqual(view.Breaks, [])

    def testBrokenOutSectionDocumentObject(self):
        """A view owns editable, suppressible broken-out section objects."""
        view = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewPart", "BrokenOutView"
        )
        self.page.addView(view)
        view.Source = [FreeCAD.ActiveDocument.Box]
        view.Direction = FreeCAD.Vector(0, 0, 1)

        section = FreeCAD.ActiveDocument.addObject(
            "TechDraw::DrawViewBrokenOutSection", "BrokenOutSection"
        )
        section.Outline = [
            FreeCAD.Vector(2.0, 2.0, 0.0),
            FreeCAD.Vector(8.0, 2.0, 0.0),
            FreeCAD.Vector(8.0, 8.0, 0.0),
            FreeCAD.Vector(2.0, 8.0, 0.0),
        ]
        section.Depth = 4.0
        view.BrokenOutSections = [section]
        FreeCAD.ActiveDocument.recompute()
        self.assertTrue(self._waitUntil(lambda: bool(view.getVisibleEdges())))

        self.assertEqual(view.BrokenOutSections, [section])
        self.assertTrue(section.hasExtension("App::SuppressibleExtension"))
        self.assertEqual(len(section.Outline), 4)
        self.assertAlmostEqual(section.Depth.Value, 4.0)

        section.Suppressed = True
        self.assertTrue(self._waitUntil(lambda: len(view.getVisibleEdges()) == 4))
        FreeCAD.ActiveDocument.recompute()
        self.assertNotIn("Touched", view.State)
        FreeCAD.ActiveDocument.removeObject(section.Name)
        FreeCAD.ActiveDocument.recompute()
        self.assertEqual(view.BrokenOutSections, [])

if __name__ == "__main__":
    unittest.main()
