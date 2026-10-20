# SPDX-License-Identifier: LGPL-2.1-or-later
"""Selection View search preserves result identity through document lifecycle changes.

These tests retain the existing empty-search workflow while checking genuine
public widget actions, live geometry, document/object identity, and callbacks.
"""

import json

import time

import unittest

import FreeCAD as App

import FreeCADGui as Gui

import Part

from PySide import QtCore, QtGui, QtWidgets


class TestSelectionSearchDocumentIdentity(unittest.TestCase):
    needle = "UniqueOriginalNeedle"

    def setUp(self):
        self.main = Gui.getMainWindow()
        self.dock = self.main.findChild(QtWidgets.QDockWidget, "Selection view")
        self.assertIsNotNone(self.dock)
        self.panel = self.dock.widget()
        self.assertIsNotNone(self.panel)
        self.assertTrue(self.panel.inherits("Gui::DockWnd::SelectionView"),
                        self.panel.metaObject().className())
        self.was_visible = self.dock.isVisible()
        self.dock.show()
        self.dock.raise_()
        self.assertTrue(self._wait(lambda: self.panel.isVisibleTo(self.main)))
        fields = self.panel.findChildren(QtWidgets.QLineEdit)
        self.assertEqual(len(fields), 1, "Use the existing Selection View search field")
        self.field = fields[0]
        self.names = []
        self.original = self._document("OriginalSearchDocument", self.needle, (10, 20, 30))
        self.other = self._document("OtherSearchDocument", "DistinctUnmatchedObject", (40, 50, 60))
        self.identities = {doc.Name: str(doc.Uid) for doc in (self.original, self.other)}
        self.assertNotEqual(self.identities[self.original.Name], self.identities[self.other.Name])
        self.assertEqual(self.original.Box.Name, self.other.Box.Name)
        self.assertNotEqual(self.original.Box.Shape.Volume, self.other.Box.Shape.Volume)
        self.assertNotIn(self.needle, self.other.Box.Label)
        self.field.clear()
        Gui.Selection.clearSelection()
        App.setActiveDocument(self.original.Name)
        self._events()
        self.assertEqual(App.ActiveDocument, self.original)
        self.assertEqual(Gui.activeDocument().Document, self.original)
        self.assertEqual(self._selected(), [])
        self.assertEqual(self.field.text(), "")
        self._record("initial")

    def tearDown(self):
        Gui.Selection.clearSelection()
        if hasattr(self, "field"):
            # An ordinary no-match query clears native results before their
            # owning documents close, keeping later cases independent.
            self.field.setText("__SelectionSearchCleanupNoMatchingLabel__")
            self._events()
            self.field.clear()
        for name in reversed(getattr(self, "names", [])):
            if name in App.listDocuments():
                App.closeDocument(name)
        if hasattr(self, "was_visible"):
            self.dock.setVisible(self.was_visible)
        self._events()

    @staticmethod
    def _events(milliseconds=30):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(milliseconds, loop.quit)
        loop.exec_()

    def _wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                return False
            self._events()
        return True

    def _document(self, name, label, dimensions):
        doc = App.newDocument(name)
        self.names.append(doc.Name)
        box = doc.addObject("Part::Box", "Box")
        box.Label = label
        box.Length, box.Width, box.Height = dimensions
        doc.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertAlmostEqual(box.Shape.Volume, dimensions[0] * dimensions[1] * dimensions[2])
        return doc

    def _rows(self):
        rows = []
        for listing in self.panel.findChildren(QtWidgets.QListWidget):
            if not listing.isVisibleTo(self.main):
                continue
            for index in range(listing.count()):
                item = listing.item(index)
                data = item.data(QtCore.Qt.UserRole)
                rows.append({"text": item.text(), "identity": list(data) if data else []})
        return rows

    @staticmethod
    def _selected():
        # '*' explicitly queries all documents instead of the current one.
        return [(selection.DocumentName, selection.ObjectName,
                 tuple(selection.SubElementNames))
                for selection in Gui.Selection.getSelectionEx("*", 0)]

    def _record(self, stage):
        print("SELECTION_SEARCH_IDENTITY", json.dumps({
            "stage": stage,
            "active": App.ActiveDocument.Name if App.ActiveDocument else None,
            "search_text": self.field.text(),
            "rows": self._rows(),
            "selected": self._selected(),
            "documents": [{"name": doc.Name, "uid": str(doc.Uid),
                           "object_name": doc.Box.Name, "label": doc.Box.Label,
                           "volume": doc.Box.Shape.Volume}
                          for doc in (self.original, self.other)],
        }, sort_keys=True), flush=True)

    def _search_original(self):
        self.field.setFocus(QtCore.Qt.OtherFocusReason)
        self.field.setText(self.needle)
        self.assertTrue(self._wait(lambda: [row["identity"][:2] for row in self._rows()]
                                  == [[self.original.Name, self.original.Box.Name]]),
                        "An actual search must show the original document's unique object")
        self.assertEqual(self._selected(), [])
        self._record("searched_original")

    def _return(self):
        self.field.setFocus(QtCore.Qt.OtherFocusReason)
        self._events()
        self.assertTrue(self.field.hasFocus(), "Return must reach the actual search editor")
        for event_type in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            event = QtGui.QKeyEvent(event_type, QtCore.Qt.Key_Return,
                                   QtCore.Qt.NoModifier, "\r")
            QtWidgets.QApplication.sendEvent(self.field, event)
        self._events()
        self._record("after_return")

    def _switch_to_other(self):
        App.setActiveDocument(self.other.Name)
        self._events()
        self.assertEqual(App.ActiveDocument, self.other)
        self.assertEqual(Gui.activeDocument().Document, self.other)
        self.assertEqual(str(self.original.Uid), self.identities[self.original.Name])
        self.assertEqual(str(self.other.Uid), self.identities[self.other.Name])
        self.assertTrue(self.original.Box.Shape.isValid())
        self.assertTrue(self.other.Box.Shape.isValid())
        self._record("switched_to_other")

    def _assert_no_wrong_document_selection(self):
        selections = self._selected()
        self.assertFalse(any(name == self.other.Name for name, _, _ in selections),
                         "The same-named unmatched object in the other document must not be selected")
        self.assertTrue(all((name, obj) == (self.original.Name, self.original.Box.Name)
                            for name, obj, _ in selections),
                        "A retained visible search row can only refer to its original identity")

    def test_fresh_empty_search_return_control(self):
        self.assertEqual(self._rows(), [])
        self._return()
        self.assertEqual(self._selected(), [])

    def test_nonempty_search_same_document_return_control(self):
        self._search_original()
        self._return()
        self.assertEqual(self._selected(), [(self.original.Name, self.original.Box.Name, ())])

    def test_cleared_search_same_document_return_control(self):
        self._search_original()
        before = self._rows()
        self.field.clear()
        self._events()
        self.assertEqual(self.field.text(), "")
        self._record("cleared_same_document")
        # Qualify the existing empty-field behavior without prescribing whether
        # clearing should retain results, restore selection, or clear the list.
        print("SELECTION_SEARCH_EMPTY_ROWS_RETAINED", self._rows() == before, flush=True)
        self._return()
        self._assert_no_wrong_document_selection()

    def test_nonempty_search_document_switch_preserves_target_identity(self):
        self._search_original()
        self._switch_to_other()
        self._return()
        self._assert_no_wrong_document_selection()

    def test_cleared_search_document_switch_preserves_target_identity(self):
        self._search_original()
        self.field.clear()
        self._events()
        self.assertEqual(self.field.text(), "")
        self._record("cleared_before_switch")
        self._switch_to_other()
        self._return()
        self._assert_no_wrong_document_selection()


