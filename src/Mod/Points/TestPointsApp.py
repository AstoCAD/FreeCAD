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
