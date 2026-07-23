# SPDX-License-Identifier: LGPL-2.1-or-later

"""Joints between stringers, newel posts, treads, risers and pickets.

The generated parts first overlap or merely touch. This module turns those
contacts into manufactured joints: stringers are trimmed at posts and tenoned
into them, abutting stringers are tenoned into each other, and every tread,
riser and picket end is housed into the board or post that carries it. The
resulting solids can be drawn on their own with all their cuts.
"""

import FreeCAD
import Part

# Proportions of a stub tenon relative to the member it is cut from.
TENON_THICKNESS_RATIO = 1.0 / 3.0
TENON_MINIMUM_THICKNESS = 10.0
TENON_SHOULDER_RATIO = 0.15
TENON_MINIMUM_SHOULDER = 15.0
TENON_MAXIMUM_DEPTH = 60.0
TENON_DEPTH_RATIO = 2.0 / 3.0
_TOLERANCE = 1e-4
# Pieces smaller than both limits are offcuts, not parts of a member.
DEBRIS_VOLUME = 50000.0
DEBRIS_RATIO = 0.01


def _solid_count(shape):
    return len(shape.Solids)


def _clean(shape):
    try:
        cleaned = shape.removeSplitter()
    except (Part.OCCError, ValueError):
        return shape
    return cleaned if cleaned.isValid() else shape


def _overlaps(first, second):
    if not first.BoundBox.intersect(second.BoundBox):
        return False
    try:
        return first.common(second).Volume > _TOLERANCE
    except (Part.OCCError, ValueError):
        return False


def _touches(first, second):
    bounds = FreeCAD.BoundBox(first.BoundBox)
    bounds.enlarge(0.01)
    if not bounds.intersect(second.BoundBox):
        return False
    return first.distToShape(second)[0] < 1e-3


def _depth_through(shape, origin, direction):
    """Return the material depth of ``shape`` along ``direction``."""

    probe = Part.makeLine(origin, origin + direction * 100000.0)
    try:
        inside = shape.common(probe)
    except (Part.OCCError, ValueError):
        return 0.0
    edges = sorted(
        inside.Edges,
        key=lambda edge: (edge.CenterOfMass - origin).Length,
    )
    return edges[0].Length if edges else 0.0


def _contact_faces(member, other):
    """Return ``(face, outward normal)`` of member faces lying on ``other``.

    Only vertical planar faces are considered: stringers are always cut
    plumb where they meet a post or another board.
    """

    contacts = []
    for face in member.Faces:
        if face.Surface.TypeId != "Part::GeomPlane":
            continue
        bounds = FreeCAD.BoundBox(face.BoundBox)
        bounds.enlarge(0.01)
        if not bounds.intersect(other.BoundBox):
            continue
        center = face.CenterOfMass
        u, v = face.Surface.parameter(center)
        normal = face.normalAt(u, v)
        if abs(normal.z) > 1e-6:
            continue
        if not face.isInside(center, 1e-6, True):
            continue
        if other.distToShape(Part.Vertex(center))[0] > 1e-4:
            continue
        if not other.isInside(center + normal * 0.5, 1e-6, False):
            continue
        contacts.append((face, normal))
    return contacts


def _tenon_from_face(face, normal, depth):
    """Extrude a centred stub tenon from a plumb end face."""

    across = FreeCAD.Vector(-normal.y, normal.x, 0.0)
    center = face.CenterOfMass
    offsets = [(vertex.Point - center).dot(across) for vertex in face.Vertexes]
    width = max(offsets) - min(offsets)
    middle = (max(offsets) + min(offsets)) / 2.0
    bottom = face.BoundBox.ZMin
    top = face.BoundBox.ZMax
    height = top - bottom
    thickness = max(width * TENON_THICKNESS_RATIO, TENON_MINIMUM_THICKNESS)
    shoulder = max(height * TENON_SHOULDER_RATIO, TENON_MINIMUM_SHOULDER)
    if thickness >= width - 1e-6 or height - 2.0 * shoulder < TENON_MINIMUM_THICKNESS:
        return None

    def point(offset, elevation):
        base = center + across * (middle + offset)
        return FreeCAD.Vector(base.x, base.y, elevation)

    half = thickness / 2.0
    rectangle = Part.Face(
        Part.makePolygon(
            [
                point(-half, bottom + shoulder),
                point(half, bottom + shoulder),
                point(half, top - shoulder),
                point(-half, top - shoulder),
                point(-half, bottom + shoulder),
            ]
        )
    )
    try:
        footprint = rectangle.common(face)
    except (Part.OCCError, ValueError):
        return None
    if not footprint.Faces or footprint.Area < rectangle.Area * 0.5:
        return None
    return footprint.Faces[0].extrude(normal * depth)


