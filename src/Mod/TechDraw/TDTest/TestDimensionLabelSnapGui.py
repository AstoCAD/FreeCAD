# SPDX-License-Identifier: LGPL-2.1-or-later
"""Dimension labels snap on radius, diameter and angle dimensions.

https://github.com/FreeCAD/FreeCAD/issues/13831

The label is moved the way a drag moves it (QGraphicsItem.setPos runs the label's
itemChange and its snapping), and the result is read back from the page scene.
"""

import math
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part
    import TechDraw  # noqa: F401
    import TechDrawGui  # noqa: F401
    from PySide import QtCore, QtWidgets

    try:
        import shiboken6 as shiboken
    except ImportError:
        import shiboken2 as shiboken

    # TechDrawGui::UserType values (QGIUserTypes.h)
    DATUM_LABEL_TYPE = QtWidgets.QGraphicsItem.UserType + 15
    DIM_LINES_TYPE = QtWidgets.QGraphicsItem.UserType + 17
    DIMENSION_TYPE = QtWidgets.QGraphicsItem.UserType + 39

TDTEST = Path(__file__).resolve().parent
RADIUS = 10.0
VERTEX = App.Vector(40, 0, 0)
LEG_ANGLES = (0.0, 40.0, 100.0)


@unittest.skipUnless(App.GuiUp, "Label snapping requires the GUI")
class TestDimensionLabelSnapGui(unittest.TestCase):
    def setUp(self):
        self.doc = None
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("TechDrawWorkbench")
        Gui.Selection.clearSelection()
        self.rez = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Rez").GetFloat(
            "Resolution", 10.0
        )
        # default cascade spacing 7 mm and SnapDimensionsTextFactor 0.4, in scene units
        dimensions = App.ParamGet("User parameter:BaseApp/Preferences/Mod/TechDraw/Dimensions")
        self.spacing = 7.0 * self.rez
        self.text_catch = self.spacing * dimensions.GetFloat("SnapDimensionsTextFactor", 0.4)
        self.chain_catch = self.spacing * dimensions.GetFloat("SnapDimensionsChainFactor", 0.2)

        self.doc = App.newDocument("DimensionLabelSnap")
        edges = [Part.makeCircle(RADIUS)]
        for degrees in LEG_ANGLES:
            angle = math.radians(degrees)
            end = VERTEX + App.Vector(math.cos(angle), math.sin(angle), 0) * 30
            edges.append(Part.makeLine(VERTEX, end))
        edges.append(Part.makeLine(App.Vector(-20, -30, 0), App.Vector(60, -30, 0)))
        self.source = self.doc.addObject("Part::Feature", "Source")
        self.source.Shape = Part.makeCompound(edges)
        self.page = self.doc.addObject("TechDraw::DrawPage", "Page")
        template = self.doc.addObject("TechDraw::DrawSVGTemplate", "Template")
        template.Template = str(TDTEST / "TestTemplate.svg")
        self.page.Template = template
        self.view = self.doc.addObject("TechDraw::DrawViewPart", "View")
        self.page.addView(self.view)
        self.view.Source = [self.source]
        self.view.Direction = App.Vector(0, 0, 1)
        self.view.XDirection = App.Vector(1, 0, 0)
        self.view.ScaleType = "Custom"
        self.view.Scale = 1
        self.view.X, self.view.Y = 150, 150
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: len(self.view.getVisibleEdges()) == 5))
        self.page.ViewObject.show()
        self._pump(100)
        self._classify_edges()

    # helpers --------------------------------------------------------------

    @staticmethod
    def _pump(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()
        Gui.updateGui()

    def _wait(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._pump()
        return bool(predicate())

    def _classify_edges(self):
        """Find the circle, the horizontal line and the three legs among the view edges."""
        self.circle = None
        self.horizontal = None
        lines = {}
        for index in range(len(self.view.getVisibleEdges())):
            name = "Edge{}".format(index)
            edge = self.view.getEdgeBySelection(name)
            if isinstance(edge.Curve, Part.Circle):
                self.circle = name
            elif abs(edge.Length - 80) < 1e-6:
                self.horizontal = name
            else:
                lines[name] = (edge.Vertexes[0].Point, edge.Vertexes[-1].Point)
        self.assertIsNotNone(self.circle)
        self.assertIsNotNone(self.horizontal)
        self.assertEqual(len(lines), 3)
        ends = [point for pair in lines.values() for point in pair]
        vertex = max(ends, key=lambda p: sum((p - q).Length < 1e-6 for q in ends))
        self.legs = {}
        for name, (start, end) in lines.items():
            other = end if (start - vertex).Length < 1e-6 else start
            found = math.degrees(math.atan2(other.y - vertex.y, other.x - vertex.x))
            # the projection may mirror Y, so match the angle up to its sign
            degrees = min(LEG_ANGLES, key=lambda d: min(abs(found - d), abs(found + d)))
            self.legs[degrees] = name
        self.assertEqual(sorted(self.legs), sorted(LEG_ANGLES))

    def _dimension(self, name, kind, references, style):
        dim = self.doc.addObject("TechDraw::DrawViewDimension", name)
        dim.Type = kind
        dim.MeasureType = "Projected"
        dim.References2D = references
        self.page.addView(dim)
        dim.ViewObject.StandardAndStyle = style
        self.doc.recompute()
        self.assertTrue(self._wait(lambda: self._label(dim) is not None))
        self._pump(100)
        return dim

    def _place(self, dim, center):
        """Place the label center at center (parent coordinates) through X and Y."""
        dim.X = center.x / self.rez
        dim.Y = -center.y / self.rez
        self.doc.recompute()
        self._pump(100)
        # the label must not have snapped while it was placed
        self._assert_close(self._center(dim), center, 0.5)

    def _dimension_item(self, dim):
        """The QGIViewDimension of dim, as listed by its scene."""
        # Only wrappers handed out by QGraphicsScene.items() are used for the dimension
        # item: a wrapper made by parentItem() was seen to destroy the item with it.
        for widget in Gui.getMainWindow().findChildren(QtWidgets.QGraphicsView):
            scene = widget.scene()
            if scene is None:
                continue
            for item in scene.items():
                if item.type() == DIMENSION_TYPE and item.data(1) == dim.Name:
                    return item
        return None

    def _label(self, dim):
        """The QGIDatumLabel holding the value of dim, as a QGraphicsObject."""
        item = self._dimension_item(dim)
        if item is None:
            return None
        # the value label is created before the area leader point label
        for child in item.childItems():
            if child.type() == DATUM_LABEL_TYPE:
                # the label starts with its QObject, use the QGraphicsObject wrapper
                return child.toGraphicsObject()
        return None

    def _dim_lines(self, dim):
        parent = self._dimension_item(dim)
        for item in parent.childItems():
            if item.type() == DIM_LINES_TYPE:
                pointer = shiboken.getCppPointer(item)[0]
                return parent, shiboken.wrapInstance(pointer, QtWidgets.QGraphicsPathItem)
        self.fail("No dimension lines for " + dim.Name)

    def _center(self, dim):
        """Label center in its parent's coordinates (Y down, scene units)."""
        label = self._label(dim)
        point = label.pos() + label.transformOriginPoint()
        return App.Vector(point.x(), point.y(), 0)

    def _move(self, dim, center):
        label = self._label(dim)
        point = QtCore.QPointF(center.x, center.y) - label.transformOriginPoint()
        label.setPos(point)
        self._pump(50)

    def _gui(self, vector):
        return App.Vector(vector.x * self.rez, vector.y * self.rez, 0)

    def _line_points(self, dim):
        parent, lines = self._dim_lines(dim)
        path = lines.path()
        points = []
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            mapped = lines.mapToItem(parent, QtCore.QPointF(element.x, element.y))
            points.append(App.Vector(mapped.x(), mapped.y(), 0))
        return points

    def _line_direction(self, dim, center):
        """Direction of the drawn radius or diameter line, checked to pass through center."""
        points = self._line_points(dim)
        far = max(points, key=lambda point: (point - center).Length)
        direction = far - center
        self.assertGreater(direction.Length, RADIUS * self.rez * 0.9)
        direction.normalize()
        for point in points:
            offset = point - center
            self.assertLess(abs(offset.x * direction.y - offset.y * direction.x), 0.5,
                            "The dimension line must run through the center")
        return direction

    def _assert_close(self, actual, expected, tolerance=0.05):
        self.assertLess((actual - expected).Length, tolerance,
                        "{} is not at {}".format(actual, expected))

    def _arc_center(self, dim):
        return self._gui(dim.getArcPoints()[0])

    def _radial(self, kind, style, name):
        dim = self._dimension(name, kind, [(self.view, self.circle)], style)
        center = self._arc_center(dim)
        angle = math.radians(-30)
        start = center + App.Vector(math.cos(angle), math.sin(angle), 0) * (2 * RADIUS * self.rez)
        self._place(dim, start)
        return dim, center, start

    # radius and diameter ------------------------------------------------------

    def test_radius_label_snaps_to_middle_asme(self):
        dim, center, start = self._radial("Radius", "ASME Inlined", "SnapRadius")
        direction = self._line_direction(dim, center)
        normal = App.Vector(-direction.y, direction.x, 0)
        target = center + direction * (RADIUS * self.rez * 0.5)
        self._move(dim, target + direction * 4 + normal * 6)
        self._assert_close(self._center(dim), target)
        self._assert_close(self._line_direction(dim, center), direction, 1e-3)

    def test_radius_label_snaps_to_middle_iso(self):
        dim, center, start = self._radial("Radius", "ISO Oriented", "SnapRadius")
        direction = self._line_direction(dim, center)
        normal = App.Vector(-direction.y, direction.x, 0)
        side = 1.0 if (start - center).dot(normal) >= 0 else -1.0
        beside = abs((start - center).dot(normal))
        self.assertGreater(beside, 1.0)
        mid = center + direction * (RADIUS * self.rez * 0.5)
        self._move(dim, mid + direction * 5 + normal * (side * beside + 4))
        snapped = self._center(dim)
        drawn = self._line_direction(dim, center)
        self._assert_close(drawn, direction, 1e-3)
        self.assertAlmostEqual((snapped - center).dot(drawn), RADIUS * self.rez * 0.5, delta=0.05)
        self.assertAlmostEqual((snapped - center).dot(normal) * side, beside, delta=0.5)

    def _assert_next_to_center(self, dim, offset):
        """A snapped diameter label is off the center by a small part of its height."""
        self.assertGreater(abs(offset), 0.1)
        self.assertLess(abs(offset), 0.1 * self._label(dim).boundingRect().height())

    def _assert_drawn_alike(self, dim, center, direction):
        """A new dimension with the same label position draws the same line, as the
        snapped one does after the document is reopened."""
        twin = self._dimension(dim.Name + "Twin", dim.Type, [(self.view, self.circle)],
                               dim.ViewObject.StandardAndStyle)
        # placed as loaded from a file, without snapping to the line it had before
        twin.ViewObject.AllowSnap = False
        self._pump()
        self._place(twin, self._center(dim))
        drawn = self._line_direction(twin, center)
        self.assertLess(abs(drawn.x * direction.y - drawn.y * direction.x), 1e-3,
                        "The line must follow from the label position alone")

    def test_diameter_label_snaps_next_to_center_asme(self):
        dim, center, start = self._radial("Diameter", "ASME Inlined", "SnapDiameter")
        direction = self._line_direction(dim, center)
        self._move(dim, center + App.Vector(5, -7, 0))
        offset = self._center(dim) - center
        # on the line, a little off the center, so that the label position keeps the direction
        self.assertAlmostEqual(offset.x * direction.y - offset.y * direction.x, 0.0, delta=0.05)
        self._assert_next_to_center(dim, offset.dot(direction))
        drawn = self._line_direction(dim, center)
        self.assertLess(abs(drawn.x * direction.y - drawn.y * direction.x), 1e-3)
        self._assert_drawn_alike(dim, center, direction)

    def test_diameter_label_snaps_beside_center_iso(self):
        dim, center, start = self._radial("Diameter", "ISO Oriented", "SnapDiameter")
        direction = self._line_direction(dim, center)
        normal = App.Vector(-direction.y, direction.x, 0)
        side = 1.0 if (start - center).dot(normal) >= 0 else -1.0
        beside = abs((start - center).dot(normal))
        self.assertGreater(beside, 1.0)
        self._move(dim, center + direction * 6 + normal * (side * beside - 5))
        snapped = self._center(dim)
        drawn = self._line_direction(dim, center)
        self.assertLess(abs(drawn.x * direction.y - drawn.y * direction.x), 1e-3,
                        "The diameter line must not flip when its label snaps")
        self._assert_next_to_center(dim, (snapped - center).dot(drawn))
        self.assertAlmostEqual(abs((snapped - center).dot(normal)), beside, delta=0.5)
        self._assert_drawn_alike(dim, center, direction)
        # dragging on near the snapped place keeps it there
        self._move(dim, snapped + direction * 3 + normal * 2)
        self._assert_close(self._center(dim), snapped, 0.05)

    def test_radius_label_does_not_snap_when_disallowed(self):
        dim, center, start = self._radial("Radius", "ASME Inlined", "SnapRadius")
        dim.ViewObject.AllowSnap = False
        self._pump()
        direction = self._line_direction(dim, center)
        request = center + direction * (RADIUS * self.rez * 0.5 + 4)
        self._move(dim, request)
        self._assert_close(self._center(dim), request)

    # angles -------------------------------------------------------------------

    def _angle(self, name, legs, radius, toward):
        """An angle between two legs, its label at radius, rotated from the bisector
        towards the first leg by the fraction toward of the half angle."""
        dim = self._dimension(name, "Angle",
                              [(self.view, self.legs[legs[0]]), (self.view, self.legs[legs[1]])],
                              "ASME Inlined")
        first, second, vertex = [self._gui(point) for point in dim.getAnglePoints()]
        leg1, leg2 = [(point - vertex).normalize() for point in (first, second)]
        bisector = (leg1 + leg2).normalize()
        ray = (bisector + (leg1 - bisector) * toward).normalize()
        self._place(dim, vertex + ray * (radius * self.rez))
        return dim, vertex, bisector

    def test_angle_label_snaps_to_bisector(self):
        dim, vertex, bisector = self._angle("SnapAngle", (0, 40), 25, 0.5)
        normal = App.Vector(-bisector.y, bisector.x, 0)
        distance = 25 * self.rez
        self._move(dim, vertex + bisector * distance + normal * 8)
        offset = self._center(dim) - vertex
        self.assertAlmostEqual(offset.x * bisector.y - offset.y * bisector.x, 0.0, delta=0.05)
        self.assertAlmostEqual(offset.dot(bisector), distance, delta=0.05)

    def test_angle_label_off_bisector_does_not_snap(self):
        dim, vertex, bisector = self._angle("SnapAngle", (0, 40), 25, 0.5)
        normal = App.Vector(-bisector.y, bisector.x, 0)
        request = vertex + bisector * (25 * self.rez) + normal * (self.text_catch + 5)
        self._move(dim, request)
        self._assert_close(self._center(dim), request)

    def test_angle_arcs_chain_and_cascade(self):
        first_dim, vertex, _ = self._angle("SnapAngleA", (0, 40), 25, 0.5)
        reference = (self._center(first_dim) - vertex).Length
        # well away from its bisector, so that only the arc radius snaps
        second_dim, _, _ = self._angle("SnapAngleB", (40, 100), 40, 0.6)
        ray = (self._center(second_dim) - vertex).normalize()

        # chained: the arc is aligned on the arc of the neighbour
        self._move(second_dim, vertex + ray * (reference + 0.5 * self.chain_catch))
        snapped = self._center(second_dim) - vertex
        self.assertAlmostEqual(snapped.Length, reference, delta=0.05)
        self.assertAlmostEqual(App.Vector(snapped).normalize().dot(ray), 1.0, delta=1e-6)

        # cascaded: the arc is one spacing outside the arc of the neighbour
        self._move(second_dim,
                   vertex + ray * (reference + self.spacing - 0.5 * self.chain_catch))
        snapped = self._center(second_dim) - vertex
        self.assertAlmostEqual(snapped.Length, reference + self.spacing, delta=0.05)

    def test_distance_label_still_snaps_to_middle(self):
        dim = self._dimension("SnapDistance", "Distance", [(self.view, self.horizontal)],
                              "ASME Inlined")
        first, second = [self._gui(point) for point in dim.getLinearPoints()]
        mid = (first + second) * 0.5
        start = mid + App.Vector(15 * self.rez, 10 * self.rez, 0)
        self._place(dim, start)
        self._move(dim, App.Vector(mid.x + 6, start.y, 0))
        self.assertAlmostEqual(self._center(dim).x, mid.x, delta=0.05)

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
            self._pump()
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)


if __name__ == "__main__":
    unittest.main()
