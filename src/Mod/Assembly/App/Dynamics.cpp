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
#include "AssemblyObject.h"
#include "AssemblyUtils.h"
#include "Dynamics.h"
#include "ContactGeometry.h"
#include "Groups.h"
#include "ContactGroups.h"
#include "EventRuntime.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <BRepCheck_Analyzer.hxx>
#include <BRepAdaptor_Surface.hxx>
#include <BRepAlgoAPI_Common.hxx>
#include <BRepClass3d_SolidClassifier.hxx>
#include <BRepExtrema_ShapeProximity.hxx>
#include <BRepBuilderAPI_Transform.hxx>
#include <BRepBuilderAPI_GTransform.hxx>
#include <BRepBndLib.hxx>
#include <BRepGProp.hxx>
#include <BRepMesh_IncrementalMesh.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <Standard_Failure.hxx>
#include <GProp_GProps.hxx>
#include <GProp_PrincipalProps.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <Base/Quantity.h>
#include <App/PropertyUnits.h>
#include <App/PropertyStandard.h>
#include <App/GeoFeature.h>
#include <App/Part.h>
#include <App/DocumentObjectGroup.h>
#include <Mod/Material/App/PropertyMaterial.h>
#include <Mod/Part/App/PartFeature.h>
#include <OndselSolver/ASMTAssembly.h>
#include <OndselSolver/ASMTPart.h>
#include <OndselSolver/ASMTMarker.h>
#include <OndselSolver/ASMTJoint.h>
#include <OndselSolver/ASMTMotion.h>
#include <OndselSolver/ASMTForceTorque.h>
#include <OndselSolver/ASMTDistanceLimit.h>
#include <OndselSolver/FullColumn.h>
#include <OndselSolver/DynamicEvents.h>

