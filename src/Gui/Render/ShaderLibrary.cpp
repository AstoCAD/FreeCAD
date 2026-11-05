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

#include <QFile>

#include "ShaderLibrary.h"

// The resources live in FreeCADGui; make sure they are registered even when the library is
// linked statically into a test executable.
static void ensureShaderResources()
{
    static const bool registered = [] {
        Q_INIT_RESOURCE(Shaders);
        return true;
    }();
    (void)registered;
}

namespace Gui::Render
{

std::string shaderResourcePath(ShaderId id)
{
    switch (id) {
        case ShaderId::FaceShadingVertex:
            return ":/shaders/render/fc_face_shading.vert";
        case ShaderId::FaceShadingFragment:
            return ":/shaders/render/fc_face_shading.frag";
        case ShaderId::FullScreenVertex:
            return ":/shaders/render/fc_fullscreen.vert";
        case ShaderId::FxaaFragment:
            return ":/shaders/render/fc_fxaa.frag";
        case ShaderId::AmbientOcclusionFragment:
            return ":/shaders/render/fc_ssao.frag";
    }
    return {};
}

std::string shaderSource(ShaderId id)
{
    ensureShaderResources();
    QFile file(QString::fromStdString(shaderResourcePath(id)));
    if (!file.open(QIODevice::ReadOnly)) {
        return {};
    }
    const QByteArray data = file.readAll();
    return std::string(data.constData(), static_cast<size_t>(data.size()));
}

std::string injectDefines(std::string_view source, const ShaderDefines& defines)
{
    std::string block;
    for (const auto& [name, value] : defines) {
        block += "#define ";
        block += name;
        if (!value.empty()) {
            block += ' ';
            block += value;
        }
        block += '\n';
    }
    if (block.empty()) {
        return std::string(source);
    }

    // Find a "#version" directive at the start of a line (only blanks before it).
    size_t lineStart = 0;
    while (lineStart < source.size()) {
        size_t pos = lineStart;
        while (pos < source.size() && (source[pos] == ' ' || source[pos] == '\t')) {
            ++pos;
        }
        const size_t lineEnd = source.find('\n', lineStart);
        if (source.compare(pos, 8, "#version") == 0) {
            if (lineEnd == std::string_view::npos) {
                return std::string(source) + "\n" + block;
            }
            std::string result(source.substr(0, lineEnd + 1));
            result += block;
            result += source.substr(lineEnd + 1);
            return result;
        }
        if (lineEnd == std::string_view::npos) {
            break;
        }
        lineStart = lineEnd + 1;
    }
    return block + std::string(source);
}

std::string buildShaderSource(ShaderId id, const ShaderDefines& defines)
{
    const std::string source = shaderSource(id);
    if (source.empty()) {
        return {};
    }
    return injectDefines(source, defines);
}

}  // namespace Gui::Render
