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
#include <chrono>
#include <memory>
#include <string>
#include <unordered_map>

#include <QMatrix4x4>
#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QOpenGLShaderProgram>
#include <QVector2D>

#include <Inventor/SbViewportRegion.h>
#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/elements/SoCacheElement.h>
#include <Inventor/elements/SoProjectionMatrixElement.h>
#include <Inventor/elements/SoViewingMatrixElement.h>
#include <Inventor/system/gl.h>

#include "AmbientOcclusion.h"
#include "PassUtilities.h"
#include "PostProcess.h"
#include "RenderSettings.h"

#ifndef GL_FRAMEBUFFER
# define GL_FRAMEBUFFER 0x8D40
#endif
#ifndef GL_FRAMEBUFFER_BINDING
# define GL_FRAMEBUFFER_BINDING 0x8CA6
#endif
#ifndef GL_FRAMEBUFFER_COMPLETE
# define GL_FRAMEBUFFER_COMPLETE 0x8CD5
#endif
#ifndef GL_DEPTH_ATTACHMENT
# define GL_DEPTH_ATTACHMENT 0x8D00
#endif
#ifndef GL_COLOR_ATTACHMENT0
# define GL_COLOR_ATTACHMENT0 0x8CE0
#endif
#ifndef GL_DEPTH_COMPONENT24
# define GL_DEPTH_COMPONENT24 0x81A6
#endif
#ifndef GL_CLAMP_TO_EDGE
# define GL_CLAMP_TO_EDGE 0x812F
#endif
#ifndef GL_TEXTURE0
# define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_TEXTURE_COMPARE_MODE
# define GL_TEXTURE_COMPARE_MODE 0x884C
#endif

using namespace Gui::Render;

SO_NODE_SOURCE(SoFCAmbientOcclusionPass)

namespace
{

thread_local bool prepassRunning = false;
thread_local bool matricesRecorded = false;
thread_local SbMatrix recordedView;
thread_local SbMatrix recordedProjection;

struct AmbientOcclusionResources
{
    GLuint depthFramebuffer = 0;
    GLuint depthTexture = 0;
    GLuint aoFramebuffer = 0;
    GLuint aoTexture = 0;
    int width = 0;   // half resolution size of both maps
    int height = 0;
    // Camera and geometry changes of the scene (a bare touch(), as preselection sends, does not
    // count: hovering does not re-render the map).
    std::unique_ptr<Detail::SceneChangeTracker> tracker = std::make_unique<Detail::SceneChangeTracker>();
    bool rendered = false;  // a result (map or "no shaded face") exists for the key below
    unsigned renderedChanges = 0;
    unsigned lastGeneration = 0;
    std::array<int, 4> lastViewport {};
    std::chrono::steady_clock::time_point renderTime;
    AmbientOcclusionFrame frame;
};

std::unordered_map<QOpenGLContext*, AmbientOcclusionResources>& allResources()
{
    static std::unordered_map<QOpenGLContext*, AmbientOcclusionResources> resources;
    return resources;
}

unsigned nextStamp()
{
    static unsigned stamp = 0;
    return ++stamp;
}

QMatrix4x4 toQMatrix(const SbMatrix& matrix)
{
    return QMatrix4x4(matrix[0]).transposed();
}

void deleteTargets(QOpenGLFunctions* gl, AmbientOcclusionResources& res)
{
    if (res.depthFramebuffer) {
        gl->glDeleteFramebuffers(1, &res.depthFramebuffer);
    }
    if (res.aoFramebuffer) {
        gl->glDeleteFramebuffers(1, &res.aoFramebuffer);
    }
    if (res.depthTexture) {
        glDeleteTextures(1, &res.depthTexture);
    }
    if (res.aoTexture) {
        glDeleteTextures(1, &res.aoTexture);
    }
    res.depthFramebuffer = res.aoFramebuffer = res.depthTexture = res.aoTexture = 0;
    res.width = res.height = 0;
}

GLuint makeTexture(GLint internalFormat, GLenum format, GLenum type, int width, int height, GLint filter)
{
    GLuint texture = 0;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexImage2D(GL_TEXTURE_2D, 0, internalFormat, width, height, 0, format, type, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    return texture;
}

/// (Re)create the half-resolution targets. Texture bindings of postProcessTextureUnit are
/// restored by the caller (FullScreenPassState). Returns an empty string on success.
std::string createTargets(QOpenGLContext* context, AmbientOcclusionResources& res, int width, int height)
{
    QOpenGLFunctions* gl = context->functions();
    if (context->isOpenGLES() || !gl->hasOpenGLFeature(QOpenGLFunctions::Framebuffers)) {
        return "no framebuffer object support";
    }
    deleteTargets(gl, res);
    for (int i = 0; i < 32 && glGetError() != GL_NO_ERROR; ++i) {
    }
    GLint previousFramebuffer = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &previousFramebuffer);

    res.depthTexture = makeTexture(GL_DEPTH_COMPONENT24, GL_DEPTH_COMPONENT, GL_UNSIGNED_INT, width, height, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);
    gl->glGenFramebuffers(1, &res.depthFramebuffer);
    gl->glBindFramebuffer(GL_FRAMEBUFFER, res.depthFramebuffer);
    gl->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, res.depthTexture, 0);
    glDrawBuffer(GL_NONE);
    glReadBuffer(GL_NONE);
    const GLenum depthStatus = gl->glCheckFramebufferStatus(GL_FRAMEBUFFER);