namespace Assembly
{
namespace
{
using Object = App::DocumentObject;
using Vec = Base::Vector3d;
using ContactClock = std::chrono::steady_clock;

struct ContactTiming
{
    double extractionMs = 0;
    double transformMs = 0;
    double broadPhaseMs = 0;
    double proximityMs = 0;
    double meshingMs = 0;
    double containmentMs = 0;
    double booleanMs = 0;
    size_t pairs = 0;
    size_t overlapTests = 0;
    size_t booleanTests = 0;
    size_t proximityTests = 0;
    size_t containmentTests = 0;
    size_t meshRetries = 0;
    size_t booleanFallbacks = 0;
    size_t broadPhaseRejects = 0;
};

double elapsedMilliseconds(ContactClock::time_point start)
{
    return std::chrono::duration<double, std::milli>(ContactClock::now() - start).count();
}

[[noreturn]] void invalid(Object* object, const std::string& reason)
{
    throw std::invalid_argument(
        std::string(object ? object->getFullName() : "Dynamics") + ": " + reason
    );
}

template<class T>
T& property(Object* object, const char* name)
{
    auto* p = object ? dynamic_cast<T*>(object->getPropertyByName(name)) : nullptr;
    if (!p) {
        invalid(object, std::string("Missing or invalid property ") + name);
    }
    return *p;
}

std::vector<Object*> simulationInputs(AssemblyObject* assembly, Object* simulation)
{
    std::vector<Object*> result;
    if (!assembly || !simulation) {
        return result;
    }
    for (auto* child : assembly->Group.getValues()) {
        if (!child || !child->isDerivedFrom<SimulationGroup>()) {
            continue;
        }
        for (auto* input : property<App::PropertyLinkList>(child, "Group").getValues()) {
            // Studies are containers. Other direct children are global inputs.
            if (input && !input->getPropertyByName("Assembly")) {
                result.push_back(input);
            }
        }
        break;
    }
    const auto local = property<App::PropertyLinkList>(simulation, "Group").getValues();
    result.insert(result.end(), local.begin(), local.end());
    return result;
}

double number(Object* object, const char* name)
{
    double value = property<App::PropertyFloat>(object, name).getValue();
    if (!std::isfinite(value)) {
        invalid(object, std::string(name) + " must be finite");
    }
    return value;
}

double quantityAs(Object* object, const char* name, const char* unit)
{
    auto& p = property<App::PropertyQuantity>(object, name);
    const double value = p.getQuantityValue().getValueAs(Base::Quantity(1, unit));
    if (!std::isfinite(value)) {
        invalid(object, std::string(name) + " must be finite");
    }
    return value;
}

Vec direction(Object* object, const char* name)
{
    Vec value = property<App::PropertyVector>(object, name).getValue();
    if (!std::isfinite(value.x) || !std::isfinite(value.y) || !std::isfinite(value.z)
        || value.Length() < 1e-12) {
        invalid(object, std::string(name) + " must be a finite nonzero direction");
    }
    value.Normalize();
    return value;
}

struct Mass
{
    GProp_GProps properties;
    double volume = 0;
    double density = 0;
    bool aggregate = false;
    std::string material;
    std::string materialUUID;
};

struct ContactSphere
{
    Vec centre;
    double radius = 0;
};

TopoDS_Shape contactShapeOf(Object* component)
{
    auto shape = Part::Feature::getShape(
        component,
        Part::ShapeOption::ResolveLink | Part::ShapeOption::Transform
    );
    if (shape.IsNull() || !TopExp_Explorer(shape, TopAbs_SOLID).More()) {
        invalid(component, "Contact requires a component containing at least one solid");
    }
    return shape;
}

bool boxContains(const Bnd_Box& container, const Bnd_Box& candidate)
{
    if (container.IsVoid() || candidate.IsVoid()) {
        return false;
    }
    double cXMin, cYMin, cZMin, cXMax, cYMax, cZMax;
    double xMin, yMin, zMin, xMax, yMax, zMax;
    container.Get(cXMin, cYMin, cZMin, cXMax, cYMax, cZMax);
    candidate.Get(xMin, yMin, zMin, xMax, yMax, zMax);
    const double tolerance = Precision::Confusion();
    return xMin >= cXMin - tolerance && yMin >= cYMin - tolerance
        && zMin >= cZMin - tolerance && xMax <= cXMax + tolerance
        && yMax <= cYMax + tolerance && zMax <= cZMax + tolerance;
}

bool representativePointInside(
    const TopoDS_Shape& candidate,
    const TopoDS_Shape& container
)
{
    // With no boundary intersection, overlap can only be containment. One
    // vertex per candidate solid is sufficient to distinguish that case and
    // avoids the former O(vertices * solids) classifier loop.
    for (TopExp_Explorer candidateSolid(candidate, TopAbs_SOLID);
         candidateSolid.More();
         candidateSolid.Next()) {
        TopExp_Explorer vertex(candidateSolid.Current(), TopAbs_VERTEX);
        if (!vertex.More()) {
            continue;
        }
        const gp_Pnt point = BRep_Tool::Pnt(TopoDS::Vertex(vertex.Current()));
        for (TopExp_Explorer solid(container, TopAbs_SOLID); solid.More(); solid.Next()) {
            BRepClass3d_SolidClassifier classifier(
                TopoDS::Solid(solid.Current()),
                point,
                Precision::Confusion()
            );
            if (classifier.State() == TopAbs_IN) {
                return true;
            }
        }
    }
    return false;
}

void ensureContactTriangulation(const TopoDS_Shape& shape, ContactTiming& timing)
{
    auto phaseStart = ContactClock::now();
    Bnd_Box bounds;
    BRepBndLib::Add(shape, bounds);
    double xMin, yMin, zMin, xMax, yMax, zMax;
    bounds.Get(xMin, yMin, zMin, xMax, yMax, zMax);
    const double diagonal = Vec(xMax - xMin, yMax - yMin, zMax - zMin).Length();
    const double deflection = std::clamp(diagonal * 1e-3, 0.01, 0.5);
    BRepMesh_IncrementalMesh mesh(shape, deflection, false, 0.5, true);
    timing.meshingMs += elapsedMilliseconds(phaseStart);
}

bool shapesOverlap(
    const TopoDS_Shape& firstShape,
    const TopoDS_Shape& secondShape,
    ContactTiming& timing
)
{
    ++timing.overlapTests;
    auto phaseStart = ContactClock::now();
    Bnd_Box firstBox;
    Bnd_Box secondBox;
    BRepBndLib::Add(firstShape, firstBox);
    BRepBndLib::Add(secondShape, secondBox);
    timing.broadPhaseMs += elapsedMilliseconds(phaseStart);
    if (firstBox.IsOut(secondBox)) {
        ++timing.broadPhaseRejects;
        return false;
    }

    const auto proximityOverlap = [&](bool& done) {
        ++timing.proximityTests;
        auto proximityStart = ContactClock::now();
        BRepExtrema_ShapeProximity proximity(
            firstShape,
            secondShape,
            Precision::Confusion()
        );
        proximity.Perform();
        done = proximity.IsDone();
        const bool overlap = done
            && (!proximity.OverlapSubShapes1().IsEmpty()
                || !proximity.OverlapSubShapes2().IsEmpty());
        timing.proximityMs += elapsedMilliseconds(proximityStart);
        return overlap;
    };

    bool proximityDone = false;
    bool surfaceIntersection = proximityOverlap(proximityDone);
    if (!proximityDone) {
        ++timing.meshRetries;
        ensureContactTriangulation(firstShape, timing);
        ensureContactTriangulation(secondShape, timing);
        surfaceIntersection = proximityOverlap(proximityDone);
    }
    if (proximityDone) {
        if (surfaceIntersection) {
            return true;
        }

        bool containment = false;
        phaseStart = ContactClock::now();
        if (boxContains(secondBox, firstBox)) {
            ++timing.containmentTests;
            containment = representativePointInside(firstShape, secondShape);
        }
        if (!containment && boxContains(firstBox, secondBox)) {
            ++timing.containmentTests;
            containment = representativePointInside(secondShape, firstShape);
        }
        timing.containmentMs += elapsedMilliseconds(phaseStart);
        return surfaceIntersection || containment;
    }

    // ShapeProximity needs face triangulation. This exact fallback keeps
    // contact functional for unusual non-tessellated shapes, but the timing
    // log makes an unexpectedly frequent fallback immediately visible.
    ++timing.booleanTests;
    ++timing.booleanFallbacks;
    phaseStart = ContactClock::now();
    BRepAlgoAPI_Common common(firstShape, secondShape);
    common.SetNonDestructive(true);
    common.SetRunParallel(false);
    common.Build();
    if (!common.IsDone() || common.Shape().IsNull()) {
        timing.booleanMs += elapsedMilliseconds(phaseStart);
        return false;
    }
    GProp_GProps overlap;
    BRepGProp::VolumeProperties(common.Shape(), overlap);
    timing.booleanMs += elapsedMilliseconds(phaseStart);
    return overlap.Mass() > 1e-9;
}

TopoDS_Shape movedShape(
    const TopoDS_Shape& targetShape,
    const Base::Placement& fromTarget,
    const Base::Placement& assemblyGlobal,
    ContactTiming& timing
)
{
    auto phaseStart = ContactClock::now();
    const Base::Placement worldDelta = assemblyGlobal * fromTarget * assemblyGlobal.inverse();
    BRepBuilderAPI_Transform transform(
        targetShape,
        Part::TopoShape::convert(worldDelta.toMatrix()),
        false
    );
    const TopoDS_Shape result = transform.Shape();
    timing.transformMs += elapsedMilliseconds(phaseStart);
    return result;
}

Base::Placement contactFramePlacement(const MbD::AppliedForceTorque::FrameState& state)
{
    const auto& r = state.rotation;
    Base::Matrix4D matrix(
        r[0], r[1], r[2], state.position[0],
        r[3], r[4], r[5], state.position[1],
        r[6], r[7], r[8], state.position[2],
        0.0, 0.0, 0.0, 1.0
    );
    return Base::Placement(matrix);
}

struct ContactBoxResponse
{
    Vec normal;
    Vec point;
    double penetration = 0;
};

ContactBoxResponse contactBoxResponse(const TopoDS_Shape& first, const TopoDS_Shape& second)
{
    Bnd_Box firstBox;
    Bnd_Box secondBox;
    BRepBndLib::Add(first, firstBox);
    BRepBndLib::Add(second, secondBox);
    double firstMin[3], firstMax[3], secondMin[3], secondMax[3];
    firstBox.Get(
        firstMin[0], firstMin[1], firstMin[2], firstMax[0], firstMax[1], firstMax[2]
    );
    secondBox.Get(
        secondMin[0], secondMin[1], secondMin[2], secondMax[0], secondMax[1], secondMax[2]
    );

    ContactBoxResponse result;
    result.penetration = std::numeric_limits<double>::infinity();
    for (size_t axis = 0; axis < 3; ++axis) {
        // Test both translations that separate the first box from the second.
        // This also gives the correct escape direction when one box contains another.
        const double negative = firstMax[axis] - secondMin[axis];
        const double positive = secondMax[axis] - firstMin[axis];
        if (negative < result.penetration) {
            result.penetration = negative;
            result.normal = Vec();
            result.normal[axis] = -1;
        }
        if (positive < result.penetration) {
            result.penetration = positive;
            result.normal = Vec();
            result.normal[axis] = 1;
        }
        result.point[axis] = 0.5
            * (std::max(firstMin[axis], secondMin[axis])
               + std::min(firstMax[axis], secondMax[axis]));
    }

    // Keep the minimum-translation axis as the response normal. A direction
    // between bounding-box centres changes under small rotations and can inject
    // lateral force into an otherwise horizontal face contact.
    return result;
}

Vec regularizedFriction(
    const Vec& normal,
    const Vec& relativeVelocity,
    double normalForce,
    double staticCoefficient,
    double dynamicCoefficient,
    double transitionVelocity
)
{
    const Vec tangentVelocity = relativeVelocity
        - normal * relativeVelocity.Dot(normal);
    const double speed = tangentVelocity.Length();
    if (!(normalForce > 0) || !(speed > 1e-12)
        || !(staticCoefficient > 0) || !(transitionVelocity > 0)) {
        return Vec();
    }
    const double ratio = speed / transitionVelocity;
    const double coefficient = dynamicCoefficient
        + (staticCoefficient - dynamicCoefficient) * std::exp(-(ratio * ratio));
    const double magnitude = coefficient * normalForce * std::tanh(ratio);
    return tangentVelocity * (-magnitude / speed);
}

MbD::AppliedForceTorque::ContactEvaluator shapeContactEvaluator(
    std::shared_ptr<ContactGeometry> geometry,
    double stiffness,
    double damping,
    double staticFriction,
    double dynamicFriction,
    double transitionVelocity
)
{
    return [geometry,
            stiffness,
            damping,
            staticFriction,
            dynamicFriction,
            transitionVelocity](const MbD::AppliedForceTorque::FrameState& first,
                     const MbD::AppliedForceTorque::FrameState& second) {
        using Wrench = MbD::AppliedForceTorque::ContactWrench;
        const Base::Placement firstFrame = contactFramePlacement(first);
        const Base::Placement secondFrame = contactFramePlacement(second);
        const auto contacts = geometry->points(firstFrame, secondFrame);
        if (contacts.empty()) {
            return Wrench {};
        }

        const auto vector = [](const std::array<double, 3>& value) {
            return Vec(value[0], value[1], value[2]);
        };
        const Vec firstVelocity = vector(first.velocity);
        const Vec secondVelocity = vector(second.velocity);
        const Vec firstOmega = vector(first.omega);
        const Vec secondOmega = vector(second.omega);
        Vec force;
        Vec torque;
        double storedEnergy = 0;
        double dissipatedPower = 0;
        double totalWeight = 0;
        for (const auto& contact : contacts) totalWeight += contact.weight;
        for (const auto& contact : contacts) {
            if (!(contact.weight > 0)) continue;
            const double pointScale = contact.weight / totalWeight;
            const Vec& point = contact.point;
            const Vec firstLever = point - firstFrame.getPosition();
            const Vec secondLever = point - secondFrame.getPosition();
            const Vec relativeVelocity = firstVelocity + firstOmega.Cross(firstLever)
                - secondVelocity - secondOmega.Cross(secondLever);
            const double normalVelocity = relativeVelocity.Dot(contact.normal);
            const double magnitude = std::max(
                0.0,
                pointScale
                    * (stiffness * contact.penetration - damping * normalVelocity)
            );
            const Vec pointForce = contact.normal * magnitude
                + regularizedFriction(
                    contact.normal,
                    relativeVelocity,
                    magnitude,
                    staticFriction,
                    dynamicFriction,
                    transitionVelocity
                );
            const Vec tangentVelocity = relativeVelocity
                - contact.normal * normalVelocity;
            const Vec tangentForce = pointForce - contact.normal * magnitude;
            force += pointForce;
            torque += firstLever.Cross(pointForce);
            storedEnergy += 0.5 * pointScale * stiffness
                * contact.penetration * contact.penetration;
            // Clipping a tensile penalty force still releases elastic energy.
            dissipatedPower += (pointScale * stiffness * contact.penetration - magnitude)
                    * normalVelocity
                - tangentForce.Dot(tangentVelocity);
        }
        return Wrench {
            {force.x, force.y, force.z},
            {torque.x, torque.y, torque.z},
            storedEnergy,
            dissipatedPower
        };
    };
}

std::vector<Object*> massChildren(Object* container)
{
    // A GeoFeatureGroup also lists descendants of plain organizational folders
    // as direct members. Flatten those folders and count each object once, not
    // each group membership. Distinct links to one source remain distinct bodies.
    std::vector<Object*> result;
    std::set<Object*> visited;
    const auto collect = [&](const auto& self, Object* object) -> void {
        if (!object || !visited.insert(object).second) {
            return;
        }
        if (auto* folder = dynamic_cast<App::DocumentObjectGroup*>(object)) {
            for (auto* child : folder->Group.getValues()) {
                self(self, child);
            }
        }
        else {
            result.push_back(object);
        }
    };
    for (auto* child : property<App::PropertyLinkList>(container, "Group").getValues()) {
        collect(collect, child);
    }

    // A Part container may retain the complete modeling history. Only terminal
    // features represent physical solids: operands consumed by another child
    // (for example Box and Cylinder under a Cut) must not be counted again.
    std::set<Object*> consumed;
    for (auto* child : result) {
        // Expression references do not make one solid a modeling operand of
        // another and must not remove otherwise independent components.
        for (auto* dependency : child->getOutList(Object::OutListNoExpression)) {
            consumed.insert(dependency);
        }
    }
    result.erase(
        std::remove_if(
            result.begin(),
            result.end(),
            [&](Object* child) { return consumed.contains(child); }
        ),
        result.end()
    );
    return result;
}

ContactSphere transformSphere(const ContactSphere& sphere, const Base::Matrix4D& transform)
{
    Vec centre;
    Vec origin;
    Vec xAxis;
    Vec yAxis;
    Vec zAxis;
    transform.multVec(sphere.centre, centre);
    transform.multVec(Vec(), origin);
    transform.multVec(Vec(1, 0, 0), xAxis);
    transform.multVec(Vec(0, 1, 0), yAxis);
    transform.multVec(Vec(0, 0, 1), zAxis);
    const double sx = (xAxis - origin).Length();
    const double sy = (yAxis - origin).Length();
    const double sz = (zAxis - origin).Length();
    const double scale = (sx + sy + sz) / 3;
    if (!(scale > 0) || std::abs(sx - scale) > scale * 1e-9
        || std::abs(sy - scale) > scale * 1e-9 || std::abs(sz - scale) > scale * 1e-9) {
        throw std::invalid_argument("Contact spheres require a rigid or uniform-scale transform");
    }
    return {centre, sphere.radius * scale};
}

ContactSphere contactSphereOfTree(
    Object* object,
    const Base::Matrix4D& offset,
    std::set<Object*> ancestors
)
{
    if (!object) {
        invalid(object, "Missing contact component");
    }
    Base::Matrix4D linkTransform;
    auto* source = object->getLinkedObject(true, &linkTransform, false);
    if (!source || !ancestors.insert(source).second) {
        invalid(object, "Missing or cyclic contact component source");
    }
    if (!source->isDerivedFrom<Part::Feature>()) {
        auto* group = dynamic_cast<App::PropertyLinkList*>(source->getPropertyByName("Group"));
        if (!group || !source->isDerivedFrom<App::Part>()) {
            invalid(object, "Contact requires a solid component, App::Part, or link");
        }
        std::vector<ContactSphere> spheres;
        for (auto* child : massChildren(source)) {
            auto* childSource = child->getLinkedObject(true);
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                child->getPropertyByName("Suppressed")
            );
            if (!childSource || (suppressed && suppressed->getValue())) {
                continue;
            }
            if (childSource->isDerivedFrom<Part::Feature>()) {
                auto shape = Part::Feature::getShape(child, Part::ShapeOption::ResolveLink);
                if (shape.IsNull() || !TopExp_Explorer(shape, TopAbs_SOLID).More()) {
                    continue;
                }
            }
            else if (!childSource->isDerivedFrom<App::Part>()) {
                continue;
            }
            auto transform = offset * linkTransform;
            if (auto* placement
                = dynamic_cast<App::PropertyPlacement*>(child->getPropertyByName("Placement"))) {
                transform *= placement->getValue().toMatrix();
            }
            spheres.push_back(contactSphereOfTree(child, transform, ancestors));
        }
        if (spheres.size() != 1) {
            invalid(object, "The first contact implementation requires one spherical solid per component");
        }
        return spheres.front();
    }

