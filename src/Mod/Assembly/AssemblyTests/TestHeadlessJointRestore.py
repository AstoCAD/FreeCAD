# SPDX-License-Identifier: LGPL-2.1-or-later
"""Current-API headless joints retain working providers after GUI restore."""

import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

import FreeCAD as App
import Part
import AssemblyApp
import JointObject
import UtilsAssembly

if App.GuiUp:
    import FreeCADGui as Gui
    import AssemblyGui
    from PySide import QtCore
    try:
        from PySide6 import QtTest
    except ImportError:
        from PySide2 import QtTest


# Produced by a genuine FreeCADCmd no-GUI run of the serialization regression.
# The archive contains native shapes and Document.xml, with no GuiDocument.xml.
_HEADLESS_FIXTURE = Path(__file__).with_name("HeadlessRevolute.FCStd")
_HEADLESS_FIXTURE_SHA256 = "c0086b06d5b8a59f887406ca8ba0194c5c81c4d0455822d3100db4d7bd52def9"


def _model_objects(doc):
    return tuple(doc.getObject(name) for name in ("Assembly", "Joints", "First", "Second", "Revolute"))


def _new_model(name, view_provider_type=None):
    doc = App.newDocument(name)
    assembly = doc.addObject("Assembly::AssemblyObject", "Assembly")
    joints = assembly.newObject("Assembly::JointGroup", "Joints")
    first = assembly.newObject("Part::Box", "First")
    second = assembly.newObject("Part::Box", "Second")
    second.Placement.Base = App.Vector(0, 0, 15)
    first.setPropertyStatus("Placement", "ReadOnly")
    doc.recompute()
    joint = joints.newObject("App::FeaturePython", "Revolute")
    JointObject.Joint(joint, JointObject.JointTypes.index("Revolute"))
    if view_provider_type is not None:
        view_provider_type(joint.ViewObject)
    # The current detached connector API used by TestDynamics.
    joint.Detach1 = True
    joint.Detach2 = True
    joint.Placement1.Base = App.Vector(0, 0, 10)
    joint.Placement2 = App.Placement()
    joint.Reference1 = (first, [""])
    joint.Reference2 = (second, [""])
    doc.recompute()
    return doc


class _CurrentModelChecks:
    def _check_model(self, doc):
        assembly, joints, first, second, joint = _model_objects(doc)
        self.assertTrue(all(obj is not None for obj in (assembly, joints, first, second, joint)))
        self.assertEqual(assembly.TypeId, "Assembly::AssemblyObject")
        self.assertEqual(joints.TypeId, "Assembly::JointGroup")
        self.assertIn(joints, assembly.Group)
        self.assertIn(first, assembly.Group)
        self.assertIn(second, assembly.Group)
        self.assertIn(joint, joints.Group)
        self.assertEqual(joint.TypeId, "App::FeaturePython")
        self.assertIsInstance(joint.Proxy, JointObject.Joint)
        self.assertEqual(joint.JointType, "Revolute")
        self.assertTrue(joint.Detach1 and joint.Detach2)
        self.assertEqual(joint.Reference1[0], first)
        self.assertEqual(joint.Reference2[0], second)
        self.assertEqual(list(joint.Reference1[1]), [""])
        self.assertEqual(list(joint.Reference2[1]), [""])
        self.assertEqual(joint.Proxy.getAssembly(joint), assembly)
        self.assertIn("ReadOnly", first.getPropertyStatus("Placement"))
        for obj in (first, second):
            self.assertFalse(obj.Shape.isNull())
            self.assertTrue(obj.Shape.isValid())
            self.assertEqual(len(obj.Shape.Solids), 1)
            self.assertAlmostEqual(obj.Shape.Volume, 1000.0, places=6)
        return assembly, joint


@unittest.skipIf(App.GuiUp, "Requires genuine no-GUI serialization")
class TestHeadlessJointSerialization(_CurrentModelChecks, unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-headless-joint-")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)

    def test_save_and_restore_current_api_revolute_without_gui(self):
        self.assertFalse(App.GuiUp)
        doc = _new_model("HeadlessJointSerialization")
        assembly, joint = self._check_model(doc)
        self.assertIsNone(joint.ViewObject)
        self.assertEqual(assembly.solve(), 0)
        self.assertNotIn("Invalid", joint.State)
        self.assertNotIn("Invalid", assembly.State)
        path = Path(self.temp.name) / "HeadlessRevolute.FCStd"
        doc.saveAs(str(path))
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size, 1000)
        App.closeDocument(doc.Name)
        restored = App.openDocument(str(path))
        assembly, joint = self._check_model(restored)
        self.assertIsNone(joint.ViewObject)
        self.assertEqual(assembly.solve(), 0)
        self.assertNotIn("Invalid", joint.State)
        with zipfile.ZipFile(path) as archive:
            self.assertIn("Document.xml", archive.namelist())
            self.assertNotIn("GuiDocument.xml", archive.namelist())


