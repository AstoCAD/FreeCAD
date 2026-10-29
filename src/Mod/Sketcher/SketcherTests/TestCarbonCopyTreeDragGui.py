# SPDX-License-Identifier: LGPL-2.1-or-later
"""Carbon Copy creates one copy for a held Model-tree gesture.

Actual public QtTest gestures retain intentional clicks, hover, normal edit-close,
and Undo/Redo. Requires an explicitly selected disposable GUI profile.
"""

import os
from pathlib import Path
import time
import unittest
import uuid

import FreeCAD as App


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def owned_profile():
    selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
    if not selected:
        raise unittest.SkipTest("Requires an explicitly selected disposable test profile")
    import stat

    def plain_path(path):
        for component in (path, *path.parents):
            try:
                if component.is_symlink():
                    return False
                is_junction = getattr(component, "is_junction", None)
                if is_junction is not None and is_junction():
                    return False
                attributes = getattr(component.lstat(), "st_file_attributes", 0)
                if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    return False
            except FileNotFoundError:
                continue
            except OSError:
                return False
        return True

    raw = Path(selected)
    if not raw.is_absolute() or not plain_path(raw):
        raise unittest.SkipTest("Disposable profile must be an absolute directory without links")
    try:
        profile = raw.resolve(strict=True)
    except OSError:
        raise unittest.SkipTest("Disposable test profile must already exist")
    if not profile.is_dir():
        raise unittest.SkipTest("Disposable test profile must be a directory")
    configured_home = os.environ.get("FREECAD_USER_HOME")
    if not configured_home:
        raise unittest.SkipTest("FREECAD_USER_HOME must select the disposable profile")
    home = Path(configured_home)
    if not home.is_absolute() or not plain_path(home):
        raise unittest.SkipTest("FREECAD_USER_HOME must be absolute and free of links")
    try:
        matching_home = home.resolve(strict=True) == profile
    except OSError:
        matching_home = False
    if not matching_home:
        raise unittest.SkipTest("FREECAD_USER_HOME does not match the selected profile")
    parameter_file = Path(App.ConfigGet("UserParameter"))
    data_directory = Path(App.getUserAppDataDir())
    paths = (parameter_file, data_directory)
    if not all(path.is_absolute() and plain_path(path) for path in paths):
        raise unittest.SkipTest("Active profile paths must be absolute and free of links")
    if parameter_file.resolve() != profile / "user.cfg":
        raise unittest.SkipTest("Active user configuration is outside the selected profile")
    if not all(path.resolve().is_relative_to(profile) for path in paths):
        raise unittest.SkipTest("Active configuration and data must stay in the test profile")
    return profile


def pump(milliseconds=100):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    loop.exec_()
    Gui.updateGui()


