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

#include <QOpenGLContext>
#include <QOpenGLFunctions>

#include <Inventor/SbBox3f.h>
#include <Inventor/SbViewportRegion.h>
#include <Inventor/SbViewVolume.h>
#include <Inventor/actions/SoGetBoundingBoxAction.h>
#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/elements/SoCacheElement.h>
#include <Inventor/nodes/SoOrthographicCamera.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/system/gl.h>

#include "PassUtilities.h"
#include "RenderSettings.h"
#include "ShadowMath.h"
#include "ShadowPass.h"

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
#ifndef GL_DEPTH_COMPONENT24
# define GL_DEPTH_COMPONENT24 0x81A6
#endif
#ifndef GL_CLAMP_TO_EDGE
# define GL_CLAMP_TO_EDGE 0x812F
#endif
#ifndef GL_TEXTURE0
# define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ACTIVE_TEXTURE
# define GL_ACTIVE_TEXTURE 0x84E0
#endif
#ifndef GL_MAX_TEXTURE_IMAGE_UNITS
# define GL_MAX_TEXTURE_IMAGE_UNITS 0x8872
#endif
#ifndef GL_TEXTURE_COMPARE_MODE
# define GL_TEXTURE_COMPARE_MODE 0x884C
#endif

using namespace Gui::Render;

SO_NODE_SOURCE(SoFCShadowPass)

namespace
{

constexpr int preferredMapSize = 2048;

thread_local bool shadowPassRunning = false;

struct ShadowResources
{
    GLuint framebuffer = 0;
    GLuint texture = 0;
    int size = 0;
    SoSeparator* root = nullptr;             // [camera, casters], referenced
    SoOrthographicCamera* camera = nullptr;  // child of root
    // Geometry changes of the casters. Preselection and selection only touch() nodes, which does
    // not count, so hovering does not re-render the map (the node id of the casters changes then).
    std::unique_ptr<Detail::SceneChangeTracker> tracker = std::make_unique<Detail::SceneChangeTracker>();
    bool rendered = false;         // a result (map or empty scene) exists for the key below
    unsigned renderedChanges = 0;  // tracker->changes() when it was rendered
    unsigned lastGeneration = 0;
    std::chrono::steady_clock::time_point renderTime;
    ShadowFrame frame;
};

std::unordered_map<QOpenGLContext*, ShadowResources>& allResources()
{
    static std::unordered_map<QOpenGLContext*, ShadowResources> resources;
    return resources;
}

unsigned nextStamp()
{
    static unsigned stamp = 0;
    return ++stamp;
}

/// Creates the depth texture and framebuffer of a context. Returns an empty string on success.
std::string createTargets(QOpenGLContext* context, ShadowResources& res)
{
    if (context->isOpenGLES()) {
        return "OpenGL ES context";
    }
    QOpenGLFunctions* gl = context->functions();
    if (!gl->hasOpenGLFeature(QOpenGLFunctions::Framebuffers)) {
        return "no framebuffer object support";
    }
    GLint units = 0;
    glGetIntegerv(GL_MAX_TEXTURE_IMAGE_UNITS, &units);
    if (units <= shadowTextureUnit) {
        return "not enough texture units";
    }
    GLint maxSize = 0;
    glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxSize);
    res.size = std::min(preferredMapSize, int(maxSize));
    if (res.size < 512) {
        return "maximum texture size too small";
    }

    GLint previousUnit = GL_TEXTURE0;
    glGetIntegerv(GL_ACTIVE_TEXTURE, &previousUnit);
    gl->glActiveTexture(GL_TEXTURE0 + shadowTextureUnit);
    GLint previousTexture = 0;
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &previousTexture);
    glGenTextures(1, &res.texture);
    glBindTexture(GL_TEXTURE_2D, res.texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24, res.size, res.size, 0, GL_DEPTH_COMPONENT,
                 GL_UNSIGNED_INT, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_COMPARE_MODE, GL_NONE);
    glBindTexture(GL_TEXTURE_2D, GLuint(previousTexture));
    gl->glActiveTexture(GLenum(previousUnit));

    GLint previousFramebuffer = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &previousFramebuffer);
    gl->glGenFramebuffers(1, &res.framebuffer);
    gl->glBindFramebuffer(GL_FRAMEBUFFER, res.framebuffer);
    gl->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, res.texture, 0);
    glDrawBuffer(GL_NONE);
    glReadBuffer(GL_NONE);
    const GLenum status = gl->glCheckFramebufferStatus(GL_FRAMEBUFFER);
    gl->glBindFramebuffer(GL_FRAMEBUFFER, GLuint(previousFramebuffer));
    if (status != GL_FRAMEBUFFER_COMPLETE || glGetError() != GL_NO_ERROR) {
        gl->glDeleteFramebuffers(1, &res.framebuffer);
        glDeleteTextures(1, &res.texture);
        res.framebuffer = 0;
        res.texture = 0;
        return "depth texture framebuffer is not supported";
    }
    return {};
}

