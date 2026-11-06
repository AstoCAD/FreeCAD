# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
#                                                                         *
#   This file is part of the FreeCAD CAx development system.              *
#                                                                         *
#   This program is free software; you can redistribute it and/or modify  *
#   it under the terms of the GNU Lesser General Public License (LGPL)    *
#   as published by the Free Software Foundation; either version 2 of     *
#   the License, or (at your option) any later version.                   *
#   for detail see the LICENCE text file.                                 *
#                                                                         *
#   FreeCAD is distributed in the hope that it will be useful,            *
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#   GNU Library General Public License for more details.                  *
#                                                                         *
#   You should have received a copy of the GNU Library General Public     *
#   License along with FreeCAD; if not, write to the Free Software        *
#   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#   USA                                                                   *
# **************************************************************************

import FreeCAD, unittest, Part
import copy
import math
import warnings
from FreeCAD import Units
from FreeCAD import Base
from TestPropertyFloatNaN import restoreValueAsFromFile

App = FreeCAD

from parttests.BRep_tests import BRepTests
from parttests.Geom2d_tests import Geom2dTests
from parttests.regression_tests import RegressionTests
from parttests.TopoShapeListTest import TopoShapeListTest
from parttests.TopoShapeTest import TopoShapeTest
from parttests.TestLinkArrayCircular import TestLinkArrayCircular
from parttests.TestLinkArrayLinear import TestLinkArrayLinear
from parttests.TestLinkArrayPath import TestLinkArrayPath
from parttests.TestLinkArrayPoint import TestLinkArrayPoint
from parttests.TestPartMirror import TestPartMirroringRegression
from parttests.TestFaceMakerUnifiedPlanar import *
from parttests.TestFaceMakerUnifiedNonPlanar import *


# ---------------------------------------------------------------------------
# define the test cases to test the FreeCAD Part module
# ---------------------------------------------------------------------------
def getCoincidentVertexes(vtx1, vtx2):
    pairs = []
    tol = Part.Precision.confusion()
    for i in vtx1:
        for j in vtx2:
            if i.Point.distanceToPoint(j.Point) < tol:
                pairs.append((i, j))

    return pairs


