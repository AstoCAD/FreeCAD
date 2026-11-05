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
#include <utility>
#include <vector>

#include <FCGlobal.h>

namespace Gui::Render
{

/// Shaders shipped as Qt resources (src/Gui/Render/Shaders, prefix ":/shaders/render").
/// The .glsl files are plain GLSL that an offline compiler (glslangValidator) can check as is.
enum class ShaderId
{
    FaceShadingVertex,
    FaceShadingFragment,
    FullScreenVertex,
    FxaaFragment,
    AmbientOcclusionFragment,
};

using ShaderDefines = std::vector<std::pair<std::string, std::string>>;

/// Resource path of a shader, e.g. ":/shaders/render/fc_face_shading.vert".
GuiExport std::string shaderResourcePath(ShaderId id);

/// Raw source of a shader as stored in the resource. Empty if the resource is missing.
GuiExport std::string shaderSource(ShaderId id);

/// Insert "#define NAME VALUE" lines right after the "#version" line of source (which must stay
/// the first statement of a GLSL program), or at the top when the source has no "#version" line.
GuiExport std::string injectDefines(std::string_view source, const ShaderDefines& defines);

/// shaderSource() with defines injected.
GuiExport std::string buildShaderSource(ShaderId id, const ShaderDefines& defines);

}  // namespace Gui::Render
