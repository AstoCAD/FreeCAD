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
#include <atomic>
#include <cctype>
#include <cstdlib>
#include <mutex>
#include <string_view>

#include <Inventor/SoPath.h>
#include <Inventor/actions/SoSearchAction.h>
#include <Inventor/lists/SoPathList.h>
#include <Inventor/nodes/SoSeparator.h>

#include <App/Application.h>
#include <Base/Console.h>
#include <Base/Parameter.h>

#include "RenderSettings.h"

namespace Gui::Render
{

namespace
{

std::atomic<Quality> requested {defaultQuality};
std::atomic<EnvironmentPreset> environment {defaultEnvironmentPreset};
std::atomic<bool> sessionFallback {false};
std::atomic<unsigned> settingsGeneration {1};
std::atomic<bool> shadows {false};
std::atomic<bool> shadowsFallback {false};
std::atomic<bool> fxaa {true};
std::atomic<bool> fxaaFallback {false};
std::atomic<bool> ambientOcclusion {false};
std::atomic<bool> ambientOcclusionFallback {false};
std::atomic<int> exportSupersamplingFactor {1};
std::atomic<KeyLight> keyLightSetting {defaultKeyLight};
std::atomic<int> classicOverride {0};

std::mutex& reasonMutex()
{
    static std::mutex mutex;
    return mutex;
}

std::string& reasonStorage()
{
    static std::string reason;
    return reason;
}

std::string& shadowReasonStorage()
{
    static std::string reason;
    return reason;
}

}  // namespace

Quality qualityFromParameter(long value)
{
    switch (value) {
        case static_cast<long>(Quality::Enhanced):
            return Quality::Enhanced;
        case static_cast<long>(Quality::Classic):
        default:
            return Quality::Classic;
    }
}

long parameterFromQuality(Quality quality)
{
    return static_cast<long>(quality);
}

EnvironmentPreset environmentFromParameter(long value)
{
    switch (value) {
        case static_cast<long>(EnvironmentPreset::Studio):
            return EnvironmentPreset::Studio;
        case static_cast<long>(EnvironmentPreset::Neutral):
            return EnvironmentPreset::Neutral;
        case static_cast<long>(EnvironmentPreset::Interior):
            return EnvironmentPreset::Interior;
        default:
            return defaultEnvironmentPreset;
    }
}

KeyLight keyLightFromParameter(long value)
{
    switch (value) {
        case static_cast<long>(KeyLight::Headlight):
            return KeyLight::Headlight;
        case static_cast<long>(KeyLight::Sun):
            return KeyLight::Sun;
        default:
            return defaultKeyLight;
    }
}

int sunKeyLightIndex(KeyLight mode, int headlightIndex, int registeredLights, int glLights)
{
    if (mode != KeyLight::Sun || headlightIndex < 0 || registeredLights != glLights
        || headlightIndex >= glLights) {
        return -1;
    }
    return headlightIndex;
}

bool environmentForcesClassic(const char* value)
{
    if (!value) {
        return false;
    }
    std::string text(value);
    // Trim surrounding blanks.
    const auto notBlank = [](unsigned char c) {
        return std::isspace(c) == 0;
    };
    text.erase(text.begin(), std::find_if(text.begin(), text.end(), notBlank));
    text.erase(std::find_if(text.rbegin(), text.rend(), notBlank).base(), text.end());
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return !(text.empty() || text == "0" || text == "false" || text == "no" || text == "off");
}

Quality resolveQuality(Quality requestedQuality, bool forcedClassic, bool fallback)
{
    if (forcedClassic || fallback) {
        return Quality::Classic;
    }
    return requestedQuality;
}

unsigned visibleRenderState(
    Quality effective,
    EnvironmentPreset preset,
    bool shadowsOn,
    bool fxaaOn,
    bool aoOn,
    KeyLight keyLightMode
)
{
    if (effective != Quality::Enhanced) {
        return 0U;
    }
    return visibleStateEnhancedBit | (static_cast<unsigned>(preset) & 0x3U) << 1U
        | (shadowsOn ? 1U << 3U : 0U) | (fxaaOn ? 1U << 4U : 0U) | (aoOn ? 1U << 5U : 0U)
        | (keyLightMode == KeyLight::Sun ? 1U << 6U : 0U);
}

void RenderSettings::loadFromParameters()
{
    ParameterGrp::handle group = App::GetApplication().GetParameterGroupByPath(parameterPath);
    setRequestedQuality(qualityFromParameter(group->GetInt(qualityKey, parameterFromQuality(defaultQuality))));
    setEnvironmentPreset(environmentFromParameter(
        group->GetInt(environmentKey, static_cast<long>(defaultEnvironmentPreset))
    ));
    setShadowsEnabled(group->GetBool(shadowsKey, false));
    setFxaaEnabled(group->GetBool(fxaaKey, true));
    setAmbientOcclusionEnabled(group->GetBool(ambientOcclusionKey, false));
    setExportSupersampling(int(group->GetInt(exportSupersamplingKey, 1)));
    setKeyLight(keyLightFromParameter(group->GetInt(keyLightKey, static_cast<long>(defaultKeyLight))));
}

void RenderSettings::setRequestedQuality(Quality quality)
{
    if (requested.exchange(quality) != quality) {
        ++settingsGeneration;
    }
}

Quality RenderSettings::requestedQuality()
{
    return requested.load();
}

void RenderSettings::setEnvironmentPreset(EnvironmentPreset preset)
{
    if (environment.exchange(preset) != preset) {
        ++settingsGeneration;
    }
}

EnvironmentPreset RenderSettings::environmentPreset()
{
    return environment.load();
}

Quality RenderSettings::effectiveQuality()
{
    const Quality quality = requested.load(std::memory_order_relaxed);
    if (quality == Quality::Classic) {
        return Quality::Classic;  // fast path: nothing else to look at
    }
    if (classicOverride.load(std::memory_order_relaxed) > 0) {
        return Quality::Classic;
    }
    return resolveQuality(quality, isForcedClassicByEnvironment(), sessionFallback.load());
}

void RenderSettings::pushClassicOverride()
{
    ++classicOverride;
}

void RenderSettings::popClassicOverride()
{
    --classicOverride;
}

bool RenderSettings::isForcedClassicByEnvironment()
{
    static const bool forced = environmentForcesClassic(std::getenv(classicEnvironmentVariable));
    return forced;
}

void RenderSettings::disableForSession(const std::string& reason)
{
    {
        std::lock_guard<std::mutex> lock(reasonMutex());
        if (sessionFallback.load()) {
            return;
        }
        reasonStorage() = reason;
        sessionFallback = true;
        ++settingsGeneration;
    }
    Base::Console().warning("Enhanced rendering disabled, using Classic: {}\n", reason);
}

bool RenderSettings::isDisabledForSession()
{
    return sessionFallback.load();
}

std::string RenderSettings::fallbackReason()
{
    std::lock_guard<std::mutex> lock(reasonMutex());
    return reasonStorage();
}

std::string RenderSettings::statusText()
{
    if (requestedQuality() == Quality::Classic) {
        return {};
    }
    if (isForcedClassicByEnvironment()) {
        return std::string("Classic is forced by the ") + classicEnvironmentVariable
            + " environment variable.";
    }
    if (isDisabledForSession()) {
        return "Not available on this system: " + fallbackReason();
    }
    if (shadowsEnabled() && areShadowsDisabledForSession()) {
        std::lock_guard<std::mutex> lock(reasonMutex());
        return "Shadows are not available on this system: " + shadowReasonStorage();
    }
    return {};
}

void RenderSettings::setShadowsEnabled(bool on)
{
    if (shadows.exchange(on) != on) {
        ++settingsGeneration;
    }
}

bool RenderSettings::shadowsEnabled()
{
    return shadows.load();
}

bool RenderSettings::shadowsActive()
{
    return shadows.load(std::memory_order_relaxed) && !shadowsFallback.load() && isEnhancedActive();
}

void RenderSettings::disableShadowsForSession(const std::string& reason)
{
    {
        std::lock_guard<std::mutex> lock(reasonMutex());
        if (shadowsFallback.load()) {
            return;
        }
        shadowReasonStorage() = reason;
        shadowsFallback = true;
        ++settingsGeneration;
    }
    Base::Console().warning("Enhanced rendering: shadows disabled: {}\n", reason);
}

bool RenderSettings::areShadowsDisabledForSession()
{
    return shadowsFallback.load();
}

void RenderSettings::setFxaaEnabled(bool on)
{
    if (fxaa.exchange(on) != on) {
        ++settingsGeneration;
    }
}

bool RenderSettings::fxaaEnabled()
{
    return fxaa.load();
}

bool RenderSettings::fxaaActive()
{
    return fxaa.load(std::memory_order_relaxed) && !fxaaFallback.load() && isEnhancedActive();
}

void RenderSettings::disableFxaaForSession(const std::string& reason)
{
    if (fxaaFallback.exchange(true)) {
        return;
    }
    ++settingsGeneration;
    Base::Console().warning("Enhanced rendering: FXAA disabled: {}\n", reason);
}

void RenderSettings::setAmbientOcclusionEnabled(bool on)
{
    if (ambientOcclusion.exchange(on) != on) {
        ++settingsGeneration;
    }
}

bool RenderSettings::ambientOcclusionEnabled()
{
    return ambientOcclusion.load();
}

bool RenderSettings::ambientOcclusionActive()
{
    return ambientOcclusion.load(std::memory_order_relaxed) && !ambientOcclusionFallback.load()
        && isEnhancedActive();
}

void RenderSettings::disableAmbientOcclusionForSession(const std::string& reason)
{
    if (ambientOcclusionFallback.exchange(true)) {
        return;
    }
    ++settingsGeneration;
    Base::Console().warning("Enhanced rendering: ambient occlusion disabled: {}\n", reason);
}

bool RenderSettings::isAmbientOcclusionDisabledForSession()
{
    return ambientOcclusionFallback.load();
}

void RenderSettings::setExportSupersampling(int factor)
{
    exportSupersamplingFactor = std::clamp(factor, 1, 4);
}

int RenderSettings::exportSupersampling()
{
    return exportSupersamplingFactor.load();
}

void RenderSettings::setKeyLight(KeyLight mode)
{
    if (keyLightSetting.exchange(mode) != mode) {
        ++settingsGeneration;
    }
}

KeyLight RenderSettings::keyLight()
{
    return keyLightSetting.load();
}

unsigned RenderSettings::generation()
{
    return settingsGeneration.load();
}

unsigned RenderSettings::visibleState()
{
    return visibleRenderState(
        effectiveQuality(),
        environmentPreset(),
        shadowsActive(),
        fxaaActive(),
        ambientOcclusionActive(),
        keyLight()
    );
}

void RenderSettings::clearSessionFallbackForTest()
{
    std::lock_guard<std::mutex> lock(reasonMutex());
    reasonStorage().clear();
    shadowReasonStorage().clear();
    sessionFallback = false;
    shadowsFallback = false;
    fxaaFallback = false;
    ambientOcclusionFallback = false;
    ++settingsGeneration;
}

int fitExportSupersampling(int requested, int width, int height, int maxSide)
{
    const int limit = maxSide > 0 ? std::min(maxSide, maxSupersampledSide) : maxSupersampledSide;
    int factor = std::clamp(requested, 1, 4);
    while (factor > 1) {
        const long long w = static_cast<long long>(width) * factor;
        const long long h = static_cast<long long>(height) * factor;
        if (w <= limit && h <= limit && w * h <= maxSupersampledPixels) {
            break;
        }
        --factor;
    }
    return factor;
}

void invalidateRenderCaches(SoNode* root)
{
    if (!root) {
        return;
    }
    SoSearchAction search;
    search.setType(SoSeparator::getClassTypeId(), TRUE);
    search.setInterest(SoSearchAction::ALL);
    search.setSearchingAll(TRUE);
    search.apply(root);
    const SoPathList& paths = search.getPaths();
    for (int i = 0; i < paths.getLength(); ++i) {
        paths[i]->getTail()->touch();
    }
    root->touch();
}

}  // namespace Gui::Render
