# SPDX-License-Identifier: LGPL-2.1-or-later

"""Stringer paths, profiles, and flight-run preparation."""

from dataclasses import replace
import math

import FreeCAD
import Part

from .geometry_core import (
    BalancedSection,
    _CircularProfile,
    _cross,
    _dot,
    balanced_section_top,
)

def straight_stringer_sections(
    metrics,
    width,
    tread_goings=None,
    top_elevations=None,
):
    """Return balanced-section compatible stations for one straight flight."""

    sections = []
    width = max(float(width), 0.01)
    goings = list(tread_goings or [])
    if len(goings) != metrics.tread_count:
        goings = [metrics.tread_width] * metrics.tread_count
    stations = [0.0]
    for going in goings:
        stations.append(stations[-1] + going)
    elevations = list(top_elevations or [])
    if len(elevations) != metrics.tread_count + 1:
        elevations = [
            (index + 1) * metrics.riser_height
            for index in range(metrics.tread_count + 1)
        ]
    for index in range(metrics.tread_count + 1):
        station = stations[index]
        sections.append(
            BalancedSection(
                center=(station, width / 2.0),
                tangent=(1.0, 0.0),
                left=(station, width),
                right=(station, 0.0),
                station=station,
                width=width,
                flight_index=0,
                riser_index=index + 1,
                top_elevation=elevations[index],
            )
        )
    return sections


def _stringer_inward(section, side):
    rail = section.left if side == "Left" else section.right
    inward = (
        section.center[0] - rail[0],
        section.center[1] - rail[1],
    )
    length = math.hypot(inward[0], inward[1])
    if length < 1e-9:
        if side == "Left":
            return (section.tangent[1], -section.tangent[0])
        return (-section.tangent[1], section.tangent[0])
    return (inward[0] / length, inward[1] / length)


def _stringer_cross_section(
    section,
    side,
    bottom,
    top,
    thickness,
    offset,
    housed,
):
    rail = section.left if side == "Left" else section.right
    inward = _stringer_inward(section, side)
    first = (
        rail[0] + inward[0] * offset,
        rail[1] + inward[1] * offset,
    )
    thickness_direction = -1.0 if housed else 1.0
    second = (
        first[0] + inward[0] * thickness * thickness_direction,
        first[1] + inward[1] * thickness * thickness_direction,
    )
    top = max(float(top), float(bottom) + 0.01)
    points = (
        FreeCAD.Vector(first[0], first[1], bottom),
        FreeCAD.Vector(second[0], second[1], bottom),
        FreeCAD.Vector(second[0], second[1], top),
        FreeCAD.Vector(first[0], first[1], top),
    )
    return Part.makePolygon((*points, points[0]))


# Largest amount a fitted pitch line may stand above any nosing it serves
# before the profile is split into another straight pitch.
PROFILE_FIT_TOLERANCE = 20.0
# Nominal easing radius joining two pitches of the upper board edge.
PROFILE_EASING_RADIUS = 600.0
# Nosings rising faster than this along a board converge on a newel.
PROFILE_MAXIMUM_PITCH = 1.5


def _fit_profile_line(points):
    """Fit one pitch through ``points``, raised to clear every one of them."""

    if len(points) == 1:
        return 0.0, points[0][1], 0.0
    mean_u = sum(u for u, _ in points) / len(points)
    mean_z = sum(z for _, z in points) / len(points)
    variance = sum((u - mean_u) ** 2 for u, _ in points)
    slope = (
        sum((u - mean_u) * (z - mean_z) for u, z in points) / variance
        if variance > 1e-9
        else 0.0
    )
    intercept = max(z - slope * u for u, z in points)
    deviation = max(intercept + slope * u - z for u, z in points)
    return slope, intercept, deviation


def _line_crossing(first, second):
    if abs(first[0] - second[0]) < 1e-12:
        return None
    return (second[1] - first[1]) / (first[0] - second[0])


