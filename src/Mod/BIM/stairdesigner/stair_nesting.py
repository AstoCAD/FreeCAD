# SPDX-License-Identifier: LGPL-2.1-or-later

"""Lay flat parts out on stock: planks or panels of one material.

Every part is a 2D outline with its grain along X. Parts keep the grain
along the stock's length, so they may only be turned half a turn, and,
those allowed to, turned over: laid on their other face. Tapered
parts, the winder treads and the strips they are glued up from, are first
paired head to tail where the pair takes notably less stock than the two
apart. Parts and pairs are then packed by their rectangles, plank after
plank, keeping a cut spacing between them. Where that takes more stock
than the parts' area asks for, the parts are also nested by their true
shapes, on a grid, which is kept when it saves a stock. Pure geometry: no
document.
"""

import functools
import math
from dataclasses import dataclass, field

# A part filling less of its rectangle than this is worth pairing.
_TAPERED_FILL = 0.8
# A pair is kept when it saves at least this share of the two rectangles.
_PAIR_SAVING = 0.1
# True shapes are nested on a grid of square cells, as wide as the cut
# spacing within these limits, in mm, and never more of them along a stock.
_FINEST_CELL = 2.5
_COARSEST_CELL = 5.0
_MOST_COLUMNS = 1500


def polygon_area(points):
    area = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0


def _bounds(points):
    xs = [x for x, _y in points]
    ys = [y for _x, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def turned(points):
    """Return ``points`` turned half a turn, back in the positive quadrant."""

    x0, y0, x1, y1 = _bounds(points)
    return [(x1 + x0 - x, y1 + y0 - y) for x, y in points]


def flipped(points):
    """Return ``points`` turned over about the grain: mirrored, in place."""

    _x0, y0, _x1, y1 = _bounds(points)
    return [(x, y1 + y0 - y) for x, y in points]


def _lying(points, was_turned, was_flipped):
    """Return ``points`` as a part turned over, turned half a turn, or both, lies."""

    if was_flipped:
        points = flipped(points)
    if was_turned:
        points = turned(points)
    return list(points)


def _x_at(points, y, rightmost):
    """Return the extreme X where the outline crosses the level ``y``."""

    found = None
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        low, high = min(y0, y1), max(y0, y1)
        if y < low - 1e-9 or y > high + 1e-9:
            continue
        if high - low < 1e-12:
            candidates = (x0, x1)
        else:
            t = (y - y0) / (y1 - y0)
            candidates = (x0 + t * (x1 - x0),)
        for x in candidates:
            if found is None or (x > found if rightmost else x < found):
                found = x
    return found


def _slide(left, right, shift_y, spacing):
    """Return how far ``right``, raised by ``shift_y``, must sit from
    ``left`` along X to keep ``spacing`` from it.

    Both outlines are piecewise straight, so the gap between them changes
    slope only at their vertices: checking at every vertex level suffices.
    """

    raised = [(x, y + shift_y) for x, y in right]
    levels = sorted({y for _x, y in left} | {y for _x, y in raised})
    low = max(min(y for _x, y in left), min(y for _x, y in raised))
    high = min(max(y for _x, y in left), max(y for _x, y in raised))
    needed = None
    for y in levels:
        if y < low - 1e-9 or y > high + 1e-9:
            continue
        a = _x_at(left, y, True)
        b = _x_at(raised, y, False)
        if a is None or b is None:
            continue
        if needed is None or a - b > needed:
            needed = a - b
    if needed is None:
        return None
    x = needed + spacing
    # Across a slanted joint the gap along X is wider than the gap square
    # to the cut: move on until the cut itself has its spacing, by what
    # the last move gained: the gap grows steadily with it.
    before = None
    for _attempt in range(16):
        gap = _distance(left, [(px + x, py) for px, py in raised])
        if gap >= spacing - 1e-6:
            break
        gained = None if before is None else (gap - before[1]) / (x - before[0])
        before = (x, gap)
        if gained is not None and gained > 1e-6:
            x += (spacing - gap) / gained * 1.01 + 1e-3
        else:
            x += (spacing - gap) * 1.5 + 1e-3
    return x


def _point_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = dx * dx + dy * dy
    t = 0.0
    if length > 1e-18:
        t = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length))
    return math.hypot(point[0] - start[0] - t * dx, point[1] - start[1] - t * dy)


