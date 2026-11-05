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

#include <FCGlobal.h>

namespace Gui::Render
{

/// Pure geometry of the enhanced-shading soft shadows (no OpenGL, no Coin).

using Vec3 = std::array<float, 3>;

/// Direction towards the shadow-casting "sun", in world coordinates (decision D4: fixed in the
/// world, above the model (+Z up) with a slight angle, so shadows stay still while orbiting).
GuiExport Vec3 defaultSunDirection();

/// An orthographic light camera fitted around a box.
struct LightFrustum
{
    Vec3 position {};   ///< camera position (on the light side of the box)
    Vec3 right {};      ///< camera x axis (unit)
    Vec3 up {};         ///< camera y axis (unit)
    Vec3 back {};       ///< camera z axis (unit) = direction towards the light
    float halfWidth = 0.0F;
    float halfHeight = 0.0F;
    float nearDistance = 0.0F;
    float farDistance = 0.0F;
    bool valid = false;
};

/// Fit an orthographic light frustum looking along -towardsLight around the axis-aligned box
/// [boxMin, boxMax], with a relative padding. Invalid for an empty or degenerate input.
GuiExport LightFrustum fitLightFrustum(
    const Vec3& towardsLight,
    const Vec3& boxMin,
    const Vec3& boxMax,
    float padding = 0.02F
);

/// Coordinates of world point p in the frustum, normalized to [-1, 1] in x, y (the shadow map)
/// and z (near to far, -1 at the near plane). Used by the tests.
GuiExport Vec3 toLightClip(const LightFrustum& frustum, const Vec3& p);

/// Constant depth bias (in [0, 1] shadow-map depth units) that covers about one map texel of
/// surface slope: texelWorld / depthRange * texels.
GuiExport float shadowDepthBias(float texelWorldSize, float depthRange, float texels = 1.5F);

/// Slope-scaled bias for a surface whose normal makes cos = NoL with the light direction:
/// constantBias * tan(theta), clamped to [constantBias, maxScale * constantBias].
/// Same formula as fcSlopeBias() in fc_face_shading.frag.
GuiExport float slopeScaledBias(float constantBias, float NoL, float maxScale = 10.0F);

/// The sample pattern of the soft (PCF) shadow lookups: a Vogel (golden angle) spiral of unit
/// radius, r_i = sqrt((i + 0.5) / N), angle_i = i * 2.39996 rad. fcShadowVisibility() in
/// fc_face_shading.frag computes the same points.
constexpr int shadowTapCount = 12;
GuiExport std::array<std::array<float, 2>, shadowTapCount> shadowSampleDisk();

}  // namespace Gui::Render
