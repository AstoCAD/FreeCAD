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
#include <cmath>
#include <memory>
#include <unordered_map>

#include <QOpenGLContext>
#include <QOpenGLFunctions>
#include <QGenericMatrix>
#include <QMatrix4x4>
#include <QVector4D>
#include <QOpenGLShaderProgram>
#include <QVector3D>

#include <Inventor/SbColor.h>
#include <Inventor/actions/SoGLRenderAction.h>
#include <Inventor/elements/SoCacheElement.h>
#include <Inventor/elements/SoDrawStyleElement.h>
#include <Inventor/elements/SoEnvironmentElement.h>
#include <Inventor/elements/SoGLLightIdElement.h>
#include <Inventor/elements/SoGLShaderProgramElement.h>
#include <Inventor/elements/SoLazyElement.h>
#include <Inventor/elements/SoMultiTextureEnabledElement.h>
#include <Inventor/elements/SoOverrideElement.h>
#include <Inventor/elements/SoProjectionMatrixElement.h>
#include <Inventor/elements/SoViewingMatrixElement.h>
#include <Inventor/elements/SoViewportRegionElement.h>
#include <Inventor/misc/SoState.h>

#include "AmbientOcclusion.h"
#include "FaceShading.h"
#include "RenderCapabilities.h"
#include "RenderSettings.h"
#include "ShaderLibrary.h"
#include "ShadingModel.h"
#include "ShadowMath.h"
#include "ShadowPass.h"

#ifndef GL_TEXTURE0
# define GL_TEXTURE0 0x84C0
#endif
#ifndef GL_ACTIVE_TEXTURE
# define GL_ACTIVE_TEXTURE 0x84E0
#endif