def _distance(first, second):
    """Return the distance between two outlines that do not cross."""

    edges_a = list(zip(first, first[1:] + first[:1]))
    edges_b = list(zip(second, second[1:] + second[:1]))
    return min(
        min(
            _point_segment(a0, b0, b1),
            _point_segment(a1, b0, b1),
            _point_segment(b0, a0, a1),
            _point_segment(b1, a0, a1),
        )
        for a0, a1 in edges_a
        for b0, b1 in edges_b
    )


@dataclass
class Placed:
    """A part laid on a stock: its outline there, whether it was turned
    half a turn, the move from its own outline's place to the stock, and
    whether it was turned over, its upper face down."""

    part: object
    outline: list
    turned: bool
    source_bounds: tuple
    offset: tuple
    flipped: bool = False

    def map(self, points):
        """Carry points given like the part's own outline onto the stock."""

        x0, y0, x1, y1 = self.source_bounds
        dx, dy = self.offset
        if self.flipped:
            points = [(x, y1 + y0 - y) for x, y in points]
        if self.turned:
            points = [(x1 + x0 - x, y1 + y0 - y) for x, y in points]
        return [(x + dx, y + dy) for x, y in points]


@dataclass
class _Item:
    width: float
    height: float
    members: list  # (part, outline in the item, turned, turned over)


@dataclass
class Stock:
    length: float
    width: float
    placed: list = field(default_factory=list)

    @property
    def used(self):
        """Share of the stock's area the parts cover."""

        area = sum(polygon_area(item.outline) for item in self.placed)
        return area / (self.length * self.width) if self.length * self.width else 0.0


def _single(part, outline):
    x0, y0, x1, y1 = _bounds(outline)
    shifted = [(x - x0, y - y0) for x, y in outline]
    return _Item(x1 - x0, y1 - y0, [(part, shifted, False, False)])


@functools.lru_cache(maxsize=2048)
def _pair_fit(a, b, spacing, flip):
    """Return ``(turn, over, x, y)``: whether the outline ``b`` is turned
    half a turn, whether it is turned over, which it may with ``flip``,
    and where it then sits, to lie tightest beside the outline ``a``.

    Both are given as tuples, from the origin. Sliding one outline along
    the other is the costly part of a layout, and the same parts are laid
    out again and again as materials are tried: the answers are kept.
    """

    def swap(points):
        return [(y, x) for x, y in points]

    a = list(a)
    x0, y0, x1, y1 = _bounds(a)
    a_width, a_height = x1 - x0, y1 - y0
    x0, y0, x1, y1 = _bounds(b)
    b_width, b_height = x1 - x0, y1 - y0
    best = None
    # Its own face up unless the other one fits better.
    for over in (False, True) if flip else (False,):
        for turn in (True, False):
            outline = _lying(b, turn, over)
            # End to end along the grain, or side by side across it: a
            # winder tapers across its nosing, so its turned twin fits
            # along its back.
            candidates = []
            for shift_y in (0.0, a_height - b_height):
                x = _slide(a, outline, shift_y, spacing)
                if x is not None:
                    candidates.append((x, shift_y))
            for shift_x in (0.0, a_width - b_width):
                y = _slide(swap(a), swap(outline), shift_x, spacing)
                if y is not None:
                    candidates.append((shift_x, y))
            if over:
                # Before or below as well. Turned half a turn as a whole,
                # that is one after the other the other way round, which
                # is tried too: unless only one may be turned over.
                for shift_y in (0.0, a_height - b_height):
                    x = _slide(outline, a, -shift_y, spacing)
                    if x is not None:
                        candidates.append((-x, shift_y))
                for shift_x in (0.0, a_width - b_width):
                    y = _slide(swap(outline), swap(a), -shift_x, spacing)
                    if y is not None:
                        candidates.append((shift_x, -y))
            for x, y in candidates:
                x0, y0, x1, y1 = _bounds(a + [(px + x, py + y) for px, py in outline])
                area = (x1 - x0) * (y1 - y0)
                if best is None or area < best[0] - 1e-6:
                    best = (area, turn, over, x, y)
    return None if best is None else best[1:]


