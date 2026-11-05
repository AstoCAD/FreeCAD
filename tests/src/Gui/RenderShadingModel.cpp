// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <cmath>

#include <Gui/Render/ShadingModel.h>

using namespace Gui::Render;

namespace
{

constexpr float tolerance = 0.02F;

Direction unit(float x, float y, float z)
{
    const float length = std::sqrt(x * x + y * y + z * z);
    return {x / length, y / length, z / length};
}

Rgb grey(float value)
{
    return {value, value, value};
}

}  // namespace

// --- spherical harmonics -----------------------------------------------------------------------

TEST(RenderShadingModel, constantEnvironmentGivesConstantIrradiance)
{
    // E(n) / pi of a constant radiance c is c in every direction.
    const SH9 sh = irradianceFromRadiance(projectRadiance([](const Direction&) {
        return Rgb {0.5F, 1.0F, 2.0F};
    }));
    for (const Direction& n : {unit(0, 1, 0), unit(0, -1, 0), unit(1, 0, 0), unit(1, 1, 1)}) {
        const Rgb e = evaluateSH9(sh, n);
        EXPECT_NEAR(e[0], 0.5F, tolerance);
        EXPECT_NEAR(e[1], 1.0F, tolerance);
        EXPECT_NEAR(e[2], 2.0F, tolerance);
    }
    // Only the constant band is present.
    for (size_t k = 1; k < sh.size(); ++k) {
        EXPECT_NEAR(sh[k][1], 0.0F, 1e-3F);
    }
}

TEST(RenderShadingModel, upperHemisphereIrradiance)
{
    // Radiance 1 above the horizon, 0 below: the order-2 SH irradiance is exact at the poles
    // (1 facing up, 0 facing down) and 1/2 on the horizon.
    const SH9 sh = irradianceFromRadiance(projectRadiance([](const Direction& d) {
        return d[1] > 0.0F ? grey(1.0F) : grey(0.0F);
    }));
    EXPECT_NEAR(evaluateSH9(sh, unit(0, 1, 0))[0], 1.0F, tolerance);
    EXPECT_NEAR(evaluateSH9(sh, unit(0, -1, 0))[0], 0.0F, tolerance);
    EXPECT_NEAR(evaluateSH9(sh, unit(1, 0, 0))[0], 0.5F, tolerance);
    EXPECT_NEAR(evaluateSH9(sh, unit(0, 0, 1))[0], 0.5F, tolerance);
}

TEST(RenderShadingModel, projectionIsDeterministic)
{
    const SH9 a = environmentIrradiance(EnvironmentPreset::Studio);
    const SH9 b = environmentIrradiance(EnvironmentPreset::Studio);
    EXPECT_EQ(a, b);
}

TEST(RenderShadingModel, presetsLightFromAbove)
{
    for (EnvironmentPreset preset :
         {EnvironmentPreset::Studio, EnvironmentPreset::Neutral, EnvironmentPreset::Interior}) {
        const SH9 sh = environmentIrradiance(preset);
        const Rgb up = evaluateSH9(sh, unit(0, 1, 0));
        const Rgb down = evaluateSH9(sh, unit(0, -1, 0));
        const Rgb front = evaluateSH9(sh, unit(0, 0, 1));
        for (int c = 0; c < 3; ++c) {
            EXPECT_GE(up[c] + tolerance, down[c]);
            // Bounded, positive ambient: an albedo multiplier, not a light source.
            EXPECT_GT(front[c], 0.05F);
            EXPECT_LT(up[c], 1.5F);
        }
    }
}

TEST(RenderShadingModel, radianceMatchesTheGradient)
{
    const EnvironmentDescription env = environmentDescription(EnvironmentPreset::Neutral);
    const Rgb horizon = environmentRadiance(env, unit(1, 0, 0));
    EXPECT_NEAR(horizon[0], env.horizon[0] * env.intensity, 1e-5F);
    const EnvironmentDescription studio = environmentDescription(EnvironmentPreset::Studio);
    const Rgb key = environmentRadiance(studio, studio.lights[0].direction);
    const Rgb away = environmentRadiance(studio, unit(0, -1, 0));
    EXPECT_GT(key[0], away[0]);
    // A studio for reflections: bright horizon, dark floor.
    EXPECT_GT(environmentRadiance(studio, unit(0, 0.02F, -1))[0], 0.5F);
    EXPECT_LT(away[0], 0.1F);
}

TEST(RenderShadingModel, uniformsMatchTheDescription)
{
    for (EnvironmentPreset preset :
         {EnvironmentPreset::Studio, EnvironmentPreset::Neutral, EnvironmentPreset::Interior}) {
        const EnvironmentDescription env = environmentDescription(preset);
        const EnvironmentUniforms uniforms = environmentUniforms(preset);
        EXPECT_EQ(uniforms.irradiance, environmentIrradiance(preset));
        EXPECT_NEAR(uniforms.horizon[1], env.horizon[1] * env.intensity, 1e-6F);
        EXPECT_GT(uniforms.diffuseScale, 0.0F);
        EXPECT_LE(uniforms.diffuseScale, 1.0F);
        for (size_t i = 0; i < uniforms.lightExponent.size(); ++i) {
            EXPECT_GE(uniforms.lightExponent[i], 1.0F);
        }
    }
}