    const auto shape = Part::Feature::getShape(object, Part::ShapeOption::ResolveLink);
    int solids = 0;
    for (TopExp_Explorer explorer(shape, TopAbs_SOLID); explorer.More(); explorer.Next()) {
        ++solids;
    }
    TopExp_Explorer faces(shape, TopAbs_FACE);
    if (shape.IsNull() || solids != 1 || !faces.More()) {
        invalid(object, "The first contact implementation requires one spherical solid per component");
    }
    BRepAdaptor_Surface surface(TopoDS::Face(faces.Current()), true);
    if (surface.GetType() != GeomAbs_Sphere) {
        invalid(object, "The first contact implementation currently supports spherical solids");
    }
    const gp_Sphere geometricSphere = surface.Sphere();
    faces.Next();
    if (faces.More()) {
        invalid(object, "The first contact implementation currently supports spherical solids");
    }
    const auto location = geometricSphere.Location();
    return transformSphere({Vec(location.X(), location.Y(), location.Z()), geometricSphere.Radius()}, offset);
}

ContactSphere contactSphereOf(Object* object)
{
    return contactSphereOfTree(object, Base::Matrix4D(), {});
}

Mass massOfTree(Object* object, const Base::Matrix4D& offset, std::set<Object*> ancestors)
{
    if (!object) {
        invalid(object, "Missing body");
    }
    Base::Matrix4D linkTransform;
    auto* source = object->getLinkedObject(true, &linkTransform, false);
    if (!source || !ancestors.insert(source).second) {
        invalid(object, "Missing or cyclic component source");
    }
    // PartDesign bodies expose the tip shape/material without counting their
    // feature history. Containers need per-child materials, not a guessed density.
    if (!source->isDerivedFrom<Part::Feature>()) {
        auto* group = dynamic_cast<App::PropertyLinkList*>(source->getPropertyByName("Group"));
        if (!group
            || (!source->isDerivedFrom<App::Part>()
                && !source->isDerivedFrom<App::DocumentObjectGroup>())) {
            invalid(object, "A solid Part feature/Body or an App::Part is required");
        }
        Mass result;
        result.aggregate = true;
        for (auto* child : massChildren(source)) {
            auto* childSource = child->getLinkedObject(true);
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                child->getPropertyByName("Suppressed")
            );
            if (!childSource || (suppressed && suppressed->getValue())) {
                continue;
            }
            if (childSource->isDerivedFrom<Part::Feature>()) {
                // Construction geometry has no mass. A Body's tip is visited once,
                // never its feature history, irrespective of visibility.
                auto shape = Part::Feature::getShape(child, Part::ShapeOption::ResolveLink);
                if (shape.IsNull() || !TopExp_Explorer(shape, TopAbs_SOLID).More()) {
                    continue;
                }
            }
            else if (!childSource->isDerivedFrom<App::Part>()
                     && !childSource->isDerivedFrom<App::DocumentObjectGroup>()) {
                continue;
            }
            auto transform = offset * linkTransform;
            if (auto* placement
                = dynamic_cast<App::PropertyPlacement*>(child->getPropertyByName("Placement"))) {
                transform *= placement->getValue().toMatrix();
            }
            auto mass = massOfTree(child, transform, ancestors);
            if (mass.volume == 0) {
                continue;  // Empty organizational folders add no material.
            }
            result.properties.Add(mass.properties);
            result.volume += mass.volume;
        }
        if (result.volume <= 0) {
            if (source->isDerivedFrom<App::DocumentObjectGroup>()) {
                return result;
            }
            invalid(object, "Container has no volumetric components");
        }
        result.density = result.properties.Mass() / result.volume;
        return result;
    }
    auto* assigned = dynamic_cast<Materials::PropertyMaterial*>(
        object->getPropertyByName("ShapeMaterial")
    );
    if (!assigned) {
        assigned = dynamic_cast<Materials::PropertyMaterial*>(
            source->getPropertyByName("ShapeMaterial")
        );
    }
    if (!assigned || !assigned->getValue().hasPhysicalProperty(QStringLiteral("Density"))) {
        invalid(object, "Assign a physical material with Density using Materials");
    }
    const auto& material = assigned->getValue();
    const auto densityProperty = material.getPhysicalProperty(QStringLiteral("Density"));
    if (!densityProperty || densityProperty->isEmpty()) {
        invalid(object, "Material density is missing");
    }
    const auto quantity = material.getPhysicalQuantity(QStringLiteral("Density"));
    const double density = quantity.getValue();  // FreeCAD's base density is kg/mm^3.
    if (quantity.getUnit() != Base::Unit::Density || !std::isfinite(density) || density <= 0) {
        invalid(object, "Material density must be finite, positive and have density units");
    }

    auto shape = Part::Feature::getShape(object, Part::ShapeOption::ResolveLink);
    if (shape.IsNull() || !BRepCheck_Analyzer(shape).IsValid()
        || !TopExp_Explorer(shape, TopAbs_SOLID).More()) {
        invalid(object, "A valid volumetric solid is required for mass properties");
    }
    if (!offset.isUnity()) {
        gp_GTrsf transform;
        for (int row = 1; row <= 3; ++row) {
            for (int col = 1; col <= 4; ++col) {
                transform.SetValue(row, col, offset[row - 1][col - 1]);
            }
        }
        transform.SetForm();
        if (transform.Form() == gp_Other) {
            shape = BRepBuilderAPI_GTransform(shape, transform, true).Shape();
        }
        else {
            // Build the similarity transform from the original coefficients.
            // Do not reuse GTrsf's internal scale after classifying raw coefficients.
            gp_Trsf similarity;
            similarity.SetValues(
                offset[0][0],
                offset[0][1],
                offset[0][2],
                offset[0][3],
                offset[1][0],
                offset[1][1],
                offset[1][2],
                offset[1][3],
                offset[2][0],
                offset[2][1],
                offset[2][2],
                offset[2][3]
            );
            shape = BRepBuilderAPI_Transform(shape, similarity, true).Shape();
        }
    }
    GProp_GProps geometry;
    BRepGProp::VolumeProperties(shape, geometry, true);
    if (!std::isfinite(geometry.Mass()) || geometry.Mass() <= 0) {
        invalid(object, "Solid volume must be finite and positive");
    }
    Mass result;
    result.properties.Add(geometry, density);
    result.volume = geometry.Mass();
    result.density = density;
    result.material = material.getName().toStdString();
    result.materialUUID = material.getUUID().toStdString();
    return result;
}

Mass massOf(Object* object, const Base::Placement& offset = {})
{
    return massOfTree(object, offset.toMatrix(), {});
}

Py::Tuple xyz(double x, double y, double z)
{
    Py::Tuple tuple(3);
    tuple[0] = Py::Float(x);
    tuple[1] = Py::Float(y);
    tuple[2] = Py::Float(z);
    return tuple;
}

Py::Dict massDict(const Mass& mass)
{
    Py::Dict result;
    result["Mass"] = Py::Float(mass.properties.Mass());
    result["Volume"] = Py::Float(mass.volume);
    result["Density"] = Py::Float(mass.density);
    result["Material"] = Py::String(mass.material);
    result["MaterialUUID"] = Py::String(mass.materialUUID);
    result["IsAggregate"] = Py::Boolean(mass.aggregate);
    auto centre = mass.properties.CentreOfMass();
    result["CenterOfMass"] = xyz(centre.X(), centre.Y(), centre.Z());
    auto tensor = mass.properties.MatrixOfInertia();
    Py::List rows;
    for (int i = 1; i <= 3; ++i) {
        rows.append(xyz(tensor(i, 1), tensor(i, 2), tensor(i, 3)));
    }
    result["Inertia"] = rows;
    return result;
}

void assignMass(const GProp_GProps& mass, const std::shared_ptr<MbD::ASMTPart>& part)
{
    const auto principal = mass.PrincipalProperties();
    double x, y, z;
    principal.Moments(x, y, z);
    if (!(mass.Mass() > 0) || !(x > 0) || !(y > 0) || !(z > 0) || !std::isfinite(x + y + z)) {
        throw std::invalid_argument("Invalid aggregate principal inertia");
    }
    auto marker = MbD::ASMTPrincipalMassMarker::With();
    marker->setMass(mass.Mass());
    marker->setMomentOfInertias(x, y, z);
    auto c = mass.CentreOfMass();
    marker->setPosition3D(c.X(), c.Y(), c.Z());
    auto a = principal.FirstAxisOfInertia();
    auto b = principal.SecondAxisOfInertia();
    auto d = a.Crossed(b);  // Right-handed principal frame, including repeated eigenvalues.
    marker->setRotationMatrix(a.X(), b.X(), d.X(), a.Y(), b.Y(), d.Y(), a.Z(), b.Z(), d.Z());
    part->setPrincipalMassMarker(marker);
    part->setVelocity3D(0, 0, 0);
    part->setOmega3D(0, 0, 0);
}

template<class T>
Py::List series(const std::shared_ptr<T>& values, double scale = 1)
{
    Py::List result;
    // ASMT stores an unassembled INPUT sample before the solved initial
    // condition at the same time. Only the latter is a physical result.
    for (size_t k = 1; k < values->size(); ++k) {
        const double value = values->at(k);
        if (!std::isfinite(value)) {
            throw std::runtime_error("Solver returned a non-finite result");
        }
        result.append(Py::Float(value * scale));
    }
    return result;
}

Py::List scalarSeries(const std::vector<double>& values)
{
    Py::List result;
    for (double value : values) {
        if (!std::isfinite(value)) {
            throw std::runtime_error("Energy calculation returned a non-finite result");
        }
        result.append(Py::Float(value));
    }
    return result;
}

std::vector<double> integratedSeries(
    const std::shared_ptr<std::vector<double>>& times,
    const std::vector<double>& values
)
{
    if (!times || times->size() != values.size() + 1 || values.empty()) {
        throw std::runtime_error("Solver returned inconsistent energy histories");
    }
    std::vector<double> result(values.size(), 0);
    for (size_t sample = 1; sample < values.size(); ++sample) {
        const size_t k = sample + 1;
        const double dt = times->at(k) - times->at(k - 1);
        if (!(dt >= 0) || !std::isfinite(dt)) {
            throw std::runtime_error("Solver returned invalid result times");
        }
        result[sample] = result[sample - 1]
            + 0.5 * dt * (values[sample - 1] + values[sample]);
    }
    return result;
}