def _pair(first, second, spacing, flip):
    """Return the tightest item of ``first`` with ``second`` beside it,
    turned over if that is tighter and it may ``flip``."""

    a = first.members[0][1]
    b = second.members[0][1]
    fit = _pair_fit(tuple(a), tuple(b), spacing, flip)
    if fit is None:
        return None
    turn, over, x, y = fit
    placed_b = [(px + x, py + y) for px, py in _lying(b, turn, over)]
    x0, y0, x1, y1 = _bounds(a + placed_b)
    return _Item(
        x1 - x0,
        y1 - y0,
        [
            (first.members[0][0], [(px - x0, py - y0) for px, py in a], False, False),
            (
                second.members[0][0],
                [(px - x0, py - y0) for px, py in placed_b],
                turn,
                over,
            ),
        ],
    )


def _pair_tapered(items, spacing, length, width, flips):
    """Pair tapered parts head to tail where it saves stock. ``flips`` are
    the ``id`` of the parts that may be turned over."""

    tapered = [
        item
        for item in items
        if polygon_area(item.members[0][1]) < _TAPERED_FILL * item.width * item.height
    ]
    options = []
    for i, first in enumerate(tapered):
        for second in tapered[i + 1 :]:
            for one, two in ((first, second), (second, first)):
                pair = _pair(one, two, spacing, id(two.members[0][0]) in flips)
                if pair is None or pair.width > length + 1e-6 or pair.height > width + 1e-6:
                    continue
                apart = one.width * one.height + two.width * two.height
                saving = apart - pair.width * pair.height
                if saving > _PAIR_SAVING * apart:
                    options.append((saving, id(one), id(two), one, two, pair))
    options.sort(key=lambda option: option[0], reverse=True)
    used = set()
    pairs = []
    for _saving, one_id, two_id, _one, _two, pair in options:
        if one_id in used or two_id in used:
            continue
        used.update((one_id, two_id))
        pairs.append(pair)
    return [item for item in items if id(item) not in used] + pairs


class _MaxRects:
    """Free rectangles of one stock; parts go to the best short-side fit."""

    def __init__(self, length, width):
        self.free = [(0.0, 0.0, length, width)]

    def find(self, w, h):
        best = None
        for x, y, fw, fh in self.free:
            if w <= fw + 1e-6 and h <= fh + 1e-6:
                score = (min(fw - w, fh - h), max(fw - w, fh - h), x, y)
                if best is None or score < best[0]:
                    best = (score, x, y)
        return None if best is None else best[1:]

    def take(self, x, y, w, h):
        result = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                result.append((fx, fy, fw, fh))
                continue
            if x > fx:
                result.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                result.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                result.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                result.append((fx, y + h, fw, fy + fh - y - h))
        result = [rect for rect in result if rect[2] > 1e-6 and rect[3] > 1e-6]
        self.free = [
            rect
            for i, rect in enumerate(result)
            if not any(
                j != i
                and other[0] <= rect[0] + 1e-9
                and other[1] <= rect[1] + 1e-9
                and other[0] + other[2] >= rect[0] + rect[2] - 1e-9
                and other[1] + other[3] >= rect[1] + rect[3] - 1e-9
                and (other != rect or j < i)
                for j, other in enumerate(result)
            )
        ]


def _smear(bits, count):
    """Return ``bits`` with each set bit spread over ``count`` bits upwards."""

    have = 1
    while have * 2 <= count:
        bits |= bits << have
        have *= 2
    if have < count:
        bits |= bits << (count - have)
    return bits