// --- Phong -> metallic / roughness --------------------------------------------------------------

TEST(RenderShadingModel, roughnessFollowsShininess)
{
    const Rgb diffuse = toLinear(grey(0.8F));
    const Rgb specular = toLinear(grey(0.5F));
    const PbrMaterial dull = phongToPbr(diffuse, specular, 0.0F);
    const PbrMaterial glossy = phongToPbr(diffuse, specular, 0.9F * 128.0F);
    EXPECT_NEAR(dull.alpha, 1.0F, 1e-5F);
    EXPECT_LT(glossy.alpha, dull.alpha);
    EXPECT_NEAR(glossy.alpha, std::sqrt(2.0F / (0.9F * 128.0F + 2.0F)), 1e-5F);
    EXPECT_NEAR(glossy.roughness, std::sqrt(glossy.alpha), 1e-6F);
}

TEST(RenderShadingModel, defaultPartMaterialStaysDielectric)
{
    // App::Material DEFAULT: diffuse (0.8, 0.8, 0.9), specular 0.5333, shininess 0.9.
    const PbrMaterial m = phongToPbr(
        toLinear({0.8F, 0.8F, 0.9F}),
        toLinear(grey(0.5333F)),
        0.9F * 128.0F
    );
    EXPECT_FLOAT_EQ(m.metallic, 0.0F);
    // The base colour is the diffuse colour, unchanged.
    const Rgb diffuse = toLinear({0.8F, 0.8F, 0.9F});
    for (int c = 0; c < 3; ++c) {
        EXPECT_NEAR(m.baseColor[c], diffuse[c], 1e-5F);
    }
    EXPECT_FLOAT_EQ(m.specularWeight, 1.0F);
}

TEST(RenderShadingModel, metalPresetsBecomeMetallic)
{
    // App::Material STEEL, GOLD and CHROME.
    const PbrMaterial steel = phongToPbr(toLinear(grey(0.0F)), toLinear(grey(0.98F)), 0.06F * 128.0F);
    const PbrMaterial gold = phongToPbr(
        toLinear({0.4F, 0.276F, 0.0F}),
        toLinear({0.9F, 0.882F, 0.702F}),
        0.0625F * 128.0F
    );
    const PbrMaterial chrome = phongToPbr(toLinear(grey(0.9176F)), toLinear(grey(0.9746F)), 0.1F * 128.0F);
    EXPECT_GT(steel.metallic, 0.95F);
    EXPECT_GT(gold.metallic, 0.9F);
    EXPECT_GT(chrome.metallic, 0.9F);
    // Steel is not black: its base colour comes from the specular colour.
    EXPECT_GT(steel.baseColor[0], 0.5F);
    // Gold keeps a warm tint.
    EXPECT_GT(gold.baseColor[0], gold.baseColor[2]);
}

TEST(RenderShadingModel, darkPlasticsStayPlastics)
{
    // A part coloured black with the default specular colour.
    const PbrMaterial blackPart = phongToPbr(toLinear(grey(0.1F)), toLinear(grey(0.5333F)), 0.9F * 128.0F);
    EXPECT_FLOAT_EQ(blackPart.metallic, 0.0F);
    EXPECT_LT(blackPart.baseColor[0], 0.02F);
    // App::Material SHINY_PLASTIC: black diffuse, white specular, shininess 1.
    const PbrMaterial shiny = phongToPbr(grey(0.0F), grey(1.0F), 128.0F);
    EXPECT_FLOAT_EQ(shiny.metallic, 0.0F);
    // App::Material PLASTIC: black with a faint specular keeps (dim) reflections.
    const PbrMaterial plastic = phongToPbr(grey(0.0F), toLinear(grey(0.06F)), 0.0078F * 128.0F);
    EXPECT_FLOAT_EQ(plastic.metallic, 0.0F);
    EXPECT_GT(plastic.specularWeight, 0.3F);
}

TEST(RenderShadingModel, metalsArePolishedABit)
{
    const float shininess = 0.06F * 128.0F;
    const PbrMaterial steel = phongToPbr(toLinear(grey(0.0F)), toLinear(grey(0.98F)), shininess);
    EXPECT_LT(steel.alpha, std::sqrt(2.0F / (shininess + 2.0F)));
}

TEST(RenderShadingModel, blackSpecularMeansNoHighlight)
{
    const PbrMaterial m = phongToPbr(toLinear(grey(0.8F)), grey(0.0F), 0.2F * 128.0F);
    EXPECT_FLOAT_EQ(m.metallic, 0.0F);
    EXPECT_FLOAT_EQ(m.specularWeight, 0.0F);
}
