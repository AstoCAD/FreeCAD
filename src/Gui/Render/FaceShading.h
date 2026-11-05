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

#include <FCGlobal.h>

class SbColor;
class SoGLRenderAction;

namespace Gui::Render
{

/**
 * Binds the enhanced face shader around the GLRender() of one face shape, and only when the
 * Enhanced quality is active and the shape's state is one the shader reproduces faithfully.
 * In every other case (Classic quality, unlit or textured faces, an emissive material, a user
 * shader, ...) the constructor does nothing at all, so the fixed-function rendering is unchanged.
 *
 * Usage, in a face shape's GLRender(), right around the draw call of the shaded faces:
 * @code
 *     Gui::Render::FaceShadingScope shading(action);
 *     inherited::GLRender(action);
 * @endcode
 * Never use it for lines, points, text, markers or overlays.
 *
 * While the shader is bound, any render cache being built is invalidated (as Coin's own
 * SoShaderProgram does), so no display list records the program or its uniforms.
 */
class GuiExport FaceShadingScope
{
public:
    /// tint: whole-object selection or preselection colour of the shape, or nullptr. A tinted
    /// shape is drawn in that colour, shaded by its lighting (exact at well lit areas) and with
    /// its own transparency. Without tint, an emissive colour override (whole-object
    /// (pre)selection of SoFCSelectionRoot and SoFCSelection) is used as the tint.
    explicit FaceShadingScope(SoGLRenderAction* action, const SbColor* tint = nullptr);
    ~FaceShadingScope();

    FaceShadingScope(const FaceShadingScope&) = delete;
    FaceShadingScope& operator=(const FaceShadingScope&) = delete;
    FaceShadingScope(FaceShadingScope&&) = delete;
    FaceShadingScope& operator=(FaceShadingScope&&) = delete;

    /// True if the shader is bound.
    bool isActive() const
    {
        return active;
    }

private:
    bool active = false;
};

/// True if, in Enhanced quality, selection and preselection of sub-elements must be drawn with the
/// unlit overlay passes (exact preference colours) instead of being mixed into the shaded faces.
GuiExport bool useUnlitSelectionOverlays();

/// True if the shader would be applied to a face shape rendered with this state.
/// Does not touch OpenGL. Exposed for tests.
GuiExport bool isFaceShadingEligible(SoGLRenderAction* action);

/// Try to compile and link the face shader in the current OpenGL context, without binding it and
/// without touching the session fallback. Returns an empty string on success, else the reason
/// (capability check or compiler / linker log). Used by tests and diagnostics.
GuiExport std::string validateFaceShaderInCurrentContext();

}  // namespace Gui::Render
