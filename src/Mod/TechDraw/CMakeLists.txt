# SPDX-License-Identifier: LGPL-2.1-or-later

disable_occt8_deprecation_warnings()

add_definitions(-DMOD_TECHDRAW_HANDLE_FACES=1)

add_subdirectory(App)
if(BUILD_GUI)
    add_subdirectory(Gui)
endif(BUILD_GUI)

set(TechDraw_Scripts
    SketchAnnotations.py
    Init.py
    TestTechDrawApp.py
    TestTechDrawGui.py
)

if(BUILD_GUI)
    list (APPEND TechDraw_Scripts InitGui.py)
endif(BUILD_GUI)

set(TechDraw_ToolsScripts
    TechDrawTools/__init__.py
    TechDrawTools/CommandMoveView.py
    TechDrawTools/CommandShareView.py
    TechDrawTools/CommandAxoLengthDimension.py
    TechDrawTools/CommandPositionSectionView.py
    TechDrawTools/CommandFillTemplateFields.py
    TechDrawTools/CommandVertexCreations.py
    TechDrawTools/CommandHoleShaftFit.py
    TechDrawTools/TaskMoveView.py
    TechDrawTools/TaskShareView.py
    TechDrawTools/TaskFillTemplateFields.py
    TechDrawTools/TaskHoleShaftFit.py
    TechDrawTools/TaskAddOffsetVertex.py
    TechDrawTools/TDToolsUtil.py
    TechDrawTools/TDToolsMovers.py
)

set(TechDraw_ToolsGui
    Gui/TaskMoveView.ui
    Gui/TaskHoleShaftFit.ui
    Gui/TaskAddOffsetVertex.ui
    Gui/DlgPageChooser.ui
)

SET(TechDraw_PATFile
    PAT/FCPAT.pat
)

SET(TechDraw_CSVFile
    CSVdata/FillTemplateFields.csv
)

SET(TechDraw_LineGroupFile
    LineGroup/ANSI.Y14.2M.1992.ElementDef.csv
    LineGroup/ANSI.Y14.2M.1992.LineDef.csv
    LineGroup/ASME.Y14.2.2008.ElementDef.csv
    LineGroup/ASME.Y14.2.2008.LineDef.csv
    LineGroup/ISO.128.20.1996.ElementDef.csv
    LineGroup/ISO.128.20.1996.LineDef.csv
    LineGroup/LineGroup.csv
)

add_custom_target(TechDraw_Data ALL
SOURCES ${TechDraw_Scripts} ${TechDraw_PATFile} ${TechDraw_CSVFile} ${TechDraw_LineGroupFile} ${TechDraw_ToolsScripts} ${TechDraw_ToolsGui}
)

fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/Mod/TechDraw
    ${TechDraw_Scripts}
)

fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    ${TechDraw_PATFile})

fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    ${TechDraw_CSVFile})

fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    ${TechDraw_LineGroupFile})

INSTALL(
    FILES
        ${TechDraw_Scripts}
    DESTINATION
        Mod/TechDraw
)

INSTALL(
    DIRECTORY
        Templates
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.svg*"
)

INSTALL(
    DIRECTORY
        PAT
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.pat*"
)

INSTALL(
    DIRECTORY
        CSVdata
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.csv*"
)

INSTALL(
    DIRECTORY
        LineGroup
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.csv*"
)

INSTALL(
    DIRECTORY
        Patterns
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.svg*"
)

INSTALL(
    DIRECTORY
        Symbols
    DESTINATION
        ${CMAKE_INSTALL_DATADIR}/Mod/TechDraw
    FILES_MATCHING
        PATTERN "*.svg*"
)

if(BUILD_GUI)
fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/Mod/TechDraw
    ${TechDraw_ToolsScripts}
)

fc_target_copy_resource(TechDraw_Data
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_BINARY_DIR}/Mod/TechDraw/TechDrawTools
    ${TechDraw_ToolsGui}
)

INSTALL(
    FILES
        ${TechDraw_ToolsScripts}
    DESTINATION
        Mod/TechDraw/TechDrawTools
)

INSTALL(
    FILES
        ${TechDraw_ToolsGui}
    DESTINATION
        Mod/TechDraw/TechDrawTools/Gui
)
endif(BUILD_GUI)