class _CustomJointViewProvider(JointObject.ViewProviderJoint):
    def __init__(self, vobj):
        self.custom_marker = "custom joint provider"
        super().__init__(vobj)

    def dumps(self):
        return self.custom_marker

    def loads(self, state):
        self.custom_marker = state


@unittest.skipUnless(App.GuiUp, "Requires a native FreeCAD GUI process")
class TestHeadlessJointRestoreGui(_CurrentModelChecks, unittest.TestCase):
    def setUp(self):
        self.before = set(App.listDocuments())
        self.previous = App.ActiveDocument.Name if App.ActiveDocument else None
        self.previous_workbench = Gui.activeWorkbench().name()
        self.doc = None
        self.temp = tempfile.TemporaryDirectory(prefix="freecad-headless-joint-gui-")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._cleanup)
        Gui.activateWorkbench("AssemblyWorkbench")
        Gui.Selection.clearSelection()

    def _cleanup(self):
        for name in set(App.listDocuments()) - self.before:
            gui_doc = Gui.getDocument(name)
            if Gui.Control.activeDialog(gui_doc):
                Gui.Control.closeDialog(gui_doc)
            if gui_doc.getInEdit():
                gui_doc.resetEdit()
            App.closeDocument(name)
        if self.previous in App.listDocuments():
            App.setActiveDocument(self.previous)
        Gui.activateWorkbench(self.previous_workbench)
        Gui.Selection.clearSelection()
        Gui.updateGui()

    def _wait(self, predicate, message):
        clock = QtCore.QElapsedTimer()
        clock.start()
        while not predicate() and clock.elapsed() < 2000:
            Gui.updateGui()
            QtTest.QTest.qWait(20)
        self.assertTrue(predicate(), message)

    def _activate_and_redraw(self):
        assembly, joint = self._check_model(self.doc)
        Gui.Selection.clearSelection()
        Gui.runCommand("Assembly_ActivateAssembly")
        self._wait(lambda: assembly.ViewObject.isInEditMode(),
                   "Actual Assembly_ActivateAssembly did not enter native edit mode")
        self.assertEqual(UtilsAssembly.activeAssembly(), assembly)
        # Native solve reports Python callback failures without rethrowing them.
        # Also call the exact production callback to expose its actual exception.
        try:
            joint.Proxy.redrawJointPlacements(joint)
        except AttributeError as error:
            self.fail("Actual joint redraw failed after GUI restore: " + str(error))
        proxy = joint.ViewObject.Proxy
        self.assertIsInstance(proxy, JointObject.ViewProviderJoint,
                              "The actual joint marker view provider was not restored")
        self.assertTrue(hasattr(proxy, "switch_JCS1") and hasattr(proxy, "switch_JCS2"))
        for marker in (proxy.switch_JCS1, proxy.switch_JCS2):
            self.assertGreater(marker.getNumChildren(), 0)
        self.assertEqual(assembly.solve(), 0)
        self.assertNotIn("Invalid", joint.State)
        self._check_model(self.doc)

    def test_gui_created_joint_provider_control(self):
        self.doc = _new_model("GuiJointProviderControl", JointObject.ViewProviderJoint)
        joint = self.doc.getObject("Revolute")
        provider = joint.ViewObject.Proxy
        self._activate_and_redraw()
        self.assertIs(joint.ViewObject.Proxy, provider)

    def test_gui_created_saved_and_restored_control(self):
        self.doc = _new_model("GuiJointRoundtripControl", JointObject.ViewProviderJoint)
        path = Path(self.temp.name) / "GuiRoundtrip.FCStd"
        self.doc.saveAs(str(path))
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(str(path))
        self._activate_and_redraw()
        self.assertIs(type(self.doc.getObject("Revolute").ViewObject.Proxy), JointObject.ViewProviderJoint)

    def test_custom_saved_joint_provider_is_preserved_control(self):
        self.doc = _new_model("CustomJointRoundtripControl", _CustomJointViewProvider)
        path = Path(self.temp.name) / "CustomRoundtrip.FCStd"
        self.doc.saveAs(str(path))
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(str(path))
        provider = self.doc.getObject("Revolute").ViewObject.Proxy
        self.assertIsInstance(provider, _CustomJointViewProvider)
        self.assertEqual(provider.custom_marker, "custom joint provider")
        self._activate_and_redraw()
        self.assertIs(self.doc.getObject("Revolute").ViewObject.Proxy, provider)

    def test_actual_headless_fixture_restores_activates_and_redraws(self):
        self.assertEqual(hashlib.sha256(_HEADLESS_FIXTURE.read_bytes()).hexdigest(),
                         _HEADLESS_FIXTURE_SHA256)
        with zipfile.ZipFile(_HEADLESS_FIXTURE) as archive:
            self.assertNotIn("GuiDocument.xml", archive.namelist())
        self.doc = App.openDocument(str(_HEADLESS_FIXTURE))
        # No view-provider initialization is performed by the candidate fixture.
        self._activate_and_redraw()
        self.assertEqual(hashlib.sha256(_HEADLESS_FIXTURE.read_bytes()).hexdigest(),
                         _HEADLESS_FIXTURE_SHA256)