namespace Gui::Render
{

namespace
{

constexpr int shaderMaxLights = 8;  // FC_MAX_LIGHTS

struct ContextProgram
{
    QOpenGLShaderProgram* program = nullptr;  // owned by the QOpenGLContext (QObject child)
    unsigned generation = 0;                  // RenderSettings::generation() of the uniforms
    int numLightsLocation = -1;
    int twoSidedLocation = -1;
    int maxLights = shaderMaxLights;
    // Shadow uniforms that depend on the camera: re-uploaded only when the view or the map change.
    int eyeToShadowLocation = -1;
    int sunDirectionLocation = -1;
    int shadowModeLocation = -1;
    int shadowBiasLocation = -1;
    int aoModeLocation = -1;
    int aoViewportLocation = -1;
    int shadowTexelLocation = -1;
    SbMatrix lastView = SbMatrix::identity();
    unsigned lastShadowStamp = 0;
    unsigned lastShadowGeneration = 0;
    // Uniform values last uploaded (the program keeps them), to skip redundant uploads per shape.
    int lastNumLights = -1;
    int lastTwoSided = -1;
    int lastAoMode = -1;
    QVector4D lastAoViewport;
    // Whole-object (pre)selection tint.
    int tintModeLocation = -1;
    int tintLocation = -1;
    int lastTintMode = -1;
    // Rotation from eye space to the environment (world, Z up), re-uploaded when the view changes.
    int eyeToEnvironmentLocation = -1;
    SbMatrix lastEnvironmentView = SbMatrix::identity();
    bool environmentViewSet = false;
};

/// What the face shading left bound on one of its texture units (6 and 7 belong to the
/// enhanced pipeline: no other texture is expected there). Shapes rebind only when the map
/// changes, so a frame does at most a couple of binds and no glGet per shape.
struct BoundTexture
{
    GLuint texture = 0;
    unsigned stamp = 0;
};

struct ContextTextures
{
    BoundTexture shadow;
    BoundTexture ambientOcclusion;
};

std::unordered_map<QOpenGLContext*, ContextTextures>& contextTextures()
{
    static std::unordered_map<QOpenGLContext*, ContextTextures> textures;
    return textures;
}

/// Bind texture on unit unless it is already bound there with the same stamp; the active unit is
/// restored. Only a (re)bind queries the active unit.
void bindOnUnit(QOpenGLContext* context, int unit, GLuint texture, unsigned stamp, BoundTexture& bound)
{
    if (bound.texture == texture && bound.stamp == stamp) {
        return;
    }
    QOpenGLFunctions* gl = context->functions();
    GLint active = GL_TEXTURE0;
    gl->glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
    gl->glActiveTexture(GL_TEXTURE0 + unit);
    gl->glBindTexture(GL_TEXTURE_2D, texture);
    gl->glActiveTexture(GLenum(active));
    bound.texture = texture;
    bound.stamp = stamp;
}

// Soft shadow filter (decision D4: fixed world sun, see ShadowMath.h). Shadows only darken the
// lighting the shader computes anyway (fc_face_shading.frag), so lit areas are unchanged.
constexpr float shadowFilterRadiusTexels = 5.0F;

std::unordered_map<QOpenGLContext*, ContextProgram>& contextPrograms()
{
    static std::unordered_map<QOpenGLContext*, ContextProgram> programs;
    return programs;
}

int maxLightsFor()
{
    return std::clamp(int(SoGLLightIdElement::getMaxGLSources()), 1, shaderMaxLights);
}

/// Compile and link the face program in the current context. On failure, returns nullptr and sets
/// error. The program has no parent.
std::unique_ptr<QOpenGLShaderProgram> compileFaceProgram(QOpenGLContext* context, std::string& error)
{
    const GLContextInfo info = queryCurrentContext();
    const CapabilityReport report = evaluateCapabilities(info);
    if (!report.enhancedShading) {
        error = report.reason;
        return nullptr;
    }
    if (!QOpenGLShaderProgram::hasOpenGLShaderPrograms(context)) {
        error = "the OpenGL context has no shader program support";
        return nullptr;
    }

    const ShaderDefines defines {
        {"FC_MAX_LIGHTS", std::to_string(maxLightsFor())},
        {"FC_ENV_LIGHTS", std::to_string(environmentLightCount)},
    };
    const std::string vertex = buildShaderSource(ShaderId::FaceShadingVertex, defines);
    const std::string fragment = buildShaderSource(ShaderId::FaceShadingFragment, defines);
    if (vertex.empty() || fragment.empty()) {
        error = "the face shader resources are missing";
        return nullptr;
    }

    auto program = std::make_unique<QOpenGLShaderProgram>();
    const auto renderer = " (" + info.renderer + ", GLSL " + info.glslVersion + ")";
    if (!program->addShaderFromSourceCode(QOpenGLShader::Vertex, vertex.c_str())) {
        error = "vertex shader compilation failed" + renderer + ": " + program->log().toStdString();
        return nullptr;
    }
    if (!program->addShaderFromSourceCode(QOpenGLShader::Fragment, fragment.c_str())) {
        error = "fragment shader compilation failed" + renderer + ": " + program->log().toStdString();
        return nullptr;
    }
    if (!program->link()) {
        error = "shader link failed" + renderer + ": " + program->log().toStdString();
        return nullptr;
    }
    return program;
}

const EnvironmentUniforms& environmentFor(EnvironmentPreset preset)
{
    // Computed once per preset (deterministic numerical integration, about 1 ms).
    static std::array<std::unique_ptr<EnvironmentUniforms>, 3> cache;
    auto& slot = cache.at(static_cast<size_t>(preset));
    if (!slot) {
        slot = std::make_unique<EnvironmentUniforms>(environmentUniforms(preset));
    }
    return *slot;
}

QVector3D toVector(const Rgb& color)
{
    return {color[0], color[1], color[2]};
}

/// Upload the uniforms that only change with the settings. The program must be bound.
void uploadSettingsUniforms(QOpenGLShaderProgram* program)
{
    const EnvironmentUniforms& env = environmentFor(RenderSettings::environmentPreset());

    std::array<QVector3D, 9> coefficients;
    for (size_t i = 0; i < env.irradiance.size(); ++i) {
        coefficients[i] = toVector(env.irradiance[i]);
    }
    program->setUniformValueArray("fc_sh", coefficients.data(), int(coefficients.size()));
    program->setUniformValue("fc_envDiffuseScale", GLfloat(env.diffuseScale));
    program->setUniformValue("fc_envSky", toVector(env.sky));
    program->setUniformValue("fc_envHorizon", toVector(env.horizon));
    program->setUniformValue("fc_envGround", toVector(env.ground));
    program->setUniformValue("fc_envSkyRamp", GLfloat(env.skyRamp));
    program->setUniformValue("fc_envGroundRamp", GLfloat(env.groundRamp));
    std::array<QVector3D, environmentLightCount> directions;
    std::array<QVector3D, environmentLightCount> colors;
    for (size_t i = 0; i < directions.size(); ++i) {
        directions[i] = toVector(env.lightDirection[i]);
        colors[i] = toVector(env.lightColor[i]);
    }
    program->setUniformValueArray("fc_envLightDirection", directions.data(), environmentLightCount);
    program->setUniformValueArray("fc_envLightColor", colors.data(), environmentLightCount);
    program->setUniformValueArray(
        "fc_envLightExponent",
        env.lightExponent.data(),
        environmentLightCount,
        1
    );
    program->setUniformValue("fc_exposure", GLfloat(1.0F));

    program->setUniformValue("fc_tintMode", GLint(0));
    program->setUniformValue("fc_aoMode", GLint(0));
    program->setUniformValue("fc_aoMap", GLint(ambientOcclusionUnit));
    program->setUniformValue("fc_shadowMode", GLint(0));
    program->setUniformValue("fc_shadowMap", GLint(shadowTextureUnit));
    program->setUniformValue("fc_shadowRadius", GLfloat(shadowFilterRadiusTexels));
    program->setUniformValue("fc_sunDirection", QVector3D(0.0F, 0.0F, 1.0F));
}

/// The face program of the current context, created on first use. Returns nullptr (and switches
/// the session to Classic, logging once) if the context cannot run it.
ContextProgram* acquireProgram(QOpenGLContext* context)
{
    auto& programs = contextPrograms();
    auto it = programs.find(context);
    if (it == programs.end()) {
        std::string error;
        std::unique_ptr<QOpenGLShaderProgram> program = compileFaceProgram(context, error);
        if (!program) {
            RenderSettings::disableForSession(error);
            return nullptr;
        }
        ContextProgram entry;
        entry.program = program.release();
        entry.program->setParent(context);  // deleted with the context
        entry.numLightsLocation = entry.program->uniformLocation("fc_numLights");
        entry.twoSidedLocation = entry.program->uniformLocation("fc_twoSided");
        entry.eyeToShadowLocation = entry.program->uniformLocation("fc_eyeToShadow");
        entry.sunDirectionLocation = entry.program->uniformLocation("fc_sunDirection");
        entry.shadowModeLocation = entry.program->uniformLocation("fc_shadowMode");
        entry.shadowBiasLocation = entry.program->uniformLocation("fc_shadowBias");
        entry.aoModeLocation = entry.program->uniformLocation("fc_aoMode");
        entry.aoViewportLocation = entry.program->uniformLocation("fc_aoViewport");
        entry.shadowTexelLocation = entry.program->uniformLocation("fc_shadowTexel");
        entry.tintModeLocation = entry.program->uniformLocation("fc_tintMode");
        entry.tintLocation = entry.program->uniformLocation("fc_tint");
        entry.eyeToEnvironmentLocation = entry.program->uniformLocation("fc_eyeToEnvironment");
        entry.maxLights = maxLightsFor();
        QObject::connect(
            context,
            &QOpenGLContext::aboutToBeDestroyed,
            context,
            [context]() {
                // The context may be re-created (QOpenGLWidget re-parenting): forget the program
                // now; Qt invalidates its GL objects with the context, the QObject goes later.
                auto& all = contextPrograms();
                auto found = all.find(context);
                if (found != all.end()) {
                    found->second.program->deleteLater();
                    all.erase(found);
                }
                contextTextures().erase(context);
            },
            Qt::DirectConnection
        );
        it = programs.emplace(context, entry).first;
    }
    return &it->second;
}

QMatrix4x4 toQMatrix(const SbMatrix& matrix)
{
    // Coin stores matrices in OpenGL (column-major) layout; QMatrix4x4(const float*) reads rows.
    return QMatrix4x4(matrix[0]).transposed();
}

/// The environment (sky, ground, softboxes) is fixed to the world like the sun of the shadows,
/// not to the camera: orbiting does not relight the model. The shader looks it up with +y up,
/// FreeCAD has +Z up. Program bound.
void bindEnvironment(ContextProgram& entry, SoState* state)
{
    const SbMatrix& view = SoViewingMatrixElement::get(state);
    if (entry.environmentViewSet && view == entry.lastEnvironmentView) {
        return;
    }
    entry.environmentViewSet = true;
    entry.lastEnvironmentView = view;
    const SbMatrix eyeToWorld = view.inverse();
    QMatrix3x3 eyeToEnvironment;
    const std::array<SbVec3f, 3> eyeAxes {SbVec3f(1, 0, 0), SbVec3f(0, 1, 0), SbVec3f(0, 0, 1)};
    for (int column = 0; column < 3; ++column) {
        SbVec3f world;
        eyeToWorld.multDirMatrix(eyeAxes[column], world);
        world.normalize();
        // world (x, y, z) -> environment (x, z, -y)
        eyeToEnvironment(0, column) = world[0];
        eyeToEnvironment(1, column) = world[2];
        eyeToEnvironment(2, column) = -world[1];
    }
    entry.program->setUniformValue(entry.eyeToEnvironmentLocation, eyeToEnvironment);
}

/// Set the camera-dependent shadow uniforms (program bound) and bind the shadow map on its
/// texture unit (left bound for the next shapes).
void bindShadows(QOpenGLContext* context, ContextProgram& entry, SoState* state)
{
    QOpenGLShaderProgram* program = entry.program;
    const SbMatrix& view = SoViewingMatrixElement::get(state);
    const ShadowFrame* frame = currentShadowFrame();
    const bool mapValid = frame && frame->valid;
    const unsigned stamp = mapValid ? frame->stamp : 0;
    if (view != entry.lastView || stamp != entry.lastShadowStamp
        || entry.lastShadowGeneration != entry.generation) {
        entry.lastView = view;
        entry.lastShadowStamp = stamp;
        entry.lastShadowGeneration = entry.generation;
        const Vec3 sun = defaultSunDirection();
        SbVec3f sunEye;
        view.multDirMatrix(SbVec3f(sun[0], sun[1], sun[2]), sunEye);
        sunEye.normalize();
        program->setUniformValue(entry.sunDirectionLocation, QVector3D(sunEye[0], sunEye[1], sunEye[2]));
        program->setUniformValue(entry.shadowModeLocation, GLint(mapValid ? 1 : 0));
        if (mapValid) {
            SbMatrix eyeToShadow = view.inverse();
            eyeToShadow.multRight(frame->worldToShadow);
            program->setUniformValue(entry.eyeToShadowLocation, toQMatrix(eyeToShadow));
            program->setUniformValue(entry.shadowBiasLocation, GLfloat(frame->bias));
            program->setUniformValue(entry.shadowTexelLocation, GLfloat(1.0F / float(frame->size)));
        }
    }
    if (mapValid) {
        bindOnUnit(context, shadowTextureUnit, frame->texture, frame->stamp, contextTextures()[context].shadow);
    }
}

bool nearlyEqual(const SbMatrix& a, const SbMatrix& b, float relative)
{
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            const float x = a[r][c];
            const float y = b[r][c];
            if (std::fabs(x - y) > relative * std::max(std::fabs(x), std::fabs(y)) + 1e-12F) {
                return false;
            }
        }
    }
    return true;
}

