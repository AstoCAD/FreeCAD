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
#include <numbers>

#include "ShadingModel.h"

// NOLINTBEGIN(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)

namespace Gui::Render
{

namespace
{

constexpr float pi = std::numbers::pi_v<float>;
constexpr float dielectricF0 = 0.04F;
constexpr float metalLow = 0.35F;   // FC_METAL_LOW in the shader
constexpr float metalHigh = 0.75F;  // FC_METAL_HIGH in the shader
constexpr float metalTint = 0.5F;   // FC_METAL_TINT in the shader
constexpr float metalSpecularLow = 0.27F;    // FC_METAL_SPECULAR_LOW (linear, ~0.55 display)
constexpr float metalSpecularHigh = 0.46F;   // FC_METAL_SPECULAR_HIGH (linear, ~0.70 display)
constexpr float metalGlossLow = 0.45F * 128.0F;   // FC_METAL_GLOSS_LOW (GL shininess)
constexpr float metalGlossHigh = 0.70F * 128.0F;  // FC_METAL_GLOSS_HIGH
constexpr float metalRoughnessScale = 0.6F;       // FC_METAL_ROUGHNESS_SCALE
constexpr float specularFade = 0.1F;              // FC_SPECULAR_FADE (display units)

Direction normalized(float x, float y, float z)
{
    const float length = std::sqrt(x * x + y * y + z * z);
    return {x / length, y / length, z / length};
}

float mix(float a, float b, float t)
{
    return a * (1.0F - t) + b * t;
}

Rgb mix(const Rgb& a, const Rgb& b, float t)
{
    return {mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)};
}

float smoothstep(float edge0, float edge1, float x)
{
    const float t = std::clamp((x - edge0) / (edge1 - edge0), 0.0F, 1.0F);
    return t * t * (3.0F - 2.0F * t);
}

float perceived(const Rgb& c)
{
    return std::sqrt(0.299F * c[0] * c[0] + 0.587F * c[1] * c[1] + 0.114F * c[2] * c[2]);
}

float solveMetallic(float diffuse, float specular, float oneMinusSpecularStrength)
{
    if (specular < dielectricF0) {
        return 0.0F;
    }
    const float a = dielectricF0;
    const float b = diffuse * oneMinusSpecularStrength / (1.0F - a) + specular - 2.0F * a;
    const float c = a - specular;
    const float discriminant = std::max(b * b - 4.0F * a * c, 0.0F);
    return std::clamp((-b + std::sqrt(discriminant)) / (2.0F * a), 0.0F, 1.0F);
}

std::array<float, 9> shBasis(const Direction& n)
{
    const float x = n[0];
    const float y = n[1];
    const float z = n[2];
    return {
        0.282095F,
        0.488603F * y,
        0.488603F * z,
        0.488603F * x,
        1.092548F * x * y,
        1.092548F * y * z,
        0.315392F * (3.0F * z * z - 1.0F),
        1.092548F * x * z,
        0.546274F * (x * x - y * y),
    };
}

}  // namespace

EnvironmentDescription environmentDescription(EnvironmentPreset preset)
{
    EnvironmentDescription env;
    switch (preset) {
        case EnvironmentPreset::Neutral:
            // Soft, even grey studio: one large overhead softbox, no strong horizon.
            env.sky = {0.36F, 0.36F, 0.36F};
            env.horizon = {0.45F, 0.45F, 0.45F};
            env.ground = {0.07F, 0.07F, 0.07F};
            env.skyRamp = 0.8F;
            env.groundRamp = 0.3F;
            env.lights[0] = {normalized(0.0F, 0.9F, 0.45F), {2.0F, 2.0F, 2.0F}, 12.0F};
            env.lights[1] = {normalized(0.0F, -0.2F, 1.0F), {0.0F, 0.0F, 0.0F}, 1.0F};
            env.intensity = 1.0F;
            env.diffuseScale = 0.18F;
            break;
        case EnvironmentPreset::Interior:
            // Warm room: bluish window light from the right, warm floor bounce.
            env.sky = {0.30F, 0.33F, 0.38F};
            env.horizon = {0.45F, 0.42F, 0.38F};
            env.ground = {0.16F, 0.12F, 0.09F};
            env.skyRamp = 0.6F;
            env.groundRamp = 0.3F;
            env.lights[0] = {normalized(0.9F, 0.35F, 0.35F), {2.6F, 2.7F, 3.0F}, 18.0F};
            env.lights[1] = {normalized(-0.6F, 0.7F, 0.4F), {0.9F, 0.8F, 0.65F}, 10.0F};
            env.intensity = 1.0F;
            env.diffuseScale = 0.18F;
            break;
        case EnvironmentPreset::Studio:
        default:
            // Photo studio: darker sky, bright soft horizon line, dark floor, an overhead
            // softbox and a vertical strip light on the left. Gives metals something to reflect.
            env.sky = {0.45F, 0.48F, 0.54F};
            env.horizon = {0.85F, 0.85F, 0.87F};
            env.ground = {0.035F, 0.035F, 0.035F};
            env.skyRamp = 0.45F;
            env.groundRamp = 0.12F;
            env.lights[0] = {normalized(0.15F, 0.85F, 0.5F), {2.6F, 2.55F, 2.5F}, 24.0F};
            env.lights[1] = {normalized(-0.85F, 0.15F, 0.5F), {1.6F, 1.6F, 1.65F}, 28.0F};
            env.intensity = 1.0F;
            env.diffuseScale = 0.18F;
            break;
    }
    return env;
}

