# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tree eye visibility for array elements and ordinary own-feature controls.

Actual eye input must update the real link renderer without changing peers.
Ordinary Body, Group, Box and Link eye/Space behavior is covered separately.
Array-element Space behavior is outside this partial issue32386 regression.
"""

import time
import unittest

import FreeCAD as App
_tree_workbenches_available = False
if App.GuiUp:
    import FreeCADGui as Gui
    _tree_workbenches_available = all(
        name in Gui.listWorkbenches()
        for name in ("AssemblyWorkbench", "PartWorkbench", "PartDesignWorkbench")
    )
    if _tree_workbenches_available:
        import Part
        import PartDesign  # noqa: F401
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipIf(not App.GuiUp, "Requires actual native tree and link renderer")
@unittest.skipUnless(
    _tree_workbenches_available, "Requires optional Assembly, Part and Part Design workbenches"
)
class _TreeVisibilityGuiTestCase(unittest.TestCase):
    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "Run in an isolated GUI process")
        self.previous_workbench = Gui.activeWorkbench().name() if Gui.activeWorkbench() else None
        self.doc_name = None
        self.retained = []
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.activateWorkbench("PartWorkbench")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("LinkElementVisibility32386")
        self.doc_name = self.doc.Name
        self.source = self.doc.addObject("Part::Box", "Source")
        self.source.Length, self.source.Width, self.source.Height = 2, 3, 4
        self.doc.recompute()
        self.assertTrue(self.source.Shape.isValid())
        self.assertAlmostEqual(self.source.Shape.Volume, 24.0)

    @staticmethod
    def _events(milliseconds=100):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self._events()
        return bool(predicate())

    @staticmethod
    def _visible_trees():
        return [widget for widget in Gui.getMainWindow().findChildren(QtWidgets.QTreeWidget)
                if widget.inherits("Gui::TreeWidget") and widget.isVisibleTo(Gui.getMainWindow())]

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            App.closeDocument(self.doc_name)
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            self._events()
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _scenario(self, inside_assembly):
        self.array = self.doc.addObject("App::Link", "Array")
        self.array.LinkedObject = self.source
        self.array.ShowElement = True
        self.array.ElementCount = 2
        self.doc.recompute()
        self.assertEqual(len(self.array.ElementList), 2)
        self.target, self.peer = self.array.ElementList
        self.target.Label = self.doc.Name + "_First"
        self.peer.Label = self.doc.Name + "_Second"
        self.array.Label = self.doc.Name + "_Array"
        if inside_assembly:
            self.assembly = self.doc.addObject("Assembly::AssemblyObject", "Assembly")
            self.assembly.addObject(self.array)
            self.assertIn(self.array, self.assembly.Group)
            self.root = self.assembly
            self.subname = self.array.Name + "." + self.target.Name + "."
        else:
            self.root = self.array
            self.subname = self.target.Name + "."
        self.source.ViewObject.Visibility = False
        self.doc.recompute()
        self.assertEqual(self.root.getSubObject(self.subname, 1), self.target)
        self.assertFalse(self.target.Suppressed)
        self.assertFalse(self.peer.Suppressed)
        self._assert_rendered(True)
        self._events()
        self._wait(lambda: bool(self._visible_trees()))
        trees = self._visible_trees()
        self.assertTrue(trees, "A genuine visible document tree is required")
        self.tree = trees[0]
        self.retained.append(self.tree)
        self.tree.expandAll()
        self.assertTrue(self._wait(lambda: bool(self._rows())))
        self._row()

    def _rows(self):
        return self.tree.findItems(self.target.Label,
            QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive, 0)

    def _row(self):
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.retained.append(item)
        self.tree.scrollToItem(item)
        self._events()
        rect = self.tree.visualItemRect(item)
        self.assertFalse(rect.isEmpty())
        self.assertTrue(self.tree.viewport().rect().contains(rect.center()))
        labels = []
        parent = item.parent()
        while parent is not None:
            self.retained.append(parent)
            labels.append(parent.text(0))
            parent = parent.parent()
        self.assertIn(self.array.Label, labels)
        if self.root != self.array:
            self.assertIn(self.assembly.Label, labels)
        return item, rect

    def _assert_rendered(self, first_visible):
        with self.subTest(oracle="real_link_element_visibility"):
            self.assertEqual(self.array.isElementVisible("0"), int(first_visible))
            self.assertEqual(self.array.isElementVisible("1"), 1)
        with self.subTest(oracle="real_link_renderer_visibility"):
            self.assertEqual(tuple(self.array.ViewObject.LinkView.Visibilities),
                             (first_visible, True))
        self.assertTrue(self.array.Visibility)
        self.assertFalse(self.source.Visibility)
        self.assertAlmostEqual(self.source.Shape.Volume, 24.0)

    def _eye(self):
        preferences = App.ParamGet("User parameter:BaseApp/Preferences/TreeView")
        self.assertTrue(preferences.GetBool("VisibilityIcon", True),
                        "Existing eye icons must be enabled; fixture changes no preferences")
        Gui.Selection.clearSelection()
        item, rect = self._row()
        style = self.tree.style()
        x = rect.left() + style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin) + 2
        if preferences.GetBool("CheckBoxesSelection", False):
            x += (style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth)
                  + style.pixelMetric(QtWidgets.QStyle.PM_LayoutHorizontalSpacing))
        point = QtCore.QPoint(x, rect.center().y())
        self.assertEqual(self.tree.itemAt(point), item)
        QtTest.QTest.mouseClick(self.tree.viewport(), QtCore.Qt.LeftButton,
                               QtCore.Qt.NoModifier, point)
        self._events()
        self.assertEqual(Gui.Selection.getSelectionEx(), [],
                         "Native eye handling must consume the click without row selection")

    def _space(self):
        item, rect = self._row()
        self.tree.clearSelection()
        self.tree.setFocus()
        point = QtCore.QPoint(min(rect.right() - 2, rect.left() + 80), rect.center().y())
        self.assertEqual(self.tree.itemAt(point), item)
        QtTest.QTest.mouseClick(self.tree.viewport(), QtCore.Qt.LeftButton,
                               QtCore.Qt.NoModifier, point)
        self._events()
        self.assertEqual(self.tree.selectedItems(), [item])
        selections = Gui.Selection.getSelectionEx()
        self.assertEqual(len(selections), 1)
        resolved = [entry.Object.getSubObject(name, 1) if name else entry.Object
                    for entry in selections for name in (entry.SubElementNames or [""])]
        self.assertIn(self.target, resolved, "Genuine tree selection must identify this occurrence")
        QtTest.QTest.keyClick(self.tree, QtCore.Qt.Key_Space, QtCore.Qt.NoModifier)
        self._events()







class TestTreeArrayElementEye(_TreeVisibilityGuiTestCase):
    def test_assembly_eye_updates_link_visibility(self):
        self._scenario(True)
        self._eye()
        self._assert_rendered(False)
        self._eye()
        self._assert_rendered(True)

    def test_root_array_eye_control(self):
        self._scenario(False)
        self._eye()
        self._assert_rendered(False)
        self._eye()
        self._assert_rendered(True)

    def test_assembly_standard_toggle_visibility_command_control(self):
        self._scenario(True)
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(self.doc.Name, self.root.Name, self.subname)
        self.assertEqual(len(Gui.Selection.getSelectionEx()), 1)
        Gui.runCommand("Std_ToggleVisibility")
        self._events()
        self._assert_rendered(False)
        Gui.runCommand("Std_ToggleVisibility")
        self._events()
        self._assert_rendered(True)


class TestTreeRepeatedArrayElementEye(_TreeVisibilityGuiTestCase):
    def _rows(self):
        rows = super()._rows()
        occurrence = getattr(self, "active_occurrence", None)
        if occurrence is None:
            return rows
        selected = []
        for row in rows:
            parent = row.parent()
            while parent is not None:
                self.retained.append(parent)
                if parent.text(0) == occurrence.Label:
                    selected.append(row)
                    break
                parent = parent.parent()
        return selected

    def _row(self):
        occurrence = getattr(self, "active_occurrence", None)
        if occurrence is None:
            return super()._row()
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.retained.append(item)
        self.tree.scrollToItem(item)
        self._events()
        rect = self.tree.visualItemRect(item)
        self.assertFalse(rect.isEmpty())
        self.assertTrue(self.tree.viewport().rect().contains(rect.center()))
        labels = []
        parent = item.parent()
        while parent is not None:
            self.retained.append(parent)
            labels.append(parent.text(0))
            parent = parent.parent()
        self.assertIn(self.array.Label, labels)
        self.assertIn(occurrence.Label, labels)
        return item, rect

    def _all_paths(self):
        result = []
        for row in super()._rows():
            self.retained.append(row)
            path = [row.text(0)]
            parent = row.parent()
            while parent is not None:
                self.retained.append(parent)
                path.insert(0, parent.text(0))
                parent = parent.parent()
            result.append(path)
        return result

    def _repeated_scenario(self):
        self.active_occurrence = None
        self._scenario(False)
        self.part = self.doc.addObject("App::Part", "ArrayPart")
        self.part.Label = self.doc.Name + "_ArrayPart"
        self.part.addObject(self.array)
        self.occurrences = []
        for index in range(2):
            link = self.doc.addObject("App::Link", "PartOccurrence")
            link.LinkedObject = self.part
            link.Label = self.doc.Name + "_Occurrence" + str(index)
            self.occurrences.append(link)
        self.doc.recompute()
        self.part.Visibility = True
        for link in self.occurrences:
            link.Visibility = True

        def expanded():
            self.tree.expandAll()
            paths = self._all_paths()
            return all(any(link.Label in path for path in paths) for link in self.occurrences)

        self.assertTrue(self._wait(expanded, seconds=3),
                        "Both real linked occurrences must expose the target tree row")
        self.assertEqual(len(self.occurrences), 2)
        for link in self.occurrences:
            resolved = link.resolve(self.array.Name + "." + self.target.Name + ".")
            self.assertEqual(len(resolved), 4)
            self.assertEqual(resolved[0], self.target)
            self.assertEqual(resolved[1], self.array)
            self.assertEqual(resolved[1].isElementVisible(resolved[2]), 1)
            self.assertEqual(resolved[3], "")
        self._assert_contexts_unchanged()

    def _context(self, link):
        self.active_occurrence = link
        self.root = link
        self.subname = self.array.Name + "." + self.target.Name + "."
        self._row()

    def _assert_contexts_unchanged(self):
        self.assertTrue(self.part.Visibility)
        self.assertFalse(self.source.Visibility)
        for link in self.occurrences:
            self.assertTrue(link.Visibility)
            self.assertEqual(link.LinkedObject, self.part)
        self.assertAlmostEqual(self.source.Shape.Volume, 24.0)

    def test_repeated_link_context_eye_roundtrip(self):
        self._repeated_scenario()
        for link in self.occurrences:
            with self.subTest(occurrence=link.Name):
                self._context(link)
                self._eye()
                self._assert_rendered(False)
                self._assert_contexts_unchanged()
                self._eye()
                self._assert_rendered(True)
                self._assert_contexts_unchanged()

    def test_repeated_link_standard_toggle_command_control(self):
        self._repeated_scenario()
        for link in self.occurrences:
            with self.subTest(occurrence=link.Name):
                self._context(link)
                Gui.Selection.clearSelection()
                Gui.Selection.addSelection(self.doc.Name, link.Name, self.subname)
                self.assertEqual(len(Gui.Selection.getSelectionEx()), 1)
                Gui.runCommand("Std_ToggleVisibility")
                self._events()
                self._assert_rendered(False)
                self._assert_contexts_unchanged()
                Gui.runCommand("Std_ToggleVisibility")
                self._events()
                self._assert_rendered(True)
                self._assert_contexts_unchanged()


class TestOrdinaryTreeVisibility(_TreeVisibilityGuiTestCase):
    def _row(self):
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        item = rows[0]
        self.retained.append(item)
        self.tree.scrollToItem(item)
        self._events()
        rect = self.tree.visualItemRect(item)
        self.assertFalse(rect.isEmpty())
        self.assertTrue(self.tree.viewport().rect().contains(rect.center()))
        labels = []
        parent = item.parent()
        while parent is not None:
            self.retained.append(parent)
            labels.append(parent.text(0))
            parent = parent.parent()
        for expected in self.expected_ancestors:
            self.assertIn(expected, labels)
        return item, rect

    def _ordinary(self, kind):
        self.expected_ancestors = []
        self.target = self.source
        if kind == "group_child":
            group = self.doc.addObject("App::DocumentObjectGroup", "Group")
            group.Label = self.doc.Name + "_Group"
            group.addObject(self.target)
            peer = self.doc.addObject("Part::Box", "Peer")
            group.addObject(peer)
            self.expected_ancestors = [group.Label]
        elif kind == "body_feature":
            body = self.doc.addObject("PartDesign::Body", "Body")
            self.target = body.newObject("PartDesign::Feature", "HistoricalFeature")
            self.target.Shape = Part.makeBox(2, 3, 4)
            tip = body.newObject("PartDesign::Feature", "TipFeature")
            tip.Shape = Part.makeBox(1, 2, 3)
            body.Tip = tip
            self.target.Visibility = True
            tip.Visibility = True
            self.expected_ancestors = [body.Label]
            self.assertEqual(body.Tip, tip)
            self.assertNotEqual(body.Tip, self.target)
        elif kind == "nested_link":
            part = self.doc.addObject("App::Part", "Part")
            self.target = self.doc.addObject("App::Link", "Occurrence")
            self.target.LinkedObject = self.source
            peer = self.doc.addObject("App::Link", "PeerOccurrence")
            peer.LinkedObject = self.source
            part.addObject(self.target)
            part.addObject(peer)
            self.expected_ancestors = [part.Label]
            self.assertEqual(self.target.LinkedObject, self.source)
            self.assertEqual(peer.LinkedObject, self.source)
        else:
            self.assertEqual(kind, "standalone_box")
        self.target.Label = self.doc.Name + "_OrdinaryTarget"
        self.doc.recompute()
        # Recompute initializes history visibility; expose the selected feature
        # afterward just as a user does before testing its own eye/Space toggle.
        if kind == "body_feature":
            body.Visibility = True
            tip.Visibility = True
        self.target.Visibility = True
        # Match the already qualified array fixture's ordinary layout turn.
        self._events()
        self.assertFalse(self.target.isDerivedFrom("App::LinkElement"))
        self.assertTrue(self.target.Visibility)
        self.assertTrue(self.target.ViewObject.Visibility)
        self.unchanged_visibility = {obj.Name: obj.Visibility for obj in self.doc.Objects
                                     if obj != self.target}
        self._wait(lambda: bool(self._visible_trees()))
        trees = self._visible_trees()
        self.assertTrue(trees)
        self.tree = trees[0]
        self.retained.append(self.tree)
        self.tree.expandAll()
        self.assertTrue(self._wait(lambda: bool(self._rows())))
        self._row()

    def _assert_ordinary(self, visible):
        self.assertEqual(self.target.Visibility, visible)
        self.assertEqual(self.target.ViewObject.Visibility, visible)
        for name, before in self.unchanged_visibility.items():
            with self.subTest(unchanged_object=name):
                self.assertEqual(self.doc.getObject(name).Visibility, before)
        self.assertAlmostEqual(self.source.Shape.Volume, 24.0)
        self.assertTrue(self.source.Shape.isValid())

    def _roundtrip_ordinary(self, kind, action):
        self._ordinary(kind)
        getattr(self, action)()
        self._assert_ordinary(False)
        getattr(self, action)()
        self._assert_ordinary(True)

    def test_standalone_box_space_control(self):
        self._roundtrip_ordinary("standalone_box", "_space")

    def test_plain_group_child_space_preserves_group_and_peer_control(self):
        self._roundtrip_ordinary("group_child", "_space")

    def test_body_feature_space_preserves_body_tip_and_peer_control(self):
        self._roundtrip_ordinary("body_feature", "_space")

    def test_nested_link_space_preserves_source_and_peer_occurrence_control(self):
        self._roundtrip_ordinary("nested_link", "_space")

    def test_standalone_box_eye_control(self):
        self._roundtrip_ordinary("standalone_box", "_eye")

    def test_plain_group_child_eye_preserves_group_and_peer_control(self):
        self._roundtrip_ordinary("group_child", "_eye")

    def test_body_feature_eye_preserves_body_tip_and_peer_control(self):
        self._roundtrip_ordinary("body_feature", "_eye")

    def test_nested_link_eye_preserves_source_and_peer_occurrence_control(self):
        self._roundtrip_ordinary("nested_link", "_eye")


if __name__ == "__main__":
    unittest.main()
