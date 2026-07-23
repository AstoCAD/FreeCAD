# SPDX-License-Identifier: LGPL-2.1-or-later

"""TechDraw drawings of a stair's members, to ask for quotes or to cut.

One page per distinct part: a view of the part itself, seen square to its
face and scaled to the page, with its overall length and width, the
length of each straight edge, the radius of each arc and the angle of
each corner that is not square. Parts of the same shape share a page,
which gives their number.

The pages are ordinary TechDraw pages, kept in a group of the stair's
document: they can be adjusted there, and are replaced the next time the
drawings are made.
"""

import math
import os
import re
import time
from dataclasses import dataclass

import FreeCAD

from .stair_bom import kind_label, stair_materials

translate = FreeCAD.Qt.translate

PAPER_SIZES = ("A4", "A3")
# The kinds of pieces that can be drawn, in the order of their pages.
DRAWN_KINDS = ("Tread", "Riser", "Stringer")

# Margin kept where a template tells nothing of its drawing space.
PAGE_MARGIN = 10.0
# A title block keeps a row of fields, and the projection symbol, above
# its frame.
TITLE_BLOCK_HEAD = 20.0
# Room kept around the part for its dimensions, and above it for its notes.
DIMENSION_ROOM = 24.0
NOTES_ROOM = 14.0
NOTES_TEXT_SIZE = 3.5
# Distance of the dimension lines: the overall ones from the part's
# extent, those of its edges from the edges.
OVERALL_OFFSET = 17.0
EDGE_OFFSET = 9.0
# Where the text of an angle or of a radius stands, from its corner or arc.
ANGLE_OFFSET = 11.0
RADIUS_OFFSET = 9.0
# Room a dimension text takes, along and across its line.
TEXT_LENGTH = 16.0
TEXT_HEIGHT = 5.0
# Edges shorter than this on the page have no room for their length.
MINIMUM_DIMENSIONED_EDGE = 7.0
# Corners this close, in degrees, to square or flat get no angle.
SQUARE_TOLERANCE = 0.5
# View edges lie this close to the outline they are the edges of.
OUTLINE_TOLERANCE = 0.3
# How long the views' hidden lines may take to compute, in seconds.
PROJECTION_TIMEOUT = 60.0


@dataclass
class DrawingSettings:
    """What the drawings show and the pages they are scaled to.

    ``kinds`` are the kinds of pieces drawn, among ``DRAWN_KINDS``;
    ``paper`` one of ``PAPER_SIZES``. With ``standard_scale`` the parts are
    drawn at the largest of 1:1, 1:2, 1:5, 1:10... fitting the page,
    otherwise as large as it allows, never enlarged. ``hidden_edges`` adds
    the edges hidden under the face shown, such as a tenon's lower cheek.
    """

    kinds: tuple = ("Tread", "Riser")
    paper: str = "A4"
    standard_scale: bool = False
    hidden_edges: bool = False


def _shape_key(piece):
    """Return what two pieces of the same shape have in common."""

    def points(outline):
        rounded = [(round(x, 1), round(y, 1)) for x, y in outline]
        first = rounded.index(min(rounded))
        return tuple(rounded[first:] + rounded[:first])

    return (
        piece.kind,
        round(piece.thickness, 1),
        points(piece.outline),
        tuple(
            sorted(
                (side, round(depth, 1), points(outline))
                for side, pockets in enumerate((piece.pockets, piece.back_pockets))
                for depth, outline in pockets
            )
        ),
    )


def distinct_parts(pieces, kinds=DRAWN_KINDS):
    """Return ``(piece, labels)`` for each distinct shape among the
    ``pieces`` of ``kinds``: the first piece of that shape and the labels
    of all of them. Treads come first, then risers, then stringers.
    """

    found = {}
    for piece in pieces:
        if (
            piece.kind in kinds
            and piece.kind in DRAWN_KINDS
            and piece.source is not None
            and len(piece.outline) >= 3
        ):
            found.setdefault(_shape_key(piece), (piece, []))[1].append(piece.label)
    return sorted(found.values(), key=lambda part: DRAWN_KINDS.index(part[0].kind))


def _standard_scale(reduction):
    """Return the smallest of 1, 2, 5, 10, 20, 50... holding ``reduction``."""

    decade = 1.0
    while True:
        for step in (1.0, 2.0, 5.0):
            if step * decade >= reduction - 1e-9:
                return step * decade
        decade *= 10.0