ShadowResources* acquireResources(QOpenGLContext* context)
{
    auto& resources = allResources();
    auto it = resources.find(context);
    if (it != resources.end()) {
        return &it->second;
    }
    ShadowResources res;
    for (int i = 0; i < 32 && glGetError() != GL_NO_ERROR; ++i) {
        // clear stale errors so that the creation check only sees its own
    }
    const std::string error = createTargets(context, res);
    if (!error.empty()) {
        RenderSettings::disableShadowsForSession(error);
        return nullptr;
    }
    res.root = new SoSeparator;
    res.root->ref();
    res.root->renderCaching = SoSeparator::OFF;
    res.root->boundingBoxCaching = SoSeparator::OFF;
    res.camera = new SoOrthographicCamera;
    res.camera->viewportMapping = SoCamera::LEAVE_ALONE;
    res.root->addChild(res.camera);
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
            // With shared contexts the texture belongs to the share group and would outlive
            // the view: delete it with the context current (QOpenGLWidget releases it first).
            ShadowResources& res = found->second;
            Detail::runWithContextCurrent(context, [&res](QOpenGLFunctions* gl) {
                gl->glDeleteFramebuffers(1, &res.framebuffer);
                gl->glDeleteTextures(1, &res.texture);
            });
            res.root->unref();
            all.erase(found);
        },
        Qt::DirectConnection
    );
    return &resources.emplace(context, std::move(res)).first->second;
}

SbMatrix biasMatrix()
{
    // clip [-1, 1] -> [0, 1], row-vector convention (translation in the last row)
    return SbMatrix(0.5F, 0.0F, 0.0F, 0.0F,
                    0.0F, 0.5F, 0.0F, 0.0F,
                    0.0F, 0.0F, 0.5F, 0.0F,
                    0.5F, 0.5F, 0.5F, 1.0F);
}

/// Saves the framebuffer binding, the attributes and the matrices, restores them on destruction
/// (also when the traversal throws).
class DepthPassState
{
public:
    explicit DepthPassState(QOpenGLFunctions* gl)
        : gl(gl)
    {
        glGetIntegerv(GL_FRAMEBUFFER_BINDING, &previousFramebuffer);
        glPushAttrib(GL_ALL_ATTRIB_BITS);
        glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
        glMatrixMode(GL_PROJECTION);
        glPushMatrix();
        glMatrixMode(GL_MODELVIEW);
        glPushMatrix();
    }
    ~DepthPassState()
    {
        gl->glBindFramebuffer(GL_FRAMEBUFFER, GLuint(previousFramebuffer));
        glMatrixMode(GL_PROJECTION);
        glPopMatrix();
        glMatrixMode(GL_MODELVIEW);
        glPopMatrix();
        glPopClientAttrib();
        glPopAttrib();
    }
    DepthPassState(const DepthPassState&) = delete;
    DepthPassState& operator=(const DepthPassState&) = delete;

private:
    QOpenGLFunctions* gl;
    GLint previousFramebuffer = 0;
};

/// Render the depth of casters into the shadow map of res. GL state is saved and restored.
void renderDepth(QOpenGLContext* context, ShadowResources& res, SoGLRenderAction* action)
{
    QOpenGLFunctions* gl = context->functions();
    // The face shading leaves the previous map bound on its unit; never render to a bound texture.
    // The next shaded face binds it again (new stamp).
    Detail::unbindTextureUnit(gl, shadowTextureUnit);
    const DepthPassState passState(gl);

    gl->glBindFramebuffer(GL_FRAMEBUFFER, res.framebuffer);
    glViewport(0, 0, res.size, res.size);
    glDisable(GL_SCISSOR_TEST);
    glDepthMask(GL_TRUE);
    glClearDepth(1.0);
    glClear(GL_DEPTH_BUFFER_BIT);
    glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE);
    // Slope-scaled offset in the rasterizer against shadow acne (nodes that set their own
    // polygon offset, like Part faces, replace it: the shader bias covers them).
    glEnable(GL_POLYGON_OFFSET_FILL);
    glPolygonOffset(2.0F, 4.0F);

    SoGLRenderAction depthAction(SbViewportRegion(short(res.size), short(res.size)));
    depthAction.setCacheContext(action->getCacheContext());
    depthAction.setTransparencyType(action->getTransparencyType());
    Detail::applyPrepass(depthAction, res.root, action, shadowPassRunning);
}

}  // namespace

namespace Gui::Render
{

const ShadowFrame* currentShadowFrame()
{
    auto& resources = allResources();
    auto it = resources.find(QOpenGLContext::currentContext());
    return it == resources.end() ? nullptr : &it->second.frame;
}

bool isInShadowPass()
{
    return shadowPassRunning;
}

SoFCShadowPass* createShadowPass(SoNode* casters)
{
    if (SoFCShadowPass::getClassTypeId() == SoType::badType()) {
        SoFCShadowPass::initClass();
    }
    auto* node = new SoFCShadowPass;
    node->setCasters(casters);
    return node;
}

}  // namespace Gui::Render

