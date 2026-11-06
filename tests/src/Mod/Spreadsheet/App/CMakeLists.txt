# SPDX-License-Identifier: LGPL-2.1-or-later

add_executable(Spreadsheet_tests_run
            CellDecimals.cpp
            PropertySheet.cpp
            RenameProperty.cpp
            UserParameters.cpp
)

target_include_directories(Spreadsheet_tests_run PUBLIC
            ${CMAKE_BINARY_DIR}
)
