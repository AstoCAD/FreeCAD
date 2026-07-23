# SPDX-License-Identifier: LGPL-2.1-or-later

"""Draw laid-out stock in a sketch, to move the parts on it by hand.

The planks or panels are drawn one above the other, as construction lines
that stay where they are. Each part is its outline as it lies on its stock,
held together by a Group constraint. The group's handle is a short
construction line inside the part, along its grain, kept level and as long
as it is by two constraints in the virtual space: the part moves as one,
without turning or changing size, when its outline or its handle is
dragged. The parts are left free: the sketch is not fully constrained.
"""

import re

import FreeCAD
import Part
import Sketcher

translate = FreeCAD.Qt.translate

# Left between two stocks, to park parts on the way from one to another.
STOCK_GAP = 300.0
# Left between the stair and the sketch beside it.
STAIR_GAP = 500.0
# Longest handle of a part: a mark of its grain, short enough to keep out
# of the way.
HANDLE_LENGTH = 100.0


def stock_sketch(stair):
    """Return the sketch of the stair's stock layout, ``None`` without one."""

    return stair.Document.getObject(f"{stair.Name}_StockLayout")


def remove_stock_sketch(stair):
    """Remove the sketch of the stair's stock layout, if it has one."""

    sketch = stock_sketch(stair)
    if sketch is not None:
        stair.Document.removeObject(sketch.Name)


def _stair_bounds(stair):
    """Return the box around the stair's members, where the document shows them."""

    bounds = FreeCAD.BoundBox()
    for name in ("StringersGroup", "StepsGroup"):
        group = getattr(stair, name, None)
        for part in group.Group if group else ():
            if part.Shape.isNull():
                continue
            # A part's shape is told in the stair, which may be placed itself.
            outer = part.getGlobalPlacement().multiply(part.Placement.inverse())
            box = part.Shape.BoundBox
            for corner in range(8):
                bounds.add(outer.multVec(box.getPoint(corner)))
    return bounds


def _closed_lines(points):
    return [
        Part.LineSegment(FreeCAD.Vector(x0, y0, 0.0), FreeCAD.Vector(x1, y1, 0.0))
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])
        if abs(x1 - x0) > 1e-9 or abs(y1 - y0) > 1e-9
    ]


def _handle_line(points):
    """Return the ends of a level line inside an outline, near its middle:
    in the widest stretch of the level halfway up it."""

    ys = [y for _x, y in points]
    level = (min(ys) + max(ys)) / 2.0
    crossings = sorted(
        x0 + (level - y0) * (x1 - x0) / (y1 - y0)
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])
        if (y0 > level) != (y1 > level)
    )
    stretches = list(zip(crossings[::2], crossings[1::2]))
    if stretches:
        left, right = max(stretches, key=lambda stretch: stretch[1] - stretch[0])
    else:
        xs = [x for x, _y in points]
        left, right = min(xs), max(xs)
    half = min(HANDLE_LENGTH, (right - left) / 2.0) / 2.0
    middle = (left + right) / 2.0
    return (middle - half, level), (middle + half, level)


def _group_name(label, taken):
    """Return a name for a part's Group constraint, from its label: one a
    constraint may have, that none has yet."""

    name = re.sub(r"\W+", "_", label, flags=re.UNICODE).strip("_") or "Part"
    if name[0].isdigit():
        name = f"Part_{name}"
    candidate = name
    count = 1
    while candidate in taken:
        count += 1
        candidate = f"{name}_{count}"
    taken.add(candidate)
    return candidate


def make_stock_sketch(stair, layouts):
    """Make the sketch of the stair's stock ``layouts``, those of
    ``stair_bom.stair_layout``, replacing the one made before.

    Returns the sketch, ``None`` when nothing is laid out.
    """

    stocks = [stock for found in layouts for stock in found.stocks]
    remove_stock_sketch(stair)
    if not stocks:
        return None
    document = stair.Document
    sketch = document.addObject("Sketcher::SketchObject", f"{stair.Name}_StockLayout")
    sketch.Label = translate("BIM", "{} stock layout").format(stair.Label)
    constraints = []
    hidden = []
    names = set()
    base = 0.0
    for stock in stocks:
        # The stock stays put: its parts are moved over it.
        edges = sketch.addGeometry(
            _closed_lines(
                [
                    (0.0, base),
                    (stock.length, base),
                    (stock.length, base + stock.width),
                    (0.0, base + stock.width),
                ]
            ),
            True,
        )
        constraints.extend(Sketcher.Constraint("Block", edge) for edge in edges)
        for placed in stock.placed:
            outline = [(x, y + base) for x, y in placed.outline]
            lines = _closed_lines(outline)
            if not lines:
                continue
            members = sketch.addGeometry(lines, False)
            start, end = _handle_line(outline)
            handle = sketch.addGeometry(
                Part.LineSegment(FreeCAD.Vector(*start, 0.0), FreeCAD.Vector(*end, 0.0)), True
            )
            elements = [handle, 0]
            for member in members:
                elements.extend((member, 0))
            group = Sketcher.Constraint("Group", elements)
            group.Name = _group_name(getattr(placed.part, "label", ""), names)
            constraints.append(group)
            # A handle that turned or stretched would turn or scale its
            # part: it only slides.
            hidden.extend((len(constraints), len(constraints) + 1))
            constraints.append(Sketcher.Constraint("Horizontal", handle))
            constraints.append(Sketcher.Constraint("Distance", handle, end[0] - start[0]))
        base += stock.width + STOCK_GAP
    sketch.addConstraint(constraints)
    sketch.setVirtualSpace(hidden, True)
    # In front of the stair, on its floor, rather than under it.
    bounds = _stair_bounds(stair)
    if bounds.isValid():
        sketch.Placement = FreeCAD.Placement(
            FreeCAD.Vector(
                bounds.XMin, bounds.YMin - STAIR_GAP - (base - STOCK_GAP), bounds.ZMin
            ),
            FreeCAD.Rotation(),
        )
    sketch.recompute()
    return sketch
