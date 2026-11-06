#version 120
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.
//
// Enhanced face shading, fragment stage (GLSL 1.20, compatibility built-ins).
//
// Physically based looking lighting computed from the fixed-function (Phong) state that Coin
// already sets, so no per-object data is needed:
//   - diffuse colour and alpha from gl_Color (Coin sends diffuse through GL_COLOR_MATERIAL),
//   - specular colour and shininess from gl_FrontMaterial,
//   - the directional / point / spot lights from gl_LightSource[0 .. fc_numLights - 1].
// The CPU mirror of the material conversion is Gui::Render::phongToPbr() (ShadingModel.cpp);
// keep both in sync.
//
// Published formulas used (re-implemented here):
//   GGX distribution (Walter et al. 2007), height-correlated Smith visibility (Heitz 2014),
//   Schlick Fresnel (1994), Blinn-Phong exponent to GGX roughness alpha = sqrt(2 / (n + 2))
//   (Walter et al. 2007), specular-glossiness to metallic-roughness solve (Khronos glTF
//   KHR_materials_pbrSpecularGlossiness conversion notes), order-2 spherical harmonics irradiance
//   (Ramamoorthi and Hanrahan 2001), analytic environment BRDF (Karis 2014),
//   "PBR Neutral" tone mapping (Khronos 2024).

#ifndef FC_MAX_LIGHTS
#define FC_MAX_LIGHTS 8
#endif

uniform int fc_numLights;
uniform int fc_twoSided;
uniform float fc_exposure;

#ifndef FC_ENV_LIGHTS
#define FC_ENV_LIGHTS 2
#endif

// Environment (eye space, +y is up on the screen): sky / bright soft horizon / dark ground
// gradient plus FC_ENV_LIGHTS softboxes. Colours are linear and already scaled by the preset
// intensity. fc_sh holds the irradiance E(n) / pi of all of it as order-2 SH coefficients;
// diffuse lighting uses it scaled by fc_envDiffuseScale. CPU side: Gui::Render::environmentUniforms().
// Eye space to environment space (world fixed, +y up), see Gui::Render::bindEnvironment().
uniform mat3 fc_eyeToEnvironment;
uniform vec3 fc_sh[9];
uniform float fc_envDiffuseScale;
uniform vec3 fc_envSky;
uniform vec3 fc_envHorizon;
uniform vec3 fc_envGround;
uniform float fc_envSkyRamp;
uniform float fc_envGroundRamp;
uniform vec3 fc_envLightDirection[FC_ENV_LIGHTS];
uniform vec3 fc_envLightColor[FC_ENV_LIGHTS];
uniform float fc_envLightExponent[FC_ENV_LIGHTS];

// Whole-object selection / preselection (Gui::Render::FaceShadingScope): the shape is drawn in
// fc_tint (display colour), shaded by its lighting relative to the tint, so it keeps its relief
// and shows the exact preference colour where it is well lit. fc_tintMode 0: no tint.
uniform int fc_tintMode;
uniform vec3 fc_tint;

// Soft shadows (Gui::Render::SoFCShadowPass). fc_shadowMode 0: no shadow map this frame.
// fc_shadowCoord (vertex stage) is the fragment in shadow-map [0, 1] coordinates.
uniform int fc_shadowMode;
uniform sampler2D fc_shadowMap;
uniform float fc_shadowTexel;   // 1 / map size
uniform float fc_shadowBias;    // constant depth bias, see Gui::Render::shadowDepthBias()
uniform float fc_shadowRadius;  // filter radius in texels
uniform vec3 fc_sunDirection;   // towards the sun, eye space

// Fixed key light (Gui::Render::KeyLight::Sun): light fc_keyLightIndex (the headlight) keeps its
// colour and intensity but shines from fc_keyLightDirection, the world-fixed sun of the shadows
// (eye space, towards the light). -1: every light is used as Coin set it.
uniform int fc_keyLightIndex;
uniform vec3 fc_keyLightDirection;

// Screen-space ambient occlusion (Gui::Render::SoFCAmbientOcclusionPass). fc_aoMode 0: none.
// fc_aoViewport = (x, y, 1 / width, 1 / height) of the viewport the AO map was computed for.
uniform int fc_aoMode;
uniform sampler2D fc_aoMap;
uniform vec4 fc_aoViewport;

varying vec3 fc_eyePosition;
varying vec3 fc_eyeNormal;
varying vec4 fc_shadowCoord;

