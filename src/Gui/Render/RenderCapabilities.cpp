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
#include <array>
#include <cctype>

#include <QOpenGLContext>
#include <QOpenGLFunctions>

#include "RenderCapabilities.h"

#ifndef GL_SHADING_LANGUAGE_VERSION
# define GL_SHADING_LANGUAGE_VERSION 0x8B8C
#endif

namespace Gui::Render
{

namespace
{

bool isDigit(char c)
{
    return std::isdigit(static_cast<unsigned char>(c)) != 0;
}

/// Find the first "<digits>.<digits>" in text. Returns false if there is none.
bool findVersionNumber(std::string_view text, std::string_view& major, std::string_view& minor)
{
    for (size_t i = 0; i < text.size(); ++i) {
        if (!isDigit(text[i])) {
            continue;
        }
        // Only start at the beginning of a number.
        if (i > 0 && (isDigit(text[i - 1]) || text[i - 1] == '.')) {
            continue;
        }
        size_t j = i;
        while (j < text.size() && isDigit(text[j])) {
            ++j;
        }
        if (j + 1 < text.size() && text[j] == '.' && isDigit(text[j + 1])) {
            size_t k = j + 1;
            while (k < text.size() && isDigit(text[k])) {
                ++k;
            }
            major = text.substr(i, j - i);
            minor = text.substr(j + 1, k - j - 1);
            return true;
        }
        i = j;
    }
    return false;
}

int toInt(std::string_view digits)
{
    int value = 0;
    for (char c : digits) {
        value = value * 10 + (c - '0');
        if (value > 100000) {
            break;
        }
    }
    return value;
}

std::string toLower(std::string_view text)
{
    std::string result(text);
    std::transform(result.begin(), result.end(), result.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return result;
}

struct DenylistEntry
{
    const char* pattern;  // lower case substring of GL_RENDERER
    const char* reason;
};

// Keep this table short and documented: every entry removes the option for real users.
// llvmpipe is deliberately not listed: it runs the shaders correctly (CI uses it).
constexpr std::array<DenylistEntry, 6> denylist {{
    {"gdi generic", "Windows software OpenGL 1.1 (GDI Generic)"},
    {"microsoft basic render", "Microsoft Basic Render Driver"},
    {"svga3d", "VMware SVGA3D virtual GPU"},
    {"softpipe", "Mesa softpipe software rasterizer"},
    {"software rasterizer", "software rasterizer"},
    {"apple software renderer", "Apple software renderer"},
}};

}  // namespace

GLVersion parseGLVersion(std::string_view text)
{
    std::string_view major;
    std::string_view minor;
    if (!findVersionNumber(text, major, minor)) {
        return {};
    }
    // GL_VERSION minors are single digits; keep only the first one ("4.60" -> 4.6).
    return {toInt(major), toInt(minor.substr(0, 1))};
}

int parseGLSLVersion(std::string_view text)
{
    std::string_view major;
    std::string_view minor;
    if (!findVersionNumber(text, major, minor)) {
        return 0;
    }
    int minorValue = toInt(minor.substr(0, std::min<size_t>(2, minor.size())));
    if (minor.size() == 1) {
        minorValue *= 10;  // "3.3" means 330
    }
    return toInt(major) * 100 + minorValue;
}

std::string denylistReason(const GLContextInfo& info)
{
    const std::string renderer = toLower(info.renderer);
    for (const auto& entry : denylist) {
        if (renderer.find(entry.pattern) != std::string::npos) {
            return entry.reason;
        }
    }
    return {};
}

CapabilityReport evaluateCapabilities(const GLContextInfo& info)
{
    CapabilityReport report;
    if (info.version.empty()) {
        report.reason = "no OpenGL context";
        return report;
    }
    if (info.isOpenGLES) {
        report.reason = "OpenGL ES context (desktop GLSL 1.20 required)";
        return report;
    }
    const GLVersion version = parseGLVersion(info.version);
    if (!version.atLeast(2, 0)) {
        report.reason = "OpenGL 2.0 or newer required, context reports '" + info.version + "'";
        return report;
    }
    const int glsl = parseGLSLVersion(info.glslVersion);
    if (glsl < minimumGLSLVersion) {
        report.reason = "GLSL 1.20 or newer required, context reports '" + info.glslVersion + "'";
        return report;
    }
    std::string denied = denylistReason(info);
    if (!denied.empty()) {
        report.reason = "renderer on the denylist: " + denied;
        return report;
    }
    report.enhancedShading = true;
    return report;
}

GLContextInfo queryCurrentContext()
{
    GLContextInfo info;
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        return info;
    }
    QOpenGLFunctions* gl = context->functions();
    auto read = [gl](GLenum name) {
        const auto* text = reinterpret_cast<const char*>(gl->glGetString(name));
        return text ? std::string(text) : std::string();
    };
    info.version = read(GL_VERSION);
    info.renderer = read(GL_RENDERER);
    info.vendor = read(GL_VENDOR);
    info.glslVersion = read(GL_SHADING_LANGUAGE_VERSION);
    info.isOpenGLES = context->isOpenGLES();
    return info;
}

}  // namespace Gui::Render
