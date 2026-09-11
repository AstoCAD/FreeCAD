// SPDX-License-Identifier: LGPL-2.1-or-later

#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepCheck_Analyzer.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <Base/Exception.h>
#include "FeatureGordonSurface.h"
#include "GordonSurfaceBuilder.h"

using namespace Surface;
PROPERTY_SOURCE(Surface::GordonSurface, Part::Spline)

GordonSurface::GordonSurface()
{
    ADD_PROPERTY_TYPE(Profiles, (nullptr), "Network", App::Prop_None, "Curves in the first direction");
    ADD_PROPERTY_TYPE(Guides, (nullptr), "Network", App::Prop_None, "Curves crossing every profile");
    Profiles.setScope(App::LinkScope::Global);
    Guides.setScope(App::LinkScope::Global);
    ADD_PROPERTY_TYPE(
        Tolerance,
        (0.001),
        "Surface",
        App::Prop_None,
        "Maximum intersection and fitting error in model units"
    );
    static const App::PropertyFloatConstraint::Constraints toleranceRange {1e-7, 1e3, 0.001};
    Tolerance.setConstraints(&toleranceRange);
    ADD_PROPERTY_TYPE(
        MaxSamples,
        (128),
        "Surface",
        App::Prop_None,
        "Maximum interpolation samples in each direction"
    );
    static const App::PropertyIntegerConstraint::Constraints sampleRange {8, 512, 8};
    MaxSamples.setConstraints(&sampleRange);
    ADD_PROPERTY_TYPE(FlipNormal, (false), "Surface", App::Prop_None, "Reverse the face orientation");
    ADD_PROPERTY_TYPE(
        ApproximationError,
        (0.0),
        "Surface",
        App::Prop_ReadOnly,
        "Largest measured error against the curve network"
    );
}

short GordonSurface::mustExecute() const
{
    return Profiles.isTouched() || Guides.isTouched() || Tolerance.isTouched()
            || MaxSamples.isTouched() || FlipNormal.isTouched()
        ? 1
        : Part::Spline::mustExecute();
}

namespace
{
std::vector<TopoDS_Edge> edges(const App::PropertyLinkSubList& links)
{
    std::vector<TopoDS_Edge> result;
    const auto objects = links.getValues();
    const auto names = links.getSubValues();
    for (size_t i = 0; i < objects.size(); ++i) {
        auto shape = Part::Feature::getShape(
            objects[i],
            Part::ShapeOption::ResolveLink | Part::ShapeOption::Transform
                | Part::ShapeOption::NeedSubElement,
            names[i].c_str()
        );
        if (shape.IsNull() || TopExp_Explorer(shape, TopAbs_FACE).More()) {
            throw Base::ValueError("The network must contain curves, not faces or empty objects.");
        }
        for (TopExp_Explorer it(shape, TopAbs_EDGE); it.More(); it.Next()) {
            auto edge = TopoDS::Edge(it.Current());
            for (const auto& existing : result) {
                if (edge.IsSame(existing)) {
                    throw Base::ValueError("A curve occurs more than once in the network.");
                }
            }
            result.push_back(edge);
        }
    }
    return result;
}
}  // namespace

App::DocumentObjectExecReturn* GordonSurface::execute()
{
    try {
        double error = 0.0;
        auto surface = buildGordonSurface(
            edges(Profiles),
            edges(Guides),
            Tolerance.getValue(),
            static_cast<int>(MaxSamples.getValue()),
            error
        );
        auto face = BRepBuilderAPI_MakeFace(surface, Tolerance.getValue()).Face();
        if (FlipNormal.getValue()) {
            face.Reverse();
        }
        if (!BRepCheck_Analyzer(face).IsValid()) {
            throw Base::ValueError("The curve network produced an invalid surface.");
        }
        Shape.setValue(face);
        ApproximationError.setValue(error);
        return StdReturn;
    }
    catch (const Standard_Failure& error) {
        Shape.setValue(TopoDS_Shape());
        return new App::DocumentObjectExecReturn(error.GetMessageString());
    }
    catch (const Base::Exception& error) {
        Shape.setValue(TopoDS_Shape());
        return new App::DocumentObjectExecReturn(error.what());
    }
}
