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
        pad = self.body1.newObject("PartDesign::Pad", "Pad")
        pad.Profile = self.sketch
        self.doc.recompute()
        self._select(pad)
        self._run("Std_Copy")
        self.assertEqual(len(self.dialogs), 1)

    def test_preference_restores_the_old_copy(self):
        self.settings.SetBool(PARAM, False)
        self._select(self.sketch)
        self._run("Std_Copy")
        self.assertEqual(len(self.dialogs), 1)
