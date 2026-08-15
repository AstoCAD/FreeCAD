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

"""Placement helpers for Forms objects and linked reference geometry."""

import Part


def _container_path(obj):
    """Return the root and subname of *obj* through its own GeoFeature groups."""
    names = []
    root = obj
    parent = obj.getParentGeoFeatureGroup()
    while parent is not None:
        names.insert(0, root.Name)
        root = parent
        parent = root.getParentGeoFeatureGroup()
    return root, "".join(name + "." for name in names)


def global_placement(obj):
    """Return *obj*'s placement in its unique document-tree context.

    ``GeoFeature.getGlobalPlacement`` does not account for Links and is being
    removed from FreeCAD. ``getGlobalPlacementOf`` needs the selection root
    and path explicitly, which are available through ``Parents`` for the
    normal single-parent Forms workflows. When there are several paths, for
    example through a Link to the Part containing *obj*, the path through the
    containers *obj* itself belongs to is used.
    """
    parents = getattr(obj, "Parents", ())
    try:
        if len(parents) == 1 and len(parents[0]) == 2:
            root, subname = parents[0]
        else:
            root, subname = _container_path(obj)
        return obj.getGlobalPlacementOf(obj, root, str(subname))
    except (AttributeError, RuntimeError, TypeError):
        # Keep documents usable on FreeCAD versions predating the replacement
        # API. This fallback can be removed with FreeCAD's deprecated method.
        try:
            return obj.getGlobalPlacement()
        except (AttributeError, RuntimeError):
            return obj.Placement


def selected_shape(root, subname=""):
    """Return the geometry a selection path picks, in global coordinates.

    *root* and *subname* are what a selection reports: the top-level object and
    the dotted path below it, which may end with an element name, for example
    ``("Part", "Body.Pad.Face6")`` or ``("Body", "Origin.XY_Plane.")``. FreeCAD
    resolves the path through Bodies, Parts, Links, origin features and datums.

    Returns ``(shape, owner, element)``: the picked element, or the sub-object's
    whole shape when the path names no element (origin planes and axes are
    infinite faces and edges); the sub-object; and the element's indexed name,
    or "" when the path names none. A path that resolves to nothing gives a null
    shape.
    """
    subname = str(subname or "")
    shape, _matrix, owner = Part.getShape(
        root, subname, needSubElement=True, transform=True, retType=1
    )
    return shape, owner, Part.splitSubname(subname)[2]


__all__ = ["global_placement", "selected_shape"]
