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

    def testAddFacetsWithPoints(self):
        # indices refer to the 8 existing points followed by the new one
        for facet in ((0, 0, -1), (0, 1, 9), (2**40, 0, 1)):
            with self.subTest(facet=facet):
                with self.assertRaises(IndexError):
                    self.mesh.addFacets(([Base.Vector(5, 5, 5)], [facet]))
        self.assertEqual(self.mesh.CountFacets, 12)
        self.assertEqual(self.mesh.CountPoints, 8)
        # the constructor uses the same code path
        with self.assertRaises(IndexError):
            Mesh.Mesh(([Base.Vector()], [(-1, 0, 0)]))
        mesh = Mesh.Mesh()
        points = [Base.Vector(0, 0, 0), Base.Vector(1, 0, 0), Base.Vector(0, 1, 0)]
        mesh.addFacets((points, [(0, 1, 2)]))
        self.assertEqual(mesh.CountFacets, 1)

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

    def testFindSectionParametersNullEdge(self):
        # a null edge was adapted as a curve (access violation)
        try:
            import MeshPart
            import Part
        except ImportError:
            self.skipTest("MeshPart not available")
        with self.assertRaises(ValueError):
            MeshPart.findSectionParameters(Part.Edge(), self.mesh, FreeCAD.Vector(0, 0, 1))
        edge = Part.makeLine(FreeCAD.Vector(-1, 0.5, 2), FreeCAD.Vector(2, 0.5, 2))
        params = MeshPart.findSectionParameters(edge, self.mesh, FreeCAD.Vector(0, 0, -1))
        self.assertIsInstance(params, list)


class MeshSmoothNegativeIteration(unittest.TestCase):
    """A negative iteration count must raise instead of smoothing ~4 billion times"""

    def testNegativeIteration(self):
        mesh = Mesh.createBox(1.0, 1.0, 1.0)
        for method in ("Laplace", "Taubin", "PlaneFit", "MedianFilter"):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    mesh.smooth(Method=method, Iteration=-1)
        mesh.smooth(Iteration=0)
        mesh.smooth(Iteration=2)
        self.assertEqual(mesh.CountFacets, 12)


class MeshOptimizeTopology(unittest.TestCase):
    def testSwapsEdgeWithBenefit(self):
        a = FreeCAD.Vector(0, 0, 0)
        b = FreeCAD.Vector(4, -1, 0)
        c = FreeCAD.Vector(8, 0, 0)
        d = FreeCAD.Vector(4, 1, 0)
        mesh = Mesh.Mesh([a, b, c, a, c, d])
        mesh.optimizeTopology()
        self.assertEqual(mesh.CountFacets, 2)
        for facet in mesh.Facets:
            points = [tuple(p) for p in facet.Points]
            self.assertIn(tuple(b), points)
            self.assertIn(tuple(d), points)

    def testSymmetricMeshTerminates(self):
        """Swaps whose benefit is rounding noise must not loop forever"""
        # The quads of a sphere are isosceles trapezoids: both diagonals were swapped
        # back and forth endlessly.
        mesh = Mesh.createSphere(1.0, 20)
        count = mesh.CountFacets
        volume = mesh.Volume
        mesh.optimizeTopology()
        self.assertEqual(mesh.CountFacets, count)
        self.assertAlmostEqual(mesh.Volume, volume, 3)


class MeshRegularGeomsNegativeSampling(unittest.TestCase):
    """A negative sampling count or edge length must fail instead of looping forever"""

    def testNegativeSampling(self):
        cases = {
            "sphere": lambda: Mesh.createSphere(1, -1),
            "ellipsoid": lambda: Mesh.createEllipsoid(1, 1, -1),
            "torus": lambda: Mesh.createTorus(2, 1, -1),
            "cylinder": lambda: Mesh.createCylinder(1, 1, 1, 0.5, -1),
            "cone": lambda: Mesh.createCone(1, 0.5, 1, 1, 0.5, -1),
            "cone edge length": lambda: Mesh.createCone(1, 0.5, 1, 1, -0.5, 10),
        }
        for name, make in cases.items():
            with self.subTest(name):
                with self.assertRaises(RuntimeError):
                    make()
        self.assertGreater(Mesh.createSphere(1, 10).CountFacets, 0)
        self.assertGreater(Mesh.createCone(1, 0.5, 1, 1, 0.5, 10).CountFacets, 0)


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