def _tenon_into(member, other):
    """Return a tenon from ``member`` into ``other``, or ``None``."""

    tenons = []
    for face, normal in _contact_faces(member, other):
        depth = _depth_through(other, face.CenterOfMass, normal)
        depth = min(TENON_MAXIMUM_DEPTH, depth * TENON_DEPTH_RATIO)
        if depth < 5.0:
            continue
        tenon = _tenon_from_face(face, normal, depth)
        if tenon is None:
            continue
        try:
            tenon = tenon.common(other)
        except (Part.OCCError, ValueError):
            continue
        if tenon.Volume > _TOLERANCE:
            tenons.append(tenon)
    if not tenons:
        return None
    return tenons[0] if len(tenons) == 1 else tenons[0].multiFuse(tenons[1:])


def _join(member, tenon):
    try:
        joined = _clean(member.fuse(tenon))
    except (Part.OCCError, ValueError):
        return member
    if joined.isValid() and _solid_count(joined) == _solid_count(member):
        return joined
    return member


def _cut(shape, tools, keep_pieces=True):
    """Cut ``tools`` from ``shape``.

    With ``keep_pieces`` false the cut may not split the member: only its
    largest original number of solids is kept. A housing cut separating a
    piece means a step runs right through the board, and that piece would
    stand proud of the step.
    """

    tools = [tool for tool in tools if shape.BoundBox.intersect(tool.BoundBox)]
    if not tools:
        return shape
    try:
        result = _clean(shape.cut(tools))
    except (Part.OCCError, ValueError):
        return shape
    if result.isNull() or not result.isValid() or not result.Solids:
        return shape
    expected = len(shape.Solids)
    if not keep_pieces and len(result.Solids) > expected:
        kept = sorted(result.Solids, key=lambda solid: solid.Volume, reverse=True)
        kept = kept[:expected]
        return kept[0] if len(kept) == 1 else Part.makeCompound(kept)
    return _without_debris(result, expected)


def _without_debris(shape, expected):
    """Drop slivers left between neighbouring cuts, e.g. beside a post."""

    solids = shape.Solids
    if len(solids) <= expected:
        return shape
    largest = max(solid.Volume for solid in solids)
    kept = [
        solid
        for solid in solids
        if solid.Volume > DEBRIS_VOLUME and solid.Volume > largest * DEBRIS_RATIO
    ]
    if not kept or len(kept) == len(solids):
        return shape
    return kept[0] if len(kept) == 1 else Part.makeCompound(kept)


def make_stair_joinery(stringers, posts, housed):
    """Return joined ``(stringers, posts)`` shapes.

    ``stringers`` and ``posts`` are lists of solids in one coordinate system;
    ``housed`` are the treads, risers and pickets whose ends must be let into
    those members. Stringers are processed in order, so an earlier board
    is tenoned into a later one where both are cut square.
    """

    stringers = list(stringers)
    posts = list(posts)

    # A post at a board end carries it: trim the board to the post face and
    # tenon it in. A post standing part way along a board is notched over it.
    post_joints = []
    for index, stringer in enumerate(stringers):
        for post_index, post in enumerate(posts):
            if not _overlaps(stringer, post):
                continue
            trimmed = _cut(stringer, [post])
            if _solid_count(trimmed) == _solid_count(stringer):
                stringers[index] = stringer = trimmed
                post_joints.append((index, post_index))
            else:
                posts[post_index] = _cut(post, [stringer])
    for index, post_index in post_joints:
        tenon = _tenon_into(stringers[index], posts[post_index])
        if tenon is not None:
            stringers[index] = _join(stringers[index], tenon)
            posts[post_index] = _cut(posts[post_index], [tenon])

    # Boards meeting each other at a seam, without a post between them.
    for index, stringer in enumerate(stringers):
        for other_index in range(index + 1, len(stringers)):
            other = stringers[other_index]
            if _overlaps(stringer, other):
                # Crossing boards: the later one butts against the earlier.
                trimmed = _cut(other, [stringer])
                if _solid_count(trimmed) == _solid_count(other):
                    stringers[other_index] = other = trimmed
            if not _touches(stringer, other):
                continue
            source, target = index, other_index
            tenon = _tenon_into(stringer, other)
            if tenon is None:
                source, target = other_index, index
                tenon = _tenon_into(other, stringer)
            if tenon is None:
                continue
            stringers[source] = _join(stringers[source], tenon)
            stringers[target] = _cut(stringers[target], [tenon])
            stringer = stringers[index]

    stringers = [_cut(stringer, housed, keep_pieces=False) for stringer in stringers]
    posts = [_cut(post, housed, keep_pieces=False) for post in posts]
    return stringers, posts
