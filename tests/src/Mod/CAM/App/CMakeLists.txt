add_executable(CAM_tests_run
    Path.cpp
    SimulatorGCodeParser.cpp
    # the simulator's G-code parser has no GUI dependency, so it is tested from its source
    ${CMAKE_SOURCE_DIR}/src/Mod/CAM/PathSimulator/AppGL/GCodeParser.cpp
)