def _stringer_profile_lines(parameters, values, single=False):
    """Approximate the nosing profile with a few straight pitches.

    Returns ``(lines, points)``. Each line is ``(slope, intercept)`` and the
    polyline formed by consecutive lines stays above every point. Several
    points at (almost) the same board position mark fan treads meeting at a newel:
    only the lowest one bears on the board, the others are carried by the
    post, so they must not bend the board's upper edge.
    """

    points = []
    for u, z in sorted(zip(parameters, values)):
        if points and (
            u - points[-1][0] < 1.0
            or z - points[-1][1] > PROFILE_MAXIMUM_PITCH * (u - points[-1][0])
        ):
            points[-1] = (points[-1][0], min(points[-1][1], z))
        else:
            points.append((u, z))
    if len(points) < 2:
        return [(0.0, points[0][1])], points

    if single:
        zones = [list(range(len(points)))]
    else:
        zones = []
        start = 0
        while start < len(points) - 1:
            end = start + 1
            while end + 1 < len(points):
                candidate = points[start : end + 2]
                if _fit_profile_line(candidate)[2] > PROFILE_FIT_TOLERANCE:
                    break
                end += 1
            zones.append(list(range(start, end + 1)))
            start = end

    lifts = [0.0] * len(zones)
    for _attempt in range(4 * len(points) + 8):
        lines = []
        for zone, lift in zip(zones, lifts):
            slope, intercept, _deviation = _fit_profile_line(
                [points[index] for index in zone]
            )
            lines.append((slope, intercept + lift))
        merge = None
        corners = []
        for index, (first, second) in enumerate(zip(lines, lines[1:])):
            crossing = _line_crossing(first, second)
            low = points[zones[index][0]][0]
            high = points[zones[index + 1][-1]][0]
            if (
                abs(first[0] - second[0]) < 0.02
                or crossing is None
                or not low < crossing < high
                or (corners and crossing <= corners[-1] + 1.0)
            ):
                merge = index
                break
            corners.append(crossing)
        if merge is not None:
            zones[merge : merge + 2] = [
                sorted(set(zones[merge]) | set(zones[merge + 1]))
            ]
            lifts[merge : merge + 2] = [max(lifts[merge], lifts[merge + 1])]
            continue

        # A point near a corner may fall under the neighbouring pitch.
        raised = False
        for u, z in points:
            index = sum(1 for corner in corners if u > corner)
            slope, intercept = lines[index]
            deficit = z - (intercept + slope * u)
            if deficit > 1e-6:
                lifts[index] += deficit
                raised = True
                break
        if not raised:
            return lines, points
    return [_fit_profile_line(points)[:2]], points


def _offset_profile_lines(lines, distance):
    """Offset pitch lines perpendicular to themselves, dropping lost ones."""

    lines = [
        (slope, intercept - distance * math.sqrt(1.0 + slope * slope))
        for slope, intercept in lines
    ]
    changed = True
    while changed and len(lines) > 1:
        changed = False
        corners = [_line_crossing(a, b) for a, b in zip(lines, lines[1:])]
        for index in range(1, len(lines) - 1):
            if (
                corners[index - 1] is None
                or corners[index] is None
                or corners[index] <= corners[index - 1] + 1.0
            ):
                del lines[index]
                changed = True
                break
        else:
            for index, corner in enumerate(corners):
                if corner is None:
                    del lines[index + 1]
                    changed = True
                    break
    return lines


def profile_value(lines, u):
    """Evaluate the polyline formed by consecutive pitch lines at ``u``."""

    index = 0
    for first, second in zip(lines, lines[1:]):
        crossing = _line_crossing(first, second)
        if crossing is None or u <= crossing:
            break
        index += 1
    slope, intercept = lines[index]
    return intercept + slope * u


def stringer_bottom_lines(parameters, values, width):
    """Return the lower board edge, ``width`` square below fitted pitches."""

    lines, _points = _stringer_profile_lines(parameters, values)
    return _offset_profile_lines(lines, float(width))


