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

"""Headless Assembly dynamics document model. No commands or GUI dependencies.

Materials belong to the part's existing ShapeMaterial property. Study objects
contain only simulation inputs; no second material/density database is created.
"""

import json
import math
import FreeCAD as App
import UtilsAssembly
import MotionProfile


def _component_placement(component):
    """Return the occurrence placement relative to its containing Assembly."""
    parent = component.getParentGeoFeatureGroup()
    while parent and not parent.isDerivedFrom("Assembly::AssemblyObject"):
        parent = parent.getParentGeoFeatureGroup()
    world = UtilsAssembly.getGlobalPlacement((component, [""]))
    if parent:
        return UtilsAssembly.getGlobalPlacement((parent, [""])).inverse() * world
    return world


component_placement = _component_placement


def attachment_placement(load, endpoint):
    """Return endpoint I or J in assembly coordinates."""
    if endpoint not in ("I", "J"):
        raise ValueError("Endpoint must be I or J")
    body = getattr(load, "Body" + endpoint)
    local = getattr(load, "Attachment" + endpoint)
    return (_component_placement(body) * local) if body else local


def load_visual_direction(load):
    """Assembly-space arrow direction, including follower rotation in playback."""
    direction = App.Vector(load.Direction)
    if load.Follower and load.LoadType in ("Force", "Torque"):
        local = load.Placement.Rotation.inverted().multVec(direction)
        direction = attachment_placement(load, "I").Rotation.multVec(local)
    return direction


def constant_load_magnitude(load):
    """Return a constant wrench magnitude, or None for a time-varying profile.

    Invalid definitions also use the positive-axis visual convention; validation
    belongs to the editor/solver, not the view provider's document callbacks.
    """
    try:
        if load.ProfileData:
            spec = json.loads(load.ProfileData)
            if spec["mode"] == "Constant":
                return MotionProfile.Profile(spec).sample(0)
            return None
        if load.Formula.strip():
            magnitude = float(load.Formula)
        else:
            magnitude = getattr(load, load.LoadType).Value
        return magnitude if math.isfinite(magnitude) else None
    except (ValueError, TypeError, KeyError):
        return None


def spring_length(load):
    """Return the current distance between a spring-damper's endpoints."""
    return (
        attachment_placement(load, "J").Base
        - attachment_placement(load, "I").Base
    ).Length


def torsional_angle(load):
    """Return signed twist of attachment J relative to I about attachment I's Z axis."""
    relative = (
        attachment_placement(load, "I").Rotation.inverted()
        * attachment_placement(load, "J").Rotation
    )
    _x, _y, z, w = relative.Q
    angle = math.atan2(2 * z * w, w * w - z * z)
    # Choose the same initial winding as the solver: nearest the free angle.
    free = load.FreeAngle.getValueAs("rad")
    return free + math.remainder(angle - free, 2 * math.pi)


def align_torsional_reference(load):
    """Align attachment J with I so the current configuration has zero twist."""
    frame = attachment_placement(load, "I")
    load.AttachmentJ = (
        _component_placement(load.BodyJ).inverse() * frame if load.BodyJ else frame
    )


def align_bushing_reference(load):
    """Make the current I frame the bushing's coincident, stress-free J frame."""
    align_torsional_reference(load)


def _property(obj, kind, name, group, description, default, unit=None):
    if name in obj.PropertiesList:
        if unit:
            # PropertyQuantity does not serialize its dynamically assigned unit.
            # Reapply the schema's unit without replacing the saved numeric value.
            setattr(obj, name, App.Units.Unit(unit))
        return
    obj.addProperty("App::Property" + kind, name, group, description)
    if unit:
        setattr(obj, name, App.Units.Unit(unit))
    setattr(obj, name, default)


def purge_touched(*objects):
    """Clear recompute state from input-only dynamics objects.

    Studies, motions, and loads are consumed explicitly by the simulation
    commands; their execute() methods deliberately do no recompute work.
    Property changes remain undoable and still mark the document modified.
    """
    for obj in objects:
        if obj is not None and obj.Document is not None:
            obj.purgeTouched()


def is_study(obj):
    return isinstance(getattr(obj, "Proxy", None), Study)


def input_owner(obj):
    """Return the direct Study or SimulationGroup containing an input object."""
    for owner in obj.InList:
        if obj not in getattr(owner, "Group", []):
            continue
        if is_study(owner) or owner.TypeId == "Assembly::SimulationGroup":
            return owner
    return None


