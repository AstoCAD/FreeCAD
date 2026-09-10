// SPDX-License-Identifier: LGPL-2.1-or-later

#include <algorithm>

#include <BRepAlgoAPI_Section.hxx>
#include <BRepBndLib.hxx>
#include <BRepPrimAPI_MakePrism.hxx>
#include <Bnd_Box.hxx>
#include <Precision.hxx>
#include <TopExp_Explorer.hxx>
#include <gp_Trsf.hxx>

#include <Base/Exception.h>
#include <Mod/Part/App/FeatureExtrusion.h>

#include "FeatureIntersectionCurve.h"

using namespace Surface;

PROPERTY_SOURCE(Surface::IntersectionCurve, Part::Feature)

IntersectionCurve::IntersectionCurve()
{
    ADD_PROPERTY_TYPE(Curve1, (nullptr), "Intersection", App::Prop_None, "First sketch or wire");
    ADD_PROPERTY_TYPE(Curve2, (nullptr), "Intersection", App::Prop_None, "Second sketch or wire");
    ADD_PROPERTY_TYPE(
        Direction1,
        (0.0, 0.0, 0.0),
        "Intersection",
        App::Prop_None,
        "First extrusion direction in document coordinates; zero uses the profile normal"
    );
    ADD_PROPERTY_TYPE(
        Direction2,
        (0.0, 0.0, 0.0),
        "Intersection",
        App::Prop_None,
        "Second extrusion direction in document coordinates; zero uses the profile normal"
    );
    Curve1.setScope(App::LinkScope::Global);
    Curve2.setScope(App::LinkScope::Global);
}

short IntersectionCurve::mustExecute() const
{
    if (Curve1.isTouched() || Curve2.isTouched() || Direction1.isTouched() || Direction2.isTouched()) {
        return 1;
    }
    return Part::Feature::mustExecute();
}

namespace
{
TopoDS_Shape profileShape(const App::PropertyLink& link)
{
    const auto shape = Part::Feature::getShape(
        link.getValue(),
        Part::ShapeOption::ResolveLink | Part::ShapeOption::Transform
    );
    if (shape.IsNull() || !TopExp_Explorer(shape, TopAbs_EDGE).More()
        || TopExp_Explorer(shape, TopAbs_FACE).More()) {
        throw Base::ValueError("Select sketches or wires containing edges and no faces.");
    }
    return shape;
}

gp_Vec extrusionDirection(const App::PropertyLink& link, const App::PropertyVector& property)
{
    auto direction = property.getValue();
    if (direction.Length() <= Precision::Confusion()) {
        direction = Part::Extrusion::calculateShapeNormal(link);
    }
    gp_Vec result(direction.x, direction.y, direction.z);
    if (result.Magnitude() <= Precision::Confusion()) {
        throw Base::ValueError(
            "Cannot determine an extrusion direction; set Direction1 or Direction2."
        );
    }
    return result.Normalized();
}

TopoDS_Shape extrude(const TopoDS_Shape& profile, const gp_Vec& direction, double extent)
{
    gp_Trsf shift;
    shift.SetTranslation(direction * -extent);
    BRepPrimAPI_MakePrism prism(profile.Moved(TopLoc_Location(shift)), direction * (2.0 * extent), true);
    if (!prism.IsDone()) {
        throw Base::ValueError("Could not extrude an input curve.");
    }
    return prism.Shape();
}
}  // namespace

App::DocumentObjectExecReturn* IntersectionCurve::execute()
{
    // Clear a previous result so a failed recompute cannot display an obsolete curve.
    Shape.setValue(TopoDS_Shape());
    try {
        if (!Curve1.getValue() || !Curve2.getValue() || Curve1.getValue() == Curve2.getValue()) {
            throw Base::ValueError("Two different sketches or wires are required.");
        }
        const auto first = profileShape(Curve1);
        const auto second = profileShape(Curve2);
        const auto direction1 = extrusionDirection(Curve1, Direction1);
        const auto direction2 = extrusionDirection(Curve2, Direction2);
        const double sine = direction1.Crossed(direction2).Magnitude();
        if (sine <= Precision::Angular()) {
            throw Base::ValueError("The extrusion directions must not be parallel.");
        }

        Bnd_Box bounds;
        BRepBndLib::Add(first, bounds);
        BRepBndLib::Add(second, bounds);
        // For p + t*d1 = q + u*d2, |t| and |u| <= |q-p| / sin(angle).
        // This bounds both extrusions even for distant profiles and oblique directions.
        const double extent = std::max(bounds.CornerMin().Distance(bounds.CornerMax()), 1.0) / sine
            + 10.0 * Precision::Confusion();
        BRepAlgoAPI_Section section(
            extrude(first, direction1, extent),
            extrude(second, direction2, extent),
            false
        );
        section.Approximation(true);
        section.Build();
        if (!section.IsDone()) {
            throw Base::ValueError("The intersection calculation failed.");
        }
        if (!TopExp_Explorer(section.Shape(), TopAbs_EDGE).More()) {
            throw Base::ValueError("The extruded curves do not intersect in a curve.");
        }
        // Preserve all branches, joining connected edges into wires.
        Shape.setValue(Part::TopoShape(section.Shape()).makeWires());
        return StdReturn;
    }
    catch (const Standard_Failure& error) {
        return new App::DocumentObjectExecReturn(error.GetMessageString());
    }
    catch (const Base::Exception& error) {
        return new App::DocumentObjectExecReturn(error.what());
    }
}