const float FC_PI = 3.14159265;
const float FC_DIELECTRIC_F0 = 0.04;
// Solved metalness is remapped through smoothstep(LOW, HIGH, m): classic CAD materials use a
// strong specular colour on bright plastics, which the plain solve reads as partly metallic.
const float FC_METAL_LOW = 0.35;
const float FC_METAL_HIGH = 0.75;
const float FC_METAL_TINT = 0.5;
const float FC_METAL_SPECULAR_LOW = 0.27;  // linear, about 0.55 in display values
const float FC_METAL_SPECULAR_HIGH = 0.46; // linear, about 0.70 in display values
const float FC_METAL_GLOSS_LOW = 57.6;     // GL shininess (0.45 * 128)
const float FC_METAL_GLOSS_HIGH = 89.6;    // GL shininess (0.70 * 128)
const float FC_METAL_ROUGHNESS_SCALE = 0.6;
const float FC_DIFFUSE_FALLOFF = 2.0;
// Dielectric reflections fade out below this Phong specular value (display units), so that a
// black specular colour still means "no highlight" while dark plastics keep their reflections.
const float FC_SPECULAR_FADE = 0.1;
// Share of the direct light and of the ambient (environment diffuse) removed in the sun's shadow.
const float FC_SHADOW_DIRECT = 0.55;
const float FC_SHADOW_AMBIENT = 0.5;
// Ambient occlusion fully applies to the ambient, partly to direct light and reflections (the
// headlight follows the view, so in a CAD view it acts much like ambient light).
const float FC_AO_DIRECT = 0.6;
const float FC_AO_SPECULAR = 0.6;
const int FC_SHADOW_TAPS = 12;

vec3 fcToLinear(vec3 c)
{
    return pow(max(c, vec3(0.0)), vec3(2.2));
}

vec3 fcToDisplay(vec3 c)
{
    return pow(clamp(c, 0.0, 1.0), vec3(1.0 / 2.2));
}

float fcPerceived(vec3 c)
{
    return sqrt(0.299 * c.r * c.r + 0.587 * c.g * c.g + 0.114 * c.b * c.b);
}

float fcSolveMetallic(float diffuse, float specular, float oneMinusSpecularStrength)
{
    if (specular < FC_DIELECTRIC_F0) {
        return 0.0;
    }
    float a = FC_DIELECTRIC_F0;
    float b = diffuse * oneMinusSpecularStrength / (1.0 - a) + specular - 2.0 * a;
    float c = a - specular;
    float discriminant = max(b * b - 4.0 * a * c, 0.0);
    return clamp((-b + sqrt(discriminant)) / (2.0 * a), 0.0, 1.0);
}

vec3 fcIrradiance(vec3 n)
{
    vec3 e = fc_sh[0] * 0.282095
        + fc_sh[1] * (0.488603 * n.y)
        + fc_sh[2] * (0.488603 * n.z)
        + fc_sh[3] * (0.488603 * n.x)
        + fc_sh[4] * (1.092548 * n.x * n.y)
        + fc_sh[5] * (1.092548 * n.y * n.z)
        + fc_sh[6] * (0.315392 * (3.0 * n.z * n.z - 1.0))
        + fc_sh[7] * (1.092548 * n.x * n.z)
        + fc_sh[8] * (0.546274 * (n.x * n.x - n.y * n.y));
    return max(e, vec3(0.0));
}

// Radiance of the environment along d, as reflected by a surface of GGX roughness alpha.
// blur = 0 gives the sharp environment (the CPU projects exactly that onto fc_sh). Roughness
// widens the horizon transitions, and widens each softbox lobe by adding lobe variances (a Phong
// lobe of exponent n has a variance of about 2 / (n + 2); the reflected GGX lobe about 2 alpha^2)
// while preserving its energy.
vec3 fcEnvironment(vec3 d, float alpha)
{
    float t = clamp(d.y, -1.0, 1.0);
    vec3 color;
    if (t >= 0.0) {
        color = mix(fc_envHorizon, fc_envSky, smoothstep(0.0, fc_envSkyRamp + alpha, t));
    }
    else {
        color = mix(fc_envHorizon, fc_envGround, smoothstep(0.0, fc_envGroundRamp + alpha, -t));
    }
    for (int i = 0; i < FC_ENV_LIGHTS; ++i) {
        float n = max(fc_envLightExponent[i], 1.0);
        float variance = 2.0 / (n + 2.0) + 2.0 * alpha * alpha;
        float widened = max(2.0 / variance - 2.0, 1.0);
        float c = max(dot(d, fc_envLightDirection[i]), 0.0);
        color += fc_envLightColor[i] * ((widened + 1.0) / (n + 1.0) * pow(max(c, 1e-6), widened));
    }
    return color;
}