Rgb environmentRadiance(const EnvironmentDescription& env, const Direction& d)
{
    const float t = std::clamp(d[1], -1.0F, 1.0F);
    Rgb result;
    if (t >= 0.0F) {
        result = mix(env.horizon, env.sky, smoothstep(0.0F, env.skyRamp, t));
    }
    else {
        result = mix(env.horizon, env.ground, smoothstep(0.0F, env.groundRamp, -t));
    }
    for (const EnvironmentLight& light : env.lights) {
        const float c = std::max(
            d[0] * light.direction[0] + d[1] * light.direction[1] + d[2] * light.direction[2],
            0.0F
        );
        const float lobe = std::pow(std::max(c, 1e-6F), std::max(light.exponent, 1.0F));
        for (int i = 0; i < 3; ++i) {
            result[i] += light.color[i] * lobe;
        }
    }
    for (float& value : result) {
        value *= env.intensity;
    }
    return result;
}

EnvironmentUniforms environmentUniforms(EnvironmentPreset preset)
{
    const EnvironmentDescription env = environmentDescription(preset);
    EnvironmentUniforms uniforms;
    uniforms.irradiance = irradianceFromRadiance(projectRadiance([&env](const Direction& d) {
        return environmentRadiance(env, d);
    }));
    uniforms.diffuseScale = env.diffuseScale;
    for (int i = 0; i < 3; ++i) {
        uniforms.sky[i] = env.sky[i] * env.intensity;
        uniforms.horizon[i] = env.horizon[i] * env.intensity;
        uniforms.ground[i] = env.ground[i] * env.intensity;
    }
    uniforms.skyRamp = env.skyRamp;
    uniforms.groundRamp = env.groundRamp;
    for (size_t k = 0; k < env.lights.size(); ++k) {
        uniforms.lightDirection[k] = env.lights[k].direction;
        for (int i = 0; i < 3; ++i) {
            uniforms.lightColor[k][i] = env.lights[k].color[i] * env.intensity;
        }
        uniforms.lightExponent[k] = std::max(env.lights[k].exponent, 1.0F);
    }
    return uniforms;
}

SH9 projectRadiance(const std::function<Rgb(const Direction&)>& radiance, int rings)
{
    rings = std::max(rings, 2);
    const int longitudes = 2 * rings;
    const float deltaTheta = pi / float(rings);
    const float deltaPhi = 2.0F * pi / float(longitudes);
    SH9 result {};
    for (int i = 0; i < rings; ++i) {
        const float theta0 = float(i) * deltaTheta;
        const float theta1 = float(i + 1) * deltaTheta;
        const float theta = 0.5F * (theta0 + theta1);
        // Exact solid angle of the cell, so that the weights add up to 4 pi.
        const float weight = (std::cos(theta0) - std::cos(theta1)) * deltaPhi;
        for (int j = 0; j < longitudes; ++j) {
            const float phi = (float(j) + 0.5F) * deltaPhi;
            const Direction d {
                std::sin(theta) * std::cos(phi),
                std::cos(theta),  // polar axis is +y (up)
                std::sin(theta) * std::sin(phi),
            };
            const Rgb value = radiance(d);
            const auto basis = shBasis(d);
            for (size_t k = 0; k < 9; ++k) {
                for (size_t c = 0; c < 3; ++c) {
                    result[k][c] += value[c] * basis[k] * weight;
                }
            }
        }
    }
    return result;
}