def wait(predicate, message, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate():
        require(time.monotonic() < deadline, message)
        pump(30)


def point(value):
    return [float(value.x), float(value.y), float(value.z)]


def placement(value):
    return list(value.toMatrix().A)


def shape_data(shape):
    if shape.isNull():
        return {"null": True}
    box = shape.BoundBox
    return {"null": False, "valid": bool(shape.isValid()), "edges": len(shape.Edges),
            "vertices": len(shape.Vertexes), "length": float(shape.Length),
            "bounds": [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]}


def sketch_data(sketch):
    geometry = []
    for index, geo in enumerate(sketch.Geometry):
        require(isinstance(geo, Part.Circle), "Only the ordinary circle producer is admitted")
        geometry.append({"type": type(geo).__name__, "center": point(geo.Center),
                         "axis": point(geo.Axis), "radius": float(geo.Radius),
                         "construction": bool(sketch.getConstruction(index))})
    constraints = [{"type": value.Type, "first": value.First, "first_pos": value.FirstPos,
                    "second": value.Second, "second_pos": value.SecondPos,
                    "third": value.Third, "third_pos": value.ThirdPos,
                    "value": float(value.Value), "name": value.Name,
                    "driving": bool(sketch.isDriving(index)),
                    "active": bool(sketch.isActive(index))}
                   for index, value in enumerate(sketch.Constraints)]
    return {"name": sketch.Name, "label": sketch.Label, "geometry": geometry,
            "geometry_count": sketch.GeometryCount, "constraints": constraints,
            "constraint_count": sketch.ConstraintCount,
            "expressions": sorted((str(path), str(expr)) for path, expr in sketch.ExpressionEngine),
            "placement": placement(sketch.Placement),
            "attachment_offset": placement(sketch.AttachmentOffset), "map_mode": str(sketch.MapMode),
            "support": [(obj.Name, list(subs)) for obj, subs in sketch.AttachmentSupport],
            "shape": shape_data(sketch.Shape), "state": list(sketch.State),
            "visibility": bool(sketch.ViewObject.Visibility)}


def selection():
    return [(item.DocumentName, item.ObjectName, list(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()]


def preselection():
    item = Gui.Selection.getPreselection()
    return {"document": item.DocumentName, "object": item.ObjectName,
            "subnames": list(item.SubElementNames)}


COPY_COMMAND = "Create a carbon copy"


class Fixture:
    def __init__(self, suffix):
        self.document_name = None
        self.document_uid = None
        self.suffix = suffix
        self.recorder = None
        self.events = []

    def open(self):
        require(not App.listDocuments(), "Requires no pre-existing documents")
        require(QtWidgets.QApplication.activeModalWidget() is None, "Foreign modal dialog exists")
        self.doc = App.newDocument("CarbonCopyTreeDrag" + self.suffix + uuid.uuid4().hex[:8])
        self.document_name, self.document_uid = self.doc.Name, str(self.doc.Uid)
        self.doc.UndoMode = 1
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.source = self.body.newObject("Sketcher::SketchObject", "CarbonSource")
        self.target = self.body.newObject("Sketcher::SketchObject", "CarbonTarget")
        origin = self.body.getObject("Origin")
        require(origin is not None, "Ordinary Body origin was not created")
        for sketch in (self.source, self.target):
            sketch.AttachmentSupport = [(origin, "XY_Plane.")]
            sketch.MapMode = "FlatFace"
        self.source.addGeometry(Part.Circle(App.Vector(-10, 10, 0), App.Vector(0, 0, 1), 5), False)
        self.doc.recompute()
        require(self.source.GeometryCount == 1 and self.target.GeometryCount == 0,
                "Ordinary circle and empty-target producer failed")
        require(self.source.isValid() and self.target.isValid(), "Ordinary sketches must be valid")
        require(placement(self.source.Placement) == placement(self.target.Placement),
                "Source and target must use the same aligned plane")
        self.doc.clearUndos()
        self.gui_doc = Gui.getDocument(self.doc.Name)
        require(self.gui_doc.setEdit(self.target.Name), "Target did not enter normal sketch editing")
        pump(200)
        edited = self.gui_doc.getInEdit()
        require(edited is not None and edited.Object.Name == self.target.Name,
                "Actual editing owner is not the target sketch")
        self.find_tree()
        self.original_source = sketch_data(self.source)
        self.original_target = sketch_data(self.target)

    def find_tree(self):
        window = Gui.getMainWindow()
        docks = window.findChildren(QtWidgets.QDockWidget)
        dock = next((value for value in docks if value.objectName() == "Tree view"
                     and value.widget() is not None
                     and value.widget().inherits("Gui::TreeDockWidget")), None)
        if dock is None:
            dock = next((value for value in docks if value.objectName() == "Model"
                         and value.widget() is not None
                         and value.widget().inherits("Gui::DockWnd::ComboView")), None)
        require(dock is not None, "Canonical Model/Tree view dock was not found")
        trees = [value for value in dock.widget().findChildren(QtWidgets.QTreeWidget)
                 if value.inherits("Gui::TreeWidget")]
        require(len(trees) == 1, "Expected one canonical native model TreeWidget")
        self.tree, self.viewport = trees[0], trees[0].viewport()
        require(self.tree.isVisible() and self.viewport.isVisible() and self.viewport.isEnabled(),
                "Actual model tree must be visible and enabled; no forced visibility")
        self.mode = {"dock_name": dock.objectName(), "dock_class": dock.widget().metaObject().className(),
                     "tree_class": self.tree.metaObject().className(),
                     "viewport_class": self.viewport.metaObject().className(),
                     "visible": self.viewport.isVisible(),
                     "start_drag_distance": QtWidgets.QApplication.startDragDistance()}
        self.tree.expandAll()
        pump(150)
        self.tree.scrollTo(self.find_index(self.source))
        pump(150)
        for obj in (self.source, self.target):
            self.find_index(obj)

    def find_index(self, obj):
        model = self.tree.model()
        start = model.index(0, 0, self.tree.rootIndex())
        require(start.isValid(), "Canonical model tree has no root row")
        matches = model.match(start, QtCore.Qt.DisplayRole, obj.Label, 2,
                              QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive)
        require(len(matches) == 1 and matches[0].isValid() and matches[0].column() == 0,
                "Owned sketch model index is not unique and valid")
        require(matches[0].data(QtCore.Qt.DisplayRole) == obj.Label,
                "Owned sketch model index has a different display label")
        return matches[0]

    def start(self):
        Gui.Selection.clearSelection()
        Gui.runCommand("Sketcher_CarbonCopy")
        pump(150)
        require(self.gui_doc.getInEdit().Object.Name == self.target.Name,
                "Carbon Copy changed the edit owner")
        require(self.target.GeometryCount == 0, "Tool activation unexpectedly copied geometry")
        fixture = self

        class Recorder(QtCore.QObject):
            def eventFilter(self, watched, event):
                kinds = {QtCore.QEvent.MouseButtonPress: "press",
                         QtCore.QEvent.MouseMove: "move",
                         QtCore.QEvent.MouseButtonRelease: "release"}
                if event.type() in kinds:
                    pos = event.position() if hasattr(event, "position") else event.pos()
                    fixture.events.append({"kind": kinds[event.type()],
                        "surface": "viewport" if watched == fixture.viewport else "tree",
                        "x": float(pos.x()), "y": float(pos.y()),
                        "left": bool(event.buttons() & QtCore.Qt.LeftButton),
                        "right": bool(event.buttons() & QtCore.Qt.RightButton),
                        "middle": bool(event.buttons() & QtCore.Qt.MiddleButton)})
                return False

        self.recorder = Recorder()
        self.tree.installEventFilter(self.recorder)
        self.viewport.installEventFilter(self.recorder)
        self.before = self.snapshot()

    def row_position(self, obj):
        self.tree.scrollTo(self.find_index(obj))
        pump(80)
        index = self.find_index(obj)
        rect = self.tree.visualRect(index)
        pos = QtCore.QPoint(rect.left() + min(45, max(12, rect.width() // 3)), rect.center().y())
        require(self.viewport.rect().contains(pos) and self.tree.indexAt(pos) == index
                and self.tree.indexAt(pos).column() == 0, "Actual row position did not qualify")
        return pos

    def snapshot(self):
        edited = self.gui_doc.getInEdit()
        return {"source": sketch_data(self.source), "target": sketch_data(self.target),
                "objects": [(obj.Name, obj.TypeId, obj.Label) for obj in self.doc.Objects],
                "body_group": [obj.Name for obj in self.body.Group],
                "body_placement": placement(self.body.Placement),
                "active_document": App.ActiveDocument.Name if App.ActiveDocument else None,
                "edit_owner": edited.Object.Name if edited else None,
                "document_uid": str(self.doc.Uid), "document_label": self.doc.Label,
                "pending": bool(self.doc.HasPendingTransaction),
                "booked": self.doc.getBookedTransactionID(),
                "undo": list(self.doc.UndoNames), "redo": list(self.doc.RedoNames),
                "selection": selection(), "preselection": preselection()}

    def expect_copies(self, count):
        actual = self.snapshot()
        require(actual["source"] == self.original_source, "Carbon Copy changed its full source model")
        expected_target = dict(self.original_target)
        expected_target["geometry"] = self.original_source["geometry"] * count
        expected_target["geometry_count"] = count
        require(actual["target"] == expected_target,
                "Target model must change only by the expected circle copies: expected "
                + str(count) + ", found " + str(actual["target"]["geometry_count"]))
        for key in ("objects", "body_group", "body_placement", "active_document", "edit_owner",
                    "document_uid", "document_label", "selection"):
            require(actual[key] == self.before[key], "Copying changed unrelated state: " + key)
        require(not self.before["pending"] and self.before["booked"] == 0
                and self.before["undo"] == [] and self.before["redo"] == [],
                "The ordinary copy control requires empty initial history")
        require(not actual["pending"] and actual["booked"] == 0,
                "The copy command must complete only its own transaction")
        require(actual["undo"] == [COPY_COMMAND] * count and actual["redo"] == [],
                "Each intentional copy must have exactly one copy-command history entry")
        return actual

    def click(self):
        pos = self.row_position(self.source)
        QtTest.QTest.mouseClick(self.viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
        pump(180)

    def close(self):
        if self.recorder is not None:
            self.tree.removeEventFilter(self.recorder)
            self.viewport.removeEventFilter(self.recorder)
            self.recorder = None
        if self.document_name and self.document_name in App.listDocuments():
            doc = App.getDocument(self.document_name)
            require(str(doc.Uid) == self.document_uid, "Owned-document identity changed")
            gui_doc = Gui.getDocument(doc.Name)
            if gui_doc.getInEdit() is not None:
                gui_doc.resetEdit()
                pump(150)
            Gui.Selection.clearSelection()
            if doc.HasPendingTransaction:
                doc.abortTransaction()
            App.closeDocument(doc.Name)
            pump(100)


def single(fixture):
    fixture.click()
    fixture.expect_copies(1)
    return {"one_real_click_one_copy": True}


def repeated(fixture):
    fixture.click()
    first = fixture.expect_copies(1)
    fixture.click()
    fixture.expect_copies(2)
    return {"two_intentional_clicks_two_copies": True, "after_first": first}


def hover(fixture):
    require(App.ParamGet("User parameter:BaseApp/Preferences/TreeView").GetBool("PreSelection", True),
            "No-button hover control requires the ordinary enabled tree preselection")
    from PySide import QtGui
    window = fixture.viewport.window().windowHandle()
    require(window is not None and window.isVisible(),
            "Public QWindow hover route requires a visible native window handle")
    hover_moves = []

    def move_hover(pos):
        requested_global = fixture.viewport.mapToGlobal(pos)
        QtTest.QTest.mouseMove(fixture.viewport, pos)
        actual_global = QtGui.QCursor.pos()
        move = {"cursor_route": "QtTestQWidgetCursor", "event_route": "QtTestQWindow",
                "requested_global": [requested_global.x(), requested_global.y()],
                "actual_global": [actual_global.x(), actual_global.y()]}
        hover_moves.append(move)
        require(actual_global == requested_global,
                "Public QtTest cursor phase did not reach the requested global position: "
                + repr(move))
        window_pos = window.mapFromGlobal(requested_global)
        require(QtCore.QRect(QtCore.QPoint(0, 0), window.size()).contains(window_pos),
                "Actual hover point is outside the native window bounds")
        move["window_position"] = [window_pos.x(), window_pos.y()]
        QtTest.QTest.mouseMove(window, window_pos)

    target_pos = fixture.row_position(fixture.target)
    move_hover(target_pos)
    pump(250)
    before_events = len(fixture.events)
    source_pos = fixture.row_position(fixture.source)
    move_hover(source_pos)
    wait(lambda: any(row["kind"] == "move" and not any(row[key] for key in ("left", "right", "middle"))
                     for row in fixture.events[before_events:]), "No real no-button hover event arrived")

    def source_preselected():
        selected = Gui.Selection.getPreselection()
        if selected.DocumentName != fixture.doc.Name:
            return False
        obj = fixture.doc.getObject(selected.ObjectName)
        return obj == fixture.source or (obj is not None and any(
            obj.getSubObject(subname, 1) == fixture.source for subname in selected.SubElementNames))

    wait(source_preselected, "Ordinary source hover did not retain tree preselection")
    fixture.expect_copies(0)
    return {"no_button_hover_no_copy": True, "source_preselection": preselection(),
            "input_route": "QtTestQWidgetCursor+QtTestQWindow", "hover_moves": hover_moves}


def quit_and_blank_drag(fixture):
    fixture.gui_doc.resetEdit()
    pump(180)
    require(fixture.gui_doc.getInEdit() is None, "Normal edit-close did not end the tool")
    Gui.Selection.clearSelection()
    pump(150)
    source = fixture.row_position(fixture.source)
    target = fixture.row_position(fixture.target)
    # A blank-area press cannot begin an object drag/drop operation.
    lower = max(fixture.tree.visualRect(fixture.find_index(obj)).bottom()
                for obj in (fixture.source, fixture.target)) + 12
    start = QtCore.QPoint(source.x(), lower)
    require(fixture.viewport.rect().contains(start) and not fixture.tree.indexAt(start).isValid(),
            "A real blank region below the owned sketch rows is required")
    end = QtCore.QPoint(source.x(), min(source.y(), target.y()) - 3)
    before = fixture.snapshot()
    event_start = len(fixture.events)
    QtTest.QTest.mousePress(fixture.viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, start)
    try:
        QtTest.QTest.mouseMove(fixture.viewport, end)
        pump(150)
        mid_selected_labels = [index.data(QtCore.Qt.DisplayRole)
                              for index in fixture.tree.selectionModel().selectedRows(0)]
        require(all(obj.Label in mid_selected_labels for obj in (fixture.source, fixture.target)),
                "Held move must select both owned sketch rows before button release")
    finally:
        QtTest.QTest.mouseRelease(fixture.viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, end)
        pump(180)
    require(any(row["kind"] == "move" and row["left"]
                for row in fixture.events[event_start:]), "Blank drag lacked a real held-left move")
    selected_labels = [index.data(QtCore.Qt.DisplayRole)
                       for index in fixture.tree.selectionModel().selectedRows(0)]
    require(any(fixture.tree.selectionModel().isSelected(fixture.find_index(obj))
                for obj in (fixture.source, fixture.target)),
            "Standard blank-area held drag did not select an owned sketch row after tool exit")
    after = fixture.snapshot()
    for key in ("source", "target", "objects", "body_group", "body_placement"):
        require(after[key] == before[key], "Blank selection drag changed the model: " + key)
    return {"normal_edit_close": True, "blank_drag_selected_owned_rows": True,
            "midgesture_selected_rows": mid_selected_labels,
            "selected_rows": selected_labels, "before_drag": before}


def held_drag(fixture):
    pos = fixture.row_position(fixture.source)
    distance = QtWidgets.QApplication.startDragDistance()
    require(distance > 2, "Requires an ordinary drag threshold above two pixels")
    step = min(3, distance - 1)
    moves = [pos + QtCore.QPoint(delta, 0) for delta in (step, 0, -step, 0, step, 0)]
    require(all(fixture.tree.indexAt(value) == fixture.find_index(fixture.source)
                and (value - pos).manhattanLength() < distance for value in moves),
            "All held moves must remain in the source row and below drag/drop threshold")
    event_start = len(fixture.events)
    QtTest.QTest.mousePress(fixture.viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
    try:
        pump(180)
        press_only = fixture.expect_copies(1)
        stages = []
        for value in moves:
            QtTest.QTest.mouseMove(fixture.viewport, value)
            pump(150)
            stages.append(fixture.snapshot())
    finally:
        QtTest.QTest.mouseRelease(fixture.viewport, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
        pump(180)
    observed = [row for row in fixture.events[event_start:]
                if row["kind"] == "move" and row["surface"] == "viewport"]
    require(observed and all(row["left"] and not row["right"] and not row["middle"] for row in observed),
            "Actual target MouseMove events must carry only held LeftButton")
    count = fixture.target.GeometryCount
    require(count >= 1, "The target gesture must perform at least its initial legitimate copy")
    fixture.expect_copies(1)
    return {"press_only": press_only, "held_stages": stages, "copies_for_one_press": count,
            "duplicate_observed": count > 1, "held_viewport_moves": observed,
            "start": [pos.x(), pos.y()], "requested_moves": [[value.x(), value.y()] for value in moves]}



def undo_redo(fixture):
    before = fixture.snapshot()
    fixture.click()
    after = fixture.expect_copies(1)
    fixture.doc.undo()
    pump(180)
    undone = fixture.snapshot()
    model_keys = ("source", "target", "objects", "body_group", "body_placement",
                  "active_document", "edit_owner", "document_uid", "document_label", "selection")
    for key in model_keys:
        require(undone[key] == before[key], "Undo did not restore the full owned state: " + key)
    require(not undone["pending"] and undone["booked"] == 0,
            "Undo left an unexpected pending transaction")
    require(undone["undo"] == before["undo"] and undone["redo"] == [COPY_COMMAND],
            "Undo must restore prior history with one copy-command redo")
    fixture.doc.redo()
    pump(180)
    redone = fixture.snapshot()
    for key in model_keys:
        require(redone[key] == after[key], "Redo did not restore the full copied state: " + key)
    require(not redone["pending"] and redone["booked"] == 0,
            "Redo left an unexpected pending transaction")
    require(redone["undo"] == after["undo"] and redone["redo"] == [],
            "Redo must restore exactly one copy-command undo entry")


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestCarbonCopyTreeDragGui(unittest.TestCase):
    def setUp(self):
        self.profile = owned_profile()
        global Gui, Part, QtCore, QtWidgets, QtTest
        import FreeCADGui as Gui
        import Part
        import Sketcher  # noqa: F401
        from PySide import QtCore, QtWidgets
        try:
            from PySide import QtTest
        except ImportError:
            from PySide6 import QtTest
        require(not App.listDocuments(), "Requires a disposable process without existing documents")
        require(QtWidgets.QApplication.activeModalWidget() is None, "Foreign modal dialog exists")
        previous = Gui.activeWorkbench()
        self.previous_workbench = previous.name() if previous else None
        self.addCleanup(self._restore_workbench)
        Gui.activateWorkbench("SketcherWorkbench")

    def _restore_workbench(self):
        if self.previous_workbench:
            Gui.activateWorkbench(self.previous_workbench)

    def _with_fixture(self, suffix, callback):
        fixture = Fixture(suffix)
        try:
            fixture.open()
            fixture.start()
            callback(fixture)
        finally:
            fixture.close()

    def test_control_single_click_creates_one_copy(self):
        self._with_fixture("SingleClick", single)

    def test_control_repeated_clicks_create_two_copies(self):
        self._with_fixture("RepeatedClick", repeated)

    def test_control_hover_retains_preselection_without_copy(self):
        self._with_fixture("Hover", hover)

    def test_control_normal_exit_restores_held_tree_selection(self):
        self._with_fixture("NormalExit", quit_and_blank_drag)

    def test_control_copy_undo_redo_restores_full_state(self):
        self._with_fixture("UndoRedo", undo_redo)

    def test_held_tree_drag_creates_one_copy(self):
        self._with_fixture("HeldDrag", held_drag)