def _covered_cells(outline, cell, snap=True):
    """Return the cells of a square grid an outline touches, row by row.

    The grid starts at the outline's lowest, leftmost corner, or without
    ``snap`` at the origin. Each row is an integer whose bits are its
    cells, the lowest one leftmost. A cell the outline only brushes
    counts: the cells hold all of the part.
    """

    x0, y0, _x1, y1 = _bounds(outline)
    if not snap:
        x0 = y0 = 0.0
    points = [(x - x0, y - y0) for x, y in outline]
    height = y1 - y0
    count = max(int(math.ceil(height / cell - 1e-9)), 1)
    edges = [[] for _row in range(count)]
    levels = [[] for _row in range(count)]
    for start, end in zip(points, points[1:] + points[:1]):
        low, high = min(start[1], end[1]), max(start[1], end[1])
        first = min(max(int(low // cell), 0), count - 1)
        last = min(max(int(high // cell), 0), count - 1)
        for row in range(first, last + 1):
            if high - low > 1e-12:
                edges[row].append((start, end))
            levels[row].extend((start[1], end[1]))
    rows = []
    for row in range(count):
        bottom, top = row * cell, min((row + 1) * cell, height)
        steps = sorted({bottom, top} | {y for y in levels[row] if bottom < y < top})
        bits = 0
        for low, high in zip(steps, steps[1:]):
            if high - low < 1e-9:
                continue
            # Between two levels no edge starts or ends: the outline is a
            # row of trapezoids there, from one crossing edge to the next.
            crossing = []
            for (xa, ya), (xb, yb) in edges[row]:
                if min(ya, yb) <= low + 1e-9 and max(ya, yb) >= high - 1e-9:
                    slope = (xb - xa) / (yb - ya)
                    crossing.append((xa + (low - ya) * slope, xa + (high - ya) * slope))
            crossing.sort(key=lambda ends: ends[0] + ends[1])
            if len(crossing) % 2:
                # Not told apart: all of it, from the first edge to the last.
                crossing = [crossing[0], crossing[-1]]
            for left, right in zip(crossing[::2], crossing[1::2]):
                first = max(int((min(left) + 1e-9) // cell), 0)
                last = max(int((max(right) - 1e-9) // cell), first)
                bits |= ((1 << (last - first + 1)) - 1) << first
        rows.append(bits)
    return rows


@dataclass
class _Mask:
    """A part on the nesting grid, one way up.

    ``rows`` are the cells it covers; ``reach`` gives, for each row from
    ``margin`` rows below it to as many above, the runs of cells no other
    part may enter, as ``(length, shift)``: a run blocks a part placed up
    to ``shift`` columns before a taken cell, and ``length`` positions on.
    """

    width: float
    height: float
    rows: list
    margin: int
    reach: list


@functools.lru_cache(maxsize=1024)
def _mask(outline, cell, margin):
    x0, y0, x1, y1 = _bounds(outline)
    rows = _covered_cells(list(outline), cell)
    # Grown by the margin all around, in a grid of its own: column and row
    # ``margin`` of it are the part's first.
    wide = [_smear(bits, 2 * margin + 1) for bits in rows]
    reach = []
    for index in range(len(rows) + 2 * margin):
        bits = 0
        for row in range(max(index - 2 * margin, 0), min(index, len(rows) - 1) + 1):
            bits |= wide[row]
        runs = []
        low = 0
        while bits:
            skip = (bits & -bits).bit_length() - 1
            bits >>= skip
            low += skip
            length = ((bits + 1) & ~bits).bit_length() - 1
            runs.append((length, low + length - 1 - margin))
            bits >>= length
            low += length
        reach.append(runs)
    return _Mask(x1 - x0, y1 - y0, rows, margin, reach)


class _Sheet:
    """The cells of one stock taken by the parts nested on it so far."""

    def __init__(self, length, width, cell):
        self.length = length
        self.width = width
        self.cell = cell
        # A part's cells may reach one past the stock's last whole one.
        self.rows = [0] * (int(width // cell) + 2)

    def find(self, mask):
        """Return the leftmost, then lowest, ``(column, row)`` where the
        part of ``mask`` keeps clear of those placed; ``None`` without one."""

        columns = int((self.length - mask.width + 1e-6) // self.cell)
        last = int((self.width - mask.height + 1e-6) // self.cell)
        if columns < 0 or last < 0:
            return None
        allowed = (1 << (columns + 1)) - 1
        best = None
        rows = self.rows
        count = len(rows)
        for y in range(last + 1):
            blocked = 0
            for index, runs in enumerate(mask.reach, start=y - mask.margin):
                if index < 0 or index >= count:
                    continue
                taken = rows[index]
                if not taken:
                    continue
                for length, shift in runs:
                    spread = _smear(taken, length)
                    blocked |= spread >> shift if shift >= 0 else spread << -shift
                if not allowed & ~blocked:
                    break
            free = allowed & ~blocked
            if free:
                x = (free & -free).bit_length() - 1
                best = (x, y)
                if x == 0:
                    break
                # Only what lies further left is better.
                allowed = (1 << x) - 1
        return best

    def take(self, mask, x, y):
        for index, bits in enumerate(mask.rows, start=y):
            if index < len(self.rows):
                self.rows[index] |= bits << x


def _grid(spacing, length):
    """Return the cell size of the nesting grid and the margin, in cells,
    that keeps parts the cut ``spacing`` apart."""

    cell = min(max(spacing, _FINEST_CELL), _COARSEST_CELL)
    cell = max(cell, length / _MOST_COLUMNS)
    margin = int(math.ceil(spacing / cell - 1e-9)) if spacing > 1e-9 else 0
    return cell, margin


def _nest_into(sheets, outline, flip, length, width, cell, margin, open_new=True):
    """Nest one outline on the first of ``sheets`` with room for it, one
    way round or the other, turned over or not if it may ``flip``,
    opening a new sheet without one.

    Returns ``(sheet index, x, y, turned, turned over)``, ``None`` without
    room.
    """

    ways = [
        (turn, over, _mask(tuple(_lying(outline, turn, over)), cell, margin))
        for over in ((False, True) if flip else (False,))
        for turn in (False, True)
    ]
    for index, sheet in enumerate(sheets):
        best = None
        for turn, over, mask in ways:
            spot = sheet.find(mask)
            if spot is not None and (best is None or spot < best[0]):
                best = (spot, turn, over, mask)
        if best is not None:
            (x, y), turn, over, mask = best
            sheet.take(mask, x, y)
            return index, x * cell, y * cell, turn, over
    if not open_new:
        return None
    sheet = _Sheet(length, width, cell)
    turn, over, mask = ways[0]
    if sheet.find(mask) is None:
        return None
    sheet.take(mask, 0, 0)
    sheets.append(sheet)
    return len(sheets) - 1, 0.0, 0.0, turn, over


@functools.lru_cache(maxsize=256)
def _nest(outlines, flips, length, width, spacing, at_most):
    """Nest ``outlines`` by their true shapes on stocks ``length`` by
    ``width``, on fewer than ``at_most`` of them. ``flips`` tells of each
    whether it may be turned over.

    Returns where each lies, ``(stock index, x, y, turned, turned over)``
    in their order; ``None`` when it does not take fewer stocks. Each part goes to
    the leftmost, then lowest, place free of the others, on the first
    stock with one: the largest first, then the longest, then the widest.
    The same parts are nested again and again as materials are tried:
    the answers are kept.
    """

    cell, margin = _grid(spacing, length)
    sizes = [_bounds(outline) for outline in outlines]
    areas = [polygon_area(list(outline)) for outline in outlines]
    least = max(int(math.ceil(sum(areas) / (length * width) - 1e-9)), 1)
    best = None
    for key in (
        lambda index: areas[index],
        lambda index: sizes[index][2] - sizes[index][0],
        lambda index: sizes[index][3] - sizes[index][1],
    ):
        sheets = []
        found = {}
        for index in sorted(range(len(outlines)), key=key, reverse=True):
            found[index] = _nest_into(
                sheets, outlines[index], flips[index], length, width, cell, margin
            )
            limit = at_most if best is None else len(best[0])
            if found[index] is None or len(sheets) >= limit:
                break
        else:
            best = (sheets, [found[index] for index in range(len(outlines))])
            if len(sheets) <= least:
                break
    return None if best is None else tuple(best[1])


def _nested(parts, flips, length, width, spacing, at_most):
    """Return the stocks of ``parts`` nested by their true shapes, when
    that takes fewer than ``at_most``; ``None`` otherwise."""

    found = _nest(
        tuple(tuple(outline) for _part, outline in parts),
        tuple(id(part) in flips for part, _outline in parts),
        length,
        width,
        spacing,
        at_most,
    )
    if found is None:
        return None
    stocks = [Stock(length, width) for _index in range(max(spot[0] for spot in found) + 1)]
    for (part, outline), spot in zip(parts, found):
        stocks[spot[0]].placed.append(_placed(part, outline, spot))
    return stocks


def _placed(part, outline, spot):
    _index, x, y, was_turned, was_flipped = spot
    lying = _lying(outline, was_turned, was_flipped)
    x0, y0, _x1, _y1 = _bounds(lying)
    return Placed(
        part,
        [(px - x0 + x, py - y0 + y) for px, py in lying],
        was_turned,
        _bounds(outline),
        (x - x0, y - y0),
        was_flipped,
    )


def _copies(stocks):
    return [Stock(stock.length, stock.width, list(stock.placed)) for stock in stocks]


def _sheet_of(stock, cell):
    """Return the cells the parts laid on ``stock`` take, wherever they lie."""

    sheet = _Sheet(stock.length, stock.width, cell)
    for item in stock.placed:
        for index, bits in enumerate(_covered_cells(item.outline, cell, snap=False)):
            if index < len(sheet.rows):
                sheet.rows[index] |= bits
    return sheet


def _squeeze(stocks, sources, flips, length, width, spacing):
    """Empty the least used of ``stocks`` into the room the others have
    left, by the true shapes of its parts, as long as that works.

    ``sources`` gives each part's own outline by ``id``, ``flips`` the
    ``id`` of those that may be turned over. Returns the stocks
    kept: the parts packed by their rectangles stay as they are, tidy, and
    those of the stocks given up lie in the gaps between them.
    """

    cell, margin = _grid(spacing, length)
    stocks = list(stocks)
    while len(stocks) > 1:
        last = min(reversed(stocks), key=lambda stock: stock.used)
        others = [stock for stock in stocks if stock is not last]
        sheets = [_sheet_of(stock, cell) for stock in others]
        moved = []
        for item in sorted(
            last.placed, key=lambda item: polygon_area(item.outline), reverse=True
        ):
            outline = sources[id(item.part)]
            spot = _nest_into(
                sheets,
                tuple(outline),
                id(item.part) in flips,
                length,
                width,
                cell,
                margin,
                open_new=False,
            )
            if spot is None:
                break
            moved.append((item.part, outline, spot))
        if len(moved) < len(last.placed):
            break
        for part, outline, spot in moved:
            others[spot[0]].placed.append(_placed(part, outline, spot))
        stocks = others
    return stocks


def _fill_nested(stocks, fillers, flips, length, width, spacing):
    """Nest ``fillers`` in the room left on ``stocks``; return those left out."""

    cell, margin = _grid(spacing, length)
    sheets = [_sheet_of(stock, cell) for stock in stocks]
    left = []
    for part, outline in sorted(
        fillers, key=lambda filler: polygon_area(list(filler[1])), reverse=True
    ):
        spot = _nest_into(
            sheets, tuple(outline), id(part) in flips, length, width, cell, margin, open_new=False
        )
        if spot is None:
            left.append(part)
        else:
            stocks[spot[0]].placed.append(_placed(part, outline, spot))
    return left


def lay_out(parts, length, width, spacing=0.0, fillers=(), flip=None):
    """Lay ``parts`` out on as few stocks ``length`` by ``width`` as it can.

    ``parts`` are ``(part, outline)`` with the outline's grain along X.
    ``fillers``, given alike, only fill the room the parts leave on their
    stocks, without a stock of their own, unless there are no parts.
    ``flip`` tells of a part whether it may be turned over, laid on its
    other face; none may without it. Parts are only turned over where
    that saves a stock, or finds room for more of the fillers.
    Returns ``(stocks, unplaced)``: the ``Stock`` list, each with its
    ``Placed`` parts in stock coordinates, and the parts too large for it
    or the fillers finding no room.

    Parts are packed by their rectangles. Where that takes more stocks
    than their area asks for, they are also nested by their true shapes,
    which is kept when it saves a stock.
    """

    parts = list(parts)
    fillers = list(fillers)
    if not parts:
        parts, fillers = fillers, []
    plain = _lay_out(parts, length, width, spacing, fillers, frozenset())
    flips = {id(part) for part, _outline in parts + fillers if flip is not None and flip(part)}
    if not flips:
        return plain
    over = _lay_out(parts, length, width, spacing, fillers, flips)
    return over if [len(found) for found in over] < [len(found) for found in plain] else plain


def _lay_out(parts, length, width, spacing, fillers, flips):
    """Lay parts out as ``lay_out`` tells, those whose ``id`` is among
    ``flips`` turned over wherever they fit better so."""

    sources = {id(part): outline for part, outline in parts + fillers}
    unplaced = []

    def fitting(pieces):
        """Return the pieces the stock can hold; the others are unplaced."""

        kept = []
        for part, outline in pieces:
            if len(outline) < 3:
                continue
            x0, y0, x1, y1 = _bounds(outline)
            if x1 - x0 > length + 1e-6 or y1 - y0 > width + 1e-6:
                unplaced.append(part)
            else:
                kept.append((part, outline))
        return kept

    def items_of(pieces):
        return _pair_tapered(
            [_single(part, outline) for part, outline in pieces], spacing, length, width, flips
        )

    parts = fitting(parts)
    items = items_of(parts)
    best = None
    # No order suits every stock: widest first fills panels, longest first
    # fills planks. Keep the one needing the fewest stocks, then leaving
    # the most of the last one free.
    for key in (
        lambda item: (round(item.height, 3), round(item.width, 3)),
        lambda item: (round(item.width, 3), round(item.height, 3)),
        lambda item: round(item.width * item.height, 3),
    ):
        stocks, bins, _left = _pack(
            sorted(items, key=key, reverse=True), length, width, spacing, sources
        )
        score = (len(stocks), stocks[-1].used if stocks else 0.0)
        if best is None or score < best[0]:
            best = (score, stocks, bins)
    stocks, bins = (best[1], best[2]) if best else ([], [])
    fillers = fitting(fillers)
    # Rectangles waste the room around tapered and curved parts. Where
    # the parts' area would go on fewer stocks, their shapes are tried.
    area = sum(polygon_area(outline) for _part, outline in parts)
    least = max(int(math.ceil(area / (length * width) - 1e-9)), 1)
    shaped = None
    if len(stocks) > least:
        shaped = _squeeze(_copies(stocks), sources, flips, length, width, spacing)
        if len(shaped) > least:
            nested = _nested(parts, flips, length, width, spacing, len(shaped))
            if nested is not None:
                shaped = nested
    if shaped is not None and len(shaped) < len(stocks):
        unplaced.extend(_fill_nested(shaped, fillers, flips, length, width, spacing))
        return shaped, unplaced
    if fillers:
        filler_items = items_of(fillers)
        filler_items.sort(key=lambda item: item.width * item.height, reverse=True)
        stocks, bins, left = _pack(
            filler_items, length, width, spacing, sources, stocks, bins, open_new=False
        )
        unplaced.extend(part for item in left for part, *_lying_how in item.members)
    return stocks, unplaced


def _pack(items, length, width, spacing, sources, stocks=None, bins=None, open_new=True):
    stocks = list(stocks or [])
    bins = list(bins or [])
    left = []
    for item in items:
        # The spacing goes between parts, not along the stock's edges.
        w, h = item.width + spacing, item.height + spacing
        spot = None
        for stock, free in zip(stocks, bins):
            spot = free.find(w, h)
            if spot is not None:
                break
        if spot is None:
            if not open_new:
                left.append(item)
                continue
            stock = Stock(length, width)
            free = _MaxRects(length + spacing, width + spacing)
            spot = free.find(w, h)
            stocks.append(stock)
            bins.append(free)
        x, y = spot
        free.take(x, y, w, h)
        for part, outline, was_turned, was_flipped in item.members:
            final = [(px + x, py + y) for px, py in outline]
            source = sources[id(part)]
            start = _lying(source, was_turned, was_flipped)[0]
            stock.placed.append(
                Placed(
                    part,
                    final,
                    was_turned,
                    _bounds(source),
                    (final[0][0] - start[0], final[0][1] - start[1]),
                    was_flipped,
                )
            )
    return stocks, bins, left
