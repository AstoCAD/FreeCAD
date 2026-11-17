# SPDX-License-Identifier: LGPL-2.1-or-later

"""Joints between stringers, newel posts, treads, risers and pickets.

The generated parts first overlap or merely touch. This module turns those
contacts into manufactured joints: stringers are trimmed at posts and tenoned
into them, abutting stringers are tenoned into each other, and every tread,
riser and picket end is housed into the board or post that carries it. A
step crossing a post is notched around it instead. The
resulting solids can be drawn on their own with all their cuts.
"""

import FreeCAD
import Part

# Proportions of a stub tenon relative to the member it is cut from: a
# third of its thickness, and never under the 12 mm BS 585-1 asks of a
# string's tenon.
TENON_THICKNESS_RATIO = 1.0 / 3.0
TENON_MINIMUM_THICKNESS = 12.0
TENON_SHOULDER_RATIO = 0.15
TENON_MINIMUM_SHOULDER = 15.0
TENON_MAXIMUM_DEPTH = 60.0
TENON_DEPTH_RATIO = 2.0 / 3.0
_TOLERANCE = 1e-4
# Pieces smaller than both limits are offcuts, not parts of a member.
DEBRIS_VOLUME = 50000.0
DEBRIS_RATIO = 0.01
# The end a butting board leaves beyond the board it meets is an offcut, up
# to this share of the board.
BUTT_OFFCUT_RATIO = 0.1
# Slope of the wedges locking the steps into open housings.
WEDGE_TAPER = 0.1


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


def _butted(shape, expected):
    """Drop the end a butting board leaves beyond the board it meets.

    A board running a little past the one it butts is cut at it, which can
    leave its last few centimetres standing free on the far side: an
    offcut. A board cut into larger pieces crosses the other one instead,
    and is returned as cut.
    """

    solids = sorted(shape.Solids, key=lambda solid: solid.Volume, reverse=True)
    if len(solids) <= expected:
        return shape
    kept, offcuts = solids[:expected], solids[expected:]
    if sum(solid.Volume for solid in offcuts) > BUTT_OFFCUT_RATIO * shape.Volume:
        return shape
    return kept[0] if len(kept) == 1 else Part.makeCompound(kept)


