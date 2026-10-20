# SPDX-License-Identifier: LGPL-2.1-or-later
"""Workbench tab identity across disabled tabs, refresh and toolbar movement.

The fixture owns workbench shells containing built-in native commands, preserves
all scoped preferences, and checks actual user clicks and activation signals.
Cleanup alone blocks tab signals while removing the owned workbenches.
"""

import json
from functools import wraps
from time import monotonic
import unittest
from uuid import uuid4

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    import Part  # noqa: F401
    from PySide import QtCore, QtWidgets
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


# Fixture-owned UUID keys are captured before registration/activation. Parent
# lookups use HasGroup so observing an absent Tux path does not create it.
def _existing_parameter_group(path):
    group = App.ParamGet("User parameter:BaseApp").Manager()
    for part in path.split("/"):
        if not group.HasGroup(part):
            return None
        group = group.GetGroup(part)
    return group


def _parameter_snapshot(group):
    if group is None:
        return None
    return {
        "values": list(group.GetContents() or []),
        "groups": {name: _parameter_snapshot(group.GetGroup(name))
                   for name in group.GetGroups()},
    }


def _restore_parameter_snapshot(group, snapshot):
    methods = {
        "String": ("SetString", "RemString"),
        "Integer": ("SetInt", "RemInt"),
        "Float": ("SetFloat", "RemFloat"),
        "Boolean": ("SetBool", "RemBool"),
        "Unsigned Long": ("SetUnsigned", "RemUnsigned"),
    }
    previous = {(kind, name): value for kind, name, value in snapshot["values"]}
    for kind, name, value in group.GetContents() or []:
        if (kind, name) not in previous:
            getattr(group, methods[kind][1])(name)
    for kind, name, value in snapshot["values"]:
        getattr(group, methods[kind][0])(name, value)
    for name in group.GetGroups():
        if name not in snapshot["groups"]:
            group.RemGroup(name)
    for name, child in snapshot["groups"].items():
        _restore_parameter_snapshot(group.GetGroup(name), child)


def _owned_bool_value(group, name):
    if group is None:
        return None
    return next((value for kind, key, value in group.GetContents() or []
                 if kind == "Boolean" and key == name), None)


def _capture_owned_artifacts(case, name):
    if name in case._owned_artifact_snapshots:
        return
    toolbar_path = "BaseApp/MainWindow/Toolbars"
    toolbar = name + "_Toolbar"
    tux = {}
    for parent_path in ("Tux/PersistentToolbars/User", "Tux/PersistentToolbars/System"):
        parent = _existing_parameter_group(parent_path)
        owned = parent.GetGroup(name) if parent is not None and parent.HasGroup(name) else None
        tux[parent_path] = _parameter_snapshot(owned)
    case._owned_artifact_snapshots[name] = {
        "toolbar_path": toolbar_path, "toolbar": toolbar,
        "boolean": _owned_bool_value(_existing_parameter_group(toolbar_path), toolbar),
        "tux": tux,
    }


def _restore_owned_artifacts(case):
    # Existing normal GUI/document/workbench cleanup runs before this callback.
    for name, snapshot in case._owned_artifact_snapshots.items():
        toolbar_group = _existing_parameter_group(snapshot["toolbar_path"])
        if snapshot["boolean"] is None:
            if toolbar_group is not None:
                toolbar_group.RemBool(snapshot["toolbar"])
        else:
            if toolbar_group is None:
                toolbar_group = App.ParamGet("User parameter:" + snapshot["toolbar_path"])
            toolbar_group.SetBool(snapshot["toolbar"], snapshot["boolean"])
        case.assertEqual(_owned_bool_value(toolbar_group, snapshot["toolbar"]),
                         snapshot["boolean"], "Exact owned toolbar Boolean restoration")
        for parent_path, previous in snapshot["tux"].items():
            parent = _existing_parameter_group(parent_path)
            if previous is None:
                if parent is not None and parent.HasGroup(name):
                    parent.RemGroup(name)
            else:
                if parent is None:
                    parent = App.ParamGet("User parameter:" + parent_path)
                _restore_parameter_snapshot(parent.GetGroup(name), previous)
            restored = parent.GetGroup(name) if parent is not None and parent.HasGroup(name) else None
            case.assertEqual(_parameter_snapshot(restored), previous,
                             "Exact owned Tux group restoration: " + parent_path + "/" + name)