template<class T>
Py::List cumulativeIntegral(
    const std::shared_ptr<std::vector<double>>& times,
    const std::shared_ptr<T>& values,
    double scale = 1
)
{
    if (!times || !values || times->size() != values->size() || times->size() < 2) {
        throw std::runtime_error("Solver returned inconsistent result histories");
    }
    Py::List result;
    double integral = 0;
    result.append(Py::Float(0.0));
    for (size_t k = 2; k < times->size(); ++k) {
        const double dt = times->at(k) - times->at(k - 1);
        if (!(dt >= 0) || !std::isfinite(dt)) {
            throw std::runtime_error("Solver returned invalid result times");
        }
        integral += 0.5 * dt * (values->at(k - 1) + values->at(k)) * scale;
        if (!std::isfinite(integral)) {
            throw std::runtime_error("Energy integration returned a non-finite result");
        }
        result.append(Py::Float(integral));
    }
    return result;
}

Py::Dict reactions(const std::shared_ptr<MbD::ASMTItemIJ>& item)
{
    Py::Dict data;
    data["ForceX"] = series(item->fxs, 0.001);  // kg mm/s^2 -> N
    data["ForceY"] = series(item->fys, 0.001);
    data["ForceZ"] = series(item->fzs, 0.001);
    data["TorqueX"] = series(item->txs, 0.001);  // kg mm^2/s^2 -> N mm
    data["TorqueY"] = series(item->tys, 0.001);
    data["TorqueZ"] = series(item->tzs, 0.001);
    return data;
}
}  // namespace

PyObject* dynamicsMassProperties(Object* object)
{
    return Py::new_reference_to(massDict(massOf(object)));
}

std::vector<Object*> AssemblyObject::getContacts(Object* simulation)
{
    std::vector<Object*> result;
    std::set<Object*> seen;
    const auto localOwner = [](Object* contact) -> Object* {
        for (auto* owner : contact->getInList()) {
            if (!owner->getPropertyByName("Assembly")
                && !owner->isDerivedFrom<SimulationGroup>()) {
                continue;
            }
            auto* group = dynamic_cast<App::PropertyLinkList*>(
                owner->getPropertyByName("Group")
            );
            if (!group) {
                continue;
            }
            const auto children = group->getValues();
            if (std::ranges::find(children, contact) != children.end()) {
                return owner;
            }
        }
        return nullptr;
    };
    const auto appendContacts = [&](const std::vector<Object*>& children, Object* owner) {
        for (auto* child : children) {
            if (!child || !child->getPropertyByName("ContactType")
                || localOwner(child) != owner || !seen.insert(child).second) {
                continue;
            }
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                child->getPropertyByName("Suppressed")
            );
            if (!suppressed || !suppressed->getValue()) {
                result.push_back(child);
            }
        }
    };
    for (auto* child : Group.getValues()) {
        if (child && child->isDerivedFrom<SimulationGroup>()) {
            appendContacts(
                property<App::PropertyLinkList>(child, "Group").getValues(), child
            );
            break;
        }
    }
    if (simulation) {
        appendContacts(
            property<App::PropertyLinkList>(simulation, "Group").getValues(), simulation
        );
    }
    return result;
}

size_t AssemblyObject::contactParts(std::vector<Object*> contacts, bool dynamics)
{
    size_t solverContactCount = 0;
    std::set<std::pair<Object*, Object*>> processed;
    const auto components = getAssemblyComponents(this);
    const std::set<Object*> membership(components.begin(), components.end());
    for (auto* contact : contacts) {
        for (const auto& [componentI, componentJ] : contactComponentPairs(contact, components)) {
            const auto pair = std::less<Object*>{}(componentI, componentJ)
                ? std::pair{componentI, componentJ} : std::pair{componentJ, componentI};
            if (!processed.insert(pair).second) continue;
            if (!componentI || !componentJ || componentI == componentJ) {
                invalid(contact, "Contact requires two different components");
            }
            if (!membership.contains(componentI) || !membership.contains(componentJ)) {
                invalid(contact, "Contact components must belong to this assembly");
            }
            const auto dataI = getMbDData(componentI);
            const auto dataJ = getMbDData(componentJ);
            if (!dataI.part || !dataJ.part || dataI.part == dataJ.part) {
                continue;  // Fixed bundles cannot collide with themselves.
            }
            double stiffness = 0;
            double damping = 0;
            double staticFriction = 0;
            double dynamicFriction = 0;
            double transitionVelocity = 1;
            if (dynamics) {
                stiffness = number(contact, "Stiffness");
                damping = number(contact, "Damping");
                if (!(stiffness > 0) || damping < 0) {
                    invalid(contact, "Contact stiffness must be positive and damping nonnegative");
                }
                if (property<App::PropertyBool>(contact, "FrictionEnabled").getValue()) {
                    staticFriction = number(contact, "StaticFriction");
                    dynamicFriction = number(contact, "DynamicFriction");
                    transitionVelocity = quantityAs(
                        contact, "FrictionTransitionVelocity", "mm/s"
                    );
                    if (staticFriction < dynamicFriction || dynamicFriction < 0
                        || !(transitionVelocity > 0)) {
                        invalid(
                            contact,
                            "Friction coefficients must satisfy static >= dynamic >= 0, and "
                            "transition velocity must be positive"
                        );
                    }
                }
            }
            ContactSphere sphereI;
            ContactSphere sphereJ;
            if (!dynamics) {
                try {
                    sphereI = contactSphereOf(componentI);
                    sphereJ = contactSphereOf(componentJ);
                }
                catch (const std::invalid_argument&) {
                    continue;
                }
            }
            else {
                TopoDS_Shape shapeI = contactShapeOf(componentI);
                TopoDS_Shape shapeJ = contactShapeOf(componentJ);
                ContactTiming timing;
                ensureContactTriangulation(shapeI, timing);
                ensureContactTriangulation(shapeJ, timing);

                Base::Placement placementI = dataI.offsetPlc;
                Base::Placement placementJ = dataJ.offsetPlc;
                const std::string suffix = std::string("_")
                    + componentI->getNameInDocument() + "_" + componentJ->getNameInDocument();
                std::string markerNameI = std::string("Contact_")
                    + contact->getNameInDocument() + suffix + "_I";
                std::string markerNameJ = std::string("Contact_")
                    + contact->getNameInDocument() + suffix + "_J";
                auto markerI = makeMbdMarker(markerNameI, placementI);
                auto markerJ = makeMbdMarker(markerNameJ, placementJ);
                dataI.part->addMarker(markerI);
                dataJ.part->addMarker(markerJ);

                auto load = MbD::ASMTForceTorque::With();
                load->setName(contact->getFullName() + suffix);
                load->setMarkerI(markerI->fullName(""));
                load->setMarkerJ(markerJ->fullName(""));
                const auto referenceI = componentI->getPlacementProperty()->getValue();
                const auto referenceJ = componentJ->getPlacementProperty()->getValue();
                // Sweep actual component frames, not interpolated deltas about
                // the assembly origin. The latter describes a different path
                // for off-origin rotations and grossly overestimates travel.
                shapeI = BRepBuilderAPI_Transform(shapeI,
                    ::Part::TopoShape::convert(referenceI.inverse().toMatrix()), false).Shape();
                shapeJ = BRepBuilderAPI_Transform(shapeJ,
                    ::Part::TopoShape::convert(referenceJ.inverse().toMatrix()), false).Shape();
                auto geometry = std::make_shared<ContactGeometry>(shapeI, shapeJ);
                load->setContactStepValidator([geometry, stiffness,
                                              partI = dataI.part, partJ = dataJ.part](
                    const auto& i0, const auto& i1, const auto& j0, const auto& j1) {
                    const auto a0 = contactFramePlacement(i0);
                    const auto a1 = contactFramePlacement(i1);
                    const auto b0 = contactFramePlacement(j0);
                    const auto b1 = contactFramePlacement(j1);
                    // Geometric travel alone is insufficient for a small,
                    // stiff projectile: its elastic compression can be much
                    // smaller than any feature of the contacting geometry.
                    const double inverseMass = (partI->isFixed ? 0 : 1 / partI->principalMassMarker->mass)
                        + (partJ->isFixed ? 0 : 1 / partJ->principalMassMarker->mass);
                    const double impactStep = inverseMass > 0
                        ? 0.02 / std::sqrt(stiffness * inverseMass)
                        : std::numeric_limits<double>::infinity();
                    if (std::abs(i1.time - i0.time) > impactStep
                        && geometry->sweep(a0, a1, b0, b1) != 1) return false;
                    return geometry->acceptStep(
                        a0, a1, b0, b1);
                });
                load->setContactEvaluator(shapeContactEvaluator(
                    geometry,
                    stiffness,
                    damping,
                    staticFriction,
                    dynamicFriction,
                    transitionVelocity
                ));
                mbdAssembly->addForceTorque(load);
                ++solverContactCount;
                continue;
            }

            Base::Placement placementI(sphereI.centre, Base::Rotation());
            Base::Placement placementJ(sphereJ.centre, Base::Rotation());
            placementI = dataI.offsetPlc * placementI;
            placementJ = dataJ.offsetPlc * placementJ;
            const std::string suffix = std::string("_") + componentI->getNameInDocument() + "_"
                + componentJ->getNameInDocument();
            std::string markerNameI = std::string("Contact_")
                + contact->getNameInDocument() + suffix + "_I";
            std::string markerNameJ = std::string("Contact_")
                + contact->getNameInDocument() + suffix + "_J";
            auto markerI = makeMbdMarker(markerNameI, placementI);
            auto markerJ = makeMbdMarker(markerNameJ, placementJ);
            dataI.part->addMarker(markerI);
            dataJ.part->addMarker(markerJ);

            auto limit = MbD::ASMTDistanceLimit::With();
            limit->setName(contact->getFullName() + suffix);
            limit->setMarkerI(markerI->fullName(""));
            limit->setMarkerJ(markerJ->fullName(""));
            limit->settype("=>");
            limit->setlimit(std::to_string(sphereI.radius + sphereJ.radius));
            limit->settol("1.0e-9");
            mbdAssembly->addLimit(limit);
            ++solverContactCount;
        }
    }
    return solverContactCount;
}

