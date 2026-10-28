# SPDX-License-Identifier: LGPL-2.1-or-later

# **************************************************************************
#   Copyright (c) 2022 WandererFan <wandererfan@gmail.com>                *
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

#these tests require QApplication in order to process events while waiting for 
#threads to complete
from TDTest.DrawViewSectionTest import DrawViewSectionTest  # noqa: F401
from TDTest.DrawComplexSectionPlacementGuiTest import TestComplexSectionPlacementGui  # noqa: F401
from TDTest.DrawViewSectionSelectionTest import DrawViewSectionSelectionTest  # noqa: F401
from TDTest.DrawViewPartTest import DrawViewPartTest  # noqa: F401
from TDTest.DrawViewPositionTest import DrawViewPositionTest  # noqa: F401
from TDTest.DrawViewDetailTest import DrawViewDetailTest  # noqa: F401
from TDTest.DrawViewDimensionTest import DrawViewDimensionTest  # noqa: F401
from TDTest.TestAreaLeaderRedrawGui import TestAreaLeaderRedrawGui  # noqa: F401
from TDTest.TestBSplineAngleDimensionGui import TestBSplineAngleDimensionGui  # noqa: F401
from TDTest.DrawDimensionApiTest import DrawDimensionApiTest  # noqa: F401
from TDTest.DrawDimensionShapeNameTest import DrawDimensionShapeNameTest  # noqa: F401
from TDTest.DrawDimensionEdgeVertexTest import DrawDimensionEdgeVertexTest  # noqa: F401
from TDTest.DrawCreationDocumentTest import DrawCreationDocumentTest  # noqa: F401
from TDTest.DrawSpreadsheetLabelXmlTest import DrawSpreadsheetLabelXmlTest  # noqa: F401
from TDTest.DrawBoltCircleTest import DrawBoltCircleTest  # noqa: F401
from TDTest.DrawAxoLengthTransactionGuiTest import TestAxoLengthTransactionGui  # noqa: F401
from TDTest.TestExtendShortenEmptySelectionGui import TestExtendShortenTransactionGui  # noqa: F401
from TDTest.TestDxfExportPendingTransactionGui import TestDxfExportPendingTransactionGui  # noqa: F401
from TDTest.DrawMoveViewPageChooserGuiTest import DrawMoveViewPageChooserGuiTest  # noqa: F401
from TDTest.DrawTemplateFieldsDismissalGuiTest import DrawTemplateFieldsDismissalGuiTest  # noqa: F401
from TDTest.TestTemplateFieldsMissingTemplateGui import TestTemplateFieldsMissingTemplateGui  # noqa: F401
from TDTest.DrawPositionSectionSelectionGuiTest import TestPositionSectionSelectionGui  # noqa: F401
from TDTest.DrawModelSelectionGuiTest import TestTechDrawModelSelectionGui  # noqa: F401
from TDTest.DrawCosmeticCircleGuiTest import (  # noqa: F401
    TestCosmeticCircleSelection, TestCosmeticCircleCompatibility,
)
from TDTest.DrawDraftViewDocumentTest import DrawDraftViewDocumentTest  # noqa: F401
from TDTest.DrawArchViewDocumentTest import DrawArchViewDocumentTest  # noqa: F401
from TDTest.DrawImportFilenameTest import DrawImportFilenameTest  # noqa: F401
from TDTest.DrawPagePdfFilenameTest import DrawPagePdfFilenameTest  # noqa: F401
from TDTest.DrawSvgzSymbolTest import DrawSvgzSymbolTest  # noqa: F401
from TDTest.DrawViewDimensionTreeTest import DrawViewDimensionTreeTest  # noqa: F401
from TDTest.DrawViewCaptionGuiTest import DrawViewCaptionGuiTest  # noqa: F401
from TDTest.DrawViewSelectionTeardownGuiTest import DrawViewSelectionTeardownGuiTest  # noqa: F401
from TDTest.TechDrawTaskTest import TechDrawTaskTest  # noqa: F401


from TDTest.SketchAnnotationsGuiTest import SketchAnnotationsGuiTest  # noqa: F401
