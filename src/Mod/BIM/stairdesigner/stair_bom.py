# SPDX-License-Identifier: LGPL-2.1-or-later

"""Bill of materials: the timber stock a stair's members are cut from.

Every stringer, tread and riser is a flat member. Its stock is a plank of
the member's thickness, long and wide enough for the smallest rectangle
around its outline. A stringer part made of several boards fused at a
corner is listed board by board. Treads wider than the planks they are
glued up from are cut into plank-wide strips running along the tread.
"""

import csv
import io
import math
from dataclasses import dataclass, field

import FreeCAD
import Part

translate = FreeCAD.Qt.translate

# Planar faces smaller than this share of a part's largest face do not make
# a board of their own: end cuts, housings, tenons.
_BOARD_FACE_RATIO = 0.1
# A board's faces are at least this many times wider than it is thick.
_BOARD_WIDTH_RATIO = 3.0
_ROUNDING = 1.0
# Narrowest plank treads are glued up from; narrower ones would cut a
# tread into an absurd number of strips.
MINIMUM_PLANK_WIDTH = 50.0


def _planar_faces(shape):
    for face in shape.Faces:
        if face.Surface.TypeId != "Part::GeomPlane":
            continue
        u, v = face.Surface.parameter(face.CenterOfMass)
        normal = face.normalAt(u, v)
        normal.normalize()
        yield face, normal


def _outline_points(shape):
    points = []
    for edge in shape.Edges:
        try:
            points.extend(edge.discretize(QuasiDeflection=0.2))
        except (Part.OCCError, ValueError):
            points.extend(vertex.Point for vertex in edge.Vertexes)
    return points


def _frame(normal):
    """Return two axes completing ``normal`` to a right-handed frame."""

    helper = FreeCAD.Vector(0.0, 0.0, 1.0)
    if abs(normal.dot(helper)) > 0.9:
        helper = FreeCAD.Vector(1.0, 0.0, 0.0)
    first = helper.cross(normal)
    first.normalize()
    second = normal.cross(first)
    second.normalize()
    return first, second


def _convex_hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def cross(origin, first, second):
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _extents(points, angle):
    """Return ``(length, width)`` of ``points`` along ``angle`` and across."""

    cosine, sine = math.cos(angle), math.sin(angle)
    along = [x * cosine + y * sine for x, y in points]
    across = [-x * sine + y * cosine for x, y in points]
    return max(along) - min(along), max(across) - min(across)


def _minimum_rectangle(points):
    """Return ``(angle, length, width)`` of the smallest rectangle around
    2D ``points``, its length along ``angle``."""

    hull = _convex_hull(points)
    best = None
    for first, second in zip(hull, hull[1:] + hull[:1]):
        angle = math.atan2(second[1] - first[1], second[0] - first[0])
        length, width = _extents(hull, angle)
        if length < width:
            angle += math.pi / 2.0
            length, width = width, length
        if best is None or length * width < best[1] * best[2] - 1e-9:
            best = (angle, length, width)
    return best


def _board_pieces(shape):
    """Return ``(piece, normal)`` for each flat board of a member.

    Boards are told apart by the direction of their large faces. A part
    with one such direction is one board; otherwise each board is the part
    within its own faces' slab, sharing the corner where boards meet.
    """

    faces = list(_planar_faces(shape))
    if not faces:
        return []
    largest = max(face.Area for face, _normal in faces)
    directions = []
    for face, normal in sorted(faces, key=lambda item: item[0].Area, reverse=True):
        if face.Area < largest * _BOARD_FACE_RATIO:
            break
        if any(abs(abs(normal.dot(other)) - 1.0) < 1e-6 for _face, other, _depth in directions):
            continue
        depth = _depth_under(shape, face, normal)
        # A board's face is much wider than the board is thick; a tread's
        # front edge is not a board of its own.
        first, second = _frame(normal)
        _angle, _length, width = _minimum_rectangle(
            [(point.dot(first), point.dot(second)) for point in _outline_points(face)]
        )
        if depth > 1e-6 and width > _BOARD_WIDTH_RATIO * depth:
            directions.append((face, normal, depth))
    if len(directions) <= 1:
        normal = directions[0][1] if directions else max(faces, key=lambda item: item[0].Area)[1]
        return [(shape, normal)]

    pieces = []
    size = shape.BoundBox.DiagonalLength * 2.0
    for face, normal, thickness in directions:
        first, second = _frame(normal)
        offset = face.CenterOfMass.dot(normal)
        corner = (
            normal * (offset - thickness)
            - first * size / 2.0
            - second * size / 2.0
            + first * shape.BoundBox.Center.dot(first)
            + second * shape.BoundBox.Center.dot(second)
        )
        slab = Part.Face(
            Part.makePolygon(
                [
                    corner,
                    corner + first * size,
                    corner + first * size + second * size,
                    corner + second * size,
                    corner,
                ]
            )
        ).extrude(normal * thickness)
        try:
            piece = shape.common(slab)
        except (Part.OCCError, ValueError):
            continue
        if piece.Volume > 1e-6:
            pieces.append((piece, normal))
    return pieces or [(shape, directions[0][1])]