def assembly_for_owner(owner):
    if is_study(owner):
        return owner.Assembly
    if owner and owner.TypeId == "Assembly::SimulationGroup":
        return next(
            (
                parent for parent in owner.InList
                if owner in getattr(parent, "Group", [])
                and parent.isDerivedFrom("Assembly::AssemblyObject")
            ),
            None,
        )
    if owner and owner.isDerivedFrom("Assembly::AssemblyObject"):
        return owner
    return None


def normalize_input_owner(owner):
    """Map an Assembly to its global SimulationGroup; preserve a local Study."""
    if is_study(owner):
        return owner
    assembly = assembly_for_owner(owner)
    if assembly is None:
        raise TypeError("A dynamics input owner must be an Assembly or dynamics study")
    return UtilsAssembly.getSimulationGroup(assembly)


def inputs_for_study(study):
    """Return global inputs followed by inputs local to *study*."""
    group = UtilsAssembly.getSimulationGroup(study.Assembly)
    return [obj for obj in group.Group if not is_study(obj)] + list(study.Group)


def is_global_input(obj):
    owner = input_owner(obj)
    return owner is not None and owner.TypeId == "Assembly::SimulationGroup"


def invalidate_results(obj):
    """Invalidate the local study, or every study for a global input."""
    if getattr(obj.Proxy, "_initializing_editor", False):
        return
    owner = input_owner(obj)
    studies = []
    if is_study(owner):
        studies = [owner]
    elif owner and owner.TypeId == "Assembly::SimulationGroup":
        studies = [child for child in owner.Group if is_study(child)]
    for study in studies:
        invalidate_study(study)
    purge_touched(obj, owner)


def invalidate_study(study):
    """Clear a study snapshot without triggering a solve or changing its inputs."""
    if App.isRestoring() or not hasattr(study, "ResultData"):
        return
    study.ResultData = ""
    study.Status = "NotRun"
    study.LastError = ""
    purge_touched(study)


class Study:
    INPUT_PROPERTIES = {
        "Assembly", "Group", "StartTime", "EndTime", "OutputStep", "MinimumStep",
        "MaximumStep", "Tolerance", "GravityEnabled", "GravityMagnitude",
        "GravityDirection", "aTimeStart", "bTimeEnd", "cTimeStepOutput",
        "fGlobalErrorTolerance", "AnalysisType",
    }

    def __init__(self, obj):
        obj.Proxy = self
        obj.addExtension("App::GroupExtensionPython")
        self._properties(obj)

    @staticmethod
    def _properties(obj, legacy=False):
        _property(obj, "Integer", "SchemaVersion", "Dynamics", "Document schema version", 1)
        if "AnalysisType" not in obj.PropertiesList:
            _property(obj, "Enumeration", "AnalysisType", "Simulation", "Analysis mode", ["Automatic", "Kinematics", "Dynamics"])
            obj.AnalysisType = "Automatic" if legacy else "Dynamics"
        # A backlink must not create a dependency cycle or pull the assembly
        # into its own GeoFeatureGroup through automatic dependency grouping.
        _property(obj, "LinkHidden", "Assembly", "Dynamics", "Owning assembly", None)
        for name, default in (("StartTime", "0 s"), ("EndTime", "1 s"),
                              ("OutputStep", "0.02 s"), ("MinimumStep", "1e-9 s"),
                              ("MaximumStep", "0.005 s")):
            if legacy and name in ("StartTime", "EndTime", "OutputStep"):
                continue  # Existing Simulation uses aTimeStart/bTimeEnd/cTimeStepOutput.
            _property(obj, "Time", name, "Integration", name, default)
        if not legacy:
            _property(obj, "Float", "Tolerance", "Integration", "Integration/corrector tolerance", 1e-8)
        _property(obj, "Bool", "GravityEnabled", "Gravity", "Enable uniform gravity", not legacy)
        _property(obj, "Acceleration", "GravityMagnitude", "Gravity", "Gravity acceleration", "9.81 m/s^2")
        _property(obj, "Vector", "GravityDirection", "Gravity", "Assembly-coordinate gravity direction", App.Vector(0, 0, -1))
        _property(obj, "String", "Status", "Results", "NotRun, Running, Complete or Failed", "NotRun")
        _property(obj, "String", "LastError", "Results", "Last validation or solver error", "")
        _property(obj, "String", "ResultData", "Results", "Versioned JSON snapshot; rerun after input changes", "")
        obj.setEditorMode("ResultData", 2)
        for name in ("SchemaVersion", "Status", "LastError"):
            obj.setEditorMode(name, 1)

    def onDocumentRestored(self, obj):
        self._properties(obj)  # Never reset saved inputs or results.
        if obj.Status == "Running":
            obj.Status = "Failed"
            obj.LastError = "The previous run did not finish."
        purge_touched(obj)

    def execute(self, obj):
        # Recomputing geometry must not implicitly run an expensive simulation.
        pass

    def onChanged(self, obj, prop):
        if prop == "Group" and getattr(self, "_previous_inputs", None) == self._input_names(obj):
            return
        if prop in self.INPUT_PROPERTIES:
            invalidate_study(obj)

    @staticmethod
    def _input_names(obj):
        return tuple(child.Name for child in obj.Group if not getattr(child, "IsPointMeasurement", False))

    def onBeforeChange(self, obj, prop):
        if prop == "Group":
            self._previous_inputs = self._input_names(obj)

    def dumps(self):
        return None

    def loads(self, state):
        pass


