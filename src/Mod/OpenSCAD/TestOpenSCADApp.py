# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2021 Chris Hennes
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

# Unit test for the OpenSCAD module
from OpenSCADTest.app.test_importCSG import TestImportCSG as OpenSCADTestImportCSG
from OpenSCADTest.app.test_importCSGIntersection import TestCsgIntersectionArity as OpenSCADTestCsgIntersectionArity
from OpenSCADTest.app.test_importCSGIntersection import TestCsgNestedUncomputedChildren as OpenSCADTestCsgNestedUncomputedChildren
from OpenSCADTest.app.test_exportCSG import TestExportCSGBooleanPlacement as OpenSCADTestExportCSGBooleanPlacement
from OpenSCADTest.app.test_importCSGFrustum import TestCsgFrustum as OpenSCADTestCsgFrustum
from OpenSCADTest.app.test_importCSGPolygon import TestCsgPolygonPaths as OpenSCADTestCsgPolygonPaths
from OpenSCADTest.app.test_importCSGResize import TestCsgResize as OpenSCADTestCsgResize
from OpenSCADTest.app.test_importCSGConsumedSources import TestCsgConsumedSources as OpenSCADTestCsgConsumedSources
from OpenSCADTest.app.test_exportCSGPrimitives import TestExportCSGPrimitives as OpenSCADTestExportCSGPrimitives
from OpenSCADTest.app.test_importCSGCircle import TestCsgCircle as OpenSCADTestCsgCircle
from OpenSCADTest.app.test_importCSGRotateExtrude import TestCsgRotateExtrudePrism as OpenSCADTestCsgRotateExtrudePrism

# dummy usage to get flake8 and lgtm quiet
False if OpenSCADTestImportCSG.__name__ else True
False if OpenSCADTestCsgIntersectionArity.__name__ else True
False if OpenSCADTestCsgNestedUncomputedChildren.__name__ else True
False if OpenSCADTestExportCSGBooleanPlacement.__name__ else True
False if OpenSCADTestCsgFrustum.__name__ else True
False if OpenSCADTestCsgPolygonPaths.__name__ else True
False if OpenSCADTestCsgResize.__name__ else True
False if OpenSCADTestCsgConsumedSources.__name__ else True
False if OpenSCADTestExportCSGPrimitives.__name__ else True
False if OpenSCADTestCsgCircle.__name__ else True
False if OpenSCADTestCsgRotateExtrudePrism.__name__ else True
