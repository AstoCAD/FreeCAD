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

#include <algorithm>
#include <cmath>

#include "ShadowMath.h"

// NOLINTBEGIN(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)

namespace Gui::Render
{

namespace
{

float dot(const Vec3& a, const Vec3& b)
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

Vec3 cross(const Vec3& a, const Vec3& b)
{
    return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]};
}

float length(const Vec3& a)
{
    return std::sqrt(dot(a, a));
}

Vec3 scaled(const Vec3& a, float s)
{
    return {a[0] * s, a[1] * s, a[2] * s};
}

Vec3 add(const Vec3& a, const Vec3& b)
{
    return {a[0] + b[0], a[1] + b[1], a[2] + b[2]};
}

Vec3 sub(const Vec3& a, const Vec3& b)
{
    return {a[0] - b[0], a[1] - b[1], a[2] - b[2]};
}

}  // namespace

Vec3 defaultSunDirection()
{
    const Vec3 d {0.35F, 0.25F, 1.0F};
    return scaled(d, 1.0F / length(d));
}

LightFrustum fitLightFrustum(const Vec3& towardsLight, const Vec3& boxMin, const Vec3& boxMax, float padding)
{
    LightFrustum frustum;
    const float lightLength = length(towardsLight);
    if (!(lightLength > 0.0F) || !std::isfinite(lightLength)) {
        return frustum;
    }
    for (int i = 0; i < 3; ++i) {
        if (!(boxMin[i] <= boxMax[i]) || !std::isfinite(boxMin[i]) || !std::isfinite(boxMax[i])) {
            return frustum;
        }
    }
    const Vec3 back = scaled(towardsLight, 1.0F / lightLength);
    // Any up vector not parallel to the light direction.
    const Vec3 worldUp = std::fabs(back[2]) < 0.99F ? Vec3 {0.0F, 0.0F, 1.0F} : Vec3 {0.0F, 1.0F, 0.0F};
    Vec3 right = cross(worldUp, back);
    right = scaled(right, 1.0F / length(right));
    const Vec3 up = cross(back, right);

    const Vec3 center = scaled(add(boxMin, boxMax), 0.5F);
    float maxX = 0.0F;
    float maxY = 0.0F;
    float minZ = 0.0F;
    float maxZ = 0.0F;
    for (int corner = 0; corner < 8; ++corner) {
        const Vec3 p {
            (corner & 1) ? boxMax[0] : boxMin[0],
            (corner & 2) ? boxMax[1] : boxMin[1],
            (corner & 4) ? boxMax[2] : boxMin[2],
        };
        const Vec3 d = sub(p, center);
        maxX = std::max(maxX, std::fabs(dot(d, right)));
        maxY = std::max(maxY, std::fabs(dot(d, up)));
        const float z = dot(d, back);
        minZ = std::min(minZ, z);
        maxZ = std::max(maxZ, z);
    }
    const float diagonal = length(sub(boxMax, boxMin));
    const float pad = std::max(padding * diagonal, 1e-6F);
    // A flat box (a plate seen edge-on by the light) still needs a non-empty frustum.
    frustum.halfWidth = maxX + pad;
    frustum.halfHeight = maxY + pad;
    const float margin = pad + 0.01F * diagonal;
    frustum.position = add(center, scaled(back, maxZ + margin));
    // The box spans the distances [margin, margin + (maxZ - minZ)] from the camera.
    frustum.nearDistance = 0.5F * margin;
    frustum.farDistance = (maxZ - minZ) + 1.5F * margin;
    frustum.right = right;
    frustum.up = up;
    frustum.back = back;
    frustum.valid = diagonal > 0.0F;
    return frustum;
}

Vec3 toLightClip(const LightFrustum& frustum, const Vec3& p)
{
    const Vec3 d = sub(p, frustum.position);
    const float x = dot(d, frustum.right);
    const float y = dot(d, frustum.up);
    const float distance = -dot(d, frustum.back);  // along the viewing direction
    const float range = frustum.farDistance - frustum.nearDistance;
    return {
        x / frustum.halfWidth,
        y / frustum.halfHeight,
        2.0F * (distance - frustum.nearDistance) / range - 1.0F,
    };
}

float shadowDepthBias(float texelWorldSize, float depthRange, float texels)
{
    if (!(depthRange > 0.0F)) {
        return 0.0F;
    }
    return std::clamp(texels * texelWorldSize / depthRange, 1e-5F, 0.05F);
}

float slopeScaledBias(float constantBias, float NoL, float maxScale)
{
    const float c = std::clamp(NoL, 0.05F, 1.0F);
    const float tangent = std::sqrt(1.0F - c * c) / c;
    return std::clamp(constantBias * tangent, constantBias, maxScale * constantBias);
}

std::array<std::array<float, 2>, shadowTapCount> shadowSampleDisk()
{
    std::array<std::array<float, 2>, shadowTapCount> disk {};
    for (int i = 0; i < shadowTapCount; ++i) {
        const float r = std::sqrt((float(i) + 0.5F) / float(shadowTapCount));
        const float a = float(i) * 2.39996323F;
        disk[size_t(i)] = {r * std::cos(a), r * std::sin(a)};
    }
    return disk;
}

}  // namespace Gui::Render

// NOLINTEND(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)
