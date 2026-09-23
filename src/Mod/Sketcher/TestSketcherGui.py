# SPDX-License-Identifier: LGPL-2.1-or-later
from SketcherTests.TestConstraintPreselectionGui import SketcherGuiTestCases
from SketcherTests.TestConstraintCommandsGui import TestConstraintCommandsGui
from SketcherTests.TestOnViewParameterGui import TestOnViewParameterGui
from SketcherTests.TestPlacementUpdate import TestSketchPlacementUpdate
from SketcherTests.TestSolverUpdateGui import TestSolverUpdateGui
from SketcherTests.TestExternalFacePreselection import TestExternalFacePreselection
from SketcherTests.TestSketchGroupsGui import TestSketchGroupsGui
from SketcherTests.TestSketchAnnotationsGui import TestSketchAnnotationsGui
from SketcherTests.TestSketchLayersGui import TestSketchLayersGui
from SketcherTests.TestSketchBlocksGui import TestSketchBlocksGui

# Use the module so that code checkers don't complain (flake8)
(
    True
    if SketcherGuiTestCases
    and TestConstraintCommandsGui
    and TestSketchPlacementUpdate
    and TestSolverUpdateGui
    and TestOnViewParameterGui
    and TestExternalFacePreselection
    and TestSketchGroupsGui
    and TestSketchAnnotationsGui
    and TestSketchLayersGui
    and TestSketchBlocksGui
    else False
)
