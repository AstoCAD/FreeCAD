# SPDX-License-Identifier: LGPL-2.1-or-later

#  Copyright (c) 2007 Jürgen Riegel <juergen.riegel@web.de>
#  LGPL

import os
import sys
import io
import FreeCAD, unittest, Mesh
import MeshEnums
from FreeCAD import Base
import time, tempfile, math

# http://python-kurs.eu/threads.php
try:
    import _thread as thread
except Exception:
    import thread

from os.path import join

# ---------------------------------------------------------------------------
# define the functions to test the FreeCAD mesh module
# ---------------------------------------------------------------------------


class MeshTopoTestCases(unittest.TestCase):
    def setUp(self):
        # set up a planar face with 18 triangles
        self.planarMesh = []
        for x in range(3):
            for y in range(3):
                self.planarMesh.append([0.0 + x, 0.0 + y, 0.0000])
                self.planarMesh.append([1.0 + x, 1.0 + y, 0.0000])
                self.planarMesh.append([0.0 + x, 1.0 + y, 0.0000])
                self.planarMesh.append([0.0 + x, 0.0 + y, 0.0000])
                self.planarMesh.append([1.0 + x, 0.0 + y, 0.0000])
                self.planarMesh.append([1.0 + x, 1.0 + y, 0.0000])

    def testCollapseFacetsSingle(self):
        for i in range(18):
            planarMeshObject = Mesh.Mesh(self.planarMesh)
            planarMeshObject.collapseFacets([i])

    def testCollapseFacetsMultible(self):
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        planarMeshObject.collapseFacets(range(7))

    def testCollapseFacetsAll(self):
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        planarMeshObject.collapseFacets(range(18))

    # fmt: off
    def testCorruptedFacet(self):
        v = FreeCAD.Vector
        mesh = Mesh.Mesh()
        mesh.addFacet(
        v(1.0e1, -1.0e1, 1.0e1),
        v(1.0e1, +1.0e1, 1.0e1),
        v(0.0e0, 0.0e0, 1.0e1))

        mesh.addFacet(
        v(-1.0e1, -1.0e1, 1.0e1),
        v(-1.0e1, +1.0e1, 1.0e1),
        v(0e0, 0.0e0, 1.0e1))

        mesh.addFacet(
        v(+1.0e1, +1.0e1, 1.0e1),
        v(-1.0e1, +1.0e1, 1.0e1),
        v(.0e0, 0.0e0, 1.0e1))

        mesh.addFacet(
        v(+1.0e1, -1.0e1, 1.0e1),
        v(-1.0e1, -1.0e1, 1.0e1),
        v(.0e0, 0.0e0, 1.0e1))

        mesh.addFacet(
        v(-1.0e1, +1.0e1, 1.0e1),
        v(+1.0e1, +1.0e1, 1.0e1),
        v(+1.0e1, +1.0e1, 1.0e1))

        mesh.addFacet(
        v(+1.0e1, +1.0e1, 1.0e1),
        v(+1.0e1, 00.0e1, 1.0e1),
        v(+1.0e1, -1.0e1, 1.0e1))

        self.assertEqual(mesh.CountFacets, 6)
        mesh.fixIndices()
        self.assertEqual(mesh.CountFacets, 5)


# fmt: on


