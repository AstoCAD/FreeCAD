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

"""Time profiles shared by prescribed motions and applied wrenches.

Profiles compile to OndselSolver expressions, with exact polynomial integration
and differentiation. The editor evaluates the same curves as the solver. Units
in the stored definition are explicit; compiled motion uses mm/rad/s, loads N/Nmm.
"""

import ast
import bisect
import json
import math
from contextlib import contextmanager


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Profile values must be finite.")
    return value


def polynomial(coefficients, x):
    value = 0.0
    for c in reversed(coefficients):
        value = value * x + c
    return value


def derivative(c):
    return [i * c[i] for i in range(1, len(c))] or [0.0]


def integral(c, initial=0.0):
    return [initial] + [v / (i + 1) for i, v in enumerate(c)]


# Small, deliberately restricted symbolic language. Never evaluate Python code
# from a document or CSV. Unsupported antiderivatives are reported to the user.
def op(kind, *args):
    if kind == "+":
        if args[0] == 0: return args[1]
        if args[1] == 0: return args[0]
    if kind == "*":
        if 0 in args: return 0.0
        if args[0] == 1: return args[1]
        if args[1] == 1: return args[0]
    if kind == "^":
        if args[1] == 0: return 1.0
        if args[1] == 1: return args[0]
    if all(isinstance(a, (int, float)) for a in args):
        return value((kind, *args), 0)
    return (kind, *args)


def expression(text):
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except SyntaxError as error:
        raise ValueError("Invalid expression syntax.") from error
    if len(list(ast.walk(tree))) > 160:
        raise ValueError("Expression is too complex.")

    def convert(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return number(node.value)
        if isinstance(node, ast.Name):
            if node.id in ("time", "t"): return "time"
            if node.id == "initialValue": return "initialValue"
            if node.id == "pi": return math.pi
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return op("*", -1.0 if isinstance(node.op, ast.USub) else 1.0, convert(node.operand))
        if isinstance(node, ast.BinOp):
            a, b = convert(node.left), convert(node.right)
            if isinstance(node.op, ast.Add): return op("+", a, b)
            if isinstance(node.op, ast.Sub): return op("+", a, op("*", -1.0, b))
            if isinstance(node.op, ast.Mult): return op("*", a, b)
            if isinstance(node.op, ast.Div): return op("*", a, op("^", b, -1.0))
            if isinstance(node.op, ast.Pow) and isinstance(b, (int, float)) and abs(b) <= 32:
                return op("^", a, b)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("sin", "cos", "exp") and len(node.args) == 1 and not node.keywords):
            return op(node.func.id, convert(node.args[0]))
        raise ValueError("Use numbers, t, pi, initialValue, + - * / ^, sin, cos and exp.")
    return convert(tree.body)


def value(expr, t, initial=0.0):
    if isinstance(expr, (int, float)): return expr
    if expr == "time": return t
    if expr == "initialValue": return initial
    kind, *args = expr
    args = [value(a, t, initial) for a in args]
    if kind == "+": result = args[0] + args[1]
    elif kind == "*": result = args[0] * args[1]
    elif kind == "^": result = args[0] ** args[1]
    else: result = getattr(math, kind)(args[0])
    return number(result)


def diff(expr):
    if isinstance(expr, (int, float)) or expr == "initialValue": return 0.0
    if expr == "time": return 1.0
    kind, a, *rest = expr
    if kind == "+": return op("+", diff(a), diff(rest[0]))
    if kind == "*": return op("+", op("*", diff(a), rest[0]), op("*", a, diff(rest[0])))
    if kind == "^": return op("*", op("*", rest[0], op("^", a, rest[0] - 1)), diff(a))
    outer = {"sin": lambda: op("cos", a), "cos": lambda: op("*", -1.0, op("sin", a)),
             "exp": lambda: op("exp", a)}[kind]()
    return op("*", outer, diff(a))


def antidiff(expr):
    if diff(expr) == 0: return op("*", expr, "time")
    if expr == "time": return op("*", 0.5, op("^", "time", 2.0))
    kind, a, *rest = expr
    if kind == "+": return op("+", antidiff(a), antidiff(rest[0]))
    if kind == "*":
        if diff(a) == 0: return op("*", a, antidiff(rest[0]))
        if diff(rest[0]) == 0: return op("*", rest[0], antidiff(a))
        coefficients = polynomial_coefficients(expr)
        if coefficients is not None:
            return polynomial_expression(integral(coefficients), 0)
    slope = diff(a)
    if isinstance(slope, (int, float)) and slope != 0:
        if kind == "^" and rest[0] != -1:
            return op("*", 1 / (slope * (rest[0] + 1)), op("^", a, rest[0] + 1))
        if kind in ("sin", "cos", "exp"):
            return op("*", (-1 if kind == "sin" else 1) / slope,
                      op({"sin": "cos", "cos": "sin", "exp": "exp"}[kind], a))
    raise ValueError("This expression cannot be integrated analytically. Use a position expression, or Segments/Data points for velocity or acceleration.")


