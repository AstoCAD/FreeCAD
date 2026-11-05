#version 120
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.
//
// Screen-space ambient occlusion from a depth prepass (normal-oriented hemisphere sampling, after
// the published Crytek 2007 / "SSAO with normal-oriented hemisphere" technique, re-implemented).
// The view-space position comes from the depth through the inverse projection, the normal from
// the depth of the neighbour pixels, so only the depth of the prepass is needed. Output: ambient
// visibility (1 = open, 0 = fully occluded) in .r, sampled by fc_face_shading.frag.

uniform sampler2D fc_depth;
uniform mat4 fc_projection;
uniform mat4 fc_inverseProjection;
uniform vec2 fc_texel;          // 1 / depth map size
uniform float fc_aoRadius;      // fraction of the visible height at the fragment
uniform float fc_aoStrength;

const int FC_AO_TAPS = 12;

vec3 fcViewPosition(vec2 uv)
{
    float d = texture2D(fc_depth, uv).r;
    vec4 v = fc_inverseProjection * vec4(uv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
    return v.xyz / v.w;
}

void main()
{
    vec2 uv = gl_TexCoord[0].xy;
    float depth = texture2D(fc_depth, uv).r;
    if (depth >= 1.0) {
        gl_FragColor = vec4(1.0);  // background: nothing to occlude
        return;
    }
    vec3 p = fcViewPosition(uv);
    // Normal from the smaller of the forward / backward depth differences (avoids smearing over
    // silhouettes).
    vec3 px0 = fcViewPosition(uv - vec2(fc_texel.x, 0.0)) - p;
    vec3 px1 = fcViewPosition(uv + vec2(fc_texel.x, 0.0)) - p;
    vec3 py0 = fcViewPosition(uv - vec2(0.0, fc_texel.y)) - p;
    vec3 py1 = fcViewPosition(uv + vec2(0.0, fc_texel.y)) - p;
    vec3 dx = abs(px0.z) < abs(px1.z) ? -px0 : px1;
    vec3 dy = abs(py0.z) < abs(py1.z) ? -py0 : py1;
    vec3 n = normalize(cross(dx, dy));
    bool orthographic = fc_projection[3][3] > 0.5;
    vec3 toViewer = orthographic ? vec3(0.0, 0.0, 1.0) : normalize(-p);
    if (dot(n, toViewer) < 0.0) {
        n = -n;
    }

    // Radius proportional to the visible height at this depth: the same look at every zoom.
    float visibleHeight = orthographic ? 2.0 / fc_projection[1][1] : 2.0 * max(-p.z, 1e-6) / fc_projection[1][1];
    float radius = fc_aoRadius * visibleHeight;

    // Tangent frame rotated per pixel (interleaved gradient noise).
    float angle = 6.2831853 * fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    vec3 helper = abs(n.z) < 0.9 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
    vec3 t = normalize(cross(helper, n));
    vec3 b = cross(n, t);
    vec3 tr = t * cos(angle) + b * sin(angle);
    vec3 br = cross(n, tr);

    float occlusion = 0.0;
    for (int i = 0; i < FC_AO_TAPS; ++i) {
        float k = (float(i) + 0.5) / float(FC_AO_TAPS);
        float a = float(i) * 2.39996323;
        float r = sqrt(k);
        // Hemisphere direction (golden-angle spiral), more samples close to the point.
        vec3 dir = tr * (r * cos(a)) + br * (r * sin(a)) + n * sqrt(max(1.0 - k, 0.0));
        float scale = mix(0.15, 1.0, k * k);
        vec3 s = p + dir * (radius * scale);
        vec4 clip = fc_projection * vec4(s, 1.0);
        vec2 suv = clip.xy / clip.w * 0.5 + 0.5;
        float sceneZ = fcViewPosition(suv).z;
        float range = smoothstep(0.0, 1.0, radius / max(abs(p.z - sceneZ), 1e-6));
        // The bias keeps flat and gently curved surfaces from occluding themselves through the
        // half-resolution depth quantization.
        occlusion += (sceneZ >= s.z + 0.1 * radius ? 1.0 : 0.0) * range;
    }
    float visibility = 1.0 - fc_aoStrength * occlusion / float(FC_AO_TAPS);
    gl_FragColor = vec4(vec3(clamp(visibility, 0.0, 1.0)), 1.0);
}