class MeshSplitTestCases(unittest.TestCase):
    def setUp(self):
        self.mesh = Mesh.createBox(1.0, 1.0, 1.0)

    def testSplitFacetOnOneEdge(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, p1, (p2 + p3) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_21(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p1 + p3) / 2, (p2 + p3) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_12(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p2 + p3) / 2, (p1 + p3) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_01(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p1 + p2) / 2, (p2 + p3) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_10(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p2 + p3) / 2, (p1 + p2) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_02(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p1 + p2) / 2, (p1 + p3) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_20(self):
        p1 = self.mesh.Points[0].Vector
        p2 = self.mesh.Points[1].Vector
        p3 = self.mesh.Points[2].Vector
        self.mesh.splitFacet(0, (p1 + p3) / 2, (p1 + p2) / 2)
        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testSplitFacetOnTwoEdges_5teps(self):
        Vec3d = FreeCAD.Vector
        for i in range(5):
            f = self.mesh.Facets[0]
            p1 = Vec3d(f.Points[0])
            p2 = Vec3d(f.Points[1])
            p3 = Vec3d(f.Points[2])
            self.mesh.splitFacet(0, (p1 + p3) / 2, (p2 + p3) / 2)

        self.assertFalse(self.mesh.hasNonManifolds())
        self.assertFalse(self.mesh.hasInvalidNeighbourhood())
        self.assertFalse(self.mesh.hasPointsOutOfRange())
        self.assertFalse(self.mesh.hasFacetsOutOfRange())
        self.assertFalse(self.mesh.hasCorruptedFacets())
        self.assertTrue(self.mesh.isSolid())

    def testFindNearest(self):
        self.assertEqual(len(self.mesh.nearestFacetOnRay((-2, 2, -6), (0, 0, 1))), 0)
        self.assertEqual(len(self.mesh.nearestFacetOnRay((0.5, 0.5, 0.5), (0, 0, 1))), 1)
        self.assertEqual(
            len(self.mesh.nearestFacetOnRay((0.5, 0.5, 0.5), (0, 0, 1), -math.pi / 2)), 0
        )
        self.assertEqual(
            len(self.mesh.nearestFacetOnRay((0.2, 0.1, 0.2), (0, 0, 1))),
            len(self.mesh.nearestFacetOnRay((0.2, 0.1, 0.2), (0, 0, -1))),
        )
        self.assertEqual(
            len(self.mesh.nearestFacetOnRay((0.2, 0.1, 0.2), (0, 0, 1), math.pi / 2)),
            len(self.mesh.nearestFacetOnRay((0.2, 0.1, 0.2), (0, 0, -1), math.pi / 2)),
        )
        # Apply placement to mesh
        plm = Base.Placement(Base.Vector(1, 2, 3), Base.Rotation(1, 1, 1, 1))
        pnt = Base.Vector(0.5, 0.5, 0.5)
        vec = Base.Vector(0.0, 0.0, 1.0)

        self.mesh.Placement = plm
        self.assertEqual(len(self.mesh.nearestFacetOnRay(pnt, vec)), 0)

        # Apply the placement on the ray as well
        pnt = plm.multVec(pnt)
        vec = plm.Rotation.multVec(vec)
        self.assertEqual(len(self.mesh.nearestFacetOnRay(pnt, vec)), 1)

    def testForaminate(self):
        class FilterAngle:
            def __init__(self, mesh, vec, limit):
                self.myMesh = mesh
                self.vec = vec
                self.limit = limit

            def check_angle(self, item):
                angle = self.myMesh.Facets[item].Normal.getAngle(self.vec)
                return angle < self.limit

        results = self.mesh.foraminate((0.0, 0.0, 0.0), (0, 1, 1))
        filtered_result = list(
            filter(
                FilterAngle(self.mesh, FreeCAD.Vector(0, 1, 1), math.pi / 2).check_angle,
                results.keys(),
            )
        )

        self.assertEqual(
            filtered_result, list(self.mesh.foraminate((0.0, 0.0, 0.0), (0, 1, 1), math.pi / 2))
        )

    def testForaminatePlacement(self):
        pnt = Base.Vector(0.0, 0.0, 0.0)
        vec = Base.Vector(0.0, 1.0, 1.0)
        results = self.mesh.foraminate(pnt, vec)
        self.assertEqual(len(results), 4)

        # Apply placement to mesh
        plm = Base.Placement(Base.Vector(1, 2, 3), Base.Rotation(1, 1, 1, 1))
        self.mesh.Placement = plm
        self.assertEqual(len(self.mesh.foraminate(pnt, vec)), 0)

        # Apply the placement on the ray as well
        pnt = plm.multVec(pnt)
        vec = plm.Rotation.multVec(vec)
        results2 = self.mesh.foraminate(pnt, vec)
        self.assertEqual(len(results2), 4)
        self.assertEqual(list(results), list(results2))


class MeshGeoTestCases(unittest.TestCase):
    def setUp(self):
        # set up a planar face with 2 triangles
        self.planarMesh = []

    def testIntersection(self):
        self.planarMesh.append([0.9961, 1.5413, 4.3943])
        self.planarMesh.append([9.4796, 10.024, -3.0937])
        self.planarMesh.append([1.4308, 11.3841, 2.6829])
        self.planarMesh.append([2.6493, 2.2536, 3.0679])
        self.planarMesh.append([13.1126, 0.4857, -4.4417])
        self.planarMesh.append([10.2410, 8.9040, -3.5002])
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertTrue(len(res) == 0)

    def testIntersection2(self):
        self.planarMesh.append([-16.097176, -29.891157, 15.987688])
        self.planarMesh.append([-16.176304, -29.859991, 15.947966])
        self.planarMesh.append([-16.071451, -29.900553, 15.912505])
        self.planarMesh.append([-16.092241, -29.893408, 16.020439])
        self.planarMesh.append([-16.007210, -29.926180, 15.967641])
        self.planarMesh.append([-16.064457, -29.904951, 16.090832])
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        # does definitely NOT intersect
        res = f1.intersect(f2)
        self.assertTrue(len(res) == 0)

    def testIntersectionOfTransformedMesh(self):
        self.planarMesh.append([0.0, 10.0, 10.0])
        self.planarMesh.append([10.0, 0.0, 10.0])
        self.planarMesh.append([10.0, 10.0, 10.0])
        self.planarMesh.append([6.0, 8.0, 10.0])
        self.planarMesh.append([16.0, 8.0, 10.0])
        self.planarMesh.append([6.0, 18.0, 10.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        mat = Base.Matrix()
        mat.rotateX(1.0)
        mat.rotateY(1.0)
        mat.rotateZ(1.0)
        planarMeshObject.transformGeometry(mat)

        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertEqual(len(res), 2)

    def testIntersectionOfParallelTriangles(self):
        self.planarMesh.append([0.0, 10.0, 10.0])
        self.planarMesh.append([10.0, 0.0, 10.0])
        self.planarMesh.append([10.0, 10.0, 10.0])
        self.planarMesh.append([6.0, 8.0, 10.1])
        self.planarMesh.append([16.0, 8.0, 10.1])
        self.planarMesh.append([6.0, 18.0, 10.1])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        mat = Base.Matrix()
        mat.rotateX(1.0)
        mat.rotateY(1.0)
        mat.rotateZ(1.0)
        planarMeshObject.transformGeometry(mat)

        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertTrue(len(res) == 0)

    def testIntersectionOnEdge(self):
        self.planarMesh.append([5.0, -1.9371663331985474, 0.49737977981567383])
        self.planarMesh.append([4.0, -1.9371663331985474, 0.49737977981567383])
        self.planarMesh.append([5.0, -1.9842294454574585, 0.25066646933555603])
        self.planarMesh.append([4.6488823890686035, -1.7827962636947632, 0.4577442705631256])
        self.planarMesh.append([4.524135112762451, -2.0620131492614746, 0.5294350385665894])
        self.planarMesh.append([4.6488823890686035, -1.8261089324951172, 0.23069120943546295])
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertEqual(len(res), 2)

    def testIntersectionCoplanar(self):
        self.planarMesh.append([0.0, 10.0, 10.0])
        self.planarMesh.append([10.0, 0.0, 10.0])
        self.planarMesh.append([10.0, 10.0, 10.0])
        self.planarMesh.append([6.0, 8.0, 10.0])
        self.planarMesh.append([16.0, 8.0, 10.0])
        self.planarMesh.append([6.0, 18.0, 10.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertTrue(len(res) == 2)

    def testIntersectionOverlap(self):
        self.planarMesh.append([0.0, 0.0, 0.0])
        self.planarMesh.append([5.0, 0.0, 0.0])
        self.planarMesh.append([8.0, 5.0, 0.0])
        self.planarMesh.append([4.0, 0.0, 0.0])
        self.planarMesh.append([10.0, 0.0, 0.0])
        self.planarMesh.append([9.0, 5.0, 0.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)
        f1 = planarMeshObject.Facets[0]
        f2 = planarMeshObject.Facets[1]
        res = f1.intersect(f2)
        self.assertTrue(len(res) == 2)

    def testIntersectionOfIntersectingEdges(self):
        self.planarMesh.append([0.0, 10.0, 10.0])
        self.planarMesh.append([10.0, 0.0, 10.0])
        self.planarMesh.append([10.0, 10.0, 10.0])
        self.planarMesh.append([6.0, 8.0, 10.0])
        self.planarMesh.append([16.0, 8.0, 10.0])
        self.planarMesh.append([6.0, 18.0, 10.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        edge1 = planarMeshObject.Facets[0].getEdge(2)
        edge2 = planarMeshObject.Facets[1].getEdge(2)
        res = edge1.intersectWithEdge(edge2)
        self.assertTrue(len(res) == 1)
        self.assertEqual(res[0][0], 6.0)
        self.assertEqual(res[0][1], 10.0)
        self.assertEqual(res[0][2], 10.0)

    def testIntersectionOfParallelEdges(self):
        self.planarMesh.append([0.0, 10.0, 10.0])
        self.planarMesh.append([10.0, 0.0, 10.0])
        self.planarMesh.append([10.0, 10.0, 10.0])
        self.planarMesh.append([6.0, 8.0, 10.0])
        self.planarMesh.append([16.0, 8.0, 10.0])
        self.planarMesh.append([6.0, 18.0, 10.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        edge1 = planarMeshObject.Facets[0].getEdge(2)
        edge2 = planarMeshObject.Facets[1].getEdge(0)
        res = edge1.intersectWithEdge(edge2)
        self.assertTrue(len(res) == 0)

    def testIntersectionOfCollinearEdges(self):
        self.planarMesh.append([0.0, 0.0, 0.0])
        self.planarMesh.append([6.0, 0.0, 0.0])
        self.planarMesh.append([3.0, 4.0, 0.0])
        self.planarMesh.append([7.0, 0.0, 0.0])
        self.planarMesh.append([13.0, 0.0, 0.0])
        self.planarMesh.append([10.0, 4.0, 0.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        edge1 = planarMeshObject.Facets[0].getEdge(0)
        edge2 = planarMeshObject.Facets[1].getEdge(0)
        res = edge1.intersectWithEdge(edge2)
        self.assertTrue(len(res) == 0)

    def testIntersectionOfWarpedEdges(self):
        self.planarMesh.append([0.0, 0.0, 0.0])
        self.planarMesh.append([6.0, 0.0, 0.0])
        self.planarMesh.append([3.0, 4.0, 0.0])
        self.planarMesh.append([2.0, 2.0, 1.0])
        self.planarMesh.append([8.0, 2.0, 1.0])
        self.planarMesh.append([5.0, 6.0, 1.0])
        planarMeshObject = Mesh.Mesh(self.planarMesh)

        edge1 = planarMeshObject.Facets[0].getEdge(1)
        edge2 = planarMeshObject.Facets[1].getEdge(0)
        res = edge1.intersectWithEdge(edge2)
        self.assertTrue(len(res) == 0)

    def testSelfIntersection(self):
        s = b"""solid Simple
facet normal 0.0e0 0.0e0 1.0e1
    outer loop
        vertex 0.0e1 0.0e1 1.0e1
        vertex 0.0e1 +1.0e1 1.0e1
        vertex +1.0e1 0.0e1 1.0e1
    endloop
endfacet
facet normal 0.0e0 0.0e0 1.0e1
    outer loop
        vertex 0.0e1 +1.0e1 1.0e1
        vertex +1.0e1 0.0e1 1.0e1
        vertex 1.0e1 1.0e1 1.0e1
    endloop
endfacet
facet normal 0.0e0 0.0e0 1.0e1
    outer loop
        vertex 0.0e1 0.0e1 1.0e1
        vertex 0.0e1 +1.0e1 1.0e1
        vertex -1.0e1 1.0e1 1.0e1
    endloop
endfacet
facet normal 0.0e0 0.0e0 1.0e1
    outer loop
        vertex 0.0e1 0.0e1 1.0e1
        vertex +1.0e1 0.0e1 1.0e1
        vertex +1.0e1 -1.0e1 1.0e1
    endloop
endfacet
facet normal 0.0e0 0.0e0 1.0e1
    outer loop
        vertex 0.6e1 0.8e1 1.0e1
        vertex +1.6e1 0.8e1 1.0e1
        vertex +0.6e1 1.8e1 1.0e1
    endloop
endfacet
endsolid Simple"""
        mesh = Mesh.Mesh()
        data = io.BytesIO(s)
        mesh.read(Stream=data, Format="AST")
        self.assertTrue(mesh.hasSelfIntersections())


# Threads


def loadFile(name):
    # lock.acquire()
    mesh = Mesh.Mesh()
    # FreeCAD.Console.PrintMessage("Create mesh instance\n")
    # lock.release()
    mesh.read(name)
    # FreeCAD.Console.PrintMessage("Mesh loaded successfully.\n")


def createMesh(r, s):
    # FreeCAD.Console.PrintMessage("Create sphere (%s,%s)...\n"%(r,s))
    mesh = Mesh.createSphere(r, s)
    # FreeCAD.Console.PrintMessage("... destroy sphere\n")


class LoadMeshInThreadsCases(unittest.TestCase):
    def setUp(self):
        pass

    def testSphereMesh(self):
        for i in range(6, 8):
            thread.start_new(createMesh, (10.0, (i + 1) * 20))
        time.sleep(10)

    def testLoadMesh(self):
        mesh = Mesh.createSphere(10.0, 100)  # a fine sphere
        name = tempfile.gettempdir() + os.sep + "mesh.stl"
        mesh.write(name)
        # FreeCAD.Console.PrintMessage("Write mesh to %s\n"%(name))
        # lock=thread.allocate_lock()
        for i in range(2):
            thread.start_new(loadFile, (name,))
        time.sleep(1)

    def tearDown(self):
        pass


class PolynomialFitCases(unittest.TestCase):
    def setUp(self):
        pass

    def testFitGood(self):
        # symmetric
        v = []
        v.append(FreeCAD.Vector(0, 0, 0.0))
        v.append(FreeCAD.Vector(1, 0, 0.5))
        v.append(FreeCAD.Vector(2, 0, 0.0))
        v.append(FreeCAD.Vector(0, 1, 0.5))
        v.append(FreeCAD.Vector(1, 1, 1.0))
        v.append(FreeCAD.Vector(2, 1, 0.5))
        v.append(FreeCAD.Vector(0, 2, 0.0))
        v.append(FreeCAD.Vector(1, 2, 0.5))
        v.append(FreeCAD.Vector(2, 2, 0.0))
        d = Mesh.polynomialFit(v)
        c = d["Coefficients"]
        # print ("Polynomial: f(x,y)=%f*x^2%+f*y^2%+f*x*y%+f*x%+f*y%+f" % (c[0],c[1],c[2],c[3],c[4],c[5]))
        for i in d["Residuals"]:
            self.assertTrue(math.fabs(i) < 0.0001, "Too high residual %f" % math.fabs(i))

    def testFitExact(self):
        # symmetric
        v = []
        v.append(FreeCAD.Vector(0, 0, 0.0))
        v.append(FreeCAD.Vector(1, 0, 0.0))
        v.append(FreeCAD.Vector(2, 0, 0.0))
        v.append(FreeCAD.Vector(0, 1, 0.0))
        v.append(FreeCAD.Vector(1, 1, 1.0))
        v.append(FreeCAD.Vector(2, 1, 0.0))
        d = Mesh.polynomialFit(v)
        c = d["Coefficients"]
        # print ("Polynomial: f(x,y)=%f*x^2%+f*y^2%+f*x*y%+f*x%+f*y%+f" % (c[0],c[1],c[2],c[3],c[4],c[5]))
        for i in d["Residuals"]:
            self.assertTrue(math.fabs(i) < 0.0001, "Too high residual %f" % math.fabs(i))

    def testFitBad(self):
        # symmetric
        v = []
        v.append(FreeCAD.Vector(0, 0, 0.0))
        v.append(FreeCAD.Vector(1, 0, 0.0))
        v.append(FreeCAD.Vector(2, 0, 0.0))
        v.append(FreeCAD.Vector(0, 1, 0.0))
        v.append(FreeCAD.Vector(1, 1, 1.0))
        v.append(FreeCAD.Vector(2, 1, 0.0))
        v.append(FreeCAD.Vector(0, 2, 0.0))
        v.append(FreeCAD.Vector(1, 2, 0.0))
        v.append(FreeCAD.Vector(2, 2, 0.0))
        d = Mesh.polynomialFit(v)
        c = d["Coefficients"]
        # print ("Polynomial: f(x,y)=%f*x^2%+f*y^2%+f*x*y%+f*x%+f*y%+f" % (c[0],c[1],c[2],c[3],c[4],c[5]))
        for i in d["Residuals"]:
            self.assertFalse(math.fabs(i) < 0.0001, "Residual %f must be higher" % math.fabs(i))

    def tearDown(self):
        pass


class NastranReader(unittest.TestCase):
    def setUp(self):
        self.test_dir = join(FreeCAD.getHomePath(), "Mod", "Mesh", "App", "TestData")

    def testEightCharGRIDElement(self):
        m = Mesh.read(f"{self.test_dir}/NASTRAN_Test_GRID_CQUAD4.bdf")
        self.assertEqual(m.CountPoints, 10)
        self.assertEqual(m.CountFacets, 8)  # Quads split into two triangles

    def testDelimitedGRIDElement(self):
        m = Mesh.read(f"{self.test_dir}/NASTRAN_Test_Delimited_GRID_CQUAD4.bdf")
        self.assertEqual(m.CountPoints, 10)
        self.assertEqual(m.CountFacets, 8)  # Quads split into two triangles

    def testSixteenCharGRIDElement(self):
        m = Mesh.read(f"{self.test_dir}/NASTRAN_Test_GRIDSTAR_CQUAD4.bdf")
        self.assertEqual(m.CountPoints, 4)
        self.assertEqual(m.CountFacets, 2)  # Quads split into two triangles

    def testCTRIA3Element(self):
        m = Mesh.read(f"{self.test_dir}/NASTRAN_Test_GRID_CTRIA3.bdf")
        self.assertEqual(m.CountPoints, 3)
        self.assertEqual(m.CountFacets, 1)

    def tearDown(self):
        pass


class MeshSubElement(unittest.TestCase):
    def setUp(self):
        self.mesh = Mesh.createBox(1.0, 1.0, 1.0)

    def testCenterOfGravity(self):
        c = self.mesh.CenterOfGravity
        self.assertEqual(c, Base.Vector(0.0, 0.0, 0.0))

    def testSubElements(self):
        types = self.mesh.getElementTypes()
        self.assertIn("Mesh", types)
        self.assertIn("Segment", types)

    def testCountSubElements(self):
        self.assertEqual(self.mesh.countSubElements("Mesh"), 1)
        self.assertEqual(self.mesh.countSubElements("Segment"), 0)

    def testFacesFromSubElement(self):
        element = self.mesh.getFacesFromSubElement("Mesh", 0)
        self.assertIsInstance(element, tuple)
        self.assertEqual(len(element), 2)
        self.assertEqual(len(element[0]), 8)
        self.assertEqual(len(element[1]), 12)

    def testSegmentSubElement(self):
        self.mesh.addSegment([0, 2, 4, 6, 8])
        self.assertEqual(self.mesh.countSegments(), 1)
        self.assertEqual(self.mesh.countSubElements("Segment"), 1)
        element = self.mesh.getFacesFromSubElement("Segment", 0)
        self.assertIsInstance(element, tuple)
        self.assertEqual(len(element), 2)
        self.assertEqual(len(element[0]), 7)
        self.assertEqual(len(element[1]), 5)
        segment = self.mesh.meshFromSegment(self.mesh.getSegment(0))
        self.assertEqual(segment.CountPoints, 7)
        self.assertEqual(segment.CountFacets, 5)

    def tearDown(self):
        pass


class MeshFacetIndexRange(unittest.TestCase):
    """Out-of-range facet indices must raise instead of accessing invalid memory"""

    def setUp(self):
        self.mesh = Mesh.createBox(1.0, 1.0, 1.0)

    def testRemoveFacets(self):
        with self.assertRaises(IndexError):
            self.mesh.removeFacets([12])
        with self.assertRaises(IndexError):
            self.mesh.removeFacets([-1])
        self.assertEqual(self.mesh.CountFacets, 12)
        self.mesh.removeFacets([0, 11])
        self.assertEqual(self.mesh.CountFacets, 10)

    def testCollapseFacets(self):
        with self.assertRaises(IndexError):
            self.mesh.collapseFacets([12])
        with self.assertRaises(IndexError):
            self.mesh.collapseFacets([-1])
        self.assertEqual(self.mesh.CountFacets, 12)

    def testMeshFromSegment(self):
        with self.assertRaises(IndexError):
            self.mesh.meshFromSegment([12])
        with self.assertRaises(IndexError):
            self.mesh.meshFromSegment([-1])
        with self.assertRaises(IndexError):
            Mesh.Mesh().meshFromSegment([0])
        self.assertEqual(self.mesh.meshFromSegment([0, 1]).CountFacets, 2)

    def testStaleFacet(self):
        facet = self.mesh.Facets[11]
        self.assertGreater(facet.Area, 0.0)
        self.mesh.clear()
        with self.assertRaises(IndexError):
            facet.isDegenerated()
        with self.assertRaises(IndexError):
            facet.isDeformed(0.1, 3.0)
        with self.assertRaises(IndexError):
            facet.Area
        with self.assertRaises(IndexError):
            facet.InCircle

    def testWireFromSegment(self):
        try:
            import MeshPart
        except ImportError:
            self.skipTest("MeshPart not available")
        with self.assertRaises(IndexError):
            MeshPart.wireFromSegment(self.mesh, [-1])
        with self.assertRaises(IndexError):
            MeshPart.wireFromSegment(self.mesh, [12])
        self.assertEqual(len(MeshPart.wireFromSegment(self.mesh, [0, 1])), 1)


class MeshHugeCoordinates(unittest.TestCase):
    """A facet with a huge coordinate must not be put outside the facet grid"""

    def testSelfIntersectionsWithHugeCoordinate(self):
        # The cell index of the bounding box maximum was computed as the grid size itself
        # (float rounding), so the facet grid wrote outside its cells (access violation).
        box = Mesh.createBox(10.0, 10.0, 10.0)
        facets = [list(f.Points) for f in box.Facets]
        facets.append([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 3.0e31)])
        mesh = Mesh.Mesh(facets)
        self.assertEqual(mesh.CountFacets, 13)
        self.assertIsInstance(mesh.hasSelfIntersections(), bool)
        self.assertIsInstance(mesh.getSelfIntersections(), (list, tuple))

    def testReadStlWithHugeCoordinate(self):
        text = (
            "solid huge\n"
            "facet normal 0 0 0\nouter loop\n"
            "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
            "endloop\nendfacet\n"
            "facet normal 0 0 0\nouter loop\n"
            "vertex 5 5 5\nvertex 6 5 5\nvertex 5 5 3.0e31\n"
            "endloop\nendfacet\n"
            "endsolid huge\n"
        )
        name = os.path.join(tempfile.gettempdir(), "mesh_huge_coordinate.ast")
        with open(name, "w") as f:
            f.write(text)
        try:
            mesh = Mesh.Mesh(name)
            self.assertEqual(mesh.CountFacets, 2)
            self.assertFalse(mesh.hasSelfIntersections())
        finally:
            os.remove(name)


class MeshCorruptedFacet(unittest.TestCase):
    """Removing a facet that references a point twice must erase that point only once"""

    def testFixIndicesRemovesIsolatedCorruptedFacet(self):
        # The point referenced twice was erased twice, the second time from an empty
        # point array (heap corruption, the process died).
        mesh = Mesh.Mesh()
        mesh.addFacets(([Base.Vector(0, 0, 0), Base.Vector(0, 0, 10)], [(0, 0, 1)]))
        self.assertEqual(mesh.CountFacets, 1)
        mesh.fixIndices()
        self.assertEqual(mesh.CountFacets, 0)
        self.assertEqual(mesh.CountPoints, 0)

    def testFixIndicesKeepsOtherFacets(self):
        points = [
            Base.Vector(0, 0, 0),
            Base.Vector(0, 0, 10),
            Base.Vector(1, 0, 0),
            Base.Vector(0, 1, 0),
            Base.Vector(5, 5, 5),
        ]
        mesh = Mesh.Mesh()
        mesh.addFacets((points, [(4, 0, 4), (1, 2, 3)]))
        mesh.fixIndices()
        self.assertEqual(mesh.CountFacets, 1)
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(
            [(p.x, p.y, p.z) for p in mesh.Points],
            [(0.0, 0.0, 10.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        )
        self.assertEqual(mesh.Topology[1], [(0, 1, 2)])


class MeshReadTruncatedOff(unittest.TestCase):
    """Reading an OFF file without the line of element counts must not hang"""

    def _read(self, text):
        name = os.path.join(tempfile.gettempdir(), "mesh_truncated_test.off")
        with open(name, "w") as f:
            f.write(text)
        try:
            return Mesh.Mesh(name)
        except Exception:
            return None
        finally:
            os.remove(name)

    def testTruncatedOff(self):
        # The reader looked for the counts line in an endless loop past the end of file
        for text in ("OFF\n", "OFF\n# comment\n", "OFF\n8 1e-320\n"):
            mesh = self._read(text)
            if mesh is not None:
                self.assertEqual(mesh.CountFacets, 0)

    def testOffWithHugeFaceVertexCount(self):
        # The reader reserved and looped over the announced vertex count of a face
        mesh = self._read("OFF\n3 1 0\n0 0 0\n1 0 0\n0 1 0\n2147483647 0 1 2\n")
        self.assertIsNotNone(mesh)
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)

    def testOffWithComment(self):
        mesh = self._read("OFF\n# comment\n3 1 0\n0 0 0\n1 0 0\n0 1 0\n3 0 1 2\n")
        self.assertIsNotNone(mesh)
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)


class MeshReadObjEscapedNames(unittest.TestCase):
    """Reading an OBJ file whose names hold a lone surrogate escape must not crash"""

    def _read(self, name):
        with tempfile.TemporaryDirectory() as tmpDir:
            fileName = os.path.join(tmpDir, "escaped_names.obj")
            with open(fileName, "w") as f:
                f.write("v 0 0 0\nv 1 0 0\nv 0 1 0\ng {}\nf 1 2 3\n".format(name))
            return Mesh.Mesh(fileName)

    def testLoneSurrogateGroupName(self):
        # The unescaped name has no UTF-8 form: a null pointer was copied
        mesh = self._read("\\ud800")
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)

    def testInvalidEscapeGroupName(self):
        # The decoding error was left pending: SystemError from Mesh.Mesh()
        mesh = self._read("\\x")
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)

    def testEscapedGroupName(self):
        mesh = self._read("\\u00e9")
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)


class MeshPartLoftOnCurve(unittest.TestCase):
    def testDegeneratedEdge(self):
        # A sphere has degenerated edges (no 3D curve) at its poles.
        # loftOnCurve() used to pass the null curve to OCC and crash.
        try:
            import MeshPart
            import Part
        except ImportError:
            self.skipTest("MeshPart not available")
        profile = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        sphere = Part.makeSphere(5)
        mesh = MeshPart.loftOnCurve(sphere, profile, (0.0, 0.0, 1.0), 1.0)
        self.assertGreater(mesh.CountFacets, 0)
        mesh = MeshPart.loftOnCurve(sphere, [], (0.0, 0.0, 1.0), 1.0)
        self.assertEqual(mesh.CountFacets, 0)

    def testCircle(self):
        try:
            import MeshPart
            import Part
        except ImportError:
            self.skipTest("MeshPart not available")
        profile = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        mesh = MeshPart.loftOnCurve(Part.makeCircle(5), profile, (0.0, 0.0, 1.0), 1.0)
        self.assertGreater(mesh.CountFacets, 0)


class MeshModuleExport(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("MeshExportTest")
        self.mesh = self.doc.addObject("Mesh::Feature", "Box")
        self.mesh.Mesh = Mesh.createBox(1.0, 1.0, 1.0)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testExportErrorRaisesPythonException(self):
        # Mesh.export() accepts keywords. Its C++ exceptions were not translated, so a
        # failing export escaped the Python interpreter as a C++ exception (aborting the
        # running script) instead of raising a Python exception.
        name = os.path.join(tempfile.gettempdir(), "no_such_mesh_export_dir", "box.amf")
        self.assertFalse(os.path.exists(os.path.dirname(name)))
        with self.assertRaises(RuntimeError):
            Mesh.export([self.mesh], name)
        with self.assertRaises(RuntimeError):
            Mesh.export([self.mesh], name, tolerance=0.1, exportAmfCompressed=False)


class MeshDumpContent(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("MeshDumpContentTest")
        self.mesh = self.doc.addObject("Mesh::Feature", "Box")
        self.mesh.Mesh = Mesh.createBox(1.0, 1.0, 1.0)

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testDumpContentInvalidCompression(self):
        # A compression level that zlib rejects used to abort the whole process
        # when the mesh data file was written.
        for level in (10, 1000000, -2):
            with self.assertRaises(ValueError):
                self.mesh.dumpContent(level)
        copy = self.doc.addObject("Mesh::Feature", "Copy")
        copy.restoreContent(self.mesh.dumpContent(3))
        self.assertEqual(copy.Mesh.CountFacets, self.mesh.Mesh.CountFacets)
        self.assertEqual(copy.Mesh.CountPoints, self.mesh.Mesh.CountPoints)

    def testMeshObjectDumpContentInvalidCompression(self):
        for level in (10, 1000000, -2):
            with self.assertRaises(ValueError):
                self.mesh.Mesh.dumpContent(level)
        self.assertIsInstance(self.mesh.Mesh.dumpContent(3), bytearray)


class MeshProperty(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("MeshTest")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _openWithInlineMesh(self, name, faceIndices, neighbourIndices=(-1, -1, -1)):
        """Save a document, replace the mesh file by an inline <Mesh> element and reopen it"""
        import re
        import zipfile

        mesh = self.doc.addObject("Mesh::Feature", "Triangle")
        mesh.Mesh = Mesh.Mesh([Base.Vector(0, 0, 0), Base.Vector(1, 0, 0), Base.Vector(0, 1, 0)])
        fileName = os.path.join(tempfile.gettempdir(), name + ".FCStd")
        inlineName = os.path.join(tempfile.gettempdir(), name + "_inline.FCStd")
        self.doc.saveAs(fileName)
        FreeCAD.closeDocument(self.doc.Name)

        p0, p1, p2 = faceIndices
        n0, n1, n2 = neighbourIndices
        inline = (
            '<Mesh file=""><Points Count="3">'
            '<P x="0" y="0" z="0"/><P x="1" y="0" z="0"/><P x="0" y="1" z="0"/>'
            '</Points><Faces Count="1">'
            '<F p0="{}" p1="{}" p2="{}" n0="{}" n1="{}" n2="{}"/>'
            "</Faces></Mesh>".format(p0, p1, p2, n0, n1, n2)
        )
        with zipfile.ZipFile(fileName) as src, zipfile.ZipFile(inlineName, "w") as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "Document.xml":
                    data = re.sub(rb'<Mesh file="[^"]*"/>', inline.encode(), data)
                dst.writestr(item, data)

        self.doc = FreeCAD.openDocument(inlineName)
        return self.doc.Triangle.Mesh

    def testInlineXmlRestore(self):
        mesh = self._openWithInlineMesh("mesh_inline_xml", (0, 1, 2))
        self.assertEqual(mesh.CountPoints, 3)
        self.assertEqual(mesh.CountFacets, 1)

    def testInlineXmlRestoreRejectsInvalidPointIndex(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33322
        mesh = self._openWithInlineMesh("mesh_inline_xml_invalid", (0, 1, 99))
        self.assertEqual(mesh.CountFacets, 0)

    def testInlineXmlRestoreRejectsInvalidNeighbourIndex(self):
        # A neighbour index past the facet array was read out of bounds later on,
        # e.g. removeFoldsOnSurface() raised an access violation.
        mesh = self._openWithInlineMesh("mesh_inline_xml_invalid_nb", (0, 1, 2), (99, -1, -1))
        self.assertEqual(mesh.CountFacets, 0)

    def testMaterial(self):
        mesh = self.doc.addObject("Mesh::Feature", "Sphere")
        mesh.Mesh = Mesh.createBox(1.0, 1.0, 1.0)
        len1 = int(mesh.Mesh.CountFacets / 2)
        len2 = int(mesh.Mesh.CountFacets - len1)
        material = {"transparency": [0.2] * len1 + [0.8] * len2}
        material["binding"] = MeshEnums.Binding.PER_FACE
        material["ambientColor"] = [(1, 0, 0)] * (len1 + len2)
        material["diffuseColor"] = [(0, 1, 0)] * (len1 + len2)
        material["specularColor"] = [(0, 0, 1)] * (len1 + len2)
        material["emissiveColor"] = [(1, 1, 1)] * (len1 + len2)
        material["shininess"] = [0.3] * (len1 + len2)

        mesh.addProperty("Mesh::PropertyMaterial", "Material")
        mesh.Material = material

        TempPath = tempfile.gettempdir()
        SaveName = TempPath + os.sep + "mesh_with_material.FCStd"
        self.doc.saveAs(SaveName)
        FreeCAD.closeDocument(self.doc.Name)

        self.doc = FreeCAD.openDocument(SaveName)
        mesh2 = self.doc.Sphere
        material2 = mesh2.Material

        self.assertEqual(int(material2["binding"]), int(MeshEnums.Binding.PER_FACE))
        self.assertEqual(len(material2["ambientColor"]), len1 + len2)
        self.assertEqual(len(material2["diffuseColor"]), len1 + len2)
        self.assertEqual(len(material2["specularColor"]), len1 + len2)
        self.assertEqual(len(material2["emissiveColor"]), len1 + len2)
        self.assertEqual(len(material2["shininess"]), len1 + len2)
        self.assertEqual(len(material2["transparency"]), len1 + len2)
