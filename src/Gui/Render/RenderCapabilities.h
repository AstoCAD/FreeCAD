// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the     *
 *   License, or (at your option) any later version.                          *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful, but           *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of               *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            *
 *   GNU Lesser General Public License for more details.                      *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD.  If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                         *
 *                                                                            *
 ******************************************************************************/

#pragma once

#include <string>
#include <string_view>

#include <FCGlobal.h>

namespace Gui::Render
{

/// The strings an OpenGL context reports about itself.
struct GLContextInfo
{
    std::string version;      ///< GL_VERSION
    std::string renderer;     ///< GL_RENDERER
    std::string vendor;       ///< GL_VENDOR
    std::string glslVersion;  ///< GL_SHADING_LANGUAGE_VERSION
    bool isOpenGLES = false;
};

struct GLVersion
{
    int major = 0;
    int minor = 0;

    bool atLeast(int maj, int min) const
    {
        return major > maj || (major == maj && minor >= min);
    }
};

/// Result of the capability check for the enhanced shading path.
struct CapabilityReport
{
    bool enhancedShading = false;
    /// Human readable reason when enhancedShading is false (empty otherwise).
    std::string reason;
};

/// Parse a GL_VERSION string ("4.6.0 NVIDIA 560.94", "2.1 Metal - 88", "OpenGL ES 3.2 Mesa 24").
/// Returns {0, 0} when no version number is found.
GuiExport GLVersion parseGLVersion(std::string_view text);

/// Parse a GL_SHADING_LANGUAGE_VERSION string into an integer version: "1.20" -> 120,
/// "4.60 NVIDIA" -> 460, "OpenGL ES GLSL ES 3.00" -> 300. Returns 0 when nothing is found.
GuiExport int parseGLSLVersion(std::string_view text);

/// Returns a non-empty reason when the renderer string matches the denylist
/// (software rasterizers and virtual GPUs known to be too slow or broken for shaders).
GuiExport std::string denylistReason(const GLContextInfo& info);

/// Decide whether the enhanced face shading may run on a context with these properties.
/// Pure function: the strings come from queryCurrentContext() or from a test.
GuiExport CapabilityReport evaluateCapabilities(const GLContextInfo& info);

/// The oldest GLSL version the shader library is written for (macOS legacy contexts).
constexpr int minimumGLSLVersion = 120;

/// Query the strings of the current QOpenGLContext. Returns an empty info if no context is current.
GuiExport GLContextInfo queryCurrentContext();

}  // namespace Gui::Render