class MeshRemoveFacetsDuplicates(unittest.TestCase):
    """A facet index given twice to removeFacets() must remove that facet only once"""

    def setUp(self):
        points = [
            Base.Vector(0, 0, 0),
            Base.Vector(1, 0, 0),
            Base.Vector(0, 1, 0),
            Base.Vector(1, 1, 0),
            Base.Vector(2, 0, 0),
        ]
        self.mesh = Mesh.Mesh()
        self.mesh.addFacets((points, [(0, 1, 2), (2, 1, 3), (1, 4, 3)]))

    def testDuplicateIndex(self):
        # The points of the removed facet were released twice and deleted although the
        # other facets still use them: those facets then referenced the wrong points.
        expected = Mesh.Mesh(self.mesh)
        expected.removeFacets([0])
        self.mesh.removeFacets([0, 0])
        self.assertEqual(self.mesh.CountFacets, 2)
        self.assertEqual(self.mesh.CountPoints, 4)
        self.assertEqual(self.mesh.Topology, expected.Topology)

    def testDuplicateIndexOfLastFacets(self):
        self.mesh.removeFacets([2, 1, 2])
        self.assertEqual(self.mesh.CountFacets, 1)
        self.assertEqual(self.mesh.CountPoints, 3)
        self.assertEqual(
            [f.Points for f in self.mesh.Facets],
            [[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]],
        )


class MeshCollapseFacetSegments(unittest.TestCase):
    """Collapsing a facet also removes its neighbours: segments must follow all removals"""

    def setUp(self):
        self.mesh = Mesh.createBox(1, 1, 1)
        self.count = self.mesh.CountFacets

    def testCollapseFacetKeepsSegmentInRange(self):
        self.mesh.addSegment(list(range(self.count)))
        self.mesh.collapseFacet(3)
        # the segment kept indices of facets that no longer exist
        self.assertEqual(self.mesh.getSegment(0), list(range(self.mesh.CountFacets)))

    def testCollapseFacetRemapsSegment(self):
        last = self.count - 1
        removed = [0] + list(self.mesh.Facets[0].NeighbourIndices)
        self.assertNotIn(last, removed)
        self.mesh.addSegment([last])
        self.mesh.collapseFacet(0)
        self.assertEqual(self.mesh.CountFacets, self.count - len(removed))
        self.assertEqual(self.mesh.getSegment(0), [last - len(removed)])

    def testCollapseFacetsKeepsSegmentInRange(self):
        self.mesh.addSegment(list(range(self.count)))
        self.mesh.collapseFacets([0])
        segment = self.mesh.getSegment(0)
        self.assertEqual(segment, list(range(self.mesh.CountFacets)))
        self.assertEqual(self.mesh.meshFromSegment(segment).CountFacets, self.mesh.CountFacets)


class MeshSetOperationsPlacement(unittest.TestCase):
    """The Mesh::SetOperations feature works on the placed source meshes"""

    def setUp(self):
        self.doc = FreeCAD.newDocument("MeshSetOperationsPlacement")
        self.box1 = self.doc.addObject("Mesh::Feature", "Box1")
        self.box1.Mesh = Mesh.createBox(1.0, 1.0, 1.0)
        self.box2 = self.doc.addObject("Mesh::Feature", "Box2")
        self.box2.Mesh = Mesh.createBox(1.0, 1.0, 1.0)
        self.box2.Placement.Base = FreeCAD.Vector(0.5, 0.5, 0.5)
        self.op = self.doc.addObject("Mesh::SetOperations", "Operation")
        self.op.Source1 = self.box1
        self.op.Source2 = self.box2

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testOperations(self):
        # The placement of Box2 was ignored: both boxes coincided (union empty, intersection 1)
        for operation, volume in (("union", 1.875), ("intersection", 0.125), ("difference", 0.875)):
            self.op.OperationType = operation
            self.doc.recompute()
            self.assertAlmostEqual(self.op.Mesh.Volume, volume, 4, operation)

    def testSameAsPythonApi(self):
        self.op.OperationType = "union"
        self.doc.recompute()
        expected = self.box1.Mesh.unite(self.box2.Mesh)
        self.assertEqual(self.op.Mesh.CountFacets, expected.CountFacets)
        self.assertTrue(self.op.Mesh.BoundBox.isInside(expected.BoundBox))
        self.assertTrue(expected.BoundBox.isInside(self.op.Mesh.BoundBox))