/// Enable the ambient occlusion map for this shape if it was computed for the same camera and
/// viewport (program bound), and bind it on its texture unit (left bound for the next shapes).
void bindAmbientOcclusion(QOpenGLContext* context, ContextProgram& entry, SoState* state)
{
    QOpenGLShaderProgram* program = entry.program;
    const AmbientOcclusionFrame* frame = currentAmbientOcclusionFrame();
    bool matches = frame && frame->valid;
    if (matches) {
        const SbViewportRegion& region = SoViewportRegionElement::get(state);
        const SbVec2s origin = region.getViewportOriginPixels();
        const SbVec2s size = region.getViewportSizePixels();
        matches = frame->viewport == std::array<int, 4> {origin[0], origin[1], size[0], size[1]}
            && frame->view == SoViewingMatrixElement::get(state)
            // The half-resolution prepass can round the aspect ratio by a pixel.
            && nearlyEqual(frame->projection, SoProjectionMatrixElement::get(state), 0.01F);
    }
    const int mode = matches ? 1 : 0;
    if (entry.lastAoMode != mode) {
        program->setUniformValue(entry.aoModeLocation, GLint(mode));
        entry.lastAoMode = mode;
    }
    if (!matches) {
        return;
    }
    const QVector4D aoViewport(
        float(frame->viewport[0]),
        float(frame->viewport[1]),
        1.0F / float(frame->viewport[2]),
        1.0F / float(frame->viewport[3])
    );
    if (aoViewport != entry.lastAoViewport) {
        program->setUniformValue(entry.aoViewportLocation, aoViewport);
        entry.lastAoViewport = aoViewport;
    }
    bindOnUnit(
        context,
        ambientOcclusionUnit,
        frame->texture,
        frame->stamp,
        contextTextures()[context].ambientOcclusion
    );
}

}  // namespace

