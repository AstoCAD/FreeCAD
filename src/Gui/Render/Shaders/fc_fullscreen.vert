#version 120
// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileNotice: Part of the FreeCAD project.
//
// Full-screen pass (FXAA, ambient occlusion): the quad is given in clip space with its texture
// coordinates in texture unit 0's coordinate set.

void main()
{
    gl_TexCoord[0] = gl_MultiTexCoord0;
    gl_Position = vec4(gl_Vertex.xy, 0.0, 1.0);
}