def _with_owned_artifact_setup(setup):
    @wraps(setup)
    def scoped(case):
        case._owned_artifact_snapshots = {}
        case.addCleanup(_restore_owned_artifacts, case)
        setup(case)
        for name in (case.a, case.b, case.c, case.disabled):
            _capture_owned_artifacts(case, name)
    return scoped


def _with_owned_registration_snapshot(register):
    @wraps(register)
    def scoped(case, name):
        _capture_owned_artifacts(case, name)
        return register(case, name)
    return scoped


@unittest.skipUnless(
    App.GuiUp and Gui.getMainWindow().findChildren(QtWidgets.QWidget, "WbTabBar"),
    "Workbench tab selector requires GUI mode and the tab selector configuration",
)
class TestWorkbenchSelectorNative(unittest.TestCase):
    @_with_owned_artifact_setup
    def setUp(self):
        self.initial_documents = set(App.listDocuments())
        self.previous = App.activeDocument().Name if App.activeDocument() else None
        self.previous_workbench = Gui.activeWorkbench().name()
        self.workbenches = []
        self.params = App.ParamGet("User parameter:BaseApp/Preferences/Workbenches")
        self.original_preferences = {
            key: next((value for kind, name, value in (self.params.GetContents() or [])
                       if name == key), None)
            for key in ("Disabled", "Ordered")
        }
        self.areas = {
            name: App.ParamGet("User parameter:BaseApp/MainWindow/" + name)
            for name in ("StatusBar", "MenuBarLeft", "MenuBarRight")
        }
        self.area_values = {name: self._integers(params) for name, params in self.areas.items()}
        self.addCleanup(self._cleanup)
        widgets = Gui.getMainWindow().findChildren(QtWidgets.QWidget, "WbTabBar")
        self.assertEqual(len(widgets), 1)
        self.selector = widgets[0]
        self.assertTrue(self.selector.inherits("Gui::WorkbenchTabWidget"))
        bars = self.selector.findChildren(QtWidgets.QTabBar)
        self.assertEqual(len(bars), 1)
        self.tabs = bars[0]
        self.toolbar = self.selector.parentWidget()
        self.assertIsInstance(self.toolbar, QtWidgets.QToolBar)
        self.original_area = self.toolbar.parentWidget().objectName()
        token = uuid4().hex[:12]
        self.a = "SelectorNativeA_" + token
        self.b = "SelectorNativeB_" + token
        self.c = "SelectorNativeC_" + token
        self.disabled = "SelectorNativeDisabled_" + token
        self.doc = App.newDocument("SelectorNativeProbe")
        self.box = self.doc.addObject("Part::Box", "SourceBox")
        self.box.Length, self.box.Width, self.box.Height = 13, 7, 11
        self.doc.recompute()
        self._assert_model()
        self.assertIsNotNone(Gui.Command.get("Std_ViewFitAll"))

    @staticmethod
    def _integers(params):
        return {name: value for kind, name, value in (params.GetContents() or [])
                if kind == "Integer"}

    @staticmethod
    def _wait(condition, timeout=3.0):
        deadline = monotonic() + timeout
        while not condition() and monotonic() < deadline:
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(10, loop.quit)
            loop.exec_()
        return bool(condition())

    def _assert_model(self):
        self.assertEqual(App.activeDocument(), self.doc)
        self.assertTrue(self.box.Shape.isValid())
        self.assertAlmostEqual(self.box.Shape.Volume, 1001)
        self.assertEqual(len(Gui.activeDocument().activeView().getCameraOrientation().Q), 4)

    @_with_owned_registration_snapshot
    def _register(self, name):
        cls = type(name, (Gui.Workbench,), {
            "MenuText": name, "ToolTip": name,
            "Initialize": lambda workbench: workbench.appendToolbar(
                name + "_Toolbar", ["Std_ViewFitAll"]),
            "GetClassName": lambda workbench: "Gui::PythonWorkbench",
        })
        self.workbenches.append(name)
        Gui.addWorkbench(cls())

    def _configure(self, rtl):
        disabled = self.original_preferences["Disabled"]
        if disabled is None:
            disabled = "NoneWorkbench,TestWorkbench,InspectionWorkbench,RobotWorkbench,OpenSCADWorkbench"
        self.params.SetString("Disabled", disabled + "," + self.disabled)
        ordered = self.original_preferences["Ordered"] or ""
        self.params.SetString("Ordered", ",".join((self.a, self.b, self.c, ordered)))
        for name in (self.a, self.b, self.disabled):
            self._register(name)
        for params in self.areas.values():
            params.RemInt("Workbench")
        target = "MenuBarRight" if rtl else "MenuBarLeft"
        positions = self._integers(self.areas[target])
        self.areas[target].SetInt("Workbench", max(positions.values(), default=-1) + 1)
        # This is the normal live toolbar-preference observer, not a fake direction.
        self.assertTrue(self._wait(
            lambda: self.toolbar.parentWidget().objectName() == target + "Area"))
        self.assertTrue(QtCore.QMetaObject.invokeMethod(
            self.selector, "updateLayout", QtCore.Qt.DirectConnection))
        expected = QtCore.Qt.RightToLeft if rtl else QtCore.Qt.LeftToRight
        self.assertEqual(self.selector.property("direction"), expected)
        self._assert_owned_tabs((self.a, self.b))

    def _assert_owned_tabs(self, names):
        texts = [self.tabs.tabText(index) for index in range(self.tabs.count())]
        for name in names:
            with self.subTest(oracle="owned_enabled_tab_present_once", workbench=name):
                self.assertEqual(texts.count(name), 1, texts)

    def _activate(self, name):
        self.assertTrue(Gui.activateWorkbench(name))
        actual = Gui.activeWorkbench().name()
        print("SELECTOR_NATIVE", json.dumps({
            "test": self.id(), "requested": name, "actual": actual,
            "direction": str(self.selector.property("direction")),
            "tabs": [self.tabs.tabText(index) for index in range(self.tabs.count())],
            "current": self.tabs.currentIndex(),
        }), flush=True)
        with self.subTest(oracle="exact_active_workbench", requested=name):
            self.assertEqual(actual, name)
        self._assert_model()

    def _ordinary(self, rtl):
        self._configure(rtl)
        self._activate(self.a)
        self._activate(self.b)
        self._assert_owned_tabs((self.a, self.b))

    def _disabled_return(self, rtl):
        self._configure(rtl)
        self._activate(self.a)
        self._activate(self.disabled)
        self._activate(self.b)
        self._assert_owned_tabs((self.a, self.b))

    def _disabled_refresh(self, rtl):
        self._configure(rtl)
        self._activate(self.a)
        self._activate(self.disabled)
        self._register(self.c)
        self._assert_owned_tabs((self.a, self.b, self.c))
        self._activate(self.b)

    def _cleanup(self):
        # Prevent the already-under-test selector bug from contaminating teardown.
        blockers = [QtCore.QSignalBlocker(widget) for widget in
                    Gui.getMainWindow().findChildren(QtWidgets.QTabBar)]
        try:
            if self.previous_workbench in Gui.listWorkbenches():
                Gui.activateWorkbench(self.previous_workbench)
            for name in list(App.listDocuments()):
                if name not in self.initial_documents:
                    App.closeDocument(name)
            if self.previous in App.listDocuments():
                App.setActiveDocument(self.previous)
            for key, value in self.original_preferences.items():
                if value is None:
                    self.params.RemString(key)
                else:
                    self.params.SetString(key, value)
            for name in reversed(self.workbenches):
                if name in Gui.listWorkbenches():
                    Gui.removeWorkbench(name)
                App.ParamGet("User parameter:BaseApp/Workbench").RemGroup(name)
            for area, params in self.areas.items():
                for key in self._integers(params):
                    params.RemInt(key)
                for key, value in self.area_values[area].items():
                    params.SetInt(key, value)
            if hasattr(self, "toolbar"):
                self.assertTrue(self._wait(
                    lambda: self.toolbar.parentWidget().objectName() == self.original_area))
            for key, value in self.original_preferences.items():
                actual = next((entry for kind, name, entry in (self.params.GetContents() or [])
                               if name == key), None)
                self.assertEqual(actual, value, "Exact selector preference restoration")
            for area, params in self.areas.items():
                self.assertEqual(self._integers(params), self.area_values[area], area)
        finally:
            blockers.clear()

    def test_ltr_ordinary_switch_control(self):
        self._ordinary(False)

    def test_rtl_ordinary_switch_control(self):
        self._ordinary(True)

    def test_ltr_disabled_then_ordinary_identity(self):
        self._disabled_return(False)

    def test_rtl_disabled_then_ordinary_identity(self):
        self._disabled_return(True)

    def test_ltr_refresh_with_disabled_tab(self):
        self._disabled_refresh(False)

    def test_rtl_refresh_with_disabled_tab(self):
        self._disabled_refresh(True)