def _profile_polyline(lines, u_start, u_end):
    vertices = [(u_start, lines[0][1] + lines[0][0] * u_start)]
    for first, second in zip(lines, lines[1:]):
        u = _line_crossing(first, second)
        if u is None or not u_start < u < u_end:
            continue
        vertices.append((u, first[1] + first[0] * u))
    vertices.append((u_end, lines[-1][1] + lines[-1][0] * u_end))
    return vertices


def _profile_fillets(vertices, radius_for_corner, clearance_points=()):
    """Return ``(tangent_in, arc_mid, tangent_out)`` easing per vertex.

    ``None`` marks a sharp corner. A fillet is shrunk until it keeps every
    clearance point under it, so easing never digs into a housing.
    """

    fillets = [None] * len(vertices)
    for index in range(1, len(vertices) - 1):
        previous, vertex, following = vertices[index - 1 : index + 2]
        incoming = (vertex[0] - previous[0], vertex[1] - previous[1])
        outgoing = (following[0] - vertex[0], following[1] - vertex[1])
        incoming_length = math.hypot(*incoming)
        outgoing_length = math.hypot(*outgoing)
        if incoming_length < 1e-6 or outgoing_length < 1e-6:
            continue
        first = (incoming[0] / incoming_length, incoming[1] / incoming_length)
        second = (outgoing[0] / outgoing_length, outgoing[1] / outgoing_length)
        turn = math.acos(max(-1.0, min(1.0, _dot(first, second))))
        if turn < 1e-4:
            continue
        bisector = (second[0] - first[0], second[1] - first[1])
        bisector_length = math.hypot(*bisector)
        bisector = (bisector[0] / bisector_length, bisector[1] / bisector_length)
        half_tangent = math.tan(turn / 2.0)
        radius = radius_for_corner(index, bisector[1] > 0.0)
        # Leave each straight segment at least a tenth of its own length.
        radius = min(
            radius,
            0.45 * min(incoming_length, outgoing_length) / half_tangent,
        )
        while radius > 1.0:
            tangent = radius * half_tangent
            center = (
                vertex[0] + bisector[0] * radius / math.cos(turn / 2.0),
                vertex[1] + bisector[1] * radius / math.cos(turn / 2.0),
            )
            start = (vertex[0] - first[0] * tangent, vertex[1] - first[1] * tangent)
            end = (vertex[0] + second[0] * tangent, vertex[1] + second[1] * tangent)
            sign = -1.0 if bisector[1] > 0.0 else 1.0
            clear = all(
                center[1] + sign * math.sqrt(max(radius * radius - (u - center[0]) ** 2, 0.0))
                >= z - 1e-6
                for u, z in clearance_points
                if start[0] <= u <= end[0]
            )
            if clear:
                middle = (
                    center[0] - bisector[0] * radius,
                    center[1] - bisector[1] * radius,
                )
                fillets[index] = (start, middle, end)
                break
            radius *= 0.5
    return fillets


def _profile_edges(origin, direction, vertices, fillets):
    """Build connected 3D line/arc edges for one board edge profile."""

    def point(value):
        return FreeCAD.Vector(
            origin[0] + direction[0] * value[0],
            origin[1] + direction[1] * value[0],
            value[1],
        )

    edges = []
    cursor = vertices[0]
    for index in range(1, len(vertices)):
        fillet = fillets[index] if index < len(fillets) else None
        target = fillet[0] if fillet else vertices[index]
        if math.dist(cursor, target) > 1e-7:
            edges.append(Part.makeLine(point(cursor), point(target)))
        if fillet:
            edges.append(
                Part.Arc(point(fillet[0]), point(fillet[1]), point(fillet[2])).toShape()
            )
            cursor = fillet[2]
        else:
            cursor = target
    return edges


