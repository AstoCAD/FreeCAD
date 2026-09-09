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
#include "EventRuntime.h"
#include <CXX/Objects.hxx>
#include <App/DocumentObject.h>
#include <App/PropertyStandard.h>
#include <App/PropertyUnits.h>
#include <App/PropertyLinks.h>
#include <OndselSolver/ASMTAssembly.h>
#include <OndselSolver/ASMTForceTorque.h>
#include <OndselSolver/ASMTMotion.h>
#include <OndselSolver/ASMTMarker.h>
#include <OndselSolver/AppliedForceTorque.h>
#include <OndselSolver/PrescribedMotion.h>
#include <OndselSolver/EndFrameqct.h>
#include <OndselSolver/System.h>
#include <OndselSolver/ASMTTime.h>
#include <OndselSolver/SymbolicParser.h>
#include <OndselSolver/BasicUserFunction.h>
#include <OndselSolver/Constant.h>
#include <cmath>
#include <map>
#include <stdexcept>

namespace Assembly
{
namespace
{
using Object = App::DocumentObject;
template<class T>
T& prop(Object* obj, const char* name)
{
    auto* value = dynamic_cast<T*>(obj->getPropertyByName(name));
    if (!value) {
        throw std::invalid_argument(obj->getFullName() + ": missing event property " + name);
    }
    return *value;
}
bool flag(Object* obj, const char* name)
{
    return prop<App::PropertyBool>(obj, name).getValue();
}
double number(Object* obj, const char* name)
{
    return prop<App::PropertyFloat>(obj, name).getValue();
}
std::string choice(Object* obj, const char* name)
{
    return prop<App::PropertyEnumeration>(obj, name).getValueAsString();
}
std::vector<Object*> activeEvents(Object* study)
{
    std::vector<Object*> result;
    for (auto* obj : prop<App::PropertyLinkList>(study, "Group").getValues()) {
        if (obj && obj->getPropertyByName("IsSimulationEvent") && !flag(obj, "Suppressed")) {
            result.push_back(obj);
        }
    }
    return result;
}
Py::Object module()
{
    return Py::Object(PyImport_ImportModule("SimulationEvents"), true);
}
using State = MbD::AppliedForceTorque::FrameState;
Base::Vector3d vec(const std::array<double, 3>& v)
{
    return Base::Vector3d(v[0], v[1], v[2]);
}
Base::Vector3d local(const State& frame, const Base::Vector3d& value)
{
    const auto& r = frame.rotation;
    return Base::Vector3d(
        r[0] * value.x + r[3] * value.y + r[6] * value.z,
        r[1] * value.x + r[4] * value.y + r[7] * value.z,
        r[2] * value.x + r[5] * value.y + r[8] * value.z
    );
}
State state(MbD::ASMTAssembly* assembly, const std::string& marker)
{
    auto frame = std::dynamic_pointer_cast<MbD::EndFramec>(assembly->markerAt(marker)->mbdObject);
    return MbD::AppliedForceTorque::frameState(frame);
}
struct Target
{
    Object* object = nullptr;
    MbD::ASMTAssembly* assembly = nullptr;
    std::shared_ptr<MbD::ASMTItemIJ> source;
    std::shared_ptr<MbD::PrescribedMotion> motion;
    std::shared_ptr<MbD::AppliedForceTorque> load;
    std::shared_ptr<std::vector<std::shared_ptr<MbD::Constraint>>> constraints;
    std::shared_ptr<MbD::Symbolic> magnitude;
    std::array<double, 3> direction {};
    std::string measureI, measureJ;
    bool angular = false, torque = false, enabled = true;