def _depth_under(shape, face, normal):
    """Return the material depth under ``face``, the board thickness.

    Sampled at several points of the face: the most common depth, as a
    sample may fall on a housing or run along a crossing board.
    """

    u0, u1, v0, v1 = face.ParameterRange
    depths = []
    for i in range(1, 6):
        for j in range(1, 6):
            u = u0 + (u1 - u0) * i / 6.0
            v = v0 + (v1 - v0) * j / 6.0
            point = face.valueAt(u, v)
            if not face.isInside(point, 1e-6, True):
                continue
            probe = Part.makeLine(point + normal * 0.01, point - normal * 100000.0)
            try:
                inside = shape.common(probe)
            except (Part.OCCError, ValueError):
                continue
            edges = sorted(inside.Edges, key=lambda edge: (edge.CenterOfMass - point).Length)
            if edges:
                depths.append(round(edges[0].Length, 1))
    if not depths:
        return 0.0
    return max(set(depths), key=depths.count)


def _grain_angle(shape, normal, first, second):
    """Return the direction of the longest straight edge across ``normal``."""

    best = None
    for edge in shape.Edges:
        if edge.Curve.TypeId != "Part::GeomLine":
            continue
        direction = edge.Vertexes[-1].Point - edge.Vertexes[0].Point
        if direction.Length < 1e-6 or abs(direction.normalize().dot(normal)) > 1e-6:
            continue
        if best is None or edge.Length > best[0]:
            best = (edge.Length, math.atan2(direction.dot(second), direction.dot(first)))
    return None if best is None else best[1]


@dataclass
class FlatPiece:
    """One flat piece of timber laid on its machined face's back.

    ``outline`` is its 2D outline, grain along X, in the positive quadrant;
    ``pockets`` are ``(depth, outline)`` of the housings cut into its upper
    face, in the same coordinates; ``back_pockets`` those cut into its
    underside, a tenon's lower cheek, seen from above with their depth
    from the underside. ``nosing_low`` tells a tread's nosing, the edge its
    strips are laid from, runs along its lower side.

    ``source`` is the stair part the piece is a board of, and ``frame``
    tells how it lies in that part's shape: the point its outline is
    measured from, its X and its Y axis there, as vectors. Seen along
    their cross product, towards the part, the board shows as ``outline``.
    """

    kind: str
    label: str
    thickness: float
    outline: list
    pockets: list = field(default_factory=list)
    back_pockets: list = field(default_factory=list)
    nosing_low: bool = True
    source: object = None
    frame: tuple = None

    @property
    def length(self):
        return max(x for x, _y in self.outline) - min(x for x, _y in self.outline)

    @property
    def width(self):
        return max(y for _x, y in self.outline) - min(y for _x, y in self.outline)


def _wire_points(wire, project):
    try:
        points = wire.discretize(QuasiDeflection=0.2)
    except (Part.OCCError, ValueError):
        points = [vertex.Point for vertex in wire.OrderedVertexes]
    flat = [project(point) for point in points]
    if len(flat) > 1 and math.dist(flat[0], flat[-1]) < 1e-6:
        flat.pop()
    return flat


def _polygon_face(points):
    vectors = [FreeCAD.Vector(x, y, 0.0) for x, y in points]
    return Part.Face(Part.makePolygon(vectors + vectors[:1]))


def _face_outline(face):
    return _wire_points(face.OuterWire, lambda point: (point.x, point.y))