class MeshSegmentByMeshPlacement(unittest.TestCase):
    """The Mesh::SegmentByMesh feature works on the placed source and tool meshes"""

    def setUp(self):
        self.doc = FreeCAD.newDocument("MeshSegmentByMeshPlacement")
        # a planar grid of 20 x 20 squares in the unit square
        n = 20
        points = [Base.Vector(i / n, j / n, 0) for j in range(n + 1) for i in range(n + 1)]
        facets = []
        for j in range(n):
            for i in range(n):
                k = j * (n + 1) + i
                facets.append((k, k + 1, k + n + 2))
                facets.append((k, k + n + 2, k + n + 1))
        self.source = self.doc.addObject("Mesh::Feature", "Source")
        self.source.Mesh = Mesh.Mesh((points, facets))
        # The feature casts rays along Normal (default +Z) and counts the tool facets
        # they cross. Keep every grid vertex off the tool sides and off the diagonals
        # of its top and bottom faces: a ray through a diagonal crosses two facets,
        # and whether it counts as inside then depends on rounding.
        tool = Mesh.createBox(0.43, 0.43, 3.0)
        tool.translate(0.51, 0.52, 0.0)
        self.tool = self.doc.addObject("Mesh::Feature", "Tool")
        self.tool.Mesh = tool
        self.segment = self.doc.addObject("Mesh::SegmentByMesh", "Segment")
        self.segment.Source = self.source
        self.segment.Tool = self.tool
        self.doc.recompute()
        self.count = self.segment.Mesh.CountFacets
        self.bound = self.segment.Mesh.BoundBox

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def testUnplaced(self):
        self.assertGreater(self.count, 0)
        self.assertLess(self.count, self.source.Mesh.CountFacets)
        self.assertTrue(self.tool.Mesh.BoundBox.isInside(self.bound.Center))

    def testSourceMovedAwayFromTool(self):
        # The placements were ignored: the segment stayed the same
        self.source.Placement.Base = FreeCAD.Vector(10, 0, 0)
        self.doc.recompute()
        self.assertEqual(self.segment.Mesh.CountFacets, 0)

    def testBothMoved(self):
        self.source.Placement.Base = FreeCAD.Vector(10, 0, 0)
        self.tool.Placement.Base = FreeCAD.Vector(10, 0, 0)
        self.doc.recompute()
        self.assertEqual(self.segment.Mesh.CountFacets, self.count)
        self.assertAlmostEqual(self.segment.Mesh.BoundBox.XMin, self.bound.XMin + 10, 4)
        self.assertAlmostEqual(self.segment.Mesh.BoundBox.XMax, self.bound.XMax + 10, 4)


