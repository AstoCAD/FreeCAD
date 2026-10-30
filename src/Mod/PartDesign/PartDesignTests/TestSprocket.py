# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
# *                                                                         *
# *   This library is free software; you can redistribute it and/or         *
# *   modify it under the terms of the GNU Library General Public           *
# *   License as published by the Free Software Foundation; either          *
# *   version 2 of the License, or (at your option) any later version.      *
# *                                                                         *
# *   This library  is distributed in the hope that it will be useful,      *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this library; see the file COPYING.LIB. If not,    *
# *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
# *   Suite 330, Boston, MA  02111-1307, USA                                *
# *                                                                         *
# ***************************************************************************

import unittest

from SprocketFeature import Sprocket


class TestSprocket(unittest.TestCase):
    def _reference(self, name):
        for row in Sprocket.SprocketReferenceRollerTable.values():
            if row[3] == name:
                return row
        self.fail("Sprocket reference '{}' not found".format(name))

    def testMotorcycle420RollerDiameter(self):
        # https://github.com/FreeCAD/FreeCAD/issues/33908
        # 420 motorcycle chain has a 7.77 mm roller, not the 7.94 mm (0.3125 in)
        # roller of ANSI 40.
        pitch, roller, _, _ = self._reference("Motorcycle 420")
        self.assertAlmostEqual(pitch * 25.4, 12.7, places=6)
        self.assertAlmostEqual(roller * 25.4, 7.77, places=6)