def _seen_faces(piece, up, project):
    """Return what each face of ``piece`` covers seen against ``up``, as
    faces in the plane ``project`` flattens to, all turned the same way.

    Faces seen edge-on cover nothing and are left out.
    """

    seen = []
    for face in piece.Faces:
        if face.Surface.TypeId == "Part::GeomPlane":
            u, v = face.Surface.parameter(face.CenterOfMass)
            if abs(face.normalAt(u, v).dot(up)) < 1e-6:
                continue
        points = _wire_points(face.OuterWire, project)
        area = 0.5 * sum(
            x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])
        )
        if abs(area) < 1.0:
            continue
        if area < 0.0:
            # A face turned away is seen from behind.
            points.reverse()
        try:
            seen.append(_polygon_face(points))
        except (Part.OCCError, ValueError):
            continue
    return seen


def _tread_going(part):
    """Return the direction a tread is walked up, as its shape is placed;
    ``None`` for a tread made before treads recorded it."""

    going = getattr(part, "GoingDirection", None)
    if going is None or going.Length < 1e-6:
        return None
    return part.Placement.Rotation.multVec(going)


def _flatten(kind, label, piece, normal, going=None):
    """Return the ``FlatPiece`` of one board of a member.

    ``going`` is the direction a tread is walked up, when known: its nosing
    and so its grain run square to it.
    """

    parallel = [
        (face, face_normal, face.CenterOfMass.dot(normal))
        for face, face_normal in _planar_faces(piece)
        if abs(abs(face_normal.dot(normal)) - 1.0) < 1e-6
    ]
    if not parallel:
        return None
    levels = [level for _face, _normal, level in parallel]
    top, bottom = max(levels), min(levels)
    # Housing floors lie between the faces; they face the side the
    # housings open on, which goes up.
    floors = [item for item in parallel if bottom + 0.5 < item[2] < top - 0.5]
    if floors:
        opening = sum(face.Area * face_normal.dot(normal) for face, face_normal, _level in floors)
        up = normal if opening >= 0.0 else -normal
    elif kind == "Tread":
        # The walked face up, clear of clamps and holding tabs' marks below.
        up = normal if normal.z >= 0.0 else -normal
    else:
        up = normal
    # A tread's grain follows its nosing, whichever of its edges is longest:
    # a winder's back edge often is. Its nosing goes to the low side.
    flat_going = None
    if kind == "Tread" and going is not None:
        flat_going = going - up * going.dot(up)
        if flat_going.Length < 1e-6:
            flat_going = None
    if flat_going is not None:
        flat_going.normalize()
        along = flat_going.cross(up)
        across = up.cross(along)
    else:
        first, second = _frame(up)
        if kind == "Tread":
            angle = _grain_angle(piece, up, first, second)
        else:
            angle = None
        if angle is None:
            angle, _length, _width = _minimum_rectangle(
                [(point.dot(first), point.dot(second)) for point in _outline_points(piece)]
            )
        along = first * math.cos(angle) + second * math.sin(angle)
        across = up.cross(along)

    def project(point):
        return (point.dot(along), point.dot(across))

    # The outline is what all its faces cover, seen from above: normally
    # its full face, which the others lie within. A board with its ends cut
    # on the bevel, as a winder's riser, reaches past it under its other
    # face and its end cuts.
    faces = sorted(_seen_faces(piece, up, project), key=lambda face: face.Area, reverse=True)
    if not faces:
        return None
    largest = faces[0]
    outside = [
        face
        for face in faces[1:]
        if any(
            not largest.isInside(vertex.Point, 0.5, True) for vertex in face.Vertexes
        )
    ]
    outline = _face_outline(largest)
    if outside:
        try:
            merged = largest.fuse(outside).removeSplitter()
            union = max(merged.Faces, key=lambda face: face.Area)
            if union.Area > largest.Area + 1.0:
                outline = _face_outline(union)
        except (Part.OCCError, ValueError):
            # Faces that do not fuse leave the outline of the largest face.
            pass
    x0 = min(x for x, _y in outline)
    y0 = min(y for _x, y in outline)
    outline = [(x - x0, y - y0) for x, y in outline]
    surface = max(face.CenterOfMass.dot(up) for face, _n, _l in parallel)
    underside = min(face.CenterOfMass.dot(up) for face, _n, _l in parallel)
    pockets = []
    back_pockets = []
    for face, face_normal, _level in floors:
        points = _wire_points(face.OuterWire, project)
        points = [(x - x0, y - y0) for x, y in points]
        level = face.CenterOfMass.dot(up)
        # A floor faces the side it is cut from: a tenon has a cheek on
        # each side, the second one machined with the board turned over.
        if face_normal.dot(up) > 0.0:
            pockets.append((round(surface - level, 2), points))
        else:
            back_pockets.append((round(level - underside, 2), points))
    nosing_low = True
    if kind == "Tread" and flat_going is None:
        # Not told where it is walked up: taken for its longest edge.
        lines = [edge for edge in piece.Edges if edge.Curve.TypeId == "Part::GeomLine"]
        if lines:
            centre = project(max(lines, key=lambda edge: edge.Length).CenterOfMass)[1] - y0
            nosing_low = centre <= (max(y for _x, y in outline)) / 2.0
    return FlatPiece(
        kind,
        label,
        top - bottom,
        outline,
        pockets,
        back_pockets,
        nosing_low,
        frame=(along * x0 + across * y0, along, across),
    )