// Prefiltered specular environment: the analytic blur above, fading to the cosine-convolved
// irradiance for very rough surfaces.
vec3 fcSpecularEnvironment(vec3 r, float alpha)
{
    return mix(fcEnvironment(r, alpha), fcIrradiance(r), alpha * alpha);
}

vec3 fcEnvironmentBRDF(vec3 f0, float roughness, float NoV)
{
    const vec4 c0 = vec4(-1.0, -0.0275, -0.572, 0.022);
    const vec4 c1 = vec4(1.0, 0.0425, 1.04, -0.04);
    vec4 r = roughness * c0 + c1;
    float a004 = min(r.x * r.x, exp2(-9.28 * NoV)) * r.x + r.y;
    vec2 ab = vec2(-1.04, 1.04) * a004 + r.zw;
    return f0 * ab.x + vec3(ab.y);
}

float fcDistributionGGX(float NoH, float alpha)
{
    float a2 = alpha * alpha;
    float d = NoH * NoH * (a2 - 1.0) + 1.0;
    return a2 / (FC_PI * d * d);
}

float fcVisibilitySmithGGX(float NoV, float NoL, float alpha)
{
    float a2 = alpha * alpha;
    float ggxV = NoL * sqrt(NoV * NoV * (1.0 - a2) + a2);
    float ggxL = NoV * sqrt(NoL * NoL * (1.0 - a2) + a2);
    return 0.5 / max(ggxV + ggxL, 1e-5);
}

vec3 fcFresnelSchlick(vec3 f0, float VoH)
{
    float f = pow(clamp(1.0 - VoH, 0.0, 1.0), 5.0);
    return f0 + (vec3(1.0) - f0) * f;
}

vec3 fcToneMap(vec3 color)
{
    // Khronos uses 0.8 - 0.04; starting later keeps specular highlights crisp on light parts.
    const float startCompression = 0.9 - 0.04;
    const float desaturation = 0.15;
    float x = min(color.r, min(color.g, color.b));
    float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
    color -= offset;
    float peak = max(color.r, max(color.g, color.b));
    if (peak < startCompression) {
        return color;
    }
    const float d = 1.0 - startCompression;
    float newPeak = 1.0 - d * d / (peak + d - startCompression);
    color *= newPeak / peak;
    float g = 1.0 - 1.0 / (desaturation * (peak - newPeak) + 1.0);
    return mix(color, vec3(newPeak), g);
}

// GGX specular (Schlick Fresnel) plus Lambert diffuse for one directional light of radiance 1.
vec3 fcDirectLight(vec3 n, vec3 v, vec3 l, float NoV, vec3 f0, vec3 diffuseColor, float alpha,
                   float specularWeight)
{
    float NoL = dot(n, l);
    if (NoL <= 0.0) {
        return vec3(0.0);
    }
    vec3 h = normalize(l + v);
    float NoH = max(dot(n, h), 0.0);
    float VoH = max(dot(v, h), 0.0);
    vec3 fresnel = fcFresnelSchlick(f0, VoH);
    vec3 specular = fresnel
        * (fcDistributionGGX(NoH, alpha) * fcVisibilitySmithGGX(NoV, NoL, alpha) * FC_PI
           * specularWeight);
    vec3 diffuse = (vec3(1.0) - fresnel) * diffuseColor;
    // FC_DIFFUSE_FALLOFF > 1 steepens the Lambert falloff towards what the classic
    // (display-space) lighting shows, so that faces of a CAD part keep distinct shades.
    return diffuse * pow(NoL, FC_DIFFUSE_FALLOFF) + specular * NoL;
}

// Slope-scaled depth bias: constant * tan(angle to the sun), clamped (Gui::Render::slopeScaledBias).
float fcSlopeBias(float NoL)
{
    float c = clamp(NoL, 0.05, 1.0);
    float tangent = sqrt(1.0 - c * c) / c;
    return clamp(fc_shadowBias * tangent, fc_shadowBias, 10.0 * fc_shadowBias);
}

