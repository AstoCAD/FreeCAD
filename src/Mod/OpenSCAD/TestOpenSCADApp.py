# SPDX-License-Identifier: LGPL-2.1-or-later
# ***************************************************************************
# *   Copyright (c) 2021 Chris Hennes <chennes@pioneerlibrarysystem.org>    *
# *                                                                         *
# *   This file is part of the FreeCAD CAx development system.              *
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
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

# Unit test for the OpenSCAD module
from OpenSCADTest.app.test_importCSG import TestImportCSG as OpenSCADTestImportCSG
from OpenSCADTest.app.test_importCSGIntersection import TestCsgIntersectionArity as OpenSCADTestCsgIntersectionArity
from OpenSCADTest.app.test_importCSGIntersection import TestCsgNestedUncomputedChildren as OpenSCADTestCsgNestedUncomputedChildren
from OpenSCADTest.app.test_exportCSG import TestExportCSGBooleanPlacement as OpenSCADTestExportCSGBooleanPlacement
from OpenSCADTest.app.test_importCSGFrustum import TestCsgFrustum as OpenSCADTestCsgFrustum
from OpenSCADTest.app.test_importCSGPolygon import TestCsgPolygonPaths as OpenSCADTestCsgPolygonPaths
from OpenSCADTest.app.test_importCSGResize import TestCsgResize as OpenSCADTestCsgResize
from OpenSCADTest.app.test_exportCSGPrimitives import TestExportCSGPrimitives as OpenSCADTestExportCSGPrimitives
from OpenSCADTest.app.test_importCSGCircle import TestCsgCircle as OpenSCADTestCsgCircle
from OpenSCADTest.app.test_importCSGRotateExtrude import TestCsgRotateExtrudePrism as OpenSCADTestCsgRotateExtrudePrism
from OpenSCADTest.app.test_importCSGPolyhedron import TestCsgPolyhedron as OpenSCADTestCsgPolyhedron
from OpenSCADTest.app.test_exportCSGShapes import TestExportCSGShapes as OpenSCADTestExportCSGShapes

# dummy usage to get flake8 and lgtm quiet
False if OpenSCADTestImportCSG.__name__ else True
False if OpenSCADTestCsgIntersectionArity.__name__ else True
False if OpenSCADTestCsgNestedUncomputedChildren.__name__ else True
False if OpenSCADTestExportCSGBooleanPlacement.__name__ else True
False if OpenSCADTestCsgFrustum.__name__ else True
False if OpenSCADTestCsgPolygonPaths.__name__ else True
False if OpenSCADTestCsgResize.__name__ else True
False if OpenSCADTestExportCSGPrimitives.__name__ else True
False if OpenSCADTestCsgCircle.__name__ else True
False if OpenSCADTestCsgRotateExtrudePrism.__name__ else True
False if OpenSCADTestCsgPolyhedron.__name__ else True
False if OpenSCADTestExportCSGShapes.__name__ else True