bool isFaceShadingEligible(SoGLRenderAction* action)
{
    if (!action || !RenderSettings::isEnhancedActive() || isInShadowPass()) {
        return false;
    }
    SoState* state = action->getState();
    // Unlit geometry (overlays, hidden line, flat lines) keeps its exact colour.
    if (SoLazyElement::getLightModel(state) != SoLazyElement::PHONG) {
        return false;
    }
    if (SoDrawStyleElement::get(state) != SoDrawStyleElement::FILLED) {
        return false;
    }
    // Somebody else's shader (add-on, SoShadowGroup, ...) has priority.
    if (SoGLShaderProgramElement::get(state)) {
        return false;
    }
    // A vertex shader bypasses texture coordinate generation; textured faces stay Classic.
    int lastEnabledUnit = -1;
    SoMultiTextureEnabledElement::getEnabledUnits(state, lastEnabledUnit);
    if (lastEnabledUnit >= 0) {
        return false;
    }
    if (SoEnvironmentElement::getFogType(state) != SoEnvironmentElement::NONE) {
        return false;
    }
    // An emissive material stays Classic. Whole-object preselection and selection are expressed as
    // an emissive colour override: the shader draws them as a tint (FaceShadingScope), so that a
    // hovered or selected object keeps the Enhanced look.
    if (!SoOverrideElement::getEmissiveColorOverride(state)
        && SoLazyElement::getEmissive(state) != SbColor(0.0F, 0.0F, 0.0F)) {
        return false;
    }
    if (action->getTransparencyType() == SoGLRenderAction::SORTED_LAYERS_BLEND) {
        return false;
    }
    return QOpenGLContext::currentContext() != nullptr;
}

