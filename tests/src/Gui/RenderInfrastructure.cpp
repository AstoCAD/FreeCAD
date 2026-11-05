// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <iterator>
#include <string>

#include <Gui/Render/RenderCapabilities.h>
#include <Gui/Render/RenderSettings.h>
#include <Gui/Render/ShaderLibrary.h>

using namespace Gui::Render;

namespace
{

GLContextInfo makeInfo(const char* version, const char* renderer, const char* glsl)
{
    GLContextInfo info;
    info.version = version;
    info.renderer = renderer;
    info.vendor = "test";
    info.glslVersion = glsl;
    return info;
}

/// Restores the process-wide render settings after each test.
class RenderSettingsTest: public ::testing::Test
{
protected:
    void TearDown() override
    {
        RenderSettings::clearSessionFallbackForTest();
        RenderSettings::setRequestedQuality(defaultQuality);
        RenderSettings::setEnvironmentPreset(defaultEnvironmentPreset);
        RenderSettings::setShadowsEnabled(false);
    }
};

}  // namespace

// --- capability parsing ------------------------------------------------------------------------

TEST(RenderCapabilities, parsesGLVersionStrings)
{
    EXPECT_EQ(parseGLVersion("4.6.0 NVIDIA 560.94").major, 4);
    EXPECT_EQ(parseGLVersion("4.6.0 NVIDIA 560.94").minor, 6);
    EXPECT_EQ(parseGLVersion("2.1 Metal - 88").major, 2);
    EXPECT_EQ(parseGLVersion("2.1 Metal - 88").minor, 1);
    EXPECT_EQ(parseGLVersion("4.5 (Compatibility Profile) Mesa 24.0.5").minor, 5);
    EXPECT_EQ(parseGLVersion("OpenGL ES 3.2 Mesa 23.1").major, 3);
    EXPECT_EQ(parseGLVersion("1.1.0").major, 1);
    EXPECT_EQ(parseGLVersion("").major, 0);
    EXPECT_EQ(parseGLVersion("no numbers").major, 0);
}

TEST(RenderCapabilities, parsesGLSLVersionStrings)
{
    EXPECT_EQ(parseGLSLVersion("1.20"), 120);
    EXPECT_EQ(parseGLSLVersion("4.60 NVIDIA"), 460);
    EXPECT_EQ(parseGLSLVersion("4.50 - Build 31.0.101.5186"), 450);
    EXPECT_EQ(parseGLSLVersion("OpenGL ES GLSL ES 3.00"), 300);
    EXPECT_EQ(parseGLSLVersion("3.3"), 330);
    EXPECT_EQ(parseGLSLVersion(""), 0);
}

TEST(RenderCapabilities, acceptsCommonDesktopContexts)
{
    EXPECT_TRUE(evaluateCapabilities(makeInfo("4.6.0 NVIDIA 560.94", "NVIDIA GeForce RTX 3060/PCIe/SSE2", "4.60 NVIDIA")).enhancedShading);
    EXPECT_TRUE(evaluateCapabilities(makeInfo("2.1 Metal - 88", "Apple M1", "1.20")).enhancedShading);
    // llvmpipe is slow but correct; CI renders with it.
    EXPECT_TRUE(evaluateCapabilities(makeInfo("4.5 (Compatibility Profile) Mesa 24.0.5", "llvmpipe (LLVM 17.0.6, 256 bits)", "4.50")).enhancedShading);
}