def flat_pieces(stair):
    """Return the ``FlatPiece`` of every board of the stair's members.

    A stringer part made of several boards fused at a corner gives one
    piece per board, each labelled with its rank.
    """

    pieces = []
    for kind, part in _members(stair):
        boards = _board_pieces(part.Shape)
        for index, (piece, normal) in enumerate(boards):
            name = f"{part.Label} ({index + 1}/{len(boards)})" if len(boards) > 1 else part.Label
            flat = _flatten(
                kind, name, piece, normal, _tread_going(part) if kind == "Tread" else None
            )
            if flat is not None:
                flat.source = part
                pieces.append(flat)
    pieces.extend(wedge_pieces(stair))
    return pieces


def wedge_pieces(stair):
    """Return the wedges the stair's wedged housings take, as ``FlatPiece``.

    Each is drawn on its side: its tip at the origin, thickening along X
    to its full width, then straight on to its driven end. It is cut from
    any stock at least as thick as its housing is deep, and planed down.
    """

    pieces = []
    group = getattr(stair, "StringersGroup", None)
    for part in group.Group if group else ():
        for kind, label in (
            ("Tread", translate("BIM", "tread wedge")),
            ("Riser", translate("BIM", "riser wedge")),
        ):
            for index, size in enumerate(getattr(part, f"{kind}Wedges", []) or [], start=1):
                length, taper, width = size.x, min(size.y, size.x), size.z
                if length < 1.0 or width < 0.1:
                    continue
                outline = [(0.0, 0.0), (length, 0.0), (length, width)]
                if taper < length - 0.01:
                    outline.append((taper, width))
                pieces.append(FlatPiece("Wedge", f"{part.Label}: {label} {index}", 0.0, outline))
    return pieces


def tread_strips(piece, plank_width):
    """Cut a tread into plank-wide strips laid from its nosing.

    Returns the strips as ``FlatPiece`` of kind ``Tread strip``, the last
    one completing the tread; the tread itself when it fits one plank.
    """

    # Within half a millimetre the last strip is dropped below, so only a
    # tread no wider than the plank is laid whole.
    if piece.width <= plank_width + 1e-6:
        return [piece]
    shape = _polygon_face(piece.outline)
    total = piece.width
    strips = []
    offset = 0.0
    while offset < total - 0.5:
        if piece.nosing_low:
            low, high = offset, min(offset + plank_width, total)
        else:
            low, high = max(total - offset - plank_width, 0.0), total - offset
        band = _polygon_face(
            [(-1.0, low), (piece.length + 1.0, low), (piece.length + 1.0, high), (-1.0, high)]
        )
        try:
            common = shape.common(band)
        except (Part.OCCError, ValueError):
            common = None
        for face in common.Faces if common is not None else ():
            if face.Area < 1.0:
                continue
            outline = _face_outline(face)
            x0 = min(x for x, _y in outline)
            y0 = min(y for _x, y in outline)
            strips.append(
                FlatPiece(
                    "Tread strip",
                    piece.label,
                    piece.thickness,
                    [(x - x0, y - y0) for x, y in outline],
                    nosing_low=True,
                    source=piece.source,
                )
            )
        offset += plank_width
    for index, strip in enumerate(strips, start=1):
        strip.label = f"{piece.label} ({index}/{len(strips)})"
    return strips


