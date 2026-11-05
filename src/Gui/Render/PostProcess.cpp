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

#include <map>
#include <memory>
#include <unordered_map>

#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QVector2D>

#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/elements/SoCacheElement.h>
#include <Inventor/system/gl.h>

#include "PassUtilities.h"
#include "PostProcess.h"
#include "RenderCapabilities.h"
#include "RenderSettings.h"

#ifndef GL_TEXTURE0
# define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ACTIVE_TEXTURE
# define GL_ACTIVE_TEXTURE 0x84E0
#endif
#ifndef GL_CURRENT_PROGRAM
# define GL_CURRENT_PROGRAM 0x8B8D
#endif
#ifndef GL_SAMPLES
# define GL_SAMPLES 0x80A9
#endif
#ifndef GL_CLAMP_TO_EDGE
# define GL_CLAMP_TO_EDGE 0x812F
#endif

using namespace Gui::Render;

SO_NODE_SOURCE(SoFCPostProcess)

namespace
{

struct ContextResources
{
    std::map<int, QOpenGLShaderProgram*> programs;  // children of the context
    GLuint copyTexture = 0;
    int copyWidth = 0;
    int copyHeight = 0;
};

std::unordered_map<QOpenGLContext*, ContextResources>& allResources()
{
    static std::unordered_map<QOpenGLContext*, ContextResources> resources;
    return resources;
}

ContextResources& resourcesFor(QOpenGLContext* context)
{
    auto& resources = allResources();
    auto it = resources.find(context);
    if (it != resources.end()) {
        return it->second;
    }
    QObject::connect(
        context,
        &QOpenGLContext::aboutToBeDestroyed,
        context,
        [context]() {
            auto& all = allResources();
            auto found = all.find(context);
            if (found == all.end()) {
                return;
            }
            // The texture belongs to the share group and would outlive the view.
            if (const GLuint texture = found->second.copyTexture) {
                Detail::runWithContextCurrent(context, [texture](QOpenGLFunctions* gl) {
                    gl->glDeleteTextures(1, &texture);
                });
            }
            for (auto& entry : found->second.programs) {
                if (entry.second) {
                    entry.second->deleteLater();
                }
            }
            all.erase(found);
        },
        Qt::DirectConnection
    );
    return resources[context];
}

}  // namespace

namespace Gui::Render
{

namespace Detail
{

QOpenGLShaderProgram* fullScreenProgram(ShaderId fragment, std::string& error)
{
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        error = "no current OpenGL context";
        return nullptr;
    }
    ContextResources& res = resourcesFor(context);
    const int key = static_cast<int>(fragment);
    auto it = res.programs.find(key);
    if (it != res.programs.end()) {
        if (!it->second) {
            error = "the shader failed to compile earlier";
        }
        return it->second;
    }
    res.programs[key] = nullptr;  // remember failures too

    const CapabilityReport report = evaluateCapabilities(queryCurrentContext());
    if (!report.enhancedShading) {
        error = report.reason;
        return nullptr;
    }
    const std::string vertex = buildShaderSource(ShaderId::FullScreenVertex, {});
    const std::string source = buildShaderSource(fragment, {});
    if (vertex.empty() || source.empty()) {
        error = "shader resources are missing";
        return nullptr;
    }
    auto program = std::make_unique<QOpenGLShaderProgram>();
    if (!program->addShaderFromSourceCode(QOpenGLShader::Vertex, vertex.c_str())
        || !program->addShaderFromSourceCode(QOpenGLShader::Fragment, source.c_str())
        || !program->link()) {
        error = shaderResourcePath(fragment) + ": " + program->log().toStdString();
        return nullptr;
    }
    program->setParent(context);
    res.programs[key] = program.get();
    return program.release();
}

void drawFullScreenQuad()
{
    glBegin(GL_QUADS);
    glTexCoord2f(0.0F, 0.0F);
    glVertex2f(-1.0F, -1.0F);
    glTexCoord2f(1.0F, 0.0F);
    glVertex2f(1.0F, -1.0F);
    glTexCoord2f(1.0F, 1.0F);
    glVertex2f(1.0F, 1.0F);
    glTexCoord2f(0.0F, 1.0F);
    glVertex2f(-1.0F, 1.0F);
    glEnd();
}

FullScreenPassState::FullScreenPassState()
{
    QOpenGLFunctions* gl = QOpenGLContext::currentContext()->functions();
    glGetIntegerv(GL_CURRENT_PROGRAM, &previousProgram);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &previousActiveTexture);
    gl->glActiveTexture(GL_TEXTURE0 + postProcessTextureUnit);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &previousTexture);
    gl->glActiveTexture(GL_TEXTURE0);

    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
    glMatrixMode(GL_TEXTURE);
    glPushMatrix();
    glLoadIdentity();
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();

    glDisable(GL_DEPTH_TEST);
    glDepthMask(GL_FALSE);
    glDisable(GL_BLEND);
    glDisable(GL_ALPHA_TEST);
    glDisable(GL_LIGHTING);
    glDisable(GL_CULL_FACE);
    glDisable(GL_STENCIL_TEST);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_POLYGON_STIPPLE);
    glDisable(GL_FOG);
    glDisable(GL_TEXTURE_2D);
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL);
    for (int plane = 0; plane < 6; ++plane) {
        glDisable(GL_CLIP_PLANE0 + plane);
    }
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
}