def polynomial_coefficients(expr):
    """Recognize polynomial products such as t*t without a symbolic dependency."""
    if isinstance(expr, (int, float)):
        return [expr]
    if expr == "time":
        return [0, 1]
    if not isinstance(expr, tuple) or expr[0] not in ("+", "*", "^"):
        return None
    kind, first, second = expr
    a = polynomial_coefficients(first)
    if kind == "^":
        if not isinstance(second, (int, float)) or second < 0 or second != int(second):
            return None
        if a is None:
            return None
        result = [1]
        for _ in range(int(second)):
            result = multiply_polynomials(result, a)
        return result
    b = polynomial_coefficients(second)
    if a is None or b is None:
        return None
    if kind == "*":
        return multiply_polynomials(a, b)
    return [(a[i] if i < len(a) else 0) + (b[i] if i < len(b) else 0)
            for i in range(max(len(a), len(b)))]


def multiply_polynomials(a, b):
    if len(a) + len(b) > 258:
        raise ValueError("Polynomial degree is too high.")
    result = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            result[i+j] += x*y
    return result


def text(expr):
    if isinstance(expr, (int, float)): return format(expr, ".17g")
    if isinstance(expr, str): return expr
    kind, *args = expr
    if kind == "exp": return "(" + format(math.e, ".17g") + "^(" + text(args[0]) + "))"
    if kind in ("sin", "cos"): return kind + "(" + text(args[0]) + ")"
    return "(" + text(args[0]) + kind + text(args[1]) + ")"


def polynomial_expression(c, origin):
    x = op("+", "time", -origin)
    result = 0.0
    for power, coefficient in enumerate(c):
        result = op("+", result, op("*", coefficient, op("^", x, power)))
    return result


def scale(spec):
    units = {"mm": 1.0, "m": 1000.0, "rad": 1.0, "deg": math.pi / 180,
             "N": 1.0, "N mm": 1.0, "N m": 1000.0}
    if spec["unit"] not in units:
        raise ValueError("Unsupported profile unit.")
    return units[spec["unit"]]


def defaults(unit="mm", mode="Segments"):
    return {"version": 1, "mode": mode, "unit": unit, "quantity": "Position",
            "start": 0.0, "end": 1.0, "initial": 0.0, "initial_position": 0.0,
            "initial_velocity": 0.0, "outside": "Hold endpoint", "expression": "sin(2*pi*t)",
            "segments": [[1.0, 1.0, "Smooth"]], "points": [[0.0, 0.0], [1.0, 1.0]],
            "interpolation": "Cubic spline"}


def intervals(spec):
    """Return finite polynomial intervals (start, end, coefficients in t-start)."""
    start = number(spec["start"])
    initial = number(spec["initial"])
    rows = spec["segments"] if spec["mode"] == "Segments" else spec["points"]
    if len(rows) > 2000:
        raise ValueError("Profiles are limited to 2000 rows.")
    if spec["mode"] == "Segments":
        result = []
        for duration, end_value, transition in spec["segments"]:
            duration, end_value = number(duration), number(end_value)
            if duration <= 0: raise ValueError("Segment durations must be positive.")
            delta = end_value - initial
            if transition == "Hold":
                if delta != 0: raise ValueError("A Hold segment must end at its starting value.")
                c = [initial]
            elif transition == "Linear": c = [initial, delta / duration]
            elif transition == "Smooth":
                c = [initial, 0, 0, 10 * delta / duration**3, -15 * delta / duration**4, 6 * delta / duration**5]
            else: raise ValueError("Unknown segment transition.")
            result.append((start, start + duration, c))
            start, initial = start + duration, end_value
        if not result: raise ValueError("Add at least one segment.")
        return result
    points = [[number(x), number(y)] for x, y in spec["points"]]
    if len(points) < 2: raise ValueError("Provide at least two data points.")
    x, y = map(list, zip(*points))
    h = [b - a for a, b in zip(x, x[1:])]
    if any(d <= 0 for d in h): raise ValueError("Data times must be strictly increasing, with no duplicates.")
    slopes = [(b - a) / d for a, b, d in zip(y, y[1:], h)]
    if spec["interpolation"] == "Linear":
        return [(x[i], x[i+1], [y[i], slopes[i]]) for i in range(len(h))]
    if spec["interpolation"] != "Cubic spline": raise ValueError("Unknown interpolation.")
    # Natural cubic spline: tridiagonal solve for nodal second derivatives.
    n = len(x)
    diagonal, rhs = [1.0] * n, [0.0] * n
    upper = [0.0] * n
    for i in range(1, n-1):
        lower = h[i-1]
        diagonal[i] = 2 * (h[i-1] + h[i]) - lower * upper[i-1] / diagonal[i-1]
        rhs[i] = 6 * (slopes[i] - slopes[i-1]) - lower * rhs[i-1] / diagonal[i-1]
        upper[i] = h[i]
    second = [0.0] * n
    for i in range(n-2, 0, -1): second[i] = (rhs[i] - upper[i] * second[i+1]) / diagonal[i]
    return [(x[i], x[i+1], [y[i], slopes[i] - h[i]*(2*second[i]+second[i+1])/6,
             second[i]/2, (second[i+1]-second[i])/(6*h[i])]) for i in range(n-1)]