def template_file(paper, lying):
    """Return the TechDraw template of a ``paper`` page, ``lying`` or standing."""

    orientation = "landscape" if lying else "portrait"
    return os.path.join(
        FreeCAD.getResourceDir(),
        "Mod",
        "TechDraw",
        "Templates",
        "ISO5457-minimal",
        paper,
        orientation,
        f"{paper}_{orientation.capitalize()}_ISO5457_minimal.svg",
    )


def _template_rectangle(text, name):
    found = re.search(r'<rect\b[^>]*\bid="%s"[^>]*>' % name, text)
    if found is None:
        return None
    values = dict(re.findall(r'\b(x|y|width|height)="([-+0-9.eE]+)"', found.group(0)))
    if len(values) != 4:
        return None
    return tuple(float(values[key]) for key in ("x", "y", "width", "height"))


def drawing_space(template):
    """Return the ``(left, bottom, width, height)`` a template leaves to the
    views, in page coordinates: its frame, above its title block. A
    template telling neither keeps a margin around its page.
    """

    with open(template, encoding="utf-8") as file:
        text = file.read()
    number = r"[-+0-9.eE]+"
    size = re.search(
        rf'<svg\b[^>]*\bviewBox="\s*{number}\s+{number}\s+({number})\s+({number})', text
    )
    if size is None:
        raise ValueError(f"template without a size: {template}")
    page_width, page_height = float(size.group(1)), float(size.group(2))
    frame = _template_rectangle(text, "drawing_space_frame") or (
        PAGE_MARGIN,
        PAGE_MARGIN,
        page_width - 2.0 * PAGE_MARGIN,
        page_height - 2.0 * PAGE_MARGIN,
    )
    left, top, width, height = frame
    title = _template_rectangle(text, "title_block_frame")
    if title is not None and top < title[1] - TITLE_BLOCK_HEAD < top + height:
        height = title[1] - TITLE_BLOCK_HEAD - top
    # A template counts from its upper left corner, a page from its lower one.
    return left, page_height - top - height, width, height


def _part_frame(piece):
    """Return ``(origin, along, across)`` of a piece in its document: the
    part's shape is told in its container, which may be placed itself."""

    origin, along, across = piece.frame
    source = piece.source
    outer = source.getGlobalPlacement().multiply(source.Placement.inverse())
    return (
        outer.multVec(origin),
        outer.Rotation.multVec(along),
        outer.Rotation.multVec(across),
    )


def part_silhouette(piece):
    """Return points all around the part ``piece`` is a board of, seen as
    the piece is drawn: along its frame, from the origin of its outline.

    The outline is the board's face. The part reaches further where its
    ends are cut on the bevel, as a winder's riser, or where it is made of
    several boards: its drawing shows all of it.
    """

    origin, along, across = piece.frame
    points = []
    for edge in piece.source.Shape.Edges:
        try:
            found = edge.discretize(Deflection=0.01)
        except (RuntimeError, ValueError):
            found = [vertex.Point for vertex in edge.Vertexes]
        points.extend(
            ((point - origin).dot(along), (point - origin).dot(across)) for point in found
        )
    return points


def _extent(points):
    """Return the ``(length, width)`` of what ``points`` lie around."""

    return (
        max(x for x, _y in points) - min(x for x, _y in points),
        max(y for _x, y in points) - min(y for _x, y in points),
    )


def _layout(size, settings):
    """Return the ``(template, space, reduction)`` showing a part of
    ``size``, its length and width, largest: the page lying or standing,
    lying when it makes no difference."""

    best = None
    for lying in (True, False):
        template = template_file(settings.paper, lying)
        space = drawing_space(template)
        room = (
            space[2] - 2.0 * DIMENSION_ROOM,
            space[3] - 2.0 * DIMENSION_ROOM - NOTES_ROOM,
        )
        if min(room) <= 0.0:
            continue
        reduction = max(size[0] / room[0], size[1] / room[1], 1.0)
        if settings.standard_scale:
            reduction = _standard_scale(reduction)
        if best is None or reduction < best[2] - 1e-9:
            best = (template, space, reduction)
    if best is None:
        raise ValueError(f"no room for a drawing on {settings.paper}")
    return best


def _drawings_group(stair, create=False):
    """Return the group holding the stair's drawings."""

    document = stair.Document
    name = f"{stair.Name}_Drawings"
    group = document.getObject(name)
    if group is None and create:
        group = document.addObject("App::DocumentObjectGroup", name)
    if group is not None:
        group.Label = translate("BIM", "{} drawings").format(stair.Label)
    return group


