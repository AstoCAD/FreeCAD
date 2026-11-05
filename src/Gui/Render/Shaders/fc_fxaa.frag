#version 120
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.
//
// Fast approximate anti-aliasing of the rendered image, re-implemented from the published
// description of FXAA (T. Lottes, NVIDIA 2009/2011, "low quality" variant): estimate the local
// edge direction from the luma of the four diagonal neighbours, blur along it with a span
// proportional to the contrast, and keep the wider blur only if its luma stays within the
// neighbourhood range (otherwise it crossed a detail).

uniform sampler2D fc_source;
uniform vec2 fc_texel;  // 1 / source size

const float FC_FXAA_SPAN_MAX = 8.0;
const float FC_FXAA_REDUCE_MUL = 1.0 / 8.0;
const float FC_FXAA_REDUCE_MIN = 1.0 / 128.0;

float fcLuma(vec3 c)
{
    return dot(c, vec3(0.299, 0.587, 0.114));
}

void main()
{
    vec2 uv = gl_TexCoord[0].xy;
    vec4 center = texture2D(fc_source, uv);
    float lumaM = fcLuma(center.rgb);
    float lumaNW = fcLuma(texture2D(fc_source, uv + vec2(-1.0, -1.0) * fc_texel).rgb);
    float lumaNE = fcLuma(texture2D(fc_source, uv + vec2(1.0, -1.0) * fc_texel).rgb);
    float lumaSW = fcLuma(texture2D(fc_source, uv + vec2(-1.0, 1.0) * fc_texel).rgb);
    float lumaSE = fcLuma(texture2D(fc_source, uv + vec2(1.0, 1.0) * fc_texel).rgb);
    float lumaMin = min(lumaM, min(min(lumaNW, lumaNE), min(lumaSW, lumaSE)));
    float lumaMax = max(lumaM, max(max(lumaNW, lumaNE), max(lumaSW, lumaSE)));

    vec2 dir = vec2(-((lumaNW + lumaNE) - (lumaSW + lumaSE)), (lumaNW + lumaSW) - (lumaNE + lumaSE));
    float reduce = max((lumaNW + lumaNE + lumaSW + lumaSE) * 0.25 * FC_FXAA_REDUCE_MUL, FC_FXAA_REDUCE_MIN);
    float scale = 1.0 / (min(abs(dir.x), abs(dir.y)) + reduce);
    dir = clamp(dir * scale, vec2(-FC_FXAA_SPAN_MAX), vec2(FC_FXAA_SPAN_MAX)) * fc_texel;

    vec3 narrow = 0.5 * (texture2D(fc_source, uv + dir * (1.0 / 3.0 - 0.5)).rgb
                         + texture2D(fc_source, uv + dir * (2.0 / 3.0 - 0.5)).rgb);
    vec3 wide = 0.5 * narrow
        + 0.25 * (texture2D(fc_source, uv - 0.5 * dir).rgb + texture2D(fc_source, uv + 0.5 * dir).rgb);
    float lumaWide = fcLuma(wide);
    vec3 result = (lumaWide < lumaMin || lumaWide > lumaMax) ? narrow : wide;
    gl_FragColor = vec4(result, center.a);
}
