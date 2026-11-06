# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
#   Copyright (c) 2021 Emmanuel O'Brien                                   *
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

# Broken-out test modules
from SketcherTests.TestSketcherSolver import TestSketcherSolver
from SketcherTests.TestSketchFillet import TestSketchFillet
from SketcherTests.TestSketchExpression import TestSketchExpression
from SketcherTests.TestSketchUserParameters import TestSketchUserParameters
from SketcherTests.TestSketchValidateCoincidents import TestSketchValidateCoincidents
from SketcherTests.TestSketchCarbonCopyReverseMapping import (
    TestSketchCarbonCopyReverseMapping,
    TestSketchCarbonCopyReverseMappingPlaced,
)
from SketcherTests.TestPerpendicularArcProjection import TestPerpendicularArcProjection
from SketcherTests.TestPerpendicularPointPointLine import TestPerpendicularPointPointLine
from SketcherTests.TestDrivenAngleConstraints import TestDrivenAngleConstraints
from SketcherTests.TestDrivenConstraintEvaluation import TestDrivenConstraintEvaluation
from SketcherTests.TestSketchJoinCurves import TestSketchJoinCurves
from SketcherTests.TestSketchInvalidConstraintList import TestSketchInvalidConstraintList
from SketcherTests.TestSketchInternalFaces import TestSketchInternalFaces
from SketcherTests.TestSketcherEllipse import TestSketcherEllipse
from SketcherTests.TestSketchLayers import TestSketchLayers
from SketcherTests.TestSketchAnnotations import TestSketchAnnotations
from SketcherTests.TestSketchGroups import TestSketchGroups
from SketcherTests.TestSketchExternalContext import TestSketchExternalContext
from SketcherTests.TestConstraintIntegerRange import (
    TestConstraintElementIntegerRange,
    TestConstraintElementAttributeRange,
)
from SketcherTests.TestConstraintScalarDispatch import (
    TestConstraintScalarIntegerValues,
    TestConstraintScalarDispatchCompatibility,
)
from SketcherTests.TestConstraintPythonSerialization import (
    TestConstraintValuePythonRoundTrip,
    TestConstraintPythonRoundTripCompatibility,
    TestConstraintPythonThirdElementRoundTrip,
    TestReversedArcPythonRoundTrip,
)
from SketcherTests.TestSketchBlocks import TestSketchBlocks
from SketcherTests.TestRemoveAxesAlignment import TestRemoveAxesAlignment
from SketcherTests.TestSketchNormal import TestSketchNormal
from SketcherTests.TestSketchSplitTrimConstraints import TestSketchSplitTrimConstraints
from SketcherTests.TestSketchSymmetricCopy import TestSketchSymmetricCopy
from SketcherTests.TestSketchMoveUndo import TestSketchMoveUndo

# Path and PartDesign tests use these functions that used to live here
# but moved to SketcherTests/TestSketcherSolver.py
from SketcherTests.TestSketcherSolver import CreateCircleSketch
from SketcherTests.TestSketcherSolver import CreateRectangleSketch
from SketcherTests.TestSketcherSolver import CreateSlotPlateSet

# Export test cases for unittest discovery and the legacy sketch helpers.
__all__ = [
    "TestSketcherSolver",
    "TestSketchFillet",
    "TestSketchExpression",
    "TestSketchUserParameters",
    "TestSketchValidateCoincidents",
    "TestSketchCarbonCopyReverseMapping",
    "TestSketchCarbonCopyReverseMappingPlaced",
    "TestPerpendicularArcProjection",
    "TestPerpendicularPointPointLine",
    "TestDrivenAngleConstraints",
    "TestDrivenConstraintEvaluation",
    "TestSketchJoinCurves",
    "TestSketchInvalidConstraintList",
    "TestSketchInternalFaces",
    "TestSketcherEllipse",
    "TestSketchGroups",
    "TestConstraintElementIntegerRange",
    "TestConstraintScalarIntegerValues",
    "TestConstraintScalarDispatchCompatibility",
    "TestConstraintValuePythonRoundTrip",
    "TestConstraintPythonRoundTripCompatibility",
    "TestConstraintPythonThirdElementRoundTrip",
    "TestReversedArcPythonRoundTrip",
    "TestSketchAnnotations",
    "TestSketchLayers",
    "TestSketchBlocks",
    "TestRemoveAxesAlignment",
    "TestSketchNormal",
    "TestSketchSplitTrimConstraints",
    "TestSketchSymmetricCopy",
    "TestSketchMoveUndo",
    "CreateCircleSketch",
    "CreateRectangleSketch",
    "CreateSlotPlateSet",
]
