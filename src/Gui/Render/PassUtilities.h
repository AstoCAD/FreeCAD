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

#include <functional>

#include <FCGlobal.h>

class QOpenGLContext;
class QOpenGLFunctions;
class SoGLRenderAction;
class SoNode;
class SoNodeSensor;
class SoSensor;

/// Helpers shared by the passes of the Enhanced quality (shadow map, ambient occlusion, FXAA).
/// None of them is used in Classic.
namespace Gui::Render::Detail
{

/// True if a scene notification can change what the scene renders. A bare touch() of a node
/// (no field, no child list change) is what preselection, selection highlighting and render cache
/// invalidation send: it is not a change of the geometry or of the camera.
GuiExport bool isRenderingChange(bool hasTriggerField, bool isChildListChange);

/**
 * Counts the notifications of a scene that are rendering changes (see isRenderingChange()), with
 * an immediate node sensor. The node is not referenced: if it dies, the sensor detaches and the
 * next track() reports a new node.
 */
class GuiExport SceneChangeTracker
{
public:
    SceneChangeTracker();
    ~SceneChangeTracker();
    SceneChangeTracker(const SceneChangeTracker&) = delete;
    SceneChangeTracker& operator=(const SceneChangeTracker&) = delete;

    /// Track node from now on. Returns true if it was not the tracked node already.
    bool track(SoNode* node);
    /// Number of rendering changes seen since construction.
    unsigned changes() const
    {
        return count;
    }

private:
    static void sensorCallback(void* data, SoSensor* sensor);

    SoNodeSensor* sensor = nullptr;
    unsigned count = 0;
};

/// What to do with a cached prepass map (shadow map, ambient occlusion map) this frame.
enum class MapUpdate
{
    Keep,      ///< up to date: reuse it
    Render,    ///< render it now
    Postpone,  ///< out of date: keep the old one this frame, a later redraw renders it
};

/// Minimum time between two re-renders of a map caused by scene changes on screen (dragging in a
/// sketch, a preview that follows the mouse, ...); the last change is caught up by a later redraw.
constexpr double minimumMapUpdateInterval = 0.25;

/**
 * mapUsable: there is a map (or a known empty result) for this scene, viewport and settings.
 * changed: the scene changed since it was rendered. postponeAllowed: on screen (exports always
 * render). navigating: the user orbits or the view animates, so camera-driven nodes change on
 * every frame and must not re-render the map.
 */
GuiExport MapUpdate decideMapUpdate(
    bool mapUsable,
    bool changed,
    bool postponeAllowed,
    bool navigating,
    double secondsSinceRender
);

/// Remember that a map update was postponed (see MapUpdate::Postpone) in this thread.
GuiExport void notePostponedMapUpdate();
/// True if a map update was postponed since the last call; clears the flag. The viewer then
/// schedules a redraw a little later.
GuiExport bool takePostponedMapUpdate();

/**
 * Applies a prepass action (shadow depth, ambient occlusion depth) to root:
 * - the per-frame FreeCAD elements of outer (GL widget, device pixel ratio, VBO switch) are set in
 *   the prepass state, as View3DInventorViewer sets them for its own action, so that nodes behave
 *   as in the main pass (VBO path, cursor reset of SoFCUnifiedSelection, ...);
 * - the delayed annotation paths the prepass collects are discarded (they would leak);
 * - runningFlag is true during the traversal and reset even if it throws.
 */
GuiExport void applyPrepass(SoGLRenderAction& prepass, SoNode* root, SoGLRenderAction* outer, bool& runningFlag);

/**
 * Run cleanup with context current, for an aboutToBeDestroyed slot (direct connection): the
 * context is usually not current when it is destroyed (QOpenGLWidget makes it current, cleans up
 * and calls doneCurrent() first), and with shared contexts its textures would outlive it.
 * The previously current context is made current again afterwards. Does nothing if the context
 * cannot be made current.
 */
GuiExport void runWithContextCurrent(QOpenGLContext* context, const std::function<void(QOpenGLFunctions*)>& cleanup);

/// Bind no 2D texture on unit (the active unit is kept). Used before a pass renders to the map
/// that the face shading leaves bound on that unit.
GuiExport void unbindTextureUnit(QOpenGLFunctions* gl, int unit);

}  // namespace Gui::Render::Detail
