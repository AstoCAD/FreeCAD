# SPDX-License-Identifier: LGPL-2.1-or-later

add_subdirectory(Dialogs)
add_subdirectory(propertyeditor)

# Standard C++ GTest tests
add_executable(Gui_tests_run
        Assistant.cpp
        Camera.cpp
        ColorScaleOverlayTest.cpp
        FileDialog.cpp
        StyleParameters/DiagnosticsCapture.h
        StyleParameters/ValueMatchers.h
        StyleParameters/ValueMatchers.cpp
        StyleParameters/StyleParametersApplicationTest.cpp
        StyleParameters/ParserTest.cpp
        StyleParameters/ParserRobustnessTest.cpp
        StyleParameters/ParameterManagerTest.cpp
        StyleParameters/YamlParameterSourceTest.cpp
        StyleParameters/DiagnosticsTest.cpp
        StyleParameters/ValueAccessTest.cpp
        StyleParameters/EdgesTest.cpp
        StyleParameters/CornersTest.cpp
        StyleParameters/GradientTest.cpp
        StyleParameters/ColorShadingTest.cpp
        InputHintTest.cpp
        ViewProviderDoubleClick.cpp
        NativeGesturePinchTest.cpp
        NavigationStylePinchTest.cpp
        NavigationStyleWheelTest.cpp
        SoMouseWheelEventTest.cpp
)

# Selection notifications require a reduced GUI application. Keep them separate
# from suites that initialize the full application without a main window.
add_executable(GuiSelection_tests_run SelectionTest.cpp)

# Qt tests
setup_qt_test(ObjectSelection)
setup_qt_test(TranslatorLocale)
setup_qt_test(InputField)
setup_qt_test(QuantitySpinBox)
setup_qt_test(SceneImageRenderer OPENGL)
setup_qt_test(GLPainterProjection OPENGL)
setup_qt_test(NumericLocaleConsumers)

target_link_libraries(Gui_tests_run PRIVATE
    GTest::gmock_main
    FreeCADApp
    FreeCADGui
)

target_link_libraries(GuiSelection_tests_run PRIVATE
    GTest::gmock_main
    FreeCADApp
    FreeCADGui
)

if(WIN32)
    target_compile_definitions(Gui_tests_run PRIVATE QUARTER_DLL)
    target_compile_definitions(GuiSelection_tests_run PRIVATE QUARTER_DLL)
    # AppHomePath is derived from the executable location, so keep this test
    # beside the FreeCAD executable even with a multi-configuration generator.
    set_target_properties(GuiSelection_tests_run PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
    foreach(_selection_config IN LISTS CMAKE_CONFIGURATION_TYPES)
        string(TOUPPER "${_selection_config}" _selection_config_upper)
        set_target_properties(GuiSelection_tests_run PROPERTIES
            RUNTIME_OUTPUT_DIRECTORY_${_selection_config_upper} ${CMAKE_BINARY_DIR}/bin)
    endforeach()
endif()
