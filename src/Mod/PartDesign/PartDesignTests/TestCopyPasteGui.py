# SPDX-License-Identifier: LGPL-2.1-or-later
"""Std_Copy / Std_Paste of PartDesign objects without the dependency dialog.

https://github.com/FreeCAD/FreeCAD/issues/9251
"""

import unittest
from uuid import uuid4

import FreeCAD as App
import FreeCADGui as Gui
import Part
import Sketcher  # noqa: F401
from PySide import QtCore, QtWidgets

PARAM_PATH = "User parameter:BaseApp/Preferences/General"
PARAM = "CopyPasteObjectRules"


class TestCopyPasteGui(unittest.TestCase):
    def setUp(self):
        self.previous_document = App.activeDocument().Name if App.activeDocument() else None
        self.settings = App.ParamGet(PARAM_PATH)
        self.had_param = any(item[1] == PARAM for item in self.settings.GetContents() or [])
        self.saved_param = self.settings.GetBool(PARAM, True)
        self.settings.SetBool(PARAM, True)
        self.saved_clipboard = self._save_clipboard()
        self.addCleanup(self._cleanup)

        Gui.Selection.clearSelection()
        self.doc = App.newDocument("CopyPaste_" + uuid4().hex[:10])
        self.doc_name = self.doc.Name
        self.doc.UndoMode = 1
        self.body1 = self.doc.addObject("PartDesign::Body", "Body1")
        self.body2 = self.doc.addObject("PartDesign::Body", "Body2")
        self.sketch = self.body1.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = [(self._origin_feature(self.body1, "XY_Plane"), "")]
        self.sketch.MapMode = "FlatFace"
        self.sketch.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
        self.doc.recompute()
        self.doc.clearUndos()
        self.dialogs = []

    @staticmethod
    def _origin_feature(container, role):
        return [f for f in container.Origin.OriginFeatures if f.Role == role][0]

    @staticmethod
    def _save_clipboard():
        data = QtWidgets.QApplication.clipboard().mimeData()
        if data is None:
            return {}
        return {fmt: bytes(data.data(fmt)) for fmt in data.formats()}

    def _restore_clipboard(self):
        mime = QtCore.QMimeData()
        for fmt, value in self.saved_clipboard.items():
            mime.setData(fmt, QtCore.QByteArray(value))
        QtWidgets.QApplication.clipboard().setMimeData(mime)

    def _cleanup(self):
        Gui.Selection.clearSelection()
        if self.doc_name in App.listDocuments():
            if self.doc.HasPendingTransaction:
                self.doc.abortTransaction()
            App.closeDocument(self.doc_name)
        if self.had_param:
            self.settings.SetBool(PARAM, self.saved_param)
        else:
            self.settings.RemBool(PARAM)
        self._restore_clipboard()
        if self.previous_document in App.listDocuments():
            App.setActiveDocument(self.previous_document)

    def _run(self, command_name):
        """Run a command; any dependency dialog is recorded and cancelled."""
        testcase = self

        class DialogRejecter(QtCore.QObject):
            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.Show and isinstance(watched, QtWidgets.QDialog):
                    if watched.objectName() in (
                        "Gui::DlgObjectSelection",
                        "Gui__DlgObjectSelection",
                    ):
                        testcase.dialogs.append(watched.objectName())
                        QtCore.QTimer.singleShot(0, watched.reject)
                return False

        rejecter = DialogRejecter()
        application = QtWidgets.QApplication.instance()
        application.installEventFilter(rejecter)
        try:
            App.setActiveDocument(self.doc_name)
            Gui.runCommand(command_name, 0)
        finally:
            application.removeEventFilter(rejecter)
        Gui.updateGui()

    def _select(self, obj):
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(obj)

    def _orphan_datums(self):
        return [
            o
            for o in self.doc.Objects
            if o.isDerivedFrom("App::DatumElement")
            and not any(i.isDerivedFrom("App::LocalCoordinateSystem") for i in o.InList)
        ]

    def test_sketch_copied_without_dialog_and_pasted_into_selected_body(self):
        self._select(self.sketch)
        self._run("Std_Copy")
        self.assertEqual(self.dialogs, [])

        before = {o.Name for o in self.doc.Objects}
        self._select(self.body2)
        self._run("Std_Paste")
        new = [o for o in self.doc.Objects if o.Name not in before]
        self.assertEqual(len(new), 1)
        pasted = new[0]
        self.assertTrue(pasted.isDerivedFrom("Sketcher::SketchObject"))
        self.assertIn(pasted, self.body2.Group)
        self.assertEqual(
            pasted.AttachmentSupport[0][0], self._origin_feature(self.body2, "XY_Plane")
        )
        self.assertEqual(pasted.MapMode, "FlatFace")
        self.assertEqual(self._orphan_datums(), [])
        self.doc.recompute()
        self.assertTrue(pasted.isValid())

        # One undo removes the whole paste
        name = pasted.Name
        self.doc.undo()
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual({o.Name for o in self.doc.Objects}, before)

    def test_sketch_pasted_next_to_itself_stays_in_its_body(self):
        self._select(self.sketch)
        self._run("Std_Copy")
        self._run("Std_Paste")
        sketches = [o for o in self.body1.Group if o.isDerivedFrom("Sketcher::SketchObject")]
        self.assertEqual(len(sketches), 2)
        self.assertEqual(
            sketches[1].AttachmentSupport[0][0], self._origin_feature(self.body1, "XY_Plane")
        )

    def _paste_and_get_new(self, selected=None):
        before = {o.Name for o in self.doc.Objects}
        if selected is None:
            Gui.Selection.clearSelection()
        else:
            self._select(selected)
        self._run("Std_Paste")
        return [o for o in self.doc.Objects if o.Name not in before]

    def test_sketch_pasted_at_root_is_detached_at_its_global_placement(self):
        self.body1.Placement = App.Placement(App.Vector(5, 10, 0), App.Rotation(0, 0, 30))
        self.sketch.AttachmentOffset = App.Placement(App.Vector(1, 2, 3), App.Rotation())
        self.doc.recompute()
        expected = self.sketch.getGlobalPlacement()

        self._select(self.sketch)
        self._run("Std_Copy")
        new = self._paste_and_get_new()
        self.assertEqual(len(new), 1)
        pasted = new[0]
        self.assertTrue(pasted.isDerivedFrom("Sketcher::SketchObject"))
        self.assertIsNone(pasted.getParentGeoFeatureGroup())
        self.assertEqual(pasted.MapMode, "Deactivated")
        self.assertEqual(len(pasted.AttachmentSupport), 0)
        self.assertTrue(pasted.Placement.isSame(expected, 1e-7))
        self.assertEqual(self._orphan_datums(), [])
        self.doc.recompute()
        self.assertTrue(pasted.isValid())
        self.assertTrue(pasted.Placement.isSame(expected, 1e-7))

    def test_preference_restores_the_old_root_paste(self):
        self._select(self.sketch)
        self._run("Std_Copy")
        self.settings.SetBool(PARAM, False)
        new = self._paste_and_get_new()
        self.assertEqual(len(new), 2)
        pasted = [o for o in new if o.isDerivedFrom("Sketcher::SketchObject")][0]
        self.assertEqual(pasted.MapMode, "FlatFace")
        self.assertEqual(len(self._orphan_datums()), 1)

    def _make_pad(self, body, name, size=10):
        sketch = body.newObject("Sketcher::SketchObject", name + "Sketch")
        sketch.AttachmentSupport = [(self._origin_feature(body, "XY_Plane"), "")]
        sketch.MapMode = "FlatFace"
        corners = [
            App.Vector(0, 0, 0),
            App.Vector(size, 0, 0),
            App.Vector(size, size, 0),
            App.Vector(0, size, 0),
        ]
        for i in range(4):
            sketch.addGeometry(Part.LineSegment(corners[i], corners[(i + 1) % 4]))
        pad = body.newObject("PartDesign::Pad", name)
        pad.Profile = sketch
        pad.Length = size
        return pad

    def test_sketch_pasted_after_selected_sibling(self):
        second = self.body1.newObject("Sketcher::SketchObject", "Second")
        self.doc.recompute()
        self._select(second)
        self._run("Std_Copy")
        new = self._paste_and_get_new(self.sketch)
        self.assertEqual(len(new), 1)
        self.assertEqual(self.body1.Group, [self.sketch, new[0], second])

    def test_pad_pasted_after_selected_feature_is_inserted_in_the_chain(self):
        source = self._make_pad(self.body1, "Source", 5)
        first = self._make_pad(self.body2, "First")
        last = self._make_pad(self.body2, "Last", 20)
        self.doc.recompute()
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(source)
        Gui.Selection.addSelection(source.Profile[0])
        self._run("Std_Copy")
        self.assertEqual(self.dialogs, [])

        new = self._paste_and_get_new(first)
        pad = [o for o in new if o.isDerivedFrom("PartDesign::Pad")][0]
        sketch = [o for o in new if o.isDerivedFrom("Sketcher::SketchObject")][0]
        group = self.body2.Group
        self.assertEqual(group.index(sketch), group.index(first) + 1)
        self.assertEqual(group.index(pad), group.index(first) + 2)
        self.assertEqual(pad.BaseFeature, first)
        self.assertEqual(last.BaseFeature, pad)
        self.assertEqual(self.body2.Tip, last)
        self.doc.recompute()
        self.assertTrue(pad.isValid())
        self.assertTrue(last.isValid())

    def _set_active(self, key, obj):
        Gui.getDocument(self.doc_name).ActiveView.setActiveObject(key, obj)

    def test_nothing_selected_pastes_into_the_active_body(self):
        self._select(self.sketch)
        self._run("Std_Copy")
        self._set_active("pdbody", self.body2)
        new = self._paste_and_get_new()
        self.assertEqual(len(new), 1)
        self.assertIn(new[0], self.body2.Group)
        self.assertEqual(
            new[0].AttachmentSupport[0][0], self._origin_feature(self.body2, "XY_Plane")
        )

    def test_nothing_selected_pastes_into_the_active_part(self):
        part = self.doc.addObject("App::Part", "Part")
        self.doc.recompute()
        self._select(self.sketch)
        self._run("Std_Copy")
        self._set_active("part", part)
        new = self._paste_and_get_new()
        self.assertEqual(len(new), 1)
        self.assertIn(new[0], part.Group)
        self.assertEqual(new[0].AttachmentSupport[0][0], self._origin_feature(part, "XY_Plane"))

    def test_body_pasted_with_an_active_body_goes_to_the_root(self):
        self._select(self.body1)
        self._run("Std_Copy")
        self._set_active("pdbody", self.body2)
        new = self._paste_and_get_new()
        bodies = [o for o in new if o.isDerivedFrom("PartDesign::Body")]
        self.assertEqual(len(bodies), 1)
        self.assertIsNone(bodies[0].getParentGeoFeatureGroup())

    def test_body_copied_without_dialog(self):
        self._select(self.body1)
        self._run("Std_Copy")
        self.assertEqual(self.dialogs, [])
        Gui.Selection.clearSelection()
        before = len([o for o in self.doc.Objects if o.isDerivedFrom("PartDesign::Body")])
        self._run("Std_Paste")
        bodies = [o for o in self.doc.Objects if o.isDerivedFrom("PartDesign::Body")]
        self.assertEqual(len(bodies), before + 1)

    def test_copy_special_still_opens_the_dialog(self):
        self._select(self.sketch)
        self._run("Std_CopySpecial")
        self.assertEqual(len(self.dialogs), 1)

    def test_unexplained_dependency_still_opens_the_dialog(self):
        other = self.body1.newObject("Sketcher::SketchObject", "Other")
        other.AttachmentSupport = [(self.sketch, "")]
        other.MapMode = "FlatFace"
        self.doc.recompute()
        self._select(other)
        self._run("Std_Copy")
        self.assertEqual(len(self.dialogs), 1)

    def test_pad_on_a_face_of_the_previous_feature_still_opens_the_dialog(self):
        first = self._make_pad(self.body1, "First")
        second = self._make_pad(self.body1, "Second", 5)
        second.Profile[0].AttachmentSupport = [(first, "Face6")]
        self.doc.recompute()
        self._select(second)
        self._run("Std_Copy")
        self.assertEqual(len(self.dialogs), 1)

    def test_pad_copied_with_its_sketch_and_rebased_in_the_target_body(self):
        first = self._make_pad(self.body1, "First")
        second = self._make_pad(self.body1, "Second", 5)
        target = self._make_pad(self.body2, "Target")
        self.doc.recompute()
        self._select(second)
        self._run("Std_Copy")
        self.assertEqual(self.dialogs, [])

        new = self._paste_and_get_new(self.body2)
        # The pad and its sketch, not the previous feature of the source body
        self.assertEqual(len(new), 2)
        pad = [o for o in new if o.isDerivedFrom("PartDesign::Pad")][0]
        sketch = [o for o in new if o.isDerivedFrom("Sketcher::SketchObject")][0]
        self.assertEqual(pad.Profile[0], sketch)
        self.assertEqual(pad.BaseFeature, target)
        self.assertEqual(self.body2.Tip, pad)
        self.assertEqual(sketch.AttachmentSupport[0][0], self._origin_feature(self.body2, "XY_Plane"))
        self.assertEqual(self._orphan_datums(), [])
        self.doc.recompute()
        self.assertTrue(pad.isValid())
        # The source is untouched
        self.assertEqual(second.BaseFeature, first)
        self.assertEqual(self.body1.Tip, second)

    def test_preference_restores_the_old_copy(self):
        self.settings.SetBool(PARAM, False)
        self._select(self.sketch)
        self._run("Std_Copy")
        self.assertEqual(len(self.dialogs), 1)