def _round(value):
    return round(value / _ROUNDING) * _ROUNDING


def _members(stair):
    """Yield ``(kind, part)`` for the stair's timber members."""

    group = getattr(stair, "StringersGroup", None)
    if group:
        for part in group.Group:
            if str(getattr(part, "StairDesignerRole", "")).endswith(("Stringer", "StringerBoard")):
                if not part.Shape.isNull():
                    yield "Stringer", part
    group = getattr(stair, "StepsGroup", None)
    if group:
        for part in group.Group:
            role = str(getattr(part, "StairDesignerRole", ""))
            if role in ("Tread", "Riser") and not part.Shape.isNull():
                yield role, part


def _check_plank_width(plank_width):
    plank_width = float(plank_width or 0.0)
    if 1e-6 < plank_width < MINIMUM_PLANK_WIDTH:
        raise ValueError(f"plank width must be 0 or at least {MINIMUM_PLANK_WIDTH:.0f} mm")
    return plank_width


def cut_pieces(pieces, plank_width=0.0):
    """Return ``pieces`` with the treads wider than ``plank_width`` cut
    into the strips they are glued up from. Zero keeps whole treads."""

    plank_width = _check_plank_width(plank_width)
    result = []
    for piece in pieces:
        if piece.kind == "Tread" and plank_width > 1e-6:
            result.extend(tread_strips(piece, plank_width))
        else:
            result.append(piece)
    return result


def stair_stock(stair, plank_width=0.0, pieces=None):
    """Return the stock rows of a stair.

    Each row is a dict: ``kind`` (Stringer, Tread, Riser, Tread strip),
    ``thickness``, ``length``, ``width`` in mm, rounded up to the
    millimetre, ``quantity``, the ``parts`` it serves, and the
    ``stock_width`` of the plank it is cut from. Identical sizes are
    grouped; ``sources`` are the stair's parts a row's items are boards
    of, none for wedges. With a ``plank_width``, treads are cut from planks
    that wide, and those wider than it are listed as the strips they are
    glued up from.
    ``pieces`` are the stair's ``flat_pieces`` when already known.
    """

    plank_width = _check_plank_width(plank_width)
    if pieces is None:
        pieces = flat_pieces(stair)
    grouped = {}

    def add(piece):
        key = (
            piece.kind,
            _round(math.ceil(piece.thickness - 0.05)),
            _round(math.ceil(piece.length - 0.05)),
            _round(math.ceil(piece.width - 0.05)),
        )
        grouped.setdefault(key, []).append(piece)

    def stock_width(kind, width):
        if kind in ("Tread", "Tread strip") and plank_width > 1e-6:
            return max(width, plank_width)
        return width

    for piece in cut_pieces(pieces, plank_width):
        add(piece)

    order = {"Stringer": 0, "Tread": 1, "Tread strip": 2, "Riser": 3, "Wedge": 4}
    rows = []
    for (kind, thickness, length, width), found in sorted(
        grouped.items(),
        key=lambda item: (order.get(item[0][0], 9), -item[0][1], -item[0][2], -item[0][3]),
    ):
        sources = []
        for piece in found:
            if piece.source is not None and not any(piece.source is other for other in sources):
                sources.append(piece.source)
        rows.append(
            {
                "kind": kind,
                "thickness": thickness,
                "length": length,
                "width": width,
                "quantity": len(found),
                "parts": [piece.label for piece in found],
                "sources": sources,
                "stock_width": stock_width(kind, width),
            }
        )
    return rows


def stock_totals(rows):
    """Return ``(thickness, width, total length)`` of plank per stock size.

    The lengths add up end to end, without saw kerf or offcut allowance.
    Wedges come from offcuts and are left out.
    """

    totals = {}
    for row in rows:
        if row["kind"] == "Wedge":
            continue
        key = (row["thickness"], row["stock_width"])
        totals[key] = totals.get(key, 0.0) + row["length"] * row["quantity"]
    return [
        (thickness, width, length)
        for (thickness, width), length in sorted(totals.items(), reverse=True)
    ]


