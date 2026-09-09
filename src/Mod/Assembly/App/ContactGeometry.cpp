// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2026 AstoCAD <hello@astocad.com>                         *
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

#include "PreCompiled.h"
#include "ContactGeometry.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <BRepAdaptor_Surface.hxx>
#include <BRepAlgoAPI_Common.hxx>
#include <BRepBndLib.hxx>
#include <BRepBuilderAPI_MakeVertex.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepClass3d_SolidClassifier.hxx>
#include <BRepClass_FaceClassifier.hxx>
#include <BRepExtrema_DistShapeShape.hxx>
#include <BRepGProp.hxx>
#include <BRep_Builder.hxx>
#include <BRep_Tool.hxx>
#include <GProp_GProps.hxx>
#include <Poly_Triangulation.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Compound.hxx>
#include <Mod/Part/App/TopoShape.h>

namespace Assembly
{
namespace
{
using Vec = Base::Vector3d;
Vec vector(const gp_Pnt& p) { return Vec(p.X(), p.Y(), p.Z()); }
gp_Pnt point(const Vec& p) { return {p.x, p.y, p.z}; }
constexpr double tolerance = 1e-7;
bool identicalPose(const Base::Placement& a, const Base::Placement& b)
{
    // Placement equality uses tolerances. A solver perturbation, however small,
    // must trigger a new geometry evaluation rather than return a stale force.
    const auto& pa = a.getPosition();
    const auto& pb = b.getPosition();
    const double* qa = a.getRotation().getValue();
    const double* qb = b.getRotation().getValue();
    return pa.x == pb.x && pa.y == pb.y && pa.z == pb.z
        && std::equal(qa, qa + 4, qb);
}
Vec transformed(const Base::Placement& placement, const Vec& value)
{
    return placement.getRotation().multVec(value) + placement.getPosition();
}

TopoDS_Shape moved(const TopoDS_Shape& shape, const Base::Placement& delta)
{
    return BRepBuilderAPI_Transform(shape, Part::TopoShape::convert(delta.toMatrix()), false).Shape();
}

struct Witness
{
    Vec point;
    Vec outward;
    double distance = 0;
    bool inside = false;
};
}

struct ContactGeometry::Shape
{
    TopoDS_Shape solid;
    Bnd_Box bounds;
    TopoDS_Compound boundary;
    struct Sample { Vec point; Vec normal; double weight; };
    std::vector<Sample> samples;
    Vec sphereCentre;
    double sphereRadius = 0;
    double surfaceArea = 0;
    double radius = 0;
    double resolution = 0;
    struct Plane { Vec point; Vec normal; TopoDS_Face face; };
    std::vector<Plane> planes;
    bool convexPlanar = true;
    bool allPlanar = true;
    std::vector<std::unique_ptr<BRepClass3d_SolidClassifier>> classifiers;
    std::vector<Bnd_Box> solidBounds;

