# SPDX-License-Identifier: LGPL-2.1-or-later
"""Toggle Grounded preserves pending edits for selections without subelements.

The actual GUI command, native assembly edit mode, full model snapshots and
Undo/Redo controls are used. An explicit disposable profile is required first.
"""

import os
from pathlib import Path
import time
import unittest

import FreeCAD as App

if App.GuiUp:
    import FreeCADGui as Gui
    from PySide import QtCore, QtWidgets

COMMAND = "Assembly_ToggleGrounded"
UNDO_NAME = "Toggle grounded"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


@unittest.skipUnless(App.GuiUp, "Requires the FreeCAD GUI")
class TestGroundedEmptySelectionGui(unittest.TestCase):
    def setUp(self):
        self.profile = self._owned_profile()
        if App.listDocuments():
            self.skipTest("Requires a disposable GUI process without existing documents")
        if QtWidgets.QApplication.activeModalWidget() is not None or Gui.Control.activeDialog():
            self.skipTest("Requires a GUI process without a foreign modal or task")
        import Part  # noqa: F401
        import CommandCreateJoint  # noqa: F401
        import UtilsAssembly
        workbench = Gui.activeWorkbench()
        previous_workbench = workbench.name() if workbench else None
        owned = []

        def pump():
            loop = QtCore.QEventLoop()
            QtCore.QTimer.singleShot(30, loop.quit)
            loop.exec_()
            Gui.updateGui()

        def wait(predicate, message):
            deadline = time.monotonic() + 10
            while not predicate():
                require(time.monotonic() < deadline, message)
                pump()

        def record(stage, **values):
            return {"stage": stage, **values}

        def placement(value):
            return {"base": [value.Base.x, value.Base.y, value.Base.z],
                    "rotation": list(value.Rotation.Q)}

        def selection():
            # Read the same public raw selection mode as the actual command.
            return [(item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
                    for item in Gui.Selection.getSelectionEx("*", 0)]

        def model(fx):
            document, assembly, joints, box, group = (fx[key] for key in
                                                    ("doc", "assembly", "joints", "box", "group"))
            shape = box.Shape
            bounds = shape.BoundBox
            return {
                "objects": sorted((obj.Name, obj.TypeId, obj.Label) for obj in document.Objects),
                "assembly_group": [obj.Name for obj in assembly.Group],
                "assembly_placement": placement(assembly.Placement),
                "joint_group": [obj.Name for obj in joints.Group],
                "grounds": sorted((obj.Name, obj.TypeId, obj.ObjectToGround.Name,
                                   type(obj.Proxy).__name__)
                                  for obj in joints.Group if hasattr(obj, "ObjectToGround")),
                "box_placement": placement(box.Placement),
                "placement_status": sorted(box.getPropertyStatus("Placement"), key=lambda value: (type(value).__name__, repr(value))),
                "box_dimensions": [box.Length.Value, box.Width.Value, box.Height.Value],
                "shape_valid": bool(shape.isValid()), "volume": shape.Volume, "area": shape.Area,
                "bounds": [bounds.XMin, bounds.YMin, bounds.ZMin, bounds.XMax, bounds.YMax, bounds.ZMax],
                "shape_counts": [len(shape.Solids), len(shape.Faces), len(shape.Edges)],
                "unrelated_group": [obj.Name for obj in group.Group],
                "unrelated_label": group.Label,
            }

        def snapshot(fx):
            document = fx["doc"]
            return {"model": model(fx), "selection": selection(),
                    "pending": bool(document.HasPendingTransaction),
                    "booked": document.getBookedTransactionID(),
                    "undo": list(document.UndoNames), "redo": list(document.RedoNames)}

        def existing_joint_group(fx):
            before = [(obj.Name, obj.TypeId) for obj in fx["doc"].Objects]
            require(UtilsAssembly.getJointGroup(fx["assembly"]) == fx["joints"],
                    "The normal fixture must already own its joint group")
            require(before == [(obj.Name, obj.TypeId) for obj in fx["doc"].Objects],
                    "Looking up the pre-existing joint group changed the model")

        def fixture(kind):
            document = App.newDocument("GroundAudit90" + kind)
            uid = str(document.Uid)
            owned.append((document.Name, uid))
            document.UndoMode = 1
            assembly = document.addObject("Assembly::AssemblyObject", "Assembly")
            joints = assembly.newObject("Assembly::JointGroup", "Joints")
            box = assembly.newObject("Part::Box", "Box")
            box.Length, box.Width, box.Height = 20, 30, 10
            group = document.addObject("App::DocumentObjectGroup", "UnrelatedGroup")
            group.Label = "Stable unrelated group"
            document.recompute()
            gui_document = Gui.getDocument(document.Name)
            require(gui_document.setEdit(assembly), "The native assembly did not enter normal edit mode")
            pump()
            require(UtilsAssembly.activeAssembly() == assembly and assembly.ViewObject.isInEditMode(),
                    "The normal fixture assembly is not active")
            require(UtilsAssembly.assembly_has_at_least_n_parts(1), "The assembly lacks a normal part")
            require(not Gui.Control.activeDialog(), "Assembly activation unexpectedly opened a task dialog")
            require(box.Shape.isValid() and box.Shape.Volume == 6000, "Ordinary box geometry differs")
            if document.HasPendingTransaction or document.getBookedTransactionID():
                document.commitTransaction()
            document.clearUndos()
            require(not document.HasPendingTransaction and document.getBookedTransactionID() == 0
                    and document.UndoNames == [] and document.RedoNames == [],
                    "Owned fixture setup history must be completely closed")
            fx = {"doc": document, "uid": uid, "gui": gui_document, "assembly": assembly,
                  "joints": joints, "box": box, "group": group}
            existing_joint_group(fx)
            require(not model(fx)["grounds"] and "ReadOnly" not in box.getPropertyStatus("Placement"),
                    "The fresh component is already grounded")
            return fx

        def select(fx, kind):
            Gui.Selection.clearSelection()
            document, assembly, box, group = (fx[key] for key in ("doc", "assembly", "box", "group"))
            if kind == "component":
                Gui.Selection.addSelection(document.Name, assembly.Name, box.Name + ".")
                expected = [(document.Name, assembly.Name, (box.Name + ".",))]
            elif kind == "assembly":
                Gui.Selection.addSelection(document.Name, assembly.Name)
                expected = [(document.Name, assembly.Name, ())]
            elif kind == "group":
                Gui.Selection.addSelection(document.Name, group.Name)
                expected = [(document.Name, group.Name, ())]
            else:
                require(kind == "empty", "Unknown ordinary selection fixture")
                expected = []
            require(selection() == expected, "Actual raw SelectionEx differs from the ordinary fixture")
            if kind == "component":
                component, _relative = UtilsAssembly.getComponentReference(assembly, assembly, box.Name + ".")
                require(component == box, "The ordinary assembly-relative component path did not resolve")
            return expected

        def invoke(fx):
            require(App.ActiveDocument.Name == fx["doc"].Name, "The owned fixture is not active")
            require(UtilsAssembly.activeAssembly() == fx["assembly"], "The admitted assembly changed")
            existing_joint_group(fx)
            command = Gui.Command.get(COMMAND)
            require(command is not None and command.isActive(), "The ordinary Toggle Grounded action is disabled")
            Gui.runCommand(COMMAND)
            pump()
            fx["doc"].recompute()
            require(QtWidgets.QApplication.activeModalWidget() is None and not Gui.Control.activeDialog(),
                    "The ordinary command unexpectedly left a dialog")
            existing_joint_group(fx)

        def close(fx):
            document = fx["doc"]
            Gui.Selection.clearSelection()
            require(document.Name in App.listDocuments() and str(document.Uid) == fx["uid"],
                    "Owned fixture identity changed before cleanup")
            if fx["gui"].getInEdit() is not None:
                fx["gui"].resetEdit()
                pump()
            if document.HasPendingTransaction or document.getBookedTransactionID():
                document.abortTransaction()
            App.closeDocument(document.Name)
            pump()

        def unchanged_component(before, after):
            fields = ("assembly_placement", "box_placement", "box_dimensions",
                      "shape_valid", "volume", "area", "bounds", "shape_counts",
                      "unrelated_group", "unrelated_label")
            for key in fields:
                require(after[key] == before[key], "Accepted grounding changed independent model field: " + key)
            before_ground_names = {value[0] for value in before["grounds"]}
            after_ground_names = {value[0] for value in after["grounds"]}
            for state, ground_names in ((before, before_ground_names), (after, after_ground_names)):
                require(all(state["assembly_group"].count(name) == 1 for name in ground_names),
                        "Every grounding joint must belong exactly once to its assembly")
                objects = {obj[0]: obj for obj in state["objects"]}
                for name, kind, target, proxy in state["grounds"]:
                    require(name in objects and objects[name] == (name, "App::FeaturePython", name)
                            and kind == "App::FeaturePython" and proxy == "GroundedJoint",
                            "The allowed membership change is not its normal grounding object")
            require([name for name in before["assembly_group"] if name not in before_ground_names] ==
                    [name for name in after["assembly_group"] if name not in after_ground_names],
                    "Accepted grounding changed assembly members outside its grounding joint")
            require([obj for obj in before["objects"] if obj[0] not in before_ground_names] ==
                    [obj for obj in after["objects"] if obj[0] not in after_ground_names],
                    "Accepted grounding changed objects outside its grounding joint")
            before_status = [value for value in before["placement_status"] if value != "ReadOnly"]
            after_status = [value for value in after["placement_status"] if value != "ReadOnly"]
            require(before_status == after_status, "Grounding changed unrelated placement status bits")

        def toggle_control(unground):
            fx = fixture("UngroundControl" if unground else "GroundControl")
            try:
                select(fx, "component")
                if unground:
                    invoke(fx)
                    require(len(model(fx)["grounds"]) == 1, "Actual grounding producer did not create its joint")
                    fx["doc"].clearUndos()
                    require(not fx["doc"].HasPendingTransaction and fx["doc"].getBookedTransactionID() == 0
                            and fx["doc"].UndoNames == [] and fx["doc"].RedoNames == [],
                            "Actual grounding producer history was not closed")
                    select(fx, "component")
                before = snapshot(fx)
                invoke(fx)
                after = snapshot(fx)
                expected = 0 if unground else 1
                require(len(after["model"]["grounds"]) == expected
                        and len(after["model"]["joint_group"]) == expected,
                        "Actual command did not toggle exactly the admitted grounding")
                if not unground:
                    require(after["model"]["grounds"][0][2] == fx["box"].Name,
                            "The new grounding references the wrong component")
                require(("ReadOnly" in after["model"]["placement_status"]) == (not unground),
                        "Actual grounding did not set the expected placement read-only state")
                unchanged_component(before["model"], after["model"])
                require(after["selection"] == before["selection"], "Accepted grounding changed its selection")
                require(not after["pending"] and after["booked"] == 0
                        and after["undo"] == [UNDO_NAME] and after["redo"] == [],
                        "Accepted command transaction history differs")
                fx["doc"].undo()
                fx["doc"].recompute()
                pump()
                undone = snapshot(fx)
                require(undone["model"] == before["model"], "Undo did not restore the full independent model")
                require(not undone["pending"] and undone["booked"] == 0
                        and undone["undo"] == [] and undone["redo"] == [UNDO_NAME], "Undo history differs")
                fx["doc"].redo()
                fx["doc"].recompute()
                pump()
                redone = snapshot(fx)
                require(redone["model"] == after["model"], "Redo did not restore the accepted model")
                require(not redone["pending"] and redone["booked"] == 0
                        and redone["undo"] == [UNDO_NAME] and redone["redo"] == [], "Redo history differs")
                return record("unground_control" if unground else "ground_control", before=before,
                              after=after, undone=undone, redone=redone)
            finally:
                close(fx)

        def pending_case(kind, control=False):
            fx = fixture("Pending" + kind.title())
            try:
                actual_selection = select(fx, kind)
                if not control:
                    require(len(actual_selection) == 1 and actual_selection[0][2] == (),
                            "Target must have an exactly empty raw SubElementNames vector")
                pristine = snapshot(fx)
                original_label = fx["group"].Label
                fx["doc"].openTransaction("Unrelated pending edit")
                fx["group"].Label = "Uncommitted unrelated label"
                require(fx["doc"].HasPendingTransaction and fx["doc"].getBookedTransactionID() > 0
                        and fx["doc"].UndoNames == ["Unrelated pending edit"]
                        and fx["doc"].RedoNames == [], "Unrelated edit did not stay pending")
                before = snapshot(fx)
                invoke(fx)
                after = snapshot(fx)
                flags = {key + "_preserved": after[key] == before[key] for key in before}
                fx["doc"].abortTransaction()
                pump()
                aborted = snapshot(fx)
                flags.update({"abort_restored_label": fx["group"].Label == original_label,
                              "abort_restored_model": aborted["model"] == pristine["model"],
                              "abort_restored_selection": aborted["selection"] == pristine["selection"],
                              "abort_history_match": (aborted["undo"], aborted["redo"]) ==
                                                     (pristine["undo"], pristine["redo"]),
                              "abort_no_pending": not aborted["pending"] and aborted["booked"] == 0})
                result = record("empty_selection_control" if control else "empty_subnames_target",
                                selection_kind=kind, pristine=pristine, before=before, after=after,
                                aborted=aborted, flags=flags, passed=all(flags.values()))
                if control:
                    require(result["passed"], "Empty-selection pending/abort control failed")
                return result
            finally:
                close(fx)

        def cleanup():
            Gui.Selection.clearSelection()
            for name, uid in reversed(owned):
                if name in App.listDocuments():
                    document = App.getDocument(name)
                    require(str(document.Uid) == uid, "Final cleanup ownership differs")
                    gui_document = Gui.getDocument(name)
                    if gui_document.getInEdit() is not None:
                        gui_document.resetEdit()
                        pump()
                    if document.HasPendingTransaction or document.getBookedTransactionID():
                        document.abortTransaction()
                    App.closeDocument(name)
            pump()
            if previous_workbench:
                Gui.activateWorkbench(previous_workbench)
            require(App.listDocuments() == {}, "Owned grounding fixtures did not close normally")

        self.addCleanup(cleanup)
        self._toggle_control = toggle_control
        self._pending_case = pending_case
        Gui.activateWorkbench("AssemblyWorkbench")

    def _owned_profile(self):
        selected = os.environ.get("FREECAD_TEST_ISOLATED_PROFILE")
        if not selected:
            self.skipTest("Requires an explicitly selected disposable test profile")
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
            self.skipTest("The disposable test profile must be an absolute directory without links")
        try:
            profile = raw.resolve(strict=True)
        except OSError:
            self.skipTest("The disposable test profile must already exist")
        if not profile.is_dir():
            self.skipTest("The disposable test profile must be a directory")
        configured_home = os.environ.get("FREECAD_USER_HOME")
        if not configured_home:
            self.skipTest("FREECAD_USER_HOME must explicitly select the disposable test profile")
        home = Path(configured_home)
        if not home.is_absolute() or not plain_path(home):
            self.skipTest("FREECAD_USER_HOME must be an absolute directory without links")
        try:
            matching_home = home.resolve(strict=True) == profile
        except OSError:
            matching_home = False
        if not matching_home:
            self.skipTest("FREECAD_USER_HOME does not match the disposable test profile")
        parameter_file = Path(App.ConfigGet("UserParameter"))
        data_directory = Path(App.getUserAppDataDir())
        paths = (parameter_file, data_directory)
        if not all(path.is_absolute() and plain_path(path) for path in paths):
            self.skipTest("Active profile paths must be absolute and free of links")
        if parameter_file.resolve() != profile / "user.cfg":
            self.skipTest("The active user configuration is outside the selected test profile")
        if not all(path.resolve().is_relative_to(profile) for path in paths):
            self.skipTest("Active user configuration and data must stay in the test profile")
        return profile

    def _check_pending(self, kind, control=False):
        result = self._pending_case(kind, control=control)
        for oracle, passed in result["flags"].items():
            with self.subTest(selection=kind, oracle=oracle):
                self.assertTrue(passed)

    def test_control_ground_undo_redo(self):
        self._toggle_control(False)

    def test_control_unground_undo_redo(self):
        self._toggle_control(True)

    def test_control_empty_selection_preserves_pending_edit(self):
        self._check_pending("empty", control=True)

    def test_whole_assembly_selection_preserves_pending_edit(self):
        self._check_pending("assembly")

    def test_group_selection_preserves_pending_edit(self):
        self._check_pending("group")