def make_stringer_profile_face(
    origin,
    direction,
    parameters,
    tops,
    width,
    straight_profile=False,
):
    """Return the flat side face of a board running over ``tops``.

    The upper edge is made of straight pitches joined by easings, the lower
    edge runs at the board ``width`` measured square to the pitch, the ends
    are plumb cuts, and anything below the floor is removed by a level cut.
    """

    lines, points = _stringer_profile_lines(parameters, tops, straight_profile)
    u_start = parameters[0]
    u_end = parameters[-1]
    top_vertices = _profile_polyline(lines, u_start, u_end)
    radii = {}

    def top_radius(index, _concave):
        radii[index] = PROFILE_EASING_RADIUS
        return PROFILE_EASING_RADIUS

    top_fillets = _profile_fillets(top_vertices, top_radius, points)
    bottom_lines = _offset_profile_lines(lines, float(width))
    bottom_vertices = _profile_polyline(bottom_lines, u_start, u_end)
    width = float(width)

    def bottom_radius(_index, concave):
        # Concentric with the upper easing: larger below a hollow, smaller
        # below a crest. A crest narrower than the board stays sharp.
        return PROFILE_EASING_RADIUS + width if concave else PROFILE_EASING_RADIUS - width

    bottom_fillets = _profile_fillets(bottom_vertices, bottom_radius)
    top_edges = _profile_edges(origin, direction, top_vertices, top_fillets)
    bottom_edges = _profile_edges(origin, direction, bottom_vertices, bottom_fillets)
    top_start = top_edges[0].Vertexes[0].Point
    top_end = top_edges[-1].Vertexes[-1].Point
    bottom_start = bottom_edges[0].Vertexes[0].Point
    bottom_end = bottom_edges[-1].Vertexes[-1].Point
    reversed_bottom = []
    for edge in reversed(bottom_edges):
        reversed_edge = edge.copy()
        reversed_edge.reverse()
        reversed_bottom.append(reversed_edge)
    face = Part.Face(
        Part.Wire(
            [
                *top_edges,
                Part.makeLine(top_end, bottom_end),
                *reversed_bottom,
                Part.makeLine(bottom_start, top_start),
            ]
        )
    )
    if face.BoundBox.ZMin < -1e-6:
        span = face.BoundBox.DiagonalLength + 1.0
        start = FreeCAD.Vector(
            origin[0] + direction[0] * (u_start - span),
            origin[1] + direction[1] * (u_start - span),
            0.0,
        )
        end = FreeCAD.Vector(
            origin[0] + direction[0] * (u_end + span),
            origin[1] + direction[1] * (u_end + span),
            0.0,
        )
        floor = Part.Face(
            Part.makePolygon(
                [
                    start,
                    end,
                    end + FreeCAD.Vector(0.0, 0.0, face.BoundBox.ZMax + span),
                    start + FreeCAD.Vector(0.0, 0.0, face.BoundBox.ZMax + span),
                    start,
                ]
            )
        )
        cut = face.common(floor).Faces
        if cut:
            face = cut[0]
    return face


