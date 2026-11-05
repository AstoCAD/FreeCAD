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
