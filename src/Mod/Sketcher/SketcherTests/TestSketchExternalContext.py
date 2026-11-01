# SPDX-License-Identifier: LGPL-2.1-or-later

"""External geometry of other components of the tree a sketch is placed in.

https://github.com/FreeCAD/FreeCAD/issues/17951
"""

import os
import tempfile
import unittest

import FreeCAD as App
import Part  # noqa: F401  (registers the Part types)
import Sketcher  # noqa: F401


def _projectedPoint(sketch):
    # ExternalGeo[0] and [1] are the H and V axes
    points = [g for g in sketch.ExternalGeo[2:] if g.TypeId == "Part::GeomPoint"]
    return points[0] if points else None


class TestSketchExternalContext(unittest.TestCase):
    def setUp(self):
        self.docs = []
        self.tmp = tempfile.mkdtemp(prefix="fc_ctx_")

    def tearDown(self):
        for name in list(App.listDocuments()):
            if name.startswith("Ctx"):
                App.closeDocument(name)

    def _newDoc(self, name):
        doc = App.newDocument(name)
        self.docs.append(doc)
        return doc

    def _build(self, partDoc, asmDoc):
        """Body1 (with the sketch) and Body2 (with a box), linked in an assembly."""
        body1 = partDoc.addObject("PartDesign::Body", "Body1")
        sketch = body1.newObject("Sketcher::SketchObject", "Sketch")
        sketch.Placement = App.Placement(App.Vector(0, 0, 5), App.Rotation(App.Vector(1, 0, 0), 90))
        body1.Placement.Base = App.Vector(100, 0, 0)  # replaced by the link placement
        body2 = partDoc.addObject("PartDesign::Body", "Body2")
        box = body2.newObject("PartDesign::AdditiveBox", "Box")
        asm = asmDoc.addObject("App::Part", "Asm")
        asm.Placement.Base = App.Vector(0, 0, 1000)  # cancels out
        link1 = asm.newObject("App::Link", "Link1")
        link1.LinkedObject = body1
        link1.Placement.Base = App.Vector(0, 50, 0)
        link2 = asm.newObject("App::Link", "Link2")
        link2.LinkedObject = body2
        link2.Placement.Base = App.Vector(0, 0, 30)
        partDoc.recompute()
        asmDoc.recompute()
        return asm, sketch, link1, link2, box

    def _expected(self, asm, sketch, globalPoint):
        # sketch-local coordinates of a point given in the assembly (without its placement)
        mat = asm.getSubObject("Link1.Body1.Sketch.", retType=2, transform=False)[1]
        local = App.Placement(mat).inverse().multVec(globalPoint)
        return App.Vector(local.x, local.y, 0)

    def _checkPoint(self, sketch, expected):
        point = _projectedPoint(sketch)
        self.assertIsNotNone(point, "the vertex of the other component was not projected")
        self.assertLess((App.Vector(point.X, point.Y, point.Z) - expected).Length, 1e-6)

    def test_reference_through_the_sibling_without_cycle(self):
        doc = self._newDoc("CtxSame")
        asm, sketch, link1, link2, box = self._build(doc, doc)

        index = sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Vertex2")
        self.assertEqual(index, 0)
        doc.recompute()
        self.assertNotIn("Invalid", sketch.State)

        # linked from the sibling, not from the assembly (which depends on the sketch)
        self.assertEqual(sketch.ExternalContextGeometry, [(link2, ("Body2.Box.Vertex2",))])
        self.assertEqual(sketch.ExternalGeometry, [])
        # depends on the geometry only, not on the assembly nor its links
        self.assertIn(box, sketch.OutList)
        self.assertNotIn(link2, sketch.OutList)
        self.assertNotIn(asm, sketch.OutList)
        self.assertEqual(sketch.ExternalContext, (asm, ["Link1.Body1.Sketch."]))

        vertex = box.Shape.Vertex2.Point
        self._checkPoint(sketch, self._expected(asm, sketch, vertex + link2.Placement.Base))

        # the other component moves: the sketch depends on it
        link2.Placement.Base = App.Vector(7, 0, 60)
        doc.recompute()
        self._checkPoint(sketch, self._expected(asm, sketch, vertex + link2.Placement.Base))

        # the component of the sketch moves: followed through the context
        link1.Placement.Base = App.Vector(3, 80, 0)
        doc.recompute()
        doc.recompute()
        self._checkPoint(sketch, self._expected(asm, sketch, vertex + link2.Placement.Base))

        # the projection is a normal external geometry of the sketch
        sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 10, 0)))
        sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -3, 1))
        doc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        start = sketch.Geometry[0].StartPoint
        self._checkPoint(sketch, App.Vector(start.x, start.y, 0))

    def test_edge_and_delete(self):
        doc = self._newDoc("CtxEdge")
        asm, sketch, link1, link2, box = self._build(doc, doc)
        sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Vertex2")
        sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Edge1")
        doc.recompute()
        self.assertEqual(len(sketch.ExternalGeo), 4)  # axes, point, edge
        # Same reference twice is refused
        with self.assertRaises(ValueError):
            sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Edge1")

        sketch.delExternal(0)
        doc.recompute()
        self.assertEqual(sketch.ExternalContextGeometry, [(link2, ("Body2.Box.Edge1",))])
        self.assertEqual(len(sketch.ExternalGeo), 3)
        self.assertIsNone(_projectedPoint(sketch))

        sketch.delExternal(0)
        doc.recompute()
        self.assertEqual(sketch.ExternalContextGeometry, [])
        self.assertIsNone(sketch.ExternalContext[0] if sketch.ExternalContext else None)
        self.assertEqual(len(sketch.ExternalGeo), 2)

    def test_mixed_with_ordinary_external_geometry(self):
        doc = self._newDoc("CtxMixed")
        asm, sketch, link1, link2, box = self._build(doc, doc)
        body1 = doc.getObject("Body1")
        own = body1.newObject("PartDesign::AdditiveBox", "OwnBox")
        doc.recompute()
        sketch.addExternal("OwnBox", "Vertex1")
        sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Vertex2")
        sketch.addExternal("OwnBox", "Edge1")
        doc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self.assertEqual(sketch.ExternalGeometry, [(own, ("Vertex1", "Edge1"))])
        self.assertEqual(len(sketch.ExternalContextGeometry), 1)
        self.assertEqual(len(sketch.ExternalGeo), 5)

        # deleting an ordinary one keeps the context one, and the other way round
        sketch.delExternal(0)
        doc.recompute()
        self.assertEqual(sketch.ExternalGeometry, [(own, ("Edge1",))])
        self.assertEqual(len(sketch.ExternalContextGeometry), 1)
        self.assertIsNotNone(_projectedPoint(sketch))
        sketch.delExternal(0)
        sketch.delExternal(0)
        doc.recompute()
        self.assertEqual(sketch.ExternalGeometry, [])
        self.assertEqual(sketch.ExternalContextGeometry, [])

    def test_undo(self):
        doc = self._newDoc("CtxUndo")
        doc.UndoMode = 1
        asm, sketch, link1, link2, box = self._build(doc, doc)
        doc.openTransaction("Add external")
        sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Vertex2")
        doc.commitTransaction()
        doc.recompute()
        self.assertIsNotNone(_projectedPoint(sketch))
        doc.undo()
        doc.recompute()
        self.assertEqual(sketch.ExternalContextGeometry, [])
        self.assertIsNone(_projectedPoint(sketch))
        doc.redo()
        doc.recompute()
        self.assertEqual(len(sketch.ExternalContextGeometry), 1)
        self.assertIsNotNone(_projectedPoint(sketch))

    def test_rejected_references(self):
        doc = self._newDoc("CtxReject")
        asm, sketch, link1, link2, box = self._build(doc, doc)
        # the sketch is not at that path
        with self.assertRaises(ValueError):
            sketch.addExternalInContext(asm, "Link2.Body2.Sketch.", "Link2.Body2.Box.Vertex2")
        # not an element
        with self.assertRaises(ValueError):
            sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.")
        self.assertEqual(sketch.ExternalContextGeometry, [])

    def test_separate_files_save_and_reload(self):
        partDoc = self._newDoc("CtxPart")
        asmDoc = self._newDoc("CtxAsm")
        partPath = os.path.join(self.tmp, "CtxPart.FCStd")
        asmPath = os.path.join(self.tmp, "CtxAsm.FCStd")
        # links to another document need it saved
        partDoc.saveAs(partPath)
        asmDoc.saveAs(asmPath)
        asm, sketch, link1, link2, box = self._build(partDoc, asmDoc)

        sketch.addExternalInContext(asm, "Link1.Body1.Sketch.", "Link2.Body2.Box.Vertex2")
        partDoc.recompute()
        expected = self._expected(asm, sketch, box.Shape.Vertex2.Point + link2.Placement.Base)
        self._checkPoint(sketch, expected)
        # the part does not depend on the assembly: no cycle between the documents
        self.assertEqual(partDoc.getDependentDocuments(True), [partDoc])
        self.assertEqual(asmDoc.getDependentDocuments(True)[-1], asmDoc)
        partDoc.save()
        asmDoc.save()
        App.closeDocument(asmDoc.Name)
        App.closeDocument(partDoc.Name)

        # the part alone: the projection is kept even if the assembly is not available
        partDoc = App.openDocument(partPath)
        sketch = partDoc.getObject("Sketch")
        partDoc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self._checkPoint(sketch, expected)

        asmDoc = App.openDocument(asmPath)
        asm = asmDoc.getObject("Asm")
        partDoc.recompute()
        self.assertNotIn("Invalid", sketch.State)
        self.assertEqual(sketch.ExternalContext[0], asm)
        self._checkPoint(sketch, expected)


if __name__ == "__main__":
    unittest.main()
