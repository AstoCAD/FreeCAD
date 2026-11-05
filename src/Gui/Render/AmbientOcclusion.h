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

#include <array>

#include <Inventor/SbLinear.h>
#include <Inventor/nodes/SoNode.h>
#include <Inventor/nodes/SoSubNode.h>

#include <FCGlobal.h>

class SoState;

namespace Gui::Render
{

/// Texture unit that holds the ambient occlusion map while faces are shaded.
constexpr int ambientOcclusionUnit = 6;

/// The ambient occlusion map of the current OpenGL context, as left by the last pass.
struct AmbientOcclusionFrame
{
    bool valid = false;
    SbMatrix view;        ///< camera matrices the map was computed with (Coin row-vector order)
    SbMatrix projection;
    std::array<int, 4> viewport {};  ///< x, y, width, height in pixels of the target viewport
    unsigned int texture = 0;
    unsigned stamp = 0;
};

/// AO state of the current context, or nullptr.
GuiExport const AmbientOcclusionFrame* currentAmbientOcclusionFrame();

/// True while the depth prepass of the ambient occlusion traverses the scene.
GuiExport bool isInAmbientOcclusionPrepass();

/// Called by FaceShadingScope for every face shape of the prepass: records the camera matrices.
GuiExport void recordAmbientOcclusionMatrices(SoState* state);

/**
 * Screen-space ambient occlusion for the shaded faces (Enhanced quality, option on):
 * a half-resolution depth prepass of its scene (which must contain the camera) followed by
 * fc_ssao.frag into an AO texture of the current context, sampled by fc_face_shading.frag at the
 * fragment's screen position. Only faces read it, so edges, text and overlays are never darkened.
 * The map is reused while the scene (camera and geometry: field and child list changes, not a bare
 * touch() such as preselection), the viewport and the settings are unchanged; the viewer
 * skips the pass during interactive navigation (faces then render without AO).
 * Contexts without framebuffer objects or depth textures switch AO off for the session.
 */
class GuiExport SoFCAmbientOcclusionPass: public SoNode
{
    using inherited = SoNode;
    SO_NODE_HEADER(SoFCAmbientOcclusionPass);

public:
    static void initClass();
    SoFCAmbientOcclusionPass();

    /// The scene to occlude, including its camera. Referenced.
    void setScene(SoNode* scene);

    /// On screen: a changed scene may keep the previous map for a short while (rate limit, see
    /// Detail::decideMapUpdate()). Exports leave it off and always get an up to date map.
    void setPostponeUpdates(bool allowed)
    {
        postponeAllowed = allowed;
    }

    void GLRender(SoGLRenderAction* action) override;

protected:
    ~SoFCAmbientOcclusionPass() override;

private:
    SoNode* scene = nullptr;
    bool postponeAllowed = false;
};

/// Create (and register the type on first use) an ambient occlusion pass for scene.
GuiExport SoFCAmbientOcclusionPass* createAmbientOcclusionPass(SoNode* scene);

/// Radius of the occlusion as a fraction of the visible height, and its strength.
constexpr float ambientOcclusionRadius = 0.05F;
constexpr float ambientOcclusionStrength = 1.6F;

}  // namespace Gui::Render