void SoFCShadowPass::initClass()
{
    SO_NODE_INIT_CLASS(SoFCShadowPass, SoNode, "Node");
}

SoFCShadowPass::SoFCShadowPass()
{
    SO_NODE_CONSTRUCTOR(SoFCShadowPass);
}

SoFCShadowPass::~SoFCShadowPass()
{
    setCasters(nullptr);
}

void SoFCShadowPass::setCasters(SoNode* node)
{
    if (node == casters) {
        return;
    }
    if (node) {
        node->ref();
    }
    if (casters) {
        casters->unref();
    }
    casters = node;
}

void SoFCShadowPass::GLRender(SoGLRenderAction* action)
{
    if (!casters || shadowPassRunning || !RenderSettings::shadowsActive()) {
        return;
    }
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        return;
    }
    ShadowResources* res = acquireResources(context);
    if (!res) {
        return;
    }
    // Never let a render cache above this node record (or skip) the shadow pass.
    SoCacheElement::invalidate(action->getState());
    const unsigned generation = RenderSettings::generation();
    const bool newCasters = res->tracker->track(casters);
    const auto now = std::chrono::steady_clock::now();
    const Detail::MapUpdate update = Detail::decideMapUpdate(
        res->rendered && !newCasters && res->lastGeneration == generation,
        res->tracker->changes() != res->renderedChanges,
        postponeAllowed,
        navigating,
        std::chrono::duration<double>(now - res->renderTime).count()
    );
    if (update == Detail::MapUpdate::Keep) {
        return;  // scene and light unchanged: keep the map (camera moves do not matter)
    }
    if (update == Detail::MapUpdate::Postpone) {
        Detail::notePostponedMapUpdate();
        return;
    }
    res->rendered = true;
    res->renderedChanges = res->tracker->changes();
    res->lastGeneration = generation;
    res->renderTime = now;
    res->frame.valid = false;

    SoGetBoundingBoxAction bboxAction(action->getViewportRegion());
    bboxAction.apply(casters);
    res->renderedChanges = res->tracker->changes();  // nodes may update fields while traversed
    const SbBox3f box = bboxAction.getBoundingBox();
    if (box.isEmpty()) {
        return;
    }
    const Vec3 sun = defaultSunDirection();
    const SbVec3f& boxMin = box.getMin();
    const SbVec3f& boxMax = box.getMax();
    const LightFrustum frustum
        = fitLightFrustum(sun, {boxMin[0], boxMin[1], boxMin[2]}, {boxMax[0], boxMax[1], boxMax[2]});
    if (!frustum.valid) {
        return;
    }

    SoOrthographicCamera* camera = res->camera;
    camera->position.setValue(frustum.position[0], frustum.position[1], frustum.position[2]);
    // Camera axes as matrix rows (row-vector convention): x = right, y = up, z = towards the sun.
    const SbMatrix axes(
        frustum.right[0], frustum.right[1], frustum.right[2], 0.0F,
        frustum.up[0], frustum.up[1], frustum.up[2], 0.0F,
        frustum.back[0], frustum.back[1], frustum.back[2], 0.0F,
        0.0F, 0.0F, 0.0F, 1.0F
    );
    camera->orientation.setValue(SbRotation(axes));
    camera->height = 2.0F * frustum.halfHeight;
    camera->aspectRatio = frustum.halfWidth / frustum.halfHeight;
    camera->nearDistance = frustum.nearDistance;
    camera->farDistance = frustum.farDistance;

    {
        struct CastersChild  // removed again even if the traversal throws
        {
            SoSeparator* root;
            explicit CastersChild(SoSeparator* root, SoNode* casters)
                : root(root)
            {
                root->addChild(casters);
            }
            ~CastersChild()
            {
                root->removeChild(root->getNumChildren() - 1);
            }
            CastersChild(const CastersChild&) = delete;
            CastersChild& operator=(const CastersChild&) = delete;
        } child(res->root, casters);
        renderDepth(context, *res, action);
    }
    // Field changes made by nodes while they render are not scene changes.
    res->renderedChanges = res->tracker->changes();

    SbMatrix view;
    SbMatrix projection;
    camera->getViewVolume(camera->aspectRatio.getValue()).getMatrices(view, projection);
    SbMatrix worldToShadow = view;
    worldToShadow.multRight(projection);
    worldToShadow.multRight(biasMatrix());

    const float texelWorld = 2.0F * std::max(frustum.halfWidth, frustum.halfHeight) / float(res->size);
    res->frame.worldToShadow = worldToShadow;
    res->frame.sunDirection.setValue(sun[0], sun[1], sun[2]);
    res->frame.texture = res->texture;
    res->frame.size = res->size;
    res->frame.bias = shadowDepthBias(texelWorld, frustum.farDistance - frustum.nearDistance);
    res->frame.stamp = nextStamp();
    res->frame.valid = true;
}