// Fraction of the sun visible from this fragment: percentage-closer filtering over a golden-angle
// (Vogel) spiral of FC_SHADOW_TAPS taps (Gui::Render::shadowSampleDisk), rotated per pixel to
// trade banding for fine noise.
float fcShadowVisibility(float NoL)
{
    if (fc_shadowMode == 0) {
        return 1.0;
    }
    vec3 c = fc_shadowCoord.xyz / fc_shadowCoord.w;
    if (c.x <= 0.0 || c.x >= 1.0 || c.y <= 0.0 || c.y >= 1.0 || c.z >= 1.0) {
        return 1.0;
    }
    if (NoL <= 0.0) {
        return 1.0;  // facing away from the sun: left to the normal lighting
    }
    float reference = c.z - fcSlopeBias(NoL);
    float rotation = 6.2831853 * fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    float lit = 0.0;
    for (int i = 0; i < FC_SHADOW_TAPS; ++i) {
        float r = sqrt((float(i) + 0.5) / float(FC_SHADOW_TAPS));
        float a = float(i) * 2.39996323 + rotation;
        vec2 offset = vec2(cos(a), sin(a)) * (r * fc_shadowRadius * fc_shadowTexel);
        float depth = texture2D(fc_shadowMap, c.xy + offset).r;
        lit += reference <= depth ? 1.0 : 0.0;
    }
    return lit / float(FC_SHADOW_TAPS);
}

// Ambient visibility of this pixel from the half-resolution AO map, smoothed by four bilinear
// taps (the AO map is noisy by design: its sample pattern rotates per pixel).
float fcAmbientOcclusion()
{
    if (fc_aoMode == 0) {
        return 1.0;
    }
    vec2 uv = (gl_FragCoord.xy - fc_aoViewport.xy) * fc_aoViewport.zw;
    vec2 d = 2.5 * fc_aoViewport.zw;
    float ao = texture2D(fc_aoMap, uv + vec2(-d.x, -d.y)).r + texture2D(fc_aoMap, uv + vec2(d.x, -d.y)).r
        + texture2D(fc_aoMap, uv + vec2(-d.x, d.y)).r + texture2D(fc_aoMap, uv + vec2(d.x, d.y)).r;
    return clamp(0.25 * ao, 0.0, 1.0);
}