    explicit Shape(const TopoDS_Shape& shape, bool prepareManifold): solid(shape)
    {
        BRepBndLib::Add(shape, bounds);
        double x0, y0, z0, x1, y1, z1;
        bounds.Get(x0, y0, z0, x1, y1, z1);
        radius = Vec(std::max(std::abs(x0), std::abs(x1)),
                     std::max(std::abs(y0), std::abs(y1)),
                     std::max(std::abs(z0), std::abs(z1))).Length();
        resolution = std::max(10 * tolerance, 0.01 * std::min({x1-x0, y1-y0, z1-z0}));
        if (!prepareManifold) return;
        BRep_Builder builder;
        builder.MakeCompound(boundary);
        size_t faceCount = 0;
        for (TopExp_Explorer faces(shape, TopAbs_FACE); faces.More(); faces.Next()) {
            const auto face = TopoDS::Face(faces.Current());
            builder.Add(boundary, face);
            ++faceCount;
            BRepAdaptor_Surface surface(face);
            Vec sampleNormal;
            if (surface.GetType() == GeomAbs_Plane) {
                auto plane = surface.Plane();
                auto axis = plane.Axis().Direction();
                Vec normal(axis.X(), axis.Y(), axis.Z());
                if (face.Orientation() == TopAbs_REVERSED) normal = -normal;
                sampleNormal = normal;
                planes.push_back({vector(plane.Location()), normal, face});
            }
            else { convexPlanar = false; allPlanar = false; }
            if (surface.GetType() == GeomAbs_Sphere) {
                sphereCentre = vector(surface.Sphere().Location());
                sphereRadius = surface.Sphere().Radius();
            }
            // Keep a small, deterministic surface quadrature per face, in the
            // reference geometry frame (never a world-axis-aligned proxy).
            TopLoc_Location location;
            const auto mesh = BRep_Tool::Triangulation(face, location);
            if (!mesh.IsNull()) {
                const int stride = std::max(1, mesh->NbTriangles() / 16);
                for (int i = 1; i <= mesh->NbTriangles(); i += stride) {
                    int a, b, c;
                    mesh->Triangle(i).Get(a, b, c);
                    const Vec pa = vector(mesh->Node(a).Transformed(location.Transformation()));
                    const Vec pb = vector(mesh->Node(b).Transformed(location.Transformation()));
                    const Vec pc = vector(mesh->Node(c).Transformed(location.Transformation()));
                    const double weight = (pb - pa).Cross(pc - pa).Length() * stride / 8;
                    // Interior quadrature points retain a face manifold even
                    // when all topological vertices lie on shared side faces.
                    for (const Vec& sample : {(pa + pb + pc) / 3.0,
                            pa * 0.6 + pb * 0.2 + pc * 0.2,
                            pa * 0.2 + pb * 0.6 + pc * 0.2,
                            pa * 0.2 + pb * 0.2 + pc * 0.6}) {
                        BRepExtrema_DistShapeShape projection(
                            BRepBuilderAPI_MakeVertex(point(sample)), face
                        );
                        if (projection.IsDone() && projection.NbSolution() > 0)
                            samples.push_back({vector(projection.PointOnShape2(1)), sampleNormal, weight});
                    }
                }
            }
        }
        if (faceCount != 1) sphereRadius = 0;
        for (TopExp_Explorer vertices(shape, TopAbs_VERTEX); vertices.More(); vertices.Next()) {
            const Vec vertex = vector(BRep_Tool::Pnt(TopoDS::Vertex(vertices.Current())));
            samples.push_back({vertex, Vec(), 0});
            for (const auto& plane : planes)
                if ((vertex - plane.point).Dot(plane.normal) > tolerance) convexPlanar = false;
        }
        for (TopExp_Explorer solids(shape, TopAbs_SOLID); solids.More(); solids.Next()) {
            classifiers.push_back(std::make_unique<BRepClass3d_SolidClassifier>(solids.Current()));
            Bnd_Box bounds;
            BRepBndLib::Add(solids.Current(), bounds);
            solidBounds.push_back(bounds);
        }
        convexPlanar = convexPlanar && classifiers.size() == 1 && !planes.empty();
        GProp_GProps properties;
        BRepGProp::SurfaceProperties(boundary, properties);
        surfaceArea = properties.Mass();
    }