class Load:
    def __init__(self, obj):
        obj.Proxy = self
        self._updating_attachment = False
        self._restoring = False
        self._properties(obj)

    @staticmethod
    def _properties(obj):
        MotionProfile.ensure_properties(obj)
        # A load is deliberately an App::Feature rather than a Part::Feature:
        # Assembly treats Part features below it as physical components.  The
        # attachment extension only requires a Placement property, so provide
        # that explicitly without making the load part of the mechanism.
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        _property(obj, "Placement", "Placement", "Attachment", "Load position and direction", App.Placement())
        load_types = ["Force", "Torque", "SpringDamper", "TorsionalSpringDamper", "Bushing"]
        previous_type = obj.LoadType if "LoadType" in obj.PropertiesList else "Force"
        _property(obj, "Enumeration", "LoadType", "Dynamics", "Load law", load_types)
        obj.LoadType = load_types
        obj.LoadType = previous_type if previous_type in load_types else "Force"
        _property(obj, "LinkGlobal", "BodyI", "Attachments", "Body receiving the load", None)
        _property(obj, "LinkGlobal", "BodyJ", "Attachments", "Reaction body; empty means assembly ground", None)
        for name in ("AttachmentI", "AttachmentJ"):
            _property(obj, "Placement", name, "Attachments", "Body-local attachment; assembly coordinates for ground", App.Placement())
        _property(obj, "Vector", "Direction", "Wrench", "Assembly-coordinate direction (not body-following)", App.Vector(0, 0, 1))
        _property(obj, "Force", "Force", "Wrench", "Force magnitude on I", "0 N")
        _property(obj, "Quantity", "Torque", "Wrench", "Torque magnitude on I", "0 N*mm", "N*mm")
        _property(obj, "String", "Formula", "Wrench", "Optional magnitude expression using time", "")
        _property(obj, "Bool", "Follower", "Wrench", "Rotate the load direction with the component instead of keeping it fixed in assembly coordinates", False)
        _property(obj, "Bool", "CoupledBushing", "Bushing", "Use full symmetric 6 by 6 stiffness and damping matrices", False)
        _property(obj, "FloatList", "BushingStiffnessMatrix", "Bushing", "Row-major matrix: efforts N, N mm; strains mm, radians", [0.0] * 36)
        _property(obj, "FloatList", "BushingDampingMatrix", "Bushing", "Row-major matrix: efforts N, N mm; strain rates mm/s, rad/s", [0.0] * 36)
        _property(obj, "Quantity", "Stiffness", "Spring", "Linear stiffness", "0 N/mm", "N/mm")
        _property(obj, "Quantity", "Damping", "Spring", "Axial viscous damping", "0 kg/s", "kg/s")
        _property(obj, "Length", "RestLength", "Spring", "Unstretched length", "0 mm")
        _property(obj, "Quantity", "TorsionalStiffness", "Torsional Spring", "Angular stiffness", "0 N*mm/rad", "N*mm/rad")
        _property(obj, "Quantity", "TorsionalDamping", "Torsional Spring", "Angular viscous damping", "0 N*mm*s/rad", "N*mm*s/rad")
        _property(obj, "Angle", "FreeAngle", "Torsional Spring", "Angle at which the spring applies no torque", "0 deg")
        for axis in "XYZ":
            _property(obj, "Quantity", "BushingLinearStiffness" + axis, "Bushing", "Translational stiffness along attachment I's local " + axis + " axis", "0 N/mm", "N/mm")
            _property(obj, "Quantity", "BushingLinearDamping" + axis, "Bushing", "Translational damping along attachment I's local " + axis + " axis", "0 kg/s", "kg/s")
            _property(obj, "Quantity", "BushingAngularStiffness" + axis, "Bushing", "Rotational stiffness about attachment I's local " + axis + " axis", "0 N*mm/rad", "N*mm/rad")
            _property(obj, "Quantity", "BushingAngularDamping" + axis, "Bushing", "Rotational damping about attachment I's local " + axis + " axis", "0 N*mm*s/rad", "N*mm*s/rad")
        if not obj.hasExtension("Part::AttachExtensionPython"):
            obj.addExtension("Part::AttachExtensionPython")

    def onDocumentRestored(self, obj):
        self._updating_attachment = False
        self._restoring = True
        try:
            self._properties(obj)
        finally:
            self._restoring = False
        purge_touched(obj)

    def onChanged(self, obj, prop):
        if App.isRestoring() or getattr(self, "_restoring", False):
            return
        if prop == "Formula" and getattr(self, "_updating_profile", False):
            return
        if prop == "Formula" and getattr(obj, "ProfileData", ""):
            obj.ProfileData = ""
        if prop == "ProfileData":
            invalidate_results(obj)
        if prop in ("Placement", "BodyI") and not self._updating_attachment:
            self.update_attachment(obj)
        elif (
            prop == "AttachmentI"
            and obj.LoadType == "Bushing"
            and not self._updating_attachment
        ):
            self._updating_attachment = True
            try:
                align_bushing_reference(obj)
            finally:
                self._updating_attachment = False
        if prop in {
            "Placement", "LoadType", "Suppressed", "BodyI", "BodyJ",
            "AttachmentI", "AttachmentJ", "Direction", "Force", "Torque",
            "Formula", "Stiffness", "Damping", "RestLength",
            "Follower", "CoupledBushing", "BushingStiffnessMatrix", "BushingDampingMatrix",
            "TorsionalStiffness", "TorsionalDamping", "FreeAngle",
            *("Bushing" + kind + axis for kind in (
                "LinearStiffness", "LinearDamping", "AngularStiffness", "AngularDamping"
            ) for axis in "XYZ"),
        }:
            invalidate_results(obj)

    def update_attachment(self, obj):
        if not hasattr(obj, "BodyI") or not obj.BodyI or not hasattr(obj, "Placement"):
            return
        self._updating_attachment = True
        try:
            # Study groups have no placement of their own, therefore this
            # App::Feature placement is expressed directly in assembly space.
            placement = obj.Placement
            component_placement = _component_placement(obj.BodyI)
            attachment = component_placement.inverse() * placement
            attachment_changed = not obj.AttachmentI.isSame(attachment, 1e-12)
            obj.AttachmentI = attachment
            obj.Direction = placement.Rotation.multVec(App.Vector(0, 0, 1))
            # Attachment task initialization may assign the same Placement.
            # Do not discard a configured second frame on a no-op update.
            if attachment_changed and obj.LoadType == "TorsionalSpringDamper":
                align_torsional_reference(obj)
            elif attachment_changed and obj.LoadType == "Bushing":
                align_bushing_reference(obj)
        finally:
            self._updating_attachment = False

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        pass