def stock_csv(rows):
    """Return the stock rows as CSV text."""

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Part", "Quantity", "Thickness (mm)", "Length (mm)", "Width (mm)", "Items"])
    for row in rows:
        writer.writerow(
            [
                row["kind"],
                row["quantity"],
                f"{row['thickness']:.0f}",
                f"{row['length']:.0f}",
                f"{row['width']:.0f}",
                ", ".join(row["parts"]),
            ]
        )
    writer.writerow([])
    writer.writerow(["Plank thickness (mm)", "Plank width (mm)", "Total length (mm)"])
    for thickness, width, length in stock_totals(rows):
        writer.writerow([f"{thickness:.0f}", f"{width:.0f}", f"{length:.0f}"])
    return buffer.getvalue()


MEMBER_KINDS = ("Stringer", "Tread", "Riser", "Wedge")


def kind_label(kind):
    """Return the name of a kind of piece, in the user's language."""

    return {
        "Stringer": translate("BIM", "Stringer"),
        "Tread": translate("BIM", "Tread"),
        "Tread strip": translate("BIM", "Tread strip"),
        "Riser": translate("BIM", "Riser"),
        "Wedge": translate("BIM", "Wedge"),
    }.get(kind, kind)


_MATERIAL_PROPERTIES = {
    "Stringer": "BomStringerMaterials",
    "Tread": "BomTreadMaterials",
    "Riser": "BomRiserMaterials",
    "Wedge": "BomWedgeMaterials",
}


def material_names(given):
    """Return the names of the materials a kind of member is ``given``:
    one name or several, without blanks or repeats, in their order."""

    if isinstance(given, str):
        given = [given]
    names = []
    for name in given or ():
        name = str(name)
        if name and name not in names:
            names.append(name)
    return names


DEFAULT_CUT_SPACING = 5.0


@dataclass
class Material:
    """Stock a member is cut from: planks or panels of one size.

    Its thickness is that of the parts it is given: parts of another
    thickness get stock of their own.
    """

    name: str
    length: float
    width: float
    # Left between parts on the stock: saw kerf or cutter diameter.
    spacing: float = DEFAULT_CUT_SPACING


def stair_materials(stair):
    """Return the stair's stock materials and which one each kind uses.

    Returns ``(materials, assignment)``: the ``Material`` list and a dict
    from member kind to the names of the materials it may be cut from.
    """

    names = list(getattr(stair, "BomMaterialNames", []) or [])
    count = len(names)

    def values(name, default=0.0):
        found = list(getattr(stair, name, []) or [])
        return (found + [default] * count)[:count]

    materials = [
        Material(name, length, width, spacing)
        for name, length, width, spacing in zip(
            names,
            values("BomMaterialLengths"),
            values("BomMaterialWidths"),
            values("BomMaterialSpacings", DEFAULT_CUT_SPACING),
        )
    ]
    assignment = {
        kind: material_names(getattr(stair, prop, None))
        for kind, prop in _MATERIAL_PROPERTIES.items()
    }
    return materials, assignment


def set_stair_materials(stair, materials, assignment):
    """Store ``materials`` and the ``assignment`` of kinds on the stair:
    for each kind, the name of its material or those of its materials."""

    stair.BomMaterialNames = [material.name for material in materials]
    stair.BomMaterialLengths = [float(material.length) for material in materials]
    stair.BomMaterialWidths = [float(material.width) for material in materials]
    stair.BomMaterialSpacings = [float(material.spacing) for material in materials]
    for kind, prop in _MATERIAL_PROPERTIES.items():
        setattr(stair, prop, material_names(assignment.get(kind)))


def default_materials(stair, pieces=()):
    """Return starting materials: one per member kind.

    Common solid-wood plank sizes, made long and wide enough for the
    stringers and risers among ``pieces``; treads are glued up from
    narrower planks. The user sets their own.
    """

    def fitting(kind, size, minimum, step):
        sizes = [size(piece) for piece in pieces if piece.kind == kind]
        largest = max(sizes, default=0.0)
        return max(minimum, math.ceil((largest + 1.0) / step) * step)

    materials = [
        Material(
            translate("BIM", "Stringer planks"),
            fitting("Stringer", lambda piece: piece.length, 4000.0, 500.0),
            fitting("Stringer", lambda piece: piece.width, 300.0, 50.0),
        ),
        Material(translate("BIM", "Tread planks"), 3000.0, 300.0),
        Material(
            translate("BIM", "Riser planks"),
            3000.0,
            fitting("Riser", lambda piece: piece.width, 200.0, 10.0),
        ),
    ]
    assignment = {kind: [material.name] for kind, material in zip(MEMBER_KINDS, materials)}
    # The stringer planks leave the most room around their parts.
    assignment["Wedge"] = [materials[0].name]
    return materials, assignment


