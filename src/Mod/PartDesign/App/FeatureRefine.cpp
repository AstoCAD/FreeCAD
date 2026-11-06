// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2024 <bgbsww@gmail.com>                                  *
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#include <BRep_Builder.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <BRepCheck_Shell.hxx>
#include <Standard_Failure.hxx>
#include <TopExp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Compound.hxx>
#include <TopTools_IndexedMapOfShape.hxx>

#include <App/Application.h>
#include <App/FeaturePythonPyImp.h>
#include <Base/Exception.h>
#include <Base/Parameter.h>
#include <Mod/Part/App/modelRefine.h>

#include "FeatureRefine.h"
#include "FeaturePy.h"


using namespace PartDesign;

namespace
{

/**
 * Cheap validity check of a refine result.
 *
 * Refine only rebuilds the faces it unites, plus the neighbouring faces whose boundary was
 * changed by sewing or edge fusion: every other face of the result is the very same face
 * (same TShape and location) as in the input, with the same wires, edges and vertices. So
 * instead of analysing the whole shape, only the faces that are not in the input are checked
 * (with their wires, edges and vertices), together with the closure and orientation of the
 * shells of the solids, which tie the faces together.
 *
 * Returns true when no problem was found. A false result is not a verdict: the caller then
 * runs the full check.
 */
bool refineResultLooksValid(const TopoDS_Shape& oldShape, const TopoDS_Shape& refinedShape)
{
    if (oldShape.IsNull() || refinedShape.IsNull()) {
        return false;
    }
    TopTools_IndexedMapOfShape oldFaces;
    TopExp::MapShapes(oldShape, TopAbs_FACE, oldFaces);
    TopTools_IndexedMapOfShape newFaces;
    TopExp::MapShapes(refinedShape, TopAbs_FACE, newFaces);

    BRep_Builder builder;
    TopoDS_Compound changedFaces;
    builder.MakeCompound(changedFaces);
    bool changed = false;
    for (int i = 1; i <= newFaces.Extent(); ++i) {
        if (!oldFaces.Contains(newFaces(i))) {
            builder.Add(changedFaces, newFaces(i));
            changed = true;
        }
    }
    if (!changed) {
        // Refine did not unite anything: the faces are the input ones.
        return true;
    }
    if (!BRepCheck_Analyzer(changedFaces).IsValid()) {
        return false;
    }
    for (TopExp_Explorer xpSolid(refinedShape, TopAbs_SOLID); xpSolid.More(); xpSolid.Next()) {
        for (TopExp_Explorer xpShell(xpSolid.Current(), TopAbs_SHELL); xpShell.More();
             xpShell.Next()) {
            BRepCheck_Shell checkShell(TopoDS::Shell(xpShell.Current()));
            if (checkShell.Closed() != BRepCheck_NoError
                || checkShell.Orientation() != BRepCheck_NoError) {
                return false;
            }
        }
    }
    return true;
}

}  // namespace

namespace PartDesign
{
PROPERTY_SOURCE(PartDesign::FeatureRefine, PartDesign::Feature)
const App::PropertyFloatConstraint::Constraints floatFuzzy = {-1.0, 1.0, 0.0001};

FeatureRefine::FeatureRefine()
{
    ADD_PROPERTY_TYPE(
        Refine,
        (false),
        "Part Design",
        (App::PropertyType)(App::Prop_None),
        "Refine shape (clean up redundant edges) after operations"
    );
    ADD_PROPERTY_TYPE(
        FuzzyTolerance,
        (0.0),
        "Part Design",
        (App::PropertyType)(App::Prop_None),
        "Fuzzy tolerance:\n"
        "If value > 0: use the value\n"
        "If value = 0: leave default value\n"
        "If value < 0: determine value"
    );
    FuzzyTolerance.setConstraints(&floatFuzzy);


    // init Refine property
    Base::Reference<ParameterGrp> hGrp = App::GetApplication()
                                             .GetUserParameter()
                                             .GetGroup("BaseApp")
                                             ->GetGroup("Preferences")
                                             ->GetGroup("Mod/PartDesign");
    this->Refine.setValue(hGrp->GetBool("RefineModel", true));
}

bool FeatureRefine::onlyHaveRefined()
{
    if (!Refine.isTouched()) {
        return false;
    }
    if (rawShape.isNull()) {
        return false;
    }
    std::vector<App::Property*> propList;
    getPropertyList(propList);
    for (auto prop : propList) {
        if (prop != &Refine
            /*&& prop != &SuppressedShape*/
            && prop->isTouched()) {
            return false;
        }
    }
    TopoShape result = refineShapeIfActive(rawShape);
    Shape.setValue(result);
    return true;
}
TopoShape FeatureRefine::refineShapeIfActive(
    const TopoShape& oldShape,
    const RefineErrorPolicy onError
) const
{
    if (!this->Refine.getValue()) {
        return oldShape;
    }
    TopoShape shape(oldShape);
    try {
        TopoShape refinedShape = shape.makeElementRefine();
        // Refining can break a valid shape (e.g. at the seam of a cylindrical face):
        // keep the unrefined result rather than an invalid one. Analysing the whole shape is
        // slow, so look at what refine changed first and only run the full check on doubt.
        if (refineResultLooksValid(oldShape.getShape(), refinedShape.getShape())
            || refinedShape.isValid() || !oldShape.isValid()) {
            return refinedShape;
        }
        if (onError == RefineErrorPolicy::Raise) {
            throw Base::RuntimeError("Refine produced an invalid shape");
        }
        Base::Console().developerWarning(
            getFullLabel(),
            "Refine produced an invalid shape; keeping the unrefined shape."
        );
        return oldShape;
    }
    catch (Standard_Failure& err) {
        if (onError == RefineErrorPolicy::Warn) {
            Base::Console().warning("Refine failed: {}", err.GetMessageString());
        }
        else {
            throw;
        }
    }
    return oldShape;
}

}  // namespace PartDesign


namespace App
{
/// @cond DOXERR
PROPERTY_SOURCE_TEMPLATE(PartDesign::FeatureRefinePython, PartDesign::FeatureRefine)
template<>
const char* PartDesign::FeatureRefinePython::getViewProviderName() const
{
    return "PartDesignGui::ViewProviderPython";
}
template<>
PyObject* PartDesign::FeatureRefinePython::getPyObject()
{
    if (PythonObject.is(Py::_None())) {
        // ref counter is set to 1
        PythonObject = Py::Object(new FeaturePythonPyT<PartDesign::FeaturePy>(this), true);
    }
    return Py::new_reference_to(PythonObject);
}
/// @endcond

// explicit template instantiation
template class PartDesignExport FeaturePythonT<PartDesign::FeatureRefine>;
}  // namespace App