#unit test files
SET(TDTest_SRCS
    TDTest/__init__.py
    TDTest/TestCosmeticEdgeLifetime.py
    TDTest/DrawCosmeticLifetimeTest.py
    TDTest/DrawCosmeticCircleRadiusTest.py
    TDTest/DrawEdgeWalkerNullEdgeTest.py
    TDTest/DrawNearestFractionTest.py
    TDTest/DrawViewSectionCycleTest.py
    TDTest/SketchAnnotationsTest.py
    TDTest/SketchAnnotationsGuiTest.py
    TDTest/DrawHatchTest.py
    TDTest/DrawDimensionApiTest.py
    TDTest/DrawDimensionShapeNameTest.py
    TDTest/DrawDimensionEdgeVertexTest.py
    TDTest/DrawCreationDocumentTest.py
    TDTest/DrawSpreadsheetLabelXmlTest.py
    TDTest/DrawBoltCircleTest.py
    TDTest/DrawAxoLengthTransactionGuiTest.py
    TDTest/TestExtendShortenEmptySelectionGui.py
    TDTest/TestViewLockNoViewSelectionGui.py
    TDTest/TestLineParallelEmptySelectionGui.py
    TDTest/TestTwoPointCircleEmptySelectionGui.py
    TDTest/TestHorizontalChainPendingGui.py
    TDTest/TestChainWarningsPendingGui.py
    TDTest/TestDimensionFormatPendingGui.py
    TDTest/TestDxfExportPendingTransactionGui.py
    TDTest/DrawMoveViewPageChooserGuiTest.py
    TDTest/DrawTemplateFieldsDismissalGuiTest.py
    TDTest/TestTemplateFieldsMissingTemplateGui.py
    TDTest/DrawPositionSectionSelectionGuiTest.py
    TDTest/DrawModelSelectionGuiTest.py
    TDTest/DrawCosmeticCircleGuiTest.py
    TDTest/DrawDraftViewDocumentTest.py
    TDTest/DrawArchViewDocumentTest.py
    TDTest/DrawImportFilenameTest.py
    TDTest/DrawPagePdfFilenameTest.py
    TDTest/DrawPageUnshownExportTest.py
    TDTest/HatchFaceLastUsedGuiTest.py
    TDTest/DrawSvgzSymbolTest.py
    TDTest/DrawPageSketchTest.py
    TDTest/DrawProjectionGroupTest.py
    TDTest/DrawViewAnnotationTest.py
    TDTest/DrawViewImageTest.py
    TDTest/DrawViewSymbolTest.py
    TDTest/DrawViewDimensionTest.py
    TDTest/TestAreaLeaderRedrawGui.py
    TDTest/TestBSplineAngleDimensionGui.py
    TDTest/DrawViewDimensionTreeTest.py
    TDTest/DrawViewCaptionGuiTest.py
    TDTest/DrawPageDocumentWindowMenuGuiTest.py
    TDTest/DrawViewAnnotationSpacesGuiTest.py
    TDTest/DrawViewSelectionTeardownGuiTest.py
    TDTest/DrawViewDeleteWhileRunningGuiTest.py
    TDTest/TestInsertSymbolStackTopGui.py
    TDTest/TestDimensionLabelSnapGui.py
    TDTest/DrawTaskUndoGuiTest.py
    TDTest/DrawViewPartTest.py
    TDTest/DrawViewPositionTest.py
    TDTest/DrawViewSectionTest.py
    TDTest/DrawComplexSectionPlacementGuiTest.py
    TDTest/DrawViewSectionSelectionTest.py
    TDTest/DrawViewBalloonTest.py
    TDTest/DrawViewDetailTest.py
    TDTest/DrawViewDetailConsoleTest.py
    TDTest/DrawViewDetailMattingTest.py
    TDTest/DrawViewScaleTypeTest.py
    TDTest/DrawViewRemovalTest.py
    TDTest/DrawViewDimensionSavedGeometryTest.py
    TDTest/TechDrawTaskTest.py
    TDTest/TechDrawTestUtilities.py
)

SET(TDTestFile_SRCS
    TDTest/TestCaptionRestore33134.FCStd
    TDTest/TestCaptionRestore33134Empty.FCStd
    TDTest/TestHatch.svg
    TDTest/TestImage.png
    TDTest/TestSymbol.svg
    TDTest/TestNonAsciiSymbol.svg
    TDTest/TestTemplate.svg
)

SET(TDAllTest
    ${TDTest_SRCS}
    ${TDTestFile_SRCS}
)

ADD_CUSTOM_TARGET(TDTestTarget ALL
    SOURCES ${TDAllTest}
)

fc_copy_sources(TDTestTarget "${CMAKE_BINARY_DIR}/Mod/TechDraw" ${TDAllTest})

# install Python packages (for make install)
INSTALL(FILES ${TDTest_SRCS} DESTINATION Mod/TechDraw/TDTest)
INSTALL(FILES ${TDTestFile_SRCS} DESTINATION Mod/TechDraw/TDTest)