@dataclass
class MaterialLayout:
    """The stock of one material and thickness, and the parts laid out on it."""

    material: Material
    thickness: float
    stocks: list
    unplaced: list


def _choose_materials(group, allowed, cut, pack):
    """Return the material each piece of ``group`` is cut from, by ``id``.

    ``allowed`` gives each piece's materials, ``cut(piece, material)`` the
    parts it is cut into there and ``pack(material, pieces)`` their layout.
    Each piece starts on the first of its materials it fits. Pieces then
    move to another of their materials only where that takes fewer stocks
    in all: those of one stock filling the room left on the other
    material's, or all those of one material together.
    """

    def fits(piece, material):
        return all(
            part.length <= material.length + 1e-6 and part.width <= material.width + 1e-6
            for part in cut(piece, material)
        )

    choice = {}
    for piece in group:
        options = allowed[id(piece)]
        choice[id(piece)] = next(
            (material for material in options if fits(piece, material)), options[0]
        )
    if all(len(allowed[id(piece)]) < 2 for piece in group):
        return choice

    def on(material, chosen):
        return [piece for piece in group if chosen[id(piece)] is material]

    def used(chosen):
        found = []
        for piece in group:
            if chosen[id(piece)] not in found:
                found.append(chosen[id(piece)])
        return found

    def taken(material, chosen):
        """Return the parts ``material`` leaves out and the stocks it takes."""

        found, unplaced = pack(material, on(material, chosen))
        return len(unplaced), len(found)

    def cost(chosen):
        """Return the parts left out and the stocks taken: fewer is better."""

        counts = [taken(material, chosen) for material in used(chosen)]
        return sum(left for left, _stocks in counts), sum(stocks for _left, stocks in counts)

    def movable(pieces, target):
        return [
            piece
            for piece in pieces
            if any(material is target for material in allowed[id(piece)])
            and fits(piece, target)
        ]

    def trials(chosen):
        """Yield the choices one move away from ``chosen``."""

        for source in used(chosen):
            mine = on(source, chosen)
            targets = []
            for piece in mine:
                for material in allowed[id(piece)]:
                    if material is not source and material not in targets:
                        targets.append(material)
            if not targets:
                continue
            stocks, _unplaced = pack(source, mine)
            owner = {id(part): piece for piece in mine for part in cut(piece, source)}
            for stock in sorted(stocks, key=lambda stock: stock.used):
                there = {}
                for item in stock.placed:
                    piece = owner.get(id(item.part))
                    if piece is not None:
                        there[id(piece)] = piece
                for target in targets:
                    # Into the room the target's stocks have left, the
                    # largest first: no stock is opened for them.
                    trial = dict(chosen)
                    room = taken(target, trial)
                    moved = False
                    for piece in sorted(
                        movable(there.values(), target),
                        key=lambda piece: piece.length * piece.width,
                        reverse=True,
                    ):
                        trial[id(piece)] = target
                        if taken(target, trial) > room:
                            trial[id(piece)] = source
                        else:
                            moved = True
                    if moved:
                        yield trial
            for target in targets:
                found = movable(mine, target)
                if found:
                    trial = dict(chosen)
                    trial.update((id(piece), target) for piece in found)
                    yield trial

    best = cost(choice)
    improved = True
    while improved:
        improved = False
        for trial in trials(choice):
            found = cost(trial)
            if found < best:
                choice, best, improved = trial, found, True
                break
    return choice


