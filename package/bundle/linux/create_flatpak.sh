#!/bin/bash

# Packages the tree that create_bundle.sh prepared for the AppImage (./AppDir) as a
# single-file Flatpak bundle: the same files, started by the same AppRun script, in the
# Flatpak sandbox on top of the freedesktop runtime. Run it after create_bundle.sh, in the
# same directory. It moves AppDir into the Flatpak build directory.
#
# Needs the flatpak command, and network access to Flathub for the runtime.
# Users install the result with: flatpak install --user AstoCAD_<tag>-Linux-<arch>.flatpak
# which gets the runtime from Flathub if it is not installed yet.

set -e
set -x

app_id="com.astocad.AstoCAD"
runtime_version="${FLATPAK_RUNTIME_VERSION:-25.08}"
flathub="https://dl.flathub.org/repo/flathub.flatpakrepo"
version_name="AstoCAD_${BUILD_TAG}-Linux-$(uname -m)"
build_dir="flatpak-build"
repo_dir="flatpak-repo"

if [ ! -x AppDir/AppRun ] || [ ! -x AppDir/usr/bin/AstoCAD ]; then
    echo "AppDir is missing: run create_bundle.sh first."
    exit 1
fi

flatpak remote-add --user --if-not-exists flathub "${flathub}"
flatpak install --user --noninteractive -y flathub \
    "org.freedesktop.Platform//${runtime_version}" \
    "org.freedesktop.Sdk//${runtime_version}"

rm -rf "${build_dir}" "${repo_dir}"
flatpak build-init "${build_dir}" "${app_id}" \
    org.freedesktop.Sdk org.freedesktop.Platform "${runtime_version}"

# The application, as in the AppImage: /app/astocad is what the mount point of the AppImage is
mv AppDir "${build_dir}/files/astocad"

mkdir -p "${build_dir}/files/bin"
cat > "${build_dir}/files/bin/astocad" << 'EOF'
#!/bin/bash
exec /app/astocad/AppRun "$@"
EOF
chmod a+x "${build_dir}/files/bin/astocad"

# What the desktop shows: Flatpak only exports files that are named after the application
mkdir -p "${build_dir}/files/share/applications"
sed -e "s/^Exec=.*/Exec=astocad --single-instance %F/" \
    -e "s/^Icon=.*/Icon=${app_id}/" \
    "${build_dir}/files/astocad/com.astocad.desktop" \
    > "${build_dir}/files/share/applications/${app_id}.desktop"
mkdir -p "${build_dir}/files/share/icons/hicolor/scalable/apps"
cp "${build_dir}/files/astocad/AstoCAD.svg" \
    "${build_dir}/files/share/icons/hicolor/scalable/apps/${app_id}.svg"
mkdir -p "${build_dir}/files/share/icons/hicolor/256x256/apps"
cp "${build_dir}/files/astocad/AstoCAD.png" \
    "${build_dir}/files/share/icons/hicolor/256x256/apps/${app_id}.png"

# The sandbox. AppRun starts Qt on X11 unless told otherwise, hence both display sockets.
# The home directory: documents refer to each other, and to their external files, by path.
# The network: the Addon Manager.
flatpak build-finish "${build_dir}" \
    --command=astocad \
    --share=ipc \
    --share=network \
    --socket=x11 \
    --socket=wayland \
    --device=dri \
    --filesystem=home

flatpak build-export "${repo_dir}" "${build_dir}" stable
flatpak build-bundle --runtime-repo="${flathub}" \
    "${repo_dir}" "${version_name}.flatpak" "${app_id}" stable

rm -rf "${build_dir}" "${repo_dir}"

echo -e "\################"
echo -e "flatpak:  ${version_name}.flatpak"
echo -e "################"