def make_stair_joinery(stringers, posts, housed, step_cutters=(), slots=None):
    """Return joined ``(stringers, posts, housed)`` shapes.

    ``slots`` opens the step housings of some boards at the back, see
    ``housing_slots``: a mapping with the ``boards`` indices to open, the
    ``treads`` and ``risers`` indices into ``housed``, and ``wedged``. It
    gets back the wedges each board takes, under ``wedges``, by index.

    ``stringers`` and ``posts`` are lists of solids in one coordinate system;
    ``housed`` are the treads, risers and pickets whose ends must be let into
    those members. Stringers are processed in order, so an earlier board
    is tenoned into a later one where both are cut square. A housed member
    passing right through a post is returned notched around it.
    ``step_cutters`` are the regions beside newels that step ends overhang;
    housed members are trimmed back out of them.
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
                trimmed = _butted(_cut(other, [stringer]), _solid_count(other))
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

    # Steps running through a post, e.g. a newel standing under the tread
    # ends of a notched stringer, are notched around the post: housing them
    # would cut the post in two. The steps taking most of the post go first,
    # until housing the others leaves it whole.
    housed = list(housed)
    # Step ends die into the newel instead of overhanging its outer face.
    for cutter in step_cutters:
        for index, member in enumerate(housed):
            if _overlaps(cutter, member):
                housed[index] = _cut(member, [cutter])
    for post in posts:
        crossing = [index for index, member in enumerate(housed) if _overlaps(post, member)]
        crossing.sort(key=lambda index: post.common(housed[index]).Volume, reverse=True)
        while crossing and _solid_count(
            _cut(post, [housed[index] for index in crossing])
        ) > _solid_count(post):
            index = crossing.pop(0)
            housed[index] = _cut(housed[index], [post])

    slots = slots or {}
    stringers = [
        _cut(
            stringer,
            housed
            + (
                housing_slots(
                    stringer,
                    [housed[step] for step in slots.get("treads", ())],
                    [housed[step] for step in slots.get("risers", ())],
                    slots.get("wedged", False),
                    slots.setdefault("wedges", {}).setdefault(index, []),
                )
                if index in slots.get("boards", ())
                else []
            ),
            keep_pieces=False,
        )
        for index, stringer in enumerate(stringers)
    ]
    posts = [_cut(post, housed, keep_pieces=False) for post in posts]
    return stringers, posts, housed


def _vertical_planes(shape, minimum_area=0.0):
    """Yield ``(face, normal)`` for the plumb planar faces of ``shape``."""

    for face in shape.Faces:
        if face.Surface.TypeId != "Part::GeomPlane" or face.Area < minimum_area:
            continue
        normal = FreeCAD.Vector(face.Surface.Axis)
        if abs(normal.z) > 1e-6:
            continue
        normal.normalize()
        yield face, normal


def _housing_frame(stringer, housing):
    """Return ``(along, normal, face_offset)`` of the board face a housing
    opens on, or ``None``.

    The housing is the part of a step inside the board: one of its faces
    lies on the board's inner face.
    """

    board_faces = list(_vertical_planes(stringer, 100.0))
    for face, normal in sorted(
        _vertical_planes(housing), key=lambda item: item[0].Area, reverse=True
    ):
        offset = face.CenterOfMass.dot(normal)
        for board_face, board_normal in board_faces:
            if abs(abs(normal.dot(board_normal)) - 1.0) > 1e-6:
                continue
            if abs(board_face.CenterOfMass.dot(normal) - offset) > 1e-4:
                continue
            return FreeCAD.Vector(-normal.y, normal.x, 0.0), normal, offset
    return None


def _range(shape, direction):
    values = [vertex.Point.dot(direction) for vertex in shape.Vertexes]
    return min(values), max(values)


def housing_slots(stringer, treads, risers, wedged=False, wedges=None):
    """Return the cuts opening a housed board's step housings at the back.

    Each tread's housing runs on up the board, level with the tread's top,
    until it leaves the board's lower edge, so that the tread slides in from
    behind the stair. Its floor starts under the tread at the riser below
    and, ``wedged``, falls away by ``WEDGE_TAPER`` towards the back for a
    wedge driven in under the tread. Each riser's housing runs on down to
    the lower edge, so that the riser slides up into it from under the
    stair; ``wedged``, it also widens downwards behind the riser, and runs
    on down at that width, for a wedge driven up behind it. The cuts follow
    each step through the board, an angled balanced riser included, and
    stay within the housing depth.

    ``wedged``, the wedges these housings take are added to ``wedges``: a
    dict per wedge with the ``kind`` of step, its overall ``length``, the
    ``taper_length`` over which it thickens to its ``width``, and the
    ``depth`` of the housing it fills.
    """

    def housings(steps, found_steps=None):
        found = []
        for step in steps:
            if not stringer.BoundBox.intersect(step.BoundBox):
                continue
            try:
                housing = step.common(stringer)
            except (Part.OCCError, ValueError):
                continue
            if housing.Volume <= _TOLERANCE:
                continue
            frame = _housing_frame(stringer, housing)
            # A riser clipping the board's end opens on that end, not on
            # the board's face: it takes the board's frame afterwards.
            if frame is not None or found_steps is not None:
                found.append((housing, frame))
                if found_steps is not None:
                    found_steps.append(step)
        return found

    tread_housings = housings(treads)
    riser_steps = []
    riser_housings = housings(risers, riser_steps)
    if not tread_housings:
        return []

    def same_face(first, second):
        return (
            abs(first[1].dot(second[1]) - 1.0) < 1e-6
            and abs(first[2] - second[2]) < 1e-4
        )

    def uphill(frame):
        # Treads further along the board stand higher: the back of a tread
        # is up the board.
        points = [
            (housing.BoundBox.Center.dot(frame[0]), housing.BoundBox.Center.z)
            for housing, other in tread_housings
            if same_face(frame, other)
        ]
        if len(points) < 2:
            return None
        mean_u = sum(u for u, _z in points) / len(points)
        mean_z = sum(z for _u, z in points) / len(points)
        trend = sum((u - mean_u) * (z - mean_z) for u, z in points)
        return 1.0 if trend > 0.0 else -1.0

    # The board's face: the one most treads open on.
    board_frame = max(
        (frame for _housing, frame in tread_housings),
        key=lambda frame: sum(same_face(frame, other) for _housing, other in tread_housings),
    )

    stringer_bounds = stringer.BoundBox
    reach = stringer_bounds.DiagonalLength
    cuts = []

    def prism(frame, sign, housing, outline):
        along, normal, offset = frame
        low, high = _range(housing, normal)
        # Clear the board face the housing opens on.
        if abs(low - offset) < abs(high - offset):
            low -= 1.0
        else:
            high += 1.0
        base = normal * low

        def point(u, z):
            return base + along * (sign * u) + FreeCAD.Vector(0.0, 0.0, z)

        face = Part.Face(Part.makePolygon([point(u, z) for u, z in outline + outline[:1]]))
        solid = face.extrude(normal * (high - low))
        try:
            pieces = solid.common(stringer).Solids
        except (Part.OCCError, ValueError):
            return []
        # Only the cut running on from the housing: past the lower edge the
        # outline may pass through the board again further up.
        kept = [piece for piece in pieces if piece.distToShape(housing)[0] < 1e-3]
        cuts.extend(kept)
        return kept

    for housing, frame in tread_housings:
        sign = uphill(frame)
        if sign is None:
            continue
        along = frame[0] * sign
        front, back = _range(housing, along)
        bottom = housing.BoundBox.ZMin
        top = housing.BoundBox.ZMax
        # The floor starts at the back of the riser standing under the
        # tread, or at the tread's front without one.
        start = front
        for riser, other in riser_housings:
            riser_front, riser_back = _range(riser, along)
            if (
                other is not None
                and same_face(frame, other)
                and abs(riser.BoundBox.ZMax - bottom) < 2.0
                and front - 1.0 < riser_back < back + 1.0
            ):
                start = max(start, riser_back)
        end = start + reach
        taper = WEDGE_TAPER if wedged else 0.0
        kept = prism(
            frame,
            sign,
            housing,
            [(start, top), (end, top), (end, bottom - taper * (end - start)), (start, bottom)],
        )
        if wedged and kept and wedges is not None:
            # Driven in from behind under the tread, as long as the slot.
            length = max(_range(piece, along)[1] for piece in kept) - start
            low, high = _range(housing, frame[1])
            if length > 1.0:
                wedges.append(
                    {
                        "kind": "Tread",
                        "length": length,
                        "taper_length": length,
                        "width": WEDGE_TAPER * length,
                        "depth": high - low,
                    }
                )

    lowest = stringer_bounds.ZMin - 10.0
    for (housing, frame), riser in zip(riser_housings, riser_steps):
        sign = uphill(frame) if frame is not None else None
        if sign is None:
            # Opening on the board's end, or a face no tread opens on.
            frame = board_frame
            sign = uphill(frame)
        if sign is None:
            continue
        bottom = housing.BoundBox.ZMin
        top = housing.BoundBox.ZMax
        section = _plan_section(riser, (bottom + top) / 2.0)
        if section is None:
            continue
        # The riser's own frame: a balanced riser crosses the board at an
        # angle, and its cuts must follow it through the board.
        longest = max(section.OuterWire.Edges, key=lambda edge: edge.Length)
        length_direction = longest.Vertexes[-1].Point - longest.Vertexes[0].Point
        length_direction.z = 0.0
        if length_direction.Length < 1e-6:
            continue
        length_direction.normalize()
        behind = FreeCAD.Vector(-length_direction.y, length_direction.x, 0.0)
        if behind.dot(frame[0] * sign) < 0.0:
            behind = -behind
        back = max(vertex.Point.dot(behind) for vertex in section.Vertexes)
        # Only where the riser is housed in this board: past its end the
        # riser may die into a newel holding the board's tenon.
        footprint = _plan_section(housing, (bottom + top) / 2.0)
        if footprint is None:
            continue
        first, last = _range(footprint, length_direction)
        middle = footprint.CenterOfMass
        # Clear the board face the housing opens on.
        if not stringer.isInside(
            middle + length_direction * (first - 1.0 - middle.dot(length_direction)),
            1e-6,
            True,
        ):
            first -= 1.0
            outward = -length_direction
        else:
            last += 1.0
            outward = length_direction
        wedge = WEDGE_TAPER * (top - bottom) if wedged else 0.0
        tools = []
        if wedged:
            # Behind the riser, widening downwards, and on down the opening
            # at that width: the wedge is driven up from under the stair.
            outline = [(0.0, top), (wedge, bottom), (wedge, lowest), (0.0, lowest)]

            def point(across, z):
                return (
                    behind * (back + across)
                    + length_direction * first
                    + FreeCAD.Vector(0.0, 0.0, z)
                )

            face = Part.Face(Part.makePolygon([point(u, z) for u, z in outline + outline[:1]]))
            tools.append(face.extrude(length_direction * (last - first)))
        # Open down to the lower edge, all the way: the riser slides up into
        # its housing from under the stair.
        for shift in (FreeCAD.Vector(), outward):
            opening = footprint.translated(
                FreeCAD.Vector(0.0, 0.0, top - footprint.BoundBox.ZMin) + shift
            )
            tools.append(opening.extrude(FreeCAD.Vector(0.0, 0.0, lowest - top)))
        made = []
        for tool in tools:
            try:
                made.extend(tool.common(stringer).Solids)
            except (Part.OCCError, ValueError):
                continue
        cuts.extend(made)
        if wedged and made and wedges is not None:
            # Tapered behind the riser, then straight down the opening to
            # the lower edge, where it is driven from.
            reach_down = min(piece.BoundBox.ZMin for piece in made)
            wedges.append(
                {
                    "kind": "Riser",
                    "length": top - reach_down,
                    "taper_length": top - bottom,
                    "width": wedge,
                    "depth": last - first - 1.0,
                }
            )
    return cuts


def _plan_section(step, z):
    """Return the horizontal section of a plumb step at ``z``, or ``None``."""

    try:
        wires = step.slice(FreeCAD.Vector(0.0, 0.0, 1.0), z)
        faces = [Part.Face(wire) for wire in wires if wire.isClosed()]
    except (Part.OCCError, ValueError):
        return None
    return max(faces, key=lambda face: face.Area) if faces else None
