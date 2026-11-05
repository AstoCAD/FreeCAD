# SPDX-License-Identifier: LGPL-2.1-or-later

add_subdirectory(Dialogs)
add_subdirectory(propertyeditor)

# Standard C++ GTest tests
add_executable(Gui_tests_run
        Assistant.cpp
        Camera.cpp
        ColorScaleOverlayTest.cpp
        DocumentParameters.cpp
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
        RenderInfrastructure.cpp
        RenderPassUtilities.cpp
        RenderShadingModel.cpp
        RenderShadowMath.cpp
        SoMouseWheelEventTest.cpp
)

# Selection notifications require a reduced GUI application. Keep them separate
# from suites that initialize the full application without a main window.
add_executable(GuiSelection_tests_run SelectionTest.cpp)

# Qt tests
setup_qt_test(ObjectSelection)
setup_qt_test(TranslatorLocale)
setup_qt_test(InputField)
setup_qt_test(ExpressionCompleter)
setup_qt_test(QuantitySpinBox)
setup_qt_test(SceneImageRenderer OPENGL)
setup_qt_test(RenderEnhancedShading OPENGL)
setup_qt_test(NumericLocaleConsumers)
setup_qt_test(TaskBox)

target_link_libraries(Gui_tests_run PRIVATE
    GTest::gmock_main
    ${Python3_LIBRARIES}
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

# Offline compile check of the GLSL shader library (src/Gui/Render/Shaders). It needs no GPU:
# glslangValidator is the Khronos reference compiler and checks GLSL 1.20 with the compatibility
# built-ins. Skipped when the tool is not installed (it is not part of every build environment).
# Labelled "Qt" too, so that the CI step that runs the Qt test group (ctest -L Qt) runs it.
find_program(GLSLANG_VALIDATOR_EXECUTABLE NAMES glslangValidator glslang)
file(GLOB _render_shader_files
    "${CMAKE_SOURCE_DIR}/src/Gui/Render/Shaders/*.vert"
    "${CMAKE_SOURCE_DIR}/src/Gui/Render/Shaders/*.frag")
if(GLSLANG_VALIDATOR_EXECUTABLE)
    foreach(_render_shader IN LISTS _render_shader_files)
        get_filename_component(_render_shader_name "${_render_shader}" NAME)
        add_test(NAME Gui_GLSL_${_render_shader_name}
            COMMAND ${GLSLANG_VALIDATOR_EXECUTABLE} "${_render_shader}")
        set_tests_properties(Gui_GLSL_${_render_shader_name} PROPERTIES LABELS "Qt;GLSL")
    endforeach()
else()
    message(STATUS "glslangValidator not found: offline GLSL checks of src/Gui/Render/Shaders skipped")
endif()