def _make_planar_housed_stringer_shape(
    sections,
    tops,
    side,
    thickness,
    penetration,
    width,
    straight_profile=False,
):
    """Extrude a stable, shape-preserving side profile for a flat board."""

    if len(sections) < 2 or len(sections) != len(tops):
        return None
    first_tangent = sections[0].tangent
    tangent_length = math.hypot(*first_tangent)
    if tangent_length < 1e-9:
        return None
    tangent = (
        first_tangent[0] / tangent_length,
        first_tangent[1] / tangent_length,
    )
    first_inward = _stringer_inward(sections[0], side)
    surface_points = []
    for section in sections:
        section_tangent = section.tangent
        section_length = math.hypot(*section_tangent)
        if section_length < 1e-9:
            return None
        section_tangent = (
            section_tangent[0] / section_length,
            section_tangent[1] / section_length,
        )
        if (
            abs(_cross(tangent, section_tangent)) > 1e-7
            or _dot(tangent, section_tangent) < 0.0
        ):
            return None
        inward = _stringer_inward(section, side)
        if _dot(first_inward, inward) < 1.0 - 1e-7:
            return None
        rail = section.left if side == "Left" else section.right
        surface_points.append(
            (
                rail[0] + inward[0] * float(penetration),
                rail[1] + inward[1] * float(penetration),
            )
        )

    axis = (
        surface_points[-1][0] - surface_points[0][0],
        surface_points[-1][1] - surface_points[0][1],
    )
    axis_length = math.hypot(*axis)
    if axis_length < 1e-7:
        return None
    direction = (axis[0] / axis_length, axis[1] / axis_length)
    if _dot(direction, tangent) < 0.0:
        direction = (-direction[0], -direction[1])
    normal = (-direction[1], direction[0])
    origin = surface_points[0]
    tolerance = max(axis_length, 1.0) * 1e-7
    if any(
        abs(
            (point[0] - origin[0]) * normal[0]
            + (point[1] - origin[1]) * normal[1]
        )
        > tolerance
        for point in surface_points
    ):
        return None

    parameters = [
        (point[0] - origin[0]) * direction[0]
        + (point[1] - origin[1]) * direction[1]
        for point in surface_points
    ]
    if parameters[-1] < 1e-7:
        return None
    if any(
        following <= previous + 1e-7
        for previous, following in zip(parameters, parameters[1:])
    ):
        # Aggressive winding can make the tread intersections backtrack
        # along a straight board.  A global loft then produces loops.  Keep
        # their distribution but restore the only physically meaningful
        # ordering before constructing the side profile.
        total = parameters[-1]
        ordered = sorted(
            min(max(parameter, 0.0), total)
            for parameter in parameters
        )
        blend = 1e-5
        parameters = [
            (1.0 - blend) * parameter
            + blend * total * index / (len(ordered) - 1)
            for index, parameter in enumerate(ordered)
        ]
        parameters[0] = 0.0
        parameters[-1] = total

    try:
        face = make_stringer_profile_face(
            origin,
            direction,
            parameters,
            [float(top) for top in tops],
            width,
            straight_profile,
        )
        result = face.extrude(
            FreeCAD.Vector(
                -first_inward[0] * float(thickness),
                -first_inward[1] * float(thickness),
                0.0,
            )
        )
    except (Part.OCCError, ValueError):
        return None
    if result.isNull() or not result.isValid() or len(result.Solids) != 1:
        return None
    try:
        return result.removeSplitter()
    except Part.OCCError:
        return result


def _stringer_elevations(sections, riser_height):
    return [
        balanced_section_top(section, index, riser_height)
        for index, section in enumerate(sections)
    ]


def _stringer_slope(sections, elevations):
    if len(sections) < 2:
        return 0.0
    run = 0.0
    rise = 0.0
    for first, second, first_top, second_top in zip(
        sections, sections[1:], elevations, elevations[1:]
    ):
        elevation_change = second_top - first_top
        if abs(elevation_change) < 1e-9:
            continue
        section_run = math.hypot(
            second.center[0] - first.center[0],
            second.center[1] - first.center[1],
        )
        if section_run < 1e-9:
            section_run = max(second.station - first.station, 0.0)
        run += section_run
        rise += elevation_change
    if run < 1e-9:
        return 0.0
    return rise / run


def automatic_stringer_width(
    riser_height,
    going,
    step_thickness,
    nosing,
    nosing_offset,
    offset_direction="Perpendicular",
):
    """Return a practical board width with 50 mm below the step profile."""

    going = max(float(going), 0.01)
    slope = math.atan(max(float(riser_height), 0.0) / going)
    slope_cosine = max(math.cos(slope), 0.01)
    slope_sine = math.sin(slope)
    upper = max(float(nosing_offset), 0.0)
    if str(offset_direction) == "Vertical":
        upper *= slope_cosine
    step_envelope = (
        (max(float(riser_height), 0.0) + max(float(step_thickness), 0.0))
        * slope_cosine
        + max(float(nosing), 0.0) * slope_sine
    )
    return max(235.0, upper + step_envelope + 50.0)


