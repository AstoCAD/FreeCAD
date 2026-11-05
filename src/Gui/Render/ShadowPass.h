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

#include <Inventor/SbLinear.h>
#include <Inventor/nodes/SoNode.h>
#include <Inventor/nodes/SoSubNode.h>

#include <FCGlobal.h>

namespace Gui::Render
{

/// Texture unit that holds the shadow map while faces are shaded (Coin's textures use the low
/// units; textured faces are not shaded by the enhanced shader anyway).
constexpr int shadowTextureUnit = 7;

/// The shadow map of the current OpenGL context, as left by the last shadow pass.
struct ShadowFrame
{
    bool valid = false;
    SbMatrix worldToShadow;  ///< world -> [0, 1]^3 shadow map coordinates (Coin row-vector order)
    SbVec3f sunDirection;    ///< towards the sun, world coordinates
    unsigned int texture = 0;
    int size = 0;
    float bias = 0.0F;       ///< constant depth bias
    unsigned stamp = 0;      ///< changes every time the map is re-rendered
};

/// Shadow state of the current context, or nullptr.
GuiExport const ShadowFrame* currentShadowFrame();

/// True while a shadow pass traverses the scene (face shading must stay off then).
GuiExport bool isInShadowPass();

/**
 * Renders the shadow map of the soft shadows (Enhanced quality, shadows enabled) for its caster
 * scene: a depth-only pass of that scene, from an orthographic "sun" camera fitted to the scene's
 * bounding box, into a depth texture of the current context. The map is kept until the caster
 * scene changes (field or child list changes; a bare touch() such as preselection does not count),
 * the settings or the context change, so orbiting the camera does not re-render it.
 *
 * Applied with the main render action before the scene (View3DInventorViewer) or as the first
 * child of a capture root (offscreen exports). It does nothing at all unless shadows are active.
 * Contexts without framebuffer objects or depth textures switch shadows off for the session.
 */
class GuiExport SoFCShadowPass: public SoNode
{
    using inherited = SoNode;
    SO_NODE_HEADER(SoFCShadowPass);

public:
    static void initClass();
    SoFCShadowPass();

    /// The scene whose faces cast and receive shadows. Referenced.
    void setCasters(SoNode* casters);
    SoNode* getCasters() const
    {
        return casters;
    }

    /// On screen: a changed scene may keep the previous map for a short while (rate limit), and
    /// for the whole navigation when navigating is true; see Detail::decideMapUpdate().
    /// Exports leave it off and always get an up to date map.
    void setPostponeUpdates(bool allowed, bool navigating)
    {
        postponeAllowed = allowed;
        this->navigating = navigating;
    }

    void GLRender(SoGLRenderAction* action) override;

protected:
    ~SoFCShadowPass() override;

private:
    SoNode* casters = nullptr;
    bool postponeAllowed = false;
    bool navigating = false;
};

/// Create (and register the type on first use) a shadow pass node for casters.
GuiExport SoFCShadowPass* createShadowPass(SoNode* casters);

}  // namespace Gui::Render