def invalidate_contact_results(contact):
    invalidate_results(contact)


class Contact:
    """Shape contact for one component pair or all pairs in an assembly."""

    MODES = ("Between two components", "General collision detection",
             "Between component sets", "Within a component set")

    def __init__(self, obj, component_i=None, component_j=None, mode=None):
        obj.Proxy = self
        self._properties(obj)
        obj.Mode = mode or self.MODES[0]
        obj.ComponentI = component_i
        obj.ComponentJ = component_j
        self._update_editor_modes(obj)

    @staticmethod
    def _properties(obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        _property(
            obj,
            "Enumeration",
            "ContactType",
            "Contact",
            "Contact geometry model",
            ["Shape"],
        )
        _property(
            obj,
            "Enumeration",
            "Mode",
            "Contact",
            "Whether contact is checked for one pair or every component pair",
            list(Contact.MODES),
        )
        _property(
            obj,
            "LinkGlobal",
            "ComponentI",
            "Contact",
            "First contacting assembly component",
            None,
        )
        mode = str(obj.Mode)
        obj.Mode = list(Contact.MODES)
        obj.Mode = mode
        for name in ("ComponentsI", "ComponentsJ"):
            _property(obj, "LinkListGlobal", name, "Contact", "Component occurrences in this contact set", [])
        _property(obj, "StringList", "ExcludedPairs", "Contact", "Properties containing excluded occurrence pairs", [])
        obj.setEditorMode("ExcludedPairs", 2)
        _property(
            obj,
            "LinkGlobal",
            "ComponentJ",
            "Contact",
            "Second contacting assembly component",
            None,
        )
        _property(
            obj,
            "Quantity",
            "Stiffness",
            "Impact",
            "Effective normal contact stiffness",
            "1 N/mm",
            "N/mm",
        )
        _property(
            obj,
            "Quantity",
            "Damping",
            "Impact",
            "Normal viscous contact damping",
            "0 kg/s",
            "kg/s",
        )
        _property(
            obj,
            "Bool",
            "FrictionEnabled",
            "Friction",
            "Enable tangential Coulomb friction",
            False,
        )
        _property(
            obj,
            "Float",
            "StaticFriction",
            "Friction",
            "Static coefficient of friction for the surface pair",
            0.5,
        )
        _property(
            obj,
            "Float",
            "DynamicFriction",
            "Friction",
            "Dynamic coefficient of friction for the surface pair",
            0.3,
        )
        _property(
            obj,
            "Quantity",
            "FrictionTransitionVelocity",
            "Friction",
            "Velocity scale used to regularize friction near zero sliding speed",
            "1 mm/s",
            "mm/s",
        )

    @staticmethod
    def _update_editor_modes(obj):
        if not {"Mode", "ComponentI", "ComponentJ"}.issubset(obj.PropertiesList):
            return
        pair = obj.Mode == Contact.MODES[0]
        obj.setEditorMode("ComponentI", 0 if pair else 2)
        obj.setEditorMode("ComponentJ", 0 if pair else 2)
        for name, visible in (("ComponentsI", obj.Mode in Contact.MODES[2:]),
                              ("ComponentsJ", obj.Mode == Contact.MODES[2])):
            if name in obj.PropertiesList:
                obj.setEditorMode(name, 0 if visible else 2)

    def onDocumentRestored(self, obj):
        self._properties(obj)
        self._update_editor_modes(obj)
        if any("|" in key for key in obj.ExcludedPairs):
            endpoints = {o.Name: o for o in getattr(obj, "ExclusionComponents", [])}
            pairs = [tuple(endpoints.get(n) for n in key.split("|")) for key in obj.ExcludedPairs]
            _store_contact_exclusions(obj, [p for p in pairs if len(p) == 2 and all(p)])
        if App.GuiUp and obj.ViewObject is not None and obj.ViewObject.Proxy is None:
            from CommandCreateContact import ViewProviderContact
            ViewProviderContact(obj.ViewObject)
        purge_touched(obj)

    def onChanged(self, obj, prop):
        if App.isRestoring():
            return
        if prop == "Mode":
            self._update_editor_modes(obj)
        if getattr(self, "_updating_exclusions", False):
            return
        if prop in getattr(obj, "ExcludedPairs", []):
            # LinkList removes deleted objects. Discard the entire incomplete
            # pair, never re-pair surviving endpoints by their list position.
            if len(getattr(obj, prop)) != 2:
                obj.ExcludedPairs = [key for key in obj.ExcludedPairs if key != prop]
            invalidate_contact_results(obj)
        if prop in {
            "Mode",
            "ComponentsI", "ComponentsJ", "ExclusionComponents", "ExcludedPairs",
            "Suppressed",
            "ComponentI",
            "ComponentJ",
            "Stiffness",
            "Damping",
            "FrictionEnabled",
            "StaticFriction",
            "DynamicFriction",
            "FrictionTransitionVelocity",
        }:
            invalidate_contact_results(obj)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        pass


def contact_exclusions(contact):
    result = []
    for key in contact.ExcludedPairs:
        if not key.startswith("ExcludedPair_") or key not in contact.PropertiesList:
            raise ValueError("Invalid contact exclusion.")
        pair = getattr(contact, key)
        if len(pair) == 2:
            result.append(tuple(pair))
    return result


def _store_contact_exclusions(contact, pairs):
    """One reference-aware property per pair survives copy, import and deletion."""
    contact.Proxy._updating_exclusions = True
    try:
        keys = []
        for index, pair in enumerate(pairs):
            key = f"ExcludedPair_{index}"
            _property(contact, "LinkListHidden", key, "Contact", "Excluded component pair", [])
            contact.setEditorMode(key, 2)
            setattr(contact, key, list(pair))
            keys.append(key)
        contact.ExcludedPairs = keys
        for name in list(contact.PropertiesList):
            if name.startswith("ExcludedPair_") and name not in keys:
                contact.removeProperty(name)
        if "ExclusionComponents" in contact.PropertiesList:
            contact.removeProperty("ExclusionComponents")
    finally:
        contact.Proxy._updating_exclusions = False
    invalidate_contact_results(contact)


def set_contact_exclusions(contact, pairs):
    """Store pairs with link-backed identity; labels are never identifiers."""
    members = assembly_for_owner(input_owner(contact)).getComponents()
    unique = []
    for a, b in pairs:
        if a not in members or b not in members or a == b:
            raise ValueError("Exclusions require two different component occurrences in this assembly.")
        if (a, b) not in unique and (b, a) not in unique:
            unique.append((a, b))
    _store_contact_exclusions(contact, unique)


def contact_pairs(contact):
    """Preview component pairs. Native dragging/dynamics use the same rules."""
    import itertools
    components = assembly_for_owner(input_owner(contact)).getComponents()
    mode = str(contact.Mode)
    if mode == Contact.MODES[0]:
        first, second = [contact.ComponentI], [contact.ComponentJ]
        if first == second:
            raise ValueError("Contact requires two different components.")
        candidates = itertools.product(first, second)
    elif mode == Contact.MODES[1]:
        first, second = list(components), []
        candidates = itertools.combinations(first, 2)
    elif mode in Contact.MODES[2:]:
        first = list(dict.fromkeys(contact.ComponentsI))
        second = list(dict.fromkeys(contact.ComponentsJ)) if mode == Contact.MODES[2] else []
        if len(first) < (2 if mode == Contact.MODES[3] else 1) or (mode == Contact.MODES[2] and not second):
            raise ValueError("Select at least two members within a set, or at least one in each set.")
        candidates = itertools.combinations(first, 2) if mode == Contact.MODES[3] else itertools.product(first, second)
    else:
        raise ValueError("Unknown contact mode.")
    if any(obj not in components for obj in first + second):
        raise ValueError("Contact members must belong to this assembly.")
    # Exclusions belong to multi-pair modes. Keep their settings when switching
    # modes, but do not let hidden exclusions disable the explicitly chosen pair.
    excluded = ({frozenset(pair) for pair in contact_exclusions(contact)}
                if mode != Contact.MODES[0] else set())
    seen, result = set(), []
    for a, b in candidates:
        key = frozenset((a, b))
        if a != b and key not in excluded and key not in seen:
            seen.add(key)
            result.append((a, b))
    return result


class InitialVelocity:
    """A simulation-owned initial velocity of a component's center of mass."""

    TYPES = ("Linear", "Angular")

    def __init__(self, obj, velocity_type="Linear", component=None):
        obj.Proxy = self
        self._restoring = False
        self._properties(obj)
        obj.InitialVelocityType = velocity_type
        obj.Component = component
        self._update_editor_modes(obj)

    @staticmethod
    def _properties(obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        _property(
            obj,
            "Enumeration",
            "InitialVelocityType",
            "Initial Condition",
            "Linear or angular initial velocity",
            list(InitialVelocity.TYPES),
        )
        _property(
            obj,
            "LinkGlobal",
            "Component",
            "Initial Condition",
            "Component receiving the initial velocity",
            None,
        )
        _property(
            obj,
            "Vector",
            "Direction",
            "Initial Condition",
            "Direction in assembly coordinates",
            App.Vector(1, 0, 0),
        )
        _property(
            obj,
            "Velocity",
            "LinearVelocity",
            "Initial Condition",
            "Signed velocity of the component center of mass",
            "0 mm/s",
        )
        _property(
            obj,
            "Quantity",
            "AngularVelocity",
            "Initial Condition",
            "Signed angular velocity using the right-hand rule",
            "0 rad/s",
            "rad/s",
        )

    @staticmethod
    def _update_editor_modes(obj):
        if not {"LinearVelocity", "AngularVelocity"}.issubset(obj.PropertiesList):
            return
        angular = obj.InitialVelocityType == "Angular"
        obj.setEditorMode("LinearVelocity", 2 if angular else 0)
        obj.setEditorMode("AngularVelocity", 0 if angular else 2)

    def onDocumentRestored(self, obj):
        self._restoring = True
        try:
            self._properties(obj)
            self._update_editor_modes(obj)
        finally:
            self._restoring = False
        purge_touched(obj)

    def onChanged(self, obj, prop):
        if App.isRestoring() or getattr(self, "_restoring", False):
            return
        if prop == "InitialVelocityType":
            self._update_editor_modes(obj)
        if prop in {
            "InitialVelocityType",
            "Suppressed",
            "Component",
            "Direction",
            "LinearVelocity",
            "AngularVelocity",
        }:
            invalidate_results(obj)


class Friction:
    """Simulation-only resistance on a revolute or slider joint."""

    MODELS = ("Specified resistance", "Reaction based", "Rolling resistance", "Thrust bearing")

    def __init__(self, obj, joint=None):
        obj.Proxy = self
        self._properties(obj)
        obj.Joint = joint

    @staticmethod
    def _properties(obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        _property(obj, "LinkGlobal", "Joint", "Friction", "Revolute or slider joint", None)
        _property(obj, "Enumeration", "FrictionModel", "Friction", "Friction law", list(Friction.MODELS))
        _property(obj, "Force", "StaticForce", "Specified resistance", "Breakaway force", "0 N")
        _property(obj, "Force", "DynamicForce", "Specified resistance", "Sliding force", "0 N")
        _property(obj, "Quantity", "StaticTorque", "Specified resistance", "Breakaway torque", "0 N*mm", "N*mm")
        _property(obj, "Quantity", "DynamicTorque", "Specified resistance", "Sliding torque", "0 N*mm", "N*mm")
        _property(obj, "Velocity", "LinearTransitionVelocity", "Regularization", "Velocity scale near zero speed", "1 mm/s")
        _property(obj, "Quantity", "AngularTransitionVelocity", "Regularization", "Angular velocity scale near zero speed", "1 rad/s", "rad/s")
        _property(obj, "Quantity", "LinearViscousDamping", "Regularization", "Additional linear viscous damping", "0 kg/s", "kg/s")
        _property(obj, "Quantity", "AngularViscousDamping", "Regularization", "Additional angular viscous damping", "0 N*mm*s/rad", "N*mm*s/rad")
        _property(obj, "Float", "StaticCoefficient", "Reaction based", "Static friction coefficient", 0.2)
        _property(obj, "Float", "DynamicCoefficient", "Reaction based", "Dynamic friction coefficient", 0.15)
        _property(obj, "Length", "EffectiveRadius", "Reaction based", "Effective bearing radius for revolute friction", "1 mm")

    def onDocumentRestored(self, obj):
        self._properties(obj)
        purge_touched(obj)

    def onChanged(self, obj, prop):
        if not App.isRestoring() and prop in obj.PropertiesList:
            invalidate_results(obj)

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        pass

def create_study(assembly, name="DynamicsStudy"):
    """Create persistent solver inputs without opening an editor or adding UI."""
    if not assembly.isDerivedFrom("Assembly::AssemblyObject"):
        raise TypeError("Expected an Assembly object")
    obj = assembly.Document.addObject("App::FeaturePython", name)
    Study(obj)
    obj.Assembly = assembly
    UtilsAssembly.getSimulationGroup(assembly).addObject(obj)
    purge_touched(obj)
    return obj


def create_load(study, kind, body, name=None, body_j=None):
    if kind not in ("Force", "Torque", "SpringDamper", "TorsionalSpringDamper", "Bushing"):
        raise ValueError("Unknown dynamics load type")
    owner = normalize_input_owner(study)
    obj = owner.Document.addObject("App::FeaturePython", name or kind)
    Load(obj)
    obj.LoadType = kind
    obj.BodyI = body
    obj.BodyJ = body_j
    owner.addObject(obj)
    if body:
        obj.Placement = _component_placement(body)
        obj.Proxy.update_attachment(obj)
    if body_j:
        obj.AttachmentJ = App.Placement()
    if kind == "TorsionalSpringDamper":
        align_torsional_reference(obj)
    elif kind == "Bushing":
        align_bushing_reference(obj)
    purge_touched(owner, obj)
    return obj


def create_contact(
    owner,
    component_i=None,
    component_j=None,
    name="Contact",
    mode="Between two components",
):
    """Create a global assembly contact or a simulation-local contact."""
    if not owner:
        raise ValueError("A contact requires an owner")
    if mode not in Contact.MODES:
        raise ValueError("Unknown contact mode")
    owner = normalize_input_owner(owner)
    assembly = assembly_for_owner(owner)
    components = assembly.getComponents()
    if mode == Contact.MODES[0]:
        if not component_i or not component_j:
            raise ValueError("Pair contact requires two components")
        if component_i is component_j:
            raise ValueError("Pair contact requires two different components")
        if component_i not in components or component_j not in components:
            raise ValueError("Contact components must belong to the owner assembly")
    obj = owner.Document.addObject("App::FeaturePython", name)
    Contact(obj, component_i, component_j, mode)
    owner.addObject(obj)
    if App.GuiUp:
        # The factory is also used by scripts: those contacts need the same
        # edit callback and icon as contacts created through the toolbar.
        from CommandCreateContact import ViewProviderContact
        ViewProviderContact(obj.ViewObject)
    invalidate_contact_results(obj)
    purge_touched(owner, obj)
    return obj


def create_initial_velocity(study, velocity_type, component, name=None):
    if velocity_type not in InitialVelocity.TYPES:
        raise ValueError("Unknown initial velocity type")
    owner = normalize_input_owner(study)
    obj = owner.Document.addObject(
        "App::FeaturePython", name or "Initial" + velocity_type + "Velocity"
    )
    InitialVelocity(obj, velocity_type, component)
    owner.addObject(obj)
    invalidate_results(obj)
    purge_touched(owner, obj)
    return obj


def create_friction(owner, joint, name="Friction"):
    owner = normalize_input_owner(owner)
    if not joint or getattr(joint, "JointType", None) not in ("Revolute", "Slider"):
        raise ValueError("Friction requires a revolute or slider joint")
    obj = owner.Document.addObject("App::FeaturePython", name)
    Friction(obj, joint)
    owner.addObject(obj)
    invalidate_results(obj)
    purge_touched(owner, obj)
    return obj


def analysis_type(study):
    """Resolve the selected mode without silently discarding physical inputs."""
    mode = str(getattr(study, "AnalysisType", "Dynamics"))
    physical = study.GravityEnabled or any(
        not getattr(child, "Suppressed", False)
        and any(hasattr(child, name) for name in (
            "LoadType", "InitialVelocityType", "ContactType", "FrictionModel", "IsSimulationEvent"
        ))
        for child in inputs_for_study(study)
    )
    if mode == "Automatic":
        return "Dynamics" if physical else "Kinematics"
    if mode == "Kinematics" and physical:
        raise ValueError(
            "Kinematics uses prescribed motion only. Disable gravity and suppress "
            "loads, initial velocities, contacts, friction and events, or select Dynamics."
        )
    if mode not in ("Kinematics", "Dynamics"):
        raise ValueError("Unknown simulation analysis mode")
    return mode


def run(study):
    """Run the selected analysis and save a snapshot without playing back the CAD pose.

    Result positions/velocities use mm and s; mass kg, inertia kg mm^2,
    forces N, torques N mm, angles radians. Samples start with the assembled
    initial condition, not the unsolved input. SolverFrames maps samples to the
    in-memory solver playback indices. ResultData is a historical snapshot.
    Recompute geometry before calling: this deliberately does not recompute the
    document, since Assembly recomputes can reposition components.
    """
    if not isinstance(study.Proxy, Study) or not study.Assembly:
        raise ValueError("A dynamics study needs an owning assembly")
    study.Status = "Running"
    study.LastError = ""
    study.ResultData = ""  # Do not mislabel a previous run as this run's result.
    try:
        with MotionProfile.prepared(study, inputs_for_study(study)):
            mode = analysis_type(study)
            if mode == "Dynamics":
                data = study.Assembly.generateDynamics(study)
            else:
                error = study.Assembly.generateSimulation(study)
                if error:
                    raise RuntimeError(f"Kinematic simulation failed with error code {error}.")
                data = study.Assembly.getSimulationResults()
        data["AnalysisType"] = mode
        return save_results(study, data)
    except Exception as error:
        study.Status = "Failed"
        study.LastError = str(error)
        purge_touched(study)
        raise


def save_results(study, data):
    """Persist a kinematic or dynamic result using the shared result schema."""
    data["Units"] = {"Length": "mm", "Time": "s", "Mass": "kg",
                     "Inertia": "kg mm^2", "Force": "N", "Torque": "N mm",
                     "Angle": "rad", "Energy": "mJ", "Power": "mW"}
    study.ResultData = json.dumps(data, allow_nan=False, separators=(",", ":"))
    study.Status = "Complete"
    study.LastError = ""
    purge_touched(study, *inputs_for_study(study))
    return data


def results(study):
    """Read a saved snapshot; this does not assert that current inputs match it."""
    if study.Status != "Complete" or not study.ResultData:
        raise ValueError("No completed dynamics results")
    data = json.loads(study.ResultData)
    if data.get("SchemaVersion") not in (1, 2):
        raise ValueError("Unsupported dynamics result schema")
    return data
