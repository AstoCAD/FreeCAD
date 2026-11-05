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

#include <QGuiApplication>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLFunctions>

#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/lists/SoPathList.h>
#include <Inventor/misc/SoState.h>
#include <Inventor/nodes/SoCallback.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/sensors/SoNodeSensor.h>

#ifndef GL_TEXTURE0
# define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ACTIVE_TEXTURE
# define GL_ACTIVE_TEXTURE 0x84E0
#endif

#include <Gui/Inventor/So3DAnnotation.h>
#include <Gui/SoDevicePixelRatioElement.h>
#include <Gui/SoFCInteractiveElement.h>

#include "PassUtilities.h"

namespace Gui::Render::Detail
{

namespace
{

/// The per-frame elements View3DInventorViewer::renderGLActionScene sets in its own action.
struct FrameElements
{
    SoGLRenderAction* action = nullptr;
    QOpenGLWidget* widget = nullptr;
    SbBool vbo = FALSE;
    float devicePixelRatio = 1.0F;
    bool hasWidget = false;
    bool hasVbo = false;
    bool hasDevicePixelRatio = false;
    bool hasAction = false;
};

template<typename Element>
bool isUsable(SoState* state)
{
    // The elements are registered by SoFCDB::init(); a bare Coin set-up (tests) has none of them.
    return state && Element::getClassTypeId() != SoType::badType()
        && state->isElementEnabled(Element::getClassStackIndex());
}

FrameElements readFrameElements(SoGLRenderAction* outer, SoGLRenderAction* prepass)
{
    FrameElements frame;
    frame.action = prepass;
    SoState* state = outer ? outer->getState() : nullptr;
    if (isUsable<SoGLWidgetElement>(state)) {
        SoGLWidgetElement::get(state, frame.widget);
        frame.hasWidget = true;
    }
    if (isUsable<SoGLVBOActivatedElement>(state)) {
        SoGLVBOActivatedElement::get(state, frame.vbo);
        frame.hasVbo = true;
    }
    if (isUsable<SoDevicePixelRatioElement>(state)) {
        frame.devicePixelRatio = SoDevicePixelRatioElement::get(state);
        frame.hasDevicePixelRatio = true;
    }
    frame.hasAction = isUsable<SoGLRenderActionElement>(state);
    return frame;
}

void setFrameElements(void* data, SoAction* action)
{
    if (!action->isOfType(SoGLRenderAction::getClassTypeId())) {
        return;
    }
    const auto* frame = static_cast<const FrameElements*>(data);
    SoState* state = action->getState();
    if (frame->hasWidget) {
        SoGLWidgetElement::set(state, frame->widget);
    }
    if (frame->hasVbo) {
        SoGLVBOActivatedElement::set(state, frame->vbo);
    }
    if (frame->hasDevicePixelRatio) {
        SoDevicePixelRatioElement::set(state, frame->devicePixelRatio);
    }
    if (frame->hasAction) {
        SoGLRenderActionElement::set(state, frame->action);
    }
}

/// Resets the running flag, discards the delayed paths and releases the wrapper, also on throw.
class PrepassScope
{
public:
    PrepassScope(SoGLRenderAction& prepass, SoSeparator* wrapper, bool& flag)
        : prepass(prepass)
        , wrapper(wrapper)
        , flag(flag)
    {
        flag = true;
    }
    ~PrepassScope()
    {
        flag = false;
        SoState* state = prepass.getState();
        if (isUsable<SoDelayedAnnotationsElement>(state)) {
            // So3DAnnotation and the clarify-selection path add a copied path per annotation;
            // the returned list owns them, so this deletes them (and releases their nodes).
            SoDelayedAnnotationsElement::getDelayedPaths(state);
        }
        wrapper->unref();
    }
    PrepassScope(const PrepassScope&) = delete;
    PrepassScope& operator=(const PrepassScope&) = delete;

private:
    SoGLRenderAction& prepass;
    SoSeparator* wrapper;
    bool& flag;
};

thread_local bool mapUpdatePostponed = false;

}  // namespace

bool isRenderingChange(bool hasTriggerField, bool isChildListChange)
{
    return hasTriggerField || isChildListChange;
}

SceneChangeTracker::SceneChangeTracker()
    : sensor(new SoNodeSensor(sensorCallback, this))
{
    // Immediate: the trigger (field, operation) is only recorded for priority 0 sensors.
    sensor->setPriority(0);
}

SceneChangeTracker::~SceneChangeTracker()
{
    delete sensor;  // detaches
}

bool SceneChangeTracker::track(SoNode* node)
{
    if (node && sensor->getAttachedNode() == node) {
        return false;
    }
    sensor->detach();
    if (node) {
        sensor->attach(node);
    }
    return true;
}

void SceneChangeTracker::sensorCallback(void* data, SoSensor* base)
{
    auto* self = static_cast<SceneChangeTracker*>(data);
    auto* nodeSensor = static_cast<SoNodeSensor*>(base);
    const SoNotRec::OperationType operation = nodeSensor->getTriggerOperationType();
    const bool childList = operation == SoNotRec::GROUP_ADDCHILD || operation == SoNotRec::GROUP_INSERTCHILD
        || operation == SoNotRec::GROUP_REPLACECHILD || operation == SoNotRec::GROUP_REMOVECHILD
        || operation == SoNotRec::GROUP_REMOVEALLCHILDREN;
    if (isRenderingChange(nodeSensor->getTriggerField() != nullptr, childList)) {
        ++self->count;
    }
}

MapUpdate decideMapUpdate(bool mapUsable, bool changed, bool postponeAllowed, bool navigating, double secondsSinceRender)
{
    if (!mapUsable) {
        return MapUpdate::Render;
    }
    if (!changed) {
        return MapUpdate::Keep;
    }
    if (postponeAllowed && (navigating || secondsSinceRender < minimumMapUpdateInterval)) {
        return MapUpdate::Postpone;
    }
    return MapUpdate::Render;
}

void notePostponedMapUpdate()
{
    mapUpdatePostponed = true;
}

bool takePostponedMapUpdate()
{
    const bool postponed = mapUpdatePostponed;
    mapUpdatePostponed = false;
    return postponed;
}

void runWithContextCurrent(QOpenGLContext* context, const std::function<void(QOpenGLFunctions*)>& cleanup)
{
    if (!context) {
        return;
    }
    QOpenGLContext* previous = QOpenGLContext::currentContext();
    if (previous == context) {
        cleanup(context->functions());
        return;
    }
    if (!QGuiApplication::instance()) {
        return;  // too late to create a surface: the process is going away anyway
    }
    QSurface* previousSurface = previous ? previous->surface() : nullptr;
    QOffscreenSurface surface;
    surface.setFormat(context->format());
    surface.create();
    if (surface.isValid() && context->makeCurrent(&surface)) {
        cleanup(context->functions());
        context->doneCurrent();
    }
    if (previous && previousSurface) {
        previous->makeCurrent(previousSurface);
    }
}

void unbindTextureUnit(QOpenGLFunctions* gl, int unit)
{
    GLint active = GL_TEXTURE0;
    gl->glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
    gl->glActiveTexture(GLenum(GL_TEXTURE0 + unit));
    gl->glBindTexture(GL_TEXTURE_2D, 0);
    gl->glActiveTexture(GLenum(active));
}

void applyPrepass(SoGLRenderAction& prepass, SoNode* root, SoGLRenderAction* outer, bool& runningFlag)
{
    FrameElements frame = readFrameElements(outer, &prepass);
    auto* wrapper = new SoSeparator;
    wrapper->ref();
    wrapper->renderCaching = SoSeparator::OFF;
    auto* callback = new SoCallback;
    callback->setCallback(setFrameElements, &frame);
    wrapper->addChild(callback);
    wrapper->addChild(root);
    PrepassScope scope(prepass, wrapper, runningFlag);
    prepass.apply(wrapper);
}

}  // namespace Gui::Render::Detail