void AssemblyObject::resolveContactMove(
    const std::vector<Object*>& movedParts,
    const std::map<Object*, Base::Placement>& previousPlacements
)
{
    ContactTiming timing;
    const auto components = getAssemblyComponents(this);
    const Base::Placement assemblyGlobal = App::GeoFeature::getGlobalPlacement(this);
    std::set<Object*> moved(movedParts.begin(), movedParts.end());
    std::map<Object*, Base::Placement> previous = previousPlacements;

    // A contact response can move another component into a pair that was
    // visited earlier in component order. Revisit the contact graph until no
    // new component joins the moving island. The component count is also a
    // strict upper bound, so malformed or duplicate contact definitions
    // cannot make dragging loop indefinitely.
    const auto contacts = getContacts();
    for (size_t pass = 0; pass < components.size(); ++pass) {
        bool expandedMovingIsland = false;
        std::set<std::pair<Object*, Object*>> processed;
        for (auto* contact : contacts) {
            for (auto [first, second] : contactComponentPairs(contact, components)) {
                ++timing.pairs;
                if (!first || !second || first == second) {
                    continue;
                }
                const bool firstMoved = moved.contains(first);
                const bool secondMoved = moved.contains(second);
                if (firstMoved == secondMoved) {
                    continue;
                }
                const auto ordered = std::less<Object*> {}(first, second)
                    ? std::pair {first, second}
                    : std::pair {second, first};
                if (!processed.insert(ordered).second) {
                    continue;
                }
                Object* driver = firstMoved ? first : second;
                Object* pushed = firstMoved ? second : first;
                auto driverPrevious = previous.find(driver);
                auto* driverPlacement = driver->getPlacementProperty();
                auto* pushedPlacement = pushed->getPlacementProperty();
                if (driverPrevious == previous.end() || !driverPlacement || !pushedPlacement) {
                    continue;
                }

                TopoDS_Shape driverTargetShape;
                TopoDS_Shape pushedShape;
                bool overlapping = false;
                try {
                    auto phaseStart = ContactClock::now();
                    driverTargetShape = contactShapeOf(driver);
                    pushedShape = contactShapeOf(pushed);
                    timing.extractionMs += elapsedMilliseconds(phaseStart);
                    overlapping = shapesOverlap(driverTargetShape, pushedShape, timing);
                }
                catch (const Standard_Failure& e) {
                    Base::Console().warning(
                        "Assembly contact detection failed: %s\n",
                        e.GetMessageString()
                    );
                    continue;
                }
                catch (const std::exception& e) {
                    Base::Console().warning("Assembly contact detection failed: %s\n", e.what());
                    continue;
                }
                const Base::Placement target = driverPlacement->getValue();
                double freeFraction = 0.0;
                double collidingFraction = 1.0;
                bool startedOverlapping = false;
                try {
                    const auto shapeAt = [&](const Base::Placement& placement) {
                        return movedShape(
                            driverTargetShape,
                            placement * target.inverse(),
                            assemblyGlobal,
                            timing
                        );
                    };
                    startedOverlapping
                        = shapesOverlap(shapeAt(driverPrevious->second), pushedShape, timing);
                    if (!overlapping) {
                        if (startedOverlapping) continue; // Dragging out of an initial overlap.
                        const auto worldTarget = assemblyGlobal * target;
                        const auto localShape = BRepBuilderAPI_Transform(driverTargetShape,
                            ::Part::TopoShape::convert(worldTarget.inverse().toMatrix()), false).Shape();
                        ContactGeometry sweepGeometry(localShape, pushedShape, false);
                        freeFraction = sweepGeometry.sweep(assemblyGlobal * driverPrevious->second, worldTarget,
                                                           Base::Placement(), Base::Placement(), true);
                        if (freeFraction == 1) continue;
                        collidingFraction = freeFraction;
                    }
                    if (!startedOverlapping && overlapping) {
                        // Ten bisections resolve a normal mouse step far below the
                        // visual tolerance without paying for 24 expensive BRep
                        // Boolean operations on every contact event.
                        for (int iteration = 0; iteration < 10; ++iteration) {
                            const double middle = (freeFraction + collidingFraction) * 0.5;
                            const Base::Placement middlePlacement
                                = Base::Placement::slerp(driverPrevious->second, target, middle);
                            if (shapesOverlap(shapeAt(middlePlacement), pushedShape, timing)) {
                                collidingFraction = middle;
                            }
                            else {
                                freeFraction = middle;
                            }
                        }
                    }
                }
                catch (...) {
                    continue;
                }

                const Base::Placement contactPlacement
                    = Base::Placement::slerp(driverPrevious->second, target, freeFraction);
                const Vec remainingTranslation = target.getPosition()
                    - contactPlacement.getPosition();
                Vec pushedTranslation = remainingTranslation;
                if (!startedOverlapping && remainingTranslation.Length() >= 1e-9) {
                    const auto entryShape = movedShape(driverTargetShape,
                        contactPlacement * target.inverse(), assemblyGlobal, timing);
                    const Vec normal = assemblyGlobal.getRotation().inverse().multVec(
                        contactBoxResponse(entryShape, pushedShape).normal);
                    const double normalDistance = std::min(0.0, remainingTranslation.Dot(normal));
                    const Vec normalTranslation = normal * normalDistance;
                    const Vec tangentTranslation = remainingTranslation - normalTranslation;
                    pushedTranslation = normalTranslation;
                    if (property<App::PropertyBool>(contact, "FrictionEnabled").getValue()) {
                        const double staticCoefficient
                            = std::max(0.0, number(contact, "StaticFriction"));
                        const double dynamicCoefficient
                            = std::clamp(number(contact, "DynamicFriction"), 0.0, staticCoefficient);
                        const double tangentDistance = tangentTranslation.Length();
                        const double normalTravel = std::abs(normalDistance);
                        if (tangentDistance <= staticCoefficient * normalTravel) {
                            pushedTranslation += tangentTranslation;
                        }
                        else if (tangentDistance > 1e-12) {
                            pushedTranslation += tangentTranslation
                                * std::min(1.0, dynamicCoefficient * normalTravel / tangentDistance);
                        }
                    }
                }
                if (startedOverlapping) {
                    // There is no collision-entry point to resolve when the pair
                    // was already intersecting before this mouse step. Allow the
                    // user to drag it out of the invalid initial state. As soon as
                    // a step separates the shapes, a later re-entry follows the
                    // normal contact response below.
                    driverPlacement->setValue(target);
                }
                else if (isPartGrounded(pushed) || pushedTranslation.Length() < 1e-9) {
                    driverPlacement->setValue(contactPlacement);
                }
                else {
                    driverPlacement->setValue(target);
                    Base::Placement movedPlacement = pushedPlacement->getValue();
                    previous.emplace(pushed, movedPlacement);
                    movedPlacement.move(pushedTranslation);
                    pushedPlacement->setValue(movedPlacement);
                    expandedMovingIsland |= moved.insert(pushed).second;
                    pushed->purgeTouched();

                    // If joints also required an MbD drag system, keep its state in
                    // step with the CAD-side shape response. Otherwise the next
                    // cursor event would restore the pre-contact solver placement.
                    if (auto mapped = objectPartMap.find(pushed);
                        mbdAssembly && mapped != objectPartMap.end() && mapped->second.part) {
                        Base::Placement solverPlacement = movedPlacement;
                        if (!mapped->second.offsetPlc.isIdentity()) {
                            solverPlacement *= mapped->second.offsetPlc.inverse();
                        }
                        const Vec position = solverPlacement.getPosition();
                        mapped->second.part->updateMbDFromPosition3D(
                            std::make_shared<MbD::FullColumn<double>>(
                                std::initializer_list<double> {position.x, position.y, position.z}
                            )
                        );
                        Base::Matrix4D rotation;
                        solverPlacement.getRotation().getValue(rotation);
                        const Vec row0 = rotation.getRow(0);
                        const Vec row1 = rotation.getRow(1);
                        const Vec row2 = rotation.getRow(2);
                        mapped->second.part->updateMbDFromRotationMatrix(
                            row0.x,
                            row0.y,
                            row0.z,
                            row1.x,
                            row1.y,
                            row1.z,
                            row2.x,
                            row2.y,
                            row2.z
                        );
                    }
                }
                driver->purgeTouched();
            }
        }
        if (!expandedMovingIsland) {
            break;
        }
    }
}

