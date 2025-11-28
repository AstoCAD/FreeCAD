if [[ ${HOST} =~ .*linux.*  ]]; then
    CMAKE_PRESET=conda-linux-release
fi

if [[ ${HOST} =~ .*darwin.* ]]; then
    CMAKE_PRESET=conda-macos-release

    # add hacks for osx here!
    echo "adding hacks for osx"

    # install space-mouse
    /usr/bin/curl -o /tmp/3dFW.dmg -L 'https://download.3dconnexion.com/drivers/mac/10-7-0_B564CC6A-6E81-42b0-82EC-418EA823B81A/3DxWareMac_v10-7-0_r3411.dmg'
    hdiutil attach -readonly /tmp/3dFW.dmg
    sudo installer -package /Volumes/3Dconnexion\ Software/Install\ 3Dconnexion\ software.pkg -target /
    diskutil eject /Volumes/3Dconnexion\ Software
    CMAKE_PLATFORM_FLAGS+=(-DFREECAD_USE_3DCONNEXION:BOOL=ON)
    CMAKE_PLATFORM_FLAGS+=(-D3DCONNEXIONCLIENT_FRAMEWORK:FILEPATH="/Library/Frameworks/3DconnexionClient.framework")

    CXXFLAGS="${CXXFLAGS} -D_LIBCPP_DISABLE_AVAILABILITY"
fi

unset CMAKE_GENERATOR
unset CMAKE_GENERATOR_PLATFORM

cmake \
    ${CMAKE_ARGS} \
    --preset ${CMAKE_PRESET} \
    -D CMAKE_IGNORE_PREFIX_PATH="/opt/homebrew;/usr/local/homebrew" \
    -D CMAKE_INCLUDE_PATH:FILEPATH="$PREFIX/include" \
    -D CMAKE_INSTALL_LIBDIR:FILEPATH="$PREFIX/lib" \
    -D CMAKE_INSTALL_PREFIX:FILEPATH="$PREFIX" \
    -D CMAKE_LIBRARY_PATH:FILEPATH="$PREFIX/lib" \
    -D CMAKE_PREFIX_PATH:FILEPATH="$PREFIX" \
    -D FREECAD_USE_EXTERNAL_FMT:BOOL=OFF \
    -D INSTALL_TO_SITEPACKAGES:BOOL=ON \
    -D OCC_INCLUDE_DIR:FILEPATH="$PREFIX/include/opencascade" \
    -D OCC_LIBRARY_DIR:FILEPATH="$PREFIX/lib" \
    -D Python_EXECUTABLE:FILEPATH="$PYTHON" \
    -D Python3_EXECUTABLE:FILEPATH="$PYTHON" \
    -D BUILD_DYNAMIC_LINK_PYTHON:BOOL=OFF \
    -B build \
    -S .

cmake --build build
cmake --install build

# --- START ASTOCAD CHANGES ---
# 1. Rename Binaries
mv ${PREFIX}/bin/FreeCAD ${PREFIX}/bin/AstoCAD
mv ${PREFIX}/bin/FreeCADCmd ${PREFIX}/bin/AstoCADcmd
# Optional: Symlinks for compatibility
ln -s AstoCAD ${PREFIX}/bin/freecad
ln -s AstoCADcmd ${PREFIX}/bin/freecadcmd

# 2. Install Branding
# Note: $SRC_DIR is the root of the repo.
BRANDING_DIR="$SRC_DIR/package/rattler-build/branding"

echo "Installing branding from $BRANDING_DIR..."

if [[ ${HOST} =~ .*linux.* ]]; then
    # 1. Desktop File
    mkdir -p "${PREFIX}/share/applications"
    install -m 644 "$BRANDING_DIR/com.astocad.desktop" "${PREFIX}/share/applications/"
    # Remove original FreeCAD desktop file
    rm "${PREFIX}/share/applications/org.freecad.FreeCAD.desktop" || true

    # 2. Icons
    mkdir -p "${PREFIX}/share/icons/hicolor/scalable/apps/"
    install -m 644 "$BRANDING_DIR/AstoCAD.svg" "${PREFIX}/share/icons/hicolor/scalable/apps/"
fi

# 3. Branding XML and Configs
# This puts branding.xml where the binary looks for it
install -m 644 "$BRANDING_DIR/branding.xml" "${PREFIX}/bin/"

# 4. Defaults Config
# Ensure the target directory exists
mkdir -p "${PREFIX}/share/Gui/AstoCAD"
install -m 644 "$BRANDING_DIR/AstoCAD-defaults.cfg" "${PREFIX}/share/Gui/AstoCAD/"

# 5. Splash screens and other assets
# Copy everything else from branding to the Gui folder
cp -r "$BRANDING_DIR/"* "${PREFIX}/share/Gui/AstoCAD/"
# --- END ASTOCAD CHANGES ---
