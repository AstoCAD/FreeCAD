# SPDX-License-Identifier: LGPL-2.1-or-later
"""Selection View hover and double-click preserve real object/subelement identity.

Regression coverage for https://github.com/FreeCAD/FreeCAD/issues/31165.
"""

import time
import unittest

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets


class TestSelectionViewLabelDots31165(unittest.TestCase):
    def setUp(self):
        self.main = Gui.getMainWindow()
        # DockWindowManager gives the outer QDockWidget the same objectName
        # as its content. Resolve the typed dock first, then its actual panel.
        self.dock = self.main.findChild(QtWidgets.QDockWidget, "Selection view")
        self.assertIsNotNone(self.dock, "Existing native Selection dock must be present")
        self.panel = self.dock.widget()
        self.assertIsNotNone(self.panel, "Existing native Selection panel must be present")
        self.assertTrue(self.panel.inherits("Gui::DockWnd::SelectionView"),
                        self.panel.metaObject().className())
        self.was_visible = self.dock.isVisible()
        self.dock.show()
        self.dock.raise_()
        self.assertTrue(self._wait(lambda: self.panel.isVisibleTo(self.main)))
        self.reports = [(widget, widget.toPlainText())
                        for widget in self.main.findChildren(QtWidgets.QTextEdit)
                        if widget.inherits("Gui::DockWnd::ReportOutput")]
        self.assertTrue(self.reports, "Actual Report output is required")
        Gui.Selection.clearSelection()
        self.doc = App.newDocument("SelectionLabelDots31165")
        self.box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self.assertTrue(self.box.Shape.isValid())
        self._events()

    def tearDown(self):
        Gui.Selection.clearSelection()
        if hasattr(self, "doc") and self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)
        if hasattr(self, "dock") and self.dock is not None:
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

    def _report_delta(self):
        parts = []
        for widget, before in self.reports:
            after = widget.toPlainText()
            parts.append(after[len(before):] if after.startswith(before) else after)
        return "\n".join(parts)

    def _assert_no_report_exception(self):
        delta = self._report_delta()
        self.assertNotIn("pyException", delta)
        self.assertNotIn("ValueError", delta)
        self.assertNotIn("Traceback", delta)

    def _actual_row(self, label, subname):
        self.box.Label = label
        Gui.Selection.addSelection(self.doc.Name, self.box.Name, subname)
        expected = [self.doc.Name, self.box.Name]

        def locate():
            for listing in self.panel.findChildren(QtWidgets.QListWidget):
                if not listing.isVisibleTo(self.main):
                    continue
                for index in range(listing.count()):
                    item = listing.item(index)
                    data = item.data(QtCore.Qt.UserRole)
                    if data is not None and list(data)[:2] == expected:
                        return listing, item
            return None

        self.assertTrue(self._wait(lambda: locate() is not None),
                        "Actual native selection row must be populated")
        listing, item = locate()
        self.assertIn(label, item.text())
        self.assertEqual(list(item.data(QtCore.Qt.UserRole))[:2], expected)
        if subname:
            self.assertIn("." + subname, item.text())
        listing.scrollToItem(item)
        self._events()
        return listing, item

    def _mouse(self, widget, event_type, point, button, buttons):
        event = QtGui.QMouseEvent(event_type, QtCore.QPointF(point),
                                 QtCore.QPointF(widget.mapToGlobal(point)),
                                 button, buttons, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(widget, event)

    def _hover(self, listing, item):
        Gui.Selection.clearPreselection()
        viewport = listing.viewport()
        rect = listing.visualItemRect(item)
        self.assertTrue(rect.isValid())
        self.assertTrue(viewport.rect().contains(rect.center()))
        # Enter through an actual item-free point to trigger QListWidget's
        # ordinary itemEntered signal without invoking the C++ slot directly.
        outside = QtCore.QPoint(1, viewport.height() - 2)
        self.assertFalse(rect.contains(outside))
        self._mouse(viewport, QtCore.QEvent.MouseMove, outside,
                    QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self._mouse(viewport, QtCore.QEvent.MouseMove, rect.center(),
                    QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self._events()

    def _check_hover(self, label, subname=""):
        listing, item = self._actual_row(label, subname)
        self._hover(listing, item)
        self._assert_no_report_exception()
        selection = Gui.Selection.getPreselection()
        self.assertEqual(selection.DocumentName, self.doc.Name)
        self.assertEqual(selection.ObjectName, self.box.Name)
        self.assertEqual(tuple(selection.SubElementNames), (subname,))
        selected = Gui.Selection.getSelectionEx(self.doc.Name)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].Object, self.box)
        self.assertEqual(tuple(selected[0].SubElementNames), (subname,) if subname else ())

    def _check_double_click(self, label, subname=""):
        listing, item = self._actual_row(label, subname)
        viewport = listing.viewport()
        center = listing.visualItemRect(item).center()
        self.assertTrue(viewport.rect().contains(center))
        self.assertTrue(Gui.Selection.isSelected(self.box, subname))
        self._mouse(viewport, QtCore.QEvent.MouseButtonPress, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._mouse(viewport, QtCore.QEvent.MouseButtonRelease, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self._mouse(viewport, QtCore.QEvent.MouseButtonDblClick, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._mouse(viewport, QtCore.QEvent.MouseButtonRelease, center,
                    QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self._events()
        self._assert_no_report_exception()
        self.assertFalse(Gui.Selection.isSelected(self.box, subname),
                         "Actual row double-click must remove the original selection")
        self.assertEqual(Gui.Selection.getSelectionEx(self.doc.Name), [])

    def test_dotted_label_hover(self):
        self._check_hover("Rectangle: Sheet: 06.50 x 24.375 [in]")

    def test_dotted_label_double_click(self):
        self._check_double_click("Rectangle: Sheet: 06.50 x 24.375 [in]")

    def test_ascii_label_hover_control(self):
        self._check_hover("Rectangle_02")

    def test_ascii_label_double_click_control(self):
        self._check_double_click("Rectangle_02")

    def test_face_hover_control(self):
        self._check_hover("Rectangle: Sheet: 06.50 x 24.375 [in]", "Face1")

    def test_face_double_click_control(self):
        self._check_double_click("Rectangle: Sheet: 06.50 x 24.375 [in]", "Face1")


class _SelectionObserver:
    def __init__(self):
        self.set_events = []
        self.picked_events = 0

    def setSelection(self, document):
        self.set_events.append(document)

    def pickedListChanged(self):
        self.picked_events += 1


class TestSelectionViewSpecialPaths(unittest.TestCase):
    _events = staticmethod(TestSelectionViewLabelDots31165._events)
    _wait = TestSelectionViewLabelDots31165._wait
    _mouse = TestSelectionViewLabelDots31165._mouse
    _hover = TestSelectionViewLabelDots31165._hover
    _actual_row = TestSelectionViewLabelDots31165._actual_row
    _report_delta = TestSelectionViewLabelDots31165._report_delta

    def setUp(self):
        TestSelectionViewLabelDots31165.setUp(self)
        listings = self.panel.findChildren(QtWidgets.QListWidget)
        self.assertEqual(len(listings), 2)
        visible = [listing for listing in listings if listing.isVisibleTo(self.main)]
        self.assertEqual(len(visible), 1)
        self.selection_list = visible[0]
        self.pick_list = next(listing for listing in listings if listing is not self.selection_list)
        checks = self.panel.findChildren(QtWidgets.QCheckBox)
        self.assertEqual(len(checks), 1)
        self.pick_check = checks[0]
        self.old_pick_enabled = self.pick_check.isChecked()
        self.observer = _SelectionObserver()
        Gui.Selection.addObserver(self.observer, 0)

    def tearDown(self):
        try:
            Gui.Selection.removeObserver(self.observer)
            self.pick_check.setChecked(self.old_pick_enabled)
            # Ordinary no-match search prevents any deleted object cache from
            # leaking from this diagnostic into the next native test case.
            fields = self.panel.findChildren(QtWidgets.QLineEdit)
            if fields:
                fields[0].setText("__SelectionProducerCleanupNoMatchingLabel__")
                fields[0].clear()
        finally:
            TestSelectionViewLabelDots31165.tearDown(self)

    def _row(self, listing, object_name):
        self.assertTrue(self._wait(lambda: listing.count() > 0))
        rows = [listing.item(index) for index in range(listing.count())
                if listing.item(index).text().startswith(self.doc.Name + "#" + object_name)]
        self.assertEqual(len(rows), 1, [listing.item(i).text() for i in range(listing.count())])
        listing.scrollToItem(rows[0])
        self._events()
        return rows[0]

    def _assert_hover_target(self, listing, item, obj, subname):
        # Public preselection may canonicalize a nested path. Independently
        # establish its actual API response before testing the widget handler.
        Gui.Selection.clearPreselection()
        Gui.Selection.setPreselection(obj, subname, tp=2)
        self._events()
        expected = Gui.Selection.getPreselection()
        expected_identity = (expected.DocumentName, expected.ObjectName,
                             tuple(expected.SubElementNames))
        self.assertEqual(expected_identity[:2], (self.doc.Name, obj.Name))
        self._assert_no_report_exception()
        self._hover(listing, item)
        self._assert_no_report_exception()
        pre = Gui.Selection.getPreselection()
        actual_identity = (pre.DocumentName, pre.ObjectName, tuple(pre.SubElementNames))
        self.assertEqual(actual_identity, expected_identity,
                         "Actual hover must match direct public preselection of the same target")

    def _double_click(self, listing, item):
        viewport = listing.viewport()
        point = listing.visualItemRect(item).center()
        self.assertTrue(viewport.rect().contains(point))
        for event_type, buttons in (
                (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
                (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
                (QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.LeftButton),
                (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton)):
            self._mouse(viewport, event_type, point, QtCore.Qt.LeftButton, buttons)
        self._events()
        self._assert_no_report_exception()

    def _assert_no_report_exception(self):
        TestSelectionViewLabelDots31165._assert_no_report_exception(self)
        self.assertNotIn("SyntaxError", self._report_delta())

    def _special_link(self, marker):
        container = self.doc.addObject("App::Part", "SourcePart")
        nested = self.doc.addObject("App::Part", "NestedPart")
        container.addObject(nested)
        nested.addObject(self.box)
        link = self.doc.addObject("App::Link", "OuterLink")
        link.setLink(container)
        nested_label = "Parent" + marker + "Branch"
        box_label = "Child" + marker + "Box"
        try:
            nested.Label = nested_label
            self.box.Label = box_label
        except ValueError as error:
            self.skipTest("Native Label API rejects this marker: " + repr(error))
        if (nested.Label, self.box.Label) != (nested_label, box_label):
            self.skipTest("Native Label API normalizes this marker: "
                          + repr((nested.Label, self.box.Label)))
        self.doc.recompute()
        path = "$" + nested.Label + ".$" + self.box.Label + ".Face1"
        try:
            face = link.getSubObject(path)
        except ValueError as error:
            self.skipTest("Native getSubObject cannot resolve this label path: " + repr(error))
        if face is None:
            self.skipTest("Native getSubObject does not support this label path: " + repr(path))
        self.assertEqual(face.ShapeType, "Face")
        self.assertTrue(face.isValid())
        expected_face = self.box.Shape.Faces[0]
        self.assertAlmostEqual(face.Area, expected_face.Area)
        self.assertLess((face.CenterOfMass - expected_face.CenterOfMass).Length, 1e-9)
        Gui.Selection.addSelection(self.doc.Name, link.Name, path)
        selected = Gui.Selection.getSelectionEx("*", 0)
        self.assertEqual(len(selected), 1)
        self.assertEqual((selected[0].DocumentName, selected[0].ObjectName),
                         (self.doc.Name, link.Name))
        self.assertEqual(len(selected[0].SubElementNames), 1)
        raw_path = selected[0].SubElementNames[0]
        if marker not in raw_path:
            self.skipTest("Native NoResolve selection canonicalizes away marker: " + repr(raw_path))
        self.assertTrue(Gui.Selection.isSelected(link, raw_path, 0))
        self._assert_no_report_exception()
        return link, raw_path

    def _check_special_path(self, marker):
        link, raw_path = self._special_link(marker)
        item = self._row(self.selection_list, link.Name)
        with self.subTest(phase="hover", marker=repr(marker)):
            self._assert_hover_target(self.selection_list, item, link, raw_path)
        with self.subTest(phase="double_click", marker=repr(marker)):
            self.assertTrue(Gui.Selection.isSelected(link, raw_path, 0))
            self._double_click(self.selection_list, item)
            self.assertFalse(Gui.Selection.isSelected(link, raw_path, 0),
                             "The actual row must remove its original special-label selection")

    def test_lf_label_path(self):
        self._check_special_path("\n")

    def test_cr_label_path(self):
        self._check_special_path("\r")

    def test_percent_placeholder_label_path(self):
        # These are real label bytes, never synthetic QListWidget item data.
        self._check_special_path("%1%4%99")

    def test_both_quotes_and_backslash_label_path(self):
        self._check_special_path("'\"\\")