PyObject* AssemblyObject::generateDynamics(Object* sim)
{
    if (!sim || sim->getDocument() != getDocument()
        || property<App::PropertyLink>(sim, "Assembly").getValue() != this) {
        invalid(sim, "Study does not belong to this assembly");
    }
    // Keep the previous simulation playable if validation or integration fails.
    auto previousAssembly = mbdAssembly;
    auto previousMap = objectPartMap;
    auto previousMotions = motions;
    const bool previousBundle = bundleFixed;
    try {
        mbdAssembly = makeMbdAssembly();
        objectPartMap.clear();
        motions.clear();
        bundleFixed = false;
        if (!getSubAssemblies().empty()) {
            invalid(sim, "Nested subassemblies are not yet supported by dynamics");
        }
        const auto components = getAssemblyComponents(this);
        std::set<Object*> membership(components.begin(), components.end());
        // Unlike interactive solving, a study must not silently remove broken
        // joints or repair rigid-group membership while producing results.
        if (auto* group = getJointGroup()) {
            for (auto* child : group->getAllChildren()) {
                auto* suppressed = dynamic_cast<App::PropertyBool*>(
                    child->getPropertyByName("Suppressed")
                );
                if (!suppressed || suppressed->getValue()) {
                    continue;
                }
                if (child->isError()) {
                    invalid(child, "Repair the failed joint/rigid group before running dynamics");
                }
                auto* members = dynamic_cast<App::PropertyLinkList*>(
                    child->getPropertyByName("ObjectsToRigidGroup")
                );
                if (members) {
                    std::set<Object*> seen;
                    for (auto* member : members->getValues()) {
                        if (!membership.count(member) || member->isError()
                            || !seen.insert(member).second) {
                            invalid(child, "Rigid group has missing, duplicate or out-of-scope members");
                        }
                    }
                    if (seen.size() < 2) {
                        invalid(child, "Rigid group needs at least two members");
                    }
                }
            }
        }
        rebuildRigidClusters();
        auto grounded = getGroundedParts();
        for (auto* object : grounded) {
            // Fix a rigid cluster once at its representative placement. Adding
            // a fixed joint for every member would pin the same body at several
            // incompatible placements.
            if (object) {
                getMbDPart(object)->isFixed = true;
            }
        }
        for (auto* object : components) {
            if (object->getDocument() != getDocument()) {
                invalid(object, "Nested external dynamics components are not supported yet");
            }
            getMbDPart(object);  // Include free bodies, not just joint-connected bodies.
        }
        auto joints = getJoints(false);
        if (auto* group = getJointGroup()) {
            for (auto* child : group->getAllChildren()) {
                if (!child->getPropertyByName("JointType")) {
                    continue;
                }
                if (property<App::PropertyBool>(child, "Suppressed").getValue()) {
                    continue;
                }
                if (std::find(joints.begin(), joints.end(), child) == joints.end()) {
                    invalid(child, "Repair the incomplete or invalid joint before running dynamics");
                }
            }
        }
        for (auto* joint : joints) {
            for (const char* reference : {"Reference1", "Reference2"}) {
                auto* body = getMovingPartFromRef(joint, reference);
                if (!membership.count(body) && !grounded.count(body)) {
                    invalid(joint, "Joint references a component outside this assembly");
                }
            }
            const auto type = getJointType(joint);
            if (type != JointType::Fixed && type != JointType::Revolute && type != JointType::Slider
                && type != JointType::Cylindrical && type != JointType::Ball
                && type != JointType::RackPinion && type != JointType::Screw
                && type != JointType::Gears && type != JointType::Belt) {
                invalid(joint, "This joint type is not yet qualified for Assembly dynamics");
            }
        }
        std::set<std::pair<Object*, std::string>> drivenAxes;
        const auto inputs = simulationInputs(this, sim);
        const auto eventInputs = eventTargets(sim);
        for (auto* child : inputs) {
            if (child->getPropertyByName("MotionType")) {
                auto* suppressed = dynamic_cast<App::PropertyBool*>(
                    child->getPropertyByName("Suppressed")
                );
                if (suppressed && suppressed->getValue() && !eventInputs.count(child)) {
                    continue;
                }
                auto* joint = property<App::PropertyXLinkSub>(child, "Joint").getValue();
                if (std::find(joints.begin(), joints.end(), joint) == joints.end()) {
                    invalid(child, "Motion must reference an active joint in this assembly");
                }
                const std::string type
                    = property<App::PropertyEnumeration>(child, "MotionType").getValueAsString();
                const auto jointType = getJointType(joint);
                if (!((type == "Angular"
                       && (jointType == JointType::Revolute || jointType == JointType::Cylindrical))
                      || (type == "Linear"
                          && (jointType == JointType::Slider || jointType == JointType::Cylindrical))
                    )) {
                    invalid(child, "Motion type is incompatible with the joint");
                }
                if (!drivenAxes.emplace(joint, type).second) {
                    invalid(child, "Duplicate motion on the same joint axis");
                }
                const auto limitEnabled = [joint](const char* name) {
                    auto* enabled
                        = dynamic_cast<App::PropertyBool*>(joint->getPropertyByName(name));
                    return enabled && enabled->getValue();
                };
                if ((type == "Linear"
                     && (limitEnabled("EnableLengthMin")
                         || limitEnabled("EnableLengthMax")))
                    || (type == "Angular"
                        && (limitEnabled("EnableAngleMin")
                            || limitEnabled("EnableAngleMax")))) {
                    invalid(child, "A prescribed motion cannot drive an axis with enabled limits");
                }
                if (getMbDPart(getMovingPartFromRef(joint, "Reference1"))
                    == getMbDPart(getMovingPartFromRef(joint, "Reference2"))) {
                    invalid(child, "A motion cannot drive an internal rigid-group joint");
                }
                if (property<App::PropertyString>(child, "Formula").getValue()[0] == '\0') {
                    invalid(child, "Motion formula is empty");
                }
                motions.push_back(child);
            }
        }
        jointParts(joints, true);
        for (auto* frictionObject : inputs) {
            if (!frictionObject->getPropertyByName("FrictionModel")) {
                continue;
            }
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                frictionObject->getPropertyByName("Suppressed")
            );
            if (suppressed && suppressed->getValue()) {
                continue;
            }
            auto* joint = property<App::PropertyLink>(frictionObject, "Joint").getValue();
            if (std::find(joints.begin(), joints.end(), joint) == joints.end()) {
                invalid(frictionObject, "Friction must reference an active joint in this assembly");
            }
            const auto type = getJointType(joint);
            const bool rotational = type == JointType::Revolute;
            if (!rotational && type != JointType::Slider) {
                invalid(frictionObject, "Joint friction supports revolute and slider joints");
            }
            const auto asmtJoint = std::find_if(
                mbdAssembly->joints->begin(),
                mbdAssembly->joints->end(),
                [joint](const std::shared_ptr<MbD::ASMTJoint>& candidate) {
                    return candidate && candidate->name == joint->getFullName();
                }
            );
            if (asmtJoint == mbdAssembly->joints->end()) {
                invalid(frictionObject, "Joint friction could not find its solver joint");
            }

            const char* staticName = rotational ? "StaticTorque" : "StaticForce";
            const char* dynamicName
                = rotational ? "DynamicTorque" : "DynamicForce";
            const char* transitionName = rotational ? "AngularTransitionVelocity"
                                                    : "LinearTransitionVelocity";
            const char* viscousName = rotational ? "AngularViscousDamping"
                                                 : "LinearViscousDamping";
            const std::string frictionModel = std::string(
                property<App::PropertyEnumeration>(frictionObject, "FrictionModel").getValueAsString()
            );
            const bool reactionBased = frictionModel != "Specified resistance";
            if (!rotational && (frictionModel == "Rolling resistance" || frictionModel == "Thrust bearing"))
                invalid(frictionObject, "Rolling and thrust bearing friction require a revolute joint");
            double staticMagnitude = number(frictionObject, staticName);
            double dynamicMagnitude = number(frictionObject, dynamicName);
            double transitionVelocity = number(frictionObject, transitionName);
            double viscousCoefficient = number(frictionObject, viscousName);
            if (rotational) {
                staticMagnitude = 1000 * quantityAs(frictionObject, staticName, "N*mm");
                dynamicMagnitude = 1000 * quantityAs(frictionObject, dynamicName, "N*mm");
                transitionVelocity = quantityAs(frictionObject, transitionName, "rad/s");
                viscousCoefficient = 1000 * quantityAs(frictionObject, viscousName, "N*mm*s/rad");
            }
            const double staticCoefficient = number(frictionObject, "StaticCoefficient");
            const double dynamicCoefficient = number(frictionObject, "DynamicCoefficient");
            const double effectiveRadius
                = quantityAs(frictionObject, "EffectiveRadius", "mm");
            if ((!reactionBased
                 && (staticMagnitude < dynamicMagnitude || dynamicMagnitude < 0))
                || (reactionBased
                    && (staticCoefficient < dynamicCoefficient
                        || dynamicCoefficient < 0 || (rotational && !(effectiveRadius > 0))))
                || !(transitionVelocity > 0) || viscousCoefficient < 0) {
                invalid(frictionObject, reactionBased
                        ? "Reaction-based friction requires static coefficient >= dynamic "
                          "coefficient >= 0, a positive transition velocity, nonnegative "
                          "viscous damping, and a positive revolute bearing radius"
                        : "Specified friction requires static resistance >= dynamic resistance "
                          ">= 0, a positive transition velocity, and nonnegative viscous damping");
            }
            auto friction = MbD::ASMTForceTorque::With();
            friction->setName(frictionObject->getNameInDocument());
            friction->setMarkerI((*asmtJoint)->markerI);
            friction->setMarkerJ((*asmtJoint)->markerJ);
            if (reactionBased) {
                friction->setReactionAxisFriction(
                    staticCoefficient,
                    dynamicCoefficient,
                    transitionVelocity,
                    viscousCoefficient,
                    effectiveRadius,
                    rotational,
                    *asmtJoint,
                    frictionModel == "Thrust bearing"
                );
            }
            else {
                friction->setAxisFriction(
                    staticMagnitude,
                    dynamicMagnitude,
                    transitionVelocity,
                    viscousCoefficient,
                    rotational
                );
            }
            mbdAssembly->addForceTorque(friction);
        }
        contactParts(getContacts(sim), true);

        std::map<std::shared_ptr<MbD::ASMTPart>, GProp_GProps> aggregates;
        std::map<Object*, Mass> componentMasses;
        Py::Dict masses;
        for (const auto& [object, data] : objectPartMap) {
            if (grounded.count(object)) {
                continue;  // Ground can be a datum with no solid/material.
            }
            if (!membership.count(object)) {
                invalid(object, "Joint references an out-of-scope component");
            }
            const auto local = massOf(object);
            componentMasses.emplace(object, local);
            masses[object->getNameInDocument()] = massDict(local);
            aggregates[data.part].Add(massOf(object, data.offsetPlc).properties);
        }
        for (const auto& [part, mass] : aggregates) {
            assignMass(mass, part);
        }
        if (aggregates.empty()) {
            invalid(sim, "Dynamics requires at least one moving solid body");
        }

        struct InitialState
        {
            Object* linearSource = nullptr;
            Object* angularSource = nullptr;
            Vec linear;
            Vec angular;
        };
        std::map<std::shared_ptr<MbD::ASMTPart>, InitialState> initialStates;
        for (auto* child : inputs) {
            if (!child->getPropertyByName("InitialVelocityType")) {
                continue;
            }
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                child->getPropertyByName("Suppressed")
            );
            if (suppressed && suppressed->getValue()) {
                continue;
            }
            auto* component = property<App::PropertyLink>(child, "Component").getValue();
            if (!component || !membership.count(component)) {
                invalid(child, "Initial velocity component is outside this assembly");
            }
            if (grounded.count(component)) {
                invalid(child, "A grounded component cannot have an initial velocity");
            }
            const std::string type
                = property<App::PropertyEnumeration>(child, "InitialVelocityType")
                      .getValueAsString();
            auto& state = initialStates[getMbDPart(component)];
            if (type == "Linear") {
                if (state.linearSource) {
                    invalid(child, "Duplicate linear initial velocity on the same rigid body");
                }
                state.linearSource = child;
                state.linear = direction(child, "Direction")
                    * quantityAs(child, "LinearVelocity", "mm/s");
            }
            else if (type == "Angular") {
                if (state.angularSource) {
                    invalid(child, "Duplicate angular initial velocity on the same rigid body");
                }
                state.angularSource = child;
                state.angular = direction(child, "Direction")
                    * quantityAs(child, "AngularVelocity", "rad/s");
            }
            else {
                invalid(child, "Unknown initial velocity type");
            }
        }
        for (const auto& [part, state] : initialStates) {
            // The UI specifies velocity at a component's centre of mass,
            // whereas ASMT expects velocity at the aggregate rigid body's COM.
            auto* source = state.linearSource ? state.linearSource : state.angularSource;
            auto* component = property<App::PropertyLink>(source, "Component").getValue();
            const auto& mapping = objectPartMap.at(component);
            const auto local = componentMasses.at(component).properties.CentreOfMass();
            Vec componentCentre;
            mapping.offsetPlc.multVec(Vec(local.X(), local.Y(), local.Z()), componentCentre);
            const auto aggregate = aggregates.at(part).CentreOfMass();
            const auto offset = getMbdPlacement(part).getRotation().multVec(
                Vec(aggregate.X(), aggregate.Y(), aggregate.Z()) - componentCentre
            );
            const auto velocity = state.linear + state.angular.Cross(offset);
            part->setCenterOfMassVelocity3D(
                velocity.x,
                velocity.y,
                velocity.z,
                state.angular.x,
                state.angular.y,
                state.angular.z
            );
        }

        auto parameters = mbdAssembly->simulationParameters;
        const bool legacy = sim->getPropertyByName("aTimeStart") != nullptr;
        parameters->settstart(number(sim, legacy ? "aTimeStart" : "StartTime"));
        parameters->settend(number(sim, legacy ? "bTimeEnd" : "EndTime"));
        parameters->sethout(number(sim, legacy ? "cTimeStepOutput" : "OutputStep"));
        parameters->sethmin(number(sim, "MinimumStep"));
        parameters->sethmax(number(sim, "MaximumStep"));
        parameters->seterrorTol(number(sim, legacy ? "fGlobalErrorTolerance" : "Tolerance"));
        parameters->iterMaxDyn = 25;
        Vec gravity;
        if (property<App::PropertyBool>(sim, "GravityEnabled").getValue()) {
            const double magnitude = number(sim, "GravityMagnitude");
            if (magnitude < 0) {
                invalid(sim, "Gravity magnitude must be nonnegative");
            }
            gravity = direction(sim, "GravityDirection") * magnitude;
        }
        mbdAssembly->constantGravity->setg(gravity.x, gravity.y, gravity.z);

        for (auto* child : inputs) {
            if (child->getPropertyByName("MotionType")
                || child->getPropertyByName("InitialVelocityType")
                || child->getPropertyByName("ContactType")
                || child->getPropertyByName("FrictionModel")
                || child->getPropertyByName("IsSimulationEvent")
                || child->getPropertyByName("IsPointMeasurement")) {
                continue;
            }
            if (!child->getPropertyByName("LoadType")) {
                invalid(child, "Unknown simulation input object");
            }
            auto* suppressed = dynamic_cast<App::PropertyBool*>(
                child->getPropertyByName("Suppressed")
            );
            if (suppressed && suppressed->getValue() && !eventInputs.count(child)) {
                continue;
            }
            const std::string type
                = property<App::PropertyEnumeration>(child, "LoadType").getValueAsString();
            auto load = MbD::ASMTForceTorque::With();
            load->setName(child->getNameInDocument());
            auto attachment = [&](const char* bodyName, const char* placementName, const char* suffix
                              ) {
                Object* body = property<App::PropertyLink>(child, bodyName).getValue();
                auto placement = property<App::PropertyPlacement>(child, placementName).getValue();
                std::string name = std::string("Load_") + child->getNameInDocument() + suffix;
                if (!body) {
                    mbdAssembly->addMarker(makeMbdMarker(name, placement));
                    return std::string("/OndselAssembly/") + name;
                }
                if (!membership.count(body)) {
                    invalid(child, "Load body is outside this assembly");
                }
                const auto data = getMbDData(body);
                placement = data.offsetPlc * placement;
                data.part->addMarker(makeMbdMarker(name, placement));
                return std::string("/OndselAssembly/") + data.part->name + "/" + name;
            };
            auto* bodyI = property<App::PropertyLink>(child, "BodyI").getValue();
            auto* bodyJ = property<App::PropertyLink>(child, "BodyJ").getValue();
            if (!bodyI) {
                invalid(child, "BodyI is required; BodyJ may be empty for ground");
            }
            if (!membership.count(bodyI) || (bodyJ && !membership.count(bodyJ))) {
                invalid(child, "Load body is outside this assembly");
            }
            if (bodyJ && getMbDPart(bodyI) == getMbDPart(bodyJ)) {
                invalid(child, "Load endpoints belong to the same rigid body");
            }
            load->setMarkerI(attachment("BodyI", "AttachmentI", "_I"));
            load->setMarkerJ(attachment("BodyJ", "AttachmentJ", "_J"));
            if (type == "Force" || type == "Torque") {
                auto axis = direction(child, "Direction");
                const bool follower = property<App::PropertyBool>(child, "Follower").getValue();
                if (follower) {
                    const auto frame = bodyI->getPlacementProperty()->getValue()
                        * property<App::PropertyPlacement>(child, "AttachmentI").getValue();
                    axis = frame.getRotation().inverse().multVec(axis);
                }
                load->setFollower(follower);
                const std::string formula
                    = property<App::PropertyString>(child, "Formula").getValue();
                if (!formula.empty()) {
                    // FreeCAD force and torque properties use N and N mm in the
                    // task UI, while the solver bridge uses kg-mm-s base values.
                    const std::string solverFormula = "1000*(" + formula + ")";
                    if (type == "Force") {
                        load->setForceFormula3D(axis.x, axis.y, axis.z, solverFormula);
                    }
                    else {
                        load->setTorqueFormula3D(axis.x, axis.y, axis.z, solverFormula);
                    }
                }
                else {
                    auto vector = axis * number(child, type.c_str());
                    if (type == "Force") {
                        load->setForce3D(vector.x, vector.y, vector.z);
                    }
                    else {
                        load->setTorque3D(vector.x, vector.y, vector.z);
                    }
                }
            }
            else if (type == "SpringDamper") {
                load->setSpringDamper(
                    number(child, "Stiffness"),
                    number(child, "Damping"),
                    number(child, "RestLength")
                );
            }
            else if (type == "TorsionalSpringDamper") {
                load->setTorsionalSpringDamper(
                    1000 * quantityAs(child, "TorsionalStiffness", "N*mm/rad"),
                    1000 * quantityAs(child, "TorsionalDamping", "N*mm*s/rad"),
                    quantityAs(child, "FreeAngle", "rad")
                );
            }
            else if (type == "Bushing"
                     && property<App::PropertyBool>(child, "CoupledBushing").getValue()) {
                std::array<double, 36> k{}, c{};
                const auto read = [&](const char* name, auto& matrix) {
                    const auto& values = property<App::PropertyFloatList>(child, name).getValues();
                    if (values.size() != 36) invalid(child, "Bushing matrices must contain 36 entries");
                    std::transform(values.begin(), values.end(), matrix.begin(),
                                   [](double value) { return 1000 * value; });
                };
                read("BushingStiffnessMatrix", k);
                read("BushingDampingMatrix", c);
                load->setCoupledBushing(k, c);
            }
            else if (type == "Bushing") {
                std::array<double, 3> linearStiffness;
                std::array<double, 3> linearDamping;
                std::array<double, 3> angularStiffness;
                std::array<double, 3> angularDamping;
                constexpr std::array<const char*, 3> axes {"X", "Y", "Z"};
                for (size_t axis = 0; axis < axes.size(); ++axis) {
                    const std::string suffix = axes[axis];
                    linearStiffness[axis] = number(child, ("BushingLinearStiffness" + suffix).c_str());
                    linearDamping[axis] = number(child, ("BushingLinearDamping" + suffix).c_str());
                    angularStiffness[axis] = 1000 * quantityAs(
                        child, ("BushingAngularStiffness" + suffix).c_str(), "N*mm/rad"
                    );
                    angularDamping[axis] = 1000 * quantityAs(
                        child, ("BushingAngularDamping" + suffix).c_str(), "N*mm*s/rad"
                    );
                }
                load->setBushing(
                    linearStiffness, linearDamping, angularStiffness, angularDamping
                );
            }
            else {
                invalid(child, "Unknown load type");
            }
            mbdAssembly->addForceTorque(load);
        }
        size_t eventMarkerIndex = 0;
        EventRunScope eventScope {mbdAssembly.get()};
        configureEvents(sim, mbdAssembly.get(), [&](Object* component, const Base::Placement& local) {
            std::string name = "EventMarker_" + std::to_string(eventMarkerIndex++);
            auto placement = local;
            if (!component) {
                mbdAssembly->addMarker(makeMbdMarker(name, placement));
                return std::string("/OndselAssembly/") + name;
            }
            const auto data = getMbDData(component);
            placement = data.offsetPlc * local;
            data.part->addMarker(makeMbdMarker(name, placement));
            return std::string("/OndselAssembly/") + data.part->name + "/" + name;
        });
        mbdAssembly->runDYNAMIC();

        Py::Dict result, bodies, jointResults, loadResults, limitResults;
        result["SchemaVersion"] = Py::Long(2);
        Py::List eventLog;
        if (auto events = mbdAssembly->dynamicEvents) {
            for (const auto& firing : events->firings) {
                Py::Dict entry;
                entry["Event"] = Py::String(events->events.at(firing.event).name);
                entry["Time"] = Py::Float(firing.time);
                eventLog.append(entry);
            }
        }
        result["EventLog"] = eventLog;
        result["CoordinateSystem"] = Py::String("Assembly");
        result["Times"] = series(mbdAssembly->times);
        Py::List frames;
        for (size_t k = 1; k < mbdAssembly->times->size(); ++k) {
            frames.append(Py::Long(k));
        }
        result["SolverFrames"] = frames;
        result["MassProperties"] = masses;
        const size_t sampleCount = mbdAssembly->times->size() - 1;
        std::vector<double> translationalEnergy(sampleCount, 0);
        std::vector<double> rotationalEnergy(sampleCount, 0);
        std::vector<double> gravitationalEnergy(sampleCount, 0);
        for (auto* object : components) {
            const auto data = objectPartMap.at(object);
            auto part = data.part;
            Py::List placements, velocities, accelerations, omegas, alphas;
            Py::List translational, rotational, gravitational, mechanical;
            size_t sample = 0;
            for (size_t k = 1; k < mbdAssembly->times->size(); ++k) {
                part->updateForFrame(k);
                auto placement = getMbdPlacement(part) * data.offsetPlc;
                auto position = placement.getPosition();
                const auto rotation = placement.getRotation();
                Py::Tuple pose(7);
                pose[0] = Py::Float(position.x);
                pose[1] = Py::Float(position.y);
                pose[2] = Py::Float(position.z);
                for (int axis = 0; axis < 4; ++axis) {
                    pose[axis + 3] = Py::Float(rotation[axis]);
                }
                placements.append(pose);
                Vec omega(part->omexs->at(k), part->omeys->at(k), part->omezs->at(k));
                Vec alpha(part->alpxs->at(k), part->alpys->at(k), part->alpzs->at(k));
                Vec v(part->vxs->at(k), part->vys->at(k), part->vzs->at(k));
                Vec a(part->axs->at(k), part->ays->at(k), part->azs->at(k));
                Vec offset = getMbdPlacement(part).getRotation().multVec(data.offsetPlc.getPosition());
                v += omega.Cross(offset);
                a += alpha.Cross(offset) + omega.Cross(omega.Cross(offset));
                velocities.append(xyz(v.x, v.y, v.z));
                accelerations.append(xyz(a.x, a.y, a.z));
                omegas.append(xyz(omega.x, omega.y, omega.z));
                alphas.append(xyz(alpha.x, alpha.y, alpha.z));
                double translationalValue = 0;
                double rotationalValue = 0;
                double gravitationalValue = 0;
                if (auto found = componentMasses.find(object);
                    found != componentMasses.end()) {
                    const Mass& mass = found->second;
                    const Vec localCentre(
                        mass.properties.CentreOfMass().X(),
                        mass.properties.CentreOfMass().Y(),
                        mass.properties.CentreOfMass().Z()
                    );
                    const Vec centreOffset = rotation.multVec(localCentre);
                    const Vec centreVelocity = v + omega.Cross(centreOffset);
                    const Vec localOmega = rotation.inverse().multVec(omega);
                    const auto inertia = mass.properties.MatrixOfInertia();
                    const Vec inertiaOmega(
                        inertia(1, 1) * localOmega.x + inertia(1, 2) * localOmega.y
                            + inertia(1, 3) * localOmega.z,
                        inertia(2, 1) * localOmega.x + inertia(2, 2) * localOmega.y
                            + inertia(2, 3) * localOmega.z,
                        inertia(3, 1) * localOmega.x + inertia(3, 2) * localOmega.y
                            + inertia(3, 3) * localOmega.z
                    );
                    // kg mm^2/s^2 -> N mm (mJ).
                    translationalValue = 0.0005 * mass.properties.Mass()
                        * centreVelocity.Sqr();
                    rotationalValue = 0.0005 * localOmega.Dot(inertiaOmega);
                    const Vec centrePosition = position + centreOffset;
                    gravitationalValue = -0.001 * mass.properties.Mass()
                        * gravity.Dot(centrePosition);
                }
                translational.append(Py::Float(translationalValue));
                rotational.append(Py::Float(rotationalValue));
                gravitational.append(Py::Float(gravitationalValue));
                mechanical.append(Py::Float(
                    translationalValue + rotationalValue + gravitationalValue
                ));
                translationalEnergy[sample] += translationalValue;
                rotationalEnergy[sample] += rotationalValue;
                gravitationalEnergy[sample] += gravitationalValue;
                ++sample;
            }
            Py::Dict body;
            body["Placements"] = placements;
            body["Velocity"] = velocities;
            body["Acceleration"] = accelerations;
            body["AngularVelocity"] = omegas;
            body["AngularAcceleration"] = alphas;
            body["TranslationalKineticEnergy"] = translational;
            body["RotationalKineticEnergy"] = rotational;
            body["GravitationalPotentialEnergy"] = gravitational;
            body["MechanicalEnergy"] = mechanical;
            bodies[object->getNameInDocument()] = body;
        }
        for (auto& item : *mbdAssembly->joints) {
            Py::Dict joint = reactions(item);
            joint["Power"] = series(item->powers, 0.001);
            joint["Work"] = cumulativeIntegral(mbdAssembly->times, item->powers, 0.001);
            jointResults[item->name] = joint;
        }
        for (auto& item : *mbdAssembly->motions) {
            Py::Dict motion = reactions(item);
            motion["Power"] = series(item->powers, 0.001);
            motion["Work"] = cumulativeIntegral(mbdAssembly->times, item->powers, 0.001);
            jointResults[item->name] = motion;
        }
        std::vector<double> storedEnergy(sampleCount, 0);
        std::vector<double> dissipatedPower(sampleCount, 0);
        std::vector<double> externalPower(sampleCount, 0);
        for (auto& item : *mbdAssembly->forcesTorques) {
            Py::Dict load = reactions(item);
            load["Power"] = series(item->powers, 0.001);  // kg mm^2/s^3 -> mW
            load["StoredEnergy"] = series(item->storedEnergies, 0.001);
            load["DissipatedPower"] = series(item->dissipatedPowers, 0.001);
            load["Work"] = cumulativeIntegral(mbdAssembly->times, item->powers, 0.001);
            load["DissipatedEnergy"] = cumulativeIntegral(
                mbdAssembly->times, item->dissipatedPowers, 0.001
            );
            for (size_t sample = 0; sample < sampleCount; ++sample) {
                const size_t k = sample + 1;
                storedEnergy[sample] += 0.001 * item->storedEnergies->at(k);
                dissipatedPower[sample] += 0.001 * item->dissipatedPowers->at(k);
                if (!item->isPassive()) {
                    externalPower[sample] += 0.001 * item->powers->at(k);
                }
            }
            loadResults[item->name] = load;
        }
        for (const auto& item : *mbdAssembly->motions) {
            for (size_t sample = 0; sample < sampleCount; ++sample) {
                externalPower[sample] += 0.001 * item->powers->at(sample + 1);
            }
        }
        for (const auto& item : *mbdAssembly->limits) {
            if (item->behavior != "Compliant") {
                continue;
            }
            Py::Dict limit;
            limit["Power"] = series(item->powers, 0.001);
            limit["StoredEnergy"] = series(item->storedEnergies, 0.001);
            limit["DissipatedPower"] = series(item->dissipatedPowers, 0.001);
            limit["DissipatedEnergy"] = cumulativeIntegral(
                mbdAssembly->times, item->dissipatedPowers, 0.001
            );
            for (size_t sample = 0; sample < sampleCount; ++sample) {
                storedEnergy[sample] += 0.001 * item->storedEnergies->at(sample + 1);
                dissipatedPower[sample] += 0.001 * item->dissipatedPowers->at(sample + 1);
            }
            limitResults[item->name] = limit;
        }
        std::vector<double> kineticEnergy(sampleCount);
        std::vector<double> mechanicalEnergy(sampleCount);
        for (size_t sample = 0; sample < sampleCount; ++sample) {
            kineticEnergy[sample] = translationalEnergy[sample] + rotationalEnergy[sample];
            mechanicalEnergy[sample] = kineticEnergy[sample]
                + gravitationalEnergy[sample] + storedEnergy[sample];
        }
        const auto externalWork = integratedSeries(mbdAssembly->times, externalPower);
        const auto dissipatedEnergy = integratedSeries(mbdAssembly->times, dissipatedPower);
        std::vector<double> balanceResidual(sampleCount, 0);
        for (size_t sample = 0; sample < sampleCount; ++sample) {
            balanceResidual[sample] = mechanicalEnergy[sample] - mechanicalEnergy.front()
                - externalWork[sample] + dissipatedEnergy[sample];
        }
        Py::Dict systemEnergy;
        systemEnergy["TranslationalKineticEnergy"] = scalarSeries(translationalEnergy);
        systemEnergy["RotationalKineticEnergy"] = scalarSeries(rotationalEnergy);
        systemEnergy["KineticEnergy"] = scalarSeries(kineticEnergy);
        systemEnergy["GravitationalPotentialEnergy"] = scalarSeries(gravitationalEnergy);
        systemEnergy["StoredEnergy"] = scalarSeries(storedEnergy);
        systemEnergy["MechanicalEnergy"] = scalarSeries(mechanicalEnergy);
        systemEnergy["ExternalPower"] = scalarSeries(externalPower);
        systemEnergy["DissipatedPower"] = scalarSeries(dissipatedPower);
        systemEnergy["ExternalWork"] = scalarSeries(externalWork);
        systemEnergy["DissipatedEnergy"] = scalarSeries(dissipatedEnergy);
        systemEnergy["EnergyBalanceResidual"] = scalarSeries(balanceResidual);
        Py::Dict energyResults;
        energyResults["System"] = systemEnergy;
        result["Bodies"] = bodies;
        result["JointReactions"] = jointResults;
        result["Loads"] = loadResults;
        result["Limits"] = limitResults;
        result["Energy"] = energyResults;
        motions = previousMotions;
        bundleFixed = previousBundle;
        return Py::new_reference_to(result);
    }
    catch (...) {
        mbdAssembly = previousAssembly;
        objectPartMap = previousMap;
        motions = previousMotions;
        bundleFixed = previousBundle;
        throw;
    }
}

