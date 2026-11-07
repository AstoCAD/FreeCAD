# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#                                                                         *
#   This file is part of FreeCAD.                                         *
#                                                                         *
#   FreeCAD is free software: you can redistribute it and/or modify it    *
#   under the terms of the GNU Lesser General Public License as           *
#   published by the Free Software Foundation, either version 2.1 of the  *
#   License, or (at your option) any later version.                       *
#                                                                         *
#   FreeCAD is distributed in the hope that it will be useful, but        *
#   WITHOUT ANY WARRANTY; without even the implied warranty of            *
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
#   Lesser General Public License for more details.                       *
#                                                                         *
#   You should have received a copy of the GNU Lesser General Public      *
#   License along with FreeCAD. If not, see                               *
#   <https://www.gnu.org/licenses/>.                                      *
#                                                                         *
# **************************************************************************

import math
import os
import tempfile
import unittest

import FreeCAD
import Points


class PointsLoadTest(unittest.TestCase):
    def setUp(self):
        self.fileNames = []

    def tearDown(self):
        for fileName in self.fileNames:
            if os.path.exists(fileName):
                os.remove(fileName)

    def writeFile(self, suffix, content):
        fd, fileName = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        self.fileNames.append(fileName)
        return fileName

    def testConstructFromAsciiFile(self):
        fileName = self.writeFile(".asc", "0 0 0\n1 2 3\n")
        self.assertEqual(Points.Points(fileName).CountPoints, 2)

    def testConstructFromUnsupportedFile(self):
        """Errors while loading must become Python exceptions"""
        fileName = self.writeFile(".unsupported", "0 0 0\n")
        with self.assertRaises(RuntimeError):
            Points.Points(fileName)

    def testConstructFromMissingFile(self):
        fileName = os.path.join(tempfile.gettempdir(), "TestPointsAppMissingFile.asc")
        with self.assertRaises(OSError):
            Points.Points(fileName)

    def writeBinaryFile(self, suffix, content):
        fd, fileName = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        self.fileNames.append(fileName)
        return fileName

    def testInsertPcdWithBadHeader(self):
        """A non-numeric SIZE entry must raise a Python exception"""
        # boost::bad_lexical_cast escaped from Points.insert() into the interpreter and
        # terminated the application.
        header = (
            "VERSION 0.7\nFIELDS x y z\nSIZE 4 x 4\nTYPE F F F\nCOUNT 1 1 1\n"
            "WIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA ascii\n0 0 0\n"
        )
        fileName = self.writeBinaryFile(".pcd", header.encode("ascii"))
        doc = FreeCAD.newDocument("TestPointsAppPcd")
        try:
            with self.assertRaises(RuntimeError):
                Points.insert(fileName, doc.Name)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def testCompressedPcdWithoutData(self):
        """A binary_compressed PCD with an empty compressed block must raise"""
        # The LZF decoder read the first control byte of an empty input buffer
        # (access violation).
        header = (
            "VERSION 0.7\nFIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 1 1 1\n"
            "WIDTH 1\nHEIGHT 1\nPOINTS 1\nDATA binary_compressed\n"
        )
        fileName = self.writeBinaryFile(".pcd", header.encode("ascii") + bytes(8))
        doc = FreeCAD.newDocument("TestPointsAppPcd")
        try:
            with self.assertRaises(Exception) as cm:
                Points.insert(fileName, doc.Name)
            self.assertNotIn("Access violation", str(cm.exception))
        finally:
            FreeCAD.closeDocument(doc.Name)


class PointsNormalTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestPointsAppNormal")
        self.fileNames = []

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        for fileName in self.fileNames:
            if os.path.exists(fileName):
                os.remove(fileName)

    def testNormalListKeepsNaN(self):
        """The normals of a structured cloud's invalid points are NaN and can be set back"""
        # A list or tuple was converted through a temporary App::PropertyVector, which
        # rejects NaN as "property ?", while a single Vector was accepted.
        fd, fileName = tempfile.mkstemp(suffix=".pcd")
        with os.fdopen(fd, "w") as f:
            f.write(
                "VERSION 0.7\nFIELDS x y z normal_x normal_y normal_z\nSIZE 4 4 4 4 4 4\n"
                "TYPE F F F F F F\nCOUNT 1 1 1 1 1 1\nWIDTH 3\nHEIGHT 1\nPOINTS 3\n"
                "DATA ascii\n0 0 0 0 0 1\nnan nan nan nan nan nan\n0 1 0 0 0 1\n"
            )
        self.fileNames.append(fileName)
        Points.insert(fileName, self.doc.Name)
        cloud = self.doc.Objects[-1]
        normals = cloud.Normal
        self.assertEqual(len(normals), 3)
        self.assertTrue(math.isnan(normals[1].x))
        cloud.Normal = normals
        self.assertEqual(len(cloud.Normal), 3)
        self.assertTrue(math.isnan(cloud.Normal[1].z))

        nan = float("nan")
        cloud.Normal = [(0, 0, 1), (nan, nan, nan), FreeCAD.Vector(0, 0, 1)]
        self.assertTrue(math.isnan(cloud.Normal[1].y))
        cloud.Normal = (nan, 0, 1)
        self.assertTrue(math.isnan(cloud.Normal[0].x))
        with self.assertRaises(TypeError):
            cloud.Normal = ["a"]
        with self.assertRaises(TypeError):
            cloud.Normal = [("a", 0, 1)]


class PointsSegmentTest(unittest.TestCase):
    def testFromSegmentHugeIndex(self):
        """An index beyond the C long range is skipped like other invalid indices"""
        # It returned a result with an OverflowError still set (SystemError).
        kernel = Points.Points()
        kernel.addPoints([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(1, 0, 0)])
        segment = kernel.fromSegment([1, 2**40, -(2**70), 5, -1, 0])
        self.assertEqual(segment.CountPoints, 2)
        self.assertEqual(segment.Points[0], FreeCAD.Vector(1, 0, 0))
        with self.assertRaises(TypeError):
            kernel.fromSegment([0, "x"])


class PointsWriteTest(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("TestPointsAppWrite")
        self.fileNames = []

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)
        for fileName in self.fileNames:
            if os.path.exists(fileName):
                os.remove(fileName)

    def tempFile(self, suffix):
        fd, fileName = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        self.fileNames.append(fileName)
        return fileName

    def readPoints(self, fileName):
        with open(fileName) as f:
            rows = [line.split() for line in f if not line.startswith("#")]
        return [FreeCAD.Vector(*map(float, row)) for row in rows if row]

    def testWriteTransformedPoints(self):
        """write() wrote the untransformed points, which read() then took as transformed ones"""
        cloud = self.doc.addObject("Points::Feature", "Cloud")
        cloud.Points = Points.Points([FreeCAD.Vector(1, 2, 3), FreeCAD.Vector(4, 5, 6)])
        cloud.Placement = FreeCAD.Placement(
            FreeCAD.Vector(10, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 90)
        )
        kernel = cloud.Points.copy()
        expected = kernel.Points

        fileName = self.tempFile(".asc")
        kernel.write(fileName)
        self.assertEqual(len(self.readPoints(fileName)), 2)
        for written, point in zip(self.readPoints(fileName), expected):
            self.assertTrue(written.isEqual(point, 1e-5), f"{written} != {point}")

        # reading the file back gives the same points
        kernel.read(fileName)
        for read, point in zip(kernel.Points, expected):
            self.assertTrue(read.isEqual(point, 1e-5), f"{read} != {point}")

        # and the same as exporting the feature
        exported = self.tempFile(".asc")
        Points.export([cloud], exported)
        for written, point in zip(self.readPoints(exported), expected):
            self.assertTrue(written.isEqual(point, 1e-5), f"{written} != {point}")

    def testExportInContainer(self):
        """Export writes the points with the global placement, once"""
        part = self.doc.addObject("App::Part", "Part")
        part.Placement.Base = FreeCAD.Vector(0, 0, 100)
        cloud = self.doc.addObject("Points::Feature", "Cloud")
        cloud.Points = Points.Points([FreeCAD.Vector(1, 2, 3)])
        part.addObject(cloud)
        cloud.Placement.Base = FreeCAD.Vector(10, 0, 0)
        exported = self.tempFile(".asc")
        Points.export([cloud], exported)
        written = self.readPoints(exported)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].isEqual(FreeCAD.Vector(11, 2, 103), 1e-5), str(written[0]))