class _MessageObserver(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.messages = []

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.Show and isinstance(watched, QtWidgets.QMessageBox):
            self.messages.append(watched.text())
        return False


class TestSelectionSearchLifecycle(unittest.TestCase):
    needle = TestSelectionSearchDocumentIdentity.needle
    _events = staticmethod(TestSelectionSearchDocumentIdentity._events)
    _wait = TestSelectionSearchDocumentIdentity._wait
    _document = TestSelectionSearchDocumentIdentity._document
    _rows = TestSelectionSearchDocumentIdentity._rows
    _selected = staticmethod(TestSelectionSearchDocumentIdentity._selected)
    _search_original = TestSelectionSearchDocumentIdentity._search_original
    _return = TestSelectionSearchDocumentIdentity._return

    def setUp(self):
        TestSelectionSearchDocumentIdentity.setUp(self)
        self.original_name = self.original.Name
        self.other_name = self.other.Name
        self.reports = [(widget, widget.toPlainText())
                        for widget in self.main.findChildren(QtWidgets.QTextEdit)
                        if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.assertTrue(self.reports)
        self.message_observer = _MessageObserver()
        QtWidgets.QApplication.instance().installEventFilter(self.message_observer)

    def tearDown(self):
        try:
            TestSelectionSearchDocumentIdentity.tearDown(self)
            self._assert_quiet()
        finally:
            QtWidgets.QApplication.instance().removeEventFilter(self.message_observer)

    def _assert_quiet(self):
        outputs = []
        for widget, before in self.reports:
            after = widget.toPlainText()
            outputs.append(after[len(before):] if after.startswith(before) else after)
        output = "\n".join(outputs + self.message_observer.messages).lower()
        for forbidden in ("access violation", "pyexception", "traceback", "valueerror"):
            self.assertNotIn(forbidden, output)

    def _record(self, stage):
        # Closed document/object wrappers are never consulted by diagnostics.
        existing = App.listDocuments()
        documents = []
        for name in getattr(self, "names", []):
            doc = existing.get(name)
            if doc is None:
                documents.append({"name": name, "present": False})
                continue
            box = doc.getObject("Box")
            documents.append({"name": name, "uid": str(doc.Uid), "present": True,
                              "box": None if box is None else {
                                  "id": box.ID, "name": box.Name, "label": box.Label,
                                  "volume": box.Shape.Volume}})
        print("SELECTION_SEARCH_LIFECYCLE", json.dumps({
            "stage": stage,
            "active": App.ActiveDocument.Name if App.ActiveDocument else None,
            "text": self.field.text(), "rows": self._rows(),
            "selected": self._selected(), "documents": documents,
        }, sort_keys=True), flush=True)

    def _box(self, doc, name="Box", label=None, dimensions=(10, 20, 30)):
        box = doc.addObject("Part::Box", name)
        box.Label = self.needle if label is None else label
        box.Length, box.Width, box.Height = dimensions
        doc.recompute()
        self.assertTrue(box.Shape.isValid())
        self.assertAlmostEqual(box.Shape.Volume, dimensions[0] * dimensions[1] * dimensions[2])
        self.assertIs(doc.getObject(box.ID), box)
        return box

    def test_multiple_live_results_same_document_control(self):
        second = self._box(self.original, "SecondBox", self.needle + " Two", (4, 5, 6))
        self.field.setText(self.needle.lower())
        self._events()
        expected = [(self.original_name, self.original.Box.Name, ()),
                    (self.original_name, second.Name, ())]
        self.assertCountEqual([tuple(row["identity"][:2]) for row in self._rows()],
                              [item[:2] for item in expected])
        self._return()
        self.assertCountEqual(self._selected(), expected)
        self._assert_quiet()

    def test_changed_label_retains_original_result_identity_control(self):
        self._search_original()
        original_id = self.original.Box.ID
        self.original.Box.Label = "ChangedAfterTheSearch"
        self.assertNotIn(self.needle, self.original.Box.Label)
        self._return()
        self.assertEqual(self._selected(), [(self.original_name, "Box", ())])
        self.assertEqual(self.original.getObject(original_id), self.original.Box)
        self._assert_quiet()

    def test_deleted_result_then_same_name_object_does_not_retarget(self):
        self.original.UndoMode = 0
        self._search_original()
        original_id = self.original.Box.ID
        self.original.removeObject("Box")
        self.assertIsNone(self.original.getObject(original_id))
        replacement = self._box(self.original, label="UnmatchedReplacement", dimensions=(7, 8, 9))
        self.assertEqual(replacement.Name, "Box")
        self.assertNotEqual(replacement.ID, original_id)
        Gui.Selection.clearSelection()
        self._return()
        self.assertEqual(self._selected(), [], "The deleted result must not retarget a same-name object")
        self._assert_quiet()

    def test_deleted_result_undo_restores_original_identity_control(self):
        self.original.UndoMode = 1
        self.original.clearUndos()
        self._search_original()
        original_id = self.original.Box.ID
        self.original.openTransaction("Delete searched Box")
        self.original.removeObject("Box")
        self.original.commitTransaction()
        self.assertIsNone(self.original.getObject(original_id))
        self._return()
        self.assertEqual(self._selected(), [], "A currently removed result must be skipped")
        self.original.undo()
        self.original.recompute()
        self.assertEqual(self.original.Box.ID, original_id)
        self.assertIs(self.original.getObject(original_id), self.original.Box)
        self._return()
        self.assertEqual(self._selected(), [(self.original_name, "Box", ())])
        self._assert_quiet()

    def test_closed_document_same_name_recreation_does_not_retarget(self):
        self._search_original()
        original_uid = str(self.original.Uid)
        App.closeDocument(self.original_name)
        self.assertNotIn(self.original_name, App.listDocuments())
        replacement = self._document(self.original_name, "UnmatchedReplacement", (7, 8, 9))
        self.assertEqual(replacement.Name, self.original_name)
        self.assertNotEqual(str(replacement.Uid), original_uid)
        Gui.Selection.clearSelection()
        self._return()
        self.assertEqual(self._selected(), [], "A closed document's result must not target its namesake")
        self._assert_quiet()

    def test_cleared_document_reused_object_id_does_not_retarget(self):
        # Ordinary clearDocument resets the ID map while retaining the App doc.
        self.original.clearDocument()
        first = self._box(self.original)
        App.setActiveDocument(self.original_name)
        self.assertEqual(App.ActiveDocument, self.original)
        original_id = first.ID
        self._search_original()
        self.original.clearDocument()
        replacement = self._box(self.original, label="UnmatchedReplacement", dimensions=(7, 8, 9))
        App.setActiveDocument(self.original_name)
        self.assertEqual(App.ActiveDocument, self.original)
        self.assertEqual(replacement.ID, original_id,
                         "Qualify the actual same-document ID reset before testing identity")
        Gui.Selection.clearSelection()
        self._return()
        self.assertEqual(self._selected(), [], "An ID reused after document clear is a different result")
        self._assert_quiet()


class _Observer:
    def __init__(self, action, on_add=False):
        self.action = action
        self.on_add = on_add
        self.fired = False

    def clearSelection(self, document):
        if not self.on_add and not self.fired:
            self.fired = True
            self.action()

    def addSelection(self, document, obj, subname, point):
        if self.on_add and not self.fired and obj == "Box":
            self.fired = True
            self.action()


class TestSelectionSearchReentry(unittest.TestCase):
    needle = TestSelectionSearchLifecycle.needle
    _events = staticmethod(TestSelectionSearchLifecycle._events)
    _wait = TestSelectionSearchLifecycle._wait
    _document = TestSelectionSearchLifecycle._document
    _rows = TestSelectionSearchLifecycle._rows
    _selected = staticmethod(TestSelectionSearchLifecycle._selected)
    _search_original = TestSelectionSearchLifecycle._search_original
    _return = TestSelectionSearchLifecycle._return
    _record = TestSelectionSearchLifecycle._record
    _assert_quiet = TestSelectionSearchLifecycle._assert_quiet
    _box = TestSelectionSearchLifecycle._box

    def setUp(self):
        TestSelectionSearchLifecycle.setUp(self)

    def tearDown(self):
        TestSelectionSearchLifecycle.tearDown(self)

    def test_clear_selection_observer_closes_result_document(self):
        self._search_original()
        Gui.Selection.addSelection(self.other_name, "Box")
        self.assertIn((self.other_name, "Box", ()), self._selected())
        observer = _Observer(lambda: App.closeDocument(self.original_name))
        Gui.Selection.addObserver(observer, 0)
        try:
            self._return()
            self.assertTrue(observer.fired, "The actual validation must reach clearSelection")
            self.assertNotIn(self.original_name, App.listDocuments())
            self.assertEqual(self._selected(), [])
            self._assert_quiet()
        finally:
            Gui.Selection.removeObserver(observer)

    def test_first_add_observer_deletes_next_result(self):
        self.original.UndoMode = 0
        second = self._box(self.original, "SecondBox", self.needle + " Two", (4, 5, 6))
        second_id = second.ID
        self.field.setText(self.needle)
        self._events()
        self.assertEqual([row["identity"][:2] for row in self._rows()],
                         [[self.original_name, "Box"], [self.original_name, "SecondBox"]])
        observer = _Observer(lambda: self.original.removeObject("SecondBox"), on_add=True)
        Gui.Selection.addObserver(observer, 0)
        try:
            self._return()
            self.assertTrue(observer.fired, "The first real selection add must trigger the observer")
            self.assertIsNone(self.original.getObject(second_id))
            self.assertEqual(self._selected(), [(self.original_name, "Box", ())])
            self._assert_quiet()
        finally:
            Gui.Selection.removeObserver(observer)
