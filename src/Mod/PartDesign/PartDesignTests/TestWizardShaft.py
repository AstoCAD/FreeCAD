# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************

"""App-level tests of the shaft wizard calculation code (no task panel)."""

import importlib.util
import unittest

import FreeCAD


def _available(name):
    try:
        return importlib.util.find_spec(name) is not None
    except ImportError:
        return False


HAVE_WIZARD = _available("PartDesign.WizardShaft") and _available("numpy") and _available("Fem")


class _ShaftFeatureStub:
    """Stands in for ShaftFeature, which needs a 3D view"""

    def __init__(self, feature):
        self.feature = feature

    def addSegment(self, length, diameter, innerdiameter):
        pass


@unittest.skipUnless(HAVE_WIZARD, "WizardShaft, numpy or Fem not available")
class TestWizardShaft(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestWizardShaft")

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def makeShaft(self):
        from PartDesign.WizardShaft import Shaft

        shaft = Shaft.Shaft.__new__(Shaft.Shaft)
        shaft.segments = []
        shaft.feature = _ShaftFeatureStub(self.Doc.addObject("Part::Box", "ShaftBody"))
        return shaft

    def testAddSegmentAfterFixedLastSegment(self):
        """A fixed end constraint loses its face when a segment is appended behind it"""
        shaft = self.makeShaft()
        shaft.addSegment(10.0, 5.0, 0.0)
        shaft.addSegment(10.0, 5.0, 0.0)
        fixed = self.Doc.addObject("Fem::ConstraintFixed", "ShaftConstraintFixed")
        fixed.References = [(shaft.feature.feature, "Face5")]
        shaft.segments[1].constraintType = "Fixed"
        shaft.segments[1].constraint = fixed

        shaft.addSegment(10.0, 5.0, 0.0)

        self.assertEqual(len(shaft.segments), 3)
        self.assertEqual(fixed.References, [])