    Witness witness(const Vec& position, bool interiorOnly = false) const
    {
        Witness result;
        if (convexPlanar) {
            double clearance = std::numeric_limits<double>::infinity();
            for (const auto& plane : planes) {
                const double d = -(position - plane.point).Dot(plane.normal);
                if (d < clearance) {
                    clearance = d;
                    result.outward = plane.normal;
                }
            }
            if (clearance > tolerance) {
                result.inside = true;
                result.distance = clearance;
                result.point = position + result.outward * clearance;
                return result;
            }
            if (interiorOnly) return result;
        }
        for (size_t i = 0; i < classifiers.size(); ++i) {
            if (solidBounds[i].IsOut(point(position))) continue;
            classifiers[i]->Perform(point(position), tolerance);
            if (classifiers[i]->State() == TopAbs_IN) {
                result.inside = true;
                break;
            }
        }
        if (interiorOnly && !result.inside) return result;
        if (result.inside && allPlanar) {
            // For an all-planar solid, the nearest supporting plane gives a
            // lower bound on boundary distance. If its projection belongs to
            // the trimmed face, that bound is attained—even for a concave part.
            // Otherwise retain the exact edge/vertex-aware distance fallback.
            const Plane* nearest = nullptr;
            double gap = std::numeric_limits<double>::infinity();
            for (const auto& plane : planes) {
                const double d = std::abs((position - plane.point).Dot(plane.normal));
                if (d < gap) { gap = d; nearest = &plane; }
            }
            if (nearest) {
                const double signedGap = -(position - nearest->point).Dot(nearest->normal);
                const Vec projection = position + nearest->normal * signedGap;
                BRepClass_FaceClassifier classifier(nearest->face, point(projection), tolerance);
                if (signedGap > tolerance
                    && (classifier.State() == TopAbs_IN || classifier.State() == TopAbs_ON)) {
                    result.point = projection;
                    result.distance = signedGap;
                    result.outward = nearest->normal;
                    return result;
                }
            }
        }
        // Distance to a solid is zero for an interior point. Query its boundary
        // instead, so the distance is the actual depth to an escape surface.
        BRepExtrema_DistShapeShape distance(BRepBuilderAPI_MakeVertex(point(position)), boundary);
        if (!distance.IsDone() || distance.NbSolution() == 0)
            throw std::runtime_error("Cannot determine a contact surface witness");
        result.point = vector(distance.PointOnShape2(1));
        result.distance = distance.Value();
        if (result.distance > tolerance) {
            result.outward = (result.inside ? result.point - position : position - result.point)
                / result.distance;
        }
        else if (distance.SupportTypeShape2(1) == BRepExtrema_IsInFace) {
            double u, v;
            distance.ParOnFaceS2(1, u, v);
            const auto face = TopoDS::Face(distance.SupportOnShape2(1));
            BRepAdaptor_Surface surface(face);
            gp_Pnt p;
            gp_Vec du, dv;
            surface.D1(u, v, p, du, dv);
            gp_Vec normal = du.Crossed(dv);
            if (normal.Magnitude() > tolerance) {
                normal.Normalize();
                if (face.Orientation() == TopAbs_REVERSED) normal.Reverse();
                result.outward = Vec(normal.X(), normal.Y(), normal.Z());
            }
        }
        return result;
    }
};

ContactGeometry::ContactGeometry(const TopoDS_Shape& a, const TopoDS_Shape& b, bool prepareManifold)
    : first(std::make_shared<Shape>(a, prepareManifold)),
      second(std::make_shared<Shape>(b, prepareManifold))
{}

double ContactGeometry::travel(const Shape& shape, const Base::Placement& start,
                              const Base::Placement& end) const
{
    const auto rotation = end.getRotation() * start.getRotation().inverse();
    const double angle = 2 * std::acos(std::clamp(std::abs(rotation.getValue()[3]), 0.0, 1.0));
    return (end.getPosition() - start.getPosition()).Length() + shape.radius * angle;
}

double ContactGeometry::sweep(const Base::Placement& a0, const Base::Placement& a1,
                             const Base::Placement& b0, const Base::Placement& b1,
                             bool allowSeparatingTouch) const
{
    const double distanceBound = travel(*first, a0, a1) + travel(*second, b0, b1);
    if (distanceBound <= tolerance) return 1;
    const auto sameRotation = [](const Base::Placement& a, const Base::Placement& b) {
        const auto* q = a.getRotation().getValue();
        return std::equal(q, q + 4, b.getRotation().getValue());
    };
    if (allowSeparatingTouch && sameRotation(a0, a1) && sameRotation(b0, b1)) {
        // With translation only, an axis separating both endpoint boxes
        // separates the entire sweep. Include OCCT's bounding-box padding so
        // tangential sliding from exact touch does not stick to the surface.
        const auto limits = [](const Bnd_Box& box) {
            std::array<double, 6> values{};
            box.Get(values[0], values[1], values[2], values[3], values[4], values[5]);
            return values;
        };
        const auto ai = limits(first->bounds.Transformed(Part::TopoShape::convert(a0.toMatrix())));
        const auto af = limits(first->bounds.Transformed(Part::TopoShape::convert(a1.toMatrix())));
        const auto bi = limits(second->bounds.Transformed(Part::TopoShape::convert(b0.toMatrix())));
        const auto bf = limits(second->bounds.Transformed(Part::TopoShape::convert(b1.toMatrix())));
        for (size_t axis = 0; axis < 3; ++axis) {
            if ((ai[axis + 3] <= bi[axis] + 4*tolerance && af[axis + 3] <= bf[axis] + 4*tolerance)
                || (bi[axis + 3] <= ai[axis] + 4*tolerance && bf[axis + 3] <= af[axis] + 4*tolerance))
                return 1;
        }
    }
    // Enlarging the initial bounds by the maximum surface travel also encloses
    // every intermediate rotated pose, unlike the union of endpoint boxes.
    auto swept = first->bounds.Transformed(Part::TopoShape::convert(a0.toMatrix()));
    swept.Enlarge(distanceBound + tolerance);
    if (swept.IsOut(second->bounds.Transformed(Part::TopoShape::convert(b0.toMatrix()))))
        return 1;
    double fraction = 0;
    for (int iteration = 0; iteration < 64; ++iteration) {
        const auto a = Base::Placement::slerp(a0, a1, fraction);
        const auto b = Base::Placement::slerp(b0, b1, fraction);
        BRepExtrema_DistShapeShape distance(moved(first->solid, a), moved(second->solid, b));
        if (!distance.IsDone()) throw std::runtime_error("Contact sweep distance failed");
        const double gap = distance.Value();
        if (gap <= tolerance) {
            if (fraction == 0 && allowSeparatingTouch) {
                // Dragging may start exactly on a surface. Probe only a tiny
                // geometric tolerance interval, never a percentage of a large
                // mouse step, so an outward move can leave that surface.
                const double probe = std::min(1.0, 16 * tolerance / distanceBound);
                BRepExtrema_DistShapeShape separation(
                    moved(first->solid, Base::Placement::slerp(a0, a1, probe)),
                    moved(second->solid, Base::Placement::slerp(b0, b1, probe)));
                if (separation.IsDone() && separation.Value() > tolerance) {
                    fraction = probe;
                    if (fraction == 1) return 1;
                    continue;
                }
            }
            return fraction;
        }
        const double advance = 0.9 * (gap - tolerance) / distanceBound;
        if (fraction + advance >= 1) return 1;
        if (advance < 1e-12) return fraction;
        fraction += advance;
    }
    // An unresolved grazing sweep is not silently declared collision-free.
    return fraction;
}

bool ContactGeometry::acceptStep(const Base::Placement& a0, const Base::Placement& a1,
                                 const Base::Placement& b0, const Base::Placement& b1) const
{
    const double movement = travel(*first, a0, a1) + travel(*second, b0, b1);
    if (movement <= std::min(first->resolution, second->resolution)) return true;
    return sweep(a0, a1, b0, b1) == 1;
}

std::vector<ContactPoint> ContactGeometry::points(
    const Base::Placement& firstDelta, const Base::Placement& secondDelta
) const
{
    if (hasCachedPoints && identicalPose(firstDelta, cachedFirstDelta)
        && identicalPose(secondDelta, cachedSecondDelta))
        return cachedPoints;
    auto result = computePoints(firstDelta, secondDelta);
    cachedPoints = result;
    cachedFirstDelta = firstDelta;
    cachedSecondDelta = secondDelta;
    hasCachedPoints = true;
    return result;
}

std::vector<ContactPoint> ContactGeometry::computePoints(
    const Base::Placement& firstDelta, const Base::Placement& secondDelta
) const
{
    // Transform conservative reference bounds without walking the BRep on every
    // solver residual. Rotated boxes may be looser, but cannot reject a contact.
    const auto boxI = first->bounds.Transformed(Part::TopoShape::convert(firstDelta.toMatrix()));
    const auto boxJ = second->bounds.Transformed(Part::TopoShape::convert(secondDelta.toMatrix()));
    if (boxI.IsOut(boxJ)) return {};

    if (first->sphereRadius > 0 && second->sphereRadius > 0) {
        const Vec centreI = transformed(firstDelta, first->sphereCentre);
        const Vec centreJ = transformed(secondDelta, second->sphereCentre);
        const Vec separation = centreI - centreJ;
        const double distance = separation.Length();
        const double depth = first->sphereRadius + second->sphereRadius - distance;
        if (!(depth > 0)) return {};
        // Coincident centres have no unique contact normal. Choose a fixed
        // escape direction rather than querying an undefined surface witness.
        const Vec normal = distance > tolerance ? separation / distance : Vec(1, 0, 0);
        return {{centreI - normal * (first->sphereRadius - 0.5 * depth), normal, depth}};
    }

    if (first->sphereRadius > 0 || second->sphereRadius > 0) {
        const bool sphereI = first->sphereRadius > 0;
        const auto& sphere = sphereI ? first : second;
        const auto& target = sphereI ? second : first;
        const auto& sphereDelta = sphereI ? firstDelta : secondDelta;
        const auto& targetDelta = sphereI ? secondDelta : firstDelta;
        const Vec centre = transformed(sphereDelta, sphere->sphereCentre);
        const Witness witness = target->witness(transformed(targetDelta.inverse(), centre));
        const double depth = sphere->sphereRadius
            + (witness.inside ? witness.distance : -witness.distance);
        if (!(depth > 0) || witness.outward.Length() < tolerance) return {};
        const Vec normal = targetDelta.getRotation().multVec(witness.outward);
        const Vec contactPoint = centre - normal * (sphere->sphereRadius - 0.5 * depth);
        return {{contactPoint, sphereI ? normal : -normal, depth}};
    }

    std::vector<ContactPoint> candidates;
    const auto append = [&](const Vec& worldPoint, bool onFirst, const Vec& sourceNormal = Vec(),
                            double weight = 0) {
        const auto& target = onFirst ? second : first;
        const auto& delta = onFirst ? secondDelta : firstDelta;
        const Witness witness = target->witness(transformed(delta.inverse(), worldPoint), true);
        if (!witness.inside || witness.distance <= tolerance) return;
        const Vec normal = delta.getRotation().multVec(witness.outward);
        // A face penetrating a broad support must not acquire a sideways force
        // from the other body's nearest side wall. Only opposing faces support
        // each other; vertices retain their unconstrained witness direction.
        if (sourceNormal.Sqr() > 0.5 && sourceNormal.Dot(normal) > -0.5) return;
        const Vec p = (worldPoint + transformed(delta, witness.point)) * 0.5;
        if (std::none_of(candidates.begin(), candidates.end(), [&](const auto& existing) {
                return (existing.point - p).Length() < tolerance;
            }))
            candidates.push_back({p, onFirst ? normal : -normal, witness.distance, weight});
    };
    // Use one quadrature surface per pair. Mixing both discretizations counts
    // the same patch twice and lets a broad support's sparse samples introduce
    // lateral forces. Prefer the smaller surface, independent of pair order.
    const bool sampleFirst = first->surfaceArea <= second->surfaceArea;
    const auto sampleSurface = [&](bool onFirst) {
        const auto& source = onFirst ? first : second;
        const auto& delta = onFirst ? firstDelta : secondDelta;
        for (const auto& sample : source->samples)
            append(transformed(delta, sample.point), onFirst,
                delta.getRotation().multVec(sample.normal), sample.weight);
    };
    sampleSurface(sampleFirst);
    if (candidates.empty()) sampleSurface(!sampleFirst);

    if (candidates.empty()) {
        // Thin crossing solids may intersect between all quadrature points.
        // Obtain samples from their actual clipped face patches in that case.
        BRepAlgoAPI_Common common(moved(first->solid, firstDelta), moved(second->solid, secondDelta));
        common.SetNonDestructive(true);
        common.Build();
        if (!common.IsDone()) throw std::runtime_error("Contact intersection failed");
        for (TopExp_Explorer faces(common.Shape(), TopAbs_FACE); faces.More(); faces.Next()) {
            GProp_GProps properties;
            BRepGProp::SurfaceProperties(faces.Current(), properties);
            const Vec centre = vector(properties.CentreOfMass());
            for (bool onFirst : {true, false}) {
                const auto& source = onFirst ? first : second;
                const auto& delta = onFirst ? firstDelta : secondDelta;
                const auto witness = source->witness(transformed(delta.inverse(), centre));
                append(transformed(delta, witness.point), onFirst);
            }
        }
    }
    if (candidates.empty()) return {};
    const bool hasSurfaceWeights = std::any_of(candidates.begin(), candidates.end(),
        [](const auto& candidate) { return candidate.weight > 0; });
    if (!hasSurfaceWeights)
        for (auto& candidate : candidates) candidate.weight = 1;

    // Keep the symmetric surface quadrature: selecting only a few deepest
    // witnesses can switch discontinuously and introduce an artificial moment.
    return candidates;
}
}