def stringer_flight_runs(sections, flight_types=None):
    """Return ``(flight_index, sections)`` for each stair-bearing flight."""

    sections = [
        replace(section, riser_index=index + 1)
        if int(getattr(section, "riser_index", 0)) <= 0
        and not section.level_to_next
        else section
        for index, section in enumerate(sections)
    ]
    runs = []
    start = None
    flight_index = None
    for index, section in enumerate(sections[:-1]):
        if section.level_to_next:
            if start is not None and index > start:
                runs.append((flight_index, sections[start : index + 1]))
            section_type = (
                str(flight_types[section.flight_index])
                if flight_types
                and section.flight_index < len(flight_types)
                else ""
            )
            if section_type.endswith("landing"):
                runs.append(
                    (
                        section.flight_index,
                        [
                            replace(section, level_to_next=False),
                            replace(
                                sections[index + 1],
                                level_to_next=False,
                            ),
                        ],
                    )
                )
            start = None
            flight_index = None
            continue
        if start is None:
            start = index
            flight_index = section.flight_index
        elif section.flight_index != flight_index:
            previous_type = (
                str(flight_types[flight_index])
                if flight_types and flight_index < len(flight_types)
                else ""
            )
            following_type = (
                str(flight_types[section.flight_index])
                if flight_types and section.flight_index < len(flight_types)
                else ""
            )
            tangent_junction = (
                previous_type.startswith("Circular")
                or following_type.startswith("Circular")
            )
            if tangent_junction and index - start >= 2:
                runs.append((flight_index, sections[start:index]))
                start = index - 1
            else:
                runs.append((flight_index, sections[start : index + 1]))
                start = index
            flight_index = section.flight_index
    if start is not None and len(sections) - start >= 2:
        runs.append((flight_index, sections[start:]))
    return runs


def planar_stringer_sections(
    sections,
    side,
    origin,
    heading,
    width,
    start_seam=None,
    end_seam=None,
    nosing=0.0,
):
    """Project a straight-flight stringer onto one vertical board plane.

    Winding changes the longitudinal positions and elevations of the section
    cuts, but it must not bend the board in plan. The resulting upper and
    lower profiles can curve within the flat side face of the plank.
    """

    radians = math.radians(float(heading))
    tangent = (math.cos(radians), math.sin(radians))
    normal = (-tangent[1], tangent[0])
    width = max(float(width), 0.01)
    right_origin = (float(origin[0]), float(origin[1]))
    left_origin = (
        right_origin[0] + normal[0] * width,
        right_origin[1] + normal[1] * width,
    )
    selected_origin = left_origin if side == "Left" else right_origin

    def longitudinal(point):
        return (
            (point[0] - selected_origin[0]) * tangent[0]
            + (point[1] - selected_origin[1]) * tangent[1]
        )

    distances = [
        longitudinal(section.left if side == "Left" else section.right)
        for section in sections
    ]
    nosing_aligned = [False] * len(sections)
    nosing = max(float(nosing), 0.0)
    if nosing > 1e-9:
        for index, section in enumerate(sections[1:-1], start=1):
            section_length = math.hypot(*section.tangent)
            if section_length < 1e-9:
                continue
            section_tangent = (
                section.tangent[0] / section_length,
                section.tangent[1] / section_length,
            )
            crossing_cosine = _dot(tangent, section_tangent)
            if crossing_cosine > 1e-5:
                # The physical nosing is a parallel line ``nosing`` before
                # the concealed riser.  Its intersection with a straight
                # side board moves by nosing / cos(angle), not merely by the
                # nosing distance.  Profile the board at that real crossing.
                distances[index] -= nosing / crossing_cosine
                nosing_aligned[index] = True
    if start_seam is not None:
        distances[0] = longitudinal(start_seam)
    if end_seam is not None:
        distances[-1] = longitudinal(end_seam)

    result = []
    for section, distance, aligned in zip(
        sections, distances, nosing_aligned
    ):
        right = (
            right_origin[0] + tangent[0] * distance,
            right_origin[1] + tangent[1] * distance,
        )
        left = (
            right[0] + normal[0] * width,
            right[1] + normal[1] * width,
        )
        center = (
            right[0] + normal[0] * width / 2.0,
            right[1] + normal[1] * width / 2.0,
        )
        result.append(
            replace(
                section,
                center=center,
                tangent=tangent,
                left=left,
                right=right,
                profile_nosing_aligned=aligned,
            )
        )
    return result