TEST(RenderCapabilities, rejectsOldOrSoftwareContexts)
{
    const auto gdi = evaluateCapabilities(makeInfo("1.1.0", "GDI Generic", ""));
    EXPECT_FALSE(gdi.enhancedShading);
    EXPECT_FALSE(gdi.reason.empty());

    EXPECT_FALSE(evaluateCapabilities(makeInfo("2.0", "Old card", "1.10")).enhancedShading);
    EXPECT_FALSE(evaluateCapabilities(makeInfo("3.3 (Compatibility Profile) Mesa", "SVGA3D; build: RELEASE;", "3.30")).enhancedShading);
    EXPECT_FALSE(evaluateCapabilities(makeInfo("4.5 Mesa", "softpipe", "4.50")).enhancedShading);
    EXPECT_FALSE(evaluateCapabilities(makeInfo("3.3", "Microsoft Basic Render Driver", "3.30")).enhancedShading);
    EXPECT_FALSE(evaluateCapabilities(GLContextInfo {}).enhancedShading);

    GLContextInfo es = makeInfo("OpenGL ES 3.2 Mesa", "Mali-G78", "OpenGL ES GLSL ES 3.20");
    es.isOpenGLES = true;
    EXPECT_FALSE(evaluateCapabilities(es).enhancedShading);
}

TEST(RenderCapabilities, denylistIsCaseInsensitive)
{
    EXPECT_FALSE(denylistReason(makeInfo("1.1.0", "gdi GENERIC", "")).empty());
    EXPECT_TRUE(denylistReason(makeInfo("4.6", "AMD Radeon RX 6800", "4.60")).empty());
}

// --- preference mapping ------------------------------------------------------------------------

TEST(RenderSettingsMapping, qualityParameters)
{
    EXPECT_EQ(qualityFromParameter(0), Quality::Classic);
    EXPECT_EQ(qualityFromParameter(1), Quality::Enhanced);
    EXPECT_EQ(qualityFromParameter(-1), Quality::Classic);
    EXPECT_EQ(qualityFromParameter(42), Quality::Classic);
    EXPECT_EQ(parameterFromQuality(Quality::Enhanced), 1);
    EXPECT_EQ(qualityFromParameter(parameterFromQuality(Quality::Classic)), Quality::Classic);
    EXPECT_EQ(defaultQuality, Quality::Classic);
}

TEST(RenderSettingsMapping, environmentParameters)
{
    EXPECT_EQ(environmentFromParameter(0), EnvironmentPreset::Studio);
    EXPECT_EQ(environmentFromParameter(1), EnvironmentPreset::Neutral);
    EXPECT_EQ(environmentFromParameter(2), EnvironmentPreset::Interior);
    EXPECT_EQ(environmentFromParameter(7), defaultEnvironmentPreset);
}

TEST(RenderSettingsMapping, classicEnvironmentVariable)
{
    EXPECT_FALSE(environmentForcesClassic(nullptr));
    EXPECT_FALSE(environmentForcesClassic(""));
    EXPECT_FALSE(environmentForcesClassic("0"));
    EXPECT_FALSE(environmentForcesClassic(" off "));
    EXPECT_FALSE(environmentForcesClassic("FALSE"));
    EXPECT_FALSE(environmentForcesClassic("no"));
    EXPECT_TRUE(environmentForcesClassic("1"));
    EXPECT_TRUE(environmentForcesClassic("yes"));
    EXPECT_TRUE(environmentForcesClassic("TRUE"));
}

TEST(RenderSettingsMapping, resolveQuality)
{
    EXPECT_EQ(resolveQuality(Quality::Enhanced, false, false), Quality::Enhanced);
    EXPECT_EQ(resolveQuality(Quality::Enhanced, true, false), Quality::Classic);
    EXPECT_EQ(resolveQuality(Quality::Enhanced, false, true), Quality::Classic);
    EXPECT_EQ(resolveQuality(Quality::Classic, false, false), Quality::Classic);
}

TEST(RenderSettingsMapping, visibleStateIgnoresEnhancedOptionsInClassic)
{
    const auto classic = [](EnvironmentPreset preset, bool shadows, bool fxaa, bool ao) {
        return visibleRenderState(Quality::Classic, preset, shadows, fxaa, ao);
    };
    EXPECT_EQ(classic(EnvironmentPreset::Studio, false, true, false), 0U);
    EXPECT_EQ(classic(EnvironmentPreset::Interior, true, false, true), 0U);
}