class MeshPartWirePlacement(unittest.TestCase):
    """MeshPart.wireFromSegment() and wireFromMesh() return the wires at the placed mesh"""

    def setUp(self):
        self.mesh = Mesh.createBox(1.0, 1.0, 1.0)
        self.mesh.removeFacets([0])
        self.placed = Mesh.Mesh(self.mesh)
        self.placed.Placement = FreeCAD.Placement(
            FreeCAD.Vector(10, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        )

    def checkWires(self, wires, placedWires):
        # The placement was ignored: the wires were at the unplaced mesh
        self.assertEqual(len(placedWires), len(wires))
        self.assertGreater(len(wires), 0)
        for wire, placedWire in zip(wires, placedWires):
            wire = wire.copy()
            wire.Placement = self.placed.Placement
            for v1, v2 in zip(wire.Vertexes, placedWire.Vertexes):
                self.assertLess(v1.Point.distanceToPoint(v2.Point), 1e-6)

    def testWireFromSegment(self):
        import MeshPart

        self.checkWires(
            MeshPart.wireFromSegment(self.mesh, [0, 1]),
            MeshPart.wireFromSegment(self.placed, [0, 1]),
        )

    def testWireFromMesh(self):
        import MeshPart

        self.checkWires(MeshPart.wireFromMesh(self.mesh), MeshPart.wireFromMesh(self.placed))


class MeshAddMeshPlacement(unittest.TestCase):
    """Mesh.addMesh() adds the other mesh where it is placed"""

    def testOtherMeshPlaced(self):
        # The placement of the added mesh was ignored
        mesh = Mesh.createBox(1.0, 1.0, 1.0)
        other = Mesh.createBox(1.0, 1.0, 1.0)
        other.Placement = FreeCAD.Placement(FreeCAD.Vector(5, 0, 0), FreeCAD.Rotation())
        mesh.addMesh(other)
        self.assertEqual(mesh.CountFacets, 24)
        self.assertAlmostEqual(mesh.BoundBox.XMin, -0.5, 5)
        self.assertAlmostEqual(mesh.BoundBox.XMax, 5.5, 5)

    def testThisMeshPlaced(self):
        mesh = Mesh.createBox(1.0, 1.0, 1.0)
        mesh.Placement = FreeCAD.Placement(
            FreeCAD.Vector(10, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        )
        other = Mesh.createBox(1.0, 2.0, 1.0)
        mesh.addMesh(other)
        self.assertEqual(mesh.CountFacets, 24)
        # the added box keeps its global position and orientation
        points = [(round(p.x, 4), round(p.y, 4)) for p in mesh.Points]
        self.assertIn((-0.5, -1.0), points)
        self.assertIn((0.5, 1.0), points)
        self.assertIn((10.5, 0.5), points)

    def testSameMesh(self):
        # Adding a mesh to itself silently did nothing
        mesh = Mesh.createBox(1.0, 1.0, 1.0)
        mesh.addMesh(mesh)
        self.assertEqual(mesh.CountFacets, 24)
        self.assertAlmostEqual(mesh.Volume, 2.0, 5)


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


class MeshReadObjPolygons(unittest.TestCase):
    """Faces of an OBJ file may have any number of vertices"""

    def _read(self, face):
        # a regular hexagon of radius 1 in the XY plane
        lines = []
        for i in range(6):
            angle = math.radians(60 * i)
            lines.append("v {} {} 0".format(math.cos(angle), math.sin(angle)))
        lines.append("vt 0 0")
        lines.append("vn 0 0 1")
        lines.append(face)
        with tempfile.TemporaryDirectory() as tmpDir:
            fileName = os.path.join(tmpDir, "polygons.obj")
            with open(fileName, "w") as f:
                f.write("\n".join(lines) + "\n")
            return Mesh.Mesh(fileName)

    def _check(self, face, count, area):
        mesh = self._read(face)
        self.assertEqual(mesh.CountFacets, count, face)
        self.assertAlmostEqual(mesh.Area, area, places=5, msg=face)

    def testTriangleAndQuad(self):
        triangle = math.sqrt(3) / 4  # area of the triangle 1, 2, 3
        quad = math.sqrt(3) * 3 / 4  # area of the quad 1, 2, 3, 4
        self._check("f 1 2 3", 1, triangle)
        self._check("f 1/1 2/1 3/1", 1, triangle)
        self._check("f 1//1 2//1 3//1", 1, triangle)
        self._check("f 1/1/1 2/1/1 3/1/1", 1, triangle)
        self._check("f -6 -5 -4", 1, triangle)
        self._check("f 1 2 3 4", 2, quad)
        self._check("f 1/1/1 2/1/1 3/1/1 4/1/1", 2, quad)

    def testPolygons(self):
        # Faces with more than four vertices were dropped or read with wrong
        # vertices, e.g. the hexagon "f 1 2 3 4 5 6" as the triangle 1, 3, 5
        hexagon = math.sqrt(3) * 3 / 2
        self._check("f 1 2 3 4 5", 3, hexagon - math.sqrt(3) / 4)
        self._check("f 1 2 3 4 5 6", 4, hexagon)
        self._check("f 1/1 2/1 3/1 4/1 5/1 6/1", 4, hexagon)
        self._check("f 1//1 2//1 3//1 4//1 5//1 6//1", 4, hexagon)
        self._check("f 1/1/1 2/1/1 3/1/1 4/1/1 5/1/1 6/1/1", 4, hexagon)

    def testDegeneratedFace(self):
        # a face with less than three vertices is ignored
        self._check("f 1 2\nf 1 2 3", 1, math.sqrt(3) / 4)

    def testTrailingComment(self):
        self._check("f 1 2 3 4 5 6 # hexagon", 4, math.sqrt(3) * 3 / 2)


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


class MeshExportObjNormals(unittest.TestCase):
    """The normals of an OBJ file must match its vertices for a placed mesh"""

    def testRotatedMesh(self):
        mesh = Mesh.createBox(1.0, 2.0, 3.0)
        mesh.Placement = Base.Placement(Base.Vector(10, 0, 0), Base.Rotation(Base.Vector(1, 1, 0), 90))
        with tempfile.TemporaryDirectory() as tmpDir:
            fileName = os.path.join(tmpDir, "rotated_box.obj")
            mesh.write(fileName)
            with open(fileName) as f:
                lines = f.read().splitlines()

        def values(prefix):
            return [[float(v) for v in line.split()[1:4]] for line in lines if line.startswith(prefix)]

        vertices = [Base.Vector(*v) for v in values("v ")]
        normals = [Base.Vector(*v) for v in values("vn ")]
        faces = [line.split()[1:] for line in lines if line.startswith("f ")]
        self.assertEqual(len(faces), mesh.CountFacets)
        for face in faces:
            points = [vertices[int(item.split("/")[0]) - 1] for item in face]
            normal = normals[int(face[0].split("/")[2]) - 1]
            expected = (points[1] - points[0]).cross(points[2] - points[0])
            expected.normalize()
            self.assertAlmostEqual((normal - expected).Length, 0.0, places=4)


class MeshExportPlacement(unittest.TestCase):
    """The IDTF and MGL writers must apply the placement of the mesh like the other formats"""

    def setUp(self):
        self.mesh = Mesh.createBox(1.0, 2.0, 3.0)
        self.mesh.Placement = Base.Placement(
            Base.Vector(10, 20, 30), Base.Rotation(Base.Vector(0, 0, 1), 90)
        )
        # centred 1 x 2 x 3 box turned by 90 degrees around Z, then moved
        self.expected = Base.BoundBox(9, 19.5, 28.5, 11, 20.5, 31.5)

    def _read(self, ext):
        with tempfile.TemporaryDirectory() as tmpDir:
            fileName = os.path.join(tmpDir, "placed_box." + ext)
            self.mesh.write(fileName)
            with open(fileName) as f:
                return f.read()

    def _checkPoints(self, points):
        self.assertEqual(len(points), self.mesh.CountPoints)
        box = Base.BoundBox()
        for p in points:
            box.add(p)
        for a, b in zip(
            (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax),
            (
                self.expected.XMin,
                self.expected.YMin,
                self.expected.ZMin,
                self.expected.XMax,
                self.expected.YMax,
                self.expected.ZMax,
            ),
        ):
            self.assertAlmostEqual(a, b, places=2)

    def testIDTF(self):
        text = self._read("idtf")
        lines = [line.strip() for line in text.splitlines()]

        def block(name):
            start = lines.index(name + " {") + 1
            end = lines.index("}", start)
            return [[float(v) for v in line.split()] for line in lines[start:end]]

        self._checkPoints([Base.Vector(*v) for v in block("MODEL_POSITION_LIST")])

    def testIDTFNormals(self):
        # A quarter turn only swaps the side normals of a box, so turn it by 30 degrees: the
        # normals must follow the rotation, i.e. no side normal stays along the X axis.
        self.mesh.Placement = Base.Placement(
            Base.Vector(10, 20, 30), Base.Rotation(Base.Vector(0, 0, 1), 30)
        )
        lines = [line.strip() for line in self._read("idtf").splitlines()]
        start = lines.index("MODEL_NORMAL_LIST {") + 1
        end = lines.index("}", start)
        normals = [Base.Vector(*[float(v) for v in line.split()]) for line in lines[start:end]]
        turned = Base.Vector(math.cos(math.radians(30)), math.sin(math.radians(30)), 0)
        self.assertTrue(any((n - turned).Length < 1e-4 for n in normals))
        self.assertFalse(any((n - Base.Vector(1, 0, 0)).Length < 1e-4 for n in normals))

    def testMGL(self):
        lists = {}
        for line in self._read("mgl").splitlines():
            items = line.split()
            if len(items) > 2 and items[0] == "list" and items[1] in ("xt", "yt", "zt"):
                lists[items[1]] = [float(v) for v in items[2:]]
        points = [Base.Vector(*v) for v in zip(lists["xt"], lists["yt"], lists["zt"])]
        self._checkPoints(points)


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

    def testMeshAfterRecompute(self):
        """Mesh returns the result of the last recompute once it was read from Python"""
        # Features replace their mesh object on recompute; the cached Python wrapper kept
        # referring to the first result.
        box1 = self.doc.addObject("Mesh::Feature", "Box1")
        box1.Mesh = Mesh.createBox(1.0, 1.0, 1.0)
        box2 = self.doc.addObject("Mesh::Feature", "Box2")
        mesh = Mesh.createBox(1.0, 1.0, 1.0)
        mesh.translate(0.5, 0.5, 0.5)
        box2.Mesh = mesh
        op = self.doc.addObject("Mesh::SetOperations", "Operation")
        op.Source1 = box1
        op.Source2 = box2
        op.OperationType = "union"
        self.doc.recompute()
        first = op.Mesh
        self.assertAlmostEqual(first.Volume, 1.875, 4)
        op.OperationType = "intersection"
        self.doc.recompute()
        self.assertAlmostEqual(op.Mesh.Volume, 0.125, 4)
        op.OperationType = "difference"
        self.doc.recompute()
        self.assertAlmostEqual(op.Mesh.Volume, 0.875, 4)
        # a reference taken before keeps the mesh it referred to
        self.assertAlmostEqual(first.Volume, 1.875, 4)

        # assigning a list of points also replaces the mesh object
        self.assertEqual(box1.Mesh.CountFacets, 12)
        box1.Mesh = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
        self.assertEqual(box1.Mesh.CountFacets, 1)

    def testNormalListKeepsNaN(self):
        """Normals given as list, tuple or Vector accept NaN alike (bulk data, as on restore)"""
        # A list or tuple was converted through a temporary App::PropertyVector, which
        # rejects NaN as "property ?", while a single Vector was accepted.
        mesh = self.doc.addObject("Mesh::Feature", "Normals")
        mesh.addProperty("Mesh::PropertyNormalList", "Normal")
        nan = float("nan")
        mesh.Normal = [FreeCAD.Vector(0, 0, 1), FreeCAD.Vector(nan, nan, nan), (nan, 0, 1)]
        self.assertEqual(len(mesh.Normal), 3)
        self.assertTrue(math.isnan(mesh.Normal[1].x))
        self.assertTrue(math.isnan(mesh.Normal[2].x))
        mesh.Normal = (nan, 0, 1)
        self.assertTrue(math.isnan(mesh.Normal[0].x))
        mesh.Normal = FreeCAD.Vector(nan, 0, 1)
        self.assertTrue(math.isnan(mesh.Normal[0].x))
        mesh.Normal = [(1, 0, 0)]
        self.assertEqual(mesh.Normal, [FreeCAD.Vector(1, 0, 0)])
        with self.assertRaises(TypeError):
            mesh.Normal = ["a"]
        with self.assertRaises(TypeError):
            mesh.Normal = [("a", 0, 1)]

    def testDocumentOpenAtExit(self):
        """FreeCADCmd exits cleanly with a document open whose mesh was read from Python"""
        # The documents still open at exit are closed without the GIL held, and releasing
        # the cached Python wrapper of the mesh property crashed with an access violation.
        import shutil
        import subprocess

        exe = None
        bindir = os.path.join(FreeCAD.getHomePath(), "bin")
        for name in ("FreeCADCmd.exe", "FreeCADCmd", "freecadcmd"):
            if os.path.isfile(os.path.join(bindir, name)):
                exe = os.path.join(bindir, name)
                break
        if not exe:
            self.skipTest("FreeCADCmd executable not found")
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        script = os.path.join(tmpdir, "mesh_open_at_exit.py")
        with open(script, "w") as f:
            f.write(
                "import FreeCAD, Mesh\n"
                "doc = FreeCAD.newDocument('OpenAtExit')\n"
                "feature = doc.addObject('Mesh::Feature', 'Box')\n"
                "feature.Mesh = Mesh.createBox(1.0, 1.0, 1.0)\n"
                "mesh = feature.Mesh\n"
                "assert mesh.CountFacets == 12\n"
                "del mesh\n"
            )
        cmd = [exe, "--user-cfg", os.path.join(tmpdir, "user.cfg"), script]
        result = subprocess.run(cmd, cwd=tmpdir, capture_output=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace")[-2000:])
