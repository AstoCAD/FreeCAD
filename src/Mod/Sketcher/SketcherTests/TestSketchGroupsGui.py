# SPDX-License-Identifier: LGPL-2.1-or-later

import os

import FreeCAD as App
import Part
import Sketcher
from PySide import QtCore, QtGui
from SketcherTests.GuiTestCase import FreeCADGui as Gui, SketcherGuiTestCase


class TestSketchGroupsGui(SketcherGuiTestCase):
    def testNestedGroupBoundsAndUngroup(self):
        from pivy import coin

        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("NestedGroupBounds")
        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x in (-40, 60):
            s.addGeometry(Part.Circle(App.Vector(x, 5, 0), App.Vector(0, 0, 1), 10))
        for x in (0, 10, 20):
            s.addGeometry(Part.LineSegment(App.Vector(x, 0, 0), App.Vector(x, 10, 0)), True)
        # Define the parent first so drawing cannot depend on constraint order.
        s.addConstraint(
            [
                Sketcher.Constraint("Group", [4, 0, 2, 0, 3, 0]),
                Sketcher.Constraint("Group", [2, 0, 0, 0]),
                Sketcher.Constraint("Group", [3, 0, 1, 0]),
            ]
        )
        self.doc.recompute()
        self.assertTrue(Gui.activeDocument().setEdit(s.Name))
        self.flush_gui(50)

        def constraint_nodes():
            search = coin.SoSearchAction()
            search.setName("ConstraintGroup")
            search.setSearchingAll(True)
            search.apply(Gui.activeDocument().activeView().getSceneGraph())
            path = search.getPath()
            self.assertIsNotNone(path)
            return path.getTail()

        nodes = constraint_nodes()
        corners = nodes.getChild(0).getChild(2).point.getValues()
        self.assertLess(corners[0][0], -50)
        self.assertGreater(corners[2][0], 70)
        self.assertLess(corners[0][1], -5)
        self.assertGreater(corners[2][1], 15)
        self.assertEqual(list(nodes.getField("enable").getValues()), [True, False, False])

        # Deactivating the parent must make both child boxes available again.
        s.toggleActive(0)
        self.flush_gui(50)
        self.assertTrue(all(constraint_nodes().getField("enable").getValues()))
        s.toggleActive(0)

        # Delete the bounding-box constraint to explode only the outer level.
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(s, "Constraint1")
        Gui.runCommand("Std_Delete", 0)
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (4, 2))
        self.assertEqual(s.solve(), 0)
        self.flush_gui(50)
        self.assertTrue(all(constraint_nodes().getField("enable").getValues()))
        self.doc.undo()
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (5, 3))
        self.flush_gui(50)
        self.assertEqual(
            list(constraint_nodes().getField("enable").getValues()), [True, False, False]
        )

    def testGroupOnlySelectedGeometry(self):
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("GroupSelection")
        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x in (0, 10, 20):
            s.addGeometry(Part.Circle(App.Vector(x, 0, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        Gui.activeDocument().setEdit(s.Name)
        Gui.Selection.clearSelection()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(s, edge)
        Gui.runCommand("Sketcher_ConstrainGroup")
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (4, 1))
        untouched = s.Geometry[2].Content
        s.addConstraint(Sketcher.Constraint("Distance", 3, 8.0))
        self.assertEqual(s.solve(), 0)
        self.assertAlmostEqual(s.Geometry[0].Radius, 4)
        self.assertAlmostEqual(s.Geometry[1].Radius, 4)
        self.assertEqual(s.Geometry[2].Content, untouched)

    def testGroupRefusedWhenAnotherObjectIsSelected(self):
        # The command warns that the selection is not just geometry from one sketch: it must
        # stop there instead of grouping anyway.
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("GroupForeignSelection")
        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x in (0, 10, 20):
            s.addGeometry(Part.Circle(App.Vector(x, 0, 0), App.Vector(0, 0, 1), 2))
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        Gui.activeDocument().setEdit(s.Name)
        state = {}

        def closeDialogs():
            if state.get("done"):
                return
            dialog = QtGui.QApplication.activeModalWidget()
            if dialog is not None:
                dialog.reject()
            QtCore.QTimer.singleShot(50, closeDialogs)

        QtCore.QTimer.singleShot(0, closeDialogs)
        Gui.Selection.clearSelection()
        for edge in ("Edge1", "Edge2"):
            Gui.Selection.addSelection(s, edge)
        Gui.Selection.addSelection(box)
        Gui.runCommand("Sketcher_ConstrainGroup")
        self.flush_gui(100)
        state["done"] = True
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (3, 0))

    def testGroupTransforms(self):
        Gui.activateWorkbench("SketcherWorkbench")
        for command in ("Rotate", "Translate", "Scale"):
            for pattern in (False, True):
                with self.subTest(command=command, pattern=pattern):
                    self.doc = App.newDocument("GroupTransform")
                    try:
                        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
                        s.addGeometry(Part.Circle(App.Vector(12, 14, 0), App.Vector(0, 0, 1), 2))
                        s.addGeometry(Part.Point(App.Vector(16, 18, 0)))
                        for x in (10, 20):
                            s.addGeometry(
                                Part.LineSegment(App.Vector(x, 10, 0), App.Vector(x, 20, 0)), True
                            )
                        s.addConstraint(Sketcher.Constraint("Group", [2, 0, 0, 0, 1, 0]))
                        s.addConstraint(Sketcher.Constraint("Group", [3, 0, 2, 0]))
                        self.doc.recompute()
                        Gui.activeDocument().setEdit(s.Name)
                        view = Gui.activeDocument().activeView()
                        view.setCamera(
                            "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
                            "orientation 0 0 1 0 focalDistance 100 height 100 }"
                        )
                        self.flush_gui(150)
                        viewport = view.graphicsView().viewport()
                        # Selecting a leaf must transform its entire outer group, including points.
                        Gui.Selection.clearSelection()
                        Gui.Selection.addSelection(s, "Edge1")
                        Gui.runCommand("Sketcher_" + command)
                        self.flush_gui(150)
                        points = [(0, 0), (20, 0)]
                        if command == "Rotate":
                            points.append((0, 20))
                        elif command == "Scale":
                            points.append((40, 0))
                        for index, (x, y) in enumerate(points):
                            pos = self.viewport_to_qpoint(
                                view, viewport, view.getPointOnScreen(App.Vector(x, y, 0))
                            )
                            self.move(viewport, pos)
                            self.click(viewport, pos)
                            if index == 0 and pattern:
                                self.key_click(viewport, QtCore.Qt.Key_U, "u")
                        self.assertEqual(s.GeometryCount, 8 if pattern else 4)
                        self.assertEqual(
                            sum(c.Type == "Group" for c in s.Constraints), 4 if pattern else 2
                        )
                        self.assertEqual(s.solve(), 0)
                        first = 4 if pattern else 0
                        root, circle, point, child = s.Geometry[first : first + 4]
                        # Derive the transformation from the outer handle: every member must
                        # follow it exactly, independently of mouse pixel rounding or snapping.
                        y_axis = (root.EndPoint - root.StartPoint) / 10
                        x_axis = App.Vector(y_axis.y, -y_axis.x, 0)

                        def transformed_point(x, y):
                            return root.StartPoint + x_axis * (x - 20) + y_axis * (y - 10)

                        for actual, expected in (
                            (circle.Center, transformed_point(12, 14)),
                            (point.toShape().Point, transformed_point(16, 18)),
                            (child.StartPoint, transformed_point(10, 10)),
                            (child.EndPoint, transformed_point(10, 20)),
                        ):
                            self.assertLess((actual - expected).Length, 1e-6)
                        self.assertAlmostEqual(circle.Radius, 2 * y_axis.Length)
                        self.assertGreater((root.StartPoint - App.Vector(20, 10, 0)).Length, 10)
                        transformed = [g.Content for g in s.Geometry]
                        self.doc.undo()
                        self.assertEqual(s.GeometryCount, 4)
                        self.assertEqual(sum(c.Type == "Group" for c in s.Constraints), 2)
                        self.doc.redo()
                        self.assertEqual([g.Content for g in s.Geometry], transformed)
                    finally:
                        # subTest continues after failures; always close its document
                        # before opening the next sketch.
                        self.cleanup_gui_document(self.doc)
                        self.doc = None

    def testNestedTextGroup(self):
        font = os.path.join(App.getResourceDir(), "examples", "osifont-lgpl3fe.ttf")
        if not os.path.isfile(font):
            self.skipTest("Bundled osifont not found")
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("NestedTextGroupTest")
        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x, text in [(0, "A"), (30, "B")]:
            handle = s.addGeometry(
                Part.LineSegment(App.Vector(x, 0, 0), App.Vector(x, 10, 0)), True
            )
            c = s.addConstraint(Sketcher.Constraint("Text", [handle, 0], text, font, True))
            s.setTextAndFont(c, text, font, True, False)
        self.doc.recompute()
        Gui.activeDocument().setEdit(s.Name)

        def select(ids):
            Gui.Selection.clearSelection()
            for geo in ids:
                Gui.Selection.addSelection(self.doc.Name, s.Name, "Edge{}".format(geo + 1))

        before = s.GeometryCount
        select(range(before))
        Gui.runCommand("Sketcher_ConstrainGroup", 0)
        self.assertEqual(s.solve(), 0)
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (before + 1, 3))

        # Ungrouping two text objects must remove only the outer group's handle.
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(s, "Constraint3")
        Gui.runCommand("Std_Delete", 0)
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (before, 2))
        self.assertEqual(sum(c.Type == "Text" for c in s.Constraints), 2)
        self.assertEqual(s.solve(), 0)
        self.doc.undo()
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (before + 1, 3))

        circle = s.addGeometry(Part.Circle(App.Vector(60, 5, 0), App.Vector(0, 0, 1), 2))
        select([0, circle])  # Selecting a text member must select its outer group.
        Gui.runCommand("Sketcher_ConstrainGroup", 0)
        root = s.GeometryCount - 1
        s.addConstraint(Sketcher.Constraint("Distance", root, 20.0))
        self.assertEqual(s.solve(), 0)
        self.assertAlmostEqual(s.Geometry[circle].Radius, 4)

        # Regeneration changes geometry indices.
        s.setTextAndFont(0, "ABC", font, True, False)
        self.assertEqual(s.solve(), 0)
        self.assertEqual(sum(c.Type == "Text" for c in s.Constraints), 2)
        groups = [c for c in s.Constraints if c.Type == "Group"]
        self.assertEqual(len(groups), 2)
        root = groups[-1].First
        counts = (s.GeometryCount, s.ConstraintCount)

        # Pattern copies must retain both levels of groups and editable text constraints.
        for command in ("Rotate", "Translate", "Scale"):
            select([root])
            view = Gui.activeDocument().activeView()
            view.setCamera(
                "#Inventor V2.1 ascii\nOrthographicCamera { position 0 0 100 "
                "orientation 0 0 1 0 focalDistance 100 height 100 }"
            )
            Gui.runCommand("Sketcher_" + command)
            self.flush_gui(150)
            viewport = view.graphicsView().viewport()
            points = [(0, 0), (20, 0)]
            if command == "Rotate":
                points.append((0, 20))
            elif command == "Scale":
                points.append((40, 0))
            for index, (x, y) in enumerate(points):
                pos = self.viewport_to_qpoint(
                    view, viewport, view.getPointOnScreen(App.Vector(x, y, 0))
                )
                self.move(viewport, pos)
                self.click(viewport, pos)
                if index == 0:
                    self.key_click(viewport, QtCore.Qt.Key_U, "u")
            self.assertEqual(s.solve(), 0, command)
            self.assertEqual(s.GeometryCount, 2 * counts[0], command)
            self.assertEqual(sum(c.Type == "Group" for c in s.Constraints), 4, command)
            self.assertEqual(sum(c.Type == "Text" for c in s.Constraints), 4, command)
            self.doc.undo()
            self.assertEqual((s.GeometryCount, s.ConstraintCount), counts)

        clipboard = QtGui.QApplication.clipboard()
        original = clipboard.mimeData()
        saved = {fmt: original.data(fmt) for fmt in original.formats()} if original else {}
        try:
            select([root])
            Gui.runCommand("Sketcher_CopyClipboard", 0)
            Gui.runCommand("Sketcher_Paste", 0)
            self.assertEqual(s.solve(), 0)
            self.assertEqual((s.GeometryCount, s.ConstraintCount), tuple(2 * n for n in counts))
            self.doc.undo()
            self.assertEqual((s.GeometryCount, s.ConstraintCount), counts)
        finally:
            restored = QtCore.QMimeData()
            for fmt, data in saved.items():
                restored.setData(fmt, data)
            clipboard.setMimeData(restored)

        select([root])
        Gui.runCommand("Std_Delete", 0)
        self.assertEqual((s.GeometryCount, s.ConstraintCount), (0, 0))
        self.doc.undo()
        self.assertEqual(s.solve(), 0)
        self.assertEqual((s.GeometryCount, s.ConstraintCount), counts)

    def testMirrorSketchKeepsWholeGroup(self):
        # Mirror Sketch renumbered only the first three elements of the mirrored constraints:
        # the last members of a group kept their index in the temporary sketch holding the
        # original and the mirrored geometry, so the mirrored sketch was malformed.
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("MirrorSketchGroup")
        s = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x in (-50, -40):
            s.addGeometry(Part.LineSegment(App.Vector(x, 0, 0), App.Vector(x, 7, 0)))
        handle = s.addGeometry(
            Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 10, 0)), True
        )
        members = [
            s.addGeometry(Part.LineSegment(App.Vector(12, 0, 0), App.Vector(15, 3, 0))),
            s.addGeometry(Part.Circle(App.Vector(13, 6, 0), App.Vector(0, 0, 1), 1)),
            s.addGeometry(Part.LineSegment(App.Vector(16, 0, 0), App.Vector(17, 3, 0))),
            s.addGeometry(Part.LineSegment(App.Vector(18, 1, 0), App.Vector(19, 4, 0))),
        ]
        elements = [handle, 0]
        for member in members:
            elements.extend([member, 0])
        s.addConstraint(Sketcher.Constraint("Group", elements))
        self.assertEqual(s.solve(), 0)
        self.doc.recompute()

        errors = []

        def mirror_about_y_axis():
            dialog = QtGui.QApplication.activeModalWidget()
            if dialog is None:
                return
            try:
                self.assertEqual(dialog.objectName(), "SketcherGui::SketchMirrorDialog")
                dialog.findChild(QtGui.QRadioButton, "YAxisRadioButton").click()
                dialog.findChild(QtGui.QDialogButtonBox).button(QtGui.QDialogButtonBox.Ok).click()
            except Exception:
                import traceback

                errors.append(traceback.format_exc())
                dialog.reject()

        closer = QtCore.QTimer(Gui.getMainWindow())
        closer.timeout.connect(mirror_about_y_axis)
        closer.start(25)
        try:
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(s)
            Gui.runCommand("Sketcher_MirrorSketch", 0)
            self.flush_gui(50)
        finally:
            closer.stop()
            closer.deleteLater()
        self.assertEqual(errors, [])

        mirrored = [o for o in self.doc.Objects if o.Name.startswith("MirroredSketch")]
        self.assertEqual(len(mirrored), 1)
        m = mirrored[0]
        self.assertEqual(m.GeometryCount, s.GeometryCount)
        self.assertEqual(sum(c.Type == "Group" for c in m.Constraints), 1)
        self.assertEqual(m.solve(), 0)
        self.assertLess((m.Geometry[members[1]].Center - App.Vector(-13, 6, 0)).Length, 1e-6)

        # Keep the mirrored handle rigid: dragging it must translate every mirrored member,
        # and nothing else.
        m.addConstraint(Sketcher.Constraint("Vertical", handle))
        m.addConstraint(Sketcher.Constraint("Distance", handle, 10.0))
        self.assertEqual(m.solve(), 0)
        others = [m.Geometry[g].StartPoint for g in range(handle)]
        before = {g: m.Geometry[g] for g in members}
        delta = App.Vector(-5, 4, 0)
        m.moveGeometry(handle, 1, m.Geometry[handle].StartPoint + delta, 0)
        self.assertEqual(m.solve(), 0)
        for geo in members:
            if geo == members[1]:
                self.assertLess((m.Geometry[geo].Center - before[geo].Center - delta).Length, 1e-6)
            else:
                moved = m.Geometry[geo].StartPoint - before[geo].StartPoint
                self.assertLess((moved - delta).Length, 1e-6, geo)
        for geo, point in enumerate(others):
            self.assertLess((m.Geometry[geo].StartPoint - point).Length, 1e-6, geo)

    def testMergeSketchesKeepsWholeGroup(self):
        # Merge Sketches renumbered only the first three elements of the merged constraints: the
        # last members of a group of the second sketch kept their index in that sketch, so they
        # named geometry of the first sketch in the merged one.
        Gui.activateWorkbench("SketcherWorkbench")
        self.doc = App.newDocument("MergeSketchesGroup")
        first = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        for x in (-50, -40, -30, -20, -10):
            first.addGeometry(Part.LineSegment(App.Vector(x, 0, 0), App.Vector(x, 7, 0)))
        second = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        handle = second.addGeometry(
            Part.LineSegment(App.Vector(10, 0, 0), App.Vector(10, 10, 0)), True
        )
        members = [
            second.addGeometry(Part.LineSegment(App.Vector(12, 0, 0), App.Vector(15, 3, 0))),
            second.addGeometry(Part.Circle(App.Vector(13, 6, 0), App.Vector(0, 0, 1), 1)),
            second.addGeometry(Part.LineSegment(App.Vector(16, 0, 0), App.Vector(17, 3, 0))),
            second.addGeometry(Part.LineSegment(App.Vector(18, 1, 0), App.Vector(19, 4, 0))),
        ]
        elements = [handle, 0]
        for member in members:
            elements.extend([member, 0])
        second.addConstraint(Sketcher.Constraint("Group", elements))
        self.assertEqual(second.solve(), 0)
        self.doc.recompute()

        before = set(self.doc.Objects)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(first)
        Gui.Selection.addSelection(second)
        Gui.runCommand("Sketcher_MergeSketches", 0)
        self.flush_gui(50)
        merged = [o for o in self.doc.Objects if o not in before]
        self.assertEqual(len(merged), 1)
        m = merged[0]
        offset = first.GeometryCount
        self.assertEqual(m.GeometryCount, offset + second.GeometryCount)
        self.assertEqual(sum(c.Type == "Group" for c in m.Constraints), 1)
        self.assertEqual(m.solve(), 0)

        # Keep the merged handle rigid: dragging it must translate every member of the group,
        # and nothing of the first sketch.
        mergedHandle = offset + handle
        mergedMembers = [offset + member for member in members]
        m.addConstraint(Sketcher.Constraint("Vertical", mergedHandle))
        m.addConstraint(Sketcher.Constraint("Distance", mergedHandle, 10.0))
        self.assertEqual(m.solve(), 0)
        others = [m.Geometry[g].StartPoint for g in range(offset)]
        moved = {g: m.Geometry[g] for g in mergedMembers}
        delta = App.Vector(-5, 4, 0)
        m.moveGeometry(mergedHandle, 1, m.Geometry[mergedHandle].StartPoint + delta, 0)
        self.assertEqual(m.solve(), 0)
        for geo in mergedMembers:
            if geo == offset + members[1]:
                shift = m.Geometry[geo].Center - moved[geo].Center
            else:
                shift = m.Geometry[geo].StartPoint - moved[geo].StartPoint
            self.assertLess((shift - delta).Length, 1e-6, geo)
        for geo, point in enumerate(others):
            self.assertLess((m.Geometry[geo].StartPoint - point).Length, 1e-6, geo)