FaceShadingScope::FaceShadingScope(SoGLRenderAction* action, const SbColor* tint)
{
    // The prepasses share the viewer's cache context: a render cache recorded there around a face
    // shape would be replayed by the main pass without running the shape, so without the shader.
    if (action && isInAmbientOcclusionPrepass()) {
        SoCacheElement::invalidate(action->getState());
        recordAmbientOcclusionMatrices(action->getState());
        return;  // depth only
    }
    if (action && isInShadowPass()) {
        SoCacheElement::invalidate(action->getState());
        return;  // depth only
    }
    if (!isFaceShadingEligible(action)) {
        return;
    }
    QOpenGLContext* context = QOpenGLContext::currentContext();
    ContextProgram* entry = acquireProgram(context);
    if (!entry) {
        return;
    }
    SoState* state = action->getState();
    // Like SoShaderProgram: never let a display list record the program or its uniforms.
    SoCacheElement::invalidate(state);

    if (!entry->program->bind()) {
        return;
    }
    const unsigned generation = RenderSettings::generation();
    if (entry->generation != generation) {
        uploadSettingsUniforms(entry->program);
        entry->generation = generation;
        entry->lastNumLights = -1;  // re-upload everything below once
        entry->lastTwoSided = -1;
        entry->lastAoMode = 0;      // uploadSettingsUniforms() set it to 0
        entry->lastAoViewport = QVector4D();
        entry->lastTintMode = 0;    // same
    }
    const int lights = std::clamp(int(SoGLLightIdElement::get(state)) + 1, 0, entry->maxLights);
    if (entry->lastNumLights != lights) {
        entry->program->setUniformValue(entry->numLightsLocation, GLint(lights));
        entry->lastNumLights = lights;
    }
    const int twoSided = SoLazyElement::getTwoSidedLighting(state) ? 1 : 0;
    if (entry->lastTwoSided != twoSided) {
        entry->program->setUniformValue(entry->twoSidedLocation, GLint(twoSided));
        entry->lastTwoSided = twoSided;
    }
    SbColor tintColor(0.0F, 0.0F, 0.0F);
    bool tinted = tint != nullptr;
    if (tinted) {
        tintColor = *tint;
    }
    else if (SoOverrideElement::getEmissiveColorOverride(state)) {
        tintColor = SoLazyElement::getEmissive(state);
        tinted = tintColor != SbColor(0.0F, 0.0F, 0.0F);
    }
    const int tintMode = tinted ? 1 : 0;
    if (entry->lastTintMode != tintMode) {
        entry->program->setUniformValue(entry->tintModeLocation, GLint(tintMode));
        entry->lastTintMode = tintMode;
    }
    if (tinted) {
        entry->program->setUniformValue(entry->tintLocation, QVector3D(tintColor[0], tintColor[1], tintColor[2]));
    }
    bindEnvironment(*entry, state);
    if (RenderSettings::shadowsActive()) {
        bindShadows(context, *entry, state);
    }
    if (RenderSettings::ambientOcclusionActive()) {
        bindAmbientOcclusion(context, *entry, state);
    }
    active = true;
}

FaceShadingScope::~FaceShadingScope()
{
    if (!active) {
        return;
    }
    // The shadow and AO maps stay bound on their own units (6, 7) for the next shape: no query
    // and no restore per shape (they are only sampled by this program).
    if (QOpenGLContext* context = QOpenGLContext::currentContext()) {
        // Eligibility guarantees no program was bound before the scope.
        context->functions()->glUseProgram(0);
    }
}

bool useUnlitSelectionOverlays()
{
    return RenderSettings::isEnhancedActive();
}

std::string validateFaceShaderInCurrentContext()
{
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        return "no current OpenGL context";
    }
    std::string error;
    std::unique_ptr<QOpenGLShaderProgram> program = compileFaceProgram(context, error);
    return program ? std::string() : error;
}

}  // namespace Gui::Render