def stair_layout(materials, assignment, pieces, flip=True):
    """Lay the stair's ``pieces`` out on the stock of their materials.

    ``assignment`` gives each kind of member the name of its material, or
    those of the materials it may be cut from. Treads wider than their
    material are cut into strips first. Kinds sharing a material share its
    stock, as long as they are as thick: each thickness gets stock of its
    own, parts spaced by the material's cut spacing. A kind with several
    materials is cut from the first one its parts fit, and its parts go to
    another only where that saves stock. Wedges only fill the room the
    other parts leave on the thickest stock of their materials, never
    needing stock of their own. With ``flip``, parts without housings may
    be turned over, laid on their other face, when that saves stock in
    all: not for stock with one finished face. Returns ``(layouts,
    unassigned)``: a ``MaterialLayout`` per material and thickness used,
    with the parts too large for its stock, and the pieces whose kind has
    no material.
    """

    def cost(found):
        layouts, _unassigned = found
        return (
            sum(len(layout.stocks) for layout in layouts),
            sum(len(layout.unplaced) for layout in layouts),
        )

    plain = _stair_layout(materials, assignment, pieces, False)
    if not flip:
        return plain
    over = _stair_layout(materials, assignment, pieces, True)
    return over if cost(over) < cost(plain) else plain


def _stair_layout(materials, assignment, pieces, flip):
    """Lay the pieces out as ``stair_layout`` tells, those without housings
    turned over wherever they fit better so with ``flip``."""

    from .stair_nesting import lay_out

    by_name = {}
    for material in materials:
        if material.length > 0.0 and material.width > 0.0:
            by_name.setdefault(material.name, material)
    allowed = {}
    members = []
    unassigned = []
    for piece in pieces:
        kind = "Tread" if piece.kind == "Tread strip" else piece.kind
        found = [
            by_name[name] for name in material_names(assignment.get(kind)) if name in by_name
        ]
        if found:
            allowed[id(piece)] = found
            members.append(piece)
        else:
            unassigned.append(piece)

    cuts = {}

    def cut(piece, material):
        key = (id(piece), material.name)
        if key not in cuts:
            if piece.kind == "Tread" and material.width >= MINIMUM_PLANK_WIDTH:
                cuts[key] = tread_strips(piece, material.width)
            else:
                cuts[key] = [piece]
        return cuts[key]

    def may_flip(part):
        # Housings are cut from the face they open on: that one stays up.
        return not part.pockets and not part.back_pockets

    def lay(material, chosen, fillers=()):
        return lay_out(
            [(part, part.outline) for piece in chosen for part in cut(piece, material)],
            material.length,
            material.width,
            material.spacing,
            [(piece, piece.outline) for piece in fillers],
            may_flip if flip else None,
        )

    packed = {}

    def pack(material, chosen):
        key = (material.name, tuple(id(piece) for piece in chosen))
        if key not in packed:
            packed[key] = lay(material, chosen)
        return packed[key]

    wedges = [piece for piece in members if piece.kind == "Wedge"]
    by_thickness = {}
    for piece in members:
        if piece.kind != "Wedge":
            by_thickness.setdefault(round(piece.thickness, 1), []).append(piece)
    choice = {}
    for group in by_thickness.values():
        choice.update(_choose_materials(group, allowed, cut, pack))

    stocked = [
        material
        for material in by_name.values()
        if any(found is material for found in choice.values())
    ]
    # A wedge fills the room left on each of its materials in turn.
    places = {
        id(wedge): [material for material in stocked if material in allowed[id(wedge)]]
        for wedge in wedges
    }
    placed = set()
    layouts = []
    for material in by_name.values():
        if material not in stocked:
            # Only wedges: nothing else of the material to fill.
            loose = [
                wedge
                for wedge in wedges
                if not places[id(wedge)] and allowed[id(wedge)][0] is material
            ]
            if loose:
                layouts.append(MaterialLayout(material, 0.0, [], loose))
            continue
        fillers = [
            wedge
            for wedge in wedges
            if id(wedge) not in placed and material in places[id(wedge)]
        ]
        for thickness in sorted(by_thickness, reverse=True):
            chosen = [piece for piece in by_thickness[thickness] if choice[id(piece)] is material]
            if not chosen:
                continue
            if fillers:
                stocks, unplaced = lay(material, chosen, fillers)
                placed.update(id(item.part) for stock in stocks for item in stock.placed)
                # Those finding no room here may find some on their next
                # material; they are left out on their last one.
                unplaced = [
                    piece
                    for piece in unplaced
                    if piece.kind != "Wedge" or places[id(piece)][-1] is material
                ]
                fillers = []
            else:
                stocks, unplaced = pack(material, chosen)
            layouts.append(MaterialLayout(material, thickness, stocks, unplaced))
    return layouts, unassigned
