# SPDX-License-Identifier: LGPL-2.1-or-later
"""External geometry from other assembly components while editing in place (#17951).

A sketch of a Body linked in an assembly is edited in place. Picking an element of
another component with the external geometry tool must reference it through the
assembly (SketchObject.addExternalInContext): linked from the other component, so
that the sketch does not depend on the assembly, and projected at the right place.
"""

import os
import shutil
import tempfile

import FreeCAD as App
import Part

from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase

V = App.Vector
P = App.Placement
R = App.Rotation


class TestExternalInAssemblyGui(SketcherGuiTestCase):
    def setUp(self):
        super().setUp()
        self.docs = []
        self.tmp = tempfile.mkdtemp(prefix="sk17951_")
        Gui.getMainWindow().show()

    def tearDown(self):
        try:
            gdoc = Gui.ActiveDocument
            if gdoc is not None:
                gdoc.resetEdit()
                self.flush_gui(50)
            Gui.Selection.clearSelection()
            # close the assembly first, it links the part documents
            for doc in reversed(self.docs):
                if doc.Name in App.listDocuments():
                    App.closeDocument(doc.Name)
            self.flush_gui(50)
            shutil.rmtree(self.tmp, ignore_errors=True)
        finally:
            super().tearDown()

    def build(self, crossDoc):
        if crossDoc:
            d1 = App.newDocument("Sk17951P1")
            d2 = App.newDocument("Sk17951P2")
            da = App.newDocument("Sk17951Asm")
            self.docs += [d1, d2, da]
        else:
            d1 = d2 = da = App.newDocument("Sk17951All")
            self.docs.append(d1)
        part1 = d1.addObject("App::Part", "Part1")
        body1 = part1.newObject("PartDesign::Body", "Body1")
        part1.Placement = P(V(5, 0, 0), R(V(0, 0, 1), 30))
        body1.Placement = P(V(0, 3, 0), R())
        box1 = body1.newObject("PartDesign::AdditiveBox", "Box1")
        sketch = body1.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = [(body1.Origin.OriginFeatures[3], "")]
        sketch.MapMode = "FlatFace"
        part2 = d2.addObject("App::Part", "Part2")
        body2 = part2.newObject("PartDesign::Body", "Body2")
        box2 = body2.newObject("PartDesign::AdditiveBox", "Box")
        box2.Length = 4
        part2.Placement = P(V(100, 0, 0), R())
        body2.Placement = P(V(0, 20, 0), R())
        if crossDoc:
            for doc in (d1, d2, da):
                doc.saveAs(os.path.join(self.tmp, doc.Name + ".FCStd"))
        asm = da.addObject("Assembly::AssemblyObject", "Assembly")
        link1 = asm.newObject("App::Link", "Link1")
        link1.LinkedObject = part1
        link2 = asm.newObject("App::Link", "Link2")
        link2.LinkedObject = part2
        link1.Placement = P(V(0, 0, 7), R(V(0, 0, 1), 90))
        link2.Placement = P(V(0, 50, 0), R())
        for doc in {d1, d2, da}:
            doc.recompute()
        self.da, self.asm, self.body1, self.sketch, self.link2 = da, asm, body1, sketch, link2
        self.box1, self.box2 = box1, box2

    def recomputeAll(self):
        for _ in range(2):
            for doc in self.docs:
                doc.recompute()

    def editInPlace(self):
        gdoc = Gui.getDocument(self.da.Name)
        Gui.ActiveDocument = gdoc
        App.setActiveDocument(self.da.Name)
        self.assertTrue(gdoc.setEdit(self.asm, 0, "Link1.Body1.Sketch."))
        self.flush_gui(100)
        Gui.runCommand("Sketcher_Projection", 0)
        self.flush_gui(100)

    def pick(self, sub):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.da.Name, self.asm.Name, sub)
        self.flush_gui(100)

    def checkProjectedAt(self, edgePath):
        """The last external geometry, placed through the assembly, matches the
        picked edge in the XY projection (the sketch lies in the global XY plane)."""
        ref = Part.getShape(self.asm, edgePath, needSubElement=True)
        geo = self.sketch.ExternalGeo[-1]
        plm = self.asm.getSubObject("Link1.Body1.Sketch.", retType=3)
        if hasattr(geo, "StartPoint"):
            pts = [plm.multVec(geo.StartPoint), plm.multVec(geo.EndPoint)]
        else:
            pts = [plm.multVec(V(geo.X, geo.Y, geo.Z))]
        refPts = [v.Point for v in ref.Vertexes]
        for p in pts:
            self.assertTrue(
                any(abs(p.x - r.x) < 1e-6 and abs(p.y - r.y) < 1e-6 for r in refPts),
                f"projected point {p} is not at the picked edge {refPts}",
            )

    def runOtherComponent(self, crossDoc):
        self.build(crossDoc)
        bodyObjects = list(self.body1.Group)
        self.editInPlace()
        edge = "Link2.Body2.Box.Edge1"
        self.pick(edge)

        # referenced through the assembly, without any new object
        self.assertEqual(self.body1.Group, bodyObjects)
        self.assertEqual(self.sketch.ExternalGeometry, [])
        links = self.sketch.ExternalContextGeometry
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0], self.link2)
        self.assertEqual(len(links[0][1]), 1)
        self.assertTrue(links[0][1][0].endswith("Box.Edge1"), links)
        self.assertEqual(self.sketch.ExternalContext, (self.asm, ["Link1.Body1.Sketch."]))
        # the sketch depends on the box only, not on the assembly
        self.assertIn(self.box2, self.sketch.OutList)
        self.assertNotIn(self.asm, self.sketch.OutList)
        self.recomputeAll()
        self.assertTrue(self.sketch.isValid(), self.sketch.State)
        self.checkProjectedAt(edge)

        # the projection follows the other component when the assembly moves it
        self.link2.Placement = P(V(30, 80, 0), R())
        self.recomputeAll()
        self.checkProjectedAt(edge)

        # one undoable step. Closing the edit may record its own "Sketch recompute"
        # step on top of it (ViewProviderSketch::unsetEdit).
        doc = self.sketch.Document
        Gui.getDocument(doc.Name).resetEdit()
        self.flush_gui(50)
        names = doc.UndoNames
        self.assertIn("Add external geometry", names)
        steps = names.index("Add external geometry")
        self.assertTrue(all(n == "Sketch recompute" for n in names[:steps]), names)
        for _ in range(steps):
            doc.undo()
        self.assertEqual(len(self.sketch.ExternalContextGeometry), 1)
        doc.undo()
        self.assertEqual(self.sketch.ExternalContextGeometry, [])
        self.assertEqual(len(self.sketch.ExternalGeo), 2)

    def testOtherComponentSameDocument(self):
        self.runOtherComponent(False)

    def testOtherComponentOtherDocument(self):
        self.runOtherComponent(True)

    def testOwnBodyStillDirect(self):
        self.build(True)
        self.editInPlace()
        self.pick("Link1.Body1.Box1.Edge1")
        self.assertEqual(self.sketch.ExternalContextGeometry, [])
        self.assertEqual(len(self.sketch.ExternalGeometry), 1)
        self.assertEqual(self.sketch.ExternalGeometry[0][0], self.box1)

    def testNotInPlaceStillRefused(self):
        self.build(False)
        gdoc = Gui.getDocument(self.da.Name)
        Gui.ActiveDocument = gdoc
        self.assertTrue(gdoc.setEdit(self.sketch.Name))
        self.flush_gui(100)
        Gui.runCommand("Sketcher_Projection", 0)
        self.flush_gui(100)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.da.Name, "Part2", "Body2.Box.Edge1")
        self.flush_gui(100)
        self.assertEqual(self.sketch.ExternalContextGeometry, [])
        self.assertEqual(len(self.sketch.ExternalGeometry), 0)