class Profile:
    def __init__(self, spec, run_start=None, run_end=None):
        self.spec = spec
        self.warnings = []
        if spec.get("version") != 1: raise ValueError("Unsupported profile version.")
        mode, quantity = spec["mode"], spec["quantity"]
        if mode not in ("Constant", "Segments", "Data points", "Expression"):
            raise ValueError("Unknown profile definition.")
        if quantity not in ("Position", "Velocity", "Acceleration", "Magnitude"):
            raise ValueError("Unknown prescribed quantity.")
        if spec["outside"] not in ("Hold endpoint", "Repeat", "Require coverage"):
            raise ValueError("Unknown out-of-range behavior.")
        if spec["unit"] in ("N", "N mm", "N m") and quantity != "Magnitude":
            raise ValueError("Loads must prescribe magnitude.")
        factor = scale(spec)
        start, end = number(spec["start"]), number(spec["end"])
        if mode in ("Segments", "Data points"):
            parts = intervals(spec)
            start, end = parts[0][0], parts[-1][1]
        else:
            if end <= start: raise ValueError("End time must be after start time.")
            expr = (substitute(expression(spec["expression"]), "time", number(spec["initial_position"]))
                    if mode == "Expression" else number(spec["initial"]))
            parts = [(start, end, expr)]
        self.start, self.end = start, end
        low = min(start, number(run_start) if run_start is not None else start)
        high = max(end, number(run_end) if run_end is not None else end)
        outside = spec["outside"]
        if outside == "Require coverage" and (low < start - 1e-12 or high > end + 1e-12):
            raise ValueError("The profile must cover the complete simulation time range.")
        expressions = [(a, b, polynomial_expression(c, a) if isinstance(c, list) else c) for a, b, c in parts]
        if outside == "Repeat":
            duration = end-start
            first = math.floor((low-start)/duration)
            last = max(0, math.ceil((high-start)/duration)-1)
            if (last-first+1)*len(parts) > 2000: raise ValueError("Too many repeated profile segments (limit 2000).")
            tiled = []
            for cycle in range(first, last+1):
                shift = cycle*duration
                for a, b, expr in expressions:
                    tiled.append((a+shift, b+shift, substitute(expr, op("+", "time", -shift))))
            expressions = tiled
            if any(abs(value(diff_n(expressions[0][2], n), expressions[0][0], spec["initial_position"])
                       - value(diff_n(expressions[len(parts)-1][2], n), expressions[len(parts)-1][1], spec["initial_position"])) > 1e-7 for n in range(3 if quantity == "Position" else 1)):
                self.warnings.append("Repeated endpoints do not join smoothly; motion derivatives may be discontinuous.")
        self.expressions = []
        preview_initial = number(spec["initial_position"])
        # Clamp the prescribed quantity, not necessarily displacement. Holding
        # a prescribed velocity means continued travel, not stopping the motor.
        left = value(expressions[0][2], expressions[0][0], preview_initial)
        right = value(expressions[-1][2], expressions[-1][1], preview_initial)
        expressions = [(-math.inf, expressions[0][0], left)] + expressions + [(expressions[-1][1], math.inf, right)]
        order = {"Position": 0, "Magnitude": 0, "Velocity": 1, "Acceleration": 2}[quantity]
        for integration in range(order):
            integrated = []
            previous = None
            for a, b, expr in expressions:
                primitive = antidiff(expr)
                if previous is not None:
                    offset = value(previous, a, preview_initial) - value(primitive, a, preview_initial)
                    primitive = op("+", primitive, offset)
                integrated.append((a, b, primitive))
                previous = primitive
            anchor = next(expr for a, b, expr in integrated if a <= start < b)
            target = number(spec["initial_velocity"] if order == 2 and integration == 0 else spec["initial_position"])
            offset = target - value(anchor, start, preview_initial)
            expressions = [(a, b, op("+", expr, offset)) for a, b, expr in integrated]
        self.expressions = [(a, b, op("*", factor, expr)) for a, b, expr in expressions]
        self.transitions = [b for a, b, expr in self.expressions[:-1]]
        self.derivatives = [[diff_n(expr, n) for a, b, expr in self.expressions] for n in range(4)]
        self.initial = preview_initial
        if mode == "Data points" and spec["interpolation"] == "Cubic spline":
            self.warnings.append("Cubic splines can overshoot input values. Check the preview and endpoint slopes.")
        if quantity == "Position" and (mode == "Data points" and spec["interpolation"] == "Linear"
                                      or mode == "Segments" and any(s[2] == "Linear" for s in spec["segments"])):
            self.warnings.append("Linear position segments can introduce instantaneous velocity changes at joins.")
        # Catch invalid domains before a formula reaches the native parser.
        for i in range(101): self.sample(start + (end-start)*i/100)

    def sample(self, time, derivative_order=0):
        index = bisect.bisect_right(self.transitions, time)
        return value(self.derivatives[derivative_order][index], time, self.initial)

    def formula(self):
        funcs = ",".join(text(expr) for a, b, expr in self.expressions)
        times = ",".join(format(t, ".17g") for t in self.transitions)
        return f"piecewise(time,functions({funcs}),transitions({times}))"


