// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <cmath>

#include <Gui/Render/ShadowMath.h>

using namespace Gui::Render;

namespace
{

void expectInsideClip(const LightFrustum& frustum, const Vec3& p)
{
    const Vec3 c = toLightClip(frustum, p);
    for (int i = 0; i < 3; ++i) {
        // The nearest corner lies exactly on the near plane: allow rounding.
        EXPECT_GE(c[i], -1.0001F) << "axis " << i;
        EXPECT_LE(c[i], 1.0001F) << "axis " << i;
    }
}

}  // namespace

TEST(RenderShadowMath, sunIsAboveWithASlightAngle)
{
    const Vec3 sun = defaultSunDirection();
    EXPECT_NEAR(std::sqrt(sun[0] * sun[0] + sun[1] * sun[1] + sun[2] * sun[2]), 1.0F, 1e-5F);
    EXPECT_GT(sun[2], 0.8F);  // from above (+Z up)
    EXPECT_GT(std::fabs(sun[0]) + std::fabs(sun[1]), 0.1F);  // not straight down
}

TEST(RenderShadowMath, frustumContainsTheBox)
{
    const Vec3 boxMin {-10.0F, -4.0F, 0.0F};
    const Vec3 boxMax {30.0F, 6.0F, 12.0F};
    for (const Vec3& light : {defaultSunDirection(), Vec3 {0, 0, 1}, Vec3 {1, 0, 0}, Vec3 {-1, -2, 0.5F}}) {
        const LightFrustum f = fitLightFrustum(light, boxMin, boxMax);
        ASSERT_TRUE(f.valid);
        for (int corner = 0; corner < 8; ++corner) {
            expectInsideClip(f, {
                (corner & 1) ? boxMax[0] : boxMin[0],
                (corner & 2) ? boxMax[1] : boxMin[1],
                (corner & 4) ? boxMax[2] : boxMin[2],
            });
        }
        // Orthonormal camera frame looking away from the light.
        auto dot = [](const Vec3& a, const Vec3& b) {
            return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
        };
        EXPECT_NEAR(dot(f.right, f.up), 0.0F, 1e-5F);
        EXPECT_NEAR(dot(f.right, f.back), 0.0F, 1e-5F);
        EXPECT_NEAR(dot(f.up, f.back), 0.0F, 1e-5F);
        EXPECT_NEAR(dot(f.back, f.back), 1.0F, 1e-5F);
        EXPECT_GT(f.nearDistance, 0.0F);
        EXPECT_GT(f.farDistance, f.nearDistance);
    }
}

TEST(RenderShadowMath, frustumIsTight)
{
    // Straight down onto a 2 x 2 x 1 box: the map covers about the box footprint.
    const LightFrustum f = fitLightFrustum({0, 0, 1}, {-1, -1, 0}, {1, 1, 1});
    ASSERT_TRUE(f.valid);
    EXPECT_LT(f.halfWidth, 1.2F);
    EXPECT_LT(f.halfHeight, 1.2F);
    EXPECT_LT(f.farDistance - f.nearDistance, 1.3F);
    // The top of the box is nearer to the light than the bottom.
    EXPECT_LT(toLightClip(f, {0, 0, 1})[2], toLightClip(f, {0, 0, 0})[2]);
}

TEST(RenderShadowMath, flatAndDegenerateInput)
{
    // A plate: flat box, still a usable frustum.
    EXPECT_TRUE(fitLightFrustum(defaultSunDirection(), {-5, -5, 0}, {5, 5, 0}).valid);
    // A point, an inverted box, no light direction: invalid.
    EXPECT_FALSE(fitLightFrustum(defaultSunDirection(), {1, 1, 1}, {1, 1, 1}).valid);
    EXPECT_FALSE(fitLightFrustum(defaultSunDirection(), {1, 1, 1}, {0, 0, 0}).valid);
    EXPECT_FALSE(fitLightFrustum({0, 0, 0}, {0, 0, 0}, {1, 1, 1}).valid);
    EXPECT_FALSE(fitLightFrustum({0, 0, 1}, {0, 0, NAN}, {1, 1, 1}).valid);
}

TEST(RenderShadowMath, biasScalesWithTexelsAndSlope)
{
    const float bias = shadowDepthBias(0.01F, 10.0F);
    EXPECT_NEAR(bias, 1.5F * 0.01F / 10.0F, 1e-7F);
    EXPECT_GT(shadowDepthBias(0.02F, 10.0F), bias);  // coarser map, more bias
    EXPECT_EQ(shadowDepthBias(0.01F, 0.0F), 0.0F);

    EXPECT_FLOAT_EQ(slopeScaledBias(bias, 1.0F), bias);  // facing the light
    EXPECT_GT(slopeScaledBias(bias, 0.5F), bias);        // grazing needs more
    EXPECT_LT(slopeScaledBias(bias, 0.5F), slopeScaledBias(bias, 0.2F));
    EXPECT_FLOAT_EQ(slopeScaledBias(bias, 0.0F), 10.0F * bias);  // clamped
    EXPECT_FLOAT_EQ(slopeScaledBias(bias, -1.0F), 10.0F * bias);
}

TEST(RenderShadowMath, sampleDiskCoversTheUnitDisk)
{
    const auto disk = shadowSampleDisk();
    float maxRadius = 0.0F;
    float sumX = 0.0F;
    float sumY = 0.0F;
    for (const auto& p : disk) {
        const float r = std::sqrt(p[0] * p[0] + p[1] * p[1]);
        EXPECT_LE(r, 1.0F);
        maxRadius = std::max(maxRadius, r);
        sumX += p[0];
        sumY += p[1];
    }
    EXPECT_GT(maxRadius, 0.9F);
    // Roughly centred: no directional smear of the soft shadow edge.
    EXPECT_LT(std::fabs(sumX) / float(disk.size()), 0.2F);
    EXPECT_LT(std::fabs(sumY) / float(disk.size()), 0.2F);
}