TEST(RenderSettingsMapping, visibleStateSeparatesEveryEnhancedOption)
{
    const unsigned base = visibleRenderState(Quality::Enhanced, EnvironmentPreset::Studio, false, false, false);
    EXPECT_NE(base & visibleStateEnhancedBit, 0U);
    const unsigned variants[] = {
        visibleRenderState(Quality::Enhanced, EnvironmentPreset::Neutral, false, false, false),
        visibleRenderState(Quality::Enhanced, EnvironmentPreset::Interior, false, false, false),
        visibleRenderState(Quality::Enhanced, EnvironmentPreset::Studio, true, false, false),
        visibleRenderState(Quality::Enhanced, EnvironmentPreset::Studio, false, true, false),
        visibleRenderState(Quality::Enhanced, EnvironmentPreset::Studio, false, false, true),
    };
    for (unsigned variant : variants) {
        EXPECT_NE(variant, base);
        // A feature change keeps the quality bit: only a redraw is needed, not a cache flush.
        EXPECT_EQ((variant ^ base) & visibleStateEnhancedBit, 0U);
    }
    for (size_t i = 0; i < std::size(variants); ++i) {
        for (size_t j = i + 1; j < std::size(variants); ++j) {
            EXPECT_NE(variants[i], variants[j]);
        }
    }
}

TEST_F(RenderSettingsTest, visibleStateFollowsTheSettings)
{
    RenderSettings::setRequestedQuality(Quality::Classic);
    RenderSettings::setShadowsEnabled(true);
    EXPECT_EQ(RenderSettings::visibleState(), 0U);
    RenderSettings::setShadowsEnabled(false);
    RenderSettings::setRequestedQuality(Quality::Enhanced);
    if (RenderSettings::isForcedClassicByEnvironment()) {
        EXPECT_EQ(RenderSettings::visibleState(), 0U);
        return;
    }
    const unsigned enhanced = RenderSettings::visibleState();
    EXPECT_NE(enhanced & visibleStateEnhancedBit, 0U);
    RenderSettings::setShadowsEnabled(true);
    EXPECT_NE(RenderSettings::visibleState(), enhanced);
    RenderSettings::setShadowsEnabled(false);
    EXPECT_EQ(RenderSettings::visibleState(), enhanced);
}

TEST(RenderSettingsMapping, exportSupersamplingFitsTheTarget)
{
    EXPECT_EQ(fitExportSupersampling(1, 1920, 1080, 16384), 1);
    EXPECT_EQ(fitExportSupersampling(2, 1920, 1080, 16384), 2);
    EXPECT_EQ(fitExportSupersampling(4, 1920, 1080, 16384), 4);  // 7680 x 4320, just below 32 Mi
    EXPECT_EQ(fitExportSupersampling(4, 2560, 1440, 16384), 3);  // x4 is wider than 8192
    EXPECT_EQ(fitExportSupersampling(3, 1000, 1000, 16384), 3);
    // 4000 x 3000 at x2 is 48 Mpixels: too much, render at the output size.
    EXPECT_EQ(fitExportSupersampling(2, 4000, 3000, 16384), 1);
    // The driver limit wins over the default side limit.
    EXPECT_EQ(fitExportSupersampling(4, 1000, 1000, 2048), 2);
    EXPECT_EQ(fitExportSupersampling(4, 1000, 1000, 0), 4);  // unknown limit: default side limit
    EXPECT_EQ(fitExportSupersampling(9, 100, 100, 0), 4);
    EXPECT_EQ(fitExportSupersampling(0, 100, 100, 0), 1);
}

TEST_F(RenderSettingsTest, scopedClassicRenderingOverridesEnhanced)
{
    RenderSettings::setRequestedQuality(Quality::Enhanced);
    const bool enhanced = RenderSettings::isEnhancedActive();  // false if FC_RENDER_CLASSIC is set
    {
        const ScopedClassicRendering outer;
        EXPECT_FALSE(RenderSettings::isEnhancedActive());
        {
            const ScopedClassicRendering inner;
            EXPECT_FALSE(RenderSettings::isEnhancedActive());
        }
        EXPECT_FALSE(RenderSettings::isEnhancedActive());
        EXPECT_EQ(RenderSettings::requestedQuality(), Quality::Enhanced);
    }
    EXPECT_EQ(RenderSettings::isEnhancedActive(), enhanced);
}