def diff_n(expr, order):
    for _ in range(order): expr = diff(expr)
    return expr


def substitute(expr, time, initial=None):
    if expr == "time": return time
    if expr == "initialValue" and initial is not None: return initial
    if not isinstance(expr, tuple): return expr
    return op(expr[0], *(substitute(a, time, initial) for a in expr[1:]))


def ensure_properties(obj):
    if "ProfileData" not in obj.PropertiesList:
        obj.addProperty("App::PropertyString", "ProfileData", "Profile", "Versioned motor/load profile definition")
        obj.setEditorMode("ProfileData", 2)


def assign(obj, spec):
    """Update both authoritative definition and legacy-compatible solver formula."""
    validate_for_object(obj, spec)
    profile = Profile(spec)
    ensure_properties(obj)
    obj.ProfileData = json.dumps(spec, allow_nan=False, separators=(",", ":"))
    obj.Proxy._updating_profile = True
    try:
        obj.Formula = profile.formula()
    finally:
        obj.Proxy._updating_profile = False


def prepare(study, inputs):
    """Expand repeats for this study without invalidating other global-input users."""
    start = float(study.aTimeStart if hasattr(study, "aTimeStart") else study.StartTime)
    end = float(study.bTimeEnd if hasattr(study, "bTimeEnd") else study.EndTime)
    event_targets = {
        target for event in inputs
        if getattr(event, "IsSimulationEvent", False) and not event.Suppressed
        for target in event.Targets
    }
    for obj in inputs:
        if (getattr(obj, "Suppressed", False) and obj not in event_targets) or not getattr(obj, "ProfileData", ""):
            continue
        if hasattr(obj, "LoadType") and obj.LoadType not in ("Force", "Torque"):
            continue
        spec = json.loads(obj.ProfileData)
        validate_for_object(obj, spec)
        profile = Profile(spec, start, end)
        obj.Proxy._updating_profile = True
        try:
            obj.Formula = profile.formula()
        finally:
            obj.Proxy._updating_profile = False


@contextmanager
def prepared(study, inputs):
    """Scope legacy solver formulas to this run, including event-reachable inputs."""
    originals = [(obj, obj.Formula) for obj in inputs if hasattr(obj, "Formula")]
    try:
        prepare(study, inputs)
        yield
    finally:
        for obj, formula in originals:
            if obj.Formula == formula:
                continue
            obj.Proxy._updating_profile = True
            try:
                obj.Formula = formula
                obj.purgeTouched()
            finally:
                obj.Proxy._updating_profile = False


def validate_for_object(obj, spec):
    if hasattr(obj, "MotionType"):
        allowed = ("rad", "deg") if obj.MotionType == "Angular" else ("mm", "m")
        quantities = ("Position", "Velocity", "Acceleration")
    else:
        allowed = ("N",) if obj.LoadType == "Force" else ("N mm", "N m")
        quantities = ("Magnitude",)
    if spec["unit"] not in allowed or spec["quantity"] not in quantities:
        raise ValueError("Profile units or prescribed quantity do not match this motion/load type.")