void main()
{
    vec3 n = fc_eyeNormal;
    if (dot(n, n) < 1e-12) {
        n = vec3(0.0, 0.0, 1.0);
    }
    n = normalize(n);
    if (fc_twoSided != 0 && !gl_FrontFacing) {
        n = -n;
    }

    // Like the fixed-function pipeline (no local viewer) an orthographic view looks along -z.
    bool orthographic = gl_ProjectionMatrix[3][3] > 0.5;
    vec3 v = orthographic ? vec3(0.0, 0.0, 1.0) : normalize(-fc_eyePosition);
    float NoV = max(dot(n, v), 1e-4);

    // Phong material -> metallic / roughness.
    vec3 diffuseIn = fcToLinear(fc_tintMode != 0 ? fc_tint : gl_Color.rgb);
    vec3 specularIn = fcToLinear(gl_FrontMaterial.specular.rgb);
    float shininess = max(gl_FrontMaterial.shininess, 0.0);
    float alpha = clamp(sqrt(2.0 / (shininess + 2.0)), 0.045, 1.0);
    float roughness = sqrt(alpha);

    float specularStrength = max(specularIn.r, max(specularIn.g, specularIn.b));
    float oneMinus = 1.0 - specularStrength;
    float solved = fcSolveMetallic(fcPerceived(diffuseIn), fcPerceived(specularIn), oneMinus);
    vec3 fromDiffuse = diffuseIn * (oneMinus / (1.0 - FC_DIELECTRIC_F0) / max(1.0 - solved, 1e-4));
    vec3 fromSpecular = (specularIn - vec3(FC_DIELECTRIC_F0) * (1.0 - solved)) / max(solved, 1e-4);
    vec3 solvedBase = clamp(mix(fromDiffuse, fromSpecular, solved * solved), 0.0, 1.0);
    // Classic metal presets put the hue in the (dark) diffuse colour and a pale specular colour:
    // keep part of the diffuse hue so that gold does not turn into pale brass.
    float diffuseMax = max(diffuseIn.r, max(diffuseIn.g, diffuseIn.b));
    vec3 hue = diffuseMax > 1e-3 ? diffuseIn / diffuseMax : vec3(1.0);
    solvedBase = mix(solvedBase, solvedBase * hue, FC_METAL_TINT);
    // Only a strong specular colour (above the default 0.5333 grey) on a not ultra glossy material
    // reads as metal: a part coloured black with the default specular, or the Shiny plastic
    // preset, stays a plastic.
    float specularGate = smoothstep(FC_METAL_SPECULAR_LOW, FC_METAL_SPECULAR_HIGH, specularStrength);
    float glossGate = 1.0 - smoothstep(FC_METAL_GLOSS_LOW, FC_METAL_GLOSS_HIGH, shininess);
    float metallic = smoothstep(FC_METAL_LOW, FC_METAL_HIGH, solved) * specularGate * glossGate;
    // Classic metal presets use a low shininess to get a broad highlight; polish them a bit.
    alpha = max(alpha * mix(1.0, FC_METAL_ROUGHNESS_SCALE, metallic), 0.045);
    roughness = sqrt(alpha);
    vec3 baseColor = mix(diffuseIn, solvedBase, metallic);
    // A zero specular colour keeps meaning "no highlight".
    float specularWeight = mix(
        min(1.0, fcPerceived(max(gl_FrontMaterial.specular.rgb, vec3(0.0))) / FC_SPECULAR_FADE),
        1.0,
        metallic
    );
    vec3 f0 = mix(vec3(FC_DIELECTRIC_F0), baseColor, metallic);
    vec3 diffuseColor = baseColor * (1.0 - metallic);

    vec3 color = vec3(0.0);
    for (int i = 0; i < FC_MAX_LIGHTS; ++i) {
        if (i >= fc_numLights) {
            break;
        }
        vec4 position = gl_LightSource[i].position;
        vec3 l;
        float attenuation = 1.0;
        if (i == fc_keyLightIndex) {
            l = fc_keyLightDirection;
        }
        else if (position.w == 0.0) {
            l = normalize(position.xyz);
        }
        else {
            vec3 toLight = position.xyz / position.w - fc_eyePosition;
            float dist = length(toLight);
            l = toLight / max(dist, 1e-6);
            attenuation = 1.0
                / max(gl_LightSource[i].constantAttenuation
                          + gl_LightSource[i].linearAttenuation * dist
                          + gl_LightSource[i].quadraticAttenuation * dist * dist,
                      1e-6);
            if (gl_LightSource[i].spotCutoff <= 90.0) {
                float spotCos = dot(-l, normalize(gl_LightSource[i].spotDirection));
                if (spotCos < gl_LightSource[i].spotCosCutoff) {
                    attenuation = 0.0;
                }
                else {
                    attenuation *= pow(max(spotCos, 1e-6), gl_LightSource[i].spotExponent);
                }
            }
        }
        float NoL = dot(n, l);
        if (NoL <= 0.0 || attenuation <= 0.0) {
            continue;
        }
        vec3 h = normalize(l + v);
        float NoH = max(dot(n, h), 0.0);
        float VoH = max(dot(v, h), 0.0);
        vec3 radiance = fcToLinear(gl_LightSource[i].diffuse.rgb) * attenuation;
        color += fcDirectLight(n, v, l, NoV, f0, diffuseColor, alpha, specularWeight) * radiance;
    }

    // Shadows only take light away: a surface the sun reaches looks exactly as without shadows,
    // a surface in the shadow of another part loses part of its direct and ambient light. Surfaces
    // turned away from the sun are left alone (fading in near the terminator), so switching the
    // shadows on adds shadows, not a different overall lighting.
    float sunNoL = dot(n, fc_sunDirection);
    float shadow = (1.0 - fcShadowVisibility(sunNoL)) * smoothstep(0.0, 0.2, sunNoL);
    float ao = fcAmbientOcclusion();
    color *= (1.0 - FC_SHADOW_DIRECT * shadow) * mix(1.0, ao, FC_AO_DIRECT);

    // Environment: energy split between the specular reflection (Fresnel-weighted, gives the
    // reflections of metals and a soft rim on plastics) and the diffuse ambient.
    vec3 r = reflect(-v, n);
    // The environment is fixed to the world: orbiting the camera does not relight the model.
    vec3 nEnvironment = fc_eyeToEnvironment * n;
    vec3 rEnvironment = fc_eyeToEnvironment * r;
    vec3 environmentSpecular = fcEnvironmentBRDF(f0, roughness, NoV) * specularWeight;
    color += diffuseColor * (vec3(1.0) - clamp(environmentSpecular, 0.0, 1.0)) * fcIrradiance(nEnvironment)
        * (fc_envDiffuseScale * (1.0 - FC_SHADOW_AMBIENT * shadow) * ao);
    color += fcSpecularEnvironment(rEnvironment, alpha) * environmentSpecular * mix(1.0, ao, FC_AO_SPECULAR);

    color *= fc_exposure;
    vec3 display = fcToDisplay(fcToneMap(color));
    if (fc_tintMode != 0) {
        // Brightness relative to the tint: 1 on a well lit area (exact colour), less on the
        // turned-away and shadowed sides; highlights do not wash the colour out.
        vec3 luma = vec3(0.2126, 0.7152, 0.0722);
        float shade = dot(display, luma) / max(dot(fc_tint, luma), 1e-3);
        display = fc_tint * clamp(0.3 + 0.8 * shade, 0.0, 1.0);
    }
    gl_FragColor = vec4(display, gl_Color.a);
}