PyObject* AssemblyObject::getSimulationResults()
{
    if (!mbdAssembly || !mbdAssembly->times || mbdAssembly->times->size() < 2) {
        throw std::runtime_error("No completed kinematic simulation results");
    }

    Py::Dict result, bodies;
    result["SchemaVersion"] = Py::Long(1);
    result["CoordinateSystem"] = Py::String("Assembly");
    result["Times"] = series(mbdAssembly->times);
    Py::List frames;
    for (size_t k = 1; k < mbdAssembly->times->size(); ++k) {
        frames.append(Py::Long(k));
    }
    result["SolverFrames"] = frames;
    result["MassProperties"] = Py::Dict();

    for (auto* object : getAssemblyComponents(this)) {
        auto found = objectPartMap.find(object);
        if (found == objectPartMap.end()) {
            continue;
        }
        const auto& data = found->second;
        auto part = data.part;
        Py::List placements, velocities, accelerations, omegas, alphas;
        for (size_t k = 1; k < mbdAssembly->times->size(); ++k) {
            part->updateForFrame(k);
            auto placement = getMbdPlacement(part) * data.offsetPlc;
            auto position = placement.getPosition();
            const auto rotation = placement.getRotation();
            Py::Tuple pose(7);
            pose[0] = Py::Float(position.x);
            pose[1] = Py::Float(position.y);
            pose[2] = Py::Float(position.z);
            for (int axis = 0; axis < 4; ++axis) {
                pose[axis + 3] = Py::Float(rotation[axis]);
            }
            placements.append(pose);

            Vec omega(part->omexs->at(k), part->omeys->at(k), part->omezs->at(k));
            Vec alpha(part->alpxs->at(k), part->alpys->at(k), part->alpzs->at(k));
            Vec velocity(part->vxs->at(k), part->vys->at(k), part->vzs->at(k));
            Vec acceleration(part->axs->at(k), part->ays->at(k), part->azs->at(k));
            Vec offset = getMbdPlacement(part).getRotation().multVec(
                data.offsetPlc.getPosition()
            );
            velocity += omega.Cross(offset);
            acceleration += alpha.Cross(offset) + omega.Cross(omega.Cross(offset));
            velocities.append(xyz(velocity.x, velocity.y, velocity.z));
            accelerations.append(xyz(acceleration.x, acceleration.y, acceleration.z));
            omegas.append(xyz(omega.x, omega.y, omega.z));
            alphas.append(xyz(alpha.x, alpha.y, alpha.z));
        }
        Py::Dict body;
        body["Placements"] = placements;
        body["Velocity"] = velocities;
        body["Acceleration"] = accelerations;
        body["AngularVelocity"] = omegas;
        body["AngularAcceleration"] = alphas;
        bodies[object->getNameInDocument()] = body;
    }
    result["Bodies"] = bodies;
    result["JointReactions"] = Py::Dict();
    result["Loads"] = Py::Dict();
    return Py::new_reference_to(result);
}
}  // namespace Assembly