class PartTestCases(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartTest")

    def testBoxCase(self):
        self.Box = self.Doc.addObject("Part::Box", "Box")
        self.Doc.recompute()
        self.assertEqual(len(self.Box.Shape.Faces), 6)

    def testIssue2985(self):
        v1 = App.Vector(0.0, 0.0, 0.0)
        v2 = App.Vector(10.0, 0.0, 0.0)
        v3 = App.Vector(10.0, 0.0, 10.0)
        v4 = App.Vector(0.0, 0.0, 10.0)
        edge1 = Part.makeLine(v1, v2)
        edge2 = Part.makeLine(v2, v3)
        edge3 = Part.makeLine(v3, v4)
        edge4 = Part.makeLine(v4, v1)
        # Travis build confirms the crash under macOS
        # result = Part.makeFilledFace([edge1,edge2,edge3,edge4])
        # self.Doc.addObject("Part::Feature","Face").Shape = result
        # self.assertTrue(isinstance(result.Surface, Part.BSplineSurface))

    def testCutHolesWireOrientation(self):
        # https://github.com/FreeCAD/FreeCAD/issues/29543
        outer = [
            App.Vector(0, 0, 0),
            App.Vector(30, 0, 0),
            App.Vector(30, 20, 0),
            App.Vector(0, 20, 0),
        ]
        inner = [
            App.Vector(5, 5, 0),
            App.Vector(25, 5, 0),
            App.Vector(25, 15, 0),
            App.Vector(5, 15, 0),
        ]
        for outerPoints in (outer, outer[::-1]):
            for innerPoints in (inner, inner[::-1]):
                face = Part.Face(Part.makePolygon(outerPoints + [outerPoints[0]]))
                face.cutHoles([Part.makePolygon(innerPoints + [innerPoints[0]])])
                self.assertTrue(face.isValid())
                self.assertEqual(len(face.Wires), 2)
                self.assertAlmostEqual(face.Area, 400.0, places=6)

    def testFaceFromWiresHoleOrientation(self):
        # Part.Face([outer, hole]), Part.Face(surface, [outer, hole]) and Part.Face(face, hole)
        # took the hole wire as it was: a hole oriented like the outer wire gave an invalid face
        # of area outer + hole.
        outer = [
            App.Vector(0, 0, 0),
            App.Vector(30, 0, 0),
            App.Vector(30, 20, 0),
            App.Vector(0, 20, 0),
        ]
        inner = [
            App.Vector(5, 5, 0),
            App.Vector(25, 5, 0),
            App.Vector(25, 15, 0),
            App.Vector(5, 15, 0),
        ]
        circle = Part.Wire(Part.makeCircle(2, App.Vector(15, 10, 0)))
        for outerPoints in (outer, outer[::-1]):
            outerWire = Part.makePolygon(outerPoints + [outerPoints[0]])
            for innerPoints in (inner, inner[::-1]):
                innerWire = Part.makePolygon(innerPoints + [innerPoints[0]])
                for name, face in (
                    ("wires", Part.Face([outerWire, innerWire])),
                    ("surface", Part.Face(Part.Plane(), [outerWire, innerWire])),
                    ("face", Part.Face(Part.Face(outerWire), innerWire)),
                ):
                    with self.subTest(case=name, outer=outerPoints[1], inner=innerPoints[1]):
                        self.assertTrue(face.isValid())
                        self.assertEqual(len(face.Wires), 2)
                        self.assertAlmostEqual(face.Area, 400.0, places=6)
            for hole in (circle, circle.reversed()):
                face = Part.Face([outerWire, hole])
                self.assertTrue(face.isValid())
                self.assertAlmostEqual(face.Area, 600.0 - 4 * math.pi, places=6)
        # a single wire is unchanged
        self.assertAlmostEqual(Part.Face([Part.makePolygon(outer + [outer[0]])]).Area, 600.0)

    def testDeprecatedInsertWarningDoesNotCreateDocument(self):
        document_name = "DeprecatedPartInsertTest"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                with self.assertRaises(DeprecationWarning):
                    Part.insert("missing.step", document_name)
            self.assertNotIn(document_name, FreeCAD.listDocuments())
        finally:
            if document_name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(document_name)

    def testDeprecatedInsertWarningIncludesLifecycle(self):
        document_name = "DeprecatedPartInsertMessageTest"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", DeprecationWarning)
                with self.assertRaises(DeprecationWarning) as caught:
                    Part.insert("missing.step", document_name)
            self.assertEqual(
                str(caught.exception),
                "Method 'Part.insert' is deprecated since FreeCAD 26.3 and will be removed in "
                "FreeCAD 27.2; use Import.insert instead.",
            )
        finally:
            if document_name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(document_name)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartTest")
        # print ("omit closing document for debugging")


class PartTestBSplineCurve(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartTest")

        poles = [[0, 0, 0], [1, 1, 0], [2, 0, 0]]
        self.spline = Part.BSplineCurve()
        self.spline.buildFromPoles(poles)

        poles = [[0, 0, 0], [1, 1, 0], [2, 0, 0], [1, -1, 0]]
        self.nurbs = Part.BSplineCurve()
        self.nurbs.buildFromPolesMultsKnots(poles, (3, 1, 3), (0, 0.5, 1), False, 2)

    def testProperties(self):
        self.assertEqual(self.spline.Continuity, "CN")
        self.assertEqual(self.spline.Degree, 2)
        self.assertEqual(self.spline.EndPoint, App.Vector(2, 0, 0))
        self.assertEqual(self.spline.FirstParameter, 0.0)
        self.assertEqual(self.spline.FirstUKnotIndex, 1)
        self.assertEqual(self.spline.KnotSequence, [0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        self.assertEqual(self.spline.LastParameter, 1.0)
        self.assertEqual(self.spline.LastUKnotIndex, 2)
        max_degree = self.spline.MaxDegree
        self.assertEqual(self.spline.NbKnots, 2)
        self.assertEqual(self.spline.NbPoles, 3)
        self.assertEqual(self.spline.StartPoint, App.Vector(0.0, 0.0, 0.0))

    def testGetters(self):
        """only check if the function doesn't crash"""
        self.spline.getKnot(1)
        self.spline.getKnots()
        self.spline.getMultiplicities()
        self.spline.getMultiplicity(1)
        self.spline.getPole(1)
        self.spline.getPoles()
        self.spline.getPolesAndWeights()
        self.spline.getResolution(0.5)
        self.spline.getWeight(1)
        self.spline.getWeights()

    def testToBiArcsParallelEndTangents(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33257
        # An S-shaped curve whose end tangents are parallel must not be
        # replaced by a straight line, whatever its parameter range.
        for last in (1.0, 2.0):
            spline = Part.BSplineCurve()
            spline.buildFromPoles(
                [
                    App.Vector(0, 0, 0),
                    App.Vector(10, 0, 0),
                    App.Vector(0, 10, 0),
                    App.Vector(10, 10, 0),
                ]
            )
            spline.scaleKnotsToBounds(0.0, last)
            arcs = spline.toBiArcs(0.01)
            self.assertGreater(len(arcs), 1)
            compound = Part.Compound([arc.toShape() for arc in arcs])
            for i in range(21):
                param = spline.FirstParameter + (spline.LastParameter - spline.FirstParameter) * i / 20
                dist = compound.distToShape(Part.Vertex(spline.value(param)))[0]
                self.assertLess(dist, 0.02)

    def testSetters(self):
        spline = copy.copy(self.spline)
        spline.setKnot(1, 0.1)
        spline.setPeriodic()
        spline.setNotPeriodic()
        # spline.setKnots()
        # spline.setOrigin(2)   # not working?
        self.spline.setPole(1, App.Vector([1, 0, 0]))  # first parameter 0 gives occ error

    def testIssue2671(self):
        if "BUILD_SPREADSHEET" in FreeCAD.__cmake__:
            self.Doc = App.newDocument("Issue2671")
            Box = self.Doc.addObject("Part::Box", "Box")
            Mirroring = self.Doc.addObject("Part::Mirroring", "Mirroring")
            Spreadsheet = self.Doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
            Mirroring.Source = Box
            Mirroring.Base = (8, 5, 25)
            Mirroring.Normal = (0.5, 0.2, 0.9)
            Spreadsheet.set("A1", "=Mirroring.Base.x")
            Spreadsheet.set("B1", "=Mirroring.Base.y")
            Spreadsheet.set("C1", "=Mirroring.Base.z")
            Spreadsheet.set("A2", "=Mirroring.Normal.x")
            Spreadsheet.set("B2", "=Mirroring.Normal.y")
            Spreadsheet.set("C2", "=Mirroring.Normal.z")
            self.Doc.recompute()
            self.assertEqual(Spreadsheet.A1, Units.Quantity("8 mm"))
            self.assertEqual(Spreadsheet.B1, Units.Quantity("5 mm"))
            self.assertEqual(Spreadsheet.C1, Units.Quantity("25 mm"))
            self.assertEqual(Spreadsheet.A2, Units.Quantity("0.5 mm"))
            self.assertEqual(Spreadsheet.B2, Units.Quantity("0.2 mm"))
            self.assertEqual(Spreadsheet.C2, Units.Quantity("0.9 mm"))
            App.closeDocument("Issue2671")

    def testIssue2876(self):
        if "BUILD_SPREADSHEET" in FreeCAD.__cmake__:
            self.Doc = App.newDocument("Issue2876")
            Cylinder = self.Doc.addObject("Part::Cylinder", "Cylinder")
            Cylinder.Radius = 5
            Pipe = self.Doc.addObject("Part::Thickness", "Pipe")
            Pipe.Faces = (Cylinder, ["Face2", "Face3"])
            Pipe.Mode = 1
            Pipe.Value = -1  # negative wall thickness
            Spreadsheet = self.Doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
            Spreadsheet.set("A1", "Pipe OD")
            Spreadsheet.set("B1", "Pipe WT")
            Spreadsheet.set("C1", "Pipe ID")
            Spreadsheet.set("A2", "=2*Cylinder.Radius")
            Spreadsheet.set("B2", "=-Pipe.Value")
            Spreadsheet.set("C2", "=2*(Cylinder.Radius + Pipe.Value)")
            self.Doc.recompute()
            self.assertEqual(Spreadsheet.B2, Units.Quantity("1 mm"))
            self.assertEqual(Spreadsheet.C2, Units.Quantity("8 mm"))
            App.closeDocument("Issue2876")

    def testSubElements(self):
        box = Part.makeBox(1, 1, 1)
        with self.assertRaises(ValueError):
            box.getElement("InvalidName")
        with self.assertRaises(ValueError):
            box.getElement("Face6_abc")
        # getSubTopoShape now catches this before it gets to OCC, so the error changes:
        # with self.assertRaises(Part.OCCError):
        with self.assertRaises(IndexError):
            box.getElement("Face7")

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartTest")


class PartTestCurveToNurbs(unittest.TestCase):
    def testCircleToNurbs(self):
        mat = Base.Matrix()
        mat.rotateX(1)
        mat.rotateY(1)
        mat.rotateZ(1)

        circle = Part.Circle()
        circle.Radius = 5

        circle.transform(mat)
        nurbs = circle.toNurbs()
        self.assertEqual(circle.value(0), nurbs.value(0))

        arc = circle.trim(0, 2)
        nurbs = arc.toNurbs()
        self.assertEqual(circle.value(0), nurbs.value(0))

        spline = circle.toBSpline()
        self.assertAlmostEqual(circle.value(0).distanceToPoint(spline.value(0)), 0)

    def testEllipseToNurbs(self):
        mat = Base.Matrix()
        mat.rotateX(1)
        mat.rotateY(1)
        mat.rotateZ(1)

        ellipse = Part.Ellipse()
        ellipse.MajorRadius = 5
        ellipse.MinorRadius = 3

        ellipse.transform(mat)
        nurbs = ellipse.toNurbs()
        self.assertEqual(ellipse.value(0), nurbs.value(0))

        arc = ellipse.trim(0, 2)
        nurbs = arc.toNurbs()
        self.assertEqual(ellipse.value(0), nurbs.value(0))

        spline = ellipse.toBSpline()
        self.assertAlmostEqual(ellipse.value(0).distanceToPoint(spline.value(0)), 0)


class PartTestBSplineSurface(unittest.TestCase):
    def testTorusToSpline(self):
        to = Part.Toroid()
        bs = to.toBSpline()
        bs.setUPeriodic()
        bs.setVPeriodic()
        self.assertGreater(len(bs.UKnotSequence), 0)
        self.assertGreater(len(bs.VKnotSequence), 0)

    def testBounds(self):
        to = Part.Toroid()
        bs = to.toBSpline()
        self.assertAlmostEqual(bs.bounds()[1], 2 * math.pi)
        self.assertAlmostEqual(bs.bounds()[3], 2 * math.pi)
        bs.scaleKnotsToBounds(0.0, 1.0, 0.0, 1.0)
        self.assertAlmostEqual(bs.bounds()[1], 1.0)
        self.assertAlmostEqual(bs.bounds()[3], 1.0)

    def testBuildFromNSectionsNeedsTwoCurves(self):
        bs = Part.BSplineSurface()
        with self.assertRaises(ValueError):
            bs.buildFromNSections([])
        with self.assertRaises(ValueError):
            bs.buildFromNSections([Part.BSplineCurve()])
        c1 = Part.LineSegment(Base.Vector(0, 0, 0), Base.Vector(1, 0, 0))
        c2 = Part.LineSegment(Base.Vector(0, 1, 0), Base.Vector(1, 1, 0))
        bs.buildFromNSections([c1, c2])
        self.assertAlmostEqual(bs.toShape().Area, 1.0)

    def testApproximateDegMinAboveDegMax(self):
        # GeomAPI_PointsToBSplineSurface never returned for DegMin > DegMax
        V = Base.Vector
        grid = [[V(i, j, 0.1 * i * j) for j in range(5)] for i in range(5)]
        heights = [[0.1 * i * j for j in range(5)] for i in range(5)]
        bs = Part.BSplineSurface()
        with self.assertRaises(Part.OCCError):
            bs.approximate(Points=grid, DegMin=5, DegMax=3, ParamType="Uniform")
        with self.assertRaises(Part.OCCError):
            bs.approximate(Points=heights, DegMin=5, DegMax=3, X0=0, dX=1, Y0=0, dY=1)
        bs.approximate(Points=grid, DegMin=3, DegMax=5, ParamType="Uniform")
        self.assertLessEqual(bs.UDegree, 5)


class PartTestGeomPlate(unittest.TestCase):
    def testConstraintErrorWithBadIndex(self):
        plate = Part.GeomPlate.BuildPlateSurface()
        for func in (plate.G0Error, plate.G1Error, plate.G2Error):
            with self.subTest(func.__name__):
                # Nothing computed yet
                with self.assertRaises(RuntimeError):
                    func(1)
        v = Base.Vector
        points = [v(0, 0, 0), v(10, 0, 0), v(10, 10, 3), v(0, 10, 0)]
        for i in range(4):
            line = Part.LineSegment(points[i], points[(i + 1) % 4])
            plate.add(Part.GeomPlate.CurveConstraint(line))
        plate.add(Part.GeomPlate.PointConstraint(v(5, 5, 5)))
        plate.perform()
        self.assertTrue(plate.isDone())
        self.assertGreaterEqual(plate.G0Error(), 0.0)
        for func in (plate.G0Error, plate.G1Error, plate.G2Error):
            with self.subTest(func.__name__):
                with self.assertRaises(RuntimeError):
                    func(100)


class PartTestNormals(unittest.TestCase):
    def setUp(self):
        self.face = Part.makePlane(1, 1)

    def testFaceNormal(self):
        self.assertEqual(self.face.normalAt(0, 0), Base.Vector(0, 0, 1))
        self.assertEqual(self.face.Surface.normal(0, 0), Base.Vector(0, 0, 1))

    def testReverseOrientation(self):
        self.face.reverse()
        self.assertEqual(self.face.normalAt(0, 0), Base.Vector(0, 0, -1))
        self.assertEqual(self.face.Surface.normal(0, 0), Base.Vector(0, 0, 1))

    def testPlacement(self):
        self.face.reverse()
        self.face.Placement.Rotation.Angle = 1
        self.face.Placement.Rotation.Axis = (1, 1, 1)
        vec = Base.Vector(-0.63905, 0.33259, -0.69353)
        self.assertGreater(self.face.normalAt(0, 0).dot(vec), 0.9999)
        self.assertLess(self.face.Surface.normal(0, 0).dot(vec), -0.9999)

    def tearDown(self):
        pass


class PartTestShapeRotate(unittest.TestCase):
    def testPlacement(self):
        tol = 1e-12

        box = Part.makeBox(1, 1, 1)
        box.Placement.Base = Base.Vector(10, 10, 10)
        box.rotate((0, 0, 0), (0, 0, 1), 90)

        p1 = Base.Placement()
        p1.Base = Base.Vector(10, 10, 10)

        p2 = Base.Placement()
        p2.Rotation.Angle = math.radians(90)
        self.assertTrue(box.Placement.isSame(p2 * p1, tol))

        p3 = p1.copy()
        p3.rotate((0, 0, 0), (0, 0, 1), 90)
        self.assertTrue(p3.isSame(p1 * p2, tol))
        self.assertFalse(box.Placement.isSame(p3, tol))

        p4 = p1.copy()
        p4.rotate((0, 0, 0), (0, 0, 1), 90, True)
        self.assertTrue(p4.isSame(p2 * p1, tol))
        self.assertTrue(box.Placement.isSame(p4, tol))


class PartTestCircle2D(unittest.TestCase):
    def testValidCircle(self):
        p1 = App.Base.Vector2d(0.01, 0.01)
        p2 = App.Base.Vector2d(0.02, 0.02)
        p3 = App.Base.Vector2d(0.01, -0.01)
        Part.Geom2d.Circle2d.getCircleCenter(p1, p2, p3)

    def testCollinearPoints(self):
        p1 = App.Base.Vector2d(0.01, 0.01)
        p2 = App.Base.Vector2d(0.02, 0.02)
        p3 = App.Base.Vector2d(0.04, 0.0399)
        with self.assertRaises(ValueError):
            Part.Geom2d.Circle2d.getCircleCenter(p1, p2, p3)


class PartTestCone(unittest.TestCase):
    def testderivatives(self):
        def get_dn(surface, u, v):
            pos = surface.value(u, v)
            v10 = surface.getDN(u, v, 1, 0)
            v01 = surface.getDN(u, v, 0, 1)
            v11 = surface.getDN(u, v, 1, 1)
            return (pos, v10, v01, v11)

        cone = Part.Cone()
        cone.SemiAngle = 0.2
        cone.Radius = 2.0

        u, v = (5.0, 5.0)
        vp, v1, v2, v3 = get_dn(cone, u, v)

        shape = cone.toShape(0, 2 * math.pi, 0, 10)
        shape = shape.toNurbs()
        spline = shape.Face1.Surface

        u, v = spline.parameter(vp)
        wp, w1, w2, w3 = get_dn(spline, u, v)

        self.assertAlmostEqual(vp.distanceToPoint(wp), 0)
        self.assertAlmostEqual(v1.getAngle(w1), 0)
        self.assertAlmostEqual(v2.getAngle(w2), 0)
        self.assertAlmostEqual(v3.getAngle(w3), 0)


class PartTestChFi2dAlgos(unittest.TestCase):
    def testChFi2d_FilletAlgo(self):
        v = FreeCAD.Vector
        edge1 = Part.makeLine(v(0, 0, 0), v(0, 10, 0))
        edge2 = Part.makeLine(v(0, 10, 0), v(10, 10, 0))
        wire = Part.Wire([edge1, edge2])
        pln = Part.Plane()

        with self.assertRaises(TypeError):
            alg = Part.ChFi2d.FilletAlgo(pln)

        alg = Part.ChFi2d.FilletAlgo()
        with self.assertRaises(TypeError):
            alg.init()

        print(alg)
        # Test without shape
        with self.assertRaises(Base.CADKernelError):
            alg.perform(1)

        with self.assertRaises(TypeError):
            alg.perform()

        alg = Part.ChFi2d.FilletAlgo(wire, pln)
        alg.init(edge1, edge2, pln)
        alg.init(wire, pln)

        alg = Part.ChFi2d.FilletAlgo(edge1, edge2, pln)
        alg.perform(1.0)

        with self.assertRaises(TypeError):
            alg.numberOfResults()

        with self.assertRaises(TypeError):
            alg.result(1)

        self.assertEqual(alg.numberOfResults(Base.Vector(0, 10, 0)), 1)
        result = alg.result(Base.Vector(0, 10, 0))
        curve = result[0].Curve
        self.assertEqual(type(curve), Part.Circle)
        self.assertEqual(curve.Axis, pln.Axis)
        self.assertEqual(curve.Radius, 1.0)

    def testChFi2d_AnaFilletAlgo(self):
        v = FreeCAD.Vector
        edge1 = Part.makeLine(v(0, 0, 0), v(0, 10, 0))
        edge2 = Part.makeLine(v(0, 10, 0), v(10, 10, 0))
        wire = Part.Wire([edge1, edge2])
        pln = Part.Plane()

        with self.assertRaises(TypeError):
            alg = Part.ChFi2d.AnaFilletAlgo(pln)

        alg = Part.ChFi2d.AnaFilletAlgo()
        with self.assertRaises(TypeError):
            alg.init()

        print(alg)
        # Test without shape
        self.assertFalse(alg.perform(1))

        with self.assertRaises(TypeError):
            alg.perform()

        alg = Part.ChFi2d.AnaFilletAlgo(wire, pln)
        alg.init(edge1, edge2, pln)
        alg.init(wire, pln)

        alg = Part.ChFi2d.AnaFilletAlgo(edge1, edge2, pln)
        alg.perform(1.0)

        with self.assertRaises(TypeError):
            alg.result(1)

        result = alg.result()
        curve = result[0].Curve
        self.assertEqual(type(curve), Part.Circle)
        self.assertEqual(curve.Radius, 1.0)

    def testChFi2d_ChamferAPI(self):
        v = FreeCAD.Vector
        edge1 = Part.makeLine(v(0, 0, 0), v(0, 10, 0))
        edge2 = Part.makeLine(v(0, 10, 0), v(10, 10, 0))
        wire = Part.Wire([edge1, edge2])

        with self.assertRaises(TypeError):
            alg = Part.ChFi2d.ChamferAPI(edge1)

        alg = Part.ChFi2d.ChamferAPI(wire)
        with self.assertRaises(TypeError):
            alg.init()

        print(alg)

        with self.assertRaises(TypeError):
            alg.perform(1)

        alg = Part.ChFi2d.ChamferAPI(wire)
        alg.init(edge1, edge2)
        alg.init(wire)

        alg = Part.ChFi2d.ChamferAPI(edge1, edge2)
        alg.perform()

        with self.assertRaises(TypeError):
            alg.result(1)

        result = alg.result(1.0, 1.0)
        curve = result[0].Curve
        self.assertEqual(type(curve), Part.Line)


class PartTestRuledSurface(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument()

    def testRuledSurfaceFromTwoObjects(self):
        line1 = Part.makeLine(FreeCAD.Vector(-70, -30, 0), FreeCAD.Vector(-50, 40, 0))
        line2 = Part.makeLine(FreeCAD.Vector(-40, -30, 0), FreeCAD.Vector(-40, 10, 0))
        plm1 = FreeCAD.Placement()
        plm1.Rotation = FreeCAD.Rotation(0.7071067811865476, 0.0, 0.0, 0.7071067811865475)
        line1.Placement = plm1
        fea1 = self.Doc.addObject("Part::Feature")
        fea2 = self.Doc.addObject("Part::Feature")
        fea1.Shape = line1
        fea2.Shape = line2
        ruled = self.Doc.addObject("Part::RuledSurface")
        ruled.Curve1 = fea1
        ruled.Curve2 = fea2

        self.Doc.recompute()

        same1 = getCoincidentVertexes(fea1.Shape.Vertexes, ruled.Shape.Vertexes)
        same2 = getCoincidentVertexes(fea2.Shape.Vertexes, ruled.Shape.Vertexes)
        self.assertEqual(len(same1), 2)
        self.assertEqual(len(same2), 2)

    def testRuledSurfaceFromTwoObjectsWithSharedVertexs(self):
        """Test reproducing issue #15539"""

        # Arrange
        line = Part.makeLine(FreeCAD.Vector(0, 0, 50), FreeCAD.Vector(0, -50, 0))
        line1 = Part.makeLine(FreeCAD.Vector(0, 0, 50), FreeCAD.Vector(50, 0, 0))
        line2 = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, -50, 0))
        line3 = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(50, 0, 0))
        fea = self.Doc.addObject("Part::Feature")
        fea1 = self.Doc.addObject("Part::Feature")
        fea2 = self.Doc.addObject("Part::Feature")
        fea3 = self.Doc.addObject("Part::Feature")
        fea.Shape = line
        fea1.Shape = line1
        fea2.Shape = line2
        fea3.Shape = line3

        # Defining all the surfaces generated by 2 lines with one common vertex
        ruled = self.Doc.addObject("Part::RuledSurface")
        ruled.Curve1 = fea
        ruled.Curve2 = fea1

        ruled1 = self.Doc.addObject("Part::RuledSurface")
        ruled1.Curve1 = fea1
        ruled1.Curve2 = fea3

        ruled2 = self.Doc.addObject("Part::RuledSurface")
        ruled2.Curve1 = fea2
        ruled2.Curve2 = fea3

        ruled3 = self.Doc.addObject("Part::RuledSurface")
        ruled3.Curve1 = fea
        ruled3.Curve2 = fea2

        # Act
        self.Doc.recompute()

        # Assert
        same00 = getCoincidentVertexes(fea.Shape.Vertexes, ruled.Shape.Vertexes)
        same03 = getCoincidentVertexes(fea.Shape.Vertexes, ruled3.Shape.Vertexes)
        same10 = getCoincidentVertexes(fea1.Shape.Vertexes, ruled.Shape.Vertexes)
        same11 = getCoincidentVertexes(fea1.Shape.Vertexes, ruled1.Shape.Vertexes)
        same22 = getCoincidentVertexes(fea2.Shape.Vertexes, ruled2.Shape.Vertexes)
        same23 = getCoincidentVertexes(fea2.Shape.Vertexes, ruled3.Shape.Vertexes)
        same31 = getCoincidentVertexes(fea3.Shape.Vertexes, ruled1.Shape.Vertexes)
        same32 = getCoincidentVertexes(fea3.Shape.Vertexes, ruled2.Shape.Vertexes)

        # BRepFill::Face() seems creating faces with 4 vertexes
        # Therefore, in this case, every face shares 3 vertexes (1 counted twice as coincident) with the lines that generate that face
        self.assertEqual(len(same00), 3)
        self.assertEqual(len(same03), 3)
        self.assertEqual(len(same10), 3)
        self.assertEqual(len(same11), 3)
        self.assertEqual(len(same22), 3)
        self.assertEqual(len(same23), 3)
        self.assertEqual(len(same31), 3)
        self.assertEqual(len(same32), 3)

    def testRuledSurfaceFromOneObject(self):
        if "BUILD_SKETCHER" in FreeCAD.__cmake__:
            sketch = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
            sketch.Placement = FreeCAD.Placement(
                FreeCAD.Vector(0.000000, 0.000000, 0.000000),
                App.Rotation(0.707107, 0.000000, 0.000000, 0.707107),
            )
            sketch.MapMode = "Deactivated"

            sketch.addGeometry(
                Part.LineSegment(
                    App.Vector(-43.475811, 34.364464, 0), App.Vector(-65.860519, -20.078733, 0)
                ),
                False,
            )
            sketch.addGeometry(
                Part.LineSegment(
                    App.Vector(14.004498, 27.390331, 0), App.Vector(33.577049, -27.952749, 0)
                ),
                False,
            )

            ruled = self.Doc.addObject("Part::RuledSurface", "Ruled Surface")
            ruled.Curve1 = (sketch, ["Edge1"])
            ruled.Curve2 = (sketch, ["Edge2"])
            self.Doc.recompute()

            same = getCoincidentVertexes(sketch.Shape.Vertexes, ruled.Shape.Vertexes)
            self.assertEqual(len(same), 4)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)


class PartTestShapeFix(unittest.TestCase):
    def testShapeFix_Root(self):
        with self.assertRaises(TypeError):
            Part.ShapeFix.Root([])

        fix = Part.ShapeFix.Root()
        print(fix)

        fix.Precision = 0.0
        self.assertEqual(fix.Precision, 0.0)

        fix.MinTolerance = 0.0
        self.assertEqual(fix.MinTolerance, 0.0)

        fix.MaxTolerance = 0.5
        self.assertEqual(fix.MaxTolerance, 0.5)

        self.assertEqual(fix.limitTolerance(0.25), 0.25)

    def testShapeFix_Shape(self):
        surface = Part.Plane()
        face = surface.toShape(-1, 1, -1, 1)

        with self.assertRaises(TypeError):
            Part.ShapeFix.Shape([])

        fix = Part.ShapeFix.Shape(face)
        fix.init(face)
        print(fix)
        fix.shape()
        fix.fixSolidTool()
        fix.fixShellTool()
        fix.fixFaceTool()
        fix.fixWireTool()
        fix.fixEdgeTool()

        fix.FixSolidMode = True
        self.assertEqual(fix.FixSolidMode, True)

        fix.FixFreeShellMode = True
        self.assertEqual(fix.FixFreeShellMode, True)

        fix.FixFreeFaceMode = True
        self.assertEqual(fix.FixFreeFaceMode, True)

        fix.FixFreeWireMode = True
        self.assertEqual(fix.FixFreeWireMode, True)

        fix.FixSameParameterMode = True
        self.assertEqual(fix.FixSameParameterMode, True)

        fix.FixVertexPositionMode = True
        self.assertEqual(fix.FixVertexPositionMode, True)

        fix.FixVertexTolMode = True
        self.assertEqual(fix.FixVertexTolMode, True)

        fix.perform()

    def testShapeFix_Edge(self):
        surface = Part.Plane()
        face = surface.toShape(-1, 1, -1, 1)

        with self.assertRaises(TypeError):
            Part.ShapeFix.Edge([])

        wirefix = Part.ShapeFix.Wire(face.OuterWire, face, 1e-7)
        fix = wirefix.fixEdgeTool()
        print(fix)

        fix.fixRemovePCurve(face.Edge1, face)
        fix.fixRemovePCurve(face.Edge1, face.Surface, face.Placement)
        with self.assertRaises(TypeError):
            fix.fixRemovePCurve(face)

        fix.fixRemoveCurve3d(face.Edge1)
        fix.fixAddCurve3d(face.Edge1)

        fix.fixAddPCurve(face.Edge1, face, False)
        fix.fixAddPCurve(face.Edge1, face.Surface, face.Placement, False)
        with self.assertRaises(TypeError):
            fix.fixAddPCurve(face)

        fix.fixVertexTolerance(face.Edge1)
        fix.fixVertexTolerance(face.Edge1, face)

        fix.fixReversed2d(face.Edge1, face)
        fix.fixReversed2d(face.Edge1, face.Surface, face.Placement)
        with self.assertRaises(TypeError):
            fix.fixReversed2d(face)

        fix.fixSameParameter(face.Edge1)
        fix.fixSameParameter(face.Edge1, face)
        with self.assertRaises(TypeError):
            fix.fixSameParameter(face)

    def testShapeFix_Face(self):
        surface = Part.Plane()
        face = surface.toShape(-1, 1, -1, 1)

        Part.ShapeFix.Face()
        Part.ShapeFix.Face(surface, 0.00001, True)
        with self.assertRaises(TypeError):
            Part.ShapeFix.Face([])

        fix = Part.ShapeFix.Face(face)
        print(fix)

        fix.fixOrientation()
        fix.fixAddNaturalBound()
        fix.fixMissingSeam()
        fix.fixSmallAreaWire(True)
        fix.fixLoopWire()
        fix.fixIntersectingWires()
        fix.fixWiresTwoCoincidentEdges()
        fix.fixPeriodicDegenerated()
        fix.perform()

        fix.add(face.OuterWire)
        current = fix.face()
        result = fix.result()
        fix.fixWireTool()

        fix.FixWireMode = True
        self.assertEqual(fix.FixWireMode, True)

        fix.FixOrientationMode = True
        self.assertEqual(fix.FixOrientationMode, True)

        fix.FixAddNaturalBoundMode = True
        self.assertEqual(fix.FixAddNaturalBoundMode, True)

        fix.FixMissingSeamMode = True
        self.assertEqual(fix.FixMissingSeamMode, True)

        fix.FixSmallAreaWireMode = True
        self.assertEqual(fix.FixSmallAreaWireMode, True)

        fix.RemoveSmallAreaFaceMode = True
        self.assertEqual(fix.RemoveSmallAreaFaceMode, True)

        fix.FixIntersectingWiresMode = True
        self.assertEqual(fix.FixIntersectingWiresMode, True)

        fix.FixLoopWiresMode = True
        self.assertEqual(fix.FixLoopWiresMode, True)

        fix.FixSplitFaceMode = True
        self.assertEqual(fix.FixSplitFaceMode, True)

        fix.AutoCorrectPrecisionMode = True
        self.assertEqual(fix.AutoCorrectPrecisionMode, True)

        fix.FixPeriodicDegeneratedMode = True
        self.assertEqual(fix.FixPeriodicDegeneratedMode, True)

        fix.clearModes()

    def testShapeFix_Shell(self):
        surface = Part.Plane()
        face = surface.toShape(-1, 1, -1, 1)
        shell = Part.Shell([face])

        Part.ShapeFix.Shell()
        with self.assertRaises(TypeError):
            Part.ShapeFix.Face([])

        fix = Part.ShapeFix.Shell(shell)
        fix.init(shell)
        print(fix)
        fix.perform()
        fix.shell()
        fix.shape()
        fix.fixFaceTool()

        fix.setNonManifoldFlag(True)
        fix.fixFaceOrientation(shell)

        self.assertEqual(len(fix.errorFaces().Faces), 0)

        self.assertEqual(fix.numberOfShells(), 1)

        fix.FixFaceMode = True
        self.assertEqual(fix.FixFaceMode, True)

        fix.FixOrientationMode = True
        self.assertEqual(fix.FixOrientationMode, True)

    def testShapeFix_Solid(self):
        box = Part.makeBox(1, 1, 1)
        with self.assertRaises(TypeError):
            Part.ShapeFix.Solid([])

        fix = Part.ShapeFix.Solid()
        fix.init(box)
        print(fix)

        fix.perform()
        fix.solid()
        fix.shape()
        fix.fixShellTool()
        fix.solidFromShell(box.Shells[0])

        fix.FixShellMode = True
        self.assertEqual(fix.FixShellMode, True)

        fix.FixShellOrientationMode = True
        self.assertEqual(fix.FixShellOrientationMode, True)

        fix.CreateOpenSolidMode = True
        self.assertEqual(fix.CreateOpenSolidMode, True)

    def testShapeFix_Wire(self):
        with self.assertRaises(TypeError):
            Part.ShapeFix.Wire([])

        surface = Part.Plane()
        face = surface.toShape(-1, 1, -1, 1)
        Part.ShapeFix.Wire(face.OuterWire, face, 1e-7)
        fix = Part.ShapeFix.Wire()
        fix.init(face.OuterWire, face, 1e-7)
        fix.load(face.OuterWire)
        fix.setSurface(surface)
        fix.setSurface(surface, face.Placement)
        fix.setFace(face)
        fix.setMaxTailAngle(math.pi)
        fix.setMaxTailWidth(10.0)
        fix.fixEdgeTool()

        self.assertEqual(fix.isLoaded(), True)
        self.assertEqual(fix.isReady(), True)
        self.assertEqual(fix.numberOfEdges(), 4)

        print(fix)
        fix.clearModes()
        fix.clearStatuses()

        fix.wire()
        fix.wireAPIMake()
        fix.face()

        fix.ModifyTopologyMode = True
        self.assertEqual(fix.ModifyTopologyMode, True)

        fix.ModifyGeometryMode = True
        self.assertEqual(fix.ModifyGeometryMode, True)

        fix.ModifyRemoveLoopMode = True
        self.assertEqual(fix.ModifyRemoveLoopMode, True)

        fix.ClosedWireMode = True
        self.assertEqual(fix.ClosedWireMode, True)

        fix.PreferencePCurveMode = True
        self.assertEqual(fix.PreferencePCurveMode, True)

        fix.FixGapsByRangesMode = True
        self.assertEqual(fix.FixGapsByRangesMode, True)

        fix.FixReorderMode = True
        self.assertEqual(fix.FixReorderMode, True)

        fix.FixSmallMode = True
        self.assertEqual(fix.FixSmallMode, True)

        fix.FixConnectedMode = True
        self.assertEqual(fix.FixConnectedMode, True)

        fix.FixEdgeCurvesMode = True
        self.assertEqual(fix.FixEdgeCurvesMode, True)

        fix.FixDegeneratedMode = True
        self.assertEqual(fix.FixDegeneratedMode, True)

        fix.FixSelfIntersectionMode = True
        self.assertEqual(fix.FixSelfIntersectionMode, True)

        fix.FixLackingMode = True
        self.assertEqual(fix.FixLackingMode, True)

        fix.FixGaps3dMode = True
        self.assertEqual(fix.FixGaps3dMode, True)

        fix.FixGaps2dMode = True
        self.assertEqual(fix.FixGaps2dMode, True)

        fix.FixReversed2dMode = True
        self.assertEqual(fix.FixReversed2dMode, True)

        fix.FixRemovePCurveMode = True
        self.assertEqual(fix.FixRemovePCurveMode, True)

        fix.FixAddPCurveMode = True
        self.assertEqual(fix.FixAddPCurveMode, True)

        fix.FixRemoveCurve3dMode = True
        self.assertEqual(fix.FixRemoveCurve3dMode, True)

        fix.FixAddCurve3dMode = True
        self.assertEqual(fix.FixAddCurve3dMode, True)

        fix.FixSeamMode = True
        self.assertEqual(fix.FixSeamMode, True)

        fix.FixShiftedMode = True
        self.assertEqual(fix.FixShiftedMode, True)

        fix.FixSameParameterMode = True
        self.assertEqual(fix.FixSameParameterMode, True)

        fix.FixVertexToleranceMode = True
        self.assertEqual(fix.FixVertexToleranceMode, True)

        fix.FixNotchedEdgesMode = True
        self.assertEqual(fix.FixNotchedEdgesMode, True)

        fix.FixSelfIntersectingEdgeMode = True
        self.assertEqual(fix.FixSelfIntersectingEdgeMode, True)

        fix.FixIntersectingEdgesMode = True
        self.assertEqual(fix.FixIntersectingEdgesMode, True)

        fix.FixNonAdjacentIntersectingEdgesMode = True
        self.assertEqual(fix.FixNonAdjacentIntersectingEdgesMode, True)

        fix.FixTailMode = True
        self.assertEqual(fix.FixTailMode, True)

        fix.perform()
        fix.fixReorder()
        fix.fixSmall(True)
        fix.fixSmall(1, True, 1e-7)
        fix.fixConnected()
        fix.fixConnected(1, True)
        fix.fixEdgeCurves()
        fix.fixDegenerated()
        fix.fixDegenerated(1)
        fix.fixSelfIntersection()
        fix.fixLacking()
        fix.fixLacking(1, False)
        fix.fixClosed()
        fix.fixGaps3d()
        fix.fixGaps2d()
        fix.fixSeam(1)
        fix.fixShifted()
        fix.fixNotchedEdges()
        fix.fixGap3d(1, False)
        fix.fixGap2d(1, False)
        fix.fixTails()


class PartBOPTestContainer(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument()

    def testMakeFuse(self):
        box = self.Doc.addObject("Part::Box", "Box")
        cyl = self.Doc.addObject("Part::Cylinder", "Cylinder")
        part = self.Doc.addObject("App::Part", "Part")
        part.addObject(box)
        part.addObject(cyl)
        from BOPTools import BOPFeatures

        bp = BOPFeatures.BOPFeatures(self.Doc)
        fuse = bp.make_multi_fuse([cyl.Name, box.Name])
        self.assertEqual(part, fuse.getParent())

    def testMakeCut(self):
        box = self.Doc.addObject("Part::Box", "Box")
        cyl = self.Doc.addObject("Part::Cylinder", "Cylinder")
        part = self.Doc.addObject("App::Part", "Part")
        part.addObject(box)
        part.addObject(cyl)
        from BOPTools import BOPFeatures

        bp = BOPFeatures.BOPFeatures(self.Doc)
        fuse = bp.make_cut([cyl.Name, box.Name])
        self.assertEqual(part, fuse.getParent())

    def testMakeCommon(self):
        box = self.Doc.addObject("Part::Box", "Box")
        cyl = self.Doc.addObject("Part::Cylinder", "Cylinder")
        part = self.Doc.addObject("App::Part", "Part")
        part.addObject(box)
        part.addObject(cyl)
        from BOPTools import BOPFeatures

        bp = BOPFeatures.BOPFeatures(self.Doc)
        fuse = bp.make_multi_common([cyl.Name, box.Name])
        self.assertEqual(part, fuse.getParent())

    def testSliceApartNestedCompound(self):
        # https://github.com/FreeCAD/FreeCAD/issues/30143
        # A chain of Part booleans without refine gives Compound{Compound{Solid}}.
        # Slice apart must still give one object per piece.
        box = self.Doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 10
        tool1 = self.Doc.addObject("Part::Box", "Tool1")
        tool1.Placement.Base = FreeCAD.Vector(5, 5, 5)
        tool2 = self.Doc.addObject("Part::Box", "Tool2")
        tool2.Placement.Base = FreeCAD.Vector(-5, -5, 5)
        cut1 = self.Doc.addObject("Part::Cut", "Cut1")
        cut1.Base = box
        cut1.Tool = tool1
        cut2 = self.Doc.addObject("Part::Cut", "Cut2")
        cut2.Base = cut1
        cut2.Tool = tool2
        cut1.Refine = cut2.Refine = False
        plane =self.Doc.addObject("Part::Plane", "Plane")
        plane.Length = plane.Width = 20
        plane.Placement = FreeCAD.Placement(
            FreeCAD.Vector(-5, 2, -5), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
        )
        self.Doc.recompute()
        self.assertEqual(cut2.Shape.childShapes()[0].ShapeType, "Compound")

        from BOPTools import SplitFeatures
        from CompoundTools import Explode

        slc = SplitFeatures.makeSlice(name="Slice")
        slc.Base = cut2
        slc.Tools = [plane]
        slc.Mode = "Split"
        self.Doc.recompute()
        self.assertEqual(len(slc.Shape.Solids), 2)

        _group, children = Explode.explodeCompound(slc)
        self.Doc.recompute()
        self.assertEqual(len(children), 2)
        for child in children:
            self.assertEqual(len(child.Shape.Solids), 1)

    def testCutoutOfCompoundBase(self):
        # Each solid of a compound base is cut out on its own (largest piece kept).
        boxes = []
        for x in (0, 20):
            box = Part.makeBox(10, 10, 10)
            box.translate(FreeCAD.Vector(x, 0, 0))
            boxes.append(box)
        base = self.Doc.addObject("Part::Feature", "Base")
        base.Shape = Part.makeCompound(boxes)
        tool = self.Doc.addObject("Part::Box", "Tool")
        tool.Length = 40
        tool.Width = 1
        tool.Height = 20
        tool.Placement.Base = FreeCAD.Vector(-5, 7, -5)
        from BOPTools import JoinFeatures

        FreeCAD.setActiveDocument(self.Doc.Name)
        cutout = JoinFeatures.makeCutout(name="Cutout")
        cutout.Base = base
        cutout.Tool = tool
        self.Doc.recompute()
        self.assertTrue(cutout.isValid(), cutout.getStatusString())
        self.assertEqual(len(cutout.Shape.Solids), 2)
        self.assertAlmostEqual(cutout.Shape.Volume, 2 * 700, places=6)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)


class PartAttachNestedLCS(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument()

    def testAttachToAxisOfNestedLCS(self):
        # https://github.com/FreeCAD/FreeCAD/issues/22618
        # Attaching to "Part.LCS.Y_Axis." must use the placement of the LCS,
        # like attaching to a line at the same place does.
        part = self.Doc.addObject("App::Part", "Part")
        part.Placement.Base = FreeCAD.Vector(100, 0, 0)
        lcs = self.Doc.addObject("Part::LocalCoordinateSystem", "LCS")
        part.addObject(lcs)
        lcs.Placement.Base = FreeCAD.Vector(0, 50, 7)
        line = self.Doc.addObject("Part::Line", "Line")
        line.X2 = line.Z2 = 0
        line.Y2 = 10
        part.addObject(line)
        line.Placement.Base = FreeCAD.Vector(0, 50, 7)
        self.Doc.recompute()
        axis = [o for o in lcs.OriginFeatures if o.Role == "Y_Axis"][0]

        shape = Part.getShape(part, "{}.{}.".format(lcs.Name, axis.Name), needSubElement=True)
        self.assertAlmostEqual(shape.Placement.Base.distanceToPoint(FreeCAD.Vector(100, 50, 7)), 0)

        def attached(support):
            feat = self.Doc.addObject("Part::Feature", "Attached")
            feat.addExtension("Part::AttachExtensionPython")
            feat.AttachmentSupport = support
            feat.MapMode = "NormalToEdge"
            self.Doc.recompute()
            return feat.Placement

        onLine = attached([(part, "Line.Edge1")])
        onAxis = attached([(part, "{}.{}.".format(lcs.Name, axis.Name))])
        self.assertTrue(onAxis.isSame(onLine, 1e-7), "{} != {}".format(onAxis, onLine))

    def testMapPathParameterTooltipIsNotSketchSpecific(self):
        # https://github.com/FreeCAD/FreeCAD/issues/21534
        # Any object can be attached, not only sketches.
        box = self.Doc.addObject("Part::Box", "Box")
        doc = box.getDocumentationOfProperty("MapPathParameter")
        self.assertNotIn("sketch", doc.lower())
        self.assertIn("curve", doc)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)


class BSplineCurve2d(unittest.TestCase):
    def setUp(self):
        vec2 = FreeCAD.Base.Vector2d
        self.pts = [vec2(0, 0), vec2(1, 0)]
        self.bs = Part.Geom2d.BSplineCurve2d()

    def testInterpolate(self):
        self.bs.interpolate(Points=self.pts)

    def testApproximate(self):
        self.bs.approximate(Points=self.pts)


class GeometryCurve(unittest.TestCase):
    def testProject(self):
        line = Part.Line()
        line.projectPoint(FreeCAD.Vector())


class EmptyEdge(unittest.TestCase):
    def testParameterByLength(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.getParameterByLength(0)

    def testValueAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.valueAt(0)

    def testParameters(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            face = Part.Face()
            edge.parameters(face)

    def testParameterAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            vertex = Part.Vertex(0, 0, 0)
            edge.parameterAt(vertex)

    def testTangentAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.tangentAt(0)

    def testCurvatureAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.curvatureAt(0)

    def testCenterOfCurvatureAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.centerOfCurvatureAt(0)

    def testDerivative1At(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.derivative1At(0)

    def testDerivative2At(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.derivative2At(0)

    def testDerivative3At(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.derivative3At(0)

    def testNormalAt(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.normalAt(0)

    def testFirstVertex(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.firstVertex()

    def testLastVertex(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.lastVertex()

    def testGetTolerance(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.Tolerance

    def testSetTolerance(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.Tolerance = 0.01

    def testLength(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.Length

    def testCurve(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.Curve

    def testParameterRange(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.ParameterRange

    def testFirstParameter(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.FirstParameter

    def testLastParameter(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.LastParameter

    def testCountNodes(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.countNodes()

    def testDiscretize(self):
        with self.assertRaises(ValueError):
            edge = Part.Edge()
            edge.discretize()
        with self.assertRaises(ValueError):
            edge.discretize(5)

    def testParameterAtNullVertex(self):
        edge = Part.makeBox(1, 1, 1).Edges[0]
        with self.assertRaises(ValueError):
            edge.parameterAt(Part.Vertex())

    def testParameterAtNullFace(self):
        edge = Part.makeBox(1, 1, 1).Edges[0]
        with self.assertRaises(ValueError):
            edge.parameterAt(edge.Vertexes[0], Part.Face())


class EmptyFace(unittest.TestCase):
    def testMakeOffset(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.makeOffset(1)

    def testValueAt(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.valueAt(0, 0)

    def testNormalAt(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.normalAt(0, 0)

    def testTangentAt(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.tangentAt(0, 0)

    def testCurvatureAt(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.curvatureAt(0, 0)

    def testDerivative1At(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.derivative1At(0, 0)

    def testDerivative2At(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.derivative2At(0, 0)

    def testCutHoles(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            circle = Part.Circle()
            wire = Part.Wire(Part.Edge(circle))
            face.cutHoles([wire])

    def testUVNodes(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.getUVNodes()

    def testGetTolerance(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.Tolerance

    def testSetTolerance(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.Tolerance = 0.01

    def testParameterRange(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.ParameterRange

    def testCountNodes(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.countNodes()

    def testCountTriangles(self):
        with self.assertRaises(ValueError):
            face = Part.Face()
            face.countTriangles()

    def testCutHolesWithNullWire(self):
        face = Part.makeBox(1, 1, 1).Faces[0]
        with self.assertRaises(Part.OCCError):
            face.cutHoles([Part.Wire()])

    def testAddNullWire(self):
        face = Part.makeBox(1, 1, 1).Faces[0]
        with self.assertRaises(ValueError):
            face.addWire(Part.Wire())


class NullShapeArguments(unittest.TestCase):
    """Null shapes passed to (or used as) Part API arguments must raise, not crash."""

    def testWireApproximate(self):
        with self.assertRaises(ValueError):
            Part.Wire().approximate()

    def testMakePipeShellWithNullProfile(self):
        spine = Part.makeBox(1, 1, 1).Wires[0]
        with self.assertRaises(Part.OCCError):
            spine.makePipeShell([Part.Shape()])

    def testSortEdgesWithNullShape(self):
        for func in (Part.getSortedClusters, Part.__sortEdges__, Part.sortEdges):
            with self.subTest(func.__name__):
                with self.assertRaises(TypeError):
                    func([Part.Shape()])

    def testMakeShellWithNullShape(self):
        with self.assertRaises(ValueError):
            Part.makeShell([Part.Shape()])
        with self.assertRaises(ValueError):
            Part.Shell([Part.makeBox(1, 1, 1).Faces[0], Part.Face()])

    def testCurve2dToShapeOnNullFace(self):
        with self.assertRaises(ValueError):
            Part.Geom2d.Line2d().toShape(Part.Face(), 0, 1)

    def testValidArgumentsStillWork(self):
        box = Part.makeBox(1, 1, 1)
        self.assertEqual(len(Part.__sortEdges__(box.Faces[0].Edges)), 4)
        self.assertEqual(len(Part.makeShell(box.Faces[:2]).Faces), 2)
        edge = Part.makeLine(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(2, 0, 0))
        self.assertAlmostEqual(edge.parameterAt(edge.Vertexes[1]), 2)
        self.assertIsInstance(Part.Wire(edge).approximate(), Part.BSplineCurve)


class PartExtrusionTests(unittest.TestCase):

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartExtrusionTest")

    def _make_face_with_hole(self):
        """Create a 10x10 face with a 6x6 centered hole."""
        outer = Part.makePolygon(
            [
                Base.Vector(-5, -5, 0),
                Base.Vector(5, -5, 0),
                Base.Vector(5, 5, 0),
                Base.Vector(-5, 5, 0),
                Base.Vector(-5, -5, 0),
            ]
        )
        inner = Part.makePolygon(
            [
                Base.Vector(-3, -3, 0),
                Base.Vector(3, -3, 0),
                Base.Vector(3, 3, 0),
                Base.Vector(-3, 3, 0),
                Base.Vector(-3, -3, 0),
            ]
        )
        return Part.makeFace([outer, inner], "Part::FaceMakerBullseye")

    @staticmethod
    def _frustum_volume(height, bottom_area, top_area):
        """Volume of a frustum: h/3 * (A1 + A2 + sqrt(A1*A2))."""
        return height / 3 * (bottom_area + top_area + math.sqrt(bottom_area * top_area))

    def testExtrudeTaperInverted(self):
        """With Inverted taper (Part::Extrusion default), the outer grows
        while the hole shrinks."""
        base_feature = self.Doc.addObject("Part::Feature", "Base")
        base_feature.Shape = self._make_face_with_hole()
        extrusion = self.Doc.addObject("Part::Extrusion", "Extrude")
        extrusion.Base = base_feature
        extrusion.LengthFwd = 10
        extrusion.Solid = True
        extrusion.TaperAngle = 10
        self.Doc.recompute()

        self.assertTrue(extrusion.Shape.isValid())
        offset = 10 * math.tan(math.radians(10))
        outer = self._frustum_volume(10, 10 * 10, (10 + 2 * offset) * (10 + 2 * offset))
        hole = self._frustum_volume(10, 6 * 6, (6 - 2 * offset) * (6 - 2 * offset))
        expected_volume = outer - hole  # ~1204
        self.assertAlmostEqual(extrusion.Shape.Volume, expected_volume, places=1)

    def testExtrudeTaperSameAsOuter(self):
        """Regression test for issue #28709: with SameAsOuter taper (the
        PartDesign path), both wires must taper in the same direction."""
        base_feature = self.Doc.addObject("Part::Feature", "Base")
        base_feature.Shape = self._make_face_with_hole()
        extrusion = self.Doc.addObject("Part::Extrusion", "Extrude")
        extrusion.Base = base_feature
        extrusion.LengthFwd = 10
        extrusion.Solid = True
        extrusion.TaperAngle = 10
        extrusion.InnerWireTaper = "SameAsOuter"
        self.Doc.recompute()

        self.assertTrue(extrusion.Shape.isValid())
        offset = 10 * math.tan(math.radians(10))
        outer = self._frustum_volume(10, 10 * 10, (10 + 2 * offset) * (10 + 2 * offset))
        hole = self._frustum_volume(10, 6 * 6, (6 + 2 * offset) * (6 + 2 * offset))
        expected_volume = outer - hole  # ~781
        self.assertAlmostEqual(extrusion.Shape.Volume, expected_volume, places=1)

    def testNonFiniteLengthOrDirectionFails(self):
        # NaN passed the zero length checks and crashed the prism (segmentation fault)
        nan = float("nan")
        inf = float("inf")
        base_feature = self.Doc.addObject("Part::Feature", "Base")
        base_feature.Shape = self._make_face_with_hole()
        for prop, value in (
            ("LengthFwd", nan),
            ("LengthFwd", inf),
            ("LengthRev", nan),
            ("Dir", Base.Vector(nan, 0, 1)),
        ):
            with self.subTest(prop=prop, value=value):
                extrusion = self.Doc.addObject("Part::Extrusion", "Extrude")
                extrusion.Base = base_feature
                if isinstance(value, float) and math.isnan(value):
                    # assigning NaN raises: it can only come from a file
                    restoreValueAsFromFile(extrusion, prop, value)
                else:
                    setattr(extrusion, prop, value)
                self.Doc.recompute()
                self.assertIn("Invalid", extrusion.State)
                self.Doc.removeObject(extrusion.Name)

    def tearDown(self):
        FreeCAD.closeDocument("PartExtrusionTest")


class PartRevolutionFaceMakerModeTests(unittest.TestCase):
    """Issue #26357: Part::Revolution has a FaceMakerMode enumeration, like
    Part::Extrusion, kept in sync with the hidden FaceMakerClass."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartRevolutionTest")

    def tearDown(self):
        FreeCAD.closeDocument("PartRevolutionTest")

    def _make_revolution(self):
        def square(x0, x1, z0, z1):
            return Part.makePolygon(
                [
                    Base.Vector(x0, 0, z0),
                    Base.Vector(x1, 0, z0),
                    Base.Vector(x1, 0, z1),
                    Base.Vector(x0, 0, z1),
                    Base.Vector(x0, 0, z0),
                ]
            )

        profile = self.Doc.addObject("Part::Feature", "Profile")
        profile.Shape = Part.Compound([square(5, 15, 0, 10), square(8, 12, 3, 7)])
        revolution = self.Doc.addObject("Part::Revolution", "Revolve")
        revolution.Source = profile
        revolution.Solid = True
        return revolution

    def testDefaults(self):
        revolution = self._make_revolution()
        self.assertEqual(revolution.FaceMakerMode, "Unified")
        self.assertEqual(revolution.FaceMakerClass, "Part::FaceMakerUnified")
        self.assertIn("Hidden", revolution.getEditorMode("FaceMakerClass"))
        self.assertNotIn("Hidden", revolution.getEditorMode("FaceMakerMode"))

    def testSameModesAsExtrusion(self):
        revolution = self._make_revolution()
        extrusion = self.Doc.addObject("Part::Extrusion", "Extrude")
        self.assertEqual(
            revolution.getEnumerationsOfProperty("FaceMakerMode"),
            extrusion.getEnumerationsOfProperty("FaceMakerMode"),
        )
        for mode in revolution.getEnumerationsOfProperty("FaceMakerMode"):
            revolution.FaceMakerMode = mode
            extrusion.FaceMakerMode = mode
            self.assertEqual(revolution.FaceMakerClass, extrusion.FaceMakerClass)

    def testModeAndClassStayInSync(self):
        revolution = self._make_revolution()
        revolution.FaceMakerMode = "Cheese"
        self.assertEqual(revolution.FaceMakerClass, "Part::FaceMakerCheese")
        revolution.FaceMakerClass = "Part::FaceMakerSimple"
        self.assertEqual(revolution.FaceMakerMode, "Simple")
        # an empty class (old documents) means Bullseye and is kept as is
        revolution.FaceMakerClass = ""
        self.assertEqual(revolution.FaceMakerMode, "Bullseye")
        self.assertEqual(revolution.FaceMakerClass, "")

    def testModeDrivesTheFaceMaker(self):
        revolution = self._make_revolution()
        revolution.FaceMakerMode = "Bullseye"
        self.Doc.recompute()
        self.assertTrue(revolution.Shape.isValid())
        # Pappus: the inner square is a hole, centroid at x = 10
        self.assertAlmostEqual(revolution.Shape.Volume, 2 * math.pi * 10 * (100 - 16), places=3)

    def testModeIsRestoredFromClass(self):
        import os
        import tempfile

        revolution = self._make_revolution()
        revolution.FaceMakerMode = "Cheese"
        path = os.path.join(tempfile.mkdtemp(), "revolution_facemaker.FCStd")
        self.Doc.saveAs(path)
        FreeCAD.closeDocument(self.Doc.Name)
        try:
            self.Doc = FreeCAD.openDocument(path)
            revolution = self.Doc.getObject("Revolve")
            self.assertEqual(revolution.FaceMakerMode, "Cheese")
            self.assertEqual(revolution.FaceMakerClass, "Part::FaceMakerCheese")
        finally:
            FreeCAD.closeDocument(self.Doc.Name)
            self.Doc = FreeCAD.newDocument("PartRevolutionTest")
            os.remove(path)
            os.rmdir(os.path.dirname(path))


class PartOffset2DBSplineTests(unittest.TestCase):
    """Regression test for issue #17708: a face made from the 2D offset of a
    B-spline wire must be valid."""

    def _bsplineWire(self, closed):
        if closed:
            pts = [
                Base.Vector(10 * math.cos(2 * math.pi * i / 12), 6 * math.sin(2 * math.pi * i / 12), 0)
                for i in range(12)
            ]
        else:
            pts = [
                Base.Vector(4 + 10 * math.sin(math.pi * i / 20), -8 * math.cos(math.pi * i / 20), 0)
                for i in range(21)
            ]
        curve = Part.BSplineCurve()
        curve.interpolate(pts, PeriodicFlag=closed)
        wire = Part.Wire(curve.toShape())
        if not closed:
            vertexes = wire.OrderedVertexes
            closing = Part.makePolygon([vertexes[-1].Point, vertexes[0].Point])
            wire = Part.Wire([wire, closing])
        return wire

    def _checkOffset(self, wire, intersection):
        offset = wire.makeOffset2D(0.5, 0, fill=False, intersection=intersection)
        self.assertEqual(offset.ShapeType, "Wire")
        self.assertTrue(offset.isClosed())
        face = Part.Face(offset)
        self.assertTrue(face.isValid())
        self.assertGreater(face.Area, Part.Face(wire).Area)

    def testOffsetOfPeriodicBSpline(self):
        self._checkOffset(self._bsplineWire(True), False)

    def testOffsetOfBSplineWithLine(self):
        self._checkOffset(self._bsplineWire(False), True)


class PartOffset2DFaceWithHoleTests(unittest.TestCase):
    """Regression test for issue #27113: the 2D offset of a face with a hole
    must not depend on the order in which the face lists its wires."""

    def _wallTopFace(self, thickness):
        # The top face of the wall left by an outward thickness lists its hole
        # wire before its outer wire.
        box = Part.makeBox(20, 10, 10)
        top = [f for f in box.Faces if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        solid = box.makeThickness([top], thickness, 1e-3, False, False, 0, 2)
        faces = [
            f for f in solid.Faces if abs(f.CenterOfMass.z - 10) < 1e-6 and len(f.Wires) == 2
        ]
        self.assertEqual(len(faces), 1)
        return faces[0]

    def _checkOffset(self, thickness):
        face = self._wallTopFace(thickness)
        outer = face.OuterWire.BoundBox
        offset = face.makeOffset2D(1.1, 2)
        self.assertTrue(offset.isValid())
        self.assertEqual(len(offset.Faces), 1)
        self.assertEqual(len(offset.Faces[0].Wires), 2)
        # The outer boundary grows by the offset and the hole shrinks by it.
        self.assertAlmostEqual(offset.BoundBox.XLength, outer.XLength + 2.2, places=6)
        self.assertAlmostEqual(offset.BoundBox.YLength, outer.YLength + 2.2, places=6)
        holeX = outer.XLength - 2 * abs(thickness)
        holeY = outer.YLength - 2 * abs(thickness)
        expected = (outer.XLength + 2.2) * (outer.YLength + 2.2) - (holeX - 2.2) * (holeY - 2.2)
        self.assertAlmostEqual(offset.Area, expected, places=6)

    def testOffsetOfInwardThicknessFace(self):
        self._checkOffset(-1.5)

    def testOffsetOfOutwardThicknessFace(self):
        self._checkOffset(1.5)


class PartLoftTests(unittest.TestCase):
    """Regression tests for issue #31307: a solid loft from open sections
    must be reported as an error instead of silently giving an invalid solid."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartLoftTest")

    def tearDown(self):
        FreeCAD.closeDocument("PartLoftTest")

    def _section(self, shape):
        obj = self.Doc.addObject("Part::Feature", "Section")
        obj.Shape = shape
        return obj

    def _loft(self, sections, solid):
        loft = self.Doc.addObject("Part::Loft", "Loft")
        loft.Sections = sections
        loft.Solid = solid
        self.Doc.recompute()
        return loft

    def _open_sections(self):
        pts = [Base.Vector(0, 0, 0), Base.Vector(10, 0, 0), Base.Vector(10, 10, 0)]
        s1 = self._section(Part.makePolygon(pts))
        s2 = self._section(Part.makePolygon([p + Base.Vector(0, 0, 10) for p in pts]))
        return [s1, s2]

    def testSolidLoftFromOpenSectionsReportsError(self):
        loft = self._loft(self._open_sections(), True)
        self.assertIn("Invalid", loft.State)

    def testShellLoftFromOpenSectionsIsValid(self):
        loft = self._loft(self._open_sections(), False)
        self.assertNotIn("Invalid", loft.State)
        self.assertEqual(loft.Shape.ShapeType, "Shell")

    def testSolidLoftFromClosedSectionsIsValid(self):
        s1 = self._section(Part.Wire(Part.makeCircle(5).Edges))
        s2 = self._section(Part.Wire(Part.makeCircle(5, Base.Vector(0, 0, 10)).Edges))
        loft = self._loft([s1, s2], True)
        self.assertNotIn("Invalid", loft.State)
        self.assertEqual(len(loft.Shape.Solids), 1)
        self.assertTrue(loft.Shape.isValid())


class PartFaceMakerBuildFaceTests(unittest.TestCase):
    """Regression: a Sketch with MakeInternals=True containing two concentric
    ellipses and two short line segments joining them on the right side fails
    to build the internal face. The direct FaceMakerBuildFace call succeeds,
    but SketchObject::buildInternals also calls Part::WireJoiner::getOpenWires,
    which currently throws ('failed to close some wire in iteration N') and
    leaves InternalShape null."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("FaceMakerBuildFaceTest")

    def tearDown(self):
        FreeCAD.closeDocument("FaceMakerBuildFaceTest")

    def _add_geometry(self, sk):
        outer = Part.Ellipse(Base.Vector(0, 0, 0), 100, 60)
        inner = Part.Ellipse(Base.Vector(0, 0, 0), 50, 30)
        u1, u2 = -math.radians(15), math.radians(15)
        sk.addGeometry(outer, False)
        sk.addGeometry(inner, False)
        sk.addGeometry(Part.LineSegment(outer.value(u1), inner.value(u1)), False)
        sk.addGeometry(Part.LineSegment(outer.value(u2), inner.value(u2)), False)

    def testBuildFaceDirectMakeFace(self):
        """Direct FaceMakerBuildFace on the same wires must produce faces."""
        outer = Part.Ellipse(Base.Vector(0, 0, 0), 100, 60)
        inner = Part.Ellipse(Base.Vector(0, 0, 0), 50, 30)
        u1, u2 = -math.radians(15), math.radians(15)
        wires = [
            Part.Wire([outer.toShape()]),
            Part.Wire([inner.toShape()]),
            Part.Wire([Part.LineSegment(outer.value(u1), inner.value(u1)).toShape()]),
            Part.Wire([Part.LineSegment(outer.value(u2), inner.value(u2)).toShape()]),
        ]
        result = Part.makeFace(wires, "Part::FaceMakerBuildFace")
        self.assertFalse(result.isNull())
        self.assertGreaterEqual(len(result.Faces), 2)

    def testSketchMakeInternalsBuildsFaces(self):
        """The full SketchObject MakeInternals path must produce a non-null
        InternalShape with at least two faces (the annulus regions split by
        the two connecting line segments)."""
        sk = self.Doc.addObject("Sketcher::SketchObject", "Sketch")
        sk.MakeInternals = True
        self._add_geometry(sk)
        self.Doc.recompute()
        self.assertFalse(
            sk.InternalShape.isNull(),
            "SketchObject.InternalShape is null - buildInternals failed",
        )
        self.assertGreaterEqual(
            len(sk.InternalShape.Faces),
            2,
            f"Expected >=2 faces in InternalShape, got {len(sk.InternalShape.Faces)}",
        )


class PartShapeContentTests(unittest.TestCase):
    """Issue #28643: Part_CheckGeometry no longer repeats the physical
    properties of solids (shown by Std_MassProperties), but keeps them for
    shapes that are not solids."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("ShapeContentTest")

    def tearDown(self):
        FreeCAD.closeDocument("ShapeContentTest")

    def _content(self, shape):
        from BasicShapes import ShapeContent

        obj = self.Doc.addObject("Part::Feature", "Feature")
        obj.Shape = shape
        return ShapeContent.buildShapeContent(obj, 2, True)

    def testSolidHasNoPhysicalProperties(self):
        for shape in (
            Part.makeBox(10, 10, 10),
            Part.Compound([Part.makeBox(1, 1, 1), Part.makeSphere(1, Base.Vector(5, 0, 0))]),
        ):
            content = self._content(shape)
            self.assertIn("Area", content)
            for name in ("Volume", "Mass", "Center of mass", "Moment", "AxisOfInertia"):
                self.assertNotIn(name, content)

    def testNonSolidKeepsPhysicalProperties(self):
        for shape in (
            Part.makePlane(10, 10),
            Part.makeBox(10, 10, 10).Shells[0],
            Part.makeLine(Base.Vector(0, 0, 0), Base.Vector(10, 0, 0)),
        ):
            content = self._content(shape)
            self.assertIn("Center of mass", content)
            self.assertIn("Mass", content)
        # A compound that is not made of solids only keeps its volume
        mixed = Part.Compound([Part.makeBox(1, 1, 1), Part.makePlane(1, 1, Base.Vector(5, 0, 0))])
        self.assertIn("Volume", self._content(mixed))


class PartTrimmedSurfaceNaNTests(unittest.TestCase):
    def testNaNTrimParametersRaise(self):
        nan = float("nan")
        with self.assertRaises(ValueError):
            Part.RectangularTrimmedSurface(Part.Plane(), nan, 1, 0, 1)
        with self.assertRaises(ValueError):
            Part.RectangularTrimmedSurface(Part.Plane(), nan, 1, True)
        surf = Part.RectangularTrimmedSurface(Part.Plane(), 0, 1, 0, 1)
        with self.assertRaises(ValueError):
            surf.setTrim(nan, nan, nan, nan)
        surf.setTrim(0, 2, 0, 3)
        self.assertAlmostEqual(surf.toShape().Area, 6)


class PartShapeFromMeshTests(unittest.TestCase):
    def testFacetWithInvalidPointIndexRaises(self):
        v = Base.Vector
        points = [v(0, 0, 0), v(1, 0, 0), v(0, 1, 0)]
        for facet in ((0, 1, 3), (0, 5, 1), (-1, 0, 1)):
            with self.subTest(facet=facet):
                with self.assertRaises(ValueError):
                    Part.Shape().makeShapeFromMesh((points, [facet]), 0.1)
        shape = Part.Shape()
        shape.makeShapeFromMesh((points, [(0, 1, 2)]), 0.1, False)
        self.assertEqual(len(shape.Faces), 1)


class PartConstructorExceptionTests(unittest.TestCase):
    """A C++ exception thrown while constructing a Python object must become a Python
    exception instead of terminating the application."""

    def testInvalidArgumentsRaise(self):
        V = Base.Vector
        cases = [
            ("Circle with null normal", lambda: Part.Circle(V(0, 0, 0), V(0, 0, 0), 1)),
            ("Plane with null normal", lambda: Part.Plane(V(0, 0, 0), V(0, 0, 0))),
            ("Solid from null shape", lambda: Part.Solid(Part.Shape())),
            ("Solid from null shell", lambda: Part.Solid(Part.Shell())),
            (
                "RectangularTrimmedSurface with empty range",
                lambda: Part.RectangularTrimmedSurface(Part.Plane(), 0, 0, 0, 0),
            ),
            (
                "RectangularTrimmedSurface beyond the period",
                lambda: Part.RectangularTrimmedSurface(Part.Sphere(), 0, 10, 0, 10),
            ),
        ]
        for name, make in cases:
            with self.subTest(name):
                with self.assertRaises(Exception):
                    make()

    def testValidArgumentsStillWork(self):
        V = Base.Vector
        self.assertAlmostEqual(Part.Circle(V(0, 0, 0), V(0, 0, 1), 2).Radius, 2)
        self.assertEqual(Part.Plane(V(0, 0, 0), V(0, 0, 1)).Axis, V(0, 0, 1))
        self.assertAlmostEqual(Part.Solid(Part.makeBox(1, 1, 1).Shells[0]).Volume, 1)
        surf = Part.RectangularTrimmedSurface(Part.Plane(), 0, 1, 0, 2)
        self.assertAlmostEqual(surf.toShape().Area, 2)


class PartHLRBRepStateTests(unittest.TestCase):
    """HLRBRep methods called in the wrong state used to dereference null or
    exhausted OCCT data (access violation)."""

    def setUp(self):
        self.box = Part.makeBox(1, 1, 1)

    def testAlgoInitEdgeStatusNeedsUpdate(self):
        algo = Part.HLRBRep.Algo()
        with self.assertRaises(RuntimeError):
            algo.initEdgeStatus()
        algo.add(self.box)
        with self.assertRaises(RuntimeError):
            algo.initEdgeStatus()
        algo.update()
        algo.initEdgeStatus()
        algo.hide()
        self.assertEqual(algo.nbShapes(), 1)
        algo.remove(1)
        with self.assertRaises(RuntimeError):
            algo.initEdgeStatus()

    def testPolyAlgoNextPastTheEnd(self):
        algo = Part.HLRBRep.PolyAlgo()
        algo.load(self.box)
        algo.update()
        count = 0
        algo.initHide()
        while algo.moreHide():
            algo.nextHide()
            count += 1
        with self.assertRaises(RuntimeError):
            algo.nextHide()
        algo.initShow()
        while algo.moreShow():
            algo.nextShow()
        with self.assertRaises(RuntimeError):
            algo.nextShow()
        # the iteration can be restarted
        algo.initHide()
        again = 0
        while algo.moreHide():
            algo.nextHide()
            again += 1
        self.assertEqual(again, count)

    def testPolyHLRToShapeNeedsAlgo(self):
        for name in (
            "vCompound",
            "Rg1LineVCompound",
            "RgNLineVCompound",
            "outLineVCompound",
            "hCompound",
            "Rg1LineHCompound",
            "RgNLineHCompound",
            "outLineHCompound",
        ):
            with self.subTest(name):
                tool = Part.HLRBRep.PolyHLRToShape()
                with self.assertRaises(RuntimeError):
                    getattr(tool, name)()
                tool.show()
                tool.hide()
                with self.assertRaises(RuntimeError):
                    getattr(tool, name)(self.box)
        algo = Part.HLRBRep.PolyAlgo()
        algo.load(self.box)
        algo.update()
        tool = Part.HLRBRep.PolyHLRToShape()
        tool.update(algo)
        self.assertIsInstance(tool.vCompound(), Part.Shape)
        self.assertIsInstance(Part.HLRBRep.PolyHLRToShape(algo).hCompound(self.box), Part.Shape)


class PartGeometryCreateInstanceTests(unittest.TestCase):
    """Some geometry types have no OCCT object when default-constructed; wrapping
    one for Python copied the null handle (access violation)."""

    def testNullGeometryTypesRaise(self):
        for name in (
            "Part::GeomTrimmedCurve",
            "Part::GeomOffsetCurve",
            "Part::GeomOffsetSurface",
            "Part::GeomPlateSurface",
            "Part::GeomTrimmedSurface",
            "Part::GeomSurfaceOfRevolution",
            "Part::GeomSurfaceOfExtrusion",
        ):
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    Base.TypeId.fromName(name).createInstance()

    def testDefaultGeometryTypesStillWork(self):
        circle = Base.TypeId.fromName("Part::GeomCircle").createInstance()
        self.assertIsInstance(circle, Part.Circle)
        line = Base.TypeId.fromName("Part::GeomLineSegment").createInstance()
        self.assertIsInstance(line, Part.LineSegment)
        self.assertIsInstance(str(line), str)
        plane = Base.TypeId.fromName("Part::GeomPlane").createInstance()
        self.assertIsInstance(plane, Part.Plane)


class PartCompoundFilterTests(unittest.TestCase):
    """CompoundFilter 'specific items' mode with index ranges."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartCompoundFilterTests")
        boxes = []
        for i in range(5):
            box = Part.makeBox(1, 1, 1)
            box.translate(FreeCAD.Vector(2 * i, 0, 0))
            boxes.append(box)
        self.base = self.Doc.addObject("Part::Feature", "Base")
        self.base.Shape = Part.makeCompound(boxes)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def _filter(self, items, invert):
        from CompoundTools.CompoundFilter import makeCompoundFilter

        cf = makeCompoundFilter("Filter", self.Doc)
        cf.Base = self.base
        cf.FilterType = "specific items"
        cf.items = items
        cf.Invert = invert
        self.Doc.recompute()
        return sorted(round(s.BoundBox.XMin) for s in cf.Shape.childShapes())

    def testRange(self):
        self.assertEqual(self._filter("1:3", False), [2, 4])
        self.assertEqual(self._filter("0;3:", False), [0, 6, 8])

    def testInvertedRange(self):
        # The pieces picked by a range must be left out when inverted, like
        # pieces picked by a single index.
        self.assertEqual(self._filter("1:3", True), [0, 6, 8])
        self.assertEqual(self._filter("::2", True), [2, 6])
        self.assertEqual(self._filter("4;0:2", True), [4, 6])


class PartGroupCycleShapeTests(unittest.TestCase):
    """A group that contains itself (Group refuses that, but old files may contain
    one); Part.getShape() recursed into its children until the stack overflowed."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartGroupCycleShape")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def _reopenWithLinkReplaced(self, old, new):
        # save, point the Group link to `old` at `new` in Document.xml, reopen
        import os
        import tempfile
        import zipfile

        tempdir = tempfile.mkdtemp()
        path = os.path.join(tempdir, "PartGroupCycleShape.FCStd")
        self.addCleanup(os.rmdir, tempdir)
        self.addCleanup(os.remove, path)
        self.Doc.saveAs(path)
        FreeCAD.closeDocument(self.Doc.Name)
        with zipfile.ZipFile(path) as zin:
            entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
        with zipfile.ZipFile(path, "w") as zout:
            for info, data in entries:
                if info.filename == "Document.xml":
                    text = data.decode("utf-8")
                    link = '<Link value="{}"/>'
                    self.assertEqual(text.count(link.format(old)), 1)
                    data = text.replace(link.format(old), link.format(new)).encode("utf-8")
                zout.writestr(info, data)
        self.Doc = FreeCAD.openDocument(path)

    def testSelfContainingPart(self):
        part = self.Doc.addObject("App::Part", "Part")
        part.Group = [self.Doc.addObject("App::FeatureTest", "Placeholder")]
        self._reopenWithLinkReplaced("Placeholder", "Part")
        part = self.Doc.getObject("Part")
        self.assertEqual(part.Group, [part])
        self.assertTrue(Part.getShape(part).isNull())

    def testMutuallyContainingParts(self):
        part1 = self.Doc.addObject("App::Part", "Part1")
        part2 = self.Doc.addObject("App::Part", "Part2")
        box = self.Doc.addObject("Part::Box", "Box")
        self.Doc.recompute()
        part1.Group = [part2, box]
        part2.Group = [self.Doc.addObject("App::FeatureTest", "Placeholder")]
        self._reopenWithLinkReplaced("Placeholder", "Part1")
        part1 = self.Doc.getObject("Part1")
        part2 = self.Doc.getObject("Part2")
        self.assertEqual(part2.Group, [part1])
        Part.getShape(part1)
        Part.getShape(part2)

    def testNestedPartsStillWork(self):
        part1 = self.Doc.addObject("App::Part", "Part1")
        part2 = part1.newObject("App::Part", "Part2")
        box = part2.newObject("Part::Box", "Box")
        self.Doc.recompute()
        shape = Part.getShape(part1)
        self.assertFalse(shape.isNull())
        self.assertAlmostEqual(shape.Volume, box.Shape.Volume)


class PartPrismNaNTests(unittest.TestCase):
    """NaN passed the height and angle checks of Prism and Cylinder; the prism built
    along the NaN vector crashed FreeCAD (segmentation fault) when it was used."""

    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartPrismNaN")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def testNaNHeightOrAngleFails(self):
        nan = float("nan")
        for typeName, prop in (
            ("Part::Prism", "Height"),
            ("Part::Prism", "FirstAngle"),
            ("Part::Prism", "SecondAngle"),
            ("Part::Cylinder", "FirstAngle"),
            ("Part::Cylinder", "SecondAngle"),
        ):
            with self.subTest(type=typeName, prop=prop):
                feature = self.Doc.addObject(typeName, "Feature")
                # assigning NaN raises: it can only come from a file
                restoreValueAsFromFile(feature, prop, nan)
                self.Doc.recompute()
                # checking the NaN prism crashed (segmentation fault)
                self.assertTrue(feature.Shape.isNull() or not feature.Shape.isValid())
                self.assertIn("Invalid", feature.State)
                self.Doc.removeObject(feature.Name)

    def testFiniteAnglesStillWork(self):
        prism = self.Doc.addObject("Part::Prism", "Prism")
        prism.FirstAngle = 10
        prism.SecondAngle = -10
        self.Doc.recompute()
        self.assertNotIn("Invalid", prism.State)
        self.assertTrue(prism.Shape.isValid())
        self.assertGreater(prism.Shape.Volume, 0)