TEST_F(RenderSettingsTest, classicByDefault)
{
    EXPECT_EQ(RenderSettings::requestedQuality(), Quality::Classic);
    EXPECT_FALSE(RenderSettings::isEnhancedActive());
    EXPECT_TRUE(RenderSettings::statusText().empty());
}

TEST_F(RenderSettingsTest, sessionFallbackForcesClassic)
{
    RenderSettings::setRequestedQuality(Quality::Enhanced);
    if (RenderSettings::isForcedClassicByEnvironment()) {
        EXPECT_FALSE(RenderSettings::isEnhancedActive());
        EXPECT_FALSE(RenderSettings::statusText().empty());
        return;
    }
    EXPECT_TRUE(RenderSettings::isEnhancedActive());
    const unsigned generation = RenderSettings::generation();

    RenderSettings::disableForSession("test failure");
    EXPECT_FALSE(RenderSettings::isEnhancedActive());
    EXPECT_EQ(RenderSettings::fallbackReason(), "test failure");
    EXPECT_NE(RenderSettings::statusText().find("test failure"), std::string::npos);
    EXPECT_NE(RenderSettings::generation(), generation);

    // Only the first reason is kept.
    RenderSettings::disableForSession("second failure");
    EXPECT_EQ(RenderSettings::fallbackReason(), "test failure");

    RenderSettings::clearSessionFallbackForTest();
    EXPECT_TRUE(RenderSettings::isEnhancedActive());
}

TEST_F(RenderSettingsTest, changesBumpTheGeneration)
{
    const unsigned generation = RenderSettings::generation();
    RenderSettings::setRequestedQuality(Quality::Classic);  // unchanged
    EXPECT_EQ(RenderSettings::generation(), generation);
    RenderSettings::setEnvironmentPreset(EnvironmentPreset::Interior);
    EXPECT_NE(RenderSettings::generation(), generation);
}

// --- shader library ----------------------------------------------------------------------------

TEST(ShaderLibrary, injectsDefinesAfterTheVersionLine)
{
    const std::string source = "#version 120\nvoid main() {}\n";
    EXPECT_EQ(
        injectDefines(source, {{"FC_MAX_LIGHTS", "8"}, {"FC_FLAG", ""}}),
        "#version 120\n#define FC_MAX_LIGHTS 8\n#define FC_FLAG\nvoid main() {}\n"
    );
}

TEST(ShaderLibrary, injectsDefinesAfterAnIndentedVersionBelowComments)
{
    const std::string source = "// comment\n  #version 120\nvoid main() {}\n";
    EXPECT_EQ(
        injectDefines(source, {{"A", "1"}}),
        "// comment\n  #version 120\n#define A 1\nvoid main() {}\n"
    );
}

TEST(ShaderLibrary, injectsDefinesAtTheTopWithoutVersion)
{
    EXPECT_EQ(injectDefines("void main() {}\n", {{"A", "1"}}), "#define A 1\nvoid main() {}\n");
    EXPECT_EQ(injectDefines("#version 120", {{"A", "1"}}), "#version 120\n#define A 1\n");
    EXPECT_EQ(injectDefines("void main() {}\n", {}), "void main() {}\n");
}

TEST(ShaderLibrary, faceShadersAreGLSL120)
{
    for (ShaderId id : {ShaderId::FaceShadingVertex, ShaderId::FaceShadingFragment}) {
        const std::string source = shaderSource(id);
        ASSERT_FALSE(source.empty()) << shaderResourcePath(id);
        EXPECT_EQ(source.rfind("#version 120", 0), 0U) << shaderResourcePath(id);
        // Clip planes must keep working.
        if (id == ShaderId::FaceShadingVertex) {
            EXPECT_NE(source.find("gl_ClipVertex"), std::string::npos);
            EXPECT_NE(source.find("ftransform()"), std::string::npos);
        }
    }
}