def remove_stair_drawings(stair):
    """Remove the pages made for ``stair``, with all they hold."""

    group = _drawings_group(stair)
    if group is None:
        return
    document = stair.Document
    names = []
    for page in group.Group:
        if not page.isDerivedFrom("TechDraw::DrawPage"):
            continue
        # Dimensions go before the views they measure.
        names.extend(
            view.Name
            for view in sorted(
                page.Views,
                key=lambda view: not view.isDerivedFrom("TechDraw::DrawViewDimension"),
            )
        )
        names.append(page.Name)
        if page.Template is not None:
            names.append(page.Template.Name)
    for name in names:
        # Removing one may take along those that only served it.
        if document.getObject(name) is not None:
            document.removeObject(name)


def _wait_for_projections(views):
    """Let the views finish their hidden line removal.

    With the application's window up TechDraw computes it aside and takes
    the result back in the event loop; without, it is done on recompute.
    """

    if not FreeCAD.GuiUp:
        return
    from PySide import QtCore

    deadline = time.monotonic() + PROJECTION_TIMEOUT
    while time.monotonic() < deadline and not all(view.isProjectionReady() for view in views):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(20, loop.quit)
        loop.exec_(QtCore.QEventLoop.ExcludeUserInputEvents)


def _numbered(get):
    """Return what ``get(0)``, ``get(1)``... give until they run out."""

    found = []
    while True:
        try:
            found.append(get(len(found)))
        except (ValueError, IndexError, RuntimeError):
            return found


def _distance_to_outline(point, outline):
    best = math.inf
    for (x1, y1), (x2, y2) in zip(outline, outline[1:] + outline[:1]):
        dx, dy = x2 - x1, y2 - y1
        length = dx * dx + dy * dy
        ratio = (
            0.0
            if length < 1e-12
            else min(max(((point[0] - x1) * dx + (point[1] - y1) * dy) / length, 0.0), 1.0)
        )
        best = min(best, math.hypot(point[0] - x1 - ratio * dx, point[1] - y1 - ratio * dy))
    return best


def _inside(point, outline):
    inside = False
    for (x1, y1), (x2, y2) in zip(outline, outline[1:] + outline[:1]):
        if (y1 > point[1]) != (y2 > point[1]) and point[0] < x1 + (point[1] - y1) * (x2 - x1) / (
            y2 - y1
        ):
            inside = not inside
    return inside


class _Texts:
    """The room the dimension texts placed so far take on the page."""

    def __init__(self):
        self.boxes = []

    def place(self, x, y, upright=False):
        """Take the room of a text at ``(x, y)`` and tell whether it had it."""

        half = (TEXT_HEIGHT / 2.0, TEXT_LENGTH / 2.0) if upright else (
            TEXT_LENGTH / 2.0,
            TEXT_HEIGHT / 2.0,
        )
        box = (x - half[0], y - half[1], x + half[0], y + half[1])
        if any(
            box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]
            for other in self.boxes
        ):
            return False
        self.boxes.append(box)
        return True


def _add_dimension(page, view, kind, references, x, y):
    dimension = page.Document.addObject("TechDraw::DrawViewDimension", "Dimension")
    dimension.Type = kind
    dimension.MeasureType = "Projected"
    dimension.References2D = [(view, reference) for reference in references]
    page.addView(dimension)
    dimension.X = x
    dimension.Y = y
    return dimension