    res.aoTexture = makeTexture(GL_RGBA8, GL_RGBA, GL_UNSIGNED_BYTE, width, height, GL_LINEAR);
    gl->glGenFramebuffers(1, &res.aoFramebuffer);
    gl->glBindFramebuffer(GL_FRAMEBUFFER, res.aoFramebuffer);
    gl->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, res.aoTexture, 0);
    const GLenum aoStatus = gl->glCheckFramebufferStatus(GL_FRAMEBUFFER);

    gl->glBindFramebuffer(GL_FRAMEBUFFER, GLuint(previousFramebuffer));
    if (depthStatus != GL_FRAMEBUFFER_COMPLETE || aoStatus != GL_FRAMEBUFFER_COMPLETE
        || glGetError() != GL_NO_ERROR) {
        deleteTargets(gl, res);
        return "depth texture framebuffer is not supported";
    }
    res.width = width;
    res.height = height;
    return {};
}

AmbientOcclusionResources& resourcesFor(QOpenGLContext* context)
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
            // The textures belong to the share group and would outlive the view.
            AmbientOcclusionResources& res = found->second;
            Detail::runWithContextCurrent(context, [&res](QOpenGLFunctions* gl) {
                deleteTargets(gl, res);
            });
            all.erase(found);
        },
        Qt::DirectConnection
    );
    return resources[context];
}

}  // namespace

namespace Gui::Render
{

const AmbientOcclusionFrame* currentAmbientOcclusionFrame()
{
    auto& resources = allResources();
    auto it = resources.find(QOpenGLContext::currentContext());
    return it == resources.end() ? nullptr : &it->second.frame;
}

bool isInAmbientOcclusionPrepass()
{
    return prepassRunning;
}

void recordAmbientOcclusionMatrices(SoState* state)
{
    if (!prepassRunning || matricesRecorded) {
        return;
    }
    recordedView = SoViewingMatrixElement::get(state);
    recordedProjection = SoProjectionMatrixElement::get(state);
    matricesRecorded = true;
}

SoFCAmbientOcclusionPass* createAmbientOcclusionPass(SoNode* scene)
{
    if (SoFCAmbientOcclusionPass::getClassTypeId() == SoType::badType()) {
        SoFCAmbientOcclusionPass::initClass();
    }
    auto* node = new SoFCAmbientOcclusionPass;
    node->setScene(scene);
    return node;
}

void SoFCAmbientOcclusionPass::initClass()
{
    SO_NODE_INIT_CLASS(SoFCAmbientOcclusionPass, SoNode, "Node");
}

SoFCAmbientOcclusionPass::SoFCAmbientOcclusionPass()
{
    SO_NODE_CONSTRUCTOR(SoFCAmbientOcclusionPass);
}

SoFCAmbientOcclusionPass::~SoFCAmbientOcclusionPass()
{
    setScene(nullptr);
}

void SoFCAmbientOcclusionPass::setScene(SoNode* node)
{
    if (node == scene) {
        return;
    }
    if (node) {
        node->ref();
    }
    if (scene) {
        scene->unref();
    }
    scene = node;
}

void SoFCAmbientOcclusionPass::GLRender(SoGLRenderAction* action)
{
    if (!scene || prepassRunning || !RenderSettings::ambientOcclusionActive()) {
        return;
    }
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        return;
    }
    SoCacheElement::invalidate(action->getState());

    const SbViewportRegion& region = action->getViewportRegion();
    const SbVec2s origin = region.getViewportOriginPixels();
    const SbVec2s size = region.getViewportSizePixels();
    if (size[0] <= 0 || size[1] <= 0) {
        return;
    }
    const std::array<int, 4> viewport {origin[0], origin[1], size[0], size[1]};
    AmbientOcclusionResources& res = resourcesFor(context);
    const unsigned generation = RenderSettings::generation();
    const bool newScene = res.tracker->track(scene);
    const auto now = std::chrono::steady_clock::now();
    const Detail::MapUpdate update = Detail::decideMapUpdate(
        res.rendered && !newScene && res.lastGeneration == generation && res.lastViewport == viewport,
        res.tracker->changes() != res.renderedChanges,
        postponeAllowed,
        false,  // the viewer does not apply the pass while navigating
        std::chrono::duration<double>(now - res.renderTime).count()
    );
    if (update == Detail::MapUpdate::Keep) {
        return;  // same scene, camera (it is part of the scene) and viewport: keep the map
    }
    if (update == Detail::MapUpdate::Postpone) {
        // The face shader only uses the old map where the camera still matches it.
        Detail::notePostponedMapUpdate();
        return;
    }
    res.frame.valid = false;
    res.rendered = true;
    res.renderedChanges = res.tracker->changes();
    res.lastGeneration = generation;
    res.lastViewport = viewport;
    res.renderTime = now;

