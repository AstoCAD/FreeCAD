# SPDX-License-Identifier: LGPL-2.1-or-later
# /**************************************************************************
#                                                                           *
#    Copyright (c) 2026 AstoCAD     <hello@astocad.com>                     *
#                                                                           *
#    This file is part of FreeCAD.                                          *
#                                                                           *
#    FreeCAD is free software: you can redistribute it and/or modify it     *
#    under the terms of the GNU Lesser General Public License as            *
#    published by the Free Software Foundation, either version 2.1 of the   *
#    License, or (at your option) any later version.                        *
#                                                                           *
#    FreeCAD is distributed in the hope that it will be useful, but         *
#    WITHOUT ANY WARRANTY; without even the implied warranty of             *
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
#    Lesser General Public License for more details.                        *
#                                                                           *
#    You should have received a copy of the GNU Lesser General Public       *
#    License along with FreeCAD. If not, see                                *
#    <https://www.gnu.org/licenses/>.                                       *
#                                                                           *
# **************************************************************************/

"""Simulation-local event definitions and run-local profile compilation.

Document links carry references; JSON carries only action parameters. Nothing
in the runtime helpers writes to a target object (including global inputs).
"""
import json
import math

import FreeCAD as App
import Dynamics
import MotionProfile


class Event:
    TRIGGERS = ("Time", "Measurement", "After event")
    QUANTITIES = ("Position X", "Position Y", "Position Z", "Distance", "Speed")
    ACTIONS = ("Activate", "Deactivate", "Start profile", "Ramp")

    def __init__(self, obj):
        obj.Proxy = self
        self.properties(obj)

    def properties(self, obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        fields = (
            ("Bool", "IsSimulationEvent", True, "Identifies a simulation event"),
            ("Enumeration", "Trigger", list(self.TRIGGERS), "Condition that triggers the actions"),
            ("Time", "Time", 0.5, "Absolute simulation time"),
            ("Link", "PreviousEvent", None, "Event whose firing starts the delay"),
            ("Time", "Delay", 0.0, "Delay after the preceding event"),
            ("Link", "Component", None, "Component occurrence to measure"),
            ("Vector", "Point", App.Vector(), "Measurement point in component coordinates (mm)"),
            ("Link", "ReferenceComponent", None, "Reference component; empty means assembly frame"),
            ("Enumeration", "Quantity", list(self.QUANTITIES), "Position/distance in mm; speed in mm/s, relative to the reference component"),
            ("Float", "Threshold", 0.0, "Threshold in the selected quantity's units"),
            ("Bool", "Rising", True, "Trigger on rising rather than falling crossings"),
            ("Float", "Hysteresis", 0.0, "Repeat requires returning past the threshold by this amount"),
            ("Bool", "Repeat", False, "Rearm after firing; time events always fire once"),
            ("Bool", "FireInitially", False, "Fire a measurement event if already satisfied at the start"),
            ("LinkList", "Targets", [], "Motion/load targets, in action order"),
            ("String", "Actions", "[]", "Versioned action parameters in target order"),
        )
        for kind, name, default, description in fields:
            Dynamics._property(obj, kind, name, "Event", description, default)
        for name in ("IsSimulationEvent", "Actions", "Targets"):
            obj.setEditorMode(name, 2)

    def onDocumentRestored(self, obj):
        self.properties(obj)
        Dynamics.purge_touched(obj)

    def onChanged(self, obj, prop):
        if prop not in ("Label", "Visibility") and hasattr(obj, "Actions") and not getattr(self, "_validating_edit", False):
            Dynamics.invalidate_results(obj)
        Dynamics.purge_touched(obj)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        pass


def create(study):
    if not Dynamics.is_study(study):
        raise ValueError("Events must belong to a simulation.")
    obj = study.Document.addObject("App::FeaturePython", "Event")
    Event(obj)
    study.addObject(obj)
    Dynamics.purge_touched(obj, study)
    return obj


def events(study):
    return [obj for obj in study.Group if getattr(obj, "IsSimulationEvent", False)]


def describe(study):
    active = [obj for obj in events(study) if not obj.Suppressed]
    inputs = Dynamics.inputs_for_study(study)
    components = study.Assembly.getComponents()
    result = []
    for obj in active:
        def fail(message):
            raise ValueError(f"{obj.Label}: {message}")

        for value in (float(obj.Time), float(obj.Delay), obj.Threshold, obj.Hysteresis):
            if not math.isfinite(value):
                fail("Event parameters must be finite.")
        if obj.Delay < 0 or obj.Hysteresis < 0:
            fail("Delay and hysteresis must be nonnegative.")
        if obj.Trigger == "After event" and obj.PreviousEvent not in active:
            fail("Select an unsuppressed preceding event in this simulation.")
        if obj.Trigger == "Measurement":
            if obj.Component not in components or (obj.ReferenceComponent and obj.ReferenceComponent not in components):
                fail("Select component occurrences in this assembly.")
            if obj.Component == obj.ReferenceComponent:
                fail("Measured and reference components must differ.")
            if not all(math.isfinite(v) for v in obj.Point):
                fail("The measurement point must be finite.")
        actions = json.loads(obj.Actions)
        if not isinstance(actions, list) or not actions or len(actions) != len(obj.Targets):
            fail("Add at least one action with a target.")
        if len(set(obj.Targets)) != len(obj.Targets):
            fail("A target may occur only once within an event.")
        for target, action in zip(obj.Targets, actions):
            if target not in inputs or not (hasattr(target, "MotionType") or hasattr(target, "LoadType")):
                fail("Actions must target motions/loads available to this simulation.")
            if hasattr(target, "MotionType"):
                joint = target.Joint[0] if target.Joint else None
                if joint is None or joint.JointType not in ("Revolute", "Slider"):
                    fail("Event actions require a motion on a revolute or slider joint.")
            if not isinstance(action, dict):
                fail("Invalid action definition.")
            if action.get("kind") not in Event.ACTIONS:
                fail("Unknown event action.")
            if action["kind"] in ("Start profile", "Ramp"):
                if hasattr(target, "LoadType") and target.LoadType not in ("Force", "Torque"):
                    fail("Profile actions require a motion, force, or torque.")
            if action["kind"] == "Start profile":
                if not getattr(target, "ProfileData", ""):
                    fail("Define the target profile in the profile editor first.")
                spec = json.loads(target.ProfileData)
                MotionProfile.validate_for_object(target, spec)
                MotionProfile.Profile(spec)
            if action["kind"] == "Ramp":
                if not math.isfinite(action.get("value", math.nan)) or not math.isfinite(action.get("duration", math.nan)) or action["duration"] <= 0:
                    fail("Ramp value must be finite and duration positive.")
        result.append(dict(name=obj.Name, trigger=Event.TRIGGERS.index(obj.Trigger),
                           time=float(obj.Time), delay=float(obj.Delay),
                           predecessor=active.index(obj.PreviousEvent) if obj.PreviousEvent in active else 0,
                           threshold=obj.Threshold, hysteresis=obj.Hysteresis, rising=obj.Rising,
                           repeat=obj.Repeat, initially=obj.FireInitially))
    # Reject dependency cycles even if positive delays might otherwise hide them.
    for obj in active:
        seen = set()
        while obj and obj.Trigger == "After event":
            if obj in seen:
                raise ValueError("Event dependencies must not contain a cycle.")
            seen.add(obj)
            obj = obj.PreviousEvent
    return result


def action_formula(target, action, time, position, velocity, magnitude, end):
    """Return a solver formula in mm/rad/N/Nmm, without editing the target."""
    action = json.loads(action) if isinstance(action, str) else action
    motion = hasattr(target, "MotionType")
    unit = ("rad" if target.MotionType == "Angular" else "mm") if motion else ("N" if target.LoadType == "Force" else "N mm")
    if action["kind"] == "Ramp":
        spec = MotionProfile.defaults(unit)
        spec.update(quantity="Velocity" if motion else "Magnitude", start=time,
                    end=time+action["duration"], initial=velocity if motion else magnitude,
                    initial_position=position, segments=[[action["duration"], action["value"], "Smooth"]])
        return MotionProfile.Profile(spec).formula()
    spec = json.loads(target.ProfileData)
    original = MotionProfile.Profile(spec)
    profile = MotionProfile.Profile(spec, original.start, original.start + max(end-time, original.end-original.start))
    shift = MotionProfile.op("+", "time", original.start-time)
    offset = position-profile.sample(profile.start) if motion else 0
    funcs = [MotionProfile.text(MotionProfile.op("+", MotionProfile.substitute(expr, shift), offset)) for _, _, expr in profile.expressions]
    times = [t-original.start+time for t in profile.transitions]
    return "piecewise(time,functions(" + ",".join(funcs) + "),transitions(" + ",".join(format(t, ".17g") for t in times) + "))"