@unittest.skipUnless(
    App.GuiUp and Gui.getMainWindow().findChildren(QtWidgets.QWidget, "WbTabBar"),
    "Workbench tab selector requires GUI mode and the tab selector configuration",
)
class TestWorkbenchSelectorBoundaries(unittest.TestCase):
    _integers = staticmethod(TestWorkbenchSelectorNative._integers)
    _wait = staticmethod(TestWorkbenchSelectorNative._wait)
    _assert_model = TestWorkbenchSelectorNative._assert_model
    _register = TestWorkbenchSelectorNative._register
    _configure = TestWorkbenchSelectorNative._configure
    _assert_owned_tabs = TestWorkbenchSelectorNative._assert_owned_tabs
    _activate = TestWorkbenchSelectorNative._activate
    _cleanup = TestWorkbenchSelectorNative._cleanup

    def setUp(self):
        TestWorkbenchSelectorNative.setUp(self)
        self.activation_events = []
        self.signal_callback = lambda name: self.activation_events.append(str(name))
        Gui.getMainWindow().workbenchActivated.connect(self.signal_callback)
        self.addCleanup(Gui.getMainWindow().workbenchActivated.disconnect, self.signal_callback)

    def _enabled_rows(self, *temporary_names):
        return [self.tabs.tabText(index) for index in range(self.tabs.count())
                if self.tabs.tabText(index) not in temporary_names]

    def _all_row_order(self, expected, *temporary_names):
        with self.subTest(oracle="all_enabled_rows_and_order_preserved"):
            self.assertEqual(self._enabled_rows(*temporary_names), expected)

    def _owned_order(self, expected):
        texts = [self.tabs.tabText(index) for index in range(self.tabs.count())]
        actual = [name for name in texts if name in (self.a, self.b, self.c)]
        self.assertEqual(actual, list(expected), texts)
        self._assert_owned_tabs(expected)

    def _activate_once(self, name):
        self.activation_events.clear()
        self._activate(name)
        with self.subTest(oracle="no_extra_native_activation", requested=name):
            self.assertEqual(self.activation_events, [name])

    def _tab_index(self, name):
        indices = [index for index in range(self.tabs.count()) if self.tabs.tabText(index) == name]
        self.assertEqual(len(indices), 1, "Real enabled/temporary tab must exist exactly once: " + name)
        return indices[0]

    def _click_tab(self, name):
        index = self._tab_index(name)
        for attempt in range(40):
            center = self.tabs.tabRect(index).center()
            if (self.tabs.rect().contains(center) and self.tabs.tabAt(center) == index
                    and self.tabs.childAt(center) is None):
                break
            preferred = "ScrollLeftButton" if center.x() < self.tabs.rect().center().x() else "ScrollRightButton"
            buttons = [button for button in self.tabs.findChildren(QtWidgets.QToolButton)
                       if button.isVisible() and button.isEnabled()
                       and button.objectName() in ("ScrollLeftButton", "ScrollRightButton")]
            self.assertTrue(buttons, "An offscreen real tab needs a native enabled scroll button")
            button = next((button for button in buttons if button.objectName() == preferred), buttons[0])
            QtTest.QTest.mouseClick(button, QtCore.Qt.LeftButton)
            QtWidgets.QApplication.processEvents()
        else:
            self.fail("The requested real tab did not become clickable through its scroll controls")
        self.activation_events.clear()
        QtTest.QTest.mouseClick(self.tabs, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, center)
        reached = self._wait(lambda: Gui.activeWorkbench().name() == name)
        print("SELECTOR_USER_TAB", json.dumps({"test": self.id(), "requested": name,
              "actual": Gui.activeWorkbench().name(), "signals": self.activation_events}), flush=True)
        with self.subTest(oracle="actual_clicked_target", requested=name):
            self.assertTrue(reached)
            self.assertEqual(Gui.activeWorkbench().name(), name)
        with self.subTest(oracle="one_native_activation_for_user_click", requested=name):
            self.assertEqual(self.activation_events, [name])
        self._assert_model()

    def _two_disabled(self, rtl):
        self._configure(rtl)
        second = self.disabled + "Second"
        self.params.SetString("Disabled", self.params.GetString("Disabled") + "," + second)
        self._register(second)
        before = self._enabled_rows()
        self._activate_once(self.a)
        self._activate_once(self.disabled)
        self._activate_once(second)
        texts = [self.tabs.tabText(index) for index in range(self.tabs.count())]
        with self.subTest(oracle="replacement_has_one_temporary_tab"):
            self.assertEqual(texts.count(second), 1)
            self.assertNotIn(self.disabled, texts)
        self._owned_order((self.a, self.b))
        self._all_row_order(before, self.disabled, second)
        self._activate_once(self.b)
        with self.subTest(oracle="ordinary_switch_removes_temporary_tab"):
            self.assertNotIn(second, [self.tabs.tabText(index) for index in range(self.tabs.count())])
        self._owned_order((self.a, self.b))

        self._all_row_order(before)
    def _ordinary_clicks(self, rtl):
        self._configure(rtl)
        before = self._enabled_rows()
        self._activate_once(self.a)
        self._click_tab(self.b)
        self._click_tab(self.a)
        self._owned_order((self.a, self.b))

        self._all_row_order(before)
    def _disabled_click(self, rtl):
        self._configure(rtl)
        before = self._enabled_rows()
        self._activate_once(self.a)
        self._activate_once(self.disabled)
        self._click_tab(self.b)
        self._owned_order((self.a, self.b))
        with self.subTest(oracle="clicked_ordinary_removes_temporary_tab"):
            self.assertNotIn(self.disabled, [self.tabs.tabText(index) for index in range(self.tabs.count())])

        self._all_row_order(before)
    def _add_remove_refresh(self, rtl):
        self._configure(rtl)
        before = self._enabled_rows()
        self.assertEqual(before[:2], [self.a, self.b])
        self._activate_once(self.a)
        self._activate_once(self.disabled)
        self.activation_events.clear()
        self._register(self.c)
        with self.subTest(oracle="add_refresh_preserves_active_identity"):
            self.assertEqual(Gui.activeWorkbench().name(), self.disabled)
            self.assertEqual(self.activation_events, [])
        self._owned_order((self.a, self.b, self.c))
        self._all_row_order(before[:2] + [self.c] + before[2:], self.disabled)
        with self.subTest(oracle="add_refresh_preserves_one_temporary_tab"):
            self.assertEqual([self.tabs.tabText(index) for index in range(self.tabs.count())].count(self.disabled), 1)
        self.activation_events.clear()
        Gui.removeWorkbench(self.c)
        with self.subTest(oracle="real_workbench_removal"):
            self.assertNotIn(self.c, Gui.listWorkbenches())
            self.assertNotIn(self.c, [self.tabs.tabText(index) for index in range(self.tabs.count())])
        with self.subTest(oracle="remove_refresh_preserves_active_identity"):
            self.assertEqual(Gui.activeWorkbench().name(), self.disabled)
            self.assertEqual(self.activation_events, [])
        self._owned_order((self.a, self.b))
        self._all_row_order(before, self.disabled)
        self._activate_once(self.b)

        self._all_row_order(before)
    def _initialize_refresh(self, rtl):
        self._configure(rtl)
        observations = []
        row_observations = []
        transient = self.c + "Transient"

        def initialize(workbench):
            workbench.appendToolbar(self.c + "_Toolbar", ["Std_ViewFitAll"])
            self._register(transient)
            observations.append(("added", transient in Gui.listWorkbenches(),
                                 [self.tabs.tabText(index) for index in range(self.tabs.count())].count(transient)))
            row_observations.append(self._enabled_rows(self.disabled, transient))
            Gui.removeWorkbench(transient)
            observations.append(("removed", transient in Gui.listWorkbenches(),
                                 [self.tabs.tabText(index) for index in range(self.tabs.count())].count(transient)))
            row_observations.append(self._enabled_rows(self.disabled, transient))

        cls = type(self.c, (Gui.Workbench,), {
            "MenuText": self.c, "ToolTip": self.c, "Initialize": initialize,
            "GetClassName": lambda workbench: "Gui::PythonWorkbench",
        })
        self.workbenches.append(self.c)
        Gui.addWorkbench(cls())
        before = self._enabled_rows()
        self._activate_once(self.a)
        self._activate_once(self.disabled)
        self._click_tab(self.c)
        with self.subTest(oracle="genuine_initializer_refresh_is_not_suppressed"):
            self.assertEqual(observations, [("added", True, 1), ("removed", False, 0)])
        with self.subTest(oracle="initializer_refresh_retains_every_other_enabled_row"):
            self.assertEqual(row_observations, [before, before])
        self._owned_order((self.a, self.b, self.c))
        self._all_row_order(before)
        with self.subTest(oracle="initializer_completion_keeps_actual_target"):
            self.assertEqual(Gui.activeWorkbench().name(), self.c)

    def test_ltr_replace_two_disabled_workbenches(self):
        self._two_disabled(False)

    def test_rtl_replace_two_disabled_workbenches(self):
        self._two_disabled(True)

    def test_ltr_real_ordinary_tab_clicks_control(self):
        self._ordinary_clicks(False)

    def test_rtl_real_ordinary_tab_clicks_control(self):
        self._ordinary_clicks(True)

    def test_ltr_real_tab_click_from_disabled_workbench(self):
        self._disabled_click(False)

    def test_rtl_real_tab_click_from_disabled_workbench(self):
        self._disabled_click(True)

    def test_ltr_add_and_remove_real_workbench_while_disabled(self):
        self._add_remove_refresh(False)

    def test_rtl_add_and_remove_real_workbench_while_disabled(self):
        self._add_remove_refresh(True)

    def test_ltr_real_click_initializer_can_refresh_workbenches(self):
        self._initialize_refresh(False)

    def test_rtl_real_click_initializer_can_refresh_workbenches(self):
        self._initialize_refresh(True)


    def _move_with_disabled_tab(self, rtl):
        self._configure(rtl)
        before = self._enabled_rows()
        self._activate_once(self.a)
        self._activate_once(self.disabled)
        self.activation_events.clear()
        for params in self.areas.values():
            params.RemInt("Workbench")
        target = "MenuBarLeft" if rtl else "MenuBarRight"
        positions = self._integers(self.areas[target])
        self.areas[target].SetInt("Workbench", max(positions.values(), default=-1) + 1)
        self.assertTrue(self._wait(
            lambda: self.toolbar.parentWidget().objectName() == target + "Area"))
        self.assertTrue(QtCore.QMetaObject.invokeMethod(
            self.selector, "updateLayout", QtCore.Qt.DirectConnection))
        expected_direction = QtCore.Qt.LeftToRight if rtl else QtCore.Qt.RightToLeft
        self.assertEqual(self.selector.property("direction"), expected_direction)
        print("SELECTOR_DIRECTION_MOVE", json.dumps({
            "test": self.id(), "actual": Gui.activeWorkbench().name(),
            "direction": str(self.selector.property("direction")),
            "rows": self._enabled_rows(), "current": self.tabs.currentIndex(),
            "signals": self.activation_events,
        }), flush=True)
        with self.subTest(oracle="ordinary_toolbar_move_does_not_activate_workbench"):
            self.assertEqual(Gui.activeWorkbench().name(), self.disabled)
            self.assertEqual(self.activation_events, [])
        expected_index = self.tabs.count() - 1 if rtl else 0
        with self.subTest(oracle="temporary_tab_tracks_actual_new_side"):
            self.assertEqual(self._tab_index(self.disabled), expected_index)
        with self.subTest(oracle="selected_tab_matches_active_workbench_after_move"):
            self.assertEqual(self.tabs.tabText(self.tabs.currentIndex()), self.disabled)
        self._all_row_order(before, self.disabled)
        self._click_tab(self.b)
        self._all_row_order(before)

    def test_move_ltr_to_rtl_with_active_disabled_tab(self):
        self._move_with_disabled_tab(False)

    def test_move_rtl_to_ltr_with_active_disabled_tab(self):
        self._move_with_disabled_tab(True)


if __name__ == "__main__":
    unittest.main()