    std::string error;
    QOpenGLShaderProgram* program = Detail::fullScreenProgram(ShaderId::AmbientOcclusionFragment, error);
    if (!program) {
        RenderSettings::disableAmbientOcclusionForSession(error);
        return;
    }

    const int width = std::max(1, size[0] / 2);
    const int height = std::max(1, size[1] / 2);
    QOpenGLFunctions* gl = context->functions();
    // Restores the framebuffer binding when leaving the block, also when the prepass throws.
    struct FramebufferBinding
    {
        QOpenGLFunctions* gl;
        GLint previous = 0;
        explicit FramebufferBinding(QOpenGLFunctions* gl)
            : gl(gl)
        {
            glGetIntegerv(GL_FRAMEBUFFER_BINDING, &previous);
        }
        ~FramebufferBinding()
        {
            gl->glBindFramebuffer(GL_FRAMEBUFFER, GLuint(previous));
        }
        FramebufferBinding(const FramebufferBinding&) = delete;
        FramebufferBinding& operator=(const FramebufferBinding&) = delete;
    };
    // The face shading leaves the previous map bound on its unit; unbind it before the map is
    // rendered to (or re-created on a resize). The next shaded face binds the new map (new stamp).
    Detail::unbindTextureUnit(gl, ambientOcclusionUnit);
    {
        Detail::FullScreenPassState passState;  // also restores the texture of the pass unit
        const FramebufferBinding framebufferBinding(gl);
        gl->glActiveTexture(GL_TEXTURE0 + postProcessTextureUnit);
        if (res.width != width || res.height != height) {
            error = createTargets(context, res, width, height);
            if (!error.empty()) {
                RenderSettings::disableAmbientOcclusionForSession(error);
                return;
            }
        }

        // 1. Depth prepass of the scene, half resolution, colour writes off.
        gl->glBindFramebuffer(GL_FRAMEBUFFER, res.depthFramebuffer);
        glViewport(0, 0, width, height);
        glEnable(GL_DEPTH_TEST);
        glDepthMask(GL_TRUE);
        glClearDepth(1.0);
        glClear(GL_DEPTH_BUFFER_BIT);
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE);
        SoGLRenderAction prepass {SbViewportRegion(short(width), short(height))};
        prepass.setCacheContext(action->getCacheContext());
        prepass.setTransparencyType(action->getTransparencyType());
        matricesRecorded = false;
        Detail::applyPrepass(prepass, scene, action, prepassRunning);
        res.renderedChanges = res.tracker->changes();  // changes made while rendering do not count

        if (matricesRecorded) {
            // 2. Occlusion from the depth map.
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
            glDisable(GL_DEPTH_TEST);
            glDepthMask(GL_FALSE);
            gl->glBindFramebuffer(GL_FRAMEBUFFER, res.aoFramebuffer);
            glViewport(0, 0, width, height);
            gl->glActiveTexture(GL_TEXTURE0 + postProcessTextureUnit);
            glBindTexture(GL_TEXTURE_2D, res.depthTexture);
            program->bind();
            program->setUniformValue("fc_depth", GLint(postProcessTextureUnit));
            program->setUniformValue("fc_projection", toQMatrix(recordedProjection));
            program->setUniformValue("fc_inverseProjection", toQMatrix(recordedProjection.inverse()));
            program->setUniformValue("fc_texel", QVector2D(1.0F / float(width), 1.0F / float(height)));
            program->setUniformValue("fc_aoRadius", GLfloat(ambientOcclusionRadius));
            program->setUniformValue("fc_aoStrength", GLfloat(ambientOcclusionStrength));
            gl->glActiveTexture(GL_TEXTURE0);
            Detail::drawFullScreenQuad();
        }
    }

    if (!matricesRecorded) {
        return;  // no shaded face in the scene: nothing to occlude
    }
    res.frame.view = recordedView;
    res.frame.projection = recordedProjection;
    res.frame.viewport = viewport;
    res.frame.texture = res.aoTexture;
    res.frame.stamp = nextStamp();
    res.frame.valid = true;
}

}  // namespace Gui::Render
