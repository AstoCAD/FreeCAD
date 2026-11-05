#version 120
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.
//
// Enhanced face shading, vertex stage (GLSL 1.20, compatibility built-ins).
// Must stay invariant with the fixed-function pipeline: selection overlays are drawn without a
// shader at the same depth, so the position comes from ftransform().

// Eye coordinates -> shadow map [0, 1] coordinates (only meaningful when fc_shadowMode != 0).
uniform mat4 fc_eyeToShadow;

varying vec3 fc_eyePosition;
varying vec3 fc_eyeNormal;
varying vec4 fc_shadowCoord;

void main()
{
    vec4 eyePosition = gl_ModelViewMatrix * gl_Vertex;
    fc_eyePosition = eyePosition.xyz / eyePosition.w;
    fc_eyeNormal = gl_NormalMatrix * gl_Normal;
    gl_FrontColor = gl_Color;
    gl_BackColor = gl_Color;
    // User clip planes (Std_ToggleClipPlane, SoClipPlane) are given in eye coordinates.
    fc_shadowCoord = fc_eyeToShadow * eyePosition;
    gl_ClipVertex = eyePosition;
    gl_Position = ftransform();
}