def _stringer_section_runs(sections):
    """Split stringers at explicit level landing cells.

    The cross-sections on either side of a landing describe the incoming and
    outgoing flights. Lofting directly between them would twist a board across
    the entire landing, so each adjacent stair run must remain a separate
    manufactured part.
    """

    runs = []
    start = 0
    for index, section in enumerate(sections[:-1]):
        if not section.level_to_next:
            continue
        if index - start >= 1:
            runs.append(sections[start : index + 1])
        start = index + 1
    if len(sections) - start >= 2:
        runs.append(sections[start:])
    return runs


def boundary_stringer_runs(sections, side, footprint, include_post_sections=False):
    """Follow a side-entry flight's boundary, splitting boards at corners.

    A tread can cross a footprint corner without a riser at that corner.
    Insert that boundary vertex before splitting, interpolating its elevation
    between the two surrounding nosings. Each resulting board is planar.
    """
    from .geometry_plan import (
        _boundary_data,
        _boundary_vertices_between,
        _unwrap_boundary_parameters,
    )

    if len(sections) < 2:
        return []
    boundary = _boundary_data(footprint)
    points = [section.left if side == "Left" else section.right for section in sections]
    newel_points = {first for first, second in zip(points, points[1:]) if first == second}
    parameters = _unwrap_boundary_parameters(points, boundary)
    expanded = [(points[0], sections[0])]
    for index, (first, second) in enumerate(zip(parameters, parameters[1:])):
        corners = _boundary_vertices_between(
            first, second, 1.0 if second > first else -1.0, boundary
        )
        start = points[index]
        distance = 0.0
        for corner in corners:
            distance += math.dist(start, corner)
            ratio = distance / max(abs(second - first), 1e-9)
            front, rear = sections[index : index + 2]
            expanded.append(
                (
                    corner,
                    replace(
                        front,
                        station=front.station + ratio * (rear.station - front.station),
                        top_elevation=(
                            front.top_elevation + ratio * (rear.top_elevation - front.top_elevation)
                        ),
                    ),
                )
            )
            start = corner
        expanded.append((points[index + 1], sections[index + 1]))

    runs = []
    current = []
    previous_direction = None

    def projected(point, section, tangent):
        normal = (-tangent[1], tangent[0])
        sign = -1.0 if side == "Left" else 1.0
        other = (
            point[0] + sign * normal[0] * section.width,
            point[1] + sign * normal[1] * section.width,
        )
        return replace(
            section,
            left=point if side == "Left" else other,
            right=other if side == "Left" else point,
            center=((point[0] + other[0]) / 2.0, (point[1] + other[1]) / 2.0),
            tangent=tangent,
            locked_to_flight=True,
            profile_at_newel=point in newel_points,
        )

    for (first, front), (second, rear) in zip(expanded, expanded[1:]):
        length = math.dist(first, second)
        if length < 1e-7:
            continue
        direction = ((second[0] - first[0]) / length, (second[1] - first[1]) / length)
        if previous_direction is None or _dot(previous_direction, direction) < 1.0 - 1e-7:
            if current:
                runs.append(current)
            current = [projected(first, front, direction)]
        current.append(projected(second, rear, direction))
        previous_direction = direction
    if current:
        runs.append(current)
    if include_post_sections:
        # A board stops at a newel, but its railing must still clear the fan
        # treads sharing that point. Retain their different elevations for
        # the rail fit rather than dropping zero-length plan intervals.
        for run in runs:
            first = run[0].left if side == "Left" else run[0].right
            last = run[-1].left if side == "Left" else run[-1].right
            preceding = [
                projected(point, section, run[0].tangent)
                for point, section in expanded
                if math.dist(point, first) < 1e-7 and section.station < run[0].station - 1e-7
            ]
            following = [
                projected(point, section, run[-1].tangent)
                for point, section in expanded
                if math.dist(point, last) < 1e-7 and section.station > run[-1].station + 1e-7
            ]
            run[:] = preceding + run + following
    return runs