SH9 irradianceFromRadiance(const SH9& radiance)
{
    // Clamped cosine convolution (Ramamoorthi and Hanrahan 2001), divided by pi.
    constexpr std::array<float, 9> band {
        1.0F,                                        // pi / pi
        2.0F / 3.0F, 2.0F / 3.0F, 2.0F / 3.0F,       // (2 pi / 3) / pi
        0.25F, 0.25F, 0.25F, 0.25F, 0.25F,           // (pi / 4) / pi
    };
    SH9 result {};
    for (size_t k = 0; k < 9; ++k) {
        for (size_t c = 0; c < 3; ++c) {
            result[k][c] = radiance[k][c] * band[k];
        }
    }
    return result;
}

Rgb evaluateSH9(const SH9& coefficients, const Direction& n)
{
    const auto basis = shBasis(n);
    Rgb result {};
    for (size_t k = 0; k < 9; ++k) {
        for (size_t c = 0; c < 3; ++c) {
            result[c] += coefficients[k][c] * basis[k];
        }
    }
    return result;
}

SH9 environmentIrradiance(EnvironmentPreset preset)
{
    const EnvironmentDescription env = environmentDescription(preset);
    return irradianceFromRadiance(projectRadiance([&env](const Direction& d) {
        return environmentRadiance(env, d);
    }));
}

PbrMaterial phongToPbr(const Rgb& diffuseIn, const Rgb& specularIn, float glShininess)
{
    PbrMaterial result;
    const float shininess = std::max(glShininess, 0.0F);
    result.alpha = std::clamp(std::sqrt(2.0F / (shininess + 2.0F)), 0.045F, 1.0F);
    result.roughness = std::sqrt(result.alpha);

    const float specularStrength = std::max({specularIn[0], specularIn[1], specularIn[2]});
    const float oneMinus = 1.0F - specularStrength;
    const float solved = solveMetallic(perceived(diffuseIn), perceived(specularIn), oneMinus);
    Rgb solvedBase;
    for (int i = 0; i < 3; ++i) {
        const float fromDiffuse = diffuseIn[i]
            * (oneMinus / (1.0F - dielectricF0) / std::max(1.0F - solved, 1e-4F));
        const float fromSpecular = (specularIn[i] - dielectricF0 * (1.0F - solved))
            / std::max(solved, 1e-4F);
        solvedBase[i] = std::clamp(mix(fromDiffuse, fromSpecular, solved * solved), 0.0F, 1.0F);
    }
    // Keep part of the diffuse hue (classic metal presets put it there).
    const float diffuseMax = std::max({diffuseIn[0], diffuseIn[1], diffuseIn[2]});
    for (int i = 0; i < 3; ++i) {
        const float hue = diffuseMax > 1e-3F ? diffuseIn[i] / diffuseMax : 1.0F;
        solvedBase[i] = mix(solvedBase[i], solvedBase[i] * hue, metalTint);
    }
    // Only a strong specular colour (above the default 0.5333 grey) on a not ultra glossy material
    // reads as metal: a part coloured black with the default specular, or the Shiny plastic
    // preset, stays a plastic.
    const float specularGate = smoothstep(metalSpecularLow, metalSpecularHigh, specularStrength);
    const float glossGate = 1.0F - smoothstep(metalGlossLow, metalGlossHigh, shininess);
    result.metallic = smoothstep(metalLow, metalHigh, solved) * specularGate * glossGate;
    // Classic metal presets use a low shininess to get a broad highlight; polish them a bit.
    result.alpha = std::max(result.alpha * mix(1.0F, metalRoughnessScale, result.metallic), 0.045F);
    result.roughness = std::sqrt(result.alpha);
    result.baseColor = mix(diffuseIn, solvedBase, result.metallic);
    // Fade on the Phong specular in display units (the shader reads gl_FrontMaterial directly).
    Rgb specularDisplay;
    for (int i = 0; i < 3; ++i) {
        specularDisplay[i] = std::pow(std::max(specularIn[i], 0.0F), 1.0F / 2.2F);
    }
    result.specularWeight
        = mix(std::min(1.0F, perceived(specularDisplay) / specularFade), 1.0F, result.metallic);
    return result;
}

Rgb toLinear(const Rgb& displayColor)
{
    Rgb result;
    for (int i = 0; i < 3; ++i) {
        result[i] = std::pow(std::max(displayColor[i], 0.0F), 2.2F);
    }
    return result;
}

}  // namespace Gui::Render

// NOLINTEND(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)
