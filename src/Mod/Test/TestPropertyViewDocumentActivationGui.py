# SPDX-License-Identifier: LGPL-2.1-or-later
"""Keep the selected owner's property model available after document activation.

Regression coverage for https://github.com/FreeCAD/FreeCAD/issues/33356.
"""

import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


@unittest.skipIf(not App.GuiUp, "Requires ordinary native document activation")
class TestPropertyViewDocumentActivationGui(unittest.TestCase):
    preference_name = "EnablePropertyViewForInactiveDocument"

    def setUp(self):
        self.assertEqual(App.listDocuments(), {}, "Run in an isolated native GUI process")
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        self.names = []
        self.parameters = App.ParamGet("User parameter:BaseApp/Preferences/View")
        self.preference_before = self._preference_state()
        self.tab_parameters = App.ParamGet("User parameter:BaseApp/Preferences/PropertyView")
        self.tab_parameter_before = [
            tuple(entry)
            for entry in self.tab_parameters.GetContents() or []
            if entry[0] == "Integer" and entry[1] == "LastTabIndex"
        ]
        self.previous_tab = None
        self.main = Gui.getMainWindow()
        areas = self.main.findChildren(QtWidgets.QMdiArea)
        self.assertEqual(len(areas), 1)
        self.area = areas[0]
        self.initial_windows = tuple(self.area.subWindowList())
        self.owned_windows = {}
        self.addCleanup(self._assert_initial_windows_preserved)
        self.addCleanup(self._cleanup)
        self.workbench_before = Gui.activeWorkbench().name()
        self.reports = [
            (widget, widget.toPlainText())
            for widget in self.main.findChildren(QtWidgets.QTextEdit)
            if widget.inherits("Gui::DockWnd::ReportOutput")
        ]
        self.assertTrue(self.reports, "Actual native Report output must be available")
        self.timer_delay = self.parameters.GetUnsigned("PropertyViewTimer", 100)
        self.assertLessEqual(self.timer_delay, 1000, "Use an ordinary property refresh interval")
        data_views = self.main.findChildren(QtWidgets.QTreeView, "propertyEditorData")
        candidates = []
        for data in data_views:
            parent = data.parentWidget()
            while parent is not None and not parent.inherits("Gui::PropertyView"):
                parent = parent.parentWidget()
            if parent is not None and parent.isVisibleTo(self.main):
                candidates.append((parent, data))
        self.assertEqual(len(candidates), 1, "One visible ordinary property pane is required")
        self.panel, self.data = candidates[0]
        self.view = self.panel.findChild(QtWidgets.QTreeView, "propertyEditorView")
        self.assertIsNotNone(self.view)
        tabs = [
            widget
            for widget in self.panel.findChildren(QtWidgets.QTabWidget)
            if widget.indexOf(self.data) >= 0
        ]
        self.assertEqual(len(tabs), 1)
        self.tabs = tabs[0]
        self.previous_tab = self.tabs.currentIndex()
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.data))
        self._settle()
        self.assertTrue(self.data.isVisibleTo(self.main))
        self.owner = self._new_document("PropertyOwner33356")
        owner_windows = [
            window for window in self.area.subWindowList() if window not in self.initial_windows
        ]
        self.assertEqual(len(owner_windows), 1, "The first owned document must create one window")
        self.owned_windows[self.owner.Name] = owner_windows[0]
        self.assertIn(self.owner.Label, owner_windows[0].widget().windowTitle())
        self.variables = self.owner.addObject("App::VarSet", "Variables")
        self.variables.addProperty("App::PropertyInteger", "Marker", "Values")
        self.variables.Marker = 37
        self.variables.Label = "Selected variables33356"
        self.other = self.owner.addObject("App::VarSet", "OtherVariables")
        self.other.addProperty("App::PropertyInteger", "Marker", "Values")
        self.other.Marker = 61
        self.other.Label = "Other variables33356"
        self.owner.recompute()
        self.peer = self._new_document("PropertyPeer33356")
        self.peer.addObject("App::VarSet", "PeerVariables")
        self.peer.recompute()
        current_windows = list(self.area.subWindowList())
        new_windows = [window for window in current_windows if window not in self.initial_windows]
        self.assertEqual(len(new_windows), 2, "Exactly two new owned document windows are required")
        peer_windows = [window for window in new_windows if window not in owner_windows]
        self.assertEqual(len(peer_windows), 1, "The second owned document must create one window")
        self.owned_windows[self.peer.Name] = peer_windows[0]
        self.assertIn(self.peer.Label, peer_windows[0].widget().windowTitle())
        self.assertCountEqual(new_windows, list(self.owned_windows.values()))
        self.assertTrue(all(window in current_windows for window in self.initial_windows))
        self._activate(self.owner.Name)
        self.owner.clearUndos()
        self.peer.clearUndos()

    def _assert_initial_windows_preserved(self):
        self.assertCountEqual(self.area.subWindowList(), self.initial_windows)

    def _preference_state(self):
        return [
            tuple(entry)
            for entry in self.parameters.GetContents() or []
            if entry[0] == "Boolean" and entry[1] == self.preference_name
        ]

    def _cleanup(self):
        try:
            Gui.Selection.clearSelection()
            for name in reversed(self.names):
                if name not in App.listDocuments():
                    continue
                owner_gui = Gui.getDocument(name)
                task = Gui.Control.activeTaskDialog(owner_gui)
                if task is not None:
                    task.reject()
                if owner_gui.getInEdit() is not None:
                    owner_gui.resetEdit()
                self.assertIsNone(owner_gui.getInEdit())
                self.assertIsNone(Gui.Control.activeTaskDialog(owner_gui))
                App.closeDocument(name)
                self.assertNotIn(name, App.listDocuments())
        finally:
            if self.preference_before:
                self.parameters.SetBool(self.preference_name, self.preference_before[0][2])
            else:
                self.parameters.RemBool(self.preference_name)
            self.assertEqual(self._preference_state(), self.preference_before)
            if self.previous_tab is not None:
                self.tabs.setCurrentIndex(self.previous_tab)
            if self.tab_parameter_before:
                self.tab_parameters.SetInt("LastTabIndex", self.tab_parameter_before[0][2])
            else:
                self.tab_parameters.RemInt("LastTabIndex")
            self.assertEqual(
                [
                    tuple(entry)
                    for entry in self.tab_parameters.GetContents() or []
                    if entry[0] == "Integer" and entry[1] == "LastTabIndex"
                ],
                self.tab_parameter_before,
            )
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
            Gui.updateGui()
        self.assertEqual(App.listDocuments(), {})
        self.assertEqual(Gui.Selection.getSelectionEx("*"), [])
        if hasattr(self, "workbench_before"):
            self.assertEqual(Gui.activeWorkbench().name(), self.workbench_before)
        if hasattr(self, "reports"):
            self._assert_no_report_error()

    def _new_document(self, label):
        document = App.newDocument(label)
        self.names.append(document.Name)
        self._settle()
        return document

    def _events(self, milliseconds=25):
        Gui.updateGui()
        QtTest.QTest.qWait(milliseconds)
        Gui.updateGui()

    def _settle(self):
        self._events(max(150, 2 * self.timer_delay + 50))

    def _wait(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._events()
        return True

    def _activate(self, name):
        target = self.owned_windows[name]
        windows = list(self.area.subWindowList())
        self.assertIn(target, windows)
        self.assertTrue(all(window in windows for window in self.initial_windows))
        for _ in range(len(windows)):
            if self.area.activeSubWindow() is target:
                break
            self.assertTrue(Gui.Command.get("Std_ActivateNextWindow").isActive())
            Gui.runCommand("Std_ActivateNextWindow", 0)
            self.assertTrue(self.panel.isVisibleTo(self.main))
            self.assertTrue(self.data.isVisibleTo(self.main))
            self._settle()
            self.assertTrue(self.panel.isVisibleTo(self.main))
            self.assertTrue(self.data.isVisibleTo(self.main))
        self.assertIs(self.area.activeSubWindow(), target)
        self.assertIsNotNone(App.ActiveDocument)
        self.assertIsNotNone(Gui.activeDocument())
        self.assertEqual(App.ActiveDocument.Name, name)
        self.assertEqual(Gui.activeDocument().Document.Name, name)
        active = self.area.activeSubWindow() if hasattr(self, "area") else None
        if active is not None:
            self.assertIn(App.getDocument(name).Label, active.widget().windowTitle())
        self.assertTrue(self.panel.isVisibleTo(self.main))
        self.assertTrue(self.data.isVisibleTo(self.main))

    def _selection(self):
        return [
            (entry.DocumentName, entry.ObjectName, tuple(entry.SubElementNames))
            for entry in Gui.Selection.getSelectionEx("*")
        ]

    def _find(self, model, label, parent=QtCore.QModelIndex() if App.GuiUp else None):
        for row in range(model.rowCount(parent)):
            name = model.index(row, 0, parent)
            if model.data(name, QtCore.Qt.DisplayRole) == label:
                return model.index(row, 1, parent)
            found = self._find(model, label, name)
            if found.isValid():
                return found
        return QtCore.QModelIndex()

    def _shows(self, obj):
        model = self.data.model()
        label = self._find(model, "Label")
        marker = self._find(model, "Marker")
        return (
            label.isValid()
            and marker.isValid()
            and model.data(label, QtCore.Qt.EditRole) == obj.Label
            and model.data(marker, QtCore.Qt.EditRole) == obj.Marker
        )

    def _select(self, obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)
        self.assertTrue(self._wait(lambda: self._shows(obj)))
        self.assertTrue(self.panel.isEnabled())
        self.assertEqual(self._selection(), [(self.owner.Name, obj.Name, ())])

    def _configure(self, inactive_enabled):
        self.parameters.SetBool(self.preference_name, inactive_enabled)
        self._activate(self.owner.Name)
        self._select(self.variables)
        self.assertEqual(self.variables.Marker, 37)
        self.assertEqual(self.other.Marker, 61)
        self.assertFalse(self.owner.HasPendingTransaction)
        self.assertFalse(self.peer.HasPendingTransaction)

    def _assert_no_report_error(self):
        for widget, before in self.reports:
            after = widget.toPlainText()
            delta = after[len(before) :] if after.startswith(before) else after
            self.assertNotIn("Traceback", delta)
            self.assertNotIn("pyException", delta)
            self.assertNotIn("RuntimeError", delta)

    @staticmethod
    def _property_count(model):
        # Clearing the native model preserves its empty property groups.
        return sum(model.rowCount(model.index(row, 0)) for row in range(model.rowCount()))

    def _away(self, inactive_enabled):
        before = self._selection()
        self._activate(self.peer.Name)
        self.assertEqual(self._selection(), before, "Document activation must not reselect")
        self.assertEqual(self._property_count(self.data.model()), 0)
        self.assertEqual(self._property_count(self.view.model()), 0)
        self.assertEqual(self.panel.isEnabled(), inactive_enabled)
        return before

    def _return_same_selection(self, inactive_enabled):
        self._configure(inactive_enabled)
        before = self._away(inactive_enabled)
        self._activate(self.owner.Name)
        self.assertEqual(self._selection(), before)
        self.assertTrue(
            self._wait(lambda: self._shows(self.variables)),
            "Returning to the selected owner must refresh its visible property model",
        )
        self.assertTrue(self.panel.isEnabled())
        self.assertEqual(self.variables.Marker, 37)
        self.assertEqual(self.other.Marker, 61)
        self.assertEqual(self.owner.UndoNames, [])
        self.assertEqual(self.peer.UndoNames, [])
        self.assertFalse(self.owner.HasPendingTransaction)
        self.assertFalse(self.peer.HasPendingTransaction)
        for name in self.names:
            self.assertIsNone(Gui.getDocument(name).getInEdit())
            self.assertIsNone(Gui.Control.activeTaskDialog(Gui.getDocument(name)))
        self._assert_no_report_error()

    def _mixed_selection_stays_cleared(self, inactive_enabled):
        self._configure(inactive_enabled)
        Gui.Selection.addSelection(self.peer.Name, "PeerVariables")
        self._settle()
        before = [
            (self.owner.Name, self.variables.Name, ()),
            (self.peer.Name, "PeerVariables", ()),
        ]
        self.assertEqual(self._selection(), before)
        self.assertEqual(App.ActiveDocument.Name, self.owner.Name)
        self.assertEqual(Gui.activeDocument().Document.Name, self.owner.Name)
        for name in (self.peer.Name, self.owner.Name):
            self._activate(name)
            self.assertEqual(self._selection(), before)
            self.assertEqual(self._property_count(self.data.model()), 0)
            self.assertEqual(self._property_count(self.view.model()), 0)
            self.assertTrue(self.panel.isEnabled())
        self.assertEqual(self.variables.Marker, 37)
        self.assertEqual(self.other.Marker, 61)
        self.assertFalse(self.owner.HasPendingTransaction)
        self.assertFalse(self.peer.HasPendingTransaction)
        self._assert_no_report_error()

    def test_ordinary_selection_populates_control(self):
        self._configure(False)
        self.assertTrue(self._shows(self.variables))

    def test_inactive_only_selection_stays_cleared_disabled_control(self):
        self._configure(False)
        self._away(False)

    def test_inactive_only_selection_stays_cleared_enabled_control(self):
        self._configure(True)
        self._away(True)

    def test_existing_reselection_workaround_control(self):
        self._configure(False)
        self._away(False)
        self._activate(self.owner.Name)
        self._select(self.other)
        self._select(self.variables)

    def test_mixed_owner_selection_stays_cleared_inactive_disabled_control(self):
        self._mixed_selection_stays_cleared(False)

    def test_mixed_owner_selection_stays_cleared_inactive_enabled_control(self):
        self._mixed_selection_stays_cleared(True)

    def test_same_selection_owner_return_inactive_disabled(self):
        self._return_same_selection(False)

    def test_same_selection_owner_return_inactive_enabled(self):
        self._return_same_selection(True)