    void enable(bool value)
    {
        enabled = value;
        if (load) {
            load->setEnabled(value);
        }
        else {
            motion->constraints = value
                ? constraints
                : std::make_shared<std::vector<std::shared_ptr<MbD::Constraint>>>();
        }
    }
    std::shared_ptr<MbD::Symbolic> parse(const std::string& formula)
    {
        auto parser = std::make_shared<MbD::SymbolicParser>();
        parser->owner = source.get();
        parser->variables->insert({"time", assembly->geoTime()});
        parser->parseUserFunction(std::make_shared<MbD::BasicUserFunction>(formula, 1.0));
        auto result = parser->stack->top();
        result->createMbD(assembly->mbdSystem, assembly->mbdUnits);
        return result->simplified(result);
    }
    void setFormula(const std::string& formula)
    {
        if (load) {
            magnitude = parse(formula);
            load->setRuntimeFormula(direction, parse("1000*(" + formula + ")"), torque);
        }
        else {
            setMotionFunction(parse(formula));
        }
    }
    void setMotionFunction(const std::shared_ptr<MbD::Symbolic>& function)
    {
        (angular ? motion->phiBlk : motion->zBlk) = function;
        motion->initMotions();
        motion->frmI->initializeGlobally();
        motion->frmI->postInput();
    }
    void apply(const Py::Dict& action, double time, double end)
    {
        const std::string kind = Py::String(action["kind"]).as_std_string();
        if (kind == "Deactivate") {
            enable(false);
            return;
        }
        if (kind == "Activate" && (load || enabled)) {
            enable(true);
            return;
        }
        double position = 0, velocity = 0, value = 0;
        if (motion) {
            auto i = state(assembly, measureI), j = state(assembly, measureJ);
            const auto delta = vec(j.position) - vec(i.position);
            if (angular) {
                const auto x = local(i, Base::Vector3d(j.rotation[0], j.rotation[3], j.rotation[6]));
                position = std::atan2(x.y, x.x);
                velocity = local(i, vec(j.omega) - vec(i.omega)).z;
                // Keep the winding of an active prescribed rotation.
                if (enabled) {
                    position = motion->phiBlk->getValue();
                }
            }
            else {
                position = local(i, delta).z;
                velocity = local(i, vec(j.velocity) - vec(i.velocity) - vec(i.omega).Cross(delta)).z;
            }
        }
        else if (enabled) {
            value = magnitude ? magnitude->getValue()
                              : number(object, torque ? "Torque" : "Force") / 1000.0;
        }
        if (kind == "Activate") {
            // Resume the profile clock without projecting the part to where
            // the inactive motor would have been. Velocity may jump; a Ramp
            // action is appropriate for a continuous velocity transition.
            auto function = angular ? motion->phiBlk : motion->zBlk;
            setMotionFunction(MbD::Symbolic::sum(
                function,
                std::make_shared<MbD::Constant>(position - function->getValue())
            ));
            enable(true);
            return;
        }
        Py::Tuple args(7);
        args[0] = Py::Object(object->getPyObject(), true);
        args[1] = action;
        args[2] = Py::Float(time);
        args[3] = Py::Float(position);
        args[4] = Py::Float(velocity);
        args[5] = Py::Float(value);
        args[6] = Py::Float(end);
        auto formula = Py::Callable(module().getAttr("action_formula")).apply(args);
        setFormula(Py::String(formula).as_std_string());
        enable(true);
    }
};
}  // namespace

std::set<Object*> eventTargets(Object* study)
{
    const auto events = activeEvents(study);
    std::set<Object*> result;
    if (events.empty()) {
        return result;
    }
    Py::Tuple args(1);
    args[0] = Py::Object(study->getPyObject(), true);
    Py::Callable(module().getAttr("describe")).apply(args);
    for (auto* event : events) {
        for (auto* target : prop<App::PropertyLinkList>(event, "Targets").getValues()) {
            result.insert(target);
        }
    }
    return result;
}

EventRunScope::~EventRunScope()
{
    if (assembly->mbdSystem) {
        assembly->mbdSystem->dynamicEvents.reset();
    }
    assembly->dynamicEvents.reset();
}

void configureEvents(Object* study, MbD::ASMTAssembly* assembly, const EventMarkerFactory& marker)
{
    auto objects = activeEvents(study);
    if (objects.empty()) {
        return;
    }
    auto engine = std::make_shared<MbD::DynamicEvents>();
    std::map<Object*, std::shared_ptr<Target>> targets;
    for (auto* object : eventTargets(study)) {
        auto target = std::make_shared<Target>();
        target->object = object;
        target->assembly = assembly;
        if (object->getPropertyByName("MotionType")) {
            target->angular = choice(object, "MotionType") == "Angular";
            auto* joint = prop<App::PropertyXLinkSub>(object, "Joint").getValue();
            const std::string name = joint->getFullName()
                + (target->angular ? "-AngularMotion" : "-LinearMotion");
            for (auto& motion : *assembly->motions) {
                if (motion->name == name) {
                    target->source = motion;
                }
            }
        }
        else {
            target->torque = choice(object, "LoadType") == "Torque";
            for (auto& load : *assembly->forcesTorques) {
                if (load->name == object->getNameInDocument()) {
                    target->source = load;
                }
            }
            auto axis = prop<App::PropertyVector>(object, "Direction").getValue();
            axis.Normalize();
            if (flag(object, "Follower")) {
                auto* component = prop<App::PropertyLink>(object, "BodyI").getValue();
                auto frame = component->getPlacementProperty()->getValue()
                    * prop<App::PropertyPlacement>(object, "AttachmentI").getValue();
                axis = frame.getRotation().inverse().multVec(axis);
            }
            target->direction = {axis.x, axis.y, axis.z};
        }
        if (!target->source) {
            throw std::invalid_argument(object->getFullName() + ": event target was not built");
        }
        if (object->getPropertyByName("MotionType")) {
            // The motor replaces its I marker with a time-dependent frame.
            // Measurement must use separate, body-fixed markers; the original
            // ASMT marker's native frame is no longer updated after replacement.
            const auto duplicate = [&](const std::string& name, const std::string& suffix) {
                auto original = assembly->markerAt(name);
                auto copy = MbD::ASMTMarker::With();
                copy->setName(std::string("EventMotor_") + object->getNameInDocument() + suffix);
                copy->position3D = original->position3D;
                copy->rotationMatrix = original->rotationMatrix;
                original->partOrAssembly()->addMarker(copy);
                return copy->fullName("");
            };
            target->measureI = duplicate(target->source->markerI, "_I");
            target->measureJ = duplicate(target->source->markerJ, "_J");
        }
        targets[object] = target;
    }
    engine->prepare = [targets]() {
        for (const auto& [object, target] : targets) {
            target->motion = std::dynamic_pointer_cast<MbD::PrescribedMotion>(target->source->mbdObject
            );
            target->load = std::dynamic_pointer_cast<MbD::AppliedForceTorque>(target->source->mbdObject
            );
            if (!target->motion && !target->load) {
                throw std::invalid_argument("Unsupported native event target");
            }
            if (target->motion) {
                target->constraints = target->motion->constraints;
            }
            if (target->load
                && (choice(object, "LoadType") == "Force" || choice(object, "LoadType") == "Torque")) {
                std::string formula = prop<App::PropertyString>(object, "Formula").getValue();
                if (!formula.empty()) {
                    target->magnitude = target->parse(formula);
                }
            }
            target->enable(!flag(object, "Suppressed"));
        }
    };
    const double end = number(study, study->getPropertyByName("bTimeEnd") ? "bTimeEnd" : "EndTime");
    Py::Object json(PyImport_ImportModule("json"), true);
    for (auto* object : objects) {
        MbD::DynamicEvents::Event event;
        event.name = object->getNameInDocument();
        const auto trigger = choice(object, "Trigger");
        event.trigger = trigger == "Time" ? MbD::DynamicEvents::Event::Time
            : trigger == "Measurement"    ? MbD::DynamicEvents::Event::Threshold
                                          : MbD::DynamicEvents::Event::After;
        event.time = number(object, "Time");
        event.delay = number(object, "Delay");
        event.threshold = number(object, "Threshold");
        event.hysteresis = number(object, "Hysteresis");
        event.rising = flag(object, "Rising");
        event.repeat = flag(object, "Repeat");
        event.fireInitially = flag(object, "FireInitially");
        auto* previous = prop<App::PropertyLink>(object, "PreviousEvent").getValue();
        event.predecessor
            = std::distance(objects.begin(), std::find(objects.begin(), objects.end(), previous));
        if (event.trigger == MbD::DynamicEvents::Event::Threshold) {
            auto point = prop<App::PropertyVector>(object, "Point").getValue();
            auto a = marker(
                prop<App::PropertyLink>(object, "Component").getValue(),
                Base::Placement(point, Base::Rotation())
            );
            auto b = marker(
                prop<App::PropertyLink>(object, "ReferenceComponent").getValue(),
                Base::Placement()
            );
            const auto quantity = choice(object, "Quantity");
            event.measure = [assembly, a, b, quantity]() {
                const auto i = state(assembly, a), j = state(assembly, b);
                auto delta = vec(i.position) - vec(j.position);
                if (quantity == "Distance") {
                    return delta.Length();
                }
                if (quantity == "Speed") {
                    return (vec(i.velocity) - vec(j.velocity) - vec(j.omega).Cross(delta)).Length();
                }
                auto p = local(j, delta);
                return quantity == "Position X" ? p.x : quantity == "Position Y" ? p.y : p.z;
            };
        }
        Py::Tuple args(1);
        args[0] = Py::String(prop<App::PropertyString>(object, "Actions").getValue());
        Py::List actions(Py::Callable(json.getAttr("loads")).apply(args));
        std::vector<std::pair<std::shared_ptr<Target>, Py::Dict>> batch;
        const auto& links = prop<App::PropertyLinkList>(object, "Targets").getValues();
        for (size_t i = 0; i < links.size(); ++i) {
            batch.emplace_back(targets.at(links[i]), Py::Dict(actions[i]));
        }
        event.action = [batch, end](double time) {
            for (const auto& [target, action] : batch) {
                target->apply(action, time, end);
            }
        };
        engine->events.push_back(std::move(event));
    }
    assembly->dynamicEvents = engine;
}
}  // namespace Assembly
