// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2023 Werner Mayer
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1            *
 *   of the License, or (at your option) any later version.                   *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful,               *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty              *
 *   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                  *
 *   See the GNU Lesser General Public License for more details.              *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD. If not, see https://www.gnu.org/licenses     *
 *                                                                            *
 ******************************************************************************/


#include <algorithm>
#include <boost/core/ignore_unused.hpp>
#include <Standard_Version.hxx>
#include <BRep_Tool.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <Precision.hxx>
#include <TColStd_IndexedDataMapOfStringString.hxx>
#include <TDF_LabelSequence.hxx>
#include <Message_ProgressRange.hxx>
#include <RWGltf_CafWriter.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <XCAFDoc_DocumentTool.hxx>
#include <XCAFDoc_ShapeTool.hxx>

#include "WriterGltf.h"
#include <App/Application.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <Mod/Part/App/encodeFilename.h>
#include <Mod/Part/App/Tools.h>

using namespace Import;

namespace
{

bool hasFaceWithoutTriangulation(const TopoDS_Shape& shape)
{
    for (TopExp_Explorer xp(shape, TopAbs_FACE); xp.More(); xp.Next()) {
        TopLoc_Location location;
        if (BRep_Tool::Triangulation(TopoDS::Face(xp.Current()), location).IsNull()) {
            return true;
        }
    }
    return false;
}

// glTF only stores triangle meshes and RWGltf_CafWriter skips every face without a
// triangulation. In the GUI the view providers have usually triangulated the shapes already,
// but hidden objects, transformed copies and shapes exported without GUI have none. Mesh those
// with the parameters of the 3D view so that the result does not depend on the GUI. Shapes that
// are completely triangulated are left untouched.
void triangulateShapes(Handle(TDocStd_Document) hDoc)
{
    ParameterGrp::handle hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Part"
    );
    const double deviation = hGrp->GetFloat("MeshDeviation", 0.2);                  // NOLINT
    const double angularDeflection = hGrp->GetFloat("MeshAngularDeflection", 28.5);  // NOLINT

    Handle(XCAFDoc_ShapeTool) aShapeTool = XCAFDoc_DocumentTool::ShapeTool(hDoc->Main());
    TDF_LabelSequence shapeLabels;
    aShapeTool->GetShapes(shapeLabels);
    for (Standard_Integer i = 1; i <= shapeLabels.Length(); i++) {
        const TDF_Label& label = shapeLabels.Value(i);
        // the components of an assembly refer to top-level shapes, which are meshed themselves
        if (aShapeTool->IsAssembly(label)) {
            continue;
        }
        TopoDS_Shape shape = aShapeTool->GetShape(label);
        if (shape.IsNull() || !hasFaceWithoutTriangulation(shape)) {
            continue;
        }
        const double deflection
            = std::max(Part::Tools::getDeflection(shape, deviation), Precision::Confusion());
        BRepMesh_IncrementalMesh(
            shape,
            deflection,
            /*isRelative*/ Standard_False,
            Base::toRadians(angularDeflection),
            /*isInParallel*/ Standard_True
        );
    }
}

}  // namespace

WriterGltf::WriterGltf(const Base::FileInfo& file)  // NOLINT
    : file {file}
{}

void WriterGltf::write(Handle(TDocStd_Document) hDoc) const  // NOLINT
{
    triangulateShapes(hDoc);

    std::string utf8Name = file.filePath();
    std::string name8bit = Part::encodeFilename(utf8Name);

    TColStd_IndexedDataMapOfStringString aMetadata;
    RWGltf_CafWriter aWriter(name8bit.c_str(), file.hasExtension("glb"));
    aWriter.SetTransformationFormat(RWGltf_WriterTrsfFormat_Compact);
    // https://github.com/KhronosGroup/glTF/blob/master/specification/2.0/README.md#coordinate-system-and-units
    aWriter.ChangeCoordinateSystemConverter().SetInputLengthUnit(0.001);  // NOLINT
    aWriter.ChangeCoordinateSystemConverter().SetInputCoordinateSystem(RWMesh_CoordinateSystem_Zup);
#if OCC_VERSION_HEX >= 0x070700
    aWriter.SetParallel(true);
#endif
    Standard_Boolean ret = aWriter.Perform(hDoc, aMetadata, Message_ProgressRange());
    if (!ret) {
        throw Base::FileException("Cannot save to file: ", file);
    }
}
