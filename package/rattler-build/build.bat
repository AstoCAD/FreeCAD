@echo on

@REM :: free up extra disk space, compare
@REM :: https://github.com/conda-forge/conda-smithy/issues/1949
@REM rmdir /s /q C:\hostedtoolcache\windows

@REM set "CFLAGS= "
@REM set "CXXFLAGS= -DBOOST_PROGRAM_OPTIONS_DYN_LINK=1"
@REM set "LDFLAGS_SHARED= ucrt.lib"

set "CMAKE_GENERATOR="
set "CMAKE_GENERATOR_PLATFORM="

cmake ^
    %CMAKE_ARGS% ^
    --preset conda-windows-release ^
    -D CMAKE_C_COMPILER:STRING="%CC%" ^
    -D CMAKE_CXX_COMPILER:STRING="%CXX%" ^
    -D CMAKE_INCLUDE_PATH:FILEPATH="%LIBRARY_PREFIX%/include" ^
    -D CMAKE_INSTALL_LIBDIR:FILEPATH="%LIBRARY_PREFIX%/lib" ^
    -D CMAKE_INSTALL_PREFIX:FILEPATH="%LIBRARY_PREFIX%" ^
    -D CMAKE_LIBRARY_PATH:FILEPATH="%LIBRARY_PREFIX%/lib" ^
    -D CMAKE_PREFIX_PATH:FILEPATH="%LIBRARY_PREFIX%" ^
    -D FREECAD_USE_EXTERNAL_FMT:BOOL=OFF ^
    -D INSTALL_TO_SITEPACKAGES:BOOL=ON ^
    -D OCC_INCLUDE_DIR:FILEPATH="%LIBRARY_PREFIX%/include/opencascade" ^
    -D OCC_LIBRARY_DIR:FILEPATH="%LIBRARY_PREFIX%/lib" ^
    -D Python_EXECUTABLE:FILEPATH="%PYTHON%" ^
    -D Python3_EXECUTABLE:FILEPATH="%PYTHON%" ^
    -D SMESH_INCLUDE_DIR:FILEPATH="%LIBRARY_PREFIX%/include/smesh" ^
    -D SMESH_LIBRARY:FILEPATH="%LIBRARY_PREFIX%/lib/SMESH.lib" ^
    -B build ^
    -S .
if %ERRORLEVEL% neq 0 exit 1

ninja -C build install

:: --- START ASTOCAD CHANGES ---
:: Rename binaries
ren %LIBRARY_PREFIX%\bin\FreeCAD.exe AstoCAD.exe
ren %LIBRARY_PREFIX%\bin\FreeCADCmd.exe AstoCADcmd.exe

:: Create compatibility copies (symlinks are not supported in Windows conda packages)
copy "%LIBRARY_PREFIX%\bin\AstoCAD.exe" "%LIBRARY_PREFIX%\bin\freecad.exe"
copy "%LIBRARY_PREFIX%\bin\AstoCADcmd.exe" "%LIBRARY_PREFIX%\bin\freecadcmd.exe"

:: --- ASTOCAD BRANDING ---
set BRANDING_DIR=%SRC_DIR%\package\rattler-build\branding

:: Copy branding.xml next to executable
copy /y "%BRANDING_DIR%\branding.xml" "%LIBRARY_PREFIX%\bin\"

:: Create Gui config folder
if not exist "%LIBRARY_PREFIX%\share\Gui\AstoCAD" mkdir "%LIBRARY_PREFIX%\share\Gui\AstoCAD"

:: Copy all branding assets
xcopy /s /y "%BRANDING_DIR%\*" "%LIBRARY_PREFIX%\share\Gui\AstoCAD\"

:: Replace the main Icon (optional, usually handled by resource compiler, but good to have)
copy /y "%BRANDING_DIR%\AstoCAD.ico" "%SRC_DIR%\src\Main\icon.ico"
:: --- END ASTOCAD CHANGES ---

if %ERRORLEVEL% neq 0 exit 1
