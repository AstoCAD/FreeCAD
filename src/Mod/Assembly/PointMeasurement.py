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

"""Rigid-point post-processing of saved Assembly motion (mm, s, rad).

References are rooted at the selected component occurrence, never its linked
source. No solver state is required, including after reopening a document.
"""

import FreeCAD as App
import Dynamics
import UtilsAssembly


def resolve_reference(assembly, root, subname):
    components = list(assembly.getComponents())
    if root in components:
        return root, subname
    component, relative = UtilsAssembly.getComponentReference(assembly, root, subname)
    if component in components:
        return component, relative
    # A directly selected datum inside a component has an unambiguous physical
    # parent. Do not search linked sources: that would silently change occurrence.
    for component in components:
        if component.isDerivedFrom("App::Link"):
            continue
        parent, path = root, subname
        while parent and parent != assembly:
            if parent == component:
                return component, path
            path = parent.Name + "." + path
            parent = parent.getParentGeoFeatureGroup()
    raise ValueError("Select a reference belonging to an assembly component.")


def local_frame(reference, point=False):
    """Resolve a reference in the occurrence's local coordinates.

    Removing the occurrence placement from the accumulated matrix preserves
    nested placements and link scale, unlike looking up the linked source.
    """
    if not reference:
        raise ValueError("Select a reference first.")
    component, names = reference
    if component is None:
        raise ValueError("The selected component no longer exists.")
    subname = names[0] if names else ""
    obj, matrix, shape = component.getSubObject(subname, retType=2)
    if obj is None:
        raise ValueError("The selected reference no longer exists.")
    inverse = component.Placement.inverse()
    if point and shape is not None and getattr(shape, "ShapeType", "") == "Vertex":
        return App.Placement(inverse.multVec(shape.Point), App.Rotation())
    source = obj.getLinkedObject() if obj.isDerivedFrom("App::Link") else obj
    is_datum = any(source.isDerivedFrom(name) for name in (
        "PartDesign::Point", "PartDesign::CoordinateSystem", "App::Point", "App::LocalCoordinateSystem"
    ))
    if point and not is_datum:
        raise ValueError("Select a vertex, datum point, or coordinate system origin.")
    if not point and subname and not (
        source.isDerivedFrom("PartDesign::CoordinateSystem")
        or source.isDerivedFrom("App::LocalCoordinateSystem")
    ):
        raise ValueError("Select a component or a coordinate system for the reference frame.")
    return inverse * App.Placement(matrix)


def placement(pose):
    return App.Placement(App.Vector(*pose[:3]), App.Rotation(*pose[3:]))


def point_state(body, index, local):
    pose = placement(body["Placements"][index])
    offset = pose.Rotation.multVec(local)
    omega = App.Vector(*body["AngularVelocity"][index])
    alpha = App.Vector(*body["AngularAcceleration"][index])
    velocity = App.Vector(*body["Velocity"][index]) + omega.cross(offset)
    acceleration = (App.Vector(*body["Acceleration"][index])
                    + alpha.cross(offset) + omega.cross(omega.cross(offset)))
    return pose.Base + offset, velocity, acceleration, omega, alpha


def evaluate(data, component, local, reference=None, frame=None):
    """Return position and time derivatives in a potentially rotating frame.

    Includes angular acceleration, centripetal and Coriolis terms. Linear
    derivatives in the saved schema refer to the component origin, not its COM.
    """
    frame = frame if frame is not None else App.Placement()
    body = data["Bodies"].get(component)
    other = data["Bodies"].get(reference) if reference else None
    if body is None or (reference and other is None):
        raise ValueError("The selected component has no recorded motion. Generate the simulation first.")
    result = {key: [] for key in ("Position", "Velocity", "Acceleration", "Frames")}
    result["Times"] = data["Times"]
    for i in range(len(data["Times"])):
        p, v, a, _, _ = point_state(body, i, local)
        if other is not None:
            origin, vr, ar, omega, alpha = point_state(other, i, frame.Base)
            axes = placement(other["Placements"][i]).Rotation * frame.Rotation
        else:
            origin, vr, ar, omega, alpha = (App.Vector() for _ in range(5))
            axes = App.Rotation()
        delta = p - origin
        relative_v = v - vr - omega.cross(delta)
        relative_a = (a - ar - alpha.cross(delta)
                      - omega.cross(omega.cross(delta)) - 2 * omega.cross(relative_v))
        inverse = axes.inverted()
        for key, vector in (("Position", delta), ("Velocity", relative_v), ("Acceleration", relative_a)):
            result[key].append(inverse.multVec(vector))
        result["Frames"].append(App.Placement(origin, axes))
    return result


def measure(obj, data=None):
    study = next((parent for parent in obj.InList if Dynamics.is_study(parent)), None)
    if study is None:
        raise ValueError("The measurement must belong to a simulation.")
    data = Dynamics.results(study) if data is None else data
    local = local_frame(obj.Point, point=True).Base
    reference = obj.Reference[0] if obj.Reference else None
    frame = local_frame(obj.Reference) if reference else None
    return evaluate(data, obj.Point[0].Name, local, reference.Name if reference else None, frame)


class Measurement:
    def __init__(self, obj):
        obj.addProperty("App::PropertyBool", "IsPointMeasurement", "Measurement")
        obj.IsPointMeasurement = True
        obj.setEditorMode("IsPointMeasurement", 2)
        obj.addProperty("App::PropertyLinkSub", "Point", "Measurement", "Point on the selected component occurrence")
        obj.addProperty("App::PropertyLinkSub", "Reference", "Measurement", "Reference component or coordinate system; empty means assembly")
        obj.addProperty("App::PropertyEnumeration", "Quantity", "Measurement")
        obj.Quantity = ["Position", "Velocity", "Acceleration"]
        obj.addProperty("App::PropertyEnumeration", "Axis", "Measurement")
        obj.Axis = ["X", "Y", "Z", "Magnitude"]
        obj.Proxy = self

    def execute(self, obj):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        pass


def create(study):
    obj = study.Document.addObject("App::FeaturePython", "PointMeasurement")
    Measurement(obj)
    study.addObject(obj)
    Dynamics.purge_touched(obj, study)
    return obj
