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

#include <FCGlobal.h>

class SoNode;

namespace Gui::Render
{

/// Rendering quality of the 3D views.
/// Classic is the fixed-function Coin rendering, unchanged pixel for pixel.
/// Enhanced shades Part and Mesh faces with a physically based looking GLSL 1.20 shader.
enum class Quality
{
    Classic = 0,
    Enhanced = 1,
};

/// Default quality (decision D1: Classic stays the default, Enhanced is opt-in).
constexpr Quality defaultQuality = Quality::Classic;

/// Environment presets of the enhanced shading.
enum class EnvironmentPreset
{
    Studio = 0,
    Neutral = 1,
    Interior = 2,
};

constexpr EnvironmentPreset defaultEnvironmentPreset = EnvironmentPreset::Studio;

/// Map the integer stored in the preferences to a quality. Unknown values give Classic.
GuiExport Quality qualityFromParameter(long value);
GuiExport long parameterFromQuality(Quality quality);

/// Map the integer stored in the preferences to a preset. Unknown values give the default.
GuiExport EnvironmentPreset environmentFromParameter(long value);

/// True if the value of the FC_RENDER_CLASSIC environment variable asks for Classic:
/// any value except empty, "0", "false", "no" and "off" (case-insensitive).
GuiExport bool environmentForcesClassic(const char* value);

/// The quality actually used: Classic when forced by the environment or after a fallback.
GuiExport Quality resolveQuality(Quality requested, bool forcedClassic, bool sessionFallback);

/// Bit of visibleRenderState() set when the effective quality is Enhanced.
constexpr unsigned visibleStateEnhancedBit = 1U;

/// A value that changes exactly when what the 3D views show changes: 0 for Classic (whatever the
/// Enhanced-only options are), else visibleStateEnhancedBit plus the preset and the active effects.
/// The preference observer compares it to decide whether render caches must be dropped (only when
/// the effective quality changes) or a redraw is enough.
GuiExport unsigned visibleRenderState(
    Quality effective,
    EnvironmentPreset preset,
    bool shadows,
    bool fxaa,
    bool ambientOcclusion
);

/**
 * Process-wide rendering settings. All accessors are cheap, they are called for every face shape
 * that is rendered. The values are pushed in by View3DSettings (preference observer) and by the
 * application start-up, so this class never reads parameters by itself during rendering.
 */
class GuiExport RenderSettings
{
public:
    static constexpr const char* parameterPath = "User parameter:BaseApp/Preferences/View";
    static constexpr const char* qualityKey = "RenderQuality";
    static constexpr const char* environmentKey = "RenderEnvironment";
    static constexpr const char* classicEnvironmentVariable = "FC_RENDER_CLASSIC";

    /// Read RenderQuality and RenderEnvironment from the user parameters.
    static void loadFromParameters();

    static void setRequestedQuality(Quality quality);
    static Quality requestedQuality();

    static void setEnvironmentPreset(EnvironmentPreset preset);
    static EnvironmentPreset environmentPreset();

    /// The quality to use for this frame.
    static Quality effectiveQuality();
    static bool isEnhancedActive()
    {
        return effectiveQuality() == Quality::Enhanced;
    }

    /// True if FC_RENDER_CLASSIC is set (read once per process).
    static bool isForcedClassicByEnvironment();

    /// Switch to Classic for the rest of the session (capability or shader failure).
    /// The first call logs the reason once; later calls are ignored.
    static void disableForSession(const std::string& reason);
    static bool isDisabledForSession();
    static std::string fallbackReason();

    /// Text for the preference page: why Enhanced is not used although requested, or empty.
    static std::string statusText();

    /// Incremented on every change that requires shader programs to be rebuilt.
    static unsigned generation();

    /// visibleRenderState() of the current settings.
    static unsigned visibleState();

    /// Test support: forget a previous session fallback (shading and shadows).
    static void clearSessionFallbackForTest();

    static constexpr const char* shadowsKey = "RenderShadows";

    /// Soft shadows from a fixed sun, only used with the Enhanced quality (default off).
    static void setShadowsEnabled(bool on);
    static bool shadowsEnabled();
    /// Enhanced active, shadows enabled and not disabled for the session.
    static bool shadowsActive();
    /// Switch shadows off for the rest of the session (no FBO / depth texture); logs once.
    static void disableShadowsForSession(const std::string& reason);
    static bool areShadowsDisabledForSession();

    static constexpr const char* fxaaKey = "RenderFxaa";
    static constexpr const char* ambientOcclusionKey = "RenderAmbientOcclusion";
    static constexpr const char* exportSupersamplingKey = "RenderExportSupersampling";

    /// FXAA post pass (Enhanced only, default on). It only runs on framebuffers without
    /// multisampling: with MSAA on, the hardware anti-aliasing is kept as is.
    static void setFxaaEnabled(bool on);
    static bool fxaaEnabled();
    static bool fxaaActive();
    static void disableFxaaForSession(const std::string& reason);

    /// Screen-space ambient occlusion on shaded faces (Enhanced only, default off).
    static void setAmbientOcclusionEnabled(bool on);
    static bool ambientOcclusionEnabled();
    static bool ambientOcclusionActive();
    static void disableAmbientOcclusionForSession(const std::string& reason);
    static bool isAmbientOcclusionDisabledForSession();

    /// Image export supersampling factor (1 to 4, Enhanced only, default 1).
    static void setExportSupersampling(int factor);
    static int exportSupersampling();

private:
    friend class ScopedClassicRendering;
    static void pushClassicOverride();
    static void popClassicOverride();
};

/**
 * Classic for the lifetime of the object (nestable). Used around rendering that does not go
 * through a QOpenGLContext, such as Coin's own SoOffscreenRenderer: Qt's current context is then
 * stale, so the program and textures of the Enhanced passes would belong to another context.
 */
class GuiExport ScopedClassicRendering
{
public:
    ScopedClassicRendering()
    {
        RenderSettings::pushClassicOverride();
    }
    ~ScopedClassicRendering()
    {
        RenderSettings::popClassicOverride();
    }
    ScopedClassicRendering(const ScopedClassicRendering&) = delete;
    ScopedClassicRendering& operator=(const ScopedClassicRendering&) = delete;
};

/// Largest pixel count of a supersampled export target (colour and depth: about 8 bytes a pixel).
constexpr long long maxSupersampledPixels = 32LL * 1024 * 1024;
/// Largest side of a supersampled export target, whatever the driver allows.
constexpr int maxSupersampledSide = 8192;

/// The export supersampling factor to use for an output of width x height: requested (1 to 4),
/// lowered until the target fits maxSide (the driver's renderbuffer / texture limit, <= 0 if
/// unknown), maxSupersampledSide and maxSupersampledPixels. Returns 1 when nothing larger fits.
GuiExport int fitExportSupersampling(int requested, int width, int height, int maxSide);

/// Invalidate the render caches below root (touch every separator, including those below
/// switches that are off), so that a change of the rendering quality shows at the next redraw.
GuiExport void invalidateRenderCaches(SoNode* root);

}  // namespace Gui::Render