def dimension_view(page, view, piece, silhouette=None):
    """Dimension the view of ``piece`` on its page, once it is projected.

    ``silhouette`` is the piece's ``part_silhouette``, when known already.
    Positions are the view's own: millimetres of paper from its centre,
    Y up. Returns the dimensions made.
    """

    import TechDraw

    scale = float(view.Scale)
    origin, _along, _across = _part_frame(piece)
    shift = view.projectPoint(origin - view.getGeometricCenter())
    outline = [(x + shift.x, y + shift.y) for x, y in piece.outline]
    edges = _numbered(view.getEdgeByIndex)
    vertices = [vertex.Point for vertex in _numbered(view.getVertexByIndex)]

    # The view's edges that are edges of the part's outline, with points
    # along each: its pockets and hidden edges get no dimension.
    outer = {}
    for index, edge in enumerate(edges):
        if edge.Length < 1e-6:
            continue
        points = [(point.x, point.y) for point in edge.discretize(Deflection=0.01)]
        if all(_distance_to_outline(point, outline) < OUTLINE_TOLERANCE for point in points):
            outer[index] = points

    def outward(point, normal):
        """Return ``normal`` or its opposite, whichever leaves the part."""

        probe = (point[0] + normal[0], point[1] + normal[1])
        return normal if not _inside(probe, outline) else (-normal[0], -normal[1])

    texts = _Texts()
    dimensions = []
    every = [
        (x + shift.x, y + shift.y)
        for x, y in (silhouette if silhouette is not None else part_silhouette(piece))
    ]
    low = (min(x for x, _y in every), min(y for _x, y in every))
    high = (max(x for x, _y in every), max(y for _x, y in every))

    # Overall length and width, between the part's extreme points, hidden
    # or not: a vertex of the view where there is one, a point marked on it
    # otherwise.
    def extreme(axis, value):
        point = min(every, key=lambda point: abs(point[axis] - value))
        for index, vertex in enumerate(vertices):
            if math.hypot(vertex.x - point[0], vertex.y - point[1]) < 0.02:
                return f"Vertex{index}", point
        return None, point

    for axis, kind in ((0, "DistanceX"), (1, "DistanceY")):
        (first, first_point), (second, second_point) = (
            extreme(axis, low[axis]),
            extreme(axis, high[axis]),
        )
        middle = (low[axis] + high[axis]) / 2.0 * scale
        x, y = (
            (middle, low[1] * scale - OVERALL_OFFSET)
            if axis == 0
            else (low[0] * scale - OVERALL_OFFSET, middle)
        )
        if first is not None and second is not None:
            dimension = _add_dimension(page, view, kind, [first, second], x, y)
        else:
            # The points are given as the view shows them: scaled.
            dimension = TechDraw.makeDistanceDim(
                view,
                kind,
                FreeCAD.Vector(first_point[0] * scale, first_point[1] * scale, 0.0),
                FreeCAD.Vector(second_point[0] * scale, second_point[1] * scale, 0.0),
            )
            dimension.X = x
            dimension.Y = y
        texts.place(x, y, upright=axis == 1)
        dimensions.append(dimension)

    # Each straight edge's length, along it on the outside, the longest
    # first: one whose text has no room is left to its neighbours.
    lines = sorted(
        (index for index in outer if edges[index].Curve.TypeId == "Part::GeomLine"),
        key=lambda index: -edges[index].Length,
    )
    for index in lines:
        start, end = outer[index][0], outer[index][-1]
        length = math.dist(start, end)
        if length * scale < MINIMUM_DIMENSIONED_EDGE:
            continue
        direction = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
        # The overall dimensions already give an edge spanning the part.
        if any(
            abs(direction[1 - axis]) < 1e-6 and abs(length - (high[axis] - low[axis])) < 0.05
            for axis in (0, 1)
        ):
            continue
        middle = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        normal = outward(middle, (-direction[1], direction[0]))
        x = middle[0] * scale + normal[0] * EDGE_OFFSET
        y = middle[1] * scale + normal[1] * EDGE_OFFSET
        if texts.place(x, y, upright=abs(direction[1]) > abs(direction[0])):
            dimensions.append(_add_dimension(page, view, "Distance", [f"Edge{index}"], x, y))

    # Each arc's radius, once per radius.
    radii = set()
    for index, points in outer.items():
        curve = edges[index].Curve
        if curve.TypeId != "Part::GeomCircle" or round(curve.Radius, 1) in radii:
            continue
        middle = points[len(points) // 2]
        centre = (curve.Center.x, curve.Center.y)
        reach = math.dist(middle, centre)
        if reach < 1e-6:
            continue
        inward = ((centre[0] - middle[0]) / reach, (centre[1] - middle[1]) / reach)
        x = middle[0] * scale + inward[0] * RADIUS_OFFSET
        y = middle[1] * scale + inward[1] * RADIUS_OFFSET
        if texts.place(x, y):
            radii.add(round(curve.Radius, 1))
            dimensions.append(_add_dimension(page, view, "Radius", [f"Edge{index}"], x, y))

    # The angle of each corner between two straight edges that is not square.
    for position, first in enumerate(lines):
        for second in lines[position + 1 :]:
            ends = [outer[first][0], outer[first][-1]], [outer[second][0], outer[second][-1]]
            corner = next(
                (
                    (a, b)
                    for a in (0, 1)
                    for b in (0, 1)
                    if math.dist(ends[0][a], ends[1][b]) < 0.02
                ),
                None,
            )
            if corner is None:
                continue
            apex = ends[0][corner[0]]
            arms = []
            for edge_ends, at in zip(ends, corner):
                far = edge_ends[1 - at]
                reach = math.dist(apex, far)
                arms.append(((far[0] - apex[0]) / reach, (far[1] - apex[1]) / reach))
            cosine = max(-1.0, min(1.0, arms[0][0] * arms[1][0] + arms[0][1] * arms[1][1]))
            angle = math.degrees(math.acos(cosine))
            if min(abs(angle - square) for square in (0.0, 90.0, 180.0)) < SQUARE_TOLERANCE:
                continue
            bisector = (arms[0][0] + arms[1][0], arms[0][1] + arms[1][1])
            reach = math.hypot(*bisector)
            x = apex[0] * scale + bisector[0] / reach * ANGLE_OFFSET
            y = apex[1] * scale + bisector[1] / reach * ANGLE_OFFSET
            if texts.place(x, y):
                dimensions.append(
                    _add_dimension(page, view, "Angle", [f"Edge{first}", f"Edge{second}"], x, y)
                )
    return dimensions


def _notes(piece, size, labels):
    """Return the lines told above a part of ``size``, its length and
    width: how many, and cut from what."""

    # The stock is rounded up to the millimetre, as in the bill of materials.
    sizes = [math.ceil(value - 0.05) for value in (piece.thickness, *size)]
    return [
        translate("BIM", "Quantity: {}").format(len(labels)),
        translate("BIM", "Smallest plank: {} × {} × {} mm (thickness × length × width)").format(
            *sizes
        ),
    ]


def make_stair_drawings(stair, pieces, settings):
    """Make the TechDraw pages of the stair's distinct parts.

    ``pieces`` are the stair's ``flat_pieces``. The pages replace those made
    before, in the stair's drawings group, and are returned in their order;
    none when the stair has no part of the kinds asked for.
    """

    parts = distinct_parts(pieces, settings.kinds)
    remove_stair_drawings(stair)
    if not parts:
        return []
    document = stair.Document
    group = _drawings_group(stair, create=True)
    materials = stair_materials(stair)[1]
    drawn = []
    for number, (piece, labels) in enumerate(parts, start=1):
        silhouette = part_silhouette(piece)
        size = _extent(silhouette)
        template_path, space, reduction = _layout(size, settings)
        _origin, along, across = _part_frame(piece)
        page = document.addObject("TechDraw::DrawPage", f"{stair.Name}_Drawing")
        template = document.addObject("TechDraw::DrawSVGTemplate", f"{stair.Name}_Template")
        template.Template = template_path
        page.Template = template
        page.KeepUpdated = True
        page.Scale = 1.0 / reduction
        title = f"{kind_label(piece.kind)}: {', '.join(labels)}"
        page.Label = title
        # The template's sample texts make way for the part's own.
        fields = dict.fromkeys(template.EditableTexts, "")
        fields.pop("date_of_issue", None)
        for name, text in (
            ("title", title),
            ("document_type", translate("BIM", "Part drawing")),
            ("drawing_number", f"{document.Label} – {stair.Label}"),
            ("sheet_number", f"{number} / {len(parts)}"),
            ("scale", f"1 : {reduction:.3g}"),
            ("part_material", materials.get(piece.kind, "")),
            ("creator", document.CreatedBy),
        ):
            if name in fields:
                fields[name] = text
        for name, text in fields.items():
            template.setEditFieldContent(name, text)

        view = document.addObject("TechDraw::DrawViewPart", f"{stair.Name}_View")
        page.addView(view)
        view.Source = [piece.source]
        # Seen from where its face looks: across the board.
        view.Direction = along.cross(across)
        view.XDirection = along
        view.ScaleType = "Custom"
        view.Scale = 1.0 / reduction
        view.DisplayStyle = "Hidden Edges" if settings.hidden_edges else "Visible Edges"
        view.X = space[0] + space[2] / 2.0
        view.Y = space[1] + (space[3] - NOTES_ROOM) / 2.0

        notes = document.addObject("TechDraw::DrawViewAnnotation", f"{stair.Name}_Notes")
        page.addView(notes)
        notes.Text = _notes(piece, size, labels)
        notes.TextSize = NOTES_TEXT_SIZE
        notes.X = space[0] + space[2] / 2.0
        notes.Y = space[1] + space[3] - NOTES_ROOM / 2.0
        group.addObject(page)
        drawn.append((page, view, piece, silhouette))

    document.recompute()
    _wait_for_projections([view for _page, view, _piece, _silhouette in drawn])
    for page, view, piece, silhouette in drawn:
        dimension_view(page, view, piece, silhouette)
    document.recompute()
    return [page for page, _view, _piece, _silhouette in drawn]
