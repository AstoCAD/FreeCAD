# SPDX-License-Identifier: LGPL-2.1-or-later
from SketcherTests.TestConstraintPreselectionGui import SketcherGuiTestCases
from SketcherTests.TestDistanceLabelExtensionGui import TestDistanceLabelExtensionGui
from SketcherTests.TestConstraintCommandsGui import TestConstraintCommandsGui
from SketcherTests.TestBSplineEndpointTransactionGui import TestBSplineEndpointTransactionGui
from SketcherTests.TestToggleActiveSelectionTransactionGui import (
    TestToggleActiveSelectionTransactionGui,
)
from SketcherTests.TestCoincidentCommandGui import TestCoincidentCommandGui
from SketcherTests.TestOnViewParameterGui import TestOnViewParameterGui
from SketcherTests.TestPlacementUpdate import TestSketchPlacementUpdate
from SketcherTests.TestExternalFacePreselection import TestExternalFacePreselection
from SketcherTests.TestSketchGroupsGui import TestSketchGroupsGui
from SketcherTests.TestSketchTransformExpressionsGui import TestSketchTransformExpressionsGui
from SketcherTests.TestSketchEndpointExpressionsGui import TestSketchEndpointExpressionsGui
from SketcherTests.TestSketchAnnotationsGui import TestSketchAnnotationsGui
from SketcherTests.TestSketchLayersGui import TestSketchLayersGui
from SketcherTests.TestSketchBlocksGui import TestSketchBlocksGui
from SketcherTests.TestViewSectionGui import TestViewSectionGui
from SketcherTests.TestSketchRubberbandGui import TestSketchRubberbandGui
from SketcherTests.TestSketchDatumNavigationGui import TestSketchDatumNavigationGui
from SketcherTests.TestSketchReorientGui import TestSketchReorientGui
from SketcherTests.TestAssociatedConstraintPointFilterGui import (
    TestAssociatedConstraintPointFilter28516Gui,
)

# Use the module so that code checkers don't complain (flake8)
(
    True
    if SketcherGuiTestCases
    and TestDistanceLabelExtensionGui
    and TestConstraintCommandsGui
    and TestBSplineEndpointTransactionGui
    and TestToggleActiveSelectionTransactionGui
    and TestCoincidentCommandGui
    and TestSketchPlacementUpdate
    and TestOnViewParameterGui
    and TestExternalFacePreselection
    and TestSketchGroupsGui
    and TestSketchTransformExpressionsGui
    and TestSketchEndpointExpressionsGui
    and TestSketchAnnotationsGui
    and TestSketchLayersGui
    and TestSketchBlocksGui
    and TestViewSectionGui
    and TestSketchRubberbandGui
    and TestSketchDatumNavigationGui
    and TestSketchReorientGui
    and TestAssociatedConstraintPointFilter28516Gui
    else False
)