FullScreenPassState::~FullScreenPassState()
{
    QOpenGLFunctions* gl = QOpenGLContext::currentContext()->functions();
    gl->glUseProgram(GLuint(previousProgram));
    // The texture matrix was pushed on unit 0: pop it there.
    gl->glActiveTexture(GL_TEXTURE0);
    glMatrixMode(GL_TEXTURE);
    glPopMatrix();
    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();
    glPopClientAttrib();
    glPopAttrib();  // restores the active unit of the push (unit 0) with the texture state
    gl->glActiveTexture(GL_TEXTURE0 + postProcessTextureUnit);
    glBindTexture(GL_TEXTURE_2D, GLuint(previousTexture));
    gl->glActiveTexture(GLenum(previousActiveTexture));
}

}  // namespace Detail

void applyFxaa()
{
    if (!RenderSettings::fxaaActive()) {
        return;
    }
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context || context->isOpenGLES()) {
        return;
    }
    GLint samples = 0;
    glGetIntegerv(GL_SAMPLES, &samples);
    if (samples > 0) {
        return;  // multisampled: keep the hardware anti-aliasing (and it cannot be copied)
    }
    GLint viewport[4] = {0, 0, 0, 0};
    glGetIntegerv(GL_VIEWPORT, viewport);
    const int width = viewport[2];
    const int height = viewport[3];
    if (width <= 0 || height <= 0) {
        return;
    }
    std::string error;
    QOpenGLShaderProgram* program = Detail::fullScreenProgram(ShaderId::FxaaFragment, error);
    if (!program) {
        RenderSettings::disableFxaaForSession(error);
        return;
    }

    Detail::FullScreenPassState passState;
    QOpenGLFunctions* gl = context->functions();
    ContextResources& res = resourcesFor(context);
    gl->glActiveTexture(GL_TEXTURE0 + postProcessTextureUnit);
    if (!res.copyTexture) {
        glGenTextures(1, &res.copyTexture);
    }
    glBindTexture(GL_TEXTURE_2D, res.copyTexture);
    if (res.copyWidth != width || res.copyHeight != height) {
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        res.copyWidth = width;
        res.copyHeight = height;
    }
    glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, viewport[0], viewport[1], width, height);

    program->bind();
    program->setUniformValue("fc_source", GLint(postProcessTextureUnit));
    program->setUniformValue("fc_texel", QVector2D(1.0F / float(width), 1.0F / float(height)));
    gl->glActiveTexture(GL_TEXTURE0);
    Detail::drawFullScreenQuad();
}

void SoFCPostProcess::initClass()
{
    SO_NODE_INIT_CLASS(SoFCPostProcess, SoNode, "Node");
}

SoFCPostProcess::SoFCPostProcess()
{
    SO_NODE_CONSTRUCTOR(SoFCPostProcess);
}

void SoFCPostProcess::GLRender(SoGLRenderAction* action)
{
    if (!RenderSettings::fxaaActive()) {
        return;
    }
    // A display list must never record (or replace) the pass.
    SoCacheElement::invalidate(action->getState());
    applyFxaa();
}

SoFCPostProcess* createPostProcess()
{
    if (SoFCPostProcess::getClassTypeId() == SoType::badType()) {
        SoFCPostProcess::initClass();
    }
    return new SoFCPostProcess;
}

}  // namespace Gui::Render
