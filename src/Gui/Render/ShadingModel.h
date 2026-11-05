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
#include <functional>

#include <FCGlobal.h>

#include "RenderSettings.h"

namespace Gui::Render
{

/// CPU side of the enhanced face shading: the procedural environments and a C++ mirror of the
/// material conversion done in fc_face_shading.frag. Pure functions, no OpenGL, no Coin.

using Rgb = std::array<float, 3>;
using Direction = std::array<float, 3>;

/// Number of soft "softbox" light lobes of an environment (FC_ENV_LIGHTS in the shader).
constexpr int environmentLightCount = 2;

/// One softbox: a Phong-like lobe pow(max(dot(d, direction), 0), exponent) * color.
struct EnvironmentLight
{
    Direction direction {0.0F, 1.0F, 0.0F};  ///< unit vector
    Rgb color {};
    float exponent = 1.0F;  ///< >= 1; larger is a smaller, sharper softbox
};

/// Procedural environment, defined in eye space (+y is up on the screen, +z toward the viewer):
/// a studio sky / bright soft horizon / dark ground gradient plus softboxes. Colours are linear.
/// The specular reflections see all of it; diffuse lighting uses its irradiance scaled by
/// diffuseScale (a CAD view needs readable shape contrast more than a physically exact ambient).
struct EnvironmentDescription
{
    Rgb sky {};      ///< zenith
    Rgb horizon {};  ///< bright band at the horizon
    Rgb ground {};
    float skyRamp = 0.6F;     ///< height above the horizon where the sky colour is reached
    float groundRamp = 0.15F; ///< depth below the horizon where the ground colour is reached
    std::array<EnvironmentLight, environmentLightCount> lights {};
    float intensity = 1.0F;   ///< multiplies every colour above
    float diffuseScale = 1.0F;
};

GuiExport EnvironmentDescription environmentDescription(EnvironmentPreset preset);

/// Radiance of the environment towards direction d (unit vector), intensity applied, unblurred.
/// Same formula as fcEnvironment(d, 0.0) in the fragment shader.
GuiExport Rgb environmentRadiance(const EnvironmentDescription& env, const Direction& d);

/// Everything the face shader needs for one preset (intensity applied).
struct EnvironmentUniforms
{
    std::array<Rgb, 9> irradiance {};  ///< fc_sh: E(n) / pi of the full environment
    float diffuseScale = 1.0F;         ///< fc_envDiffuseScale
    Rgb sky {};
    Rgb horizon {};
    Rgb ground {};
    float skyRamp = 0.6F;
    float groundRamp = 0.15F;
    std::array<Direction, environmentLightCount> lightDirection {};
    std::array<Rgb, environmentLightCount> lightColor {};
    std::array<float, environmentLightCount> lightExponent {};
};

GuiExport EnvironmentUniforms environmentUniforms(EnvironmentPreset preset);

/// Order-2 real spherical harmonics, coefficient order:
/// Y00, Y1-1 (y), Y10 (z), Y11 (x), Y2-2 (xy), Y2-1 (yz), Y20, Y21 (xz), Y22 (x^2 - y^2).
using SH9 = std::array<Rgb, 9>;

/// Project a radiance function onto SH9 by numerical integration on a latitude / longitude grid
/// (deterministic; `rings` latitude bands around the +y axis, 2 * rings longitudes).
GuiExport SH9 projectRadiance(const std::function<Rgb(const Direction&)>& radiance, int rings = 64);

/// Convolve projected radiance with the clamped cosine lobe and divide by pi, so that
/// evaluateSH9(result, n) is the irradiance E(n) / pi (a diffuse albedo multiplier).
GuiExport SH9 irradianceFromRadiance(const SH9& radiance);

/// Evaluate SH9 coefficients in direction n (same basis as fcIrradiance() in the shader).
GuiExport Rgb evaluateSH9(const SH9& coefficients, const Direction& n);

/// The SH9 irradiance coefficients uploaded to the shader for a preset.
GuiExport SH9 environmentIrradiance(EnvironmentPreset preset);

/// The metallic / roughness reading of a Phong material (linear colours, GL shininess 0..128).
struct PbrMaterial
{
    Rgb baseColor {};
    float metallic = 0.0F;
    float alpha = 1.0F;           ///< GGX alpha
    float roughness = 1.0F;       ///< perceptual roughness, sqrt(alpha)
    float specularWeight = 1.0F;  ///< 0 when the Phong specular colour is black
};

GuiExport PbrMaterial phongToPbr(const Rgb& diffuseLinear, const Rgb& specularLinear, float glShininess);

/// sRGB-like transfer used by the shader (gamma 2.2).
GuiExport Rgb toLinear(const Rgb& displayColor);

}  // namespace Gui::Render