def _circular_stringer_data(
    sections,
    side,
    thickness,
    lateral_offset,
    housed,
):
    """Return exact coaxial radii and unwrapped angles for a curved board."""

    if len(sections) < 2:
        return None
    radial_lines = []
    for section in sections:
        direction = (
            section.left[0] - section.right[0],
            section.left[1] - section.right[1],
        )
        length = math.hypot(*direction)
        if length < 1e-9:
            return None
        radial_lines.append(
            (
                section.center,
                (direction[0] / length, direction[1] / length),
            )
        )

    best_pair = None
    best_cross = 0.0
    for first_index, first in enumerate(radial_lines[:-1]):
        for second_index in range(first_index + 1, len(radial_lines)):
            second = radial_lines[second_index]
            magnitude = abs(_cross(first[1], second[1]))
            if magnitude > best_cross:
                best_cross = magnitude
                best_pair = first, second
    if best_pair is None or best_cross < 1e-6:
        return None

    first_line, second_line = best_pair
    denominator = _cross(first_line[1], second_line[1])
    relative = (
        second_line[0][0] - first_line[0][0],
        second_line[0][1] - first_line[0][1],
    )
    distance = _cross(relative, second_line[1]) / denominator
    circle_center = (
        first_line[0][0] + first_line[1][0] * distance,
        first_line[0][1] + first_line[1][1] * distance,
    )

    path_radii = [
        math.hypot(
            section.center[0] - circle_center[0],
            section.center[1] - circle_center[1],
        )
        for section in sections
    ]
    path_radius = sum(path_radii) / len(path_radii)
    tolerance = max(path_radius, sections[0].width, 1.0) * 1e-5
    if max(path_radii) - min(path_radii) > tolerance:
        return None

    raw_angles = [
        math.atan2(
            section.center[1] - circle_center[1],
            section.center[0] - circle_center[0],
        )
        for section in sections
    ]
    angles = [raw_angles[0]]
    for angle in raw_angles[1:]:
        difference = math.atan2(
            math.sin(angle - angles[-1]),
            math.cos(angle - angles[-1]),
        )
        angles.append(angles[-1] + difference)
    sweep = angles[-1] - angles[0]
    if abs(sweep) < 1e-6:
        return None

    thickness = max(float(thickness), 0.01)
    thickness_direction = -1.0 if housed else 1.0
    surface_radii = []
    for section in sections:
        rail = section.left if side == "Left" else section.right
        inward = _stringer_inward(section, side)
        first = (
            rail[0] + inward[0] * float(lateral_offset),
            rail[1] + inward[1] * float(lateral_offset),
        )
        second = (
            first[0] + inward[0] * thickness * thickness_direction,
            first[1] + inward[1] * thickness * thickness_direction,
        )
        surface_radii.extend(
            (
                math.hypot(
                    first[0] - circle_center[0],
                    first[1] - circle_center[1],
                ),
                math.hypot(
                    second[0] - circle_center[0],
                    second[1] - circle_center[1],
                ),
            )
        )
    inner_radius = sum(surface_radii[0::2]) / len(sections)
    outer_radius = sum(surface_radii[1::2]) / len(sections)
    inner_radius, outer_radius = sorted((inner_radius, outer_radius))
    if inner_radius < 0.01 or outer_radius - inner_radius < 0.005:
        return None

    return {
        "profile": _CircularProfile(
            circle_center,
            inner_radius,
            outer_radius,
            angles[0],
            sweep,
        ),
        "angles": angles,
        "path_radius": path_radius,
    }
