# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI regressions for explicit EditableDatumLabel constructor colors.

Uses valid RGB tuples and observes only the newly owned native scene branch.
Omitted and None colors preserve the existing preference-based appearance.
"""

import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from pivy import coin


@unittest.skipUnless(App.GuiUp, "requires GUI")
class TestEditableDatumConstructorColorGui(unittest.TestCase):
    COLOR = (0.125, 0.375, 0.875)
    SETTER_COLOR = (0.875, 0.25, 0.5)
    PREFERENCE_COLOR = 0x2060A000
    PREFERENCE_RGB = (32.0 / 255.0, 96.0 / 255.0, 160.0 / 255.0)

    def setUp(self):
        self.assertFalse(App.listDocuments(), "requires an isolated empty GUI session")
        self.assertFalse(Gui.Control.activeDialog())
        self.labels = []
        self.branches = []
        self.doc = App.newDocument("EditableDatumColor33928")
        self.view = Gui.getDocument(self.doc.Name).activeView()
        self.scene = self.view.getViewer().getSceneGraph()
        self.initial_child_count = self.scene.getNumChildren()
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/View")
        self.key = "DeactivatedConstrDimColor"
        self.had_color = self.key in self.params.GetUnsigneds()
        self.old_color = self.params.GetUnsigned(self.key, 0)
        self.addCleanup(self._cleanup)
        self.params.SetUnsigned(self.key, self.PREFERENCE_COLOR)

    def _cleanup(self):
        try:
            # Every label and its viewer remain alive while its own branch is unlinked.
            for label in self.labels:
                label.deactivate()
            for branch in self.branches:
                self.scene.removeChild(branch)
            label = None
            branch = None
            self.branches.clear()
            self.labels.clear()
            self.assertEqual(self.scene.getNumChildren(), self.initial_child_count)
        finally:
            try:
                if self.had_color:
                    self.params.SetUnsigned(self.key, self.old_color)
                else:
                    self.params.RemUnsigned(self.key)
            finally:
                self.scene = None
                self.view = None
                App.closeDocument(self.doc.Name)
                self.doc = None

    def _make_label(self, *args, **kwargs):
        before = self.scene.getNumChildren()
        label = Gui.EditableDatumLabel(self.view, App.Placement(), *args, **kwargs)
        self.labels.append(label)
        self.assertEqual(self.scene.getNumChildren(), before + 1)
        branch = self.scene.getChild(before)
        self.branches.append(branch)
        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoDatumLabel"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(branch)
        nodes = [path.getTail() for path in search.getPaths()]
        self.assertEqual(len(nodes), 1, "exactly one datum node in the newly owned branch")
        self.assertFalse(label.isActive())
        self.assertFalse(label.isInEdit())
        self.assertEqual(label.getValue(), 0.0)
        self.assertEqual(label.getFunction(), "positioning")
        return label, nodes[0]

    def _color(self, node):
        return tuple(float(value) for value in node.getField("textColor").getValue().getValue())

    def _assert_color(self, node, expected):
        actual = self._color(node)
        self.assertEqual(len(actual), 3)
        for index, value in enumerate(expected):
            self.assertAlmostEqual(actual[index], value, places=6)

    def _non_color_fields(self, node):
        return {
            "string": tuple(node.getField("string").getValues()),
            "datumtype": node.getField("datumtype").getValue(),
            "size": node.getField("size").getValue(),
            "lineWidth": node.getField("lineWidth").getValue(),
            "strikethrough": node.getField("strikethrough").getValue(),
            "pnts": tuple(tuple(point) for point in node.getField("pnts").getValues()),
        }

    def test_existing_set_color_control(self):
        label, node = self._make_label()
        self._assert_color(node, self.PREFERENCE_RGB)
        before = self._non_color_fields(node)
        label.setColor(self.COLOR)
        self._assert_color(node, self.COLOR)
        self.assertEqual(self._non_color_fields(node), before)
        label.setColor(self.SETTER_COLOR)
        self._assert_color(node, self.SETTER_COLOR)
        self.assertEqual(self._non_color_fields(node), before)
        self.assertFalse(label.isActive())
        self.assertFalse(label.isInEdit())

    def test_omitted_and_none_preserve_preference_control(self):
        omitted, omitted_node = self._make_label()
        explicit_none, none_node = self._make_label(color=None)
        self._assert_color(omitted_node, self.PREFERENCE_RGB)
        self._assert_color(none_node, self.PREFERENCE_RGB)
        self.assertEqual(self._non_color_fields(omitted_node), self._non_color_fields(none_node))
        self.assertFalse(omitted.isActive())
        self.assertFalse(explicit_none.isActive())

    def test_explicit_positional_rgb_constructor(self):
        baseline, baseline_node = self._make_label()
        explicit, explicit_node = self._make_label(self.COLOR)
        self._assert_color(baseline_node, self.PREFERENCE_RGB)
        self.assertEqual(
            self._non_color_fields(explicit_node), self._non_color_fields(baseline_node)
        )
        self.assertEqual(explicit.getValue(), baseline.getValue())
        self._assert_color(explicit_node, self.COLOR)

    def test_explicit_keyword_rgb_constructor(self):
        baseline, baseline_node = self._make_label()
        explicit, explicit_node = self._make_label(color=self.COLOR)
        self._assert_color(baseline_node, self.PREFERENCE_RGB)
        self.assertEqual(
            self._non_color_fields(explicit_node), self._non_color_fields(baseline_node)
        )
        self.assertEqual(explicit.getFunction(), baseline.getFunction())
        self._assert_color(explicit_node, self.COLOR)

    def test_invalid_constructor_arguments_raise(self):
        """The converters throw C++ exceptions: they must reach Python as
        TypeError instead of escaping tp_new (which hung FreeCAD)."""
        before = self.scene.getNumChildren()
        with self.assertRaises(TypeError):
            Gui.EditableDatumLabel(self.view, App.Placement(), (1.0, 2.0))
        with self.assertRaises(TypeError):
            Gui.EditableDatumLabel(self.view, 1)
        self.assertEqual(self.scene.getNumChildren(), before)
