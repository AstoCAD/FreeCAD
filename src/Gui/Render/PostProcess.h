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

#include <Inventor/nodes/SoNode.h>
#include <Inventor/nodes/SoSubNode.h>

#include <FCGlobal.h>

#include "ShaderLibrary.h"

class QOpenGLShaderProgram;

namespace Gui::Render
{

/// Texture unit used by the full-screen passes for their input (restored afterwards).
constexpr int postProcessTextureUnit = 5;

/**
 * FXAA on the current draw framebuffer, in place: the colour of the current viewport is copied
 * to a texture and drawn back through fc_fxaa.frag. Call it after the scene and before overlays
 * that must stay crisp (navigation cube, axis cross, decorations).
 * Does nothing unless RenderSettings::fxaaActive(), and nothing on a multisampled framebuffer
 * (the hardware anti-aliasing is kept). GL state is saved and restored.
 */
GuiExport void applyFxaa();

/// A node that calls applyFxaa() when rendered: last child of capture roots (exports).
class GuiExport SoFCPostProcess: public SoNode
{
    using inherited = SoNode;
    SO_NODE_HEADER(SoFCPostProcess);

public:
    static void initClass();
    SoFCPostProcess();
    void GLRender(SoGLRenderAction* action) override;

protected:
    ~SoFCPostProcess() override = default;
};

/// Create (and register the type on first use) a post-process node.
GuiExport SoFCPostProcess* createPostProcess();

namespace Detail
{

/// Full-screen program (fc_fullscreen.vert + fragment) of the current context, compiled on first
/// use and kept with the context. nullptr and error set on failure.
GuiExport QOpenGLShaderProgram* fullScreenProgram(ShaderId fragment, std::string& error);

/// Draw a quad covering clip space with texture coordinates [0, 1]^2 (immediate mode, unit 0).
GuiExport void drawFullScreenQuad();

/// Saves the GL state a full-screen pass changes and sets a neutral one (no depth test or write,
/// no blending, lighting, clipping, culling or stencil, identity matrices); restores in the
/// destructor, including the bound program and the texture of postProcessTextureUnit.
class GuiExport FullScreenPassState
{
public:
    FullScreenPassState();
    ~FullScreenPassState();
    FullScreenPassState(const FullScreenPassState&) = delete;
    FullScreenPassState& operator=(const FullScreenPassState&) = delete;

private:
    int previousProgram = 0;
    int previousActiveTexture = 0;
    int previousTexture = 0;
};

}  // namespace Detail

}  // namespace Gui::Render
